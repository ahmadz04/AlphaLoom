from datetime import datetime

def _date_str(dt_utc: datetime) -> str:
    return dt_utc.strftime("%Y-%m-%d")

def transcript_path(ticker: str, call_id: str, call_dt_utc: datetime) -> str:
    t = ticker.upper()
    d = _date_str(call_dt_utc)
    return f"data/raw/transcripts/{t}/{d}_{call_id}_call.json"

def manifest_path(ticker: str, call_id: str, call_dt_utc: datetime) -> str:
    t = ticker.upper()
    d = _date_str(call_dt_utc)
    return f"data/processed/manifests/{t}/{d}_{call_id}_manifest.json"

def latest_index_path(ticker: str) -> str:
    return f"data/processed/latest_index/{ticker.upper()}.json"
