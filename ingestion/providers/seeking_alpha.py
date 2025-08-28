import httpx, os
from typing import Any, Dict, Optional, Tuple
from ..utils.time import to_utc
from bs4 import BeautifulSoup

class SeekingAlphaClient:
    def __init__(self, timeout_s: float = 20.0):
        self.rapidapi_base = os.getenv("RAPIDAPI_BASE", "https://seeking-alpha21.p.rapidapi.com")
        self.rapidapi_host = os.getenv("RAPIDAPI_HOST", "seeking-alpha21.p.rapidapi.com")
        self.rapidapi_key = os.getenv("RAPIDAPI_KEY")
        
        if not self.rapidapi_key:
            raise RuntimeError("RAPIDAPI_KEY not set")
            
        self.headers = {
            "x-rapidapi-host": self.rapidapi_host,
            "x-rapidapi-key": self.rapidapi_key,
        }
        
        self.client = httpx.Client(timeout=timeout_s, headers=self.headers, base_url=self.rapidapi_base)

    def list_transcripts(self, symbol: str) -> Dict[str, Any]:
        resp = self.client.get("/transcripts/list", params={"symbol": symbol.upper()})
        resp.raise_for_status()
        return resp.json()

    def get_details(self, transcript_id: str) -> Dict[str, Any]:
        resp = self.client.get("/transcripts/details", params={"id": transcript_id})
        resp.raise_for_status()
        return resp.json()

    def pick_latest_transcript(self, list_payload: Dict[str, Any]) -> Tuple[str, str, str, str]:
        """
        Returns: (transcript_id, publishOn, title, article_self_path)
        """
        data = list_payload.get("data", [])
        if not data:
            raise RuntimeError("No transcripts in list payload")

        # Sort by publishOn desc
        def pub_on(it):
            return it.get("attributes", {}).get("publishOn") or ""
        sorted_items = sorted(data, key=pub_on, reverse=True)

        chosen = None
        for item in sorted_items:
            attrs = item.get("attributes", {})
            if attrs.get("isPaywalled") is True:
                continue
            if item.get("type") != "transcript":
                continue
            chosen = item
            break
        if chosen is None:
            chosen = sorted_items[0]

        tid = chosen["id"]
        publish_on = chosen["attributes"]["publishOn"]
        title = chosen["attributes"].get("title", "")
        self_path = chosen.get("links", {}).get("self", "")
        return tid, publish_on, title, self_path

def html_to_text_preserve_paragraphs(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    # Replace <br> with newline
    for br in soup.find_all("br"):
        br.replace_with("\n")
    # Convert block elements to paragraphs
    paras = []
    for el in soup.find_all(["p", "h1","h2","h3","h4","h5","h6","li"]):
        txt = el.get_text(" ", strip=True)
        if txt:
            paras.append(txt)
    # Fallback: whole doc text if we didn't capture anything
    if not paras:
        body = soup.get_text("\n", strip=True)
        return body
    return "\n\n".join(paras)

def split_sections_simple(text: str):
    """Try to split transcript into basic sections; fall back to one."""
    lowered = text.lower()
    labels = [("Prepared Remarks", "prepared"), ("Question-and-Answer Session", "qna"), ("Q&A", "qna")]
    idxs = []
    for label, _ in labels:
        i = lowered.find(label.lower())
        if i != -1:
            idxs.append((i, label))
    if not idxs:
        return [{"label": "Full Transcript", "text": text}]
    idxs.sort()
    chunks = []
    for j, (start, label) in enumerate(idxs):
        end = idxs[j+1][0] if j+1 < len(idxs) else len(text)
        chunks.append({"label": label, "text": text[start:end].strip()})
    return chunks
