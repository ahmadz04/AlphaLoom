#!/usr/bin/env python3
"""
Extract complete SEC filing from ingested data and write to clean JSON file.
"""

import json
import os
from datetime import datetime
from pathlib import Path

def extract_filing(filing_file_path: str, output_file_path: str = None):
    """
    Extract SEC filing from ingested data and write to clean JSON file.
    
    Args:
        filing_file_path: Path to the ingested filing file
        output_file_path: Path for output file (optional, auto-generated if not provided)
    """
    
    # Read the ingested filing data
    with open(filing_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Extract key information
    ticker = data['ticker']
    filing_type = data['filing_type']
    year = data['year']
    company_name = data.get('company_name', '')
    cik = data.get('cik', '')
    period_end_date = data.get('period_end_date')
    filed_date = data.get('filed_date')
    
    # Extract the full filing content from items
    filing_content = ""
    items_summary = []
    
    if data.get('items'):
        for item in data['items']:
            item_name = item.get('item', '')
            item_content = item.get('content', '')
            
            if item_content:
                filing_content += f"=== {item_name} ===\n\n{item_content}\n\n"
                items_summary.append({
                    "item": item_name,
                    "content_length": len(item_content),
                    "section_type": item.get('section_type')
                })
    
    # Create clean filing structure
    clean_filing = {
        "metadata": {
            "ticker": ticker,
            "company_name": company_name,
            "cik": cik,
            "filing_type": filing_type,
            "year": year,
            "period_end_date": period_end_date,
            "filed_date": filed_date,
            "extracted_at": datetime.now().isoformat() + "Z",
            "source_file": filing_file_path,
            "items_count": len(items_summary),
            "items_summary": items_summary
        },
        "filing_content": filing_content.strip()
    }
    
    # Generate output filename if not provided
    if not output_file_path:
        date_part = year
        if filed_date:
            date_part = filed_date.split('T')[0]
        output_file_path = f"filing_{ticker}_{filing_type}_{date_part}.json"
    
    # Write to output file
    with open(output_file_path, 'w', encoding='utf-8') as f:
        json.dump(clean_filing, f, indent=2, ensure_ascii=False)
    
    print(f"✅ SEC Filing extracted successfully!")
    print(f"📁 Output file: {output_file_path}")
    print(f"📊 Filing content length: {len(filing_content)} characters")
    print(f"📋 Items included: {len(items_summary)}")
    print(f"📅 Filing year: {year}")
    print(f"🏢 Company: {company_name} ({ticker})")
    print(f"📄 Filing type: {filing_type}")
    
    return output_file_path

def main():
    """Main function to extract the most recent SEC filing."""
    
    # Find the most recent filing for AAPL - updated path for new structure
    latest_index_path = "data/dash/latest_index/AAPL.json"
    
    if not os.path.exists(latest_index_path):
        print("❌ No latest index found. Run filing ingestion first.")
        return
    
    # Read latest index to find the most recent filing
    with open(latest_index_path, 'r') as f:
        latest_index = json.load(f)
    
    manifest_path = latest_index['latest_manifest_path']
    
    # Read manifest to get filing path
    with open(manifest_path, 'r') as f:
        manifest = json.load(f)
    
    # Check if this is a filing manifest (has filing_path) or transcript manifest
    if 'filing_path' not in manifest:
        print("❌ Latest manifest is not for a SEC filing. Run SEC filing ingestion first.")
        return
        
    filing_path = manifest['filing_path']
    
    if not os.path.exists(filing_path):
        print(f"❌ Filing file not found: {filing_path}")
        return
    
    print(f"📖 Extracting SEC filing from: {filing_path}")
    
    # Extract and save filing
    output_file = extract_filing(filing_path)
    
    # Show a preview of the extracted filing
    with open(output_file, 'r', encoding='utf-8') as f:
        extracted_data = json.load(f)
    
    print(f"\n📝 Filing Preview (first 500 characters):")
    print("-" * 50)
    preview = extracted_data['filing_content'][:500] + "..." if len(extracted_data['filing_content']) > 500 else extracted_data['filing_content']
    print(preview)

if __name__ == "__main__":
    main()