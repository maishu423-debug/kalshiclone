"""Append-only forecast history log, stored in a Google Sheet instead of the
local SQL database.

Render's free tier wipes the local disk (including SQLite) on every restart
or redeploy, so a history log written there doesn't survive. A Google Sheet,
written via a service account, does.

Configure via env vars:
  GOOGLE_SERVICE_ACCOUNT_JSON  - full service account JSON as a string
  GOOGLE_SERVICE_ACCOUNT_PATH  - path to a service account JSON file (local dev)
  GOOGLE_SHEETS_ID             - spreadsheet ID for forecast history
  GOOGLE_TRADES_SHEET_ID       - spreadsheet ID for trade history
                                  (optional — falls back to GOOGLE_SHEETS_ID)

If none of these are configured, both public functions fail gracefully
(print a warning, return "[]" / no-op) rather than raising.
"""
import json
import os
import threading
from datetime import datetime, timezone

HEADER = ["timestamp", "current_temp_f", "model_forecast_f"]
TRADES_WORKSHEET_TITLE = "Trades"
TRADES_HEADER = [
    "timestamp", "market_ticker", "market_label", "action", "side",
    "price_cents", "contracts", "cash_delta_cents", "realized_pl_cents",
]

_client_lock = threading.Lock()
_worksheet = None
_init_failed = False

_trades_client_lock = threading.Lock()
_trades_worksheet = None
_trades_init_failed = False


def _open_sheet(sheet_id):
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    raw_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    json_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_PATH")

    if not sheet_id:
        raise RuntimeError("No spreadsheet ID configured")

    if raw_json:
        info = json.loads(raw_json)
        creds = Credentials.from_service_account_info(info, scopes=scopes)
    elif json_path:
        creds = Credentials.from_service_account_file(json_path, scopes=scopes)
    else:
        raise RuntimeError(
            "Neither GOOGLE_SERVICE_ACCOUNT_JSON nor GOOGLE_SERVICE_ACCOUNT_PATH is set"
        )

    client = gspread.authorize(creds)
    return client.open_by_key(sheet_id)


def _build_worksheet():
    sheet_id = os.environ.get("GOOGLE_SHEETS_ID")
    if not sheet_id:
        raise RuntimeError("GOOGLE_SHEETS_ID is not set")

    worksheet = _open_sheet(sheet_id).sheet1

    if not worksheet.get_all_values():
        worksheet.append_row(HEADER)

    return worksheet


def _get_worksheet():
    """Lazily build and cache the worksheet handle. Thread-safe."""
    global _worksheet, _init_failed

    if _worksheet is not None:
        return _worksheet
    if _init_failed:
        return None

    with _client_lock:
        if _worksheet is not None:
            return _worksheet
        if _init_failed:
            return None
        try:
            _worksheet = _build_worksheet()
        except Exception as exc:
            _init_failed = True
            print(f"[sheets_history] Google Sheets not configured, skipping ({exc})")
            return None

    return _worksheet


def _build_trades_worksheet():
    import gspread

    sheet_id = os.environ.get("GOOGLE_TRADES_SHEET_ID") or os.environ.get("GOOGLE_SHEETS_ID")
    if not sheet_id:
        raise RuntimeError("Neither GOOGLE_TRADES_SHEET_ID nor GOOGLE_SHEETS_ID is set")

    sheet = _open_sheet(sheet_id)
    try:
        worksheet = sheet.worksheet(TRADES_WORKSHEET_TITLE)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sheet.add_worksheet(title=TRADES_WORKSHEET_TITLE, rows=1000, cols=len(TRADES_HEADER))

    if not worksheet.get_all_values():
        worksheet.append_row(TRADES_HEADER)

    return worksheet


def _get_trades_worksheet():
    """Lazily build and cache the Trades worksheet handle. Thread-safe."""
    global _trades_worksheet, _trades_init_failed

    if _trades_worksheet is not None:
        return _trades_worksheet
    if _trades_init_failed:
        return None

    with _trades_client_lock:
        if _trades_worksheet is not None:
            return _trades_worksheet
        if _trades_init_failed:
            return None
        try:
            _trades_worksheet = _build_trades_worksheet()
        except Exception as exc:
            _trades_init_failed = True
            print(f"[sheets_history] Google Sheets Trades tab not configured, skipping ({exc})")
            return None

    return _trades_worksheet


def append_snapshot(current_temp_f, model_forecast_f):
    """Append one forecast-history row. No-ops if Sheets isn't configured."""
    worksheet = _get_worksheet()
    if worksheet is None:
        return

    try:
        timestamp = datetime.now(timezone.utc).isoformat()
        worksheet.append_row([timestamp, current_temp_f, model_forecast_f])
    except Exception as exc:
        print(f"[sheets_history] failed to append snapshot ({exc})")


def get_recent_snapshots(limit=100):
    """Return up to `limit` most recent snapshots, newest first, as dicts
    shaped like {"timestamp", "current_temp_f", "model_forecast_f"}.
    Returns [] if Sheets isn't configured or the read fails.
    """
    worksheet = _get_worksheet()
    if worksheet is None:
        return []

    try:
        rows = worksheet.get_all_values()
    except Exception as exc:
        print(f"[sheets_history] failed to read snapshots ({exc})")
        return []

    if len(rows) <= 1:
        return []

    data_rows = rows[1:]  # drop header
    recent = data_rows[-limit:]
    recent.reverse()  # newest first

    def _to_float(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    return [
        {
            "timestamp": row[0] if len(row) > 0 else None,
            "current_temp_f": _to_float(row[1]) if len(row) > 1 else None,
            "model_forecast_f": _to_float(row[2]) if len(row) > 2 else None,
        }
        for row in recent
    ]


def append_trade(
    market_ticker, market_label, action, side,
    price_cents, contracts, cash_delta_cents, realized_pl_cents,
):
    """Append one trade-history row. No-ops if Sheets isn't configured."""
    worksheet = _get_trades_worksheet()
    if worksheet is None:
        return

    try:
        timestamp = datetime.now(timezone.utc).isoformat()
        worksheet.append_row([
            timestamp, market_ticker, market_label, action, side,
            price_cents, contracts, cash_delta_cents, realized_pl_cents,
        ])
    except Exception as exc:
        print(f"[sheets_history] failed to append trade ({exc})")


def get_recent_trades(limit=100):
    """Return up to `limit` most recent trades, newest first, as dicts shaped
    like {"timestamp", "market_ticker", "market_label", "action", "side",
    "price_cents", "contracts", "cash_delta_cents", "realized_pl_cents"}.
    Returns [] if Sheets isn't configured or the read fails.
    """
    worksheet = _get_trades_worksheet()
    if worksheet is None:
        return []

    try:
        rows = worksheet.get_all_values()
    except Exception as exc:
        print(f"[sheets_history] failed to read trades ({exc})")
        return []

    if len(rows) <= 1:
        return []

    data_rows = rows[1:]  # drop header
    recent = data_rows[-limit:]
    recent.reverse()  # newest first

    def _to_float(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _to_int(value):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    return [
        {
            "timestamp":          row[0] if len(row) > 0 else None,
            "market_ticker":      row[1] if len(row) > 1 else None,
            "market_label":       row[2] if len(row) > 2 else None,
            "action":             row[3] if len(row) > 3 else None,
            "side":               row[4] if len(row) > 4 else None,
            "price_cents":        _to_int(row[5])   if len(row) > 5 else None,
            "contracts":          _to_float(row[6]) if len(row) > 6 else None,
            "cash_delta_cents":   _to_int(row[7])   if len(row) > 7 else None,
            "realized_pl_cents":  _to_int(row[8])   if len(row) > 8 and row[8] != "" else None,
        }
        for row in recent
    ]
