#!/usr/bin/env python3
"""
S3-Enhanced SEC Filing Ingestion Pipeline

This script extends run_filings.py with intelligent S3 caching to avoid redundant API calls.
It checks S3 first for existing processed data before fetching from financialdatasets.ai API.
"""

import os, argparse, json
from datetime import datetime, timezone
from dotenv import load_dotenv

# Import original modules
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from ingestion.storage.hybrid import HybridStorage
from ingestion.utils.paths import filing_path, filing_txt_path, legacy_manifest_path, latest_index_path
from ingestion.utils.time import utc_now_iso
from ingestion.utils.hashing import sha256_text
from ingestion.providers.financial_datasets import FinancialDatasetsClient
from ingestion.utils.models import FilingRaw, FilingItem, Manifest, LatestIndex
from config.sections_config import get_enabled_sections

# Import S3 caching services
from services.pipeline_cache import get_pipeline_cache


def main():
    load_dotenv(dotenv_path=os.path.join("config", ".env"), override=True)

    parser = argparse.ArgumentParser(description="Alpha Loom - S3-Enhanced SEC Filing Ingestion")
    parser.add_argument("--ticker", default=os.getenv("DEFAULT_TICKER", "AAPL"))
    parser.add_argument("--filing-type", default=os.getenv("DEFAULT_FILING_TYPE", "10-K"), 
                       choices=["10-K", "10-Q"], help="Filing type to fetch")
    parser.add_argument("--year", type=int, help="Specific year (defaults to current/previous year)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files and ignore cache")
    parser.add_argument("--skip-cache-check", action="store_true", help="Skip cache checks and force fresh processing")
    args = parser.parse_args()

    ticker = args.ticker.upper()
    filing_type = args.filing_type
    year = args.year
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    print(f"🚀 [{run_id}] S3-Enhanced Filing Ingestion")
    print(f"   📊 Ticker: {ticker}")
    print(f"   📋 Filing Type: {filing_type}")
    print(f"   📅 Year: {year or 'auto'}")
    print(f"   💾 Storage: {'S3' if os.getenv('USE_S3_STORAGE', 'false').lower() == 'true' else 'Local'}")

    # Initialize services
    storage = HybridStorage()
    client = FinancialDatasetsClient()
    pipeline_cache = get_pipeline_cache()

    # Determine actual year if not specified
    if not year:
        current_year = datetime.now(timezone.utc).year
        # Try current year first, then previous year
        for test_year in [current_year, current_year - 1]:
            if not args.skip_cache_check:
                print(f"\n🔍 Checking cache for {ticker} {filing_type} {test_year}...")
                if not pipeline_cache.should_skip_ingestion(ticker, filing_type, test_year):
                    year = test_year
                    break
                else:
                    # Check if we have cached summaries to return
                    cached_data = pipeline_cache.get_cached_data_summary(ticker, filing_type, test_year)
                    if cached_data:
                        print(f"\n✅ Using cached data from {test_year}:")
                        print(f"   📊 Sections: {cached_data['sections_count']}")
                        print(f"   📋 Bullets: {cached_data['total_bullets']}")
                        print(f"   🔢 Key Numbers: {cached_data['total_key_numbers']}")
                        print(f"   ⚠️ Uncertainties: {cached_data['total_uncertainties']}")
                        print(f"\n💡 No ingestion needed - data already processed!")
                        return
            else:
                year = current_year
                break
        
        if not year:
            # If no year found and cache checks passed, use current year
            year = current_year

    print(f"   📅 Final Year: {year}")

    # Check cache first (unless forced or cache check skipped)
    if not args.force and not args.skip_cache_check:
        print(f"\n🧠 Checking intelligent cache for {ticker} {filing_type} {year}...")
        
        # Get comprehensive status
        cache_status = pipeline_cache.get_processing_status(ticker, filing_type, year)
        
        if cache_status["can_skip_ingestion"]:
            print(f"\n✅ Complete data already exists!")
            
            # Show cached data summary
            if cache_status["summaries_data"]:
                summary = pipeline_cache.get_cached_data_summary(ticker, filing_type, year)
                if summary:
                    print(f"   📊 Cached Summaries Found:")
                    print(f"     - Sections: {summary['sections_count']}")
                    print(f"     - Total bullets: {summary['total_bullets']}")
                    print(f"     - Total key numbers: {summary['total_key_numbers']}")
                    print(f"     - Total uncertainties: {summary['total_uncertainties']}")
                    print(f"   💡 No API call needed - returning cached data!")
                    return
        
        elif cache_status["raw_filing_exists"]:
            print(f"   📁 Raw filing exists - skipping API fetch")
            print(f"   💡 Will use existing raw data for processing")
        else:
            print(f"   📥 No cached data found - will fetch from API")

    # 1) Fetch filing data using Option 2 (targeted section extraction)
    enabled_sections = get_enabled_sections()
    print(f"\n📋 [{run_id}] Fetching targeted sections: {enabled_sections}")
    
    try:
        # Option 2: Request specific sections only
        filing_data = client.get_filing_items(ticker, filing_type, year, items=enabled_sections)
        print(f"   ✅ Successfully fetched {len(filing_data.get('items', []))} sections from API")
    except Exception as e:
        # Try previous year as fallback
        if year == datetime.now(timezone.utc).year:
            try:
                print(f"   ⚠️ Current year failed, trying previous year...")
                year = year - 1
                filing_data = client.get_filing_items(ticker, filing_type, year, items=enabled_sections)
                print(f"   ✅ Successfully fetched from {year}")
            except Exception as e2:
                print(f"   ❌ Both current and previous year failed: {e2}")
                raise
        else:
            print(f"   ❌ API fetch failed: {e}")
            raise

    # 2) Extract metadata and validate
    metadata = client.get_filing_metadata(filing_data)
    if not metadata.get("ticker"):
        raise RuntimeError("Invalid filing data - no ticker found")

    actual_year = metadata["year"]
    period_end_date = metadata.get("period_end_date")
    filed_date = metadata.get("filed_date")
    
    print(f"📊 [{run_id}] Filing metadata:")
    print(f"   - Ticker: {metadata['ticker']}")
    print(f"   - Type: {metadata['filing_type']}")
    print(f"   - Year: {actual_year}")
    print(f"   - Filed: {filed_date}")
    print(f"   - Items: {metadata['items_count']}")

    # 3) Extract content and build FilingRaw
    content = client.extract_filing_content(filing_data)
    if not content or len(content) < 100:
        raise RuntimeError("Filing content too short or empty")

    # Build filing items
    filing_items = []
    for item_data in filing_data.get("items", []):
        section_number = item_data.get("number", "")
        section_title = item_data.get("title", "")
        section_text = item_data.get("text", "")
        
        filing_items.append(FilingItem(
            item=section_number or section_title or "",
            content=section_text or "",
            section_type=section_number or None
        ))
        
        print(f"   📄 {section_number} - {section_title} ({len(section_text):,} chars)")

    # Create filing hash
    filing_hash = sha256_text(content.lower().strip())
    
    fr = FilingRaw(
        ticker=ticker,
        filing_type=filing_type,
        year=actual_year,
        period_end_date=period_end_date,
        filed_date=filed_date,
        provider="financialdatasets-api",
        retrieved_at=datetime.now(timezone.utc),
        company_name=metadata.get("company_name"),
        cik=metadata.get("cik"),
        items=filing_items,
        hash=filing_hash,
        meta={
            "api_base": os.getenv("FINANCIAL_DATASETS_API_BASE"),
            "items_requested": len(filing_items),
            "content_length": len(content),
            "extraction_method": "option_2_targeted",
            "sections_requested": enabled_sections,
            "sections_received": [item.get("number", "") for item in filing_data.get("items", [])],
            "s3_enhanced": True,
            "cache_status": "fresh_fetch"
        }
    )

    # 4) Generate file paths
    f_path = filing_path(ticker, filing_type, actual_year, filed_date)
    f_txt_path = filing_txt_path(ticker, filing_type, actual_year, filed_date)
    m_path = legacy_manifest_path(ticker, filing_type=filing_type, year=actual_year, filed_date=filed_date)
    li_path = latest_index_path(ticker)

    # 5) Store files (respecting S3 configuration)
    print(f"\n💾 [{run_id}] Storing filing data...")
    
    if storage.exists(f_path) and not args.force:
        print(f"   ⏩ Files exist (skipping write): {f_path}")
    else:
        # Write JSON (full API response)
        storage.write_json(json.loads(fr.model_dump_json()), f_path)
        print(f"   ✅ JSON: {f_path}")
        
        # Write TXT (normalized plain text)
        storage.write_file(content, f_txt_path)
        print(f"   ✅ TXT: {f_txt_path}")

    # Get file sizes
    if storage.use_s3:
        filing_bytes = len(json.dumps(json.loads(fr.model_dump_json())))
        filing_txt_bytes = len(content.encode('utf-8'))
    else:
        filing_bytes = os.path.getsize(f_path)
        filing_txt_bytes = os.path.getsize(f_txt_path) if os.path.exists(f_txt_path) else 0

    # 6) Create manifest
    man = Manifest(
        ticker=ticker,
        filing_type=filing_type,
        filing_year=actual_year,
        period_end_date=period_end_date,
        filed_date=filed_date,
        filing_path=f_path,
        filing_bytes=filing_bytes,
        filing_hash=fr.hash,
        items_count=len(filing_items),
        provider=fr.provider,
        news_path=None,
        news_items_total=0,
        news_deduped_total=0,
        warnings=[],
        created_at=datetime.now(timezone.utc),
        ingestion_version="0.3.0-s3",
        run_id=run_id,
        runner="s3-enhanced",
    )
    storage.write_json(json.loads(man.model_dump_json()), m_path)
    print(f"   ✅ Manifest: {m_path}")

    # 7) Update latest index
    idx = LatestIndex(
        ticker=ticker,
        latest_manifest_path=m_path,
        updated_at=datetime.now(timezone.utc),
    )
    storage.write_json(json.loads(idx.model_dump_json()), li_path)
    print(f"   ✅ Index: {li_path}")

    print(f"\n🎉 [{run_id}] Ingestion completed successfully!")
    print(f"   📊 Data: {filing_bytes:,} bytes")
    print(f"   📋 Items: {len(filing_items)}")
    print(f"   📄 Type: {filing_type}")
    print(f"   📅 Year: {actual_year}")
    print(f"\n💡 Next: Run processing pipeline to generate summaries!")


if __name__ == "__main__":
    main()