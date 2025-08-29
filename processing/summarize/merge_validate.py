"""
Merge, dedupe, cap 7, validate citations for LLM section summaries.

This module provides functions to:
- Merge: concatenate bullets, key_numbers, and uncertainties from all chunks
- Dedupe: remove near-duplicates and union their span_ids  
- Cap: trim to 7 bullets (milestone limit)
- Validate: drop items with no valid span_id and record warnings
"""

import re
from typing import Dict, List, Set, Tuple

try:
    from rapidfuzz import fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    import difflib
    RAPIDFUZZ_AVAILABLE = False


def normalize_text(s: str) -> str:
    """Normalize text by lowercasing, stripping, and collapsing spaces."""
    if not s:
        return ""
    return re.sub(r'\s+', ' ', s.lower().strip())


def dedupe_items(items: List[Dict], threshold: float = 0.88) -> List[Dict]:
    """
    Remove near-duplicate items using token set ratio comparison.
    Keep first occurrence; union span_ids from duplicates.
    
    Args:
        items: List of dicts with 'text' and 'span_ids' keys
        threshold: Similarity threshold (0.0-1.0) for considering items duplicates
        
    Returns:
        List of deduplicated items with merged span_ids
    """
    if not items:
        return []
    
    result = []
    
    for item in items:
        if not item.get('text'):
            continue
            
        normalized_text = normalize_text(item['text'])
        is_duplicate = False
        
        for existing in result:
            existing_normalized = normalize_text(existing['text'])
            
            if RAPIDFUZZ_AVAILABLE:
                similarity = fuzz.token_set_ratio(normalized_text, existing_normalized) / 100.0
            else:
                # Fallback to difflib
                similarity = difflib.SequenceMatcher(None, normalized_text, existing_normalized).ratio()
            
            if similarity >= threshold:
                # Union span_ids from duplicate into existing item
                existing_span_ids = set(existing.get('span_ids', []))
                item_span_ids = set(item.get('span_ids', []))
                existing['span_ids'] = list(existing_span_ids | item_span_ids)
                is_duplicate = True
                break
        
        if not is_duplicate:
            # Make a copy to avoid modifying original
            new_item = item.copy()
            new_item['span_ids'] = list(set(item.get('span_ids', [])))
            result.append(new_item)
    
    return result


def cap7(items: List[Dict]) -> List[Dict]:
    """Return first 7 items from the list."""
    return items[:7]


def filter_invalid_citations(items: List[Dict], valid_span_ids: Set[str]) -> Tuple[List[Dict], List[str]]:
    """
    Filter out items with no valid span_ids and ensure each kept item has ≥1 valid span.
    
    Args:
        items: List of items with span_ids
        valid_span_ids: Set of valid span IDs for the section
        
    Returns:
        Tuple of (kept_items, warnings)
    """
    kept = []
    warnings = []
    
    for item in items:
        item_span_ids = set(item.get('span_ids', []))
        valid_spans_for_item = item_span_ids & valid_span_ids
        
        if not valid_spans_for_item:
            # No valid spans - drop this item
            warnings.append(f"Dropped item with no valid citations: '{item.get('text', 'Unknown')[:50]}...'")
            continue
        
        # Keep item but filter to only valid span_ids
        filtered_item = item.copy()
        filtered_item['span_ids'] = list(valid_spans_for_item)
        kept.append(filtered_item)
    
    return kept, warnings


def merge_outputs(per_chunk_outputs: List[Dict], valid_span_ids: Set[str]) -> Dict:
    """
    Merge per-chunk outputs into final section summary.
    
    Concatenates by list type, dedupes, filters invalid citations, caps at 7,
    and aggregates warnings.
    
    Args:
        per_chunk_outputs: List of chunk outputs, each with bullets, key_numbers, uncertainties
        valid_span_ids: Set of valid span IDs for the section
        
    Returns:
        Dict with final {bullets, key_numbers, uncertainties, warnings}
    """
    # Concatenate all items by type
    all_bullets = []
    all_key_numbers = []
    all_uncertainties = []
    all_warnings = []
    
    for chunk_output in per_chunk_outputs:
        bullets = chunk_output.get('bullets', [])
        key_numbers = chunk_output.get('key_numbers', [])
        uncertainties = chunk_output.get('uncertainties', [])
        warnings = chunk_output.get('warnings', [])
        
        # Convert span_id (singular) to span_ids (plural) for compatibility
        def normalize_items(items):
            normalized = []
            for i, item in enumerate(items):
                if isinstance(item, dict):
                    normalized_item = item.copy()
                    # Convert span_id to span_ids if needed
                    if 'span_id' in normalized_item and 'span_ids' not in normalized_item:
                        normalized_item['span_ids'] = [normalized_item['span_id']]
                        del normalized_item['span_id']
                    # Ensure span_ids is always a list
                    if 'span_ids' not in normalized_item:
                        normalized_item['span_ids'] = []
                    elif not isinstance(normalized_item['span_ids'], list):
                        normalized_item['span_ids'] = [normalized_item['span_ids']]
                    normalized.append(normalized_item)
                elif isinstance(item, str):
                    # Handle legacy string format - convert to expected dict format
                    # Try to extract span_id if it's in the format "text (span::id)"
                    import re
                    match = re.search(r'\(([^)]+)\)\.?$', item)
                    if match:
                        text = item[:match.start()].strip()
                        span_id = match.group(1)
                        normalized_item = {
                            'text': text,
                            'span_ids': [span_id]
                        }
                    else:
                        normalized_item = {
                            'text': item,
                            'span_ids': []
                        }
                    normalized.append(normalized_item)
                else:
                    normalized.append(item)
            return normalized
        
        all_bullets.extend(normalize_items(bullets))
        all_key_numbers.extend(normalize_items(key_numbers))
        all_uncertainties.extend(normalize_items(uncertainties))
        all_warnings.extend(warnings)
    
    # Process each type: dedupe, filter invalid citations, cap at 7
    final_bullets, bullet_warnings = filter_invalid_citations(
        cap7(dedupe_items(all_bullets)), valid_span_ids
    )
    
    final_key_numbers, key_number_warnings = filter_invalid_citations(
        cap7(dedupe_items(all_key_numbers)), valid_span_ids
    )
    
    final_uncertainties, uncertainty_warnings = filter_invalid_citations(
        cap7(dedupe_items(all_uncertainties)), valid_span_ids
    )
    
    # Aggregate all warnings
    final_warnings = (
        all_warnings + 
        bullet_warnings + 
        key_number_warnings + 
        uncertainty_warnings
    )
    
    return {
        'bullets': final_bullets,
        'key_numbers': final_key_numbers,
        'uncertainties': final_uncertainties,
        'warnings': final_warnings
    }