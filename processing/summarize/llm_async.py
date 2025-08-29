#!/usr/bin/env python3
"""
Async OpenAI API client for SEC filing summarization with rate limiting.

This module provides async OpenAI API calls with proper rate limiting,
retry logic, and connection pooling for maximum performance.
"""

import asyncio
import os
import sys
import time
from typing import Dict, List
import aiohttp

try:
    import ujson as json
except ImportError:
    import json

try:
    from .prompt import common_schema_dict
except ImportError:
    # For standalone testing
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from summarize.prompt import common_schema_dict


class AsyncOpenAIClient:
    """
    Async OpenAI client with rate limiting and connection pooling.
    """
    
    def __init__(self, api_key: str = None, max_requests_per_minute: int = 50):
        """
        Initialize async OpenAI client.
        
        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            max_requests_per_minute: Rate limit for API requests
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key not provided and OPENAI_API_KEY not set")
        
        self.max_requests_per_minute = max_requests_per_minute
        self.request_times = []
        self.semaphore = asyncio.Semaphore(max_requests_per_minute // 2)  # Conservative limit
        
        # HTTP session for connection pooling
        self.session = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        connector = aiohttp.TCPConnector(
            limit=100,  # Total connection pool size
            limit_per_host=20,  # Connections per host
            keepalive_timeout=60,
            enable_cleanup_closed=True
        )
        
        timeout = aiohttp.ClientTimeout(total=120, connect=10)
        
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    async def _rate_limit(self):
        """Enforce rate limiting."""
        now = time.time()
        
        # Remove old requests (older than 1 minute)
        self.request_times = [t for t in self.request_times if now - t < 60]
        
        # Check if we need to wait
        if len(self.request_times) >= self.max_requests_per_minute:
            # Wait until the oldest request is > 1 minute old
            wait_time = 60 - (now - self.request_times[0]) + 0.1
            if wait_time > 0:
                await asyncio.sleep(wait_time)
        
        # Record this request
        self.request_times.append(now)
    
    async def call_openai_async(
        self,
        messages: Dict,
        model: str = "gpt-4o-mini",
        max_output_tokens: int = 1200,
        temperature: float = 0.2,
        max_retries: int = 3
    ) -> Dict:
        """
        Make async OpenAI API call with rate limiting and retries.
        
        Args:
            messages: Dictionary with 'system_text' and 'user_text' keys
            model: OpenAI model name to use
            max_output_tokens: Maximum tokens in response
            temperature: Response randomness (0.0-1.0)
            max_retries: Maximum number of retries
            
        Returns:
            Dictionary with bullets, key_numbers, uncertainties, warnings arrays
        """
        async with self.semaphore:
            await self._rate_limit()
            
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": messages["system_text"]},
                    {"role": "user", "content": messages["user_text"]}
                ],
                "response_format": {"type": "json_object"},
                "temperature": temperature,
                "max_tokens": max_output_tokens
            }
            
            for attempt in range(max_retries + 1):
                try:
                    async with self.session.post(
                        'https://api.openai.com/v1/chat/completions',
                        json=payload
                    ) as response:
                        
                        if response.status == 429:  # Rate limited
                            retry_after = int(response.headers.get('retry-after', 60))
                            print(f"Rate limited, waiting {retry_after}s...", file=sys.stderr)
                            await asyncio.sleep(retry_after)
                            continue
                        
                        if response.status != 200:
                            error_text = await response.text()
                            raise Exception(f"HTTP {response.status}: {error_text}")
                        
                        response_data = await response.json()
                        
                        # Extract content
                        if not response_data.get('choices') or not response_data['choices'][0].get('message', {}).get('content'):
                            if attempt < max_retries:
                                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                                continue
                            raise Exception("Empty response from OpenAI API")
                        
                        content = response_data['choices'][0]['message']['content']
                        parsed_response = json.loads(content)
                        
                        # Validate required fields
                        required_fields = ["bullets", "key_numbers", "uncertainties", "warnings"]
                        for field in required_fields:
                            if field not in parsed_response:
                                parsed_response[field] = []
                        
                        # Ensure warnings is a list
                        if not isinstance(parsed_response["warnings"], list):
                            parsed_response["warnings"] = [str(parsed_response["warnings"])]
                        
                        return parsed_response
                        
                except asyncio.TimeoutError:
                    if attempt < max_retries:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    return self._create_empty_response("Request timeout")
                    
                except json.JSONDecodeError as e:
                    if attempt < max_retries:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    return self._create_empty_response(f"JSON parse error: {e}")
                    
                except Exception as e:
                    error_msg = str(e).lower()
                    retryable_errors = [
                        "rate limit", "quota exceeded", "internal error",
                        "service unavailable", "timeout", "connection error"
                    ]
                    
                    is_retryable = any(retryable in error_msg for retryable in retryable_errors)
                    
                    if is_retryable and attempt < max_retries:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    
                    return self._create_empty_response(f"API error: {e}")
            
            return self._create_empty_response("Max retries exceeded")
    
    def _create_empty_response(self, warning_message: str) -> Dict:
        """Create empty response structure with warning for error cases."""
        return {
            "bullets": [],
            "key_numbers": [],
            "uncertainties": [],
            "warnings": [warning_message]
        }


async def batch_call_openai_async(
    messages_list: List[Dict],
    model: str = "gpt-4o-mini",
    max_output_tokens: int = 1200,
    temperature: float = 0.2,
    max_concurrent: int = 10
) -> List[Dict]:
    """
    Make multiple OpenAI API calls concurrently.
    
    Args:
        messages_list: List of message dictionaries
        model: OpenAI model name
        max_output_tokens: Maximum tokens per response
        temperature: Response randomness
        max_concurrent: Maximum concurrent requests
        
    Returns:
        List of response dictionaries in same order as input
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")
    
    async with AsyncOpenAIClient(api_key, max_requests_per_minute=50) as client:
        # Create semaphore for concurrent request limiting
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def process_single_request(messages: Dict, index: int):
            async with semaphore:
                result = await client.call_openai_async(
                    messages, model, max_output_tokens, temperature
                )
                return index, result
        
        # Create tasks for all requests
        tasks = [
            process_single_request(messages, i) 
            for i, messages in enumerate(messages_list)
        ]
        
        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Sort results by original index and extract responses
        sorted_results = [None] * len(messages_list)
        for result in results:
            if isinstance(result, Exception):
                # Handle exceptions
                print(f"Async request failed: {result}", file=sys.stderr)
                continue
            
            index, response = result
            sorted_results[index] = response
        
        # Fill any None results with error responses
        for i, result in enumerate(sorted_results):
            if result is None:
                sorted_results[i] = {
                    "bullets": [],
                    "key_numbers": [],
                    "uncertainties": [],
                    "warnings": [f"Async processing failed for request {i}"]
                }
        
        return sorted_results


async def main():
    """Test async OpenAI functionality."""
    print("=== Async OpenAI API Client Test ===")
    
    # Test single request
    test_messages = {
        "system_text": """You are a financial filings summarizer. Output ONLY valid JSON matching the response schema. Focus on key insights from the provided text. Always include the required fields: bullets, key_numbers, uncertainties, and warnings as arrays.""",
        "user_text": """Please summarize this test content:
        
SECTION METADATA:
- Section: Item 7 (Test)
- Content Hash: test123
- Chunk Index: 0

ALLOWED SPAN IDS:
["test::p001"]

PARAGRAPHS TO ANALYZE:
[{"span_id": "test::p001", "text": "Revenue increased 15% to $100 billion."}]

Output structured JSON with bullets, key_numbers, uncertainties, and warnings arrays."""
    }
    
    async with AsyncOpenAIClient() as client:
        print("Testing single async request...")
        result = await client.call_openai_async(test_messages, temperature=0.1)
        
        print(f"Response received:")
        print(f"- Bullets: {len(result.get('bullets', []))}")
        print(f"- Key numbers: {len(result.get('key_numbers', []))}")
        print(f"- Uncertainties: {len(result.get('uncertainties', []))}")
        print(f"- Warnings: {len(result.get('warnings', []))}")
        
        if result.get("warnings"):
            print(f"Warnings: {result['warnings']}")
    
    # Test batch requests
    print("\nTesting batch async requests...")
    batch_messages = [test_messages] * 3  # 3 identical requests for testing
    
    batch_results = await batch_call_openai_async(
        batch_messages, 
        temperature=0.1,
        max_concurrent=2
    )
    
    print(f"Batch processing complete: {len(batch_results)} responses")
    for i, result in enumerate(batch_results):
        bullet_count = len(result.get("bullets", []))
        warning_count = len(result.get("warnings", []))
        print(f"  Request {i}: {bullet_count} bullets, {warning_count} warnings")
    
    print("\n✅ Async OpenAI API client test completed")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))