#!/usr/bin/env python3
"""
OpenAI API client for SEC filing summarization.

This module provides a clean interface to the OpenAI API with structured JSON
response handling, retry logic, and error resilience. It ensures the rest of
the codebase only deals with clean Python data, not API quirks.
"""

try:
    import ujson as json
except ImportError:
    import json
import os
import sys
import time
from typing import Dict, Optional

try:
    from openai import OpenAI
except ImportError:
    print("Error: openai package not installed. Run: pip install openai", file=sys.stderr)
    sys.exit(1)

try:
    from .prompt import common_schema_dict
except ImportError:
    # For standalone testing
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from summarize.prompt import common_schema_dict


def configure_openai_api() -> bool:
    """
    Configure OpenAI API with API key from environment.
    
    Returns:
        True if configuration successful, False otherwise
    """
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set", file=sys.stderr)
        return False
    
    try:
        # Test the API key by creating a client
        client = OpenAI(api_key=api_key)
        return True
    except Exception as e:
        print(f"Error configuring OpenAI API: {e}", file=sys.stderr)
        return False


def create_empty_response(warning_message: str) -> Dict:
    """
    Create empty response structure with warning for error cases.
    
    Args:
        warning_message: Error or warning message to include
        
    Returns:
        Empty response dict with warning
    """
    return {
        "bullets": [],
        "key_numbers": [],
        "uncertainties": [],
        "warnings": [warning_message]
    }


def call_openai(
    messages: Dict,
    model: str = "gpt-4o-mini",
    max_output_tokens: int = 1200,
    temperature: float = 0.2
) -> Dict:
    """
    Call OpenAI API for structured JSON summarization.
    
    Args:
        messages: Dictionary with 'system_text' and 'user_text' keys
        model: OpenAI model name to use
        max_output_tokens: Maximum tokens in response
        temperature: Response randomness (0.0-1.0)
        
    Returns:
        Dictionary with bullets, key_numbers, uncertainties, warnings arrays.
        On errors, returns empty arrays with error in warnings.
    """
    # Ensure API is configured
    if not configure_openai_api():
        return create_empty_response("Failed to configure OpenAI API - check OPENAI_API_KEY")
    
    # Get response schema
    response_schema = common_schema_dict()
    
    # Retry configuration
    max_retries = 2
    retry_delay = 1.0  # Initial delay in seconds
    
    # Create OpenAI client
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    for attempt in range(max_retries + 1):
        try:
            # Create the completion request
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": messages["system_text"]},
                    {"role": "user", "content": messages["user_text"]}
                ],
                response_format={"type": "json_object"},
                temperature=temperature,
                max_tokens=max_output_tokens
            )
            
            # Check if response has content
            if not response.choices or not response.choices[0].message.content:
                warning_msg = f"Empty response from OpenAI API (attempt {attempt + 1})"
                if attempt == max_retries:
                    return create_empty_response(warning_msg)
                print(f"Warning: {warning_msg}, retrying...", file=sys.stderr)
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
                continue
            
            # Parse JSON response
            try:
                response_text = response.choices[0].message.content
                parsed_response = json.loads(response_text)
                
                # Validate required fields are present
                required_fields = ["bullets", "key_numbers", "uncertainties", "warnings"]
                for field in required_fields:
                    if field not in parsed_response:
                        parsed_response[field] = []
                
                # Ensure warnings is a list
                if not isinstance(parsed_response["warnings"], list):
                    parsed_response["warnings"] = [str(parsed_response["warnings"])]
                
                return parsed_response
                
            except json.JSONDecodeError as e:
                warning_msg = f"JSON parse error (attempt {attempt + 1}): {e}"
                if attempt == max_retries:
                    return create_empty_response(warning_msg)
                print(f"Warning: {warning_msg}, retrying...", file=sys.stderr)
                time.sleep(retry_delay)
                retry_delay *= 2
                continue
                
        except Exception as e:
            # Handle API errors, rate limits, etc.
            error_msg = str(e).lower()
            
            # Check for retryable errors
            retryable_errors = [
                "rate limit",
                "quota exceeded", 
                "internal error",
                "service unavailable",
                "timeout",
                "connection error"
            ]
            
            is_retryable = any(retryable in error_msg for retryable in retryable_errors)
            
            warning_msg = f"OpenAI API error (attempt {attempt + 1}): {e}"
            
            if is_retryable and attempt < max_retries:
                print(f"Warning: {warning_msg}, retrying...", file=sys.stderr)
                time.sleep(retry_delay)
                retry_delay *= 2
                continue
            else:
                return create_empty_response(warning_msg)
    
    # Should not reach here, but handle edge case
    return create_empty_response("Unexpected error in OpenAI API call")


def test_openai_connection() -> bool:
    """
    Test OpenAI API connection with a simple request.
    
    Returns:
        True if connection successful, False otherwise
    """
    if not configure_openai_api():
        return False
    
    try:
        # Simple test messages
        test_messages = {
            "system_text": "You are a test assistant. Output only JSON with the required fields: bullets, key_numbers, uncertainties, and warnings. Each should be an empty array for this test.",
            "user_text": "Return a simple test response with empty arrays for all required fields."
        }
        
        result = call_openai(test_messages, max_output_tokens=100, temperature=0.0)
        
        # Check if we got a proper response structure
        required_fields = ["bullets", "key_numbers", "uncertainties", "warnings"]
        return all(field in result for field in required_fields)
        
    except Exception as e:
        print(f"OpenAI connection test failed: {e}", file=sys.stderr)
        return False


def main():
    """
    Test OpenAI API integration.
    """
    print("=== OpenAI API Client Test ===")
    
    # Test API configuration
    print("Testing API configuration...")
    if configure_openai_api():
        print("✅ API configured successfully")
    else:
        print("❌ API configuration failed")
        return 1
    
    # Test connection
    print("\nTesting API connection...")
    if test_openai_connection():
        print("✅ API connection successful")
    else:
        print("❌ API connection failed")
        return 1
    
    # Test with sample data
    print("\nTesting with sample summarization request...")
    
    sample_messages = {
        "system_text": """You are a financial filings summarizer. Output ONLY valid JSON matching the response schema. Focus on key insights from the provided text. Always include the required fields: bullets, key_numbers, uncertainties, and warnings as arrays.""",
        
        "user_text": """Please summarize this SEC filing section chunk:

SECTION METADATA:
- Section: Item 7 (Management's Discussion and Analysis)
- Content Hash: test123
- Chunk Index: 0

ALLOWED SPAN IDS:
["test::p001", "test::p002"]

PARAGRAPHS TO ANALYZE:
[
  {
    "span_id": "test::p001",
    "text": "Revenue increased 10% to $100 billion driven by strong product sales."
  },
  {
    "span_id": "test::p002", 
    "text": "However, supply chain challenges may impact future performance."
  }
]

Output structured JSON with bullets, key_numbers, uncertainties, and warnings arrays."""
    }
    
    result = call_openai(sample_messages, temperature=0.1, max_output_tokens=500)
    
    print(f"Response received:")
    print(f"- Bullets: {len(result.get('bullets', []))}")
    print(f"- Key numbers: {len(result.get('key_numbers', []))}")
    print(f"- Uncertainties: {len(result.get('uncertainties', []))}")
    print(f"- Warnings: {len(result.get('warnings', []))}")
    
    if result.get("warnings"):
        print(f"Warnings: {result['warnings']}")
    
    # Show sample content if available
    if result.get("bullets"):
        print(f"Sample bullet: {result['bullets'][0].get('text', 'N/A')}")
    
    print("\n✅ OpenAI API client test completed")
    return 0


if __name__ == "__main__":
    sys.exit(main())