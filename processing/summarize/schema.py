#!/usr/bin/env python3
"""
Schema contract for summaries.json - LLM-generated summaries of SEC filing sections.

This module defines the data structures for storing structured summaries
of SEC filing content, including key bullet points, numbers, and uncertainties.
"""

from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field


VERSION = "1.0.0"


class Bullet(BaseModel):
    """
    A single bullet point with references to source paragraph spans.
    
    Attributes:
        text: The bullet point content
        span_ids: List of paragraph span IDs that support this bullet point
    """
    text: str = Field(..., description="The bullet point content")
    span_ids: List[str] = Field(..., description="List of paragraph span IDs that support this bullet point")


class SentimentAnalysis(BaseModel):
    """
    FinBERT sentiment analysis results for a section.
    
    Attributes:
        negative: Negative sentiment probability (0-1)
        neutral: Neutral sentiment probability (0-1) 
        positive: Positive sentiment probability (0-1)
        overall_score: Overall sentiment score (-1 to +1, negative to positive)
        sentiment_label: Human-readable sentiment label
        confidence: Confidence score of the prediction (0-1)
        model_used: Name of the model used for analysis
        chunks_analyzed: Number of text chunks analyzed
    """
    negative: float = Field(..., description="Negative sentiment probability (0-1)")
    neutral: float = Field(..., description="Neutral sentiment probability (0-1)")
    positive: float = Field(..., description="Positive sentiment probability (0-1)")
    overall_score: float = Field(..., description="Overall sentiment score (-1 to +1, negative to positive)")
    sentiment_label: str = Field(..., description="Human-readable sentiment label")
    confidence: float = Field(..., description="Confidence score of the prediction (0-1)")
    model_used: str = Field(..., description="Name of the model used for analysis")
    chunks_analyzed: int = Field(..., description="Number of text chunks analyzed")


class SummariesSection(BaseModel):
    """
    Summary data for a single SEC filing section.
    
    Attributes:
        section_name: SEC Item name (e.g., "Item 7", "Item 1A")
        section_alias: Human-readable section title
        section_hash: Hash of the source section content for change detection
        bullets: Key insights and findings as bullet points
        key_numbers: Important numerical data points
        uncertainties: Risk factors and uncertain elements
        sentiment_analysis: FinBERT sentiment analysis results (optional)
        warnings: Processing warnings or issues
        created_at: UTC timestamp when summary was generated
    """
    section_name: str = Field(..., description="SEC Item name (e.g., 'Item 7', 'Item 1A')")
    section_alias: str = Field(..., description="Human-readable section title")
    section_hash: str = Field(..., description="Hash of the source section content for change detection")
    bullets: List[Bullet] = Field(default_factory=list, description="Key insights and findings as bullet points")
    key_numbers: List[Bullet] = Field(default_factory=list, description="Important numerical data points")
    uncertainties: List[Bullet] = Field(default_factory=list, description="Risk factors and uncertain elements")
    sentiment_analysis: Optional[SentimentAnalysis] = Field(None, description="FinBERT sentiment analysis results (optional)")
    warnings: List[str] = Field(default_factory=list, description="Processing warnings or issues")
    created_at: str = Field(..., description="UTC timestamp when summary was generated")


class SummariesFile(BaseModel):
    """
    Complete summaries file for a SEC filing.
    
    Attributes:
        ticker: Stock ticker symbol
        form: SEC form type (e.g., "10-K", "10-Q")
        year: Filing year
        sections: List of summarized sections
        version: Schema version for compatibility
    """
    ticker: str = Field(..., description="Stock ticker symbol")
    form: str = Field(..., description="SEC form type (e.g., '10-K', '10-Q')")
    year: int = Field(..., description="Filing year")
    sections: List[SummariesSection] = Field(default_factory=list, description="List of summarized sections")
    version: str = Field(default=VERSION, description="Schema version for compatibility")


def now_iso() -> str:
    """
    Get current UTC time as ISO-8601 string with seconds precision.
    
    Returns:
        ISO-8601 formatted timestamp string (e.g., "2024-01-15T10:30:45Z")
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_json_schema() -> dict:
    """
    Generate JSON Schema for SummariesFile model.
    
    Returns:
        JSON Schema dictionary for validation and documentation
    """
    return SummariesFile.model_json_schema()


if __name__ == "__main__":
    # Self-test: Build a minimal valid summaries file
    test_bullet = Bullet(
        text="Revenue increased 15% year-over-year driven by strong iPhone sales",
        span_ids=["mdna::p005", "mdna::p006"]
    )
    
    test_section = SummariesSection(
        section_name="Item 7",
        section_alias="Management's Discussion and Analysis",
        section_hash="abc123def456",
        bullets=[test_bullet],
        key_numbers=[
            Bullet(
                text="Total revenue: $394.3 billion (up 15% YoY)",
                span_ids=["mdna::p010"]
            )
        ],
        uncertainties=[
            Bullet(
                text="Supply chain disruptions may impact future quarters",
                span_ids=["mdna::p025"]
            )
        ],
        warnings=["Some financial metrics could not be extracted"],
        created_at=now_iso()
    )
    
    test_file = SummariesFile(
        ticker="AAPL",
        form="10-K",
        year=2023,
        sections=[test_section]
    )
    
    print("=== Test SummariesFile JSON ===")
    print(test_file.model_dump_json(indent=2))
    
    print("\n=== JSON Schema ===")
    schema = to_json_schema()
    print(f"Schema title: {schema.get('title', 'N/A')}")
    print(f"Required fields: {schema.get('required', [])}")
    print(f"Properties count: {len(schema.get('properties', {}))}")