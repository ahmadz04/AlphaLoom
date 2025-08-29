#!/usr/bin/env python3
"""
Section Processing Configuration

This file controls which SEC filing sections are processed by the AI summarization pipeline.
Modify the ENABLED_SECTIONS list to add or remove sections as needed.
"""

# Default sections to process (can be overridden by environment variables or command line args)
ENABLED_SECTIONS = [
    "Item 1A",   # Risk Factors  
    "Item 7",    # Management's Discussion and Analysis
]

# Full list of possible sections for reference
# Uncomment any of these to add them to processing:
AVAILABLE_SECTIONS = {
    "Item 1": "Business Overview",
    "Item 1A": "Risk Factors",
    "Item 1B": "Unresolved Staff Comments",
    "Item 2": "Properties", 
    "Item 3": "Legal Proceedings",
    "Item 4": "Mine Safety Disclosures",
    "Item 5": "Market for Registrant's Common Equity",
    "Item 6": "Selected Financial Data",
    "Item 7": "Management's Discussion and Analysis",
    "Item 7A": "Quantitative and Qualitative Disclosures About Market Risk",
    "Item 8": "Financial Statements and Supplementary Data",
    "Item 9": "Changes in and Disagreements with Accountants",
    "Item 9A": "Controls and Procedures",
    "Item 9B": "Other Information",
    "Item 10": "Directors, Executive Officers and Corporate Governance",
    "Item 11": "Executive Compensation",
    "Item 12": "Security Ownership of Certain Beneficial Owners",
    "Item 13": "Certain Relationships and Related Transactions",
    "Item 14": "Principal Accounting Fees and Services",
    "Item 15": "Exhibits and Financial Statement Schedules"
}

def get_enabled_sections():
    """
    Get the list of sections that should be processed.
    
    Returns:
        list: Section names to process
    """
    return ENABLED_SECTIONS.copy()

def add_section(section_name):
    """
    Add a section to the enabled sections list.
    
    Args:
        section_name (str): Section name to add (e.g., "Item 8")
    """
    if section_name not in ENABLED_SECTIONS:
        ENABLED_SECTIONS.append(section_name)

def remove_section(section_name):
    """
    Remove a section from the enabled sections list.
    
    Args:
        section_name (str): Section name to remove
    """
    if section_name in ENABLED_SECTIONS:
        ENABLED_SECTIONS.remove(section_name)

def get_section_description(section_name):
    """
    Get the description for a section.
    
    Args:
        section_name (str): Section name
        
    Returns:
        str: Section description or "Unknown Section" if not found
    """
    return AVAILABLE_SECTIONS.get(section_name, "Unknown Section")