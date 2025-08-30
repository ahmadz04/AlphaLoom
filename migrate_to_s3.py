#!/usr/bin/env python3
"""
AlphaLoom S3 Migration Utility

This script helps you:
1. Test your S3 connection
2. Migrate existing local data to S3
3. Switch between local and S3 storage
4. Verify data integrity after migration
"""

import os
import sys
import json
from pathlib import Path
from typing import List, Dict, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv('config/.env')

# Import our S3 services
from services.s3_service import get_s3_service, get_s3_path
from processing.summarize.cache_s3 import CacheManager
from processing.summarize.persist_s3 import PersistManager


class S3Migrator:
    """Utility class for migrating AlphaLoom data to S3."""
    
    def __init__(self):
        """Initialize the migrator."""
        self.s3_service = get_s3_service()
        self.cache_manager = CacheManager(use_s3=True)
        self.persist_manager = PersistManager(use_s3=True)
        
        print(f"🚀 S3 Migrator initialized")
        print(f"   Bucket: {self.s3_service.bucket_name}")
        print(f"   Region: {self.s3_service.region}")
    
    def test_connection(self) -> bool:
        """Test S3 connection and permissions."""
        print("\n🔍 Testing S3 connection...")
        
        try:
            # Test basic connectivity
            test_key = "test/connection_test.json"
            test_data = {"test": "connection", "timestamp": "2024-01-15T10:30:00Z"}
            
            # Test upload
            if not self.s3_service.upload_json(test_data, test_key):
                print("❌ Failed to upload test file")
                return False
            
            print("✅ Upload test passed")
            
            # Test download
            downloaded = self.s3_service.download_json(test_key)
            if not downloaded or downloaded != test_data:
                print("❌ Failed to download or verify test file")
                return False
            
            print("✅ Download test passed")
            
            # Test delete
            if not self.s3_service.delete_file(test_key):
                print("❌ Failed to delete test file")
                return False
            
            print("✅ Delete test passed")
            print("✅ S3 connection is working perfectly!")
            return True
            
        except Exception as e:
            print(f"❌ S3 connection test failed: {e}")
            return False
    
    def scan_local_data(self) -> Dict[str, List[str]]:
        """Scan local data directory and categorize files."""
        print("\n📂 Scanning local data directory...")
        
        data_dir = Path("data")
        if not data_dir.exists():
            print("❌ No data directory found")
            return {}
        
        categories = {
            "raw_filings": [],
            "processed_summaries": [],
            "cache_files": [],
            "other_files": []
        }
        
        # Scan for different types of files
        for file_path in data_dir.rglob("*"):
            if file_path.is_file():
                relative_path = str(file_path.relative_to(data_dir))
                
                if "raw/filings" in relative_path:
                    categories["raw_filings"].append(str(file_path))
                elif "processed" in relative_path and "summaries.json" in file_path.name:
                    categories["processed_summaries"].append(str(file_path))
                elif "cache/summaries" in relative_path:
                    categories["cache_files"].append(str(file_path))
                else:
                    categories["other_files"].append(str(file_path))
        
        # Print summary
        print(f"   📄 Raw filings: {len(categories['raw_filings'])}")
        print(f"   📊 Processed summaries: {len(categories['processed_summaries'])}")
        print(f"   💾 Cache files: {len(categories['cache_files'])}")
        print(f"   📁 Other files: {len(categories['other_files'])}")
        
        return categories
    
    def migrate_files(self, file_paths: List[str], file_type: str) -> Dict[str, int]:
        """Migrate a list of files to S3."""
        print(f"\n📤 Migrating {len(file_paths)} {file_type} files to S3...")
        
        results = {"success": 0, "failed": 0}
        
        for file_path in file_paths:
            try:
                local_path = Path(file_path)
                
                # Generate S3 key
                s3_key = get_s3_path(str(local_path))
                
                # Check if file already exists in S3
                if self.s3_service.file_exists(s3_key):
                    print(f"   ⏩ Skipping {local_path.name} (already exists in S3)")
                    results["success"] += 1
                    continue
                
                # Upload file
                if local_path.suffix == '.json':
                    # Upload JSON files with proper content type
                    with open(local_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    if self.s3_service.upload_json(data, s3_key):
                        print(f"   ✅ Migrated {local_path.name}")
                        results["success"] += 1
                    else:
                        print(f"   ❌ Failed to migrate {local_path.name}")
                        results["failed"] += 1
                else:
                    # Upload other file types
                    if self.s3_service.upload_file(local_path, s3_key):
                        print(f"   ✅ Migrated {local_path.name}")
                        results["success"] += 1
                    else:
                        print(f"   ❌ Failed to migrate {local_path.name}")
                        results["failed"] += 1
                        
            except Exception as e:
                print(f"   ❌ Error migrating {file_path}: {e}")
                results["failed"] += 1
        
        return results
    
    def verify_migration(self, local_files: List[str]) -> Dict[str, int]:
        """Verify that migrated files match local versions."""
        print(f"\n🔍 Verifying migration of {len(local_files)} files...")
        
        results = {"verified": 0, "missing": 0, "different": 0}
        
        for file_path in local_files:
            try:
                local_path = Path(file_path)
                s3_key = get_s3_path(str(local_path))
                
                # Check if file exists in S3
                if not self.s3_service.file_exists(s3_key):
                    print(f"   ❌ Missing in S3: {local_path.name}")
                    results["missing"] += 1
                    continue
                
                # For JSON files, compare content
                if local_path.suffix == '.json':
                    with open(local_path, 'r', encoding='utf-8') as f:
                        local_data = json.load(f)
                    
                    s3_data = self.s3_service.download_json(s3_key)
                    
                    if s3_data == local_data:
                        results["verified"] += 1
                    else:
                        print(f"   ❌ Content differs: {local_path.name}")
                        results["different"] += 1
                else:
                    # For other files, just check existence
                    results["verified"] += 1
                    
            except Exception as e:
                print(f"   ❌ Error verifying {file_path}: {e}")
                results["different"] += 1
        
        return results
    
    def update_config(self, use_s3: bool):
        """Update .env file to use S3 or local storage."""
        env_file = Path('config/.env')
        
        if not env_file.exists():
            print("❌ .env file not found")
            return False
        
        # Read current content
        with open(env_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Update USE_S3_STORAGE setting
        if "USE_S3_STORAGE=" in content:
            # Replace existing setting
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if line.startswith('USE_S3_STORAGE='):
                    lines[i] = f'USE_S3_STORAGE={"true" if use_s3 else "false"}'
                    break
            content = '\n'.join(lines)
        else:
            # Add new setting
            content += f'\n\n# Storage Configuration\n# Set to "true" to use S3, "false" to use local storage\nUSE_S3_STORAGE={"true" if use_s3 else "false"}\n'
        
        # Write back
        with open(env_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        storage_type = "S3" if use_s3 else "local"
        print(f"✅ Updated configuration to use {storage_type} storage")
        return True


def main():
    """Main migration workflow."""
    print("🔄 AlphaLoom S3 Migration Utility")
    print("=" * 50)
    
    try:
        migrator = S3Migrator()
        
        # Test connection first
        if not migrator.test_connection():
            print("\n❌ S3 connection failed. Please check your configuration.")
            sys.exit(1)
        
        # Scan local data
        local_data = migrator.scan_local_data()
        total_files = sum(len(files) for files in local_data.values())
        
        if total_files == 0:
            print("\n✅ No local data found to migrate")
        else:
            print(f"\n📋 Found {total_files} files to potentially migrate")
            
            # Ask user what to migrate
            print("\nWhat would you like to migrate?")
            print("1. Everything (recommended)")
            print("2. Just processed summaries")
            print("3. Just cache files")
            print("4. Custom selection")
            print("5. Skip migration, just switch to S3")
            
            choice = input("\nEnter your choice (1-5): ").strip()
            
            files_to_migrate = []
            
            if choice == "1":
                # Migrate everything
                for file_list in local_data.values():
                    files_to_migrate.extend(file_list)
            elif choice == "2":
                files_to_migrate = local_data["processed_summaries"]
            elif choice == "3":
                files_to_migrate = local_data["cache_files"]
            elif choice == "4":
                # Custom selection (simplified for now)
                print("Custom selection not implemented yet. Migrating processed summaries...")
                files_to_migrate = local_data["processed_summaries"]
            elif choice == "5":
                print("Skipping migration...")
            else:
                print("Invalid choice. Defaulting to processed summaries...")
                files_to_migrate = local_data["processed_summaries"]
            
            if files_to_migrate:
                # Perform migration
                print(f"\n🚀 Starting migration of {len(files_to_migrate)} files...")
                results = migrator.migrate_files(files_to_migrate, "selected")
                
                print(f"\n📊 Migration Results:")
                print(f"   ✅ Success: {results['success']}")
                print(f"   ❌ Failed: {results['failed']}")
                
                if results['success'] > 0:
                    # Verify migration
                    verify_results = migrator.verify_migration(files_to_migrate)
                    print(f"\n🔍 Verification Results:")
                    print(f"   ✅ Verified: {verify_results['verified']}")
                    print(f"   ❌ Missing: {verify_results['missing']}")
                    print(f"   ❌ Different: {verify_results['different']}")
        
        # Ask about switching to S3
        print("\n" + "=" * 50)
        switch = input("Switch AlphaLoom to use S3 storage? (y/n): ").strip().lower()
        
        if switch in ['y', 'yes']:
            migrator.update_config(use_s3=True)
            print("\n✅ AlphaLoom is now configured to use S3 storage!")
            print("💡 Tip: You can switch back to local storage anytime by setting USE_S3_STORAGE=false in config/.env")
        else:
            print("\n📝 Configuration unchanged. AlphaLoom will continue using local storage.")
            print("💡 Tip: You can switch to S3 anytime by setting USE_S3_STORAGE=true in config/.env")
        
        print("\n🎉 Migration utility completed successfully!")
        
    except KeyboardInterrupt:
        print("\n\n⚠️ Migration interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Migration failed with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()