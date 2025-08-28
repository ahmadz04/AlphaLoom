#!/usr/bin/env python3
"""
CLI tool for analyzing and summarizing SEC filing sections.

This tool loads processed sections.json and chunks.json files to analyze
filing structure and prepare for LLM-based summarization.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def resolve_data_paths(ticker: str, form: str, year: int) -> Tuple[Path, Path]:
    """
    Resolve paths to sections.json and chunks.json files.
    
    Args:
        ticker: Stock ticker symbol
        form: SEC form type
        year: Filing year
        
    Returns:
        Tuple of (sections_path, chunks_path)
    """
    base_dir = Path("data/processed") / ticker / form / str(year)
    sections_path = base_dir / "sections.json"
    chunks_path = base_dir / "chunks.json"
    
    return sections_path, chunks_path


def load_json_safe(file_path: Path) -> Optional[dict]:
    """
    Safely load JSON file with error handling.
    
    Args:
        file_path: Path to JSON file
        
    Returns:
        Parsed JSON data or None if error
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {file_path}: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error: Failed to read {file_path}: {e}", file=sys.stderr)
        return None


def analyze_sections(sections_data: dict, chunks_data: dict, requested_sections: List[str]) -> None:
    """
    Analyze and print section statistics.
    
    Args:
        sections_data: Loaded sections.json data
        chunks_data: Loaded chunks.json data  
        requested_sections: List of section names to analyze
    """
    # Build section lookup from sections.json
    sections_lookup = {}
    for section in sections_data.get("sections", []):
        sections_lookup[section["name"]] = section
    
    # Count paragraphs per section from chunks.json
    section_paragraph_counts = {}
    for paragraph in chunks_data.get("paragraphs", []):
        section_name = paragraph["section"]
        section_paragraph_counts[section_name] = section_paragraph_counts.get(section_name, 0) + 1
    
    print(f"Analysis for {sections_data.get('ticker', 'UNKNOWN')} "
          f"{sections_data.get('form', 'UNKNOWN')} {sections_data.get('year', 'UNKNOWN')}")
    print()
    
    # Analyze each requested section
    for section_name in requested_sections:
        if section_name not in sections_lookup:
            print(f"❌ {section_name}: Section not found")
            continue
            
        section_info = sections_lookup[section_name]
        paragraph_count = section_paragraph_counts.get(section_name, 0)
        
        # Calculate section span (character count)
        section_start = section_info.get("start", 0)
        section_end = section_info.get("end", 0)
        section_span = section_end - section_start if section_end and section_start else 0
        
        print(f"✅ {section_name}: {section_info.get('alias', 'N/A')}")
        print(f"   • Character span: {section_span:,} characters")
        print(f"   • Paragraph chunks: {paragraph_count}")
        print()


def cmd_analyze(args) -> int:
    """
    Handle the analyze command.
    
    Args:
        args: Parsed command line arguments
        
    Returns:
        Exit code (0 for success, 1 for error)
    """
    ticker = args.ticker.upper()
    form = args.form.upper()
    year = args.year
    requested_sections = [s.strip() for s in args.sections.split(',') if s.strip()]
    
    print(f"Loading data for {ticker} {form} {year}...")
    print(f"Requested sections: {', '.join(requested_sections)}")
    print()
    
    # Resolve file paths
    sections_path, chunks_path = resolve_data_paths(ticker, form, year)
    
    # Load JSON files
    sections_data = load_json_safe(sections_path)
    if sections_data is None:
        return 1
        
    chunks_data = load_json_safe(chunks_path)
    if chunks_data is None:
        return 1
    
    # Analyze sections
    analyze_sections(sections_data, chunks_data, requested_sections)
    
    return 0


def cmd_summarize(args) -> int:
    """
    Handle the summarize command.
    
    Args:
        args: Parsed command line arguments
        
    Returns:
        Exit code (0 for success, 1 for error)
    """
    ticker = args.ticker.upper()
    form = args.form.upper() 
    year = args.year
    requested_sections = [s.strip() for s in args.sections.split(',') if s.strip()]
    
    print(f"🤖 Starting summarization for {ticker} {form} {year}")
    print(f"Target sections: {', '.join(requested_sections)}")
    print()
    
    try:
        # Import the runner module
        from .runner import run
        
        # Execute the summarization pipeline
        result = run(ticker, form, year, requested_sections)
        
        print(f"\n✅ Summarization complete!")
        print(f"📄 Output file: {result['out_path']}")
        
        # Print compact summary from report
        report = result['report']
        print(f"📊 Summary: {report['sections_processed']}/{report['sections_requested']} sections processed")
        
        if report['section_stats']:
            print("📈 Results:")
            for section_name, stats in report['section_stats'].items():
                print(f"   • {section_name}: {stats['bullets']}B/{stats['key_numbers']}N/{stats['uncertainties']}U")
        
        if report['total_warnings'] > 0:
            print(f"⚠️  {report['total_warnings']} warnings (see output above)")
        
        print(f"💾 Cache: {report['cache_hits']} hits, {report['cache_misses']} misses")
        
        return 0
        
    except Exception as e:
        print(f"❌ Summarization failed: {e}", file=sys.stderr)
        return 1


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze and summarize SEC filing sections",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze specific sections for AAPL 2023 10-K
  python -m processing.summarize.cli analyze --ticker AAPL --form 10-K --year 2023 --sections "Item 7,Item 1A"
  
  # Generate LLM summaries for Item 7 and Item 1A
  python -m processing.summarize.cli summarize --ticker AAPL --form 10-K --year 2023 --sections "Item 7,Item 1A"
        """
    )
    
    # Create subcommands
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    subparsers.required = True
    
    # Analyze command
    analyze_parser = subparsers.add_parser('analyze', help='Analyze section structure and counts')
    analyze_parser.add_argument('--ticker', required=True, help='Stock ticker symbol (e.g., AAPL)')
    analyze_parser.add_argument('--form', required=True, help='SEC form type (e.g., 10-K, 10-Q)')
    analyze_parser.add_argument('--year', required=True, type=int, help='Filing year')
    analyze_parser.add_argument('--sections', required=True, 
                               help='Comma-separated list of section names (e.g., "Item 7,Item 1A")')
    analyze_parser.set_defaults(func=cmd_analyze)
    
    # Summarize command
    summarize_parser = subparsers.add_parser('summarize', help='Generate LLM summaries of SEC filing sections')
    summarize_parser.add_argument('--ticker', required=True, help='Stock ticker symbol (e.g., AAPL)')
    summarize_parser.add_argument('--form', required=True, help='SEC form type (e.g., 10-K, 10-Q)')
    summarize_parser.add_argument('--year', required=True, type=int, help='Filing year')
    summarize_parser.add_argument('--sections', required=True,
                                 help='Comma-separated list of section names (e.g., "Item 7,Item 1A")')
    summarize_parser.set_defaults(func=cmd_summarize)
    
    # Parse arguments and execute command
    args = parser.parse_args()
    
    try:
        exit_code = args.func(args)
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()