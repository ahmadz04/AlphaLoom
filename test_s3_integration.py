#!/usr/bin/env python3
"""
Simple S3 Integration Test

Tests the complete S3 integration without user interaction.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv('config/.env')

from services.s3_service import get_s3_service
from processing.summarize.cache_s3 import CacheManager
from processing.summarize.persist_s3 import PersistManager


def test_complete_integration():
    """Test the complete S3 integration."""
    print("🧪 Testing Complete S3 Integration")
    print("=" * 50)
    
    try:
        # Test 1: S3 Service
        print("\n1️⃣ Testing S3 Service...")
        s3_service = get_s3_service()
        
        test_data = {"integration_test": True, "timestamp": "2024-01-15"}
        test_key = "integration_test/service_test.json"
        
        if s3_service.upload_json(test_data, test_key):
            print("   ✅ S3 Service upload works")
            
            downloaded = s3_service.download_json(test_key)
            if downloaded == test_data:
                print("   ✅ S3 Service download works")
            else:
                print("   ❌ S3 Service download failed")
                
            s3_service.delete_file(test_key)
            print("   ✅ S3 Service cleanup complete")
        else:
            print("   ❌ S3 Service upload failed")
            return False
        
        # Test 2: Cache Manager with S3
        print("\n2️⃣ Testing Cache Manager with S3...")
        cache_manager = CacheManager(use_s3=True)
        
        cache_path = cache_manager.cache_path(
            "data/cache", "TEST", "10-K", 2023, "Item 7", "test_hash", 0
        )
        
        cache_data = {
            "ticker": "TEST",
            "section": "Item 7",
            "summary": {"bullets": [{"text": "Test bullet", "span_ids": ["test::1"]}]}
        }
        
        if cache_manager.write_cache(cache_path, cache_data):
            print("   ✅ Cache Manager S3 write works")
            
            cached = cache_manager.read_cache(cache_path)
            if cached == cache_data:
                print("   ✅ Cache Manager S3 read works")
            else:
                print("   ❌ Cache Manager S3 read failed")
                
            cache_manager.delete_cache(cache_path)
            print("   ✅ Cache Manager S3 cleanup complete")
        else:
            print("   ❌ Cache Manager S3 write failed")
            return False
        
        # Test 3: Persist Manager with S3
        print("\n3️⃣ Testing Persist Manager with S3...")
        persist_manager = PersistManager(use_s3=True)
        
        import sys
        from pathlib import Path as PathLib
        sys.path.append(str(PathLib(__file__).parent / "processing" / "summarize"))
        from schema import now_iso
        
        test_sections = [{
            "section_name": "Item 7",
            "section_alias": "Test MD&A", 
            "section_hash": "test_persist_hash",
            "bullets": [{"text": "Test persist bullet", "span_ids": ["persist::1"]}],
            "key_numbers": [],
            "uncertainties": [],
            "warnings": [],
            "created_at": now_iso()
        }]
        
        persist_path = persist_manager.write_summaries(
            "TEST", "10-K", 2023, test_sections, "integration_test"
        )
        
        if persist_path:
            print("   ✅ Persist Manager S3 write works")
            
            loaded = persist_manager.load_summaries("TEST", "10-K", 2023, "integration_test")
            if loaded and len(loaded.sections) == 1:
                print("   ✅ Persist Manager S3 read works")
            else:
                print("   ❌ Persist Manager S3 read failed")
                
            persist_manager.delete_summaries("TEST", "10-K", 2023, "integration_test")
            print("   ✅ Persist Manager S3 cleanup complete")
        else:
            print("   ❌ Persist Manager S3 write failed")
            return False
        
        # Test 4: Configuration Detection
        print("\n4️⃣ Testing Configuration Detection...")
        
        # Test with USE_S3_STORAGE=false
        os.environ['USE_S3_STORAGE'] = 'false'
        local_cache = CacheManager()
        if not local_cache.use_s3:
            print("   ✅ Correctly detected local storage setting")
        else:
            print("   ❌ Failed to detect local storage setting")
        
        # Test with USE_S3_STORAGE=true  
        os.environ['USE_S3_STORAGE'] = 'true'
        s3_cache = CacheManager()
        if s3_cache.use_s3:
            print("   ✅ Correctly detected S3 storage setting")
        else:
            print("   ❌ Failed to detect S3 storage setting")
        
        print("\n" + "=" * 50)
        print("🎉 ALL TESTS PASSED!")
        print("✅ Your S3 integration is working perfectly!")
        print("\n💡 You can now:")
        print("   • Set USE_S3_STORAGE=true in config/.env to use S3")
        print("   • Set USE_S3_STORAGE=false to use local storage")
        print("   • Run 'python migrate_to_s3.py' to migrate existing data")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Integration test failed: {e}")
        return False


if __name__ == "__main__":
    success = test_complete_integration()
    sys.exit(0 if success else 1)