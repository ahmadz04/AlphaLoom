#!/usr/bin/env python3
"""
Chunk quality auditing for SEC filing paragraph data.

This module validates that paragraph chunks are properly sized (6-10 paragraphs ideal)
and contain valid span IDs that match their declared sections. Quality issues can
lead to unstable or invalid LLM summaries.
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

from .validate_inputs import build_span_index, load_test_data


def check_chunk_quality(chunks_json: dict, span_index: Dict[str, Set[str]]) -> dict:
    """
    Audit chunk quality for paragraph data integrity and sizing.
    
    Args:
        chunks_json: Loaded chunks.json data containing paragraph inventory
        span_index: Dictionary mapping section_name -> set of valid span_ids
        
    Returns:
        Dictionary with stats and warnings:
        {
            "stats": {
                "total_paragraphs": int,
                "sections_count": int,
                "avg_paragraphs_per_section": float,
                "size_distribution": dict,
                "section_stats": dict
            },
            "warnings": [str, ...]
        }
    """
    stats = {
        "total_paragraphs": 0,
        "sections_count": 0,
        "avg_paragraphs_per_section": 0.0,
        "size_distribution": {
            "tiny": 0,      # < 3 paragraphs
            "small": 0,     # 3-5 paragraphs  
            "ideal": 0,     # 6-10 paragraphs
            "large": 0,     # 11-20 paragraphs
            "huge": 0       # > 20 paragraphs
        },
        "section_stats": {}
    }
    
    warnings = []
    
    # Group paragraphs by section
    section_paragraphs = defaultdict(list)
    
    for paragraph in chunks_json.get("paragraphs", []):
        section_name = paragraph.get("section")
        if section_name:
            section_paragraphs[section_name].append(paragraph)
    
    stats["total_paragraphs"] = len(chunks_json.get("paragraphs", []))
    stats["sections_count"] = len(section_paragraphs)
    
    if stats["sections_count"] > 0:
        stats["avg_paragraphs_per_section"] = stats["total_paragraphs"] / stats["sections_count"]
    
    # Analyze each section
    for section_name, paragraphs in section_paragraphs.items():
        paragraph_count = len(paragraphs)
        
        # Categorize section size
        if paragraph_count < 3:
            stats["size_distribution"]["tiny"] += 1
            warnings.append(f"Section '{section_name}' has only {paragraph_count} paragraphs (too small)")
        elif paragraph_count <= 5:
            stats["size_distribution"]["small"] += 1
            warnings.append(f"Section '{section_name}' has {paragraph_count} paragraphs (below ideal 6-10)")
        elif paragraph_count <= 10:
            stats["size_distribution"]["ideal"] += 1
        elif paragraph_count <= 20:
            stats["size_distribution"]["large"] += 1
            warnings.append(f"Section '{section_name}' has {paragraph_count} paragraphs (above ideal 6-10)")
        else:
            stats["size_distribution"]["huge"] += 1
            warnings.append(f"Section '{section_name}' has {paragraph_count} paragraphs (too large)")
        
        # Validate span IDs for this section
        valid_spans_for_section = span_index.get(section_name, set())
        invalid_spans = []
        missing_spans = []
        text_lengths = []
        
        for paragraph in paragraphs:
            span_id = paragraph.get("span_id")
            text = paragraph.get("text", "")
            
            # Check span ID validity
            if not span_id:
                missing_spans.append("(missing span_id)")
            elif span_id not in valid_spans_for_section:
                invalid_spans.append(span_id)
            
            # Collect text length stats
            if text:
                text_lengths.append(len(text))
        
        # Calculate text statistics
        avg_text_length = sum(text_lengths) / len(text_lengths) if text_lengths else 0
        min_text_length = min(text_lengths) if text_lengths else 0
        max_text_length = max(text_lengths) if text_lengths else 0
        
        # Store section-level stats
        stats["section_stats"][section_name] = {
            "paragraph_count": paragraph_count,
            "avg_text_length": round(avg_text_length, 1),
            "min_text_length": min_text_length,
            "max_text_length": max_text_length,
            "invalid_spans": len(invalid_spans),
            "missing_spans": len(missing_spans)
        }
        
        # Add warnings for span issues
        if invalid_spans:
            warnings.append(f"Section '{section_name}' has {len(invalid_spans)} invalid span IDs: {invalid_spans[:3]}{'...' if len(invalid_spans) > 3 else ''}")
        
        if missing_spans:
            warnings.append(f"Section '{section_name}' has {len(missing_spans)} paragraphs with missing span IDs")
        
        # Check for extremely short/long paragraphs
        if text_lengths:
            very_short = [length for length in text_lengths if length < 50]
            very_long = [length for length in text_lengths if length > 2000]
            
            if very_short:
                warnings.append(f"Section '{section_name}' has {len(very_short)} very short paragraphs (< 50 chars)")
            
            if very_long:
                warnings.append(f"Section '{section_name}' has {len(very_long)} very long paragraphs (> 2000 chars)")
    
    return {
        "stats": stats,
        "warnings": warnings
    }


def print_chunk_report(result: dict, ticker: str, form: str, year: int) -> None:
    """
    Print a formatted chunk quality report.
    
    Args:
        result: Result from check_chunk_quality()
        ticker: Stock ticker symbol
        form: SEC form type
        year: Filing year
    """
    stats = result["stats"]
    warnings = result["warnings"]
    
    print(f"=== Chunk Quality Report: {ticker} {form} {year} ===")
    print()
    
    # Overall statistics
    print("📊 Overall Statistics:")
    print(f"   Total paragraphs: {stats['total_paragraphs']:,}")
    print(f"   Sections: {stats['sections_count']}")
    print(f"   Avg paragraphs per section: {stats['avg_paragraphs_per_section']:.1f}")
    print()
    
    # Size distribution
    size_dist = stats["size_distribution"]
    print("📏 Section Size Distribution:")
    print(f"   Tiny (< 3 paragraphs):    {size_dist['tiny']:2d} sections")
    print(f"   Small (3-5 paragraphs):   {size_dist['small']:2d} sections") 
    print(f"   Ideal (6-10 paragraphs):  {size_dist['ideal']:2d} sections ✅")
    print(f"   Large (11-20 paragraphs): {size_dist['large']:2d} sections")
    print(f"   Huge (> 20 paragraphs):   {size_dist['huge']:2d} sections")
    print()
    
    # Top/bottom sections by size
    section_stats = stats["section_stats"]
    if section_stats:
        sorted_sections = sorted(section_stats.items(), key=lambda x: x[1]["paragraph_count"], reverse=True)
        
        print("📈 Largest Sections:")
        for section_name, section_data in sorted_sections[:3]:
            count = section_data["paragraph_count"]
            avg_len = section_data["avg_text_length"]
            print(f"   {section_name}: {count} paragraphs (avg {avg_len:.0f} chars)")
        print()
        
        print("📉 Smallest Sections:")
        for section_name, section_data in sorted_sections[-3:]:
            count = section_data["paragraph_count"]
            avg_len = section_data["avg_text_length"]
            print(f"   {section_name}: {count} paragraphs (avg {avg_len:.0f} chars)")
        print()
    
    # Warnings
    if warnings:
        print(f"⚠️  Quality Warnings ({len(warnings)}):")
        for i, warning in enumerate(warnings[:10], 1):  # Limit to first 10 warnings
            print(f"   {i}. {warning}")
        if len(warnings) > 10:
            print(f"   ... and {len(warnings) - 10} more warnings")
    else:
        print("✅ No quality warnings - all chunks look good!")
    
    print()


def main():
    """CLI entry point for chunk quality checking."""
    parser = argparse.ArgumentParser(
        description="Audit chunk quality for SEC filing paragraph data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check chunk quality for AAPL 2023 10-K
  python -m processing.summarize.chunk_checks --ticker AAPL --form 10-K --year 2023
  
  # Check with detailed section stats
  python -m processing.summarize.chunk_checks --ticker AAPL --form 10-K --year 2023 --detailed
        """
    )
    
    parser.add_argument('--ticker', required=True, help='Stock ticker symbol (e.g., AAPL)')
    parser.add_argument('--form', required=True, help='SEC form type (e.g., 10-K, 10-Q)')
    parser.add_argument('--year', required=True, type=int, help='Filing year')
    parser.add_argument('--detailed', action='store_true', help='Show detailed section statistics')
    
    args = parser.parse_args()
    
    ticker = args.ticker.upper()
    form = args.form.upper()
    year = args.year
    
    # Load data
    base_dir = Path("data/processed") / ticker / form / str(year)
    sections_path = base_dir / "sections.json"
    chunks_path = base_dir / "chunks.json"
    
    try:
        with open(sections_path, 'r') as f:
            sections_json = json.load(f)
        with open(chunks_path, 'r') as f:
            chunks_json = json.load(f)
    except FileNotFoundError as e:
        print(f"Error: Data files not found: {e}", file=sys.stderr)
        print(f"Expected files in: {base_dir}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error loading data: {e}", file=sys.stderr)
        return 1
    
    # Build span index
    span_index = build_span_index(chunks_json)
    
    # Run quality check
    result = check_chunk_quality(chunks_json, span_index)
    
    # Print report
    print_chunk_report(result, ticker, form, year)
    
    # Show detailed section stats if requested
    if args.detailed:
        print("📋 Detailed Section Statistics:")
        section_stats = result["stats"]["section_stats"]
        
        for section_name, stats in sorted(section_stats.items()):
            print(f"\n   {section_name}:")
            print(f"      Paragraphs: {stats['paragraph_count']}")
            print(f"      Avg text length: {stats['avg_text_length']:.0f} chars")
            print(f"      Text range: {stats['min_text_length']}-{stats['max_text_length']} chars")
            if stats['invalid_spans'] > 0:
                print(f"      ❌ Invalid spans: {stats['invalid_spans']}")
            if stats['missing_spans'] > 0:
                print(f"      ❌ Missing spans: {stats['missing_spans']}")
    
    # Return appropriate exit code
    warning_count = len(result["warnings"])
    if warning_count == 0:
        print("✅ Chunk quality check passed!")
        return 0
    elif warning_count < 5:
        print(f"⚠️  Chunk quality check completed with {warning_count} minor warnings")
        return 0
    else:
        print(f"❌ Chunk quality check found {warning_count} warnings - review recommended")
        return 1


if __name__ == "__main__":
    sys.exit(main())