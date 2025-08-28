#!/usr/bin/env python3
"""
Tests for sectionize.py pattern matching and heading detection.

Self-contained tests that don't require large files or external dependencies.
"""

import sys
import os

# Add the project root to the path so we can import from processing/
try:
    # When run as a file
    project_root = os.path.join(os.path.dirname(__file__), '..')
except NameError:
    # When run via exec() or in interactive mode
    project_root = os.path.join(os.path.dirname(os.path.abspath('.')), '.')
    
sys.path.insert(0, project_root)

from processing.sectionize import find_headings, map_title_to_item, prefix_for_item


def test_traditional_sec_headings():
    """Test traditional SEC heading formats like 'ITEM 7. MANAGEMENT'S DISCUSSION'."""
    
    text = """
ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS OF FINANCIAL CONDITION AND RESULTS OF OPERATIONS

Some content here about the company's financial performance.

ITEM 1A. RISK FACTORS  

Risk factor content goes here.

ITEM 9A — CONTROLS AND PROCEDURES

Controls content here.
"""
    
    # Note: Our current implementation looks for "=== Title ===" format,
    # so this test will need to be adapted if we add support for traditional headings
    headings = find_headings(text)
    
    # Since our current implementation doesn't match traditional SEC formats,
    # this test documents the expected behavior if we extend it
    assert len(headings) == 0, "Current implementation expects '=== Title ===' format"


def test_processed_heading_format():
    """Test the processed heading format that our implementation currently supports."""
    
    text = """
=== Business ===

Company Background The Company designs and manufactures products.

=== Risk Factors ===

The Company faces various risks in its business operations.

=== Management Discussion & Analysis (MD&A) ===

This section provides management's perspective on financial results.

=== Properties ===

The Company owns and leases various facilities.
"""
    
    headings = find_headings(text)
    
    # Should find 4 headings
    assert len(headings) == 4, f"Expected 4 headings, got {len(headings)}"
    
    # Check specific mappings
    expected = [
        ("Item 1", "Business"),
        ("Item 1A", "Risk Factors"), 
        ("Item 7", "Management Discussion & Analysis (MD&A)"),
        ("Item 2", "Properties")
    ]
    
    for i, (expected_name, expected_title) in enumerate(expected):
        heading = headings[i]
        assert heading['name'] == expected_name, f"Expected name {expected_name}, got {heading['name']}"
        assert heading['title'] == expected_title, f"Expected title {expected_title}, got {heading['title']}"


def test_map_title_to_item():
    """Test the title to item number mapping function."""
    
    test_cases = [
        ("Business", "1"),
        ("Risk Factors", "1A"),
        ("Management Discussion & Analysis (MD&A)", "7"),
        ("Management's Discussion and Analysis", "7"),
        ("Properties", "2"),
        ("Legal Proceedings", "3"),
        ("Financial Statements and Supplementary Data", "8"),
        ("Unknown Section", None)
    ]
    
    for title, expected_item in test_cases:
        result = map_title_to_item(title)
        assert result == expected_item, f"Title '{title}' should map to '{expected_item}', got '{result}'"


def test_prefix_for_item():
    """Test the item name to prefix mapping function."""
    
    test_cases = [
        ("Item 1", "biz"),
        ("Item 1A", "risks"),
        ("Item 7", "mdna"),
        ("Item 2", "item2"),
        ("Item 10", "item10"),
        ("Item 1B", "item1b"),
        ("Item 7A", "item7a")
    ]
    
    for item_name, expected_prefix in test_cases:
        result = prefix_for_item(item_name)
        assert result == expected_prefix, f"Item '{item_name}' should map to prefix '{expected_prefix}', got '{result}'"


def test_heading_positions():
    """Test that heading positions are calculated correctly."""
    
    text = """=== Business ===

Some business content here.

=== Risk Factors ===

Risk factor content here.
"""
    
    headings = find_headings(text)
    assert len(headings) == 2
    
    # First heading should start at position 0
    assert headings[0]['start'] == 0, f"First heading should start at 0, got {headings[0]['start']}"
    assert headings[0]['name'] == "Item 1"
    
    # Second heading should start after the first
    assert headings[1]['start'] > headings[0]['start'], "Second heading should start after first"
    assert headings[1]['name'] == "Item 1A"


def test_mixed_case_and_punctuation():
    """Test handling of different case and punctuation in headings."""
    
    text = """
=== BUSINESS ===

Content here.

=== risk factors ===  

More content.

=== Management Discussion & Analysis (MD&A) ===

Analysis content.
"""
    
    headings = find_headings(text)
    assert len(headings) == 3
    
    # Should map correctly despite case differences
    expected_names = ["Item 1", "Item 1A", "Item 7"]
    for i, expected_name in enumerate(expected_names):
        assert headings[i]['name'] == expected_name, f"Heading {i} should be {expected_name}"


def run_all_tests():
    """Run all tests and report results."""
    
    test_functions = [
        test_traditional_sec_headings,
        test_processed_heading_format,
        test_map_title_to_item,
        test_prefix_for_item,
        test_heading_positions,
        test_mixed_case_and_punctuation
    ]
    
    passed = 0
    failed = 0
    
    for test_func in test_functions:
        try:
            test_func()
            print(f"✓ {test_func.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"✗ {test_func.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test_func.__name__}: Unexpected error: {e}")
            failed += 1
    
    print(f"\nResults: {passed} passed, {failed} failed")
    
    if failed > 0:
        sys.exit(1)
    else:
        print("All tests passed!")


if __name__ == "__main__":
    # Check if pytest is available
    try:
        import pytest
        print("Running tests with pytest...")
        try:
            pytest.main([__file__, "-q"])
        except NameError:
            # __file__ not available, run manually
            print("pytest available but running manually due to execution context...")
            run_all_tests()
    except ImportError:
        print("pytest not available, running tests manually...")
        run_all_tests()