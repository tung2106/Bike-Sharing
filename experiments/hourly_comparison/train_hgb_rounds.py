"""Choose HGB boosting rounds on chronological validation, then export one model."""

from datetime import datetime, timezone
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'training'))
from model_utils import save_json
from verify_hgb import read_json, scores, sha256

RUNS = Path(__file__).resolve().parent / 'runs'
REFERENCE = RUNS / '20261025_024202'
RF_PREVIOUS_DAY = ROOT / (
    'experiments/rf85_previous_day/runs/20261102T154526002202Z/test_predictions.csv'
)
ROUNDS = (100, 200, 300, 400, 600)


def align_archive(path, test):
    archive = pd.read_csv(path, parse_dates=['timestamp'])
    np.testing.assert_array_equal(archive.timestamp, test.timestamp)
    np.testing.assert_array_equal(archive.cnt, test.cnt)
    return archive


def run():
    source = ROOT / 'data/raw/hour.csv'
    model_path = REFERENCE / 'model.joblib'
    provenance = read_json(REFERENCE / 'provenance.json')
    source_hash = sha256(source)
    reference_hash = sha256(model_path)
    assert source_hash == provenance['source_sha256']
    assert reference_hash == provenance['model_sha256']
    reference = joblib.load(model_path)
    assert reference['versions']['scikit-learn'] == sklearn.__version__
    template = reference['pipeline']
    model = template.named_steps['model']
    assert isinstance(model, HistGradientBoostingRegressor)
    assert not model.early_stopping and model.n_iter_ == 400
    features = reference['features']
    assert list(template.feature_names_in_) == features

    raw = pd.read_csv(source, parse_dates=['dteday'])
    raw['timestamp'] = raw.dteday + pd.to_timedelta(raw.hr, unit='h')
    raw = raw.sort_values('timestamp').reset_index(drop=True)
    assert raw.timestamp.is_unique
    plan = read_json(REFERENCE / 'plan.json')
    folds = plan['folds']
    cut = folds[-1]['train_rows'] + folds[-1]['validation_rows']
    assert (cut, len(raw) - cut) == (14771, 2608)

    validation = []
    for fold_number, fold in enumerate(folds, 1):
        start = fold['train_rows']
        end = start + fold['validation_rows']
        train, valid = raw.iloc[:start], raw.iloc[start:end]
        assert str(train.timestamp.iloc[-1]) == fold['train_end']
        assert str(valid.timestamp.iloc[0]) == fold['validation_start']
        assert str(valid.timestamp.iloc[-1]) == fold['validation_end']
        assert train.timestamp.iloc[-1] < valid.timestamp.iloc[0] and end <= cut
        for rounds in ROUNDS:
            pipeline = clone(template).set_params(model__max_iter=rounds)
            pipeline.fit(train[features], train.cnt)
            assert pipeline.named_steps['model'].n_iter_ == rounds
            predicted = pipeline.predict(valid[features])
            assert np.isfinite(predicted).all() and (predicted >= 0).all()
            mae = mean_absolute_error(valid.cnt, predicted)
            validation.append(
                dict(
                    fold=fold_number,
                    rounds=rounds,
                    train_rows=len(train),
                    validation_rows=len(valid),
                    MAE=mae,
                )
            )
            print(f'Fold {fold_number}, {rounds} rounds: MAE={mae:.6f}', flush=True)

    validation = pd.DataFrame(validation)
    previous_folds = pd.read_csv(REFERENCE / 'validation_folds.csv')
    old = previous_folds[previous_folds.candidate == 'hist_boost_poisson'].sort_values(
        'fold'
    )
    np.testing.assert_allclose(
        validation.loc[validation.rounds == 400, 'MAE'], old.MAE, rtol=1e-9
    )
    summary = validation.pivot(index='rounds', columns='fold', values='MAE')
    summary.columns = [f'fold_{fold}_MAE' for fold in summary.columns]
    summary = summary.reset_index()
    summary['pooled_MAE'] = [
        np.average(rows.MAE, weights=rows.validation_rows)
        for _, rows in validation.groupby('rounds', sort=True)
    ]
    summary = summary.sort_values(['pooled_MAE', 'rounds'])
    winner = int(summary.iloc[0].rounds)
    print(f'Selected by validation MAE before test: {winner} rounds', flush=True)

    train, test = raw.iloc[:cut], raw.iloc[cut:]
    assert str(test.timestamp.iloc[0]) == plan['test']['start']
    assert str(test.timestamp.iloc[-1]) == plan['test']['end']
    fitted = (
        clone(template)
        .set_params(model__max_iter=winner)
        .fit(train[features], train.cnt)
    )
    assert fitted.named_steps['model'].n_iter_ == winner
    predicted = fitted.predict(test[features])
    measured = scores(test.cnt, predicted)

    archive = align_archive(REFERENCE / 'test_predictions.csv', test)
    archive['hgb400_reference'] = archive['selected_refit_85']
    archive['selected_refit_85'] = predicted
    archive['rf85_previous_day'] = align_archive(RF_PREVIOUS_DAY, test)[
        'rf85_previous_day'
    ]
    comparison = {
        'HGB 400 (reference)': scores(test.cnt, archive.hgb400_reference),
        f'HGB {winner} (selected)': measured,
    }
    expected = reference['report']['test']
    np.testing.assert_allclose(
        list(comparison['HGB 400 (reference)'].values()),
        [expected[key] for key in measured],
        rtol=1e-9,
    )
    selection = dict(
        candidate='hist_boost_poisson',
        algorithm=type(model).__name__,
        candidate_rounds=list(ROUNDS),
        selected_rounds=winner,
        best_params=fitted.named_steps['model'].get_params(),
        selection_metric='Minimum pooled validation MAE; fewer rounds break ties',
        validation=summary.iloc[0].to_dict(),
        folds=folds,
    )
    now = datetime.now(timezone.utc)
    report = dict(
        test=measured,
        baseline_test=reference['report']['baseline_test'],
        comparison=comparison,
        selection=selection,
        split=dict(
            train_rows=cut,
            test_rows=len(test),
            test_start=plan['test']['start'],
            test_end=plan['test']['end'],
        ),
        previous_day_comparison=True,
        evaluation_note=reference['report']['evaluation_note'],
        evaluated_at_utc=now.isoformat(timespec='seconds'),
    )
    bundle = dict(
        reference,
        pipeline=fitted,
        report=report,
        name=f'HistGradientBoosting 85% · {winner} vòng',
    )
    destination = RUNS / now.strftime('%Y%m%dT%H%M%S%fZ_hgb_rounds')
    with TemporaryDirectory(dir=RUNS) as temporary:
        out = Path(temporary) / 'ready'
        out.mkdir()
        validation.to_csv(out / 'validation_folds.csv', index=False)
        summary.to_csv(out / 'validation_summary.csv', index=False)
        archive.to_csv(out / 'test_predictions.csv', index=False)
        save_json(out / 'selection.json', selection)
        save_json(out / 'metrics.json', report)
        joblib.dump(bundle, out / 'model.joblib', compress=3)
        reloaded = joblib.load(out / 'model.joblib')
        np.testing.assert_allclose(
            reloaded['pipeline'].predict(test[features]), predicted, rtol=0, atol=1e-8
        )
        save_json(
            out / 'provenance.json',
            dict(
                source_sha256=source_hash,
                reference_sha256=reference_hash,
                model_sha256=sha256(out / 'model.joblib'),
                test_predictions_sha256=sha256(out / 'test_predictions.csv'),
                script_sha256=sha256(Path(__file__)),
                versions=reference['versions'],
            ),
        )
        out.rename(destination)
    print(summary.to_string(index=False), flush=True)
    print(pd.DataFrame.from_dict(comparison, orient='index').to_string(), flush=True)
    print(f'RUN={destination}', flush=True)


if __name__ == '__main__':
    with threadpool_limits(limits=4):
        run()
