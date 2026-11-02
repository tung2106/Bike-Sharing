"""Compare RF, HGB and a validation-selected weighted prediction average."""
import os
os.environ.setdefault('OMP_NUM_THREADS', '4')
import sys
import hashlib
from pathlib import Path
from datetime import datetime, timezone
import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import VotingRegressor
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'experiments/hourly_v2'))
from train_experiment import candidates, FEATURES, regression_metrics, save_json


def main():
    out = Path(__file__).parent / 'runs' / datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    out.mkdir(parents=True, exist_ok=False)
    source = ROOT / 'du_lieu/goc/hour.csv'
    original_path = ROOT / 'website/models/model.joblib'
    original = joblib.load(original_path)
    templates = candidates(original)
    rf, hgb = templates['rf_original'], templates['hist_boost_poisson']
    df = pd.read_csv(source)
    df['timestamp'] = pd.to_datetime(df.dteday) + pd.to_timedelta(df.hr, unit='h')
    df = df.sort_values('timestamp').reset_index(drop=True)
    assert not df.timestamp.duplicated().any()
    assert np.isfinite(df[FEATURES + ['cnt']].to_numpy()).all()
    assert (df.cnt >= 0).all()
    n = len(df)
    cut70, cut85 = n * 70 // 100, n * 70 // 100 + n * 15 // 100
    folds = [(n*50//100, n*60//100), (n*60//100, cut70), (cut70, cut85)]
    weights = [i / 10 for i in range(11)]
    plan = dict(features=FEATURES, rf_weights=weights,
        selection='Pooled validation MAE, then RMSE, then RF weight ascending; select interior weight separately from overall winner.',
        folds=[dict(train_rows=a, validation_rows=b-a, train_end=str(df.timestamp.iloc[a-1]),
                    validation_end=str(df.timestamp.iloc[b-1])) for a,b in folds],
        fit_rows=cut85, test_rows=n-cut85,
        test_start=str(df.timestamp.iloc[cut85]), test_end=str(df.timestamp.iloc[-1]),
        caveat='Previously viewed historical test and previously selected HGB configuration; exploratory comparison, not independent confirmation.',
        input_caveat='Observed weather, not archived weather forecasts. Same feature columns; preprocessing differs by model.',
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        original_sha256=hashlib.sha256(original_path.read_bytes()).hexdigest(),
        rf_params=rf.named_steps['model'].get_params(), hgb_params=hgb.named_steps['model'].get_params())
    save_json(out/'plan.json', plan)  # Freeze the grid BEFORE computing scores.
    validation, fold_scores = [], []
    for fold, (a,b) in enumerate(folds, 1):
        train, valid = df.iloc[:a], df.iloc[a:b]
        fitted_rf = clone(rf).fit(train[FEATURES], train.cnt)
        fitted_hgb = clone(hgb).fit(train[FEATURES], train.cnt)
        pr, ph = fitted_rf.predict(valid[FEATURES]), fitted_hgb.predict(valid[FEATURES])
        part = valid[['timestamp','cnt']].copy()
        part['fold'], part['rf'], part['hgb'] = fold, pr, ph
        validation.append(part)
        for w in weights:
            fold_scores.append(dict(fold=fold, rf_weight=w, **regression_metrics(valid.cnt, w*pr+(1-w)*ph)))
        print('Completed chronological fold', fold, flush=True)
    oof = pd.concat(validation, ignore_index=True)
    oof.to_csv(out/'validation_predictions.csv', index=False)
    pd.DataFrame(fold_scores).to_csv(out/'validation_folds.csv', index=False)
    ranking = pd.DataFrame([dict(rf_weight=w, **regression_metrics(oof.cnt,w*oof.rf+(1-w)*oof.hgb))
                            for w in weights]).sort_values(['MAE','RMSE','rf_weight'])
    ranking.to_csv(out/'validation_weights.csv',index=False)
    mixed = ranking.loc[ranking.rf_weight.between(.1,.9)].iloc[0]
    w = float(mixed.rf_weight)
    selection = dict(best_overall=ranking.iloc[0].to_dict(), best_mixed=mixed.to_dict(),
                     export='Best interior-weight blend for experimental comparison; not automatically the best overall model.')
    save_json(out/'selection.json',selection)  # No test results used to select w.
    print('SELECTED BEFORE TEST:', selection, flush=True)
    train, test = df.iloc[:cut85], df.iloc[cut85:]
    # VotingRegressor clones and fits each complete pipeline on the same 85%.
    ensemble = VotingRegressor([('rf',rf),('hgb',hgb)], weights=[w,1-w], n_jobs=1)
    ensemble.fit(train[FEATURES],train.cnt)
    pr = ensemble.named_estimators_['rf'].predict(test[FEATURES])
    ph = ensemble.named_estimators_['hgb'].predict(test[FEATURES])
    blend = ensemble.predict(test[FEATURES])
    np.testing.assert_allclose(blend,w*pr+(1-w)*ph)
    predictions = test[['timestamp','hr','workingday','cnt']].copy()
    rows, groups = [], []
    for name, pred in dict(random_forest=pr,hist_gradient_boosting=ph,weighted_blend=blend).items():
        assert np.isfinite(pred).all() and (pred>=0).all()
        predictions[name] = pred
        rows.append(dict(model=name, **regression_metrics(test.cnt,pred)))
        for group, mask in dict(peak_hours=test.hr.isin([7,8,9,16,17,18,19]),
                               workingday=test.workingday.eq(1),non_workingday=test.workingday.eq(0)).items():
            groups.append(dict(model=name,group=group,rows=int(mask.sum()),
                               **regression_metrics(test.loc[mask,'cnt'],pred[mask.to_numpy()])))
    predictions.to_csv(out/'test_predictions.csv',index=False)
    pd.DataFrame(rows).to_csv(out/'test_comparison.csv',index=False)
    pd.DataFrame(groups).to_csv(out/'test_groups.csv',index=False)
    metrics = {k:rows[-1][k] for k in ['MAE','RMSE','R2']}
    report = dict(test=metrics,selection=selection,comparison=rows,evaluation_note=plan['caveat'])
    bundle = dict(pipeline=ensemble,features=FEATURES,target='cnt',dataset='hour',
        name=f'RF {w:.0%} + HGB {1-w:.0%} · thử nghiệm kết hợp',versions=original['versions'],report=report)
    import sklearn, platform
    bundle['versions'] = dict(python=platform.python_version(),numpy=np.__version__,pandas=pd.__version__,
                              **{'scikit-learn':sklearn.__version__,'joblib':joblib.__version__})
    joblib.dump(bundle,out/'model.joblib',compress=3)
    loaded = joblib.load(out/'model.joblib')
    np.testing.assert_allclose(loaded['pipeline'].predict(test[FEATURES]),blend)
    save_json(out/'metrics.json',report)
    save_json(out/'provenance.json',dict(versions=bundle['versions'],
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        model_sha256=hashlib.sha256((out/'model.joblib').read_bytes()).hexdigest()))
    print(ranking.to_string(index=False),flush=True)
    print(pd.DataFrame(rows).to_string(index=False),flush=True)
    print('OUTPUT:',out,flush=True)


if __name__=='__main__':
    with threadpool_limits(limits=4):
        main()
