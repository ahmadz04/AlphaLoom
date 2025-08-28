"""
Summarization processing module for SEC filing analysis.

This module provides schema definitions, CLI tools, and utilities for generating
structured summaries of SEC filing sections using LLMs.
"""

from .schema import (
    VERSION,
    Bullet,
    SummariesSection, 
    SummariesFile,
    now_iso,
    to_json_schema
)

from .validate_inputs import (
    build_span_index,
    normalize_section_name,
    validate_requested_sections
)

from .chunk_checks import (
    check_chunk_quality,
)

from .cache import (
    cache_path,
    read_cache,
    write_cache,
    cache_stats,
    clear_cache
)

from .prompt import (
    common_schema_dict,
    build_messages_for_gemini,
    validate_response_citations
)

try:
    from .llm import (
        call_gemini,
        configure_gemini_api,
        test_gemini_connection
    )
    from .section_runner import (
        summarize_section,
        load_section_data,
        group_paragraphs_into_chunks
    )
    _llm_available = True
except ImportError:
    _llm_available = False

__all__ = [
    "VERSION",
    "Bullet",
    "SummariesSection",
    "SummariesFile", 
    "now_iso",
    "to_json_schema",
    "build_span_index",
    "normalize_section_name", 
    "validate_requested_sections",
    "check_chunk_quality",
    "cache_path",
    "read_cache",
    "write_cache",
    "cache_stats",
    "clear_cache",
    "common_schema_dict",
    "build_messages_for_gemini",
    "validate_response_citations"
]

# Add LLM functions if available
if _llm_available:
    __all__.extend([
        "call_gemini",
        "configure_gemini_api", 
        "test_gemini_connection",
        "summarize_section",
        "load_section_data",
        "group_paragraphs_into_chunks"
    ])