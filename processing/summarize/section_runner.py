#!/usr/bin/env python3
"""
Section runner for chunk-by-chunk LLM summarization with caching.

This module processes one SEC filing section at a time, breaking it into chunks
and summarizing each chunk independently. Uses caching to avoid redundant API
calls and provides localized error handling so one bad chunk doesn't break
the entire section.
"""

import hashlib
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Import with fallback for standalone testing
try:
    from .cache import cache_path, read_cache, write_cache
    from .prompt import build_messages_for_gemini
    from .llm import call_gemini
except ImportError:
    # For standalone testing
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from summarize.cache import cache_path, read_cache, write_cache
    from summarize.prompt import build_messages_for_gemini
    from summarize.llm import call_gemini


def validate_chunk_result(result: Dict) -> Dict:
    """
    Validate and normalize chunk result structure.
    
    Args:
        result: Raw result dictionary from LLM or cache
        
    Returns:
        Validated dictionary with required keys and proper types
    """
    validated = {}
    
    # Required array fields
    required_arrays = ["bullets", "key_numbers", "uncertainties", "warnings"]
    
    for field in required_arrays:
        if field in result and isinstance(result[field], list):
            validated[field] = result[field]
        else:
            validated[field] = []
    
    # Add metadata if present
    for field in ["generated_at", "model", "tokens_used", "cache_hit"]:
        if field in result:
            validated[field] = result[field]
    
    return validated


def extract_span_ids_from_paragraphs(paragraphs: List[Dict]) -> List[str]:
    """
    Extract valid span IDs from paragraph list.
    
    Args:
        paragraphs: List of paragraph dicts with span_id keys
        
    Returns:
        List of valid span IDs
    """
    span_ids = []
    for paragraph in paragraphs:
        span_id = paragraph.get("span_id")
        if span_id and isinstance(span_id, str):
            span_ids.append(span_id)
    
    return span_ids


def group_paragraphs_into_chunks(
    section_paragraphs: List[Dict], 
    chunk_size: int = 8
) -> List[List[Dict]]:
    """
    Group section paragraphs into chunks for processing.
    
    Args:
        section_paragraphs: All paragraphs for this section
        chunk_size: Target number of paragraphs per chunk
        
    Returns:
        List of paragraph chunks
    """
    chunks = []
    
    for i in range(0, len(section_paragraphs), chunk_size):
        chunk = section_paragraphs[i:i + chunk_size]
        chunks.append(chunk)
    
    return chunks


def summarize_section(
    ticker: str,
    form: str,
    year: int,
    section_name: str,
    section_alias: str,
    section_hash: str,
    chunks_for_section: List[List[Dict]],
    cache_base: str = "data/cache/summaries"
) -> List[Dict]:
    """
    Summarize a complete SEC filing section chunk by chunk with caching.
    
    Args:
        ticker: Stock ticker symbol
        form: SEC form type
        year: Filing year
        section_name: Section name (e.g., "Item 7")
        section_alias: Human-readable section title
        section_hash: Hash of section content for cache invalidation
        chunks_for_section: List of paragraph chunks to process
        cache_base: Base directory for cache storage
        
    Returns:
        List of per-chunk summary dictionaries
    """
    print(f"Processing {section_name} ({section_alias}): {len(chunks_for_section)} chunks")
    
    chunk_results = []
    cache_hits = 0
    cache_misses = 0
    
    for chunk_index, chunk_paragraphs in enumerate(chunks_for_section):
        print(f"  Chunk {chunk_index + 1}/{len(chunks_for_section)}: {len(chunk_paragraphs)} paragraphs", end="")
        
        # Generate cache path
        cache_file_path = cache_path(
            cache_base, ticker, form, year, 
            section_name, section_hash, chunk_index
        )
        
        # Try to load from cache first
        cached_result = read_cache(cache_file_path)
        
        if cached_result is not None:
            print(" [CACHE HIT]")
            cached_result["cache_hit"] = True
            validated_result = validate_chunk_result(cached_result)
            chunk_results.append(validated_result)
            cache_hits += 1
            continue
        
        print(" [CACHE MISS]", end="")
        
        # Extract allowed span IDs from this chunk's paragraphs
        allowed_span_ids = extract_span_ids_from_paragraphs(chunk_paragraphs)
        
        if not allowed_span_ids:
            print(" [NO SPANS - SKIPPING]")
            empty_result = {
                "bullets": [],
                "key_numbers": [],
                "uncertainties": [],
                "warnings": [f"No valid span IDs found in chunk {chunk_index}"],
                "cache_hit": False
            }
            chunk_results.append(empty_result)
            continue
        
        # Build messages for Gemini
        try:
            messages = build_messages_for_gemini(
                section_name=section_name,
                section_alias=section_alias,
                section_hash=section_hash,
                chunk_index=chunk_index,
                paragraphs=chunk_paragraphs,
                allowed_span_ids=allowed_span_ids
            )
        except Exception as e:
            print(f" [MESSAGE BUILD ERROR: {e}]")
            error_result = {
                "bullets": [],
                "key_numbers": [],
                "uncertainties": [],
                "warnings": [f"Failed to build messages for chunk {chunk_index}: {e}"],
                "cache_hit": False
            }
            chunk_results.append(error_result)
            continue
        
        # Call Gemini API
        try:
            print(" [API CALL]", end="")
            
            llm_result = call_gemini(
                messages=messages,
                model="gemini-2.0-flash-exp",
                max_output_tokens=1200,
                temperature=0.2
            )
            
            # Add metadata
            llm_result["cache_hit"] = False
            llm_result["generated_at"] = __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
            llm_result["model"] = "gemini-2.0-flash-exp"
            
        except Exception as e:
            print(f" [API ERROR: {e}]")
            error_result = {
                "bullets": [],
                "key_numbers": [],
                "uncertainties": [],
                "warnings": [f"API call failed for chunk {chunk_index}: {e}"],
                "cache_hit": False
            }
            chunk_results.append(error_result)
            continue
        
        # Validate result structure
        validated_result = validate_chunk_result(llm_result)
        
        # Count content for logging
        content_items = (
            len(validated_result.get("bullets", [])) +
            len(validated_result.get("key_numbers", [])) +
            len(validated_result.get("uncertainties", []))
        )
        
        print(f" [SUCCESS: {content_items} items]")
        
        # Write to cache
        try:
            write_cache(cache_file_path, validated_result)
        except Exception as e:
            print(f"  Warning: Failed to write cache for chunk {chunk_index}: {e}", file=sys.stderr)
        
        chunk_results.append(validated_result)
        cache_misses += 1
    
    # Summary stats
    print(f"  Section complete: {cache_hits} cache hits, {cache_misses} API calls")
    
    return chunk_results


def load_section_data(
    ticker: str, 
    form: str, 
    year: int, 
    section_name: str
) -> Optional[Dict]:
    """
    Load section data and paragraphs for processing.
    
    Args:
        ticker: Stock ticker symbol
        form: SEC form type
        year: Filing year
        section_name: Section name to load
        
    Returns:
        Dictionary with section metadata and paragraphs, or None if not found
    """
    import json
    
    base_dir = Path("data/processed") / ticker / form / str(year)
    sections_path = base_dir / "sections.json"
    chunks_path = base_dir / "chunks.json"
    
    try:
        # Load sections and chunks data
        with open(sections_path, 'r') as f:
            sections_data = json.load(f)
        with open(chunks_path, 'r') as f:
            chunks_data = json.load(f)
        
        # Find the requested section
        section_info = None
        for section in sections_data.get("sections", []):
            if section.get("name") == section_name:
                section_info = section
                break
        
        if not section_info:
            print(f"Section {section_name} not found in {ticker} {form} {year}", file=sys.stderr)
            return None
        
        # Get paragraphs for this section
        section_paragraphs = []
        for paragraph in chunks_data.get("paragraphs", []):
            if paragraph.get("section") == section_name:
                section_paragraphs.append(paragraph)
        
        if not section_paragraphs:
            print(f"No paragraphs found for section {section_name}", file=sys.stderr)
            return None
        
        # Create section hash from content for cache invalidation
        section_text = "".join([p.get("text", "") for p in section_paragraphs])
        section_hash = hashlib.sha256(section_text.encode('utf-8')).hexdigest()[:16]
        
        return {
            "section_info": section_info,
            "paragraphs": section_paragraphs,
            "section_hash": section_hash
        }
        
    except Exception as e:
        print(f"Error loading section data: {e}", file=sys.stderr)
        return None


def main():
    """
    Test section runner with sample data.
    """
    print("=== Section Runner Test ===")
    
    # Test with AAPL Item 7 data
    ticker = "AAPL"
    form = "10-K"
    year = 2023
    section_name = "Item 7"
    
    # Load section data
    section_data = load_section_data(ticker, form, year, section_name)
    
    if not section_data:
        print("Failed to load section data")
        return 1
    
    section_info = section_data["section_info"]
    paragraphs = section_data["paragraphs"]
    section_hash = section_data["section_hash"]
    
    print(f"Loaded {section_name}: {len(paragraphs)} paragraphs")
    print(f"Section alias: {section_info.get('alias', 'N/A')}")
    print(f"Section hash: {section_hash}")
    
    # Group into chunks (smaller chunks for testing)
    chunks = group_paragraphs_into_chunks(paragraphs, chunk_size=3)
    print(f"Grouped into {len(chunks)} chunks")
    
    # Process just the first 2 chunks for testing
    test_chunks = chunks[:2]
    print(f"Processing first {len(test_chunks)} chunks for testing...")
    
    try:
        results = summarize_section(
            ticker=ticker,
            form=form,
            year=year,
            section_name=section_name,
            section_alias=section_info.get("alias", section_name),
            section_hash=section_hash,
            chunks_for_section=test_chunks,
            cache_base="data/cache/summaries"
        )
        
        print(f"\n=== Results ===")
        print(f"Processed {len(results)} chunks")
        
        for i, result in enumerate(results):
            bullets = len(result.get("bullets", []))
            numbers = len(result.get("key_numbers", []))
            uncertainties = len(result.get("uncertainties", []))
            warnings = len(result.get("warnings", []))
            cache_hit = result.get("cache_hit", False)
            
            print(f"Chunk {i}: {bullets}B/{numbers}N/{uncertainties}U/{warnings}W {'(cached)' if cache_hit else '(fresh)'}")
        
        print("\n✅ Section runner test completed")
        return 0
        
    except Exception as e:
        print(f"Section runner test failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())