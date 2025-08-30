#!/usr/bin/env python3
"""
S3-Enhanced Persist summaries.json - Write assembled SummariesFile to disk/S3 with validation.

This module extends the original persist.py with S3 support, allowing seamless
migration from local storage to cloud storage while maintaining backwards compatibility.
"""

import json
import os
from pathlib import Path
from typing import List, Dict, Any, Union
from dotenv import load_dotenv

# Load environment variables
load_dotenv('config/.env')

# Import S3 service
try:
    import sys
    sys.path.append('/Users/ahmad/Documents/GitHub/AlphaLoom')
    from services.s3_service import get_s3_service, get_s3_path, get_local_path
    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False

# Import original functions for backward compatibility
try:
    from .schema import SummariesFile, SummariesSection, VERSION, to_json_schema
except ImportError:
    # If running as script, try importing from local directory
    import sys
    from pathlib import Path as PathLib
    sys.path.append(str(PathLib(__file__).parent))
    from schema import SummariesFile, SummariesSection, VERSION, to_json_schema


class PersistManager:
    """
    Enhanced persist manager that supports both local and S3 storage.
    """
    
    def __init__(self, use_s3: bool = None):
        """
        Initialize persist manager.
        
        Args:
            use_s3: Force S3 usage (True/False) or auto-detect from env (None)
        """
        if use_s3 is None:
            # Auto-detect: use S3 if credentials are available
            use_s3 = (
                S3_AVAILABLE and 
                os.getenv('AWS_S3_BUCKET') and 
                os.getenv('AWS_ACCESS_KEY_ID')
            )
        
        self.use_s3 = use_s3
        
        if self.use_s3 and not S3_AVAILABLE:
            raise RuntimeError("S3 requested but boto3 not installed or S3 service unavailable")
        
        if self.use_s3:
            self.s3_service = get_s3_service()
            print(f"Persist manager initialized with S3 storage (bucket: {self.s3_service.bucket_name})")
        else:
            print("Persist manager initialized with local storage")
    
    def write_summaries(
        self,
        ticker: str, 
        form: str, 
        year: int, 
        sections: List[Dict[str, Any]], 
        out_base: str = "data/processed"
    ) -> str:
        """
        Write summaries to processed storage (local or S3).
        
        If the file exists, loads it and replaces sections by section_name instead
        of overwriting everything. Validates the full file against schema before saving.
        
        Args:
            ticker: Stock ticker symbol (e.g., "AAPL")
            form: SEC form type (e.g., "10-K", "10-Q")  
            year: Filing year
            sections: List of SummariesSection dictionaries to write
            out_base: Base directory path for processed data
            
        Returns:
            Path/key to the written summaries.json file
            
        Raises:
            ValueError: If schema validation fails
            Exception: If file operations fail
        """
        if self.use_s3:
            return self._write_summaries_s3(ticker, form, year, sections, out_base)
        else:
            return self._write_summaries_local(ticker, form, year, sections, out_base)
    
    def load_summaries(
        self,
        ticker: str,
        form: str, 
        year: int,
        out_base: str = "data/processed"
    ) -> SummariesFile:
        """
        Load existing summaries.json file from storage.
        
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
        if self.use_s3:
            return self._load_summaries_s3(ticker, form, year, out_base)
        else:
            return self._load_summaries_local(ticker, form, year, out_base)
    
    def _write_summaries_s3(self, ticker: str, form: str, year: int, 
                           sections: List[Dict[str, Any]], out_base: str) -> str:
        """Write summaries to S3."""
        # Construct S3 key
        s3_key = get_s3_path(f"{out_base}/{ticker}/{form}/{year}/summaries.json")
        
        # Load existing file or create new structure
        existing_data = self.s3_service.download_json(s3_key)
        
        if existing_data:
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
        
        # Upload to S3
        success = self.s3_service.upload_json(file_dict, s3_key)
        if not success:
            raise Exception(f"Failed to upload summaries to S3: {s3_key}")
        
        return s3_key
    
    def _write_summaries_local(self, ticker: str, form: str, year: int,
                              sections: List[Dict[str, Any]], out_base: str) -> str:
        """Write summaries to local filesystem."""
        # Use original persist logic
        from persist import write_summaries as original_write_summaries
        output_path = original_write_summaries(ticker, form, year, sections, out_base)
        return str(output_path)
    
    def _load_summaries_s3(self, ticker: str, form: str, year: int, out_base: str) -> SummariesFile:
        """Load summaries from S3."""
        s3_key = get_s3_path(f"{out_base}/{ticker}/{form}/{year}/summaries.json")
        
        data = self.s3_service.download_json(s3_key)
        if data is None:
            raise FileNotFoundError(f"Summaries file not found in S3: {s3_key}")
        
        return SummariesFile.model_validate(data)
    
    def _load_summaries_local(self, ticker: str, form: str, year: int, out_base: str) -> SummariesFile:
        """Load summaries from local filesystem."""
        from persist import load_summaries as original_load_summaries
        return original_load_summaries(ticker, form, year, out_base)
    
    def file_exists(self, ticker: str, form: str, year: int, out_base: str = "data/processed") -> bool:
        """Check if summaries file exists."""
        if self.use_s3:
            s3_key = get_s3_path(f"{out_base}/{ticker}/{form}/{year}/summaries.json")
            return self.s3_service.file_exists(s3_key)
        else:
            local_path = Path(out_base) / ticker / form / str(year) / "summaries.json"
            return local_path.exists()
    
    def delete_summaries(self, ticker: str, form: str, year: int, out_base: str = "data/processed") -> bool:
        """Delete summaries file."""
        if self.use_s3:
            s3_key = get_s3_path(f"{out_base}/{ticker}/{form}/{year}/summaries.json")
            return self.s3_service.delete_file(s3_key)
        else:
            local_path = Path(out_base) / ticker / form / str(year) / "summaries.json"
            try:
                local_path.unlink()
                return True
            except OSError:
                return False


# Backward compatibility: create global persist manager
_persist_manager = None

def get_persist_manager(use_s3: bool = None) -> PersistManager:
    """Get singleton persist manager instance."""
    global _persist_manager
    if _persist_manager is None:
        _persist_manager = PersistManager(use_s3)
    return _persist_manager


# Convenience functions for backward compatibility
def write_summaries(
    ticker: str, 
    form: str, 
    year: int, 
    sections: List[Dict[str, Any]], 
    out_base: str = "data/processed"
) -> Union[Path, str]:
    """Write summaries using the global persist manager."""
    result = get_persist_manager().write_summaries(ticker, form, year, sections, out_base)
    # Return Path object for local storage (backward compatibility)
    if not get_persist_manager().use_s3:
        return Path(result)
    return result


def load_summaries(
    ticker: str,
    form: str, 
    year: int,
    out_base: str = "data/processed"
) -> SummariesFile:
    """Load summaries using the global persist manager."""
    return get_persist_manager().load_summaries(ticker, form, year, out_base)


if __name__ == "__main__":
    """Test S3 persist functionality."""
    # Import test dependencies
    import sys
    from pathlib import Path as PathLib
    sys.path.append(str(PathLib(__file__).parent))
    from schema import now_iso
    
    print("=== S3 Persist System Test ===")
    
    # Test data
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
    
    # Test S3 persist
    print("\n--- Testing S3 Persist ---")
    s3_persist = PersistManager(use_s3=True)
    
    print("Testing write_summaries to S3...")
    s3_path = s3_persist.write_summaries("TEST", "10-K", 2023, test_sections, "test_output")
    print(f"✓ Written to S3: {s3_path}")
    
    # Test loading it back
    print("Testing load_summaries from S3...")
    loaded = s3_persist.load_summaries("TEST", "10-K", 2023, "test_output")
    print(f"✓ Loaded {len(loaded.sections)} sections from S3")
    print(f"✓ First section: {loaded.sections[0].section_name}")
    
    # Test non-destructive update
    print("Testing non-destructive update in S3...")
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
    
    s3_path = s3_persist.write_summaries("TEST", "10-K", 2023, additional_sections, "test_output")
    print(f"✓ Updated S3 file: {s3_path}")
    
    # Verify both sections are present
    updated = s3_persist.load_summaries("TEST", "10-K", 2023, "test_output")
    print(f"✓ Now has {len(updated.sections)} sections in S3:")
    for section in updated.sections:
        print(f"  - {section.section_name}: {section.section_alias}")
    
    # Test file existence
    exists = s3_persist.file_exists("TEST", "10-K", 2023, "test_output")
    print(f"✓ File existence check: {exists}")
    
    # Clean up test file
    if s3_persist.delete_summaries("TEST", "10-K", 2023, "test_output"):
        print("✓ S3 cleanup complete")
    
    print("\n✅ S3 persist system test completed")