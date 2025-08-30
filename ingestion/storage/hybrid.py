#!/usr/bin/env python3
"""
Hybrid Storage - Unified storage interface for both local and S3 storage
"""

import json
import os
import tempfile
from typing import Any
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv('config/.env')

try:
    import sys
    sys.path.append(str(Path(__file__).parent.parent.parent))
    from services.s3_service import get_s3_service, get_s3_path
    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False

from .local import LocalStorage


class HybridStorage:
    """
    Hybrid storage that automatically uses S3 or local storage based on USE_S3_STORAGE setting.
    """
    
    def __init__(self):
        """Initialize hybrid storage."""
        self.use_s3 = os.getenv('USE_S3_STORAGE', 'false').lower() == 'true'
        
        if self.use_s3 and not S3_AVAILABLE:
            print("Warning: S3 requested but not available, falling back to local storage")
            self.use_s3 = False
        
        if self.use_s3:
            self.s3_service = get_s3_service()
            print(f"Using S3 storage (bucket: {self.s3_service.bucket_name})")
        else:
            self.local_storage = LocalStorage()
            print("Using local storage")
    
    def write_json(self, obj: Any, path_str: str) -> None:
        """Write JSON to storage."""
        if self.use_s3:
            s3_key = get_s3_path(path_str)
            success = self.s3_service.upload_json(obj, s3_key)
            if not success:
                raise Exception(f"Failed to write to S3: {s3_key}")
        else:
            self.local_storage.write_json(obj, path_str)
    
    def read_json(self, path_str: str):
        """Read JSON from storage."""
        if self.use_s3:
            s3_key = get_s3_path(path_str)
            data = self.s3_service.download_json(s3_key)
            if data is None:
                raise FileNotFoundError(f"File not found in S3: {s3_key}")
            return data
        else:
            return self.local_storage.read_json(path_str)
    
    def exists(self, path_str: str) -> bool:
        """Check if file exists in storage."""
        if self.use_s3:
            s3_key = get_s3_path(path_str)
            return self.s3_service.file_exists(s3_key)
        else:
            return self.local_storage.exists(path_str)
    
    def mkdirs_for(self, path_str: str) -> None:
        """Create directories (only needed for local storage)."""
        if not self.use_s3:
            self.local_storage.mkdirs_for(path_str)
    
    def write_file(self, content: str, path_str: str) -> None:
        """Write text file to storage."""
        if self.use_s3:
            import tempfile
            import os
            
            # Write to temp file first, then upload
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False) as f:
                f.write(content)
                temp_path = f.name
            
            try:
                s3_key = get_s3_path(path_str)
                success = self.s3_service.upload_file(temp_path, s3_key)
                if not success:
                    raise Exception(f"Failed to upload file to S3: {s3_key}")
            finally:
                os.unlink(temp_path)
        else:
            # Write directly to local file
            self.mkdirs_for(path_str)
            with open(path_str, 'w', encoding='utf-8') as f:
                f.write(content)
    
    def get_storage_type(self) -> str:
        """Get current storage type."""
        return "S3" if self.use_s3 else "Local"