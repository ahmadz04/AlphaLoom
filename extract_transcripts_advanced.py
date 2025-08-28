#!/usr/bin/env python3
"""
Advanced transcript extraction with multiple output formats and batch processing.
"""

import json
import os
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

class TranscriptExtractor:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        
    def find_all_transcripts(self, ticker: str = None) -> List[Dict]:
        """Find all available transcripts for a ticker or all tickers."""
        transcripts = []
        
        if ticker:
            ticker_dirs = [self.data_dir / "raw" / "transcripts" / ticker.upper()]
        else:
            ticker_dirs = list((self.data_dir / "raw" / "transcripts").glob("*"))
        
        for ticker_dir in ticker_dirs:
            if not ticker_dir.exists():
                continue
                
            ticker_symbol = ticker_dir.name
            for transcript_file in ticker_dir.glob("*_call.json"):
                try:
                    with open(transcript_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    transcripts.append({
                        'file_path': str(transcript_file),
                        'ticker': data['ticker'],
                        'call_id': data['call_id'],
                        'call_datetime': data['call_datetime'],
                        'title': data['title'],
                        'file_size': transcript_file.stat().st_size
                    })
                except Exception as e:
                    print(f"⚠️  Error reading {transcript_file}: {e}")
        
        # Sort by call datetime (newest first)
        transcripts.sort(key=lambda x: x['call_datetime'], reverse=True)
        return transcripts
    
    def extract_transcript(self, transcript_file_path: str, output_format: str = "json") -> Dict:
        """Extract transcript from ingested data."""
        
        with open(transcript_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Extract transcript text
        transcript_text = ""
        if data.get('sections'):
            for section in data['sections']:
                if section.get('text'):
                    transcript_text += section['text'] + "\n\n"
        
        # Create clean transcript structure
        clean_transcript = {
            "metadata": {
                "ticker": data['ticker'],
                "call_id": data['call_id'],
                "call_datetime": data['call_datetime'],
                "title": data['title'],
                "canonical_url": data.get('canonical_url'),
                "extracted_at": datetime.now().isoformat() + "Z",
                "source_file": transcript_file_path,
                "hash": data.get('hash'),
                "provider": data.get('provider')
            },
            "transcript": transcript_text.strip()
        }
        
        return clean_transcript
    
    def save_transcript(self, transcript_data: Dict, output_path: str, format_type: str = "json"):
        """Save transcript in specified format."""
        
        if format_type == "json":
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(transcript_data, f, indent=2, ensure_ascii=False)
        
        elif format_type == "txt":
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(f"Title: {transcript_data['metadata']['title']}\n")
                f.write(f"Ticker: {transcript_data['metadata']['ticker']}\n")
                f.write(f"Call Date: {transcript_data['metadata']['call_datetime']}\n")
                f.write(f"Call ID: {transcript_data['metadata']['call_id']}\n")
                f.write(f"URL: {transcript_data['metadata']['canonical_url']}\n")
                f.write("-" * 80 + "\n\n")
                f.write(transcript_data['transcript'])
        
        elif format_type == "md":
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(f"# {transcript_data['metadata']['title']}\n\n")
                f.write(f"**Ticker:** {transcript_data['metadata']['ticker']}  \n")
                f.write(f"**Call Date:** {transcript_data['metadata']['call_datetime']}  \n")
                f.write(f"**Call ID:** {transcript_data['metadata']['call_id']}  \n")
                f.write(f"**URL:** [{transcript_data['metadata']['canonical_url']}]({transcript_data['metadata']['canonical_url']})  \n\n")
                f.write("---\n\n")
                f.write(transcript_data['transcript'])
    
    def batch_extract(self, ticker: str = None, output_dir: str = "extracted_transcripts", 
                      format_type: str = "json", limit: int = None):
        """Extract multiple transcripts in batch."""
        
        transcripts = self.find_all_transcripts(ticker)
        
        if limit:
            transcripts = transcripts[:limit]
        
        if not transcripts:
            print("❌ No transcripts found.")
            return
        
        # Create output directory
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        print(f"📊 Found {len(transcripts)} transcripts to extract")
        print(f"📁 Output directory: {output_path}")
        print(f"🔤 Format: {format_type.upper()}")
        print("-" * 50)
        
        for i, transcript_info in enumerate(transcripts, 1):
            print(f"\n[{i}/{len(transcripts)}] Processing {transcript_info['ticker']} - {transcript_info['title'][:50]}...")
            
            try:
                # Extract transcript
                transcript_data = self.extract_transcript(transcript_info['file_path'])
                
                # Generate output filename
                call_date = transcript_data['metadata']['call_datetime'].split('T')[0]
                ticker = transcript_data['metadata']['ticker']
                call_id = transcript_data['metadata']['call_id']
                
                if format_type == "json":
                    output_file = output_path / f"transcript_{ticker}_{call_date}_{call_id}.json"
                elif format_type == "txt":
                    output_file = output_path / f"transcript_{ticker}_{call_date}_{call_id}.txt"
                elif format_type == "md":
                    output_file = output_path / f"transcript_{ticker}_{call_date}_{call_id}.md"
                
                # Save transcript
                self.save_transcript(transcript_data, str(output_file), format_type)
                
                print(f"✅ Saved: {output_file.name}")
                print(f"📊 Length: {len(transcript_data['transcript'])} characters")
                
            except Exception as e:
                print(f"❌ Error processing {transcript_info['file_path']}: {e}")
        
        print(f"\n🎉 Batch extraction complete! {len(transcripts)} transcripts processed.")

def main():
    parser = argparse.ArgumentParser(description="Advanced transcript extraction tool")
    parser.add_argument("--ticker", help="Specific ticker to extract (e.g., AAPL)")
    parser.add_argument("--format", choices=["json", "txt", "md"], default="json", 
                       help="Output format (default: json)")
    parser.add_argument("--output-dir", default="extracted_transcripts", 
                       help="Output directory (default: extracted_transcripts)")
    parser.add_argument("--limit", type=int, help="Limit number of transcripts to extract")
    parser.add_argument("--list", action="store_true", help="List available transcripts only")
    
    args = parser.parse_args()
    
    extractor = TranscriptExtractor()
    
    if args.list:
        # Just list available transcripts
        transcripts = extractor.find_all_transcripts(args.ticker)
        if not transcripts:
            print("❌ No transcripts found.")
            return
        
        print(f"📊 Available transcripts ({len(transcripts)} total):")
        print("-" * 80)
        for i, t in enumerate(transcripts, 1):
            call_date = t['call_datetime'].split('T')[0]
            print(f"{i:2d}. {t['ticker']} | {call_date} | {t['title'][:60]}...")
        return
    
    # Extract transcripts
    extractor.batch_extract(
        ticker=args.ticker,
        output_dir=args.output_dir,
        format_type=args.format,
        limit=args.limit
    )

if __name__ == "__main__":
    main()
