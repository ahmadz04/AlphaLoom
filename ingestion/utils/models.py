from typing import List, Optional, Literal
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

class Manifest(BaseModel):
    ticker: str
    call_id: str
    call_datetime: datetime
    provider: str
    transcript_path: str
    transcript_bytes: int
    transcript_hash: str
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
