#!/usr/bin/env python3
"""
Cache management for LLM-generated SEC filing summaries.

This module provides utilities to save and retrieve per-chunk LLM outputs
to/from disk using cache keys based on ticker, form, year, section details,
and chunk index. This prevents redundant expensive LLM API calls when
section content hasn't changed (stable section_hash).
"""

import json
import sys
from pathlib import Path
from typing import Dict, Optional, Union


def cache_path(
    base_dir: Union[str, Path], 
    ticker: str, 
    form: str, 
    year: int, 
    section_name: str, 
    section_hash: str, 
    chunk_index: int
) -> Path:
    """
    Generate cache file path for LLM chunk summary.
    
    The cache structure allows for efficient lookups and invalidation:
    - Organized by ticker/form/year for easy bulk operations
    - section_name allows filtering by section type
    - section_hash enables cache invalidation when content changes
    - chunk_index handles multiple chunks per section
    
    Args:
        base_dir: Base directory for cache storage
        ticker: Stock ticker symbol (e.g., "AAPL")
        form: SEC form type (e.g., "10-K", "10-Q")
        year: Filing year
        section_name: SEC section name (e.g., "Item 7", "Item 1A")
        section_hash: Hash of section content for change detection
        chunk_index: Index of chunk within section (0-based)
    
    Returns:
        Path to cache file
        
    Example:
        cache_path("data/cache", "AAPL", "10-K", 2023, "Item 7", "abc123", 0)
        → data/cache/summaries/AAPL/10-K/2023/Item 7/abc123/0.json
    """
    base_dir = Path(base_dir)
    
    # Sanitize section_name for filesystem (replace problematic characters)
    safe_section_name = section_name.replace("/", "_").replace("\\", "_").replace(":", "_")
    
    # Build hierarchical path
    cache_file_path = (
        base_dir 
        / "summaries" 
        / ticker.upper() 
        / form.upper() 
        / str(year) 
        / safe_section_name 
        / section_hash[:16]  # Use first 16 chars of hash to avoid very long paths
        / f"{chunk_index}.json"
    )
    
    return cache_file_path


def read_cache(cache_file_path: Path) -> Optional[Dict]:
    """
    Read cached LLM result from disk.
    
    Args:
        cache_file_path: Path to cache file
        
    Returns:
        Cached data dictionary, or None if file doesn't exist or can't be read
    """
    try:
        if not cache_file_path.exists():
            return None
            
        with open(cache_file_path, 'r', encoding='utf-8') as f:
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


def write_cache(cache_file_path: Path, data: Dict) -> bool:
    """
    Write LLM result to cache file.
    
    Args:
        cache_file_path: Path where cache file should be written
        data: Dictionary to cache (will be JSON serialized)
        
    Returns:
        True if write succeeded, False otherwise
    """
    try:
        # Ensure parent directories exist
        cache_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write with pretty formatting for debugging
        with open(cache_file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)
        
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


def cache_stats(base_dir: Union[str, Path], ticker: str = None) -> Dict:
    """
    Get cache statistics for analysis and cleanup.
    
    Args:
        base_dir: Base cache directory
        ticker: Optional ticker to filter stats (None for all tickers)
        
    Returns:
        Dictionary with cache statistics
    """
    base_dir = Path(base_dir)
    cache_root = base_dir / "summaries"
    
    if not cache_root.exists():
        return {
            "total_files": 0,
            "total_size_bytes": 0,
            "tickers": [],
            "by_ticker": {}
        }
    
    stats = {
        "total_files": 0,
        "total_size_bytes": 0,
        "tickers": [],
        "by_ticker": {}
    }
    
    # Walk cache directory structure
    search_pattern = f"*/{ticker}/*" if ticker else "*/*/*"
    
    for cache_file in cache_root.glob(f"{search_pattern}/**/*.json"):
        if cache_file.is_file():
            # Parse path components
            path_parts = cache_file.parts
            summaries_idx = path_parts.index("summaries")
            
            if len(path_parts) > summaries_idx + 1:
                file_ticker = path_parts[summaries_idx + 1]
                
                # Update stats
                stats["total_files"] += 1
                file_size = cache_file.stat().st_size
                stats["total_size_bytes"] += file_size
                
                if file_ticker not in stats["by_ticker"]:
                    stats["by_ticker"][file_ticker] = {
                        "files": 0,
                        "size_bytes": 0
                    }
                    stats["tickers"].append(file_ticker)
                
                stats["by_ticker"][file_ticker]["files"] += 1
                stats["by_ticker"][file_ticker]["size_bytes"] += file_size
    
    # Sort tickers for consistent output
    stats["tickers"].sort()
    
    return stats


def clear_cache(
    base_dir: Union[str, Path], 
    ticker: str = None, 
    form: str = None, 
    year: int = None,
    section_name: str = None
) -> int:
    """
    Clear cache files matching the specified criteria.
    
    Args:
        base_dir: Base cache directory
        ticker: Optional ticker filter
        form: Optional form filter  
        year: Optional year filter
        section_name: Optional section name filter
        
    Returns:
        Number of files deleted
    """
    base_dir = Path(base_dir)
    cache_root = base_dir / "summaries"
    
    if not cache_root.exists():
        return 0
    
    # Build search pattern based on filters
    pattern_parts = []
    
    if ticker:
        pattern_parts.append(ticker.upper())
    else:
        pattern_parts.append("*")
        
    if form:
        pattern_parts.append(form.upper())
    else:
        pattern_parts.append("*")
        
    if year:
        pattern_parts.append(str(year))
    else:
        pattern_parts.append("*")
    
    if section_name:
        safe_section_name = section_name.replace("/", "_").replace("\\", "_").replace(":", "_")
        pattern_parts.append(safe_section_name)
    else:
        pattern_parts.append("*")
    
    # Add wildcards for hash and chunk files
    pattern_parts.extend(["*", "*.json"])
    
    search_pattern = "/".join(pattern_parts)
    files_deleted = 0
    
    for cache_file in cache_root.glob(search_pattern):
        if cache_file.is_file():
            try:
                cache_file.unlink()
                files_deleted += 1
            except OSError as e:
                print(f"Warning: Cannot delete cache file {cache_file}: {e}", file=sys.stderr)
    
    return files_deleted


def main():
    """
    Test cache functionality with sample data.
    """
    print("=== Cache System Test ===")
    
    # Test cache path generation
    test_path = cache_path(
        "data/cache", 
        "AAPL", 
        "10-K", 
        2023, 
        "Item 7", 
        "abc123def456789", 
        0
    )
    print(f"Sample cache path: {test_path}")
    
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
    
    # Test write cache
    print("\n=== Testing Cache Write ===")
    success = write_cache(test_path, test_data)
    print(f"Write success: {success}")
    
    if success:
        print(f"Cache file created: {test_path}")
        print(f"File size: {test_path.stat().st_size} bytes")
    
    # Test read cache
    print("\n=== Testing Cache Read ===")
    cached_data = read_cache(test_path)
    
    if cached_data:
        print("Cache read successful!")
        print(f"Cached ticker: {cached_data.get('ticker')}")
        print(f"Bullets count: {len(cached_data.get('summary', {}).get('bullets', []))}")
        print(f"Generated at: {cached_data.get('generated_at')}")
    else:
        print("Cache read failed")
    
    # Test cache stats
    print("\n=== Cache Statistics ===")
    stats = cache_stats("data/cache", "AAPL")
    print(f"Total files: {stats['total_files']}")
    print(f"Total size: {stats['total_size_bytes']} bytes")
    print(f"Tickers: {stats['tickers']}")
    
    # Test cache clearing
    print("\n=== Testing Cache Clear ===")
    deleted_count = clear_cache("data/cache", "AAPL", "10-K", 2023)
    print(f"Files deleted: {deleted_count}")
    
    # Verify cache is cleared
    cached_data_after = read_cache(test_path)
    print(f"Cache exists after clear: {cached_data_after is not None}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())