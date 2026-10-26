#!/usr/bin/env python3
"""
SEC Filing Sectionizer - Extract and identify SEC item boundaries and paragraph spans.

This script processes raw SEC filing text to identify sections (Items) and their boundaries,
preparing structured data for downstream LLM analysis.
"""

import argparse
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

# Run as a script from processing/, so put the repo root on the path for ingestion.*
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ingestion.storage.hybrid import HybridStorage

_storage = None


def get_storage():
    """Lazily create the shared storage (local or S3, per USE_S3_STORAGE)."""
    global _storage
    if _storage is None:
        _storage = HybridStorage()
    return _storage


def compile_heading_patterns(form):
    """
    Compile regex patterns to detect SEC Item headings.
    
    Args:
        form: SEC form type (e.g., "10-K", "10-Q")
    
    Returns:
        Compiled regex pattern for detecting Item headings
    """
    # Pattern for "=== Title ===" format (as seen in our Apple 10-K file)
    # This matches the actual format in the processed filing text
    pattern = r'^\s*===\s*(?P<title>.*?)\s*===\s*$'
    
    return re.compile(pattern, re.MULTILINE | re.IGNORECASE)


def is_mda_title(title):
    """Check if title matches MD&A (Management Discussion & Analysis) patterns."""
    if not title:
        return False
    
    title_lower = title.lower()
    # Remove common punctuation and normalize spaces
    title_clean = re.sub(r'[^\w\s&]', ' ', title_lower)
    title_clean = re.sub(r'\s+', ' ', title_clean).strip()
    
    # Check for MD&A abbreviation
    if 'md&a' in title_clean or 'mda' in title_clean:
        return True
    
    # Check for full phrases
    has_management = 'management' in title_clean
    has_discussion = 'discussion' in title_clean
    has_analysis = 'analysis' in title_clean
    
    return has_management and has_discussion and has_analysis


def is_risk_factors_title(title):
    """Check if title matches Risk Factors patterns."""
    if not title:
        return False
    
    title_lower = title.lower()
    return 'risk' in title_lower and 'factor' in title_lower


def map_title_to_item(title):
    """
    Map section titles to SEC Item numbers based on common patterns.
    
    Args:
        title: Section title string
    
    Returns:
        Item number (e.g., "1", "1A") or None if no match
    """
    title_lower = title.lower().strip()
    
    # Common title mappings for SEC 10-K filings
    title_mappings = {
        'business': '1',
        'risk factors': '1A', 
        'unresolved staff comments': '1B',
        'none': '1C',  # Common for empty sections
        'properties': '2',
        'legal proceedings': '3',
        'submission of matters to a vote': '4',
        'market for securities': '5',
        'selected financial data': '6',
        'management discussion & analysis (md&a)': '7',
        'management\'s discussion and analysis': '7',
        'quantitative and qualitative disclosures about market risks': '7A',
        'financial statements and supplementary data': '8',
        'changes in and disagreements with accountants': '9',
        'controls and procedures': '9A',
        'other information': '9B',
        'disclosure regarding foreign jurisdictions': '9C',
        'directors, executive officers and corporate governance': '10',
        'executive compensation': '11',
        'security ownership': '12',
        'certain relationships and related transactions': '13',
        'principal accounting fees and services': '14',
        'exhibits and financial statement schedules': '15',
        'form 10-k summary': '16'
    }
    
    # Check for exact matches first
    if title_lower in title_mappings:
        return title_mappings[title_lower]
    
    # Check for partial matches
    if 'risk' in title_lower and 'factor' in title_lower:
        return '1A'
    elif is_mda_title(title):
        return '7'
    elif 'financial statements' in title_lower:
        return '8'
    elif 'legal' in title_lower and 'proceeding' in title_lower:
        return '3'
    elif 'properties' in title_lower:
        return '2'
    elif 'business' in title_lower and len(title_lower) < 20:  # Avoid false matches
        return '1'
    
    return None


def find_headings(text):
    """
    Find all SEC Item headings in the text.
    
    Args:
        text: Normalized filing text
    
    Returns:
        List of dictionaries with keys: name, title, start
    """
    pattern = compile_heading_patterns("10-K")  # Use pattern for "=== Title ===" format
    headings = []
    
    # Find all matches
    for match in pattern.finditer(text):
        raw_title = match.group('title') or ""
        start_pos = match.start()
        
        # Clean up the title
        title = raw_title.strip()
        
        # Map title to Item number
        item_num = map_title_to_item(title)
        
        if item_num:  # Only include if we can map to an Item number
            heading = {
                'name': f"Item {item_num}",
                'title': title,
                'start': start_pos
            }
            headings.append(heading)
    
    # Check if we have the critical sections (Item 1, Item 1A, Item 7)
    found_sections = {h['name'] for h in headings}
    critical_sections = {"Item 1", "Item 1A", "Item 7"}
    missing_critical = critical_sections - found_sections
    
    # If we're missing critical sections, try fallback patterns
    if missing_critical:
        fallback_headings = []
        
        # Pattern 1: "PART I ITEM X" format
        fallback_pattern1 = re.compile(
            r'PART\s+[IVX]+\s+ITEM\s+(\d+[A-Z]*)\.\s+([^\n]+)',
            re.MULTILINE | re.IGNORECASE
        )
        
        for match in fallback_pattern1.finditer(text):
            item_num = match.group(1).strip()
            title = match.group(2).strip()
            start_pos = match.start()
            
            section_name = f"Item {item_num}"
            # Only add if we don't already have this section or if it's a critical missing section
            if section_name not in found_sections or section_name in missing_critical:
                heading = {
                    'name': section_name,
                    'title': title,
                    'start': start_pos
                }
                fallback_headings.append(heading)
        
        # Pattern 2: Standalone section headers
        standalone_patterns = [
            (r'^RISK\s+FACTORS\s+', 'Item 1A', 'Risk Factors'),
            (r'^MANAGEMENT[\'\u2019]?S\s+DISCUSSION\s+AND\s+ANALYSIS', 'Item 7', 'Management\'s Discussion and Analysis')
        ]
        
        for pattern_text, item_name, section_title in standalone_patterns:
            pattern = re.compile(pattern_text, re.MULTILINE | re.IGNORECASE)
            for match in pattern.finditer(text):
                start_pos = match.start()
                if item_name not in found_sections or item_name in missing_critical:
                    heading = {
                        'name': item_name,
                        'title': section_title,
                        'start': start_pos
                    }
                    fallback_headings.append(heading)
        
        # Replace the existing headings with fallback if fallback found critical sections
        if fallback_headings:
            fallback_sections = {h['name'] for h in fallback_headings}
            if critical_sections.intersection(fallback_sections):
                # Use fallback headings as they contain critical sections
                headings = fallback_headings
    
    # Sort by start position
    headings.sort(key=lambda x: x['start'])
    
    return headings


def split_paragraphs(text, start, end, min_len):
    """
    Split text section into paragraphs and return with absolute positions.
    
    Args:
        text: Full text string
        start: Start position in full text
        end: End position in full text
        min_len: Minimum paragraph length to keep
    
    Returns:
        List of dictionaries with keys: abs_start, abs_end, text
    """
    # Extract section text
    section_text = text[start:end]
    
    # Try different splitting strategies
    # First try double newlines
    raw_paragraphs = re.split(r'\n{2,}', section_text)
    
    # If that doesn't produce many paragraphs, try sentence-based splitting
    if len(raw_paragraphs) <= 2 and len(section_text) > 1000:
        # Split on periods followed by spaces and capital letters (likely sentence boundaries)
        # But be careful not to split on abbreviations
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', section_text)
        
        # Group sentences into paragraphs of reasonable length
        raw_paragraphs = []
        current_para = ""
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
                
            # If adding this sentence would make paragraph too long, start new paragraph
            if current_para and len(current_para + " " + sentence) > 800:
                raw_paragraphs.append(current_para)
                current_para = sentence
            else:
                if current_para:
                    current_para += " " + sentence
                else:
                    current_para = sentence
        
        # Add the last paragraph
        if current_para:
            raw_paragraphs.append(current_para)
    
    paragraphs = []
    current_pos = start
    
    for raw_para in raw_paragraphs:
        # Trim whitespace
        para_text = raw_para.strip()
        
        if not para_text:
            continue
        
        # Find the actual start of this paragraph in the full text
        # Use a portion of the paragraph text to search
        search_text = para_text[:100] if len(para_text) > 100 else para_text
        para_start = text.find(search_text, current_pos)
        
        if para_start == -1:
            # Fallback - use current position
            para_start = current_pos
        
        para_end = para_start + len(para_text)
        
        # Check if paragraph should be kept
        should_keep = len(para_text) >= min_len
        
        # Keep short paragraphs with strong signals
        if not should_keep:
            para_lower = para_text.lower()
            strong_signals = [
                'forward-looking statements',
                'risk factors',
                'safe harbor',
                'cautionary statement',
                'non-gaap',
                'sec filings'
            ]
            
            for signal in strong_signals:
                if signal in para_lower:
                    should_keep = True
                    break
        
        if should_keep:
            paragraphs.append({
                'abs_start': para_start,
                'abs_end': para_end,
                'text': para_text
            })
        
        # Move current position forward
        current_pos = para_end
    
    return paragraphs


def build_paragraph_inventory(text, sections, min_len):
    """
    Build a flat list of all paragraphs across all sections.
    
    Args:
        text: Full normalized text
        sections: List of section headings with start positions
        min_len: Minimum paragraph length
    
    Returns:
        List of dictionaries with keys: section, abs_start, abs_end, text
    """
    inventory = []
    
    for i, section in enumerate(sections):
        # Determine section boundaries
        section_start = section['start']
        if i + 1 < len(sections):
            section_end = sections[i + 1]['start']
        else:
            section_end = len(text)
        
        # Split section into paragraphs
        section_paragraphs = split_paragraphs(text, section_start, section_end, min_len)
        
        # Add section information to each paragraph
        for para in section_paragraphs:
            inventory.append({
                'section': section['name'],
                'abs_start': para['abs_start'],
                'abs_end': para['abs_end'],
                'text': para['text']
            })
    
    # Sort by absolute start position
    inventory.sort(key=lambda x: x['abs_start'])
    
    return inventory


def prefix_for_item(name):
    """
    Map SEC Item names to short prefixes for span IDs.
    
    Args:
        name: Item name (e.g., "Item 7", "Item 1A")
    
    Returns:
        Short prefix string
    """
    # Handle special cases
    if name == "Item 7":
        return "mdna"
    elif name == "Item 1A":
        return "risks"
    elif name == "Item 1":
        return "biz"
    else:
        # Extract number part and create generic prefix
        # Handle cases like "Item 10", "Item 1B", etc.
        item_part = name.replace("Item ", "").lower()
        return f"item{item_part}"


def attach_span_ids(paragraphs):
    """
    Assign unique span IDs to paragraphs grouped by section.
    
    Args:
        paragraphs: List of paragraph dictionaries
    
    Returns:
        List of paragraphs with span_id field added
    """
    # Group paragraphs by section
    section_groups = {}
    for para in paragraphs:
        section = para['section']
        if section not in section_groups:
            section_groups[section] = []
        section_groups[section].append(para)
    
    # Sort paragraphs within each section by abs_start
    for section in section_groups:
        section_groups[section].sort(key=lambda x: x['abs_start'])
    
    # Assign span IDs
    updated_paragraphs = []
    for section, section_paras in section_groups.items():
        prefix = prefix_for_item(section)
        
        for i, para in enumerate(section_paras):
            # Create zero-padded counter (p000, p001, etc.)
            counter = f"p{i:03d}"
            span_id = f"{prefix}::{counter}"
            
            # Add span_id to paragraph
            para_with_id = para.copy()
            para_with_id['span_id'] = span_id
            updated_paragraphs.append(para_with_id)
    
    # Sort final list by abs_start to maintain document order
    updated_paragraphs.sort(key=lambda x: x['abs_start'])
    
    return updated_paragraphs


def write_sections_json(output_dir, ticker, form, year, source_text_path, headings, warnings=None):
    """
    Write sections.json file with SEC item boundaries.
    
    Args:
        output_dir: Output directory path
        ticker: Stock ticker
        form: SEC form type
        year: Filing year
        source_text_path: Path to source text file
        headings: List of section headings with start positions
        warnings: Optional list of warning messages
    """
    if warnings is None:
        warnings = []
    
    # Build sections list with end positions
    sections = []
    for i, heading in enumerate(headings):
        # Calculate end position
        if i + 1 < len(headings):
            end_pos = headings[i + 1]['start']
        else:
            # For the last section, we don't know the exact end without the full text
            # Use a placeholder that will be updated if full text is available
            end_pos = None
        
        section = {
            "name": heading['name'],
            "alias": heading['title'],
            "start": heading['start'],
            "end": end_pos
        }
        sections.append(section)
    
    sections_data = {
        "ticker": ticker,
        "form": form,
        "year": year,
        "source_text": source_text_path,
        "warnings": warnings,
        "sections": sections
    }
    
    output_path = os.path.join(output_dir, "sections.json")
    get_storage().write_json(sections_data, output_path)
    
    return output_path


def write_chunks_json(output_dir, ticker, form, year, source_text_path, paragraphs_with_ids, warnings=None):
    """
    Write chunks.json file with paragraph inventory.
    
    Args:
        output_dir: Output directory path
        ticker: Stock ticker
        form: SEC form type
        year: Filing year
        source_text_path: Path to source text file
        paragraphs_with_ids: List of paragraphs with span IDs
        warnings: Optional list of warning messages
    """
    if warnings is None:
        warnings = []
    
    # Build paragraphs list
    paragraphs = []
    for para in paragraphs_with_ids:
        paragraph = {
            "section": para['section'],
            "span_id": para['span_id'],
            "abs_start": para['abs_start'],
            "abs_end": para['abs_end'],
            "text": para['text']
        }
        paragraphs.append(paragraph)
    
    chunks_data = {
        "ticker": ticker,
        "form": form,
        "year": year,
        "source_text": source_text_path,
        "warnings": warnings,
        "paragraphs": paragraphs
    }
    
    output_path = os.path.join(output_dir, "chunks.json")
    get_storage().write_json(chunks_data, output_path)
    
    return output_path


def validate(sections, paragraphs):
    """
    Validate the extracted sections and paragraphs.
    
    Args:
        sections: List of section headings
        paragraphs: List of paragraphs with span IDs
    
    Returns:
        Tuple of (warnings, exit_code) where exit_code is 0 or 2
    """
    warnings = []
    exit_code = 0
    
    # Check for required sections
    section_names = [section['name'] for section in sections]
    required_sections = ["Item 7", "Item 1A"]
    
    for required in required_sections:
        if required not in section_names:
            warnings.append(f"Missing required section: {required}")
            exit_code = 2
    
    # Count paragraphs per section
    section_paragraph_counts = {}
    for para in paragraphs:
        section = para['section']
        section_paragraph_counts[section] = section_paragraph_counts.get(section, 0) + 1
    
    # Check paragraph counts for required sections that are present
    for required in required_sections:
        if required in section_names:
            count = section_paragraph_counts.get(required, 0)
            if count < 10:
                warnings.append(f"Section {required} has only {count} paragraphs (expected >= 10)")
    
    return warnings, exit_code


def read_and_normalize(path, encoding="utf-8"):
    """
    Read and normalize SEC filing text.
    
    Args:
        path: Path to text file
        encoding: Text encoding (default: utf-8)
    
    Returns:
        Normalized string with page headers/footers removed
    """
    try:
        text = get_storage().read_text(path, encoding=encoding)
    except FileNotFoundError:
        print(f"Error: File not found: {path}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file {path}: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Normalize Unicode to NFC
    text = unicodedata.normalize('NFC', text)
    
    # Convert all newlines to \n
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    
    # Split into lines for processing
    lines = text.split('\n')
    
    # Remove page headers/footers heuristically
    cleaned_lines = []
    page_pattern = re.compile(r'^Page\s+\d+(\s+of\s+\d+)?$', re.IGNORECASE)
    
    for line in lines:
        stripped = line.strip()
        
        # Skip lines that are only digits
        if stripped.isdigit():
            continue
            
        # Skip lines matching page pattern (e.g., "Page 1", "Page 1 of 10")
        if page_pattern.match(stripped):
            continue
            
        cleaned_lines.append(line)
    
    # Rejoin lines
    normalized_text = '\n'.join(cleaned_lines)
    
    return normalized_text


def main():
    parser = argparse.ArgumentParser(
        description="Extract SEC item boundaries and paragraph spans from filing text"
    )
    
    # Required arguments
    parser.add_argument("--ticker", required=True, 
                       help="Stock ticker symbol (e.g., AAPL)")
    parser.add_argument("--form", required=True,
                       help="SEC form type (e.g., 10-K, 10-Q)")
    parser.add_argument("--year", required=True, type=int,
                       help="Filing year")
    parser.add_argument("--input-text", required=True,
                       help="Path to input text file")
    parser.add_argument("--out-dir", required=True,
                       help="Output directory for processed files")
    
    # Optional arguments
    parser.add_argument("--min-paragraph-len", type=int, default=40,
                       help="Minimum paragraph length (default: 40)")
    parser.add_argument("--encoding", default="utf-8",
                       help="Text file encoding (default: utf-8)")
    
    args = parser.parse_args()
    
    # Print parsed arguments in one line
    print(f"ticker={args.ticker} form={args.form} year={args.year} "
          f"input-text={args.input_text} out-dir={args.out_dir} "
          f"min-paragraph-len={args.min_paragraph_len} encoding={args.encoding}")
    
    # Read and normalize the input text
    normalized_text = read_and_normalize(args.input_text, args.encoding)
    
    # Check if file is empty after normalization
    if not normalized_text or len(normalized_text.strip()) == 0:
        print(f"Error: File is empty after normalization: {args.input_text}", file=sys.stderr)
        sys.exit(1)
    
    # Print character count
    char_count = len(normalized_text)
    print(f"Total character count: {char_count}")
    
    # Find SEC Item headings
    headings = find_headings(normalized_text)
    
    # Check if any headings were found
    if not headings:
        print("Error: No SEC Item headings found in the text", file=sys.stderr)
        sys.exit(1)
    
    # Print found headings (first 10 only)
    print(f"Found {len(headings)} headings:")
    for i, heading in enumerate(headings[:10]):
        title_preview = heading['title'][:50] + "..." if len(heading['title']) > 50 else heading['title']
        print(f"  {heading['name']} at position {heading['start']}: {title_preview}")
    
    if len(headings) > 10:
        print(f"  ... and {len(headings) - 10} more")
    
    # Build paragraph inventory
    paragraph_inventory = build_paragraph_inventory(normalized_text, headings, args.min_paragraph_len)
    
    # Print paragraph statistics
    print(f"\nTotal paragraph count: {len(paragraph_inventory)}")
    
    # Attach span IDs
    paragraphs_with_ids = attach_span_ids(paragraph_inventory)
    
    # Print first 10 span IDs with their section names
    print("\nFirst 10 span IDs:")
    for i, para in enumerate(paragraphs_with_ids[:10]):
        print(f"  {i+1}. {para['span_id']} [{para['section']}]")
    
    # Show 3 sample snippets (truncated)
    print("\nSample paragraphs:")
    sample_count = min(3, len(paragraphs_with_ids))
    for i in range(sample_count):
        para = paragraphs_with_ids[i]
        snippet = para['text'][:100] + "..." if len(para['text']) > 100 else para['text']
        print(f"  {i+1}. {para['span_id']} [{para['section']}] at {para['abs_start']}-{para['abs_end']}: {snippet}")
    
    # Update section end positions using the full text
    for i, heading in enumerate(headings):
        if i + 1 < len(headings):
            heading['end'] = headings[i + 1]['start']
        else:
            heading['end'] = len(normalized_text)
    
    # Validate the extracted data
    validation_warnings, exit_code = validate(headings, paragraphs_with_ids)
    
    # Write output files
    print("\nWriting output files:")
    
    # Write sections.json (include validation warnings)
    sections_path = write_sections_json(
        args.out_dir, 
        args.ticker, 
        args.form, 
        args.year, 
        args.input_text, 
        headings,
        validation_warnings
    )
    print(f"  sections.json: {sections_path} ({get_storage().get_storage_type()})")
    
    # Write chunks.json (include validation warnings)
    chunks_path = write_chunks_json(
        args.out_dir,
        args.ticker,
        args.form, 
        args.year,
        args.input_text,
        paragraphs_with_ids,
        validation_warnings
    )
    print(f"  chunks.json: {chunks_path} ({get_storage().get_storage_type()})")
    
    # Print summary line
    print(f"\nsectionize ok ticker={args.ticker} form={args.form} year={args.year} "
          f"items={len(headings)} paragraphs={len(paragraphs_with_ids)} "
          f"warnings={len(validation_warnings)}")
    
    # Print warnings if any
    if validation_warnings:
        print("Warnings:")
        for warning in validation_warnings:
            print(f"  - {warning}")
    
    # Exit with appropriate code
    sys.exit(exit_code)


if __name__ == "__main__":
    main()