"""Local model and port settings shared by the API and launcher."""

import os
from pathlib import Path

WEBSITE_DIR = Path(__file__).resolve().parent
HGB_MODEL_PATH = (
    WEBSITE_DIR.parent
    / 'experiments/hourly_comparison/runs/20261111T160820094592Z_hgb_rounds/model.joblib'
)
HGB_PORT = 8002


def configured_model_path():
    custom = os.environ.get('BIKE_MODEL_PATH')
    return WEBSITE_DIR / custom if custom else HGB_MODEL_PATH
