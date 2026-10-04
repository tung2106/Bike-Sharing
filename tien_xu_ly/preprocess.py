"""Prepare Bike Sharing CSVs using only Python's standard library.

Run from project root: python tien_xu_ly/preprocess.py
Outputs: du_lieu/da_xu_ly/{day,hour}/{train,validation,test}.csv
"""

import argparse
import csv
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import median


NUMERIC = ['temp', 'atemp', 'hum', 'windspeed']
BINARY = ['yr', 'holiday', 'workingday']
CATEGORICAL = ['season', 'mnth', 'weekday', 'weathersit']
MISSING = {'', 'na', 'n/a', 'nan', 'null', 'none', '?'}


def number(value):
    if value is None or value.strip().lower() in MISSING:
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def write_csv(path, columns, rows):
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def fit_preprocessor(train, categorical):
    """Learn imputation and category vocabulary exclusively from train."""
    fill = {}
    categories = {}
    for column in NUMERIC + BINARY + categorical:
        observed = [row[column] for row in train if row[column] is not None]
        if not observed:
            raise ValueError(f'Entire training column is missing: {column}')
        counts = Counter(observed)
        fill[column] = (median(observed) if column in NUMERIC else
                        min(counts, key=lambda v: (-counts[v], v)))
        if column in categorical:
            categories[column] = sorted(set(observed))
    features = NUMERIC + BINARY
    for column, values in categories.items():
        features += [f'{column}_{int(v)}' for v in values]
        features += [f'{column}_unknown']
    return {'fill_values': fill, 'categories': categories,
            'feature_names': features, 'target': 'cnt',
            'numeric_scaling': 'preserve original normalized values',
            'fit_partition': 'train'}


def transform(rows, state):
    """Apply saved state; never learn from validation/test or new data."""
    result = []
    for row in rows:
        values = {c: state['fill_values'][c] if row[c] is None else row[c]
                  for c in state['fill_values']}
        encoded = {c: values[c] for c in NUMERIC + BINARY}
        for column, vocabulary in state['categories'].items():
            encoded.update({f'{column}_{int(v)}': int(values[column] == v)
                            for v in vocabulary})
            encoded[f'{column}_unknown'] = int(values[column] not in vocabulary)
        result.append(encoded)
    return result


def prepare(source, destination):
    with source.open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        raw = list(reader)
        columns = reader.fieldnames
    if not raw:
        raise ValueError(f'Empty dataset: {source}')
    categorical = CATEGORICAL + (['hr'] if 'hr' in columns else [])
    required = ['instant', 'dteday', 'cnt'] + NUMERIC + BINARY + categorical
    if set(required) - set(columns):
        raise ValueError(f'Missing columns: {set(required) - set(columns)}')
    missing = {c: sum(r[c].strip().lower() in MISSING for r in raw) for c in columns}
    seen, rows = set(), []
    duplicates = missing_target = 0
    for raw_row in raw:
        signature = tuple(raw_row[c] for c in columns)
        if signature in seen:
            duplicates += 1
            continue
        seen.add(signature)
        row = {c: number(raw_row[c]) for c in NUMERIC + BINARY + categorical + ['cnt']}
        if row['cnt'] is None:
            missing_target += 1
            continue
        if row['cnt'] < 0 or not row['cnt'].is_integer():
            raise ValueError(f'Invalid target at instant {raw_row["instant"]}')
        for c in BINARY + categorical:
            if row[c] is not None and not row[c].is_integer():
                raise ValueError(f'Noninteger category: {c}')
        for c in BINARY:
            if row[c] is not None and row[c] not in (0, 1):
                raise ValueError(f'Invalid binary value: {c}')
        # A missing date/hour cannot safely be imputed for chronological splitting.
        date = datetime.strptime(raw_row['dteday'], '%Y-%m-%d')
        if 'hr' in categorical and (row['hr'] is None or not 0 <= row['hr'] <= 23):
            raise ValueError('Missing/invalid hour: cannot order records safely')
        row.update(instant=raw_row['instant'], dteday=date.strftime('%Y-%m-%d'))
        row['timestamp'] = row['dteday'] + (f'T{int(row["hr"]):02d}:00:00' if 'hr' in categorical else '')
        rows.append(row)
    rows.sort(key=lambda r: r['timestamp'])
    if len({r['timestamp'] for r in rows}) != len(rows):
        raise ValueError('Conflicting records at the same timestamp')
    n = len(rows)
    n_train, n_val = n * 70 // 100, n * 15 // 100
    partitions = {'train': rows[:n_train],
                  'validation': rows[n_train:n_train + n_val],
                  'test': rows[n_train + n_val:]}
    if any(not part for part in partitions.values()):
        raise ValueError('Too few records to split into three nonempty partitions')
    state = fit_preprocessor(partitions['train'], categorical)
    destination.mkdir(parents=True, exist_ok=True)
    report = {'source': source.name, 'original_rows': len(raw),
              'missing_cells_original': missing,
              'duplicates_removed': duplicates, 'missing_target_rows_removed': missing_target,
              'retained_rows': n, 'target': 'cnt',
              'excluded_features': ['instant', 'dteday', 'casual', 'registered'],
              'split_method': 'chronological; floor(70% N), floor(15% N), remainder',
              'feature_count': len(state['feature_names']), 'splits': {}}
    manifest = []
    for name, part in partitions.items():
        encoded = transform(part, state)
        for x, original in zip(encoded, part):
            if list(x) != state['feature_names'] or not all(math.isfinite(v) for v in x.values()):
                raise AssertionError('Invalid encoded feature matrix')
            x['cnt'] = int(original['cnt'])
            manifest.append({c: original[c] for c in ['instant', 'dteday', 'timestamp']} | {'split': name})
        write_csv(destination / f'{name}.csv', state['feature_names'] + ['cnt'], encoded)
        report['splits'][name] = {
            'rows': len(part), 'percentage': round(100 * len(part) / n, 4),
            'start': part[0]['timestamp'], 'end': part[-1]['timestamp'],
            'imputed_cells': {c: sum(r[c] is None for r in part) for c in state['fill_values']},
            'unknown_categories': {c: sum(x[f'{c}_unknown'] for x in encoded) for c in categorical}}
    write_csv(destination / 'split_manifest.csv', ['instant', 'dteday', 'timestamp', 'split'], manifest)
    for filename, data in [('preprocessor.json', state), ('report.json', report)]:
        (destination / filename).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    assert sum(len(p) for p in partitions.values()) == n
    assert partitions['train'][-1]['timestamp'] < partitions['validation'][0]['timestamp']
    assert partitions['validation'][-1]['timestamp'] < partitions['test'][0]['timestamp']
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    project_root = Path(__file__).resolve().parent.parent
    parser.add_argument('--input-dir', type=Path, default=project_root / 'du_lieu' / 'goc')
    parser.add_argument('--output-dir', type=Path, default=project_root / 'du_lieu' / 'da_xu_ly')
    args = parser.parse_args()
    for name in ['day', 'hour']:
        report = prepare(args.input_dir / f'{name}.csv', args.output_dir / name)
        print(name, {k: v['rows'] for k, v in report['splits'].items()},
              f"features={report['feature_count']}")


if __name__ == '__main__':
    main()
