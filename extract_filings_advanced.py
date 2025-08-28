#!/usr/bin/env python3
"""
Advanced SEC filing extraction with multiple output formats and batch processing.
"""

import json
import os
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

class FilingExtractor:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        
    def find_all_filings(self, ticker: str = None) -> List[Dict]:
        """Find all available SEC filings for a ticker or all tickers."""
        filings = []
        
        if ticker:
            ticker_dirs = [self.data_dir / "raw" / "filings" / ticker.upper()]
        else:
            ticker_dirs = list((self.data_dir / "raw" / "filings").glob("*"))
        
        for ticker_dir in ticker_dirs:
            if not ticker_dir.exists():
                continue
                
            ticker_symbol = ticker_dir.name
            for filing_file in ticker_dir.glob("*_filing.json"):
                try:
                    with open(filing_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    filings.append({
                        'file_path': str(filing_file),
                        'ticker': data['ticker'],
                        'filing_type': data['filing_type'],
                        'year': data['year'],
                        'filed_date': data.get('filed_date'),
                        'company_name': data.get('company_name', ''),
                        'items_count': len(data.get('items', [])),
                        'file_size': filing_file.stat().st_size
                    })
                except Exception as e:
                    print(f"⚠️  Error reading {filing_file}: {e}")
        
        # Sort by year and filed_date (newest first)
        filings.sort(key=lambda x: (x['year'], x['filed_date'] or ''), reverse=True)
        return filings
    
    def extract_filing(self, filing_file_path: str, output_format: str = "json") -> Dict:
        """Extract SEC filing from ingested data."""
        
        with open(filing_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Extract filing content
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
                "ticker": data['ticker'],
                "company_name": data.get('company_name', ''),
                "cik": data.get('cik', ''),
                "filing_type": data['filing_type'],
                "year": data['year'],
                "period_end_date": data.get('period_end_date'),
                "filed_date": data.get('filed_date'),
                "extracted_at": datetime.now().isoformat() + "Z",
                "source_file": filing_file_path,
                "hash": data.get('hash'),
                "provider": data.get('provider'),
                "items_count": len(items_summary),
                "items_summary": items_summary
            },
            "filing_content": filing_content.strip()
        }
        
        return clean_filing
    
    def save_filing(self, filing_data: Dict, output_path: str, format_type: str = "json"):
        """Save SEC filing in specified format."""
        
        metadata = filing_data['metadata']
        
        if format_type == "json":
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(filing_data, f, indent=2, ensure_ascii=False)
        
        elif format_type == "txt":
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(f"Company: {metadata['company_name']}\n")
                f.write(f"Ticker: {metadata['ticker']}\n")
                f.write(f"CIK: {metadata['cik']}\n")
                f.write(f"Filing Type: {metadata['filing_type']}\n")
                f.write(f"Year: {metadata['year']}\n")
                f.write(f"Filed Date: {metadata['filed_date']}\n")
                f.write(f"Period End Date: {metadata['period_end_date']}\n")
                f.write(f"Items Count: {metadata['items_count']}\n")
                f.write("-" * 80 + "\n\n")
                f.write(filing_data['filing_content'])
        
        elif format_type == "md":
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(f"# {metadata['company_name']} ({metadata['ticker']}) - {metadata['filing_type']} {metadata['year']}\n\n")
                f.write(f"**Company:** {metadata['company_name']}  \n")
                f.write(f"**Ticker:** {metadata['ticker']}  \n")
                f.write(f"**CIK:** {metadata['cik']}  \n")
                f.write(f"**Filing Type:** {metadata['filing_type']}  \n")
                f.write(f"**Year:** {metadata['year']}  \n")
                f.write(f"**Filed Date:** {metadata['filed_date']}  \n")
                f.write(f"**Period End Date:** {metadata['period_end_date']}  \n")
                f.write(f"**Items Count:** {metadata['items_count']}  \n\n")
                
                # Add items summary
                if metadata.get('items_summary'):
                    f.write("## Items Included\n\n")
                    for item in metadata['items_summary']:
                        f.write(f"- **{item['item']}** ({item['content_length']:,} characters)\n")
                    f.write("\n")
                
                f.write("---\n\n")
                f.write(filing_data['filing_content'])
    
    def batch_extract(self, ticker: str = None, output_dir: str = "extracted_filings", 
                      format_type: str = "json", limit: int = None, filing_type: str = None):
        """Extract multiple SEC filings in batch."""
        
        filings = self.find_all_filings(ticker)
        
        # Filter by filing type if specified
        if filing_type:
            filings = [f for f in filings if f['filing_type'] == filing_type]
        
        if limit:
            filings = filings[:limit]
        
        if not filings:
            print("❌ No SEC filings found.")
            return
        
        # Create output directory
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        print(f"📊 Found {len(filings)} SEC filings to extract")
        print(f"📁 Output directory: {output_path}")
        print(f"🔤 Format: {format_type.upper()}")
        print("-" * 50)
        
        for i, filing_info in enumerate(filings, 1):
            print(f"\n[{i}/{len(filings)}] Processing {filing_info['ticker']} - {filing_info['filing_type']} {filing_info['year']}")
            
            try:
                # Extract filing
                filing_data = self.extract_filing(filing_info['file_path'])
                
                # Generate output filename
                ticker = filing_data['metadata']['ticker']
                filing_type = filing_data['metadata']['filing_type']
                year = filing_data['metadata']['year']
                filed_date = filing_data['metadata']['filed_date']
                
                if filed_date:
                    date_part = filed_date.split('T')[0]
                else:
                    date_part = str(year)
                
                if format_type == "json":
                    output_file = output_path / f"filing_{ticker}_{filing_type}_{date_part}.json"
                elif format_type == "txt":
                    output_file = output_path / f"filing_{ticker}_{filing_type}_{date_part}.txt"
                elif format_type == "md":
                    output_file = output_path / f"filing_{ticker}_{filing_type}_{date_part}.md"
                
                # Save filing
                self.save_filing(filing_data, str(output_file), format_type)
                
                print(f"✅ Saved: {output_file.name}")
                print(f"📊 Length: {len(filing_data['filing_content'])} characters")
                print(f"📋 Items: {filing_data['metadata']['items_count']}")
                
            except Exception as e:
                print(f"❌ Error processing {filing_info['file_path']}: {e}")
        
        print(f"\n🎉 Batch extraction complete! {len(filings)} SEC filings processed.")

def main():
    parser = argparse.ArgumentParser(description="Advanced SEC filing extraction tool")
    parser.add_argument("--ticker", help="Specific ticker to extract (e.g., AAPL)")
    parser.add_argument("--filing-type", choices=["10-K", "10-Q"], 
                       help="Specific filing type to extract")
    parser.add_argument("--format", choices=["json", "txt", "md"], default="json", 
                       help="Output format (default: json)")
    parser.add_argument("--output-dir", default="extracted_filings", 
                       help="Output directory (default: extracted_filings)")
    parser.add_argument("--limit", type=int, help="Limit number of filings to extract")
    parser.add_argument("--list", action="store_true", help="List available SEC filings only")
    
    args = parser.parse_args()
    
    extractor = FilingExtractor()
    
    if args.list:
        # Just list available filings
        filings = extractor.find_all_filings(args.ticker)
        if not filings:
            print("❌ No SEC filings found.")
            return
        
        print(f"📊 Available SEC filings ({len(filings)} total):")
        print("-" * 80)
        for i, f in enumerate(filings, 1):
            filed_date = f['filed_date'].split('T')[0] if f['filed_date'] else str(f['year'])
            company_name = (f['company_name'] or 'Unknown')[:40]
            print(f"{i:2d}. {f['ticker']} | {f['filing_type']} | {f['year']} | {filed_date} | {company_name}...")
        return
    
    # Extract filings
    extractor.batch_extract(
        ticker=args.ticker,
        output_dir=args.output_dir,
        format_type=args.format,
        limit=args.limit,
        filing_type=args.filing_type
    )

if __name__ == "__main__":
    main()