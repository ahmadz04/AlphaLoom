#!/usr/bin/env python3
"""
Async section runner for chunk-by-chunk LLM summarization with rate limiting.

This module provides fully async processing of SEC filing sections with
proper rate limiting, connection pooling, and batch cache operations.
"""

import asyncio
import hashlib
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import ujson as json
except ImportError:
    import json

# Import with fallback for standalone testing
try:
    from .cache import cache_path, batch_read_cache, batch_write_cache
    from .prompt import build_messages_for_openai
    from .llm_async import AsyncOpenAIClient, batch_call_openai_async
except ImportError:
    # For standalone testing
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from summarize.cache import cache_path, batch_read_cache, batch_write_cache
    from summarize.prompt import build_messages_for_openai
    from summarize.llm_async import AsyncOpenAIClient, batch_call_openai_async


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
    chunk_size: int = 6
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


async def summarize_section_async(
    ticker: str,
    form: str,
    year: int,
    section_name: str,
    section_alias: str,
    section_hash: str,
    chunks_for_section: List[List[Dict]],
    cache_base: str = "data/cache/summaries",
    max_concurrent: int = 10
) -> List[Dict]:
    """
    Summarize a complete SEC filing section chunk by chunk with async processing and batch caching.
    
    Args:
        ticker: Stock ticker symbol
        form: SEC form type
        year: Filing year
        section_name: Section name (e.g., "Item 7")
        section_alias: Human-readable section title
        section_hash: Hash of section content for cache invalidation
        chunks_for_section: List of paragraph chunks to process
        cache_base: Base directory for cache storage
        max_concurrent: Maximum concurrent API requests
        
    Returns:
        List of per-chunk summary dictionaries in original order
    """
    print(f"Processing {section_name} ({section_alias}): {len(chunks_for_section)} chunks (async + batch)")
    
    # Step 1: Batch check cache for all chunks
    cache_paths = []
    chunk_metadata = []
    
    for chunk_index, chunk_paragraphs in enumerate(chunks_for_section):
        cache_file_path = cache_path(
            cache_base, ticker, form, year, 
            section_name, section_hash, chunk_index
        )
        cache_paths.append(cache_file_path)
        
        # Store chunk metadata for uncached processing
        allowed_span_ids = extract_span_ids_from_paragraphs(chunk_paragraphs)
        chunk_metadata.append({
            'chunk_index': chunk_index,
            'chunk_paragraphs': chunk_paragraphs,
            'allowed_span_ids': allowed_span_ids
        })
    
    # Batch read all cache files
    print(f"  Batch checking cache for {len(cache_paths)} chunks...")
    cached_results = batch_read_cache(cache_paths)
    
    # Separate cached vs uncached chunks
    chunk_results = [None] * len(chunks_for_section)  # Pre-allocate to maintain order
    uncached_chunks = []  # Chunks that need processing
    cache_hits = 0
    
    for chunk_index, cached_result in enumerate(cached_results):
        if cached_result is not None:
            # Cache hit
            cached_result["cache_hit"] = True
            validated_result = validate_chunk_result(cached_result)
            chunk_results[chunk_index] = validated_result
            cache_hits += 1
        else:
            # Cache miss - need to process
            metadata = chunk_metadata[chunk_index]
            if metadata['allowed_span_ids']:  # Only process if valid span IDs
                uncached_chunks.append(metadata)
            else:
                # No valid spans - create empty result
                empty_result = {
                    "bullets": [],
                    "key_numbers": [],
                    "uncertainties": [],
                    "warnings": [f"No valid span IDs found in chunk {chunk_index}"],
                    "cache_hit": False
                }
                chunk_results[chunk_index] = empty_result
    
    print(f"  Cache performance: {cache_hits} hits, {len(uncached_chunks)} misses")
    
    # Step 2: Process uncached chunks with async batch API calls
    pending_cache_writes = []  # For batch cache writing
    
    if uncached_chunks:
        # Prepare messages for all uncached chunks
        messages_list = []
        chunk_index_map = {}  # Map messages index to chunk index
        
        for i, metadata in enumerate(uncached_chunks):
            try:
                messages = build_messages_for_openai(
                    section_name=section_name,
                    section_alias=section_alias,
                    section_hash=section_hash,
                    chunk_index=metadata['chunk_index'],
                    paragraphs=metadata['chunk_paragraphs'],
                    allowed_span_ids=metadata['allowed_span_ids']
                )
                messages_list.append(messages)
                chunk_index_map[i] = metadata['chunk_index']
                
            except Exception as e:
                # Handle message building error
                chunk_index = metadata['chunk_index']
                error_result = {
                    "bullets": [],
                    "key_numbers": [],
                    "uncertainties": [],
                    "warnings": [f"Failed to build messages for chunk {chunk_index}: {e}"],
                    "cache_hit": False
                }
                chunk_results[chunk_index] = error_result
        
        # Make batch async API calls
        if messages_list:
            print(f"  Making {len(messages_list)} async API calls (max concurrent: {max_concurrent})...")
            
            try:
                api_responses = await batch_call_openai_async(
                    messages_list,
                    model="gpt-4o-mini",
                    max_output_tokens=1200,
                    temperature=0.2,
                    max_concurrent=max_concurrent
                )
                
                # Process API responses
                for i, response in enumerate(api_responses):
                    chunk_index = chunk_index_map[i]
                    
                    # Add metadata
                    response["cache_hit"] = False
                    response["generated_at"] = __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
                    response["model"] = "gpt-4o-mini"
                    
                    # Validate result structure
                    validated_result = validate_chunk_result(response)
                    chunk_results[chunk_index] = validated_result
                    
                    # Prepare for batch cache write
                    cache_file_path = cache_paths[chunk_index]
                    pending_cache_writes.append((cache_file_path, validated_result))
                    
                    # Log result
                    content_items = (
                        len(validated_result.get("bullets", [])) +
                        len(validated_result.get("key_numbers", [])) +
                        len(validated_result.get("uncertainties", []))
                    )
                    print(f"  Chunk {chunk_index + 1}: {content_items} items generated")
                    
            except Exception as e:
                print(f"  Error in batch API calls: {e}", file=sys.stderr)
                # Handle batch API failure
                for i in range(len(messages_list)):
                    chunk_index = chunk_index_map[i]
                    if chunk_results[chunk_index] is None:  # Not already handled
                        error_result = {
                            "bullets": [],
                            "key_numbers": [],
                            "uncertainties": [],
                            "warnings": [f"Batch API call failed for chunk {chunk_index}: {e}"],
                            "cache_hit": False
                        }
                        chunk_results[chunk_index] = error_result
    
    # Step 3: Batch write all new cache files
    if pending_cache_writes:
        print(f"  Batch writing {len(pending_cache_writes)} cache files...")
        success_count, failure_count = batch_write_cache(pending_cache_writes)
        if failure_count > 0:
            print(f"  Warning: {failure_count} cache writes failed", file=sys.stderr)
    
    # Summary stats
    cache_misses = len(uncached_chunks)
    print(f"  Section complete: {cache_hits} cache hits, {cache_misses} API calls")
    
    return chunk_results


async def load_section_data_async(
    ticker: str, 
    form: str, 
    year: int, 
    section_name: str
) -> Optional[Dict]:
    """
    Load section data and paragraphs for processing (async version).
    
    Args:
        ticker: Stock ticker symbol
        form: SEC form type
        year: Filing year
        section_name: Section name to load
        
    Returns:
        Dictionary with section metadata and paragraphs, or None if not found
    """
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


async def main():
    """
    Test async section runner with sample data.
    """
    print("=== Async Section Runner Test ===")
    
    # Test with AAPL Item 7 data
    ticker = "AAPL"
    form = "10-K"
    year = 2023
    section_name = "Item 7"
    
    # Load section data
    section_data = await load_section_data_async(ticker, form, year, section_name)
    
    if not section_data:
        print("Failed to load section data")
        return 1
    
    section_info = section_data["section_info"]
    paragraphs = section_data["paragraphs"]
    section_hash = section_data["section_hash"]
    
    print(f"Loaded {section_name}: {len(paragraphs)} paragraphs")
    print(f"Section alias: {section_info.get('alias', 'N/A')}")
    print(f"Section hash: {section_hash}")
    
    # Group into chunks
    chunks = group_paragraphs_into_chunks(paragraphs, chunk_size=6)
    print(f"Grouped into {len(chunks)} chunks")
    
    # Process first 3 chunks for testing
    test_chunks = chunks[:3]
    print(f"Processing first {len(test_chunks)} chunks for testing...")
    
    try:
        results = await summarize_section_async(
            ticker=ticker,
            form=form,
            year=year,
            section_name=section_name,
            section_alias=section_info.get("alias", section_name),
            section_hash=section_hash,
            chunks_for_section=test_chunks,
            cache_base="data/cache/summaries",
            max_concurrent=5
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
        
        print("\n✅ Async section runner test completed")
        return 0
        
    except Exception as e:
        print(f"Async section runner test failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))