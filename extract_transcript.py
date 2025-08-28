#!/usr/bin/env python3
"""
Extract complete transcript from ingested data and write to clean JSON file.
"""

import json
import os
from datetime import datetime
from pathlib import Path

def extract_transcript(transcript_file_path: str, output_file_path: str = None):
    """
    Extract transcript from ingested data and write to clean JSON file.
    
    Args:
        transcript_file_path: Path to the ingested transcript file
        output_file_path: Path for output file (optional, auto-generated if not provided)
    """
    
    # Read the ingested transcript data
    with open(transcript_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Extract key information
    ticker = data['ticker']
    call_id = data['call_id']
    call_datetime = data['call_datetime']
    title = data['title']
    canonical_url = data['canonical_url']
    
    # Extract the full transcript text from sections
    transcript_text = ""
    if data.get('sections'):
        for section in data['sections']:
            if section.get('text'):
                transcript_text += section['text'] + "\n\n"
    
    # Create clean transcript structure
    clean_transcript = {
        "metadata": {
            "ticker": ticker,
            "call_id": call_id,
            "call_datetime": call_datetime,
            "title": title,
            "canonical_url": canonical_url,
            "extracted_at": datetime.now().isoformat() + "Z",
            "source_file": transcript_file_path
        },
        "transcript": transcript_text.strip()
    }
    
    # Generate output filename if not provided
    if not output_file_path:
        call_date = call_datetime.split('T')[0]  # Extract date part
        output_file_path = f"transcript_{ticker}_{call_date}_{call_id}.json"
    
    # Write to output file
    with open(output_file_path, 'w', encoding='utf-8') as f:
        json.dump(clean_transcript, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Transcript extracted successfully!")
    print(f"📁 Output file: {output_file_path}")
    print(f"📊 Transcript length: {len(transcript_text)} characters")
    print(f"📅 Call date: {call_date}")
    print(f"🏷️  Ticker: {ticker}")
    
    return output_file_path

def main():
    """Main function to extract the most recent transcript."""
    
    # Find the most recent transcript for AAPL - updated path for new structure
    latest_index_path = "data/dash/latest_index/AAPL.json"
    
    if not os.path.exists(latest_index_path):
        print("❌ No latest index found. Run ingestion first.")
        return
    
    # Read latest index to find the most recent transcript
    with open(latest_index_path, 'r') as f:
        latest_index = json.load(f)
    
    manifest_path = latest_index['latest_manifest_path']
    
    # Read manifest to get transcript path
    with open(manifest_path, 'r') as f:
        manifest = json.load(f)
    
    transcript_path = manifest.get('transcript_path')
    
    if not transcript_path:
        print("❌ Latest manifest is not for a transcript. Run transcript ingestion first, or use extract_filing.py for SEC filings.")
        return
    
    if not os.path.exists(transcript_path):
        print(f"❌ Transcript file not found: {transcript_path}")
        return
    
    print(f"📖 Extracting transcript from: {transcript_path}")
    
    # Extract and save transcript
    output_file = extract_transcript(transcript_path)
    
    # Show a preview of the extracted transcript
    with open(output_file, 'r', encoding='utf-8') as f:
        extracted_data = json.load(f)
    
    print(f"\n📝 Transcript Preview (first 500 characters):")
    print("-" * 50)
    preview = extracted_data['transcript'][:500] + "..." if len(extracted_data['transcript']) > 500 else extracted_data['transcript']
    print(preview)

if __name__ == "__main__":
    main()
