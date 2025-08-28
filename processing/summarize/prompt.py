#!/usr/bin/env python3
"""
Prompt builder for Gemini LLM SEC filing summarization.

This module creates structured prompts for Gemini to generate JSON summaries
with strict citation validation and response formatting. The explicit "allowed span"
list ensures all citations reference valid paragraph spans from the source section.
"""

import json
from typing import Dict, List


def common_schema_dict() -> Dict:
    """
    Return JSON Schema for structured summary responses.
    
    This schema enforces the required structure for all summary outputs:
    - bullets, key_numbers, uncertainties: Arrays of objects with text and span_ids
    - warnings: Array of strings for issues/rejections
    
    Returns:
        JSON Schema dictionary for validation
    """
    return {
        "type": "object",
        "properties": {
            "bullets": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "span_ids": {
                            "type": "array", 
                            "items": {"type": "string"}
                        }
                    },
                    "required": ["text", "span_ids"]
                }
            },
            "key_numbers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "span_ids": {
                            "type": "array",
                            "items": {"type": "string"}
                        }
                    },
                    "required": ["text", "span_ids"]
                }
            },
            "uncertainties": {
                "type": "array", 
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "span_ids": {
                            "type": "array",
                            "items": {"type": "string"}
                        }
                    },
                    "required": ["text", "span_ids"]
                }
            },
            "warnings": {
                "type": "array",
                "items": {"type": "string"}
            }
        },
        "required": ["bullets", "key_numbers", "uncertainties", "warnings"]
    }


def build_messages_for_gemini(
    section_name: str,
    section_alias: str, 
    section_hash: str,
    chunk_index: int,
    paragraphs: List[Dict],
    allowed_span_ids: List[str]
) -> Dict:
    """
    Build system and user messages for Gemini LLM summarization.
    
    Args:
        section_name: SEC section name (e.g., "Item 7", "Item 1A")
        section_alias: Human-readable section title  
        section_hash: Hash of section content for tracking
        chunk_index: Index of this chunk within the section
        paragraphs: List of paragraph dicts with 'span_id' and 'text' keys
        allowed_span_ids: List of valid span IDs that can be cited
        
    Returns:
        Dictionary with 'system_text' and 'user_text' keys for Gemini API
    """
    
    # Build system instruction with clear rules
    system_text = """You are a financial filings summarizer specialized in SEC documents. Your task is to analyze paragraph chunks from SEC filings and generate structured JSON summaries.

CRITICAL RULES:
1. Output ONLY valid JSON matching the response schema - no other text
2. NEVER fabricate information - only use content from provided paragraphs
3. Citations MUST use span_ids from the allowed list - reject invalid references
4. Maximum 7 bullets per section (bullets array) - prioritize most important points
5. Put any problems, rejections, or issues into the warnings array
6. Be concise and decision-useful for investors
7. Focus on material information affecting business performance and risks

RESPONSE CATEGORIES:
- bullets: Key insights, business developments, performance highlights
- key_numbers: Financial metrics, percentages, monetary amounts with context
- uncertainties: Risks, cautionary statements, forward-looking concerns  
- warnings: Processing issues, citations rejected, content limitations

Remember: Every bullet point MUST cite at least one valid span_id from the allowed list."""

    # Build user message with task details and data
    user_text = f"""Please summarize this SEC filing section chunk:

SECTION METADATA:
- Section: {section_name} ({section_alias})
- Content Hash: {section_hash}
- Chunk Index: {chunk_index}

ALLOWED SPAN IDS (you may ONLY cite these):
{json.dumps(allowed_span_ids, indent=2)}

PARAGRAPHS TO ANALYZE:
{json.dumps(paragraphs, indent=2, ensure_ascii=False)}

TASK: Generate a structured JSON summary following these rules:
- Extract up to 7 key bullet points focusing on material business information
- Identify important financial numbers or metrics with context
- Note any uncertainties, risks, or forward-looking statements
- Each bullet/number/uncertainty MUST cite valid span_ids from the allowed list above
- If you cannot cite a valid span_id for a point, put explanation in warnings instead
- Be concise but informative - focus on investor decision-making value

Output your analysis as valid JSON matching the response schema."""

    return {
        "system_text": system_text,
        "user_text": user_text
    }


def validate_response_citations(response: Dict, allowed_span_ids: List[str]) -> List[str]:
    """
    Validate that all citations in LLM response use allowed span IDs.
    
    Args:
        response: Parsed JSON response from LLM
        allowed_span_ids: List of valid span IDs for this chunk
        
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    allowed_set = set(allowed_span_ids)
    
    # Check each category for citation validity
    for category in ["bullets", "key_numbers", "uncertainties"]:
        items = response.get(category, [])
        
        for i, item in enumerate(items):
            span_ids = item.get("span_ids", [])
            
            # Check if any span IDs are invalid
            invalid_spans = [span_id for span_id in span_ids if span_id not in allowed_set]
            
            if invalid_spans:
                errors.append(
                    f"{category}[{i}] cites invalid span_ids: {invalid_spans}. "
                    f"Only these are allowed: {sorted(allowed_set)}"
                )
            
            # Check if item has at least one citation
            if not span_ids:
                errors.append(f"{category}[{i}] has no span_id citations")
    
    return errors


def create_sample_prompt() -> Dict:
    """
    Create a sample prompt for testing and documentation.
    
    Returns:
        Sample prompt dictionary
    """
    sample_paragraphs = [
        {
            "span_id": "mdna::p005",
            "text": "Net sales increased 15% to $394.3 billion compared to $343.2 billion in the prior year, driven primarily by strong iPhone sales and services growth."
        },
        {
            "span_id": "mdna::p006", 
            "text": "Gross margin improved to 45.8% from 43.3% in the previous year, reflecting favorable product mix and operational efficiencies."
        },
        {
            "span_id": "mdna::p007",
            "text": "However, we continue to face uncertainty from supply chain disruptions and geopolitical tensions that may impact future quarters."
        }
    ]
    
    allowed_spans = ["mdna::p005", "mdna::p006", "mdna::p007"]
    
    return build_messages_for_gemini(
        section_name="Item 7",
        section_alias="Management's Discussion and Analysis",
        section_hash="abc123def456",
        chunk_index=0,
        paragraphs=sample_paragraphs,
        allowed_span_ids=allowed_spans
    )


def main():
    """
    Test prompt building functionality.
    """
    print("=== Gemini Prompt Builder Test ===")
    
    # Test schema generation
    schema = common_schema_dict()
    print("JSON Schema created:")
    print(f"- Required fields: {schema['required']}")
    print(f"- Properties count: {len(schema['properties'])}")
    print()
    
    # Test sample prompt creation
    prompt = create_sample_prompt()
    
    print("=== System Instruction ===")
    print(prompt["system_text"][:200] + "..." if len(prompt["system_text"]) > 200 else prompt["system_text"])
    print()
    
    print("=== User Message (first 300 chars) ===")
    print(prompt["user_text"][:300] + "..." if len(prompt["user_text"]) > 300 else prompt["user_text"])
    print()
    
    # Test response validation
    print("=== Response Validation Test ===")
    
    # Valid response
    valid_response = {
        "bullets": [
            {
                "text": "Net sales increased 15% to $394.3 billion",
                "span_ids": ["mdna::p005"]
            }
        ],
        "key_numbers": [
            {
                "text": "Gross margin: 45.8% (up from 43.3%)", 
                "span_ids": ["mdna::p006"]
            }
        ],
        "uncertainties": [
            {
                "text": "Supply chain and geopolitical risks may impact future performance",
                "span_ids": ["mdna::p007"]
            }
        ],
        "warnings": []
    }
    
    allowed_spans = ["mdna::p005", "mdna::p006", "mdna::p007"]
    errors = validate_response_citations(valid_response, allowed_spans)
    print(f"Valid response errors: {len(errors)}")
    
    # Invalid response
    invalid_response = {
        "bullets": [
            {
                "text": "Revenue grew significantly",
                "span_ids": ["invalid::p999"]  # Invalid span ID
            }
        ],
        "key_numbers": [],
        "uncertainties": [],
        "warnings": []
    }
    
    errors = validate_response_citations(invalid_response, allowed_spans)
    print(f"Invalid response errors: {len(errors)}")
    if errors:
        print(f"Error example: {errors[0]}")
    
    print("\n✅ Prompt builder test completed")
    
    return 0


if __name__ == "__main__":
    main()