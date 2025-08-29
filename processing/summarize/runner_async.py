#!/usr/bin/env python3
"""
Async orchestrator & CLI "summarize" - Top-level glue for SEC filing summarization with async processing.

This module provides async orchestration for maximum performance:
1. Loads sections.json and chunks.json
2. Builds span index and groups chunks by section
3. For each target section: processes chunks asynchronously with rate limiting
4. Writes summaries.json and returns compact report
"""

import asyncio
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set, Any, Optional

try:
    import ujson as json
except ImportError:
    import json

try:
    from .section_runner_async import (
        summarize_section_async, 
        group_paragraphs_into_chunks,
        extract_span_ids_from_paragraphs
    )
    from .merge_validate import merge_outputs
    from .persist import write_summaries
    from .schema import SummariesSection, now_iso
except ImportError:
    # For standalone testing
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from section_runner_async import (
        summarize_section_async,
        group_paragraphs_into_chunks,
        extract_span_ids_from_paragraphs
    )
    from merge_validate import merge_outputs
    from persist import write_summaries
    from schema import SummariesSection, now_iso


def load_filing_data(ticker: str, form: str, year: int) -> Optional[Dict[str, Any]]:
    """
    Load sections.json and chunks.json for a filing.
    
    Args:
        ticker: Stock ticker symbol
        form: SEC form type
        year: Filing year
        
    Returns:
        Dict with sections_data, chunks_data, or None if error
    """
    base_dir = Path("data/processed") / ticker / form / str(year)
    sections_path = base_dir / "sections.json"
    chunks_path = base_dir / "chunks.json"
    
    if not sections_path.exists():
        print(f"Error: sections.json not found at {sections_path}", file=sys.stderr)
        return None
    
    if not chunks_path.exists():
        print(f"Error: chunks.json not found at {chunks_path}", file=sys.stderr)
        return None
    
    try:
        with open(sections_path, 'r', encoding='utf-8') as f:
            sections_data = json.load(f)
        with open(chunks_path, 'r', encoding='utf-8') as f:
            chunks_data = json.load(f)
        
        return {
            'sections_data': sections_data,
            'chunks_data': chunks_data
        }
        
    except Exception as e:
        print(f"Error loading filing data: {e}", file=sys.stderr)
        return None


def build_span_index(chunks_data: Dict) -> Dict[str, List[str]]:
    """Build index mapping section names to valid span IDs."""
    span_index = {}
    
    for paragraph in chunks_data.get("paragraphs", []):
        section = paragraph.get("section")
        span_id = paragraph.get("span_id")
        
        if section and span_id:
            if section not in span_index:
                span_index[section] = []
            span_index[section].append(span_id)
    
    return span_index


def group_chunks_by_section(chunks_data: Dict) -> Dict[str, List[Dict]]:
    """Group paragraph chunks by section name."""
    chunks_by_section = {}
    
    for paragraph in chunks_data.get("paragraphs", []):
        section = paragraph.get("section")
        
        if section:
            if section not in chunks_by_section:
                chunks_by_section[section] = []
            chunks_by_section[section].append(paragraph)
    
    return chunks_by_section


def find_section_info(sections_data: Dict, section_name: str) -> Optional[Dict]:
    """Find section metadata from sections.json."""
    for section in sections_data.get("sections", []):
        if section.get("name") == section_name:
            return section
    return None


def create_section_hash(section_paragraphs: List[Dict]) -> str:
    """Create hash of section content for cache invalidation."""
    section_text = "".join([p.get("text", "") for p in section_paragraphs])
    return hashlib.sha256(section_text.encode('utf-8')).hexdigest()[:16]


async def run_async(
    ticker: str, 
    form: str, 
    year: int, 
    target_sections: List[str] = None,
    max_concurrent: int = 10
) -> Dict[str, Any]:
    """
    Main async orchestrator for SEC filing summarization.
    
    Args:
        ticker: Stock ticker symbol (e.g., "AAPL")
        form: SEC form type (e.g., "10-K")
        year: Filing year
        target_sections: List of section names to process (default: ["Item 7", "Item 1A"])
        max_concurrent: Maximum concurrent API requests
        
    Returns:
        Dict containing:
        - out_path: Path to written summaries.json
        - report: Dict with stats (bullets per section, warnings, cache hits/misses)
    """
    if target_sections is None:
        target_sections = ["Item 7", "Item 1A"]
    
    print(f"=== Async Summarizing {ticker} {form} {year} ===")
    print(f"Target sections: {', '.join(target_sections)}")
    
    # Step 1: Load sections.json and chunks.json
    filing_data = load_filing_data(ticker, form, year)
    if not filing_data:
        raise Exception("Failed to load filing data")
    
    sections_data = filing_data['sections_data']
    chunks_data = filing_data['chunks_data']
    
    print(f"Loaded {len(sections_data.get('sections', []))} sections, "
          f"{len(chunks_data.get('paragraphs', []))} paragraphs")
    
    # Step 2: Build span index and group chunks by section
    span_index = build_span_index(chunks_data)
    chunks_by_section = group_chunks_by_section(chunks_data)
    
    print(f"Built span index for {len(span_index)} sections")
    
    # Process each target section asynchronously
    async_tasks = []
    section_metadata = {}
    
    for section_name in target_sections:
        print(f"\n--- Preparing {section_name} for async processing ---")
        
        # Get section info and paragraphs
        section_info = find_section_info(sections_data, section_name)
        if not section_info:
            warning = f"Section {section_name} not found in sections.json"
            print(f"Warning: {warning}")
            continue
        
        section_alias = section_info.get("alias", section_name)
        section_paragraphs = chunks_by_section.get(section_name, [])
        
        if not section_paragraphs:
            warning = f"No paragraphs found for section {section_name}"
            print(f"Warning: {warning}")
            continue
        
        # Create section hash and group into chunks
        section_hash = create_section_hash(section_paragraphs)
        paragraph_chunks = group_paragraphs_into_chunks(section_paragraphs, chunk_size=6)
        
        print(f"Section {section_name}: {len(paragraph_chunks)} chunks prepared")
        
        # Store metadata
        section_metadata[section_name] = {
            'section_info': section_info,
            'section_alias': section_alias,
            'section_hash': section_hash,
            'valid_span_ids': set(span_index.get(section_name, []))
        }
        
        # Create async task
        task = summarize_section_async(
            ticker=ticker,
            form=form,
            year=year,
            section_name=section_name,
            section_alias=section_alias,
            section_hash=section_hash,
            chunks_for_section=paragraph_chunks,
            cache_base="data/cache/summaries",
            max_concurrent=max_concurrent
        )
        async_tasks.append((section_name, task))
    
    if not async_tasks:
        raise Exception("No sections were prepared for processing")
    
    # Execute all section processing concurrently
    print(f"\n--- Running {len(async_tasks)} sections concurrently ---")
    
    section_results = {}
    try:
        # Gather all async tasks
        tasks_dict = {section_name: task for section_name, task in async_tasks}
        results = await asyncio.gather(*tasks_dict.values(), return_exceptions=True)
        
        # Map results back to sections
        for i, (section_name, _) in enumerate(async_tasks):
            result = results[i]
            if isinstance(result, Exception):
                print(f"Error processing {section_name}: {result}", file=sys.stderr)
                continue
            section_results[section_name] = result
            
    except Exception as e:
        print(f"Error in concurrent processing: {e}", file=sys.stderr)
        raise
    
    # Process results and build final summaries
    processed_sections = []
    all_warnings = []
    total_cache_hits = 0
    total_cache_misses = 0
    section_stats = {}
    
    for section_name, per_chunk_results in section_results.items():
        print(f"\n--- Processing results for {section_name} ---")
        
        metadata = section_metadata[section_name]
        
        # Count cache performance
        section_cache_hits = sum(1 for result in per_chunk_results if result.get("cache_hit", False))
        section_cache_misses = len(per_chunk_results) - section_cache_hits
        
        total_cache_hits += section_cache_hits
        total_cache_misses += section_cache_misses
        
        # Merge outputs
        try:
            merged_output = merge_outputs(per_chunk_results, metadata['valid_span_ids'])
        except Exception as e:
            warning = f"Failed to merge outputs for section {section_name}: {e}"
            print(f"Error: {warning}")
            all_warnings.append(warning)
            continue
        
        # Add warnings from merge process
        merge_warnings = merged_output.get("warnings", [])
        all_warnings.extend(merge_warnings)
        
        # Build SummariesSection
        summary_section = {
            "section_name": section_name,
            "section_alias": metadata['section_alias'],
            "section_hash": metadata['section_hash'],
            "bullets": merged_output.get("bullets", []),
            "key_numbers": merged_output.get("key_numbers", []),
            "uncertainties": merged_output.get("uncertainties", []),
            "warnings": merge_warnings,
            "created_at": now_iso()
        }
        
        # Count results for reporting
        bullets_count = len(summary_section["bullets"])
        key_numbers_count = len(summary_section["key_numbers"])
        uncertainties_count = len(summary_section["uncertainties"])
        total_items = bullets_count + key_numbers_count + uncertainties_count
        
        section_stats[section_name] = {
            "bullets": bullets_count,
            "key_numbers": key_numbers_count,
            "uncertainties": uncertainties_count,
            "total_items": total_items,
            "warnings": len(merge_warnings),
            "cache_hits": section_cache_hits,
            "cache_misses": section_cache_misses
        }
        
        print(f"Results: {bullets_count}B/{key_numbers_count}N/{uncertainties_count}U "
              f"({total_items} total), {len(merge_warnings)} warnings")
        
        processed_sections.append(summary_section)
    
    if not processed_sections:
        raise Exception("No sections were successfully processed")
    
    # Write summaries
    print(f"\n--- Writing summaries.json ---")
    
    try:
        output_path = write_summaries(
            ticker=ticker,
            form=form,
            year=year,
            sections=processed_sections,
            out_base="data/processed"
        )
    except Exception as e:
        raise Exception(f"Failed to write summaries: {e}")
    
    print(f"Written to: {output_path}")
    
    # Build final report
    report = {
        "sections_processed": len(processed_sections),
        "sections_requested": len(target_sections),
        "total_warnings": len(all_warnings),
        "cache_hits": total_cache_hits,
        "cache_misses": total_cache_misses,
        "section_stats": section_stats,
        "warnings": all_warnings
    }
    
    # Print summary report
    print(f"\n=== Async Summary Report ===")
    print(f"Sections processed: {report['sections_processed']}/{report['sections_requested']}")
    
    for section_name, stats in section_stats.items():
        print(f"{section_name}: {stats['bullets']}B/{stats['key_numbers']}N/{stats['uncertainties']}U "
              f"({stats['total_items']} total), {stats['warnings']} warnings")
    
    print(f"Total warnings: {report['total_warnings']}")
    print(f"Cache performance: {report['cache_hits']} hits, {report['cache_misses']} misses")
    
    return {
        "out_path": str(output_path),
        "report": report
    }


def main():
    """CLI entry point for async summarization."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Async SEC filing summarization")
    parser.add_argument("ticker", help="Stock ticker symbol (e.g., AAPL)")
    parser.add_argument("form", help="SEC form type (e.g., 10-K)")
    parser.add_argument("year", type=int, help="Filing year")
    parser.add_argument(
        "--sections", 
        nargs="+", 
        default=["Item 7", "Item 1A"],
        help="Target section names (default: Item 7, Item 1A)"
    )
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=10,
        help="Maximum concurrent API requests (default: 10)"
    )
    
    args = parser.parse_args()
    
    try:
        result = asyncio.run(run_async(
            args.ticker, 
            args.form, 
            args.year, 
            args.sections,
            args.max_concurrent
        ))
        print(f"\n🎉 Async processing complete! Output: {result['out_path']}")
        return 0
        
    except Exception as e:
        print(f"❌ Async processing failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())