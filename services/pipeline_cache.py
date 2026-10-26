#!/usr/bin/env python3
"""
Intelligent Pipeline Cache Manager

This service provides comprehensive caching logic for the AlphaLoom ingestion pipeline.
It checks for existing data at all stages (raw filings, processed summaries, cache chunks)
to avoid redundant API calls and processing.
"""

import os
from typing import Optional, Dict, List, Tuple, Any
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv('config/.env')

# Import our services
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))
from services.s3_service import get_s3_service, get_s3_path
from processing.summarize.cache_s3 import CacheManager
from processing.summarize.persist_s3 import PersistManager


class PipelineCacheManager:
    """
    Manages caching at all stages of the AlphaLoom pipeline.
    
    Pipeline stages:
    1. Raw Filing (from financialdataset.ai API)
    2. Processed Sections (parsed SEC items)
    3. LLM Summaries (per-section summaries)
    4. Cache Chunks (LLM chunk-level cache)
    """
    
    def __init__(self):
        """Initialize the pipeline cache manager."""
        self.use_s3 = os.getenv('USE_S3_STORAGE', 'false').lower() == 'true'
        
        if self.use_s3:
            self.s3_service = get_s3_service()
        
        self.cache_manager = CacheManager()
        self.persist_manager = PersistManager()
        
        print(f"🧠 Pipeline Cache Manager initialized ({'S3' if self.use_s3 else 'Local'} storage)")
    
    def check_raw_filing_exists(self, ticker: str, filing_type: str, year: int, 
                               filed_date: Optional[str] = None) -> bool:
        """
        Check if raw filing already exists in storage.
        
        Args:
            ticker: Stock ticker (e.g., "AAPL")
            filing_type: SEC form type (e.g., "10-K")
            year: Filing year
            filed_date: Optional filed date
            
        Returns:
            True if raw filing exists, False otherwise
        """
        from ingestion.utils.paths import filing_path, find_filing_path
        from ingestion.storage.hybrid import HybridStorage

        if filed_date is None:
            # Name depends on the filed date we don't know yet - look it up by prefix
            local_path = find_filing_path(HybridStorage(), ticker, filing_type, year, "json")
            if local_path is None:
                return False
        else:
            local_path = filing_path(ticker, filing_type, year, filed_date, "json")

        if self.use_s3:
            s3_key = get_s3_path(local_path)
            exists = self.s3_service.file_exists(s3_key)
            if exists:
                print(f"   📁 Found raw filing in S3: {s3_key}")
            return exists
        else:
            exists = Path(local_path).exists()
            if exists:
                print(f"   📁 Found raw filing locally: {local_path}")
            return exists
    
    def check_processed_summaries_exist(self, ticker: str, filing_type: str, year: int) -> bool:
        """
        Check if processed summaries already exist.
        
        Args:
            ticker: Stock ticker
            filing_type: SEC form type
            year: Filing year
            
        Returns:
            True if summaries exist, False otherwise
        """
        exists = self.persist_manager.file_exists(ticker, filing_type, year)
        if exists:
            storage_type = "S3" if self.use_s3 else "local"
            print(f"   📊 Found processed summaries in {storage_type}: {ticker} {filing_type} {year}")
        return exists
    
    def get_cached_summaries(self, ticker: str, filing_type: str, year: int):
        """
        Retrieve cached summaries if they exist.
        
        Args:
            ticker: Stock ticker
            filing_type: SEC form type
            year: Filing year
            
        Returns:
            SummariesFile object if found, None otherwise
        """
        if self.check_processed_summaries_exist(ticker, filing_type, year):
            try:
                return self.persist_manager.load_summaries(ticker, filing_type, year)
            except Exception as e:
                print(f"   ⚠️ Error loading cached summaries: {e}")
                return None
        return None
    
    def check_section_cache_exists(self, ticker: str, filing_type: str, year: int, 
                                  section_name: str, section_hash: str) -> Tuple[bool, List[Dict]]:
        """
        Check if LLM cache exists for a specific section.
        
        Args:
            ticker: Stock ticker
            filing_type: SEC form type  
            year: Filing year
            section_name: Section name (e.g., "Item 7")
            section_hash: Hash of section content
            
        Returns:
            Tuple of (cache_exists, cached_chunks_list)
        """
        cached_chunks = []
        chunk_index = 0
        
        # Check for cached chunks until we find a gap
        while True:
            cache_path = self.cache_manager.cache_path(
                "data/cache", ticker, filing_type, year, section_name, section_hash, chunk_index
            )
            
            cached_data = self.cache_manager.read_cache(cache_path)
            
            if cached_data is None:
                # No more cached chunks
                break
            
            cached_chunks.append(cached_data)
            chunk_index += 1
        
        if cached_chunks:
            storage_type = "S3" if self.use_s3 else "local"
            print(f"   💾 Found {len(cached_chunks)} cached chunks in {storage_type} for {section_name}")
        
        return len(cached_chunks) > 0, cached_chunks
    
    def get_processing_status(self, ticker: str, filing_type: str, year: int) -> Dict[str, Any]:
        """
        Get comprehensive processing status for a filing.
        
        Args:
            ticker: Stock ticker
            filing_type: SEC form type
            year: Filing year
            
        Returns:
            Dictionary with processing status information
        """
        status = {
            "ticker": ticker,
            "filing_type": filing_type,
            "year": year,
            "raw_filing_exists": False,
            "processed_summaries_exist": False,
            "summaries_data": None,
            "can_skip_ingestion": False,
            "can_skip_processing": False,
            "sections_with_cache": [],
            "storage_type": "S3" if self.use_s3 else "Local"
        }
        
        print(f"\n🔍 Checking processing status for {ticker} {filing_type} {year}...")
        
        # Check raw filing
        status["raw_filing_exists"] = self.check_raw_filing_exists(ticker, filing_type, year)
        
        # Check processed summaries
        status["processed_summaries_exist"] = self.check_processed_summaries_exist(ticker, filing_type, year)
        
        if status["processed_summaries_exist"]:
            status["summaries_data"] = self.get_cached_summaries(ticker, filing_type, year)
            status["can_skip_processing"] = True
            
            # If we have summaries, we can also skip ingestion
            status["can_skip_ingestion"] = True
        
        return status
    
    def should_skip_ingestion(self, ticker: str, filing_type: str, year: int) -> bool:
        """
        Determine if ingestion can be skipped for this filing.
        
        Returns True if we already have processed data or raw filing.
        """
        status = self.get_processing_status(ticker, filing_type, year)
        
        if status["can_skip_ingestion"]:
            print(f"   ✅ Can skip ingestion - data already processed")
            return True
        elif status["raw_filing_exists"]:
            print(f"   ✅ Can skip API fetch - raw filing exists")
            return True
        else:
            print(f"   📥 Need to fetch from API - no existing data")
            return False
    
    def should_skip_processing(self, ticker: str, filing_type: str, year: int) -> bool:
        """
        Determine if processing can be skipped for this filing.
        
        Returns True if we already have processed summaries.
        """
        status = self.get_processing_status(ticker, filing_type, year)
        
        if status["can_skip_processing"]:
            print(f"   ✅ Can skip processing - summaries already exist")
            return True
        else:
            print(f"   ⚙️ Need to process - no existing summaries")
            return False
    
    def get_cached_data_summary(self, ticker: str, filing_type: str, year: int) -> Optional[Dict]:
        """
        Get a summary of all cached data for a filing.
        
        Returns:
            Dictionary with cached data summary or None if no cache
        """
        summaries = self.get_cached_summaries(ticker, filing_type, year)
        
        if summaries is None:
            return None
        
        summary = {
            "ticker": summaries.ticker,
            "form": summaries.form, 
            "year": summaries.year,
            "sections_count": len(summaries.sections),
            "sections": [],
            "total_bullets": 0,
            "total_key_numbers": 0,
            "total_uncertainties": 0
        }
        
        for section in summaries.sections:
            section_info = {
                "name": section.section_name,
                "alias": section.section_alias,
                "bullets": len(section.bullets),
                "key_numbers": len(section.key_numbers),
                "uncertainties": len(section.uncertainties),
                "created_at": section.created_at
            }
            
            summary["sections"].append(section_info)
            summary["total_bullets"] += section_info["bullets"]
            summary["total_key_numbers"] += section_info["key_numbers"]
            summary["total_uncertainties"] += section_info["uncertainties"]
        
        return summary
    
    def invalidate_cache(self, ticker: str, filing_type: str, year: int) -> bool:
        """
        Invalidate/delete all cached data for a filing.
        
        This forces fresh processing on the next run.
        
        Args:
            ticker: Stock ticker
            filing_type: SEC form type
            year: Filing year
            
        Returns:
            True if cache was invalidated successfully
        """
        print(f"🗑️ Invalidating cache for {ticker} {filing_type} {year}...")
        
        try:
            # Delete processed summaries
            if self.persist_manager.delete_summaries(ticker, filing_type, year):
                print(f"   ✅ Deleted processed summaries")
            
            # Delete cache files (this is more complex - would need to scan and delete)
            # For now, we'll just report what we did
            print(f"   ⚠️ Cache chunk cleanup not implemented yet")
            
            return True
            
        except Exception as e:
            print(f"   ❌ Error invalidating cache: {e}")
            return False


# Global pipeline cache manager instance
_pipeline_cache = None

def get_pipeline_cache() -> PipelineCacheManager:
    """Get singleton pipeline cache manager."""
    global _pipeline_cache
    if _pipeline_cache is None:
        _pipeline_cache = PipelineCacheManager()
    return _pipeline_cache


if __name__ == "__main__":
    """Test the pipeline cache manager."""
    print("🧪 Testing Pipeline Cache Manager")
    print("=" * 50)
    
    cache_mgr = PipelineCacheManager()
    
    # Test with your existing data
    test_cases = [
        ("AAPL", "10-K", 2023),
        ("TSLA", "10-K", 2023),
        ("MSFT", "10-K", 2023)  # This shouldn't exist
    ]
    
    for ticker, filing_type, year in test_cases:
        print(f"\n📋 Testing {ticker} {filing_type} {year}:")
        
        status = cache_mgr.get_processing_status(ticker, filing_type, year)
        
        print(f"   📁 Raw filing exists: {status['raw_filing_exists']}")
        print(f"   📊 Summaries exist: {status['processed_summaries_exist']}")
        print(f"   ⚙️ Can skip ingestion: {status['can_skip_ingestion']}")
        print(f"   ⚙️ Can skip processing: {status['can_skip_processing']}")
        
        if status["summaries_data"]:
            summary = cache_mgr.get_cached_data_summary(ticker, filing_type, year)
            if summary:
                print(f"   📊 Sections: {summary['sections_count']}")
                print(f"   📊 Total bullets: {summary['total_bullets']}")
                print(f"   📊 Total key numbers: {summary['total_key_numbers']}")
    
    print("\n✅ Pipeline cache manager test completed!")