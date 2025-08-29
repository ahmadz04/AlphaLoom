#!/usr/bin/env python3
"""
Input validation utilities for SEC filing summarization.

This module provides functions to validate section names, normalize aliases,
and build fast lookups of valid span IDs to ensure LLM-generated summaries
cite real paragraphs from the correct sections.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Set


def build_span_index(chunks_json: dict) -> Dict[str, Set[str]]:
    """
    Build a fast lookup index of valid span IDs per section.
    
    Args:
        chunks_json: Loaded chunks.json data containing paragraph inventory
        
    Returns:
        Dictionary mapping section_name -> set of span_ids in that section
        
    Example:
        {
            "Item 7": {"mdna::p001", "mdna::p002", ...},
            "Item 1A": {"risks::p001", "risks::p002", ...}
        }
    """
    span_index = {}
    
    for paragraph in chunks_json.get("paragraphs", []):
        section_name = paragraph.get("section")
        span_id = paragraph.get("span_id")
        
        if section_name and span_id:
            if section_name not in span_index:
                span_index[section_name] = set()
            span_index[section_name].add(span_id)
    
    return span_index


def normalize_section_name(section_name: str) -> str:
    """
    Normalize section names to canonical form, handling common aliases.
    
    This allows users to request "Risk Factors" or "MD&A" and have them
    properly mapped to the canonical "Item 1A" and "Item 7" names used
    in the JSON files.
    
    Args:
        section_name: Raw section name from user input
        
    Returns:
        Canonical section name that matches sections.json structure
    """
    # Clean input: strip whitespace and normalize case
    normalized = section_name.strip()
    normalized_lower = normalized.lower()
    
    # Alias mappings - map common user terms to canonical SEC Item names
    alias_mappings = {
        # Risk Factors variations
        "risk factors": "Item 1A",
        "risks": "Item 1A", 
        "item 1a": "Item 1A",
        "item1a": "Item 1A",
        "1a": "Item 1A",
        
        # MD&A variations  
        "md&a": "Item 7",
        "mda": "Item 7",
        "management discussion & analysis": "Item 7",
        "management's discussion and analysis": "Item 7", 
        "management discussion and analysis": "Item 7",
        "item 7": "Item 7",
        "item7": "Item 7",
        "7": "Item 7",
        
        # Business section variations
        "business": "Item 1",
        "item 1": "Item 1", 
        "item1": "Item 1",
        "1": "Item 1",
        
        # Other common sections
        "properties": "Item 2",
        "item 2": "Item 2",
        "legal proceedings": "Item 3", 
        "item 3": "Item 3",
        "financial statements": "Item 8",
        "item 8": "Item 8",
        "controls and procedures": "Item 9A",
        "item 9a": "Item 9A",
    }
    
    # Try exact alias match first
    if normalized_lower in alias_mappings:
        return alias_mappings[normalized_lower]
    
    # If no alias found, return the input with proper capitalization
    # Handle "Item X" format specifically
    if normalized_lower.startswith("item "):
        item_part = normalized[5:].strip().upper()  # Get part after "Item "
        return f"Item {item_part}"
    
    # Return original with title case for other formats
    return normalized


def validate_requested_sections(sections_json: dict, requested: List[str]) -> List[str]:
    """
    Validate requested section names against available sections in JSON.
    
    Args:
        sections_json: Loaded sections.json data
        requested: List of requested section names (may include aliases)
        
    Returns:
        List of canonical section names that exist in sections.json
        
    Raises:
        ValueError: If no valid sections found
    """
    # Get all available section names from JSON
    available_sections = set()
    for section in sections_json.get("sections", []):
        section_name = section.get("name")
        if section_name:
            available_sections.add(section_name)
    
    # Normalize and validate each requested section (deduplicate)
    valid_sections = []
    seen_sections = set()
    
    for section_name in requested:
        canonical_name = normalize_section_name(section_name)
        
        if canonical_name in available_sections:
            if canonical_name not in seen_sections:
                valid_sections.append(canonical_name)
                seen_sections.add(canonical_name)
        else:
            print(f"Warning: Section '{section_name}' (normalized: '{canonical_name}') not found in filing", 
                  file=sys.stderr)
    
    if not valid_sections:
        available_list = sorted(available_sections)
        raise ValueError(f"No valid sections found. Available sections: {', '.join(available_list)}")
    
    return valid_sections


def load_test_data(ticker: str = "AAPL", form: str = "10-K", year: int = 2023) -> tuple:
    """
    Load test data for demonstration purposes.
    
    Args:
        ticker: Stock ticker symbol
        form: SEC form type  
        year: Filing year
        
    Returns:
        Tuple of (sections_json, chunks_json) or (None, None) if files not found
    """
    base_dir = Path("data/processed") / ticker / form / str(year)
    sections_path = base_dir / "sections.json"
    chunks_path = base_dir / "chunks.json"
    
    try:
        with open(sections_path, 'r') as f:
            sections_json = json.load(f)
        with open(chunks_path, 'r') as f:
            chunks_json = json.load(f)
        return sections_json, chunks_json
    except FileNotFoundError as e:
        print(f"Test data not found: {e}", file=sys.stderr)
        return None, None
    except Exception as e:
        print(f"Error loading test data: {e}", file=sys.stderr)
        return None, None


def main():
    """
    Test function that demonstrates span index building and validation.
    
    Loads AAPL 2023 10-K data and shows span counts for different section aliases.
    """
    print("=== SEC Filing Section Validation Test ===")
    
    # Load test data
    sections_json, chunks_json = load_test_data()
    if not sections_json or not chunks_json:
        print("Unable to load test data. Ensure AAPL 2023 10-K data exists.", file=sys.stderr)
        return 1
    
    # Build span index
    span_index = build_span_index(chunks_json)
    
    print(f"Loaded filing: {sections_json.get('ticker')} {sections_json.get('form')} {sections_json.get('year')}")
    print(f"Total sections with spans: {len(span_index)}")
    print()
    
    # Test various section name formats
    test_requests = [
        "Item 7",           # Canonical
        "MD&A",             # Common alias  
        "Risk Factors",     # Alias
        "Item 1A",          # Canonical
        "risks",            # Short alias
        "Business",         # Another section
        "Item 99",          # Invalid section
    ]
    
    print("=== Section Name Normalization ===")
    for request in test_requests:
        canonical = normalize_section_name(request)
        print(f"'{request}' → '{canonical}'")
    print()
    
    # Test validation with mixed valid/invalid sections
    print("=== Validation Test ===")
    try:
        valid_sections = validate_requested_sections(sections_json, test_requests)
        print(f"Valid sections found: {len(valid_sections)}")
        print()
        
        # Show span counts for valid sections
        print("=== Span Counts ===")
        for section_name in valid_sections:
            span_count = len(span_index.get(section_name, set()))
            print(f"{section_name}: {span_count:,} spans")
            
            # Show first few span IDs as examples
            if section_name in span_index:
                example_spans = sorted(list(span_index[section_name]))[:3]
                print(f"  Examples: {', '.join(example_spans)}")
            print()
            
    except ValueError as e:
        print(f"Validation error: {e}", file=sys.stderr)
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())