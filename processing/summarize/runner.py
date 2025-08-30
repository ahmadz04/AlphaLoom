#!/usr/bin/env python3
"""
Orchestrator & CLI "summarize" - Top-level glue for SEC filing summarization.

This module provides the main orchestration for the summarization pipeline:
1. Loads sections.json and chunks.json
2. Builds span index and groups chunks by section
3. For each target section: processes chunks, merges outputs
4. Writes summaries.json and returns compact report

Usage:
    from processing.summarize.runner import run
    result = run("AAPL", "10-K", 2023, ["Item 7", "Item 1A"])
    print(f"Written to: {result['out_path']}")
    print(f"Report: {result['report']}")
"""

import hashlib
import os
try:
    import ujson as json
except ImportError:
    import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set, Any, Optional
from dotenv import load_dotenv

# Load environment variables from config/.env
load_dotenv('config/.env')

try:
    from .section_runner import (
        summarize_section, 
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
    from section_runner import (
        summarize_section,
        group_paragraphs_into_chunks,
        extract_span_ids_from_paragraphs
    )
    from merge_validate import merge_outputs
    from persist import write_summaries
    from schema import SummariesSection, now_iso


def load_filing_data(ticker: str, form: str, year: int) -> Optional[Dict[str, Any]]:
    """
    Load sections.json and chunks.json for a filing using hybrid storage.
    
    Args:
        ticker: Stock ticker symbol
        form: SEC form type
        year: Filing year
        
    Returns:
        Dict with sections_data, chunks_data, or None if error
    """
    # Import hybrid storage
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent.parent))
    from ingestion.storage.hybrid import HybridStorage
    
    storage = HybridStorage()
    
    sections_path = f"data/processed/{ticker}/{form}/{year}/sections.json"
    chunks_path = f"data/processed/{ticker}/{form}/{year}/chunks.json"
    
    if not storage.exists(sections_path):
        print(f"Error: sections.json not found at {sections_path}", file=sys.stderr)
        return None
    
    if not storage.exists(chunks_path):
        print(f"Error: chunks.json not found at {chunks_path}", file=sys.stderr)
        return None
    
    try:
        sections_data = storage.read_json(sections_path)
        chunks_data = storage.read_json(chunks_path)
        
        return {
            'sections_data': sections_data,
            'chunks_data': chunks_data
        }
        
    except Exception as e:
        print(f"Error loading filing data: {e}", file=sys.stderr)
        return None


def build_span_index(chunks_data: Dict) -> Dict[str, List[str]]:
    """
    Build index mapping section names to valid span IDs.
    
    Args:
        chunks_data: Loaded chunks.json data
        
    Returns:
        Dict mapping section_name -> list of span_ids
    """
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
    """
    Group paragraph chunks by section name.
    
    Args:
        chunks_data: Loaded chunks.json data
        
    Returns:
        Dict mapping section_name -> list of paragraphs
    """
    chunks_by_section = {}
    
    for paragraph in chunks_data.get("paragraphs", []):
        section = paragraph.get("section")
        
        if section:
            if section not in chunks_by_section:
                chunks_by_section[section] = []
            chunks_by_section[section].append(paragraph)
    
    return chunks_by_section


def find_section_info(sections_data: Dict, section_name: str) -> Optional[Dict]:
    """
    Find section metadata from sections.json.
    
    Args:
        sections_data: Loaded sections.json data
        section_name: Section name to find
        
    Returns:
        Section dict or None if not found
    """
    for section in sections_data.get("sections", []):
        if section.get("name") == section_name:
            return section
    return None


def create_section_hash(section_paragraphs: List[Dict]) -> str:
    """
    Create hash of section content for cache invalidation.
    
    Args:
        section_paragraphs: List of paragraphs for the section
        
    Returns:
        Hash string (first 16 characters of SHA256)
    """
    section_text = "".join([p.get("text", "") for p in section_paragraphs])
    return hashlib.sha256(section_text.encode('utf-8')).hexdigest()[:16]


def run(
    ticker: str, 
    form: str, 
    year: int, 
    target_sections: List[str] = None
) -> Dict[str, Any]:
    """
    Main orchestrator for SEC filing summarization.
    
    This function:
    1. Loads sections.json and chunks.json
    2. Builds span index and groups chunks by section
    3. For each target section: processes chunks and merges outputs
    4. Writes summaries.json and returns compact report
    
    Args:
        ticker: Stock ticker symbol (e.g., "AAPL")
        form: SEC form type (e.g., "10-K")
        year: Filing year
        target_sections: List of section names to process (default: ["Item 7", "Item 1A"])
        
    Returns:
        Dict containing:
        - out_path: Path to written summaries.json
        - report: Dict with stats (bullets per section, warnings, cache hits/misses)
        
    Raises:
        Exception: If critical errors occur during processing
    """
    if target_sections is None:
        target_sections = ["Item 7", "Item 1A"]
    
    print(f"=== Summarizing {ticker} {form} {year} ===")
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
    
    # Process each target section
    processed_sections = []
    all_warnings = []
    total_cache_hits = 0
    total_cache_misses = 0
    section_stats = {}
    
    for section_name in target_sections:
        print(f"\n--- Processing {section_name} ---")
        
        # Step 3: Get section_alias and section_hash from sections.json
        section_info = find_section_info(sections_data, section_name)
        if not section_info:
            warning = f"Section {section_name} not found in sections.json"
            print(f"Warning: {warning}")
            all_warnings.append(warning)
            continue
        
        section_alias = section_info.get("alias", section_name)
        
        # Get paragraphs for this section
        section_paragraphs = chunks_by_section.get(section_name, [])
        if not section_paragraphs:
            warning = f"No paragraphs found for section {section_name}"
            print(f"Warning: {warning}")
            all_warnings.append(warning)
            continue
        
        # Create section hash
        section_hash = create_section_hash(section_paragraphs)
        
        print(f"Section alias: {section_alias}")
        print(f"Section hash: {section_hash}")
        print(f"Paragraphs: {len(section_paragraphs)}")
        
        # Group paragraphs into chunks
        paragraph_chunks = group_paragraphs_into_chunks(section_paragraphs, chunk_size=6)
        print(f"Grouped into {len(paragraph_chunks)} chunks")
        
        # Step 4: per_chunk = summarize_section(...)
        try:
            per_chunk_results = summarize_section(
                ticker=ticker,
                form=form,
                year=year,
                section_name=section_name,
                section_alias=section_alias,
                section_hash=section_hash,
                chunks_for_section=paragraph_chunks,
                cache_base="data/cache/summaries"
            )
        except Exception as e:
            warning = f"Failed to summarize section {section_name}: {e}"
            print(f"Error: {warning}")
            all_warnings.append(warning)
            continue
        
        # Count cache hits/misses for this section
        section_cache_hits = sum(1 for result in per_chunk_results if result.get("cache_hit", False))
        section_cache_misses = len(per_chunk_results) - section_cache_hits
        
        total_cache_hits += section_cache_hits
        total_cache_misses += section_cache_misses
        
        # Step 5: merged = merge_outputs(per_chunk, valid_span_ids=span_index[section_name])
        valid_span_ids = set(span_index.get(section_name, []))
        
        try:
            merged_output = merge_outputs(per_chunk_results, valid_span_ids)
        except Exception as e:
            warning = f"Failed to merge outputs for section {section_name}: {e}"
            print(f"Error: {warning}")
            all_warnings.append(warning)
            continue
        
        # Add any warnings from merge process
        merge_warnings = merged_output.get("warnings", [])
        all_warnings.extend(merge_warnings)
        
        # Step 6: Build SummariesSection with created_at=now_iso()
        summary_section = {
            "section_name": section_name,
            "section_alias": section_alias,
            "section_hash": section_hash,
            "bullets": merged_output.get("bullets", []),
            "key_numbers": merged_output.get("key_numbers", []),
            "uncertainties": merged_output.get("uncertainties", []),
            "warnings": merge_warnings,
            "created_at": now_iso()
        }
        
        # Count bullets for reporting
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
    
    # Step 7: Call write_summaries(...)
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
    
    # Step 8: Return path + small counts
    report = {
        "sections_processed": len(processed_sections),
        "sections_requested": len(target_sections),
        "total_warnings": len(all_warnings),
        "cache_hits": total_cache_hits,
        "cache_misses": total_cache_misses,
        "section_stats": section_stats,
        "warnings": all_warnings
    }
    
    # Print compact report
    print(f"\n=== Summary Report ===")
    print(f"Sections processed: {report['sections_processed']}/{report['sections_requested']}")
    
    for section_name, stats in section_stats.items():
        print(f"{section_name}: {stats['bullets']}B/{stats['key_numbers']}N/{stats['uncertainties']}U "
              f"({stats['total_items']} total), {stats['warnings']} warnings")
    
    print(f"Total warnings: {report['total_warnings']}")
    print(f"Cache performance: {report['cache_hits']} hits, {report['cache_misses']} misses")
    
    # Validate that both target sections have ≥5 bullets (combined items)
    success_sections = []
    for section_name, stats in section_stats.items():
        if stats['total_items'] >= 5:
            success_sections.append(section_name)
    
    if len(success_sections) >= 2:
        print("✅ Success: Both sections have ≥5 bullets")
    else:
        print(f"⚠️  Warning: Only {len(success_sections)} sections have ≥5 bullets")
    
    return {
        "out_path": str(output_path),
        "report": report
    }


def main():
    """
    CLI entry point for testing the orchestrator.
    """
    import argparse
    
    parser = argparse.ArgumentParser(description="Orchestrate SEC filing summarization")
    parser.add_argument("ticker", help="Stock ticker symbol (e.g., AAPL)")
    parser.add_argument("form", help="SEC form type (e.g., 10-K)")
    parser.add_argument("year", type=int, help="Filing year")
    parser.add_argument(
        "--sections", 
        nargs="+", 
        default=["Item 7", "Item 1A"],
        help="Target section names (default: Item 7, Item 1A)"
    )
    
    args = parser.parse_args()
    
    try:
        result = run(args.ticker, args.form, args.year, args.sections)
        print(f"\n🎉 Complete! Output: {result['out_path']}")
        return 0
        
    except Exception as e:
        print(f"❌ Failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())