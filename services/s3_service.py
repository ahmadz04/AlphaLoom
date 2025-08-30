#!/usr/bin/env python3
"""
AWS S3 Service Layer for AlphaLoom
Handles all S3 operations for file storage and retrieval.
"""

import os
import json
import boto3
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
from botocore.exceptions import ClientError, NoCredentialsError
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv('config/.env')

logger = logging.getLogger(__name__)


class S3Service:
    """
    Service class for AWS S3 operations.
    Handles file uploads, downloads, and management for AlphaLoom data.
    """
    
    def __init__(self):
        """Initialize S3 service with credentials from environment variables."""
        self.bucket_name = os.getenv('AWS_S3_BUCKET')
        self.region = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        
        if not self.bucket_name:
            raise ValueError("AWS_S3_BUCKET environment variable is required")
        
        try:
            # Initialize S3 client
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
                region_name=self.region
            )
            
            # Test connection
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info(f"Successfully connected to S3 bucket: {self.bucket_name}")
            
        except NoCredentialsError:
            raise ValueError("AWS credentials not found. Please check your .env file.")
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                raise ValueError(f"S3 bucket '{self.bucket_name}' does not exist")
            elif error_code == '403':
                raise ValueError(f"Access denied to S3 bucket '{self.bucket_name}'. Check your permissions.")
            else:
                raise ValueError(f"Failed to connect to S3: {e}")
    
    def upload_file(self, local_path: Union[str, Path], s3_key: str) -> bool:
        """
        Upload a file to S3.
        
        Args:
            local_path: Path to local file
            s3_key: S3 object key (path in bucket)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            local_path = Path(local_path)
            
            if not local_path.exists():
                logger.error(f"Local file does not exist: {local_path}")
                return False
            
            self.s3_client.upload_file(str(local_path), self.bucket_name, s3_key)
            logger.info(f"Uploaded {local_path} to s3://{self.bucket_name}/{s3_key}")
            return True
            
        except ClientError as e:
            logger.error(f"Failed to upload {local_path} to S3: {e}")
            return False
    
    def download_file(self, s3_key: str, local_path: Union[str, Path]) -> bool:
        """
        Download a file from S3.
        
        Args:
            s3_key: S3 object key (path in bucket)
            local_path: Path where to save the file locally
            
        Returns:
            True if successful, False otherwise
        """
        try:
            local_path = Path(local_path)
            
            # Ensure parent directory exists
            local_path.parent.mkdir(parents=True, exist_ok=True)
            
            self.s3_client.download_file(self.bucket_name, s3_key, str(local_path))
            logger.info(f"Downloaded s3://{self.bucket_name}/{s3_key} to {local_path}")
            return True
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                logger.warning(f"S3 object does not exist: {s3_key}")
            else:
                logger.error(f"Failed to download {s3_key} from S3: {e}")
            return False
    
    def upload_json(self, data: Dict[str, Any], s3_key: str) -> bool:
        """
        Upload JSON data directly to S3.
        
        Args:
            data: Dictionary to upload as JSON
            s3_key: S3 object key (path in bucket)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            json_data = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True)
            
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=json_data.encode('utf-8'),
                ContentType='application/json'
            )
            
            logger.info(f"Uploaded JSON data to s3://{self.bucket_name}/{s3_key}")
            return True
            
        except ClientError as e:
            logger.error(f"Failed to upload JSON to {s3_key}: {e}")
            return False
    
    def download_json(self, s3_key: str) -> Optional[Dict[str, Any]]:
        """
        Download and parse JSON data from S3.
        
        Args:
            s3_key: S3 object key (path in bucket)
            
        Returns:
            Parsed JSON data or None if failed
        """
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=s3_key)
            json_data = response['Body'].read().decode('utf-8')
            
            logger.info(f"Downloaded JSON from s3://{self.bucket_name}/{s3_key}")
            return json.loads(json_data)
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                logger.warning(f"S3 object does not exist: {s3_key}")
            else:
                logger.error(f"Failed to download JSON from {s3_key}: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from {s3_key}: {e}")
            return None
    
    def file_exists(self, s3_key: str) -> bool:
        """
        Check if a file exists in S3.
        
        Args:
            s3_key: S3 object key (path in bucket)
            
        Returns:
            True if file exists, False otherwise
        """
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            return True
        except ClientError:
            return False
    
    def delete_file(self, s3_key: str) -> bool:
        """
        Delete a file from S3.
        
        Args:
            s3_key: S3 object key (path in bucket)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
            logger.info(f"Deleted s3://{self.bucket_name}/{s3_key}")
            return True
        except ClientError as e:
            logger.error(f"Failed to delete {s3_key}: {e}")
            return False
    
    def list_files(self, prefix: str = "") -> List[str]:
        """
        List files in S3 with optional prefix filter.
        
        Args:
            prefix: S3 key prefix to filter by
            
        Returns:
            List of S3 object keys
        """
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )
            
            if 'Contents' not in response:
                return []
            
            return [obj['Key'] for obj in response['Contents']]
            
        except ClientError as e:
            logger.error(f"Failed to list files with prefix '{prefix}': {e}")
            return []
    
    def get_file_size(self, s3_key: str) -> Optional[int]:
        """
        Get file size in bytes.
        
        Args:
            s3_key: S3 object key (path in bucket)
            
        Returns:
            File size in bytes or None if file doesn't exist
        """
        try:
            response = self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            return response['ContentLength']
        except ClientError:
            return None


def get_s3_path(local_path: str) -> str:
    """
    Convert local file path to S3 key by removing 'data/' prefix.
    
    Examples:
        'data/raw/filings/AAPL/2023_10-K_filing.json' -> 'raw/filings/AAPL/2023_10-K_filing.json'
        'data/processed/AAPL/10-K/2023/summaries.json' -> 'processed/AAPL/10-K/2023/summaries.json'
    
    Args:
        local_path: Local file path (with or without 'data/' prefix)
        
    Returns:
        S3 key path
    """
    path = Path(local_path)
    
    # Remove 'data/' prefix if present
    if path.parts and path.parts[0] == 'data':
        return str(Path(*path.parts[1:]))
    
    return str(path)


def get_local_path(s3_key: str) -> str:
    """
    Convert S3 key to local file path by adding 'data/' prefix.
    
    Args:
        s3_key: S3 object key
        
    Returns:
        Local file path with 'data/' prefix
    """
    return f"data/{s3_key}"


# Global S3 service instance
_s3_service = None

def get_s3_service() -> S3Service:
    """Get singleton S3 service instance."""
    global _s3_service
    if _s3_service is None:
        _s3_service = S3Service()
    return _s3_service


if __name__ == "__main__":
    # Test S3 service
    print("=== Testing S3 Service ===")
    
    try:
        s3 = S3Service()
        print(f"✓ Connected to bucket: {s3.bucket_name}")
        
        # Test uploading some JSON data
        test_data = {
            "test": "data",
            "timestamp": "2024-01-15T10:30:00Z",
            "numbers": [1, 2, 3]
        }
        
        test_key = "test/sample_data.json"
        
        if s3.upload_json(test_data, test_key):
            print(f"✓ Uploaded test JSON to {test_key}")
            
            # Test downloading it back
            downloaded_data = s3.download_json(test_key)
            if downloaded_data and downloaded_data == test_data:
                print("✓ Downloaded and verified test JSON")
            else:
                print("✗ Failed to verify downloaded JSON")
            
            # Test file existence
            if s3.file_exists(test_key):
                print("✓ File existence check passed")
            else:
                print("✗ File existence check failed")
            
            # Clean up test file
            if s3.delete_file(test_key):
                print("✓ Test cleanup completed")
        else:
            print("✗ Failed to upload test JSON")
            
    except Exception as e:
        print(f"✗ S3 service test failed: {e}")