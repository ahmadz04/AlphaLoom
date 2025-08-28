import os, argparse, json
from datetime import datetime, timezone
from dotenv import load_dotenv
from .storage.local import LocalStorage
from .utils.paths import transcript_path, manifest_path, latest_index_path
from .utils.time import to_utc, utc_now_iso
from .utils.hashing import sha256_text
from .providers.seeking_alpha import SeekingAlphaClient, html_to_text_preserve_paragraphs, split_sections_simple
from .utils.models import TranscriptRaw, Manifest, LatestIndex

def main():
    load_dotenv(dotenv_path=os.path.join("config", ".env"), override=True)

    parser = argparse.ArgumentParser(description="Alpha Loom - Ingest latest transcript")
    parser.add_argument("--ticker", default=os.getenv("DEFAULT_TICKER", "AAPL"))
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    args = parser.parse_args()

    ticker = args.ticker.upper()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    print(f"[{run_id}] start ticker={ticker}")

    storage = LocalStorage()
    client = SeekingAlphaClient()

    # 1) list → pick latest
    lst = client.list_transcripts(ticker)
    tx_id, publish_on, title, self_path = client.pick_latest_transcript(lst)
    call_dt_utc = to_utc(publish_on)
    print(f"[{run_id}] picked id={tx_id} publishOn={publish_on} utc={call_dt_utc.isoformat()} title='{title}'")

    # 2) details → get content
    det = client.get_details(tx_id)
    det_data = det.get("data", {}) or {}
    attrs = det_data.get("attributes", {}) or {}

    if not attrs.get("isTranscript", False):
        raise RuntimeError("Details payload is not a transcript")
    content_html = attrs.get("content", "") or ""
    canonical_url = det_data.get("links", {}).get("canonical", "")

    text = html_to_text_preserve_paragraphs(content_html)
    if not text or len(text) < 1000:
        raise RuntimeError("Transcript content too short or empty")

    sections = split_sections_simple(text)

    # 3) build TranscriptRaw (normalize)
    transcript_hash = sha256_text(text.lower().strip())
    tr = TranscriptRaw(
        ticker=ticker,
        call_id=str(tx_id),
        call_datetime=call_dt_utc,
        provider="seekingalpha-rapidapi",
        retrieved_at=datetime.now(timezone.utc),
        title=title,
        canonical_url=canonical_url,
        sections=[{"label": s["label"], "text": s["text"]} for s in sections],
        hash=transcript_hash,
        meta={
            "source_publish_on": publish_on,
            "article_self_path": self_path,
            "rapidapi_base": os.getenv("RAPIDAPI_BASE"),
            "rapidapi_host": os.getenv("RAPIDAPI_HOST"),
        },
    )

    # 4) paths
    t_path = transcript_path(ticker, tr.call_id, tr.call_datetime)
    m_path = manifest_path(ticker, tr.call_id, tr.call_datetime)
    li_path = latest_index_path(ticker)

    # 5) idempotency: skip if exists and not --force
    if storage.exists(t_path) and not args.force:
        print(f"[{run_id}] transcript exists (skip). path={t_path}")
    else:
        storage.write_json(json.loads(tr.model_dump_json()), t_path)
        print(f"[{run_id}] wrote transcript path={t_path}")

    # file size bytes
    transcript_bytes = os.path.getsize(t_path)

    # 6) manifest
    man = Manifest(
        ticker=ticker,
        call_id=tr.call_id,
        call_datetime=tr.call_datetime,
        provider=tr.provider,
        transcript_path=t_path,
        transcript_bytes=transcript_bytes,
        transcript_hash=tr.hash,
        news_path=None,
        news_items_total=0,
        news_deduped_total=0,
        warnings=[],
        created_at=datetime.now(timezone.utc),
        ingestion_version="0.1.0",
        run_id=run_id,
        runner="local",
    )
    storage.write_json(json.loads(man.model_dump_json()), m_path)
    print(f"[{run_id}] wrote manifest path={m_path}")

    # 7) latest index
    idx = LatestIndex(
        ticker=ticker,
        latest_manifest_path=m_path,
        updated_at=datetime.now(timezone.utc),
    )
    storage.write_json(json.loads(idx.model_dump_json()), li_path)
    print(f"[{run_id}] updated latest index path={li_path}")

    print(f"[{run_id}] success bytes={transcript_bytes} sections={len(tr.sections)}")

if __name__ == "__main__":
    main()
