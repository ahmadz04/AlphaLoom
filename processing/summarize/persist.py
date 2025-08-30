#!/usr/bin/env python3
"""
Persist summaries.json - Write assembled SummariesFile to disk with validation.

This module handles writing LLM-generated summaries to the processed data directory,
with support for non-destructive updates that preserve existing sections.
"""

import json
from pathlib import Path
from typing import List, Dict, Any

from .schema import SummariesFile, SummariesSection, VERSION, to_json_schema


def write_summaries(
    ticker: str, 
    form: str, 
    year: int, 
    sections: List[Dict[str, Any]], 
    out_base: str = "data/processed"
) -> str:
    """
    Write summaries to data/processed/{ticker}/{form}/{year}/summaries.json using hybrid storage.
    
    If the file exists, loads it and replaces sections by section_name instead
    of overwriting everything. Validates the full file against schema before saving.
    
    Args:
        ticker: Stock ticker symbol (e.g., "AAPL")
        form: SEC form type (e.g., "10-K", "10-Q")  
        year: Filing year
        sections: List of SummariesSection dictionaries to write
        out_base: Base directory path for processed data
        
    Returns:
        String path to the written summaries.json file
        
    Raises:
        ValueError: If schema validation fails
        OSError: If file operations fail
    """
    # Import hybrid storage
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent.parent))
    from ingestion.storage.hybrid import HybridStorage
    
    storage = HybridStorage()
    
    # Construct output path
    output_path = f"{out_base}/{ticker}/{form}/{year}/summaries.json"
    
    # Load existing file or create new structure
    if storage.exists(output_path):
        existing_data = storage.read_json(output_path)
        
        # Parse existing data into SummariesFile model for validation
        existing_file = SummariesFile.model_validate(existing_data)
        
        # Create lookup of existing sections by name for replacement
        existing_sections_map = {
            section.section_name: section 
            for section in existing_file.sections
        }
    else:
        # Create new file structure
        existing_file = SummariesFile(
            ticker=ticker,
            form=form,
            year=year,
            sections=[],
            version=VERSION
        )
        existing_sections_map = {}
    
    # Convert new sections from dicts to SummariesSection objects
    new_sections = []
    for section_dict in sections:
        section = SummariesSection.model_validate(section_dict)
        new_sections.append(section)
    
    # Merge new sections with existing ones (new sections replace by section_name)
    for new_section in new_sections:
        existing_sections_map[new_section.section_name] = new_section
    
    # Update the file with merged sections
    existing_file.sections = list(existing_sections_map.values())
    
    # Sort sections by section_name for stable output
    existing_file.sections.sort(key=lambda s: s.section_name)
    
    # Validate against schema before writing
    schema = to_json_schema()
    file_dict = existing_file.model_dump()
    
    # Use jsonschema for validation if available, otherwise rely on Pydantic
    try:
        import jsonschema
        jsonschema.validate(file_dict, schema)
    except ImportError:
        # Fallback: Pydantic validation already happened during model_validate
        pass
    
    # Write using hybrid storage
    storage.write_json(file_dict, output_path)
    
    return output_path


def load_summaries(
    ticker: str,
    form: str, 
    year: int,
    out_base: str = "data/processed"
) -> SummariesFile:
    """
    Load existing summaries.json file using hybrid storage.
    
    Args:
        ticker: Stock ticker symbol
        form: SEC form type
        year: Filing year
        out_base: Base directory path for processed data
        
    Returns:
        SummariesFile object
        
    Raises:
        FileNotFoundError: If summaries.json doesn't exist
        ValueError: If file is invalid or schema validation fails
    """
    # Import hybrid storage
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent.parent))
    from ingestion.storage.hybrid import HybridStorage
    
    storage = HybridStorage()
    
    output_path = f"{out_base}/{ticker}/{form}/{year}/summaries.json"
    
    if not storage.exists(output_path):
        raise FileNotFoundError(f"Summaries file not found: {output_path}")
    
    data = storage.read_json(output_path)
    
    return SummariesFile.model_validate(data)


if __name__ == "__main__":
    # Self-test: Create and persist a test summaries file
    from .schema import Bullet, now_iso
    
    test_sections = [
        {
            "section_name": "Item 7",
            "section_alias": "Management's Discussion and Analysis", 
            "section_hash": "test_hash_123",
            "bullets": [
                {
                    "text": "Revenue grew 15% year-over-year",
                    "span_ids": ["mdna::p001", "mdna::p002"]
                }
            ],
            "key_numbers": [
                {
                    "text": "Total revenue: $394.3B",
                    "span_ids": ["mdna::p005"]
                }
            ],
            "uncertainties": [
                {
                    "text": "Supply chain risks may impact Q4",
                    "span_ids": ["mdna::p020"]
                }
            ],
            "warnings": [],
            "created_at": now_iso()
        }
    ]
    
    print("=== Testing write_summaries ===")
    output_path = write_summaries("TEST", "10-K", 2023, test_sections, "test_output")
    print(f"✓ Written to: {output_path}")
    
    # Test loading it back
    print("\n=== Testing load_summaries ===")
    loaded = load_summaries("TEST", "10-K", 2023, "test_output")
    print(f"✓ Loaded {len(loaded.sections)} sections")
    print(f"✓ First section: {loaded.sections[0].section_name}")
    
    # Test non-destructive update
    print("\n=== Testing non-destructive update ===")
    additional_sections = [
        {
            "section_name": "Item 1A",
            "section_alias": "Risk Factors",
            "section_hash": "risk_hash_456",
            "bullets": [
                {
                    "text": "Increased regulatory scrutiny",
                    "span_ids": ["risk::p001"]
                }
            ],
            "key_numbers": [],
            "uncertainties": [
                {
                    "text": "Potential antitrust actions",
                    "span_ids": ["risk::p010"]
                }
            ],
            "warnings": [],
            "created_at": now_iso()
        }
    ]
    
    output_path = write_summaries("TEST", "10-K", 2023, additional_sections, "test_output")
    print(f"✓ Updated file: {output_path}")
    
    # Verify both sections are present
    updated = load_summaries("TEST", "10-K", 2023, "test_output")
    print(f"✓ Now has {len(updated.sections)} sections:")
    for section in updated.sections:
        print(f"  - {section.section_name}: {section.section_alias}")
    
    # Clean up test file
    output_path.unlink()
    output_path.parent.rmdir()
    output_path.parent.parent.rmdir()
    output_path.parent.parent.parent.rmdir()
    print("✓ Cleanup complete")