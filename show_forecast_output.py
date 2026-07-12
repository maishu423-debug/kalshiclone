"""
Run backend/kalshi_api/forecast.py once and print its cached output.

Usage:
    python show_forecast_output.py
    python show_forecast_output.py --strike 85
"""
import argparse
import contextlib
import io
import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
BACKEND_DIR = PROJECT_ROOT / "backend"
ENV_FILE = BACKEND_DIR / ".env"


def load_env_file(path):
    """Tiny .env loader so this script does not need python-dotenv."""
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def sanitize_output(text):
    api_key = os.getenv("ACCUWEATHER_API_KEY")
    if api_key:
        text = text.replace(api_key, "***")
    return text


def main():
    parser = argparse.ArgumentParser(
        description="Run the forecast refresh once and print the JSON cache."
    )
    parser.add_argument(
        "--strike",
        type=float,
        help="Optional temperature strike for ensemble_prob_above().",
    )
    args = parser.parse_args()

    load_env_file(ENV_FILE)
    sys.path.insert(0, str(BACKEND_DIR))

    from kalshi_api import forecast

    refresh_output = io.StringIO()
    with contextlib.redirect_stdout(refresh_output):
        forecast._do_refresh()
    warning_text = sanitize_output(refresh_output.getvalue()).strip()
    if warning_text:
        print(warning_text, file=sys.stderr)

    cache = forecast.get_forecast_cache()

    if args.strike is not None:
        cache["ensemble_prob_above"] = {
            "strike_f": args.strike,
            "probability": forecast.ensemble_prob_above(args.strike, cache["results"]),
        }

    print(json.dumps(cache, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
