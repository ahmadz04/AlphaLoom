from datetime import datetime
from typing import Optional

def _date_str(dt_utc: datetime) -> str:
    return dt_utc.strftime("%Y-%m-%d")

# ============================================================================
# RAW ZONE PATHS - Exact inputs from outside world
# ============================================================================

# Transcript paths (legacy support)
def transcript_path(ticker: str, call_id: str, call_dt_utc: datetime) -> str:
    t = ticker.upper()
    d = _date_str(call_dt_utc)
    return f"data/raw/transcripts/{t}/{d}_{call_id}_call.json"

# SEC Filing paths
def filing_path(ticker: str, filing_type: str, year: int, filed_date: Optional[str] = None, 
               file_format: str = "json") -> str:
    t = ticker.upper()
    if filed_date:
        # Use filed date if available
        date_part = filed_date.split('T')[0] if 'T' in filed_date else filed_date
    else:
        # Fallback to year
        date_part = str(year)
    return f"data/raw/filings/{t}/{year}_{filing_type}_{date_part}_filing.{file_format}"

def filing_txt_path(ticker: str, filing_type: str, year: int, filed_date: Optional[str] = None) -> str:
    """Get path for normalized TXT version of filing."""
    return filing_path(ticker, filing_type, year, filed_date, "txt")

# ============================================================================
# PROCESSED ZONE PATHS - Everything we compute from raw
# ============================================================================

def processed_base_path(ticker: str, filing_type: str, year: int) -> str:
    """Base path for processed analysis outputs."""
    t = ticker.upper()
    return f"data/processed/{t}/{filing_type}/{year}"

def sections_path(ticker: str, filing_type: str, year: int) -> str:
    """Path for SEC item boundaries and paragraph spans."""
    return f"{processed_base_path(ticker, filing_type, year)}/sections.json"

def summaries_path(ticker: str, filing_type: str, year: int) -> str:
    """Path for LLM-generated summaries with citations."""
    return f"{processed_base_path(ticker, filing_type, year)}/summaries.json"

def sentiment_path(ticker: str, filing_type: str, year: int) -> str:
    """Path for FinBERT sentiment scores."""
    return f"{processed_base_path(ticker, filing_type, year)}/sentiment.json"

def topics_path(ticker: str, filing_type: str, year: int) -> str:
    """Path for BERTopic analysis results."""
    return f"{processed_base_path(ticker, filing_type, year)}/topics.json"

def processed_manifest_path(ticker: str, filing_type: str, year: int) -> str:
    """Path for processing metadata and manifest."""
    return f"{processed_base_path(ticker, filing_type, year)}/manifest.json"

# ============================================================================
# DASH ZONE PATHS - App interface layer
# ============================================================================

def latest_index_path(ticker: str) -> str:
    """Latest index path - pointer to newest processed data."""
    return f"data/dash/latest_index/{ticker.upper()}.json"

# ============================================================================
# LEGACY PATHS - For backward compatibility during transition
# ============================================================================

def legacy_manifest_path(ticker: str, call_id: Optional[str] = None, call_dt_utc: Optional[datetime] = None, 
                        filing_type: Optional[str] = None, year: Optional[int] = None, 
                        filed_date: Optional[str] = None) -> str:
    """Legacy manifest path for backward compatibility."""
    t = ticker.upper()
    
    if call_id and call_dt_utc:  # Transcript manifest
        d = _date_str(call_dt_utc)
        return f"data/processed/manifests/{t}/{d}_{call_id}_manifest.json"
    elif filing_type and year:  # Filing manifest
        if filed_date:
            date_part = filed_date.split('T')[0] if 'T' in filed_date else filed_date
        else:
            date_part = str(year)
        return f"data/processed/manifests/{t}/{year}_{filing_type}_{date_part}_manifest.json"
    else:
        raise ValueError("Must provide either (call_id, call_dt_utc) or (filing_type, year)")

# Keep manifest_path as alias for backward compatibility
def manifest_path(ticker: str, call_id: Optional[str] = None, call_dt_utc: Optional[datetime] = None, 
                 filing_type: Optional[str] = None, year: Optional[int] = None, 
                 filed_date: Optional[str] = None) -> str:
    """Legacy manifest path - use legacy_manifest_path for new code."""
    return legacy_manifest_path(ticker, call_id, call_dt_utc, filing_type, year, filed_date)