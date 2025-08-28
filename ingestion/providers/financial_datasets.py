import httpx, os
from typing import Any, Dict, Optional, List
from datetime import datetime

class FinancialDatasetsClient:
    def __init__(self, timeout_s: float = 30.0):
        self.api_base = os.getenv("FINANCIAL_DATASETS_API_BASE", "https://api.financialdatasets.ai")
        self.api_key = os.getenv("FINANCIAL_DATASETS_API_KEY")
        
        if not self.api_key:
            raise RuntimeError("FINANCIAL_DATASETS_API_KEY not set")
            
        self.headers = {
            "X-API-KEY": self.api_key,
        }
        
        self.client = httpx.Client(
            timeout=timeout_s, 
            headers=self.headers, 
            base_url=self.api_base,
            follow_redirects=True
        )

    def get_filing_items(self, ticker: str, filing_type: str = "10-K", year: int = None, 
                        items: List[str] = None) -> Dict[str, Any]:
        """
        Get SEC filing items for a specific ticker.
        
        Args:
            ticker: Stock ticker symbol
            filing_type: Type of filing (10-K, 10-Q)
            year: Filing year (defaults to current year)
            items: Specific items to extract (optional)
        
        Returns:
            API response containing filing items
        """
        if year is None:
            year = datetime.now().year
            
        params = {
            "ticker": ticker.upper(),
            "filing_type": filing_type,
            "year": year,
        }
        
        if items:
            for item in items:
                params[f"item"] = item
                
        resp = self.client.get("/filings/items/", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_latest_filing(self, ticker: str, filing_type: str = "10-K") -> Dict[str, Any]:
        """
        Get the most recent filing for a ticker.
        Tries current year first, then previous year if not found.
        """
        current_year = datetime.now().year
        
        try:
            return self.get_filing_items(ticker, filing_type, current_year)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # Try previous year
                return self.get_filing_items(ticker, filing_type, current_year - 1)
            raise

    def extract_filing_content(self, filing_data: Dict[str, Any]) -> str:
        """
        Extract and combine text content from filing items.
        """
        items = filing_data.get("items", [])
        content_parts = []
        
        for item in items:
            # API uses 'title' and 'text' instead of 'item' and 'content'
            item_name = item.get("title", item.get("item", ""))
            item_content = item.get("text", item.get("content", ""))
            
            if item_content:
                content_parts.append(f"=== {item_name} ===\n\n{item_content}")
        
        return "\n\n".join(content_parts)

    def get_filing_metadata(self, filing_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract metadata from filing response.
        """
        return {
            "ticker": filing_data.get("ticker"),
            "filing_type": filing_data.get("filing_type"),
            "year": filing_data.get("year"),
            "period_end_date": filing_data.get("period_end_date"),
            "filed_date": filing_data.get("filed_date"),
            "items_count": len(filing_data.get("items", [])),
            "cik": filing_data.get("cik"),
            "company_name": filing_data.get("company_name"),
        }