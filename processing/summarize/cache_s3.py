#!/usr/bin/env python3
"""
S3-Enhanced Cache management for LLM-generated SEC filing summaries.

This module extends the original cache.py with S3 support, allowing seamless
migration from local storage to cloud storage while maintaining backwards compatibility.
"""

try:
    import ujson as json
except ImportError:
    import json
import sys
import os
from pathlib import Path
from typing import Dict, Optional, Union, List, Tuple
from dotenv import load_dotenv

# Load environment variables
load_dotenv('config/.env')

# Import S3 service
try:
    import sys
    sys.path.append('/Users/ahmad/Documents/GitHub/AlphaLoom')
    from services.s3_service import get_s3_service, get_s3_path
    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False

# Import original cache functions for backward compatibility
import sys
from pathlib import Path as PathLib
sys.path.append(str(PathLib(__file__).parent))
from cache import cache_path as local_cache_path


class CacheManager:
    """
    Enhanced cache manager that supports both local and S3 storage.
    """
    
    def __init__(self, use_s3: bool = None):
        """
        Initialize cache manager.
        
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
            print(f"Cache manager initialized with S3 storage (bucket: {self.s3_service.bucket_name})")
        else:
            print("Cache manager initialized with local storage")
    
    def cache_path(self, base_dir: Union[str, Path], ticker: str, form: str, year: int, 
                   section_name: str, section_hash: str, chunk_index: int) -> str:
        """
        Generate cache path (local or S3 key).
        
        Returns local path for local storage, S3 key for S3 storage.
        """
        local_path = local_cache_path(base_dir, ticker, form, year, section_name, section_hash, chunk_index)
        
        if self.use_s3:
            return get_s3_path(str(local_path))
        else:
            return str(local_path)
    
    def read_cache(self, cache_file_path: str) -> Optional[Dict]:
        """
        Read cached LLM result from storage.
        
        Args:
            cache_file_path: Path to cache file (local path or S3 key)
            
        Returns:
            Cached data dictionary, or None if file doesn't exist or can't be read
        """
        if self.use_s3:
            return self._read_cache_s3(cache_file_path)
        else:
            return self._read_cache_local(cache_file_path)
    
    def write_cache(self, cache_file_path: str, data: Dict) -> bool:
        """
        Write LLM result to cache.
        
        Args:
            cache_file_path: Path where cache should be written (local path or S3 key)
            data: Dictionary to cache
            
        Returns:
            True if write succeeded, False otherwise
        """
        if self.use_s3:
            return self._write_cache_s3(cache_file_path, data)
        else:
            return self._write_cache_local(cache_file_path, data)
    
    def _read_cache_s3(self, s3_key: str) -> Optional[Dict]:
        """Read cache from S3."""
        try:
            return self.s3_service.download_json(s3_key)
        except Exception as e:
            print(f"Warning: Cannot read S3 cache {s3_key}: {e}", file=sys.stderr)
            return None
    
    def _write_cache_s3(self, s3_key: str, data: Dict) -> bool:
        """Write cache to S3."""
        try:
            return self.s3_service.upload_json(data, s3_key)
        except Exception as e:
            print(f"Error: Cannot write S3 cache {s3_key}: {e}", file=sys.stderr)
            return False
    
    def _read_cache_local(self, cache_file_path: str) -> Optional[Dict]:
        """Read cache from local filesystem."""
        try:
            cache_path = Path(cache_file_path)
            if not cache_path.exists():
                return None
                
            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
                
        except json.JSONDecodeError as e:
            print(f"Warning: Corrupted cache file {cache_file_path}: {e}", file=sys.stderr)
            return None
        except OSError as e:
            print(f"Warning: Cannot read cache file {cache_file_path}: {e}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"Warning: Unexpected error reading cache {cache_file_path}: {e}", file=sys.stderr)
            return None
    
    def _write_cache_local(self, cache_file_path: str, data: Dict) -> bool:
        """Write cache to local filesystem."""
        try:
            cache_path = Path(cache_file_path)
            
            # Ensure parent directories exist
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write without pretty formatting for faster I/O
            with open(cache_path, 'w', encoding='utf-8') as f:
                if hasattr(json, 'dump'):
                    json.dump(data, f, ensure_ascii=False)
                else:
                    # ujson doesn't have dump, use dumps + write
                    f.write(json.dumps(data, ensure_ascii=False))
            
            return True
            
        except OSError as e:
            print(f"Error: Cannot write cache file {cache_file_path}: {e}", file=sys.stderr)
            return False
        except TypeError as e:
            print(f"Error: Cannot serialize data for cache {cache_file_path}: {e}", file=sys.stderr)
            return False
        except Exception as e:
            print(f"Error: Unexpected error writing cache {cache_file_path}: {e}", file=sys.stderr)
            return False
    
    def batch_write_cache(self, cache_operations: List[Tuple[str, Dict]]) -> Tuple[int, int]:
        """
        Write multiple cache files in batch.
        
        Args:
            cache_operations: List of (cache_path, data) tuples
            
        Returns:
            Tuple of (success_count, failure_count)
        """
        success_count = 0
        failure_count = 0
        
        for cache_path, data in cache_operations:
            if self.write_cache(cache_path, data):
                success_count += 1
            else:
                failure_count += 1
        
        return success_count, failure_count
    
    def batch_read_cache(self, cache_paths: List[str]) -> List[Optional[Dict]]:
        """
        Read multiple cache files in batch.
        
        Args:
            cache_paths: List of cache paths to read
            
        Returns:
            List of cached data dictionaries (None for missing/corrupt files)
        """
        results = []
        for cache_path in cache_paths:
            results.append(self.read_cache(cache_path))
        return results
    
    def cache_exists(self, cache_path: str) -> bool:
        """Check if cache exists."""
        if self.use_s3:
            return self.s3_service.file_exists(cache_path)
        else:
            return Path(cache_path).exists()
    
    def delete_cache(self, cache_path: str) -> bool:
        """Delete cache file."""
        if self.use_s3:
            return self.s3_service.delete_file(cache_path)
        else:
            try:
                Path(cache_path).unlink()
                return True
            except OSError:
                return False
    
    def list_cache_files(self, base_dir: str, ticker: str = None) -> List[str]:
        """
        List cache files matching criteria.
        
        Args:
            base_dir: Base directory/prefix
            ticker: Optional ticker filter
            
        Returns:
            List of cache paths
        """
        if self.use_s3:
            prefix = get_s3_path(f"{base_dir}/summaries")
            if ticker:
                prefix = f"{prefix}/{ticker.upper()}"
            return self.s3_service.list_files(prefix)
        else:
            # Local filesystem listing
            base_path = Path(base_dir) / "summaries"
            if ticker:
                base_path = base_path / ticker.upper()
            
            if not base_path.exists():
                return []
            
            cache_files = []
            for file_path in base_path.rglob("*.json"):
                cache_files.append(str(file_path))
            
            return cache_files


# Backward compatibility: create global cache manager
_cache_manager = None

def get_cache_manager(use_s3: bool = None) -> CacheManager:
    """Get singleton cache manager instance."""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager(use_s3)
    return _cache_manager


# Convenience functions for backward compatibility
def cache_path(base_dir: Union[str, Path], ticker: str, form: str, year: int, 
               section_name: str, section_hash: str, chunk_index: int) -> str:
    """Generate cache path using the global cache manager."""
    return get_cache_manager().cache_path(base_dir, ticker, form, year, section_name, section_hash, chunk_index)


def read_cache(cache_file_path: str) -> Optional[Dict]:
    """Read cache using the global cache manager."""
    return get_cache_manager().read_cache(cache_file_path)


def write_cache(cache_file_path: str, data: Dict) -> bool:
    """Write cache using the global cache manager."""
    return get_cache_manager().write_cache(cache_file_path, data)


if __name__ == "__main__":
    """Test S3 cache functionality."""
    print("=== S3 Cache System Test ===")
    
    # Test with S3
    print("\n--- Testing S3 Cache ---")
    s3_cache = CacheManager(use_s3=True)
    
    # Test cache path generation
    test_path = s3_cache.cache_path(
        "data/cache", 
        "AAPL", 
        "10-K", 
        2023, 
        "Item 7", 
        "abc123def456789", 
        0
    )
    print(f"S3 cache path: {test_path}")
    
    # Test data to cache
    test_data = {
        "ticker": "AAPL",
        "section": "Item 7",
        "chunk_index": 0,
        "summary": {
            "bullets": [
                {
                    "text": "Revenue increased 15% YoY to $394.3B",
                    "span_ids": ["mdna::p005", "mdna::p006"]
                }
            ],
            "key_numbers": [
                {
                    "text": "Net sales: $394.3 billion",
                    "span_ids": ["mdna::p010"]
                }
            ],
            "uncertainties": []
        },
        "generated_at": "2024-01-15T10:30:45Z",
        "model": "gpt-4",
        "tokens_used": 1250
    }
    
    # Test S3 cache write/read
    print("Testing S3 cache write...")
    if s3_cache.write_cache(test_path, test_data):
        print("✓ S3 cache write successful")
        
        print("Testing S3 cache read...")
        cached_data = s3_cache.read_cache(test_path)
        if cached_data and cached_data == test_data:
            print("✓ S3 cache read and verification successful")
            
            # Test existence check
            if s3_cache.cache_exists(test_path):
                print("✓ S3 cache existence check successful")
            
            # Clean up
            if s3_cache.delete_cache(test_path):
                print("✓ S3 cache cleanup successful")
        else:
            print("✗ S3 cache read failed")
    else:
        print("✗ S3 cache write failed")
    
    # Test with local storage for comparison
    print("\n--- Testing Local Cache ---")
    local_cache = CacheManager(use_s3=False)
    
    test_local_path = local_cache.cache_path(
        "data/cache", 
        "AAPL", 
        "10-K", 
        2023, 
        "Item 7", 
        "abc123def456789", 
        0
    )
    print(f"Local cache path: {test_local_path}")
    
    if local_cache.write_cache(test_local_path, test_data):
        print("✓ Local cache write successful")
        
        cached_data = local_cache.read_cache(test_local_path)
        if cached_data and cached_data == test_data:
            print("✓ Local cache read successful")
            
            # Clean up
            if local_cache.delete_cache(test_local_path):
                print("✓ Local cache cleanup successful")
    
    print("\n✅ S3 cache system test completed")