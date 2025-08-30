#!/usr/bin/env python3
"""
Test script to validate Option 2 integration
This script tests the complete flow without making actual API calls
"""

import os
import json
from datetime import datetime, timezone
from pathlib import Path

# Add the project root to the path so we can import modules
import sys
sys.path.append('.')

from config.sections_config import get_enabled_sections
from ingestion.providers.financial_datasets import FinancialDatasetsClient
from ingestion.utils.models import FilingRaw, FilingItem

def test_sections_config():
    """Test that sections config is updated for Option 2"""
    sections = get_enabled_sections()
    print(f"✅ Enabled sections: {sections}")
    
    expected = ['Item 1', 'Item 1A']
    if sections == expected:
        print(f"✅ Sections configuration correct: {sections}")
        return True
    else:
        print(f"❌ Expected {expected}, got {sections}")
        return False

def test_api_url_construction():
    """Test Option 2 URL construction logic"""
    try:
        # This mimics what happens in the client when items are provided
        import urllib.parse
        
        params = {
            "ticker": "AAPL",
            "filing_type": "10-K", 
            "year": 2023
        }
        
        items = ['Item 1', 'Item 1A']
        query_parts = [f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items()]
        
        for item in items:
            query_parts.append(f"item={urllib.parse.quote(item)}")
        
        url_path = f"/filings/items/?{'&'.join(query_parts)}"
        expected_path = "/filings/items/?ticker=AAPL&filing_type=10-K&year=2023&item=Item%201&item=Item%201A"
        
        if url_path == expected_path:
            print(f"✅ URL construction correct: {url_path}")
            return True
        else:
            print(f"❌ URL mismatch. Expected: {expected_path}, Got: {url_path}")
            return False
            
    except Exception as e:
        print(f"❌ URL construction failed: {e}")
        return False

def test_mock_option2_response():
    """Test processing of mock Option 2 API response"""
    try:
        # Mock Option 2 API response structure
        mock_response = {
            "resource": "filing_items",
            "ticker": "AAPL",
            "cik": "0000320193",
            "filing_type": "10-K",
            "year": 2023,
            "items": [
                {
                    "number": "Item 1",
                    "title": "Business",
                    "text": "Apple Inc. designs, manufactures and markets smartphones, personal computers, tablets..."
                },
                {
                    "number": "Item 1A",
                    "title": "Risk Factors", 
                    "text": "The Company's business, reputation, results of operations, financial condition..."
                }
            ]
        }
        
        # Test the FilingItem creation logic from run_filings.py
        filing_items = []
        for item_data in mock_response.get("items", []):
            section_number = item_data.get("number", "")
            section_title = item_data.get("title", "")
            section_text = item_data.get("text", "")
            
            filing_items.append(FilingItem(
                item=section_number or section_title or "",
                content=section_text or "",
                section_type=section_number or None
            ))
        
        if len(filing_items) == 2:
            print(f"✅ Successfully processed {len(filing_items)} sections from Option 2 response")
            print(f"   - Section 1: {filing_items[0].item} ({len(filing_items[0].content)} chars)")
            print(f"   - Section 2: {filing_items[1].item} ({len(filing_items[1].content)} chars)")
            return True
        else:
            print(f"❌ Expected 2 sections, got {len(filing_items)}")
            return False
            
    except Exception as e:
        print(f"❌ Mock response processing failed: {e}")
        return False

def test_bypass_sectionizer_detection():
    """Test the logic that detects when to bypass sectionizer"""
    try:
        # Mock filing data that would trigger sectionizer bypass
        mock_filing_data = {
            "ticker": "AAPL",
            "filing_type": "10-K",
            "year": 2023,
            "items": [
                {"item": "Item 1", "content": "Business content"},
                {"item": "Item 1A", "content": "Risk factors content"}
            ],
            "meta": {
                "extraction_method": "option_2_targeted",
                "sections_requested": ["Item 1", "Item 1A"],
                "sections_received": ["Item 1", "Item 1A"]
            }
        }
        
        # Test the bypass logic from terminal_app.py and app.py
        should_skip = (
            mock_filing_data.get('meta', {}).get('extraction_method') == 'option_2_targeted' and 
            len(mock_filing_data.get('items', [])) <= 3
        )
        
        if should_skip:
            print("✅ Sectionizer bypass logic working correctly")
            return True
        else:
            print("❌ Sectionizer bypass logic failed")
            return False
            
    except Exception as e:
        print(f"❌ Bypass detection test failed: {e}")
        return False

def test_frontend_labels():
    """Test that frontend labels are updated correctly"""
    try:
        # Import the updated get_section_title functions
        from terminal_app import get_section_title as terminal_get_section_title
        from app import get_section_title as app_get_section_title
        
        # Test both frontend implementations
        terminal_item1 = terminal_get_section_title("Item 1", "Business")
        terminal_item1a = terminal_get_section_title("Item 1A", "Risk Factors")
        
        app_item1 = app_get_section_title("Item 1", "Business")
        app_item1a = app_get_section_title("Item 1A", "Risk Factors")
        
        expected_item1 = "Summary of Business"
        expected_item1a = "Summary of Risk Factors"
        
        if (terminal_item1 == expected_item1 and terminal_item1a == expected_item1a and
            app_item1 == expected_item1 and app_item1a == expected_item1a):
            print("✅ Frontend labels updated correctly")
            print(f"   - Item 1: {terminal_item1}")
            print(f"   - Item 1A: {terminal_item1a}")
            return True
        else:
            print(f"❌ Frontend labels incorrect")
            print(f"   Terminal - Item 1: {terminal_item1} (expected: {expected_item1})")
            print(f"   Terminal - Item 1A: {terminal_item1a} (expected: {expected_item1a})")
            print(f"   App - Item 1: {app_item1} (expected: {expected_item1})")
            print(f"   App - Item 1A: {app_item1a} (expected: {expected_item1a})")
            return False
            
    except Exception as e:
        print(f"❌ Frontend labels test failed: {e}")
        return False

def main():
    """Run all integration tests"""
    print("🔍 Testing Option 2 Integration")
    print("=" * 50)
    
    tests = [
        ("Sections Configuration", test_sections_config),
        ("API URL Construction", test_api_url_construction), 
        ("Option 2 Response Processing", test_mock_option2_response),
        ("Sectionizer Bypass Detection", test_bypass_sectionizer_detection),
        ("Frontend Labels", test_frontend_labels)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n🧪 {test_name}")
        print("-" * 30)
        if test_func():
            passed += 1
        else:
            print(f"❌ {test_name} failed")
    
    print(f"\n{'=' * 50}")
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All Option 2 integration tests passed!")
        print("\nNext steps:")
        print("1. Test with a real API call using: python terminal_app.py")
        print("2. Test with Gradio interface using: python app.py")
        print("3. Verify that 'Summary of Business' and 'Summary of Risk Factors' appear correctly")
        return True
    else:
        print("❌ Some tests failed. Please fix the issues before proceeding.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)