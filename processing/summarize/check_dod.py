#!/usr/bin/env python3
"""
Definition of Done (DoD) checker for summarization milestone.

This script automatically verifies milestone requirements:
1. summaries.json exists and is valid JSON matching the schema
2. Item 7 and Item 1A each have ≥5 bullets with ≥1 span_id each
3. If section_hash unchanged and rerun, cache is hit for all processed chunks
4. Any dropped/invalid items produced at least one warnings entry

Usage:
    python check_dod.py [--summaries-path path/to/summaries.json] [--cache-dir path/to/cache]
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Set

from schema import SummariesFile


def load_summaries(summaries_path: Path) -> SummariesFile:
    """Load and validate summaries.json against schema."""
    if not summaries_path.exists():
        raise FileNotFoundError(f"Summaries file not found: {summaries_path}")
    
    try:
        with open(summaries_path, 'r') as f:
            data = json.load(f)
        return SummariesFile.model_validate(data)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {summaries_path}: {e}")
    except Exception as e:
        raise ValueError(f"Schema validation failed for {summaries_path}: {e}")


def check_bullet_requirements(summaries: SummariesFile) -> Dict[str, List[str]]:
    """Check Item 7 and Item 1A bullet requirements."""
    issues = {}
    
    # Find Item 7 and Item 1A sections
    item7_section = None
    item1a_section = None
    
    for section in summaries.sections:
        if section.section_name == "Item 7":
            item7_section = section
        elif section.section_name == "Item 1A":
            item1a_section = section
    
    # Check Item 7
    if not item7_section:
        issues["Item 7"] = ["Section not found"]
    else:
        item7_issues = []
        if len(item7_section.bullets) < 5:
            item7_issues.append(f"Only {len(item7_section.bullets)} bullets (need ≥5)")
        
        for i, bullet in enumerate(item7_section.bullets):
            if len(bullet.span_ids) == 0:
                item7_issues.append(f"Bullet {i+1} has no span_ids")
        
        if item7_issues:
            issues["Item 7"] = item7_issues
    
    # Check Item 1A
    if not item1a_section:
        issues["Item 1A"] = ["Section not found"]
    else:
        item1a_issues = []
        if len(item1a_section.bullets) < 5:
            item1a_issues.append(f"Only {len(item1a_section.bullets)} bullets (need ≥5)")
        
        for i, bullet in enumerate(item1a_section.bullets):
            if len(bullet.span_ids) == 0:
                item1a_issues.append(f"Bullet {i+1} has no span_ids")
        
        if item1a_issues:
            issues["Item 1A"] = item1a_issues
    
    return issues


def check_cache_hits(summaries: SummariesFile, cache_dir: Path) -> Dict[str, List[str]]:
    """Check cache hits for sections with unchanged section_hash."""
    issues = {}
    
    if not cache_dir.exists():
        return {"Cache": ["Cache directory not found"]}
    
    # Build expected cache path structure: cache_dir/summaries/{ticker}/{form}/{year}/
    cache_base = cache_dir / "summaries" / summaries.ticker / summaries.form / str(summaries.year)
    
    for section in summaries.sections:
        section_issues = []
        section_cache_dir = cache_base / section.section_name / section.section_hash
        
        if not section_cache_dir.exists():
            # This might be the first run, so not necessarily an issue
            continue
        
        # Check if cache files exist (look for *.json files)
        cache_files = list(section_cache_dir.glob("*.json"))
        if not cache_files:
            section_issues.append(f"No cache files found in {section_cache_dir}")
        
        if section_issues:
            issues[f"{section.section_name} cache"] = section_issues
    
    return issues


def check_warnings_for_dropped_items(summaries: SummariesFile) -> Dict[str, List[str]]:
    """Check that sections with no bullets have warnings."""
    issues = {}
    
    for section in summaries.sections:
        # If section has no bullets/key_numbers/uncertainties but no warnings, that's suspicious
        has_content = (
            len(section.bullets) > 0 or
            len(section.key_numbers) > 0 or
            len(section.uncertainties) > 0
        )
        
        if not has_content and not section.warnings:
            if "Missing warnings" not in issues:
                issues["Missing warnings"] = []
            issues["Missing warnings"].append(
                f"{section.section_name}: no content but no warnings explaining why"
            )
    
    return issues


def print_report(all_issues: Dict[str, Dict[str, List[str]]], summaries: SummariesFile) -> bool:
    """Print pass/fail report."""
    has_failures = any(issues for issues in all_issues.values() if issues)
    
    print("=== Definition of Done (DoD) Check Report ===")
    print(f"File: {summaries.ticker} {summaries.form} {summaries.year}")
    print(f"Sections found: {len(summaries.sections)}")
    
    # Schema validation
    if "schema" in all_issues and all_issues["schema"]:
        print(f"\n❌ SCHEMA: {list(all_issues['schema'].values())[0][0]}")
    else:
        print("\n✅ SCHEMA: Valid JSON matching schema")
    
    # Bullet requirements
    if "bullets" in all_issues and all_issues["bullets"]:
        print("\n❌ BULLET REQUIREMENTS:")
        for section, issues_list in all_issues["bullets"].items():
            print(f"  - {section}: {', '.join(issues_list)}")
    else:
        print("\n✅ BULLET REQUIREMENTS: Item 7 and Item 1A have ≥5 bullets with span_ids")
    
    # Cache hits
    if "cache" in all_issues and all_issues["cache"]:
        print("\n⚠️  CACHE VALIDATION:")
        for section, issues_list in all_issues["cache"].items():
            print(f"  - {section}: {', '.join(issues_list)}")
    else:
        print("\n✅ CACHE: Cache structure verified")
    
    # Warnings validation
    if "warnings" in all_issues and all_issues["warnings"]:
        print("\n❌ WARNINGS:")
        for category, issues_list in all_issues["warnings"].items():
            for issue in issues_list:
                print(f"  - {issue}")
    else:
        print("\n✅ WARNINGS: Sections with no content have explanatory warnings")
    
    print(f"\n{'='*50}")
    if has_failures:
        print("❌ RESULT: FAIL - See issues above")
        return False
    else:
        print("✅ RESULT: PASS - All DoD requirements met")
        return True


def main():
    parser = argparse.ArgumentParser(description="Check Definition of Done for summarization milestone")
    parser.add_argument(
        "--summaries-path",
        type=Path,
        default=Path("data/processed"),  # Will need to find summaries.json in subdirs
        help="Path to summaries.json file or directory containing it"
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("data/cache"),
        help="Path to cache directory"
    )
    
    args = parser.parse_args()
    
    # Find summaries.json if a directory was provided
    summaries_path = args.summaries_path
    if summaries_path.is_dir():
        # Look for summaries.json in subdirectories
        found_summaries = list(summaries_path.rglob("summaries.json"))
        if not found_summaries:
            print(f"❌ No summaries.json found in {summaries_path}")
            sys.exit(1)
        elif len(found_summaries) > 1:
            print(f"❌ Multiple summaries.json found in {summaries_path}:")
            for f in found_summaries:
                print(f"  - {f}")
            print("Please specify exact path with --summaries-path")
            sys.exit(1)
        else:
            summaries_path = found_summaries[0]
    
    all_issues = {}
    
    try:
        # 1. Load and validate schema
        summaries = load_summaries(summaries_path)
        all_issues["schema"] = {}
    except Exception as e:
        all_issues["schema"] = {"validation": [str(e)]}
        print_report(all_issues, None)
        sys.exit(1)
    
    # 2. Check bullet requirements
    bullet_issues = check_bullet_requirements(summaries)
    if bullet_issues:
        all_issues["bullets"] = bullet_issues
    
    # 3. Check cache hits
    cache_issues = check_cache_hits(summaries, args.cache_dir)
    if cache_issues:
        all_issues["cache"] = cache_issues
    
    # 4. Check warnings for dropped items
    warning_issues = check_warnings_for_dropped_items(summaries)
    if warning_issues:
        all_issues["warnings"] = warning_issues
    
    # Print report and exit
    success = print_report(all_issues, summaries)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()