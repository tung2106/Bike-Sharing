"""Shared feature, preprocessing, and metric helpers for local experiments."""

import json
from pathlib import Path

import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

NUMERIC = ['temp', 'atemp', 'hum', 'windspeed']
BINARY = ['yr', 'holiday', 'workingday']
CATEGORICAL = ['season', 'mnth', 'weekday', 'weathersit']


def save_json(path, data):
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False),
        encoding='utf-8',
    )


def feature_columns(dataset):
    if dataset not in ('day', 'hour'):
        raise ValueError("dataset phải là 'day' hoặc 'hour'")
    categorical = CATEGORICAL + (['hr'] if dataset == 'hour' else [])
    return NUMERIC + BINARY + categorical, categorical


def make_preprocessor(dataset):
    _, categorical = feature_columns(dataset)
    return ColumnTransformer(
        [
            ('numeric', SimpleImputer(strategy='median'), NUMERIC),
            ('binary', SimpleImputer(strategy='most_frequent'), BINARY),
            (
                'category',
                Pipeline(
                    [
                        ('imputer', SimpleImputer(strategy='most_frequent')),
                        (
                            'encoder',
                            OneHotEncoder(handle_unknown='ignore', sparse_output=False),
                        ),
                    ]
                ),
                categorical,
            ),
        ],
        remainder='drop',
        verbose_feature_names_out=False,
    )


def regression_metrics(actual, predicted):
    return {
        'RMSE': float(np.sqrt(mean_squared_error(actual, predicted))),
        'MAE': float(mean_absolute_error(actual, predicted)),
        'R2': float(r2_score(actual, predicted)),
    }
