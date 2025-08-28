import os, argparse, json
from datetime import datetime, timezone
from dotenv import load_dotenv
from .storage.local import LocalStorage
from .utils.paths import filing_path, filing_txt_path, legacy_manifest_path, latest_index_path
from .utils.time import utc_now_iso
from .utils.hashing import sha256_text
from .providers.financial_datasets import FinancialDatasetsClient
from .utils.models import FilingRaw, FilingItem, Manifest, LatestIndex

def main():
    load_dotenv(dotenv_path=os.path.join("config", ".env"), override=True)

    parser = argparse.ArgumentParser(description="Alpha Loom - Ingest latest SEC filing")
    parser.add_argument("--ticker", default=os.getenv("DEFAULT_TICKER", "AAPL"))
    parser.add_argument("--filing-type", default=os.getenv("DEFAULT_FILING_TYPE", "10-K"), 
                       choices=["10-K", "10-Q"], help="Filing type to fetch")
    parser.add_argument("--year", type=int, help="Specific year (defaults to current/previous year)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    args = parser.parse_args()

    ticker = args.ticker.upper()
    filing_type = args.filing_type
    year = args.year
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    print(f"[{run_id}] start ticker={ticker} filing_type={filing_type} year={year or 'auto'}")

    storage = LocalStorage()
    client = FinancialDatasetsClient()

    # 1) Fetch filing data
    try:
        if year:
            filing_data = client.get_filing_items(ticker, filing_type, year)
        else:
            filing_data = client.get_latest_filing(ticker, filing_type)
    except Exception as e:
        print(f"[{run_id}] error fetching filing: {e}")
        raise

    # 2) Extract metadata and validate
    metadata = client.get_filing_metadata(filing_data)
    if not metadata.get("ticker"):
        raise RuntimeError("Invalid filing data - no ticker found")

    actual_year = metadata["year"]
    period_end_date = metadata.get("period_end_date")
    filed_date = metadata.get("filed_date")
    
    print(f"[{run_id}] fetched filing ticker={metadata['ticker']} type={metadata['filing_type']} "
          f"year={actual_year} filed={filed_date} items={metadata['items_count']}")

    # 3) Extract content and build FilingRaw
    content = client.extract_filing_content(filing_data)
    if not content or len(content) < 100:
        raise RuntimeError("Filing content too short or empty")

    # Build filing items - API uses 'title' and 'text' fields
    filing_items = []
    for item_data in filing_data.get("items", []):
        filing_items.append(FilingItem(
            item=item_data.get("title", item_data.get("item", "")) or "",
            content=item_data.get("text", item_data.get("content", "")) or "",
            section_type=str(item_data.get("section_type", item_data.get("number", ""))) or None
        ))

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
            "content_length": len(content)
        }
    )

    # 4) Generate file paths
    f_path = filing_path(ticker, filing_type, actual_year, filed_date)  # JSON file
    f_txt_path = filing_txt_path(ticker, filing_type, actual_year, filed_date)  # TXT file
    m_path = legacy_manifest_path(ticker, filing_type=filing_type, year=actual_year, filed_date=filed_date)
    li_path = latest_index_path(ticker)

    # 5) Store both JSON and TXT files in raw zone
    if storage.exists(f_path) and not args.force:
        print(f"[{run_id}] filing exists (skip). paths={f_path}, {f_txt_path}")
    else:
        # Write JSON (full API response)
        storage.write_json(json.loads(fr.model_dump_json()), f_path)
        print(f"[{run_id}] wrote filing JSON path={f_path}")
        
        # Write TXT (normalized plain text with paragraph breaks)
        with open(f_txt_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"[{run_id}] wrote filing TXT path={f_txt_path}")

    # Get file sizes
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
        ingestion_version="0.2.0",
        run_id=run_id,
        runner="local",
    )
    storage.write_json(json.loads(man.model_dump_json()), m_path)
    print(f"[{run_id}] wrote manifest path={m_path}")

    # 7) Update latest index
    idx = LatestIndex(
        ticker=ticker,
        latest_manifest_path=m_path,
        updated_at=datetime.now(timezone.utc),
    )
    storage.write_json(json.loads(idx.model_dump_json()), li_path)
    print(f"[{run_id}] updated latest index path={li_path}")

    print(f"[{run_id}] success bytes={filing_bytes} items={len(filing_items)} "
          f"type={filing_type} year={actual_year}")

if __name__ == "__main__":
    main()