from typing import List, Optional, Literal, Union
from pydantic import BaseModel, Field
from datetime import datetime

class TranscriptSection(BaseModel):
    label: str
    text: str

class SpeakerBlock(BaseModel):
    speaker: str
    role: Optional[str] = None
    text: str
    start_idx: Optional[int] = None
    end_idx: Optional[int] = None

class FilingItem(BaseModel):
    item: str
    content: str
    section_type: Optional[str] = None

class TranscriptRaw(BaseModel):
    ticker: str
    call_id: str
    call_datetime: datetime      # UTC
    provider: Literal["seekingalpha-rapidapi"]
    retrieved_at: datetime       # UTC
    title: Optional[str] = None
    canonical_url: Optional[str] = None
    sections: List[TranscriptSection]
    speaker_blocks: Optional[List[SpeakerBlock]] = None
    hash: str
    meta: dict = Field(default_factory=dict)

class FilingRaw(BaseModel):
    ticker: str
    filing_type: str             # 10-K, 10-Q
    year: int
    period_end_date: Optional[str] = None
    filed_date: Optional[str] = None
    provider: Literal["financialdatasets-api"]
    retrieved_at: datetime       # UTC
    company_name: Optional[str] = None
    cik: Optional[str] = None
    items: List[FilingItem]
    hash: str
    meta: dict = Field(default_factory=dict)

class Manifest(BaseModel):
    ticker: str
    # For transcripts
    call_id: Optional[str] = None
    call_datetime: Optional[datetime] = None
    transcript_path: Optional[str] = None
    transcript_bytes: Optional[int] = None
    transcript_hash: Optional[str] = None
    # For filings
    filing_type: Optional[str] = None
    filing_year: Optional[int] = None
    period_end_date: Optional[str] = None
    filed_date: Optional[str] = None
    filing_path: Optional[str] = None
    filing_bytes: Optional[int] = None
    filing_hash: Optional[str] = None
    items_count: Optional[int] = None
    # Common fields
    provider: str
    news_path: Optional[str] = None
    news_items_total: int = 0
    news_deduped_total: int = 0
    warnings: List[str] = Field(default_factory=list)
    created_at: datetime
    ingestion_version: str
    run_id: str
    runner: str

class LatestIndex(BaseModel):
    ticker: str
    latest_manifest_path: str
    updated_at: datetime
