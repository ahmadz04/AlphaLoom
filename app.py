#!/usr/bin/env python3
"""
AlphaLoom - SEC Filing Analysis
AI-powered analysis of company SEC filings made simple.
"""

import gradio as gr
import subprocess
import sys
import json
import os
from pathlib import Path
from datetime import datetime
import tempfile
import traceback
from dotenv import load_dotenv
from config.sections_config import get_enabled_sections

# Load environment variables
load_dotenv('config/.env')

def run_command(cmd, description, cwd=None, env=None):
    """Run a command with simple progress display"""
    try:        
        process = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=cwd,
            env=env,  # Pass environment variables
            bufsize=1,
            universal_newlines=True
        )
        
        output_lines = []
        for line in iter(process.stdout.readline, ''):
            if line:
                output_lines.append(line.strip())
        
        process.wait()
        
        if process.returncode == 0:
            return True, '\n'.join(output_lines)
        else:
            return False, '\n'.join(output_lines)
            
    except Exception as e:
        return False, str(e)


def load_results(ticker, filing_type, year):
    """Load analysis results using hybrid storage"""
    try:
        from ingestion.storage.hybrid import HybridStorage
        storage = HybridStorage()
        
        summaries_path = f"data/processed/{ticker}/{filing_type}/{year}/summaries.json"
        if storage.exists(summaries_path):
            summaries = storage.read_json(summaries_path)
            return summaries
        return None
    except Exception as e:
        print(f"Error loading results: {e}")
        return None


def get_section_title(section_name, section_alias):
    """Convert technical section names to user-friendly titles for frontend display"""
    title_map = {
        "Item 1": "Summary of Business",
        "Item 1A": "Summary of Risk Factors", 
        "Item 1B": "📝 Unresolved Staff Comments",
        "Item 2": "🏗️ Properties",
        "Item 3": "⚖️ Legal Proceedings",
        "Item 4": "🗳️ Corporate Governance",
        "Item 5": "📈 Stock Information",
        "Item 6": "📊 Financial Highlights",
        "Item 7": "💰 Financial Performance & Management Analysis",
        "Item 7A": "📉 Market Risk Analysis",
        "Item 8": "📋 Financial Statements",
        "Item 9": "🔍 Controls & Procedures",
        "Item 9A": "🛡️ Internal Controls",
        "Item 9B": "📄 Other Information",
        "Item 10": "👥 Directors & Officers",
        "Item 11": "💵 Executive Compensation",
        "Item 12": "📊 Stock Ownership",
        "Item 13": "🤝 Related Transactions",
        "Item 14": "👨‍💼 Principal Accountant",
        "Item 15": "📎 Exhibits & Financial Statement Schedules"
    }
    
    return title_map.get(section_name, f"{section_name} - {section_alias}")


def format_summaries(summaries, ticker):
    """Format analysis results for display"""
    if not summaries or 'sections' not in summaries:
        return "No analysis results available yet."
    
    # Get company name and year
    company_names = {
        "AAPL": "Apple Inc.",
        "MSFT": "Microsoft Corp.", 
        "NVDA": "NVIDIA Corp.",
        "TSLA": "Tesla Inc."
    }
    company_name = company_names.get(ticker, ticker)
    year = summaries.get('year', 'Unknown')
    
    output = f"# 📋 {company_name} - {year} Annual Report Analysis\n\n"
    output += "*Clear, jargon-free summaries of key business information*\n\n"
    
    # Show when this analysis was generated
    if summaries.get('sections') and summaries['sections'][0].get('created_at'):
        created_at = summaries['sections'][0]['created_at']
        try:
            dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            output += f"📅 Analysis generated: {dt.strftime('%B %d, %Y at %I:%M %p UTC')}\n\n"
        except:
            output += f"📅 Analysis generated: {created_at}\n\n"
    
    output += "---\n\n"
    
    # Filter out sections with no meaningful content
    sections_with_content = [
        section for section in summaries['sections'] 
        if (section.get('bullets') or section.get('key_numbers') or section.get('uncertainties'))
    ]
    
    if not sections_with_content:
        return "⏳ Analysis is complete, but summaries are still being generated. This may take a few minutes."
    
    for section in sections_with_content:
        section_name = section.get('section_name', 'Unknown Section')
        title = get_section_title(section_name, section.get('section_alias', ''))
        
        output += f"## {title}\n\n"
        
        # Key points (bullets)
        bullets = section.get('bullets', [])
        if bullets:
            output += "### What You Need to Know:\n\n"
            for i, bullet in enumerate(bullets[:8], 1):  # Limit to 8 most important
                clean_bullet = bullet.get('text', '') if isinstance(bullet, dict) else str(bullet)
                if clean_bullet:
                    output += f"**{i}.** {clean_bullet}\n\n"
        
        # Key numbers
        numbers = section.get('key_numbers', [])
        if numbers:
            output += "### Important Numbers:\n\n"
            for number in numbers[:6]:  # Limit to 6 most important
                clean_number = number.get('text', '') if isinstance(number, dict) else str(number)
                if clean_number:
                    output += f"💰 {clean_number}\n\n"
        
        # Risks and uncertainties
        uncertainties = section.get('uncertainties', [])
        if uncertainties:
            output += "### Potential Challenges:\n\n"
            for uncertainty in uncertainties[:6]:  # Limit to 6 most important
                clean_uncertainty = uncertainty.get('text', '') if isinstance(uncertainty, dict) else str(uncertainty)
                if clean_uncertainty:
                    output += f"⚠️ {clean_uncertainty}\n\n"
        
        # Add context if no content
        if not bullets and not numbers and not uncertainties:
            output += "*This section is currently being analyzed. Summary will appear once processing is complete.*\n\n"
        
        output += "---\n\n"
    
    return output


def analyze_filing(ticker, year, use_async, progress=gr.Progress()):
    """Main analysis function"""
    try:
        company_names = {"AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "NVIDIA", "TSLA": "Tesla"}
        company_name = company_names.get(ticker, ticker)
        filing_type = "10-K"
        
        progress(0.0, desc="Starting analysis...")
        
        # Step 1: Fetch filing data
        progress(0.2, desc="📥 Downloading annual report from SEC database...")
        
        ingest_cmd = f"python -m ingestion.run_filings_s3 --ticker {ticker} --filing-type {filing_type} --year {year}"
        success, output = run_command(ingest_cmd, f"Fetching {ticker} {filing_type} {year}")
        
        if not success:
            return "❌ Unable to download the annual report. Please check if the filing exists for this year.", None
        
        # Step 2: Check if we need sectionization (Option 2 bypass)
        progress(0.4, desc="📋 Processing document structure...")
        
        # Import hybrid storage to check file existence properly
        from ingestion.storage.hybrid import HybridStorage
        storage = HybridStorage()
        
        txt_path = f"data/raw/filings/{ticker}/{year}_{filing_type}_{year}_filing.txt"
        if not storage.exists(txt_path):
            return "❌ Downloaded file is not available for processing.", None
        
        output_dir = f"data/processed/{ticker}/{filing_type}/{year}"
        storage.mkdirs_for(f"{output_dir}/dummy")  # Ensure directory exists (for local storage)
        
        # Check if we're using Option 2 (targeted extraction)
        # Option 2 provides pre-structured sections, so we can bypass sectionizer
        json_path = f"data/raw/filings/{ticker}/{year}_{filing_type}_{year}_filing.json"
        skip_sectionizer = False
        
        if storage.exists(json_path):
            try:
                filing_data = storage.read_json(json_path)
                # Check if this is Option 2 structured data
                if (filing_data.get('meta', {}).get('extraction_method') == 'option_2_targeted' and 
                    len(filing_data.get('items', [])) <= 3):  # Small number indicates targeted extraction
                    progress(0.5, desc="🚀 Using pre-structured sections from Option 2 API")
                    skip_sectionizer = True
            except:
                pass
        
        if not skip_sectionizer:
            # Traditional sectionization for Option 1 or fallback
            sectionize_cmd = (f"python processing/sectionize.py "
                             f"--ticker {ticker} --form {filing_type} --year {year} "
                             f"--input-text {txt_path} --out-dir {output_dir}")
            
            success, output = run_command(sectionize_cmd, "Processing document structure")
            
            if not success:
                return "❌ Unable to process the document structure.", None
        else:
            # Create minimal sections.json and chunks.json for Option 2 structured data
            progress(0.5, desc="✅ Creating structured data from Option 2 response")
            try:
                filing_data = storage.read_json(json_path)
                
                # Create sections.json with proper format matching sectionizer output
                sections_data = {
                    "ticker": ticker.upper(),
                    "form": filing_type,
                    "year": year,
                    "source_text": txt_path,
                    "warnings": [],
                    "sections": []
                }
                chunks_data = {"paragraphs": []}
                
                current_pos = 0
                for idx, item in enumerate(filing_data.get('items', [])):
                    section_raw = item.get('item', f'Item {idx+1}')  # Raw section name from API
                    section_content = item.get('content', '')
                    
                    # Normalize section names using position-based logic (more reliable than text parsing)
                    # Since we request Item 1 and Item 1A specifically, we know the order
                    if idx == 0:  # First requested item is always Item 1 (Business)
                        section_number = 'Item 1'
                        section_alias = 'Business'
                    elif idx == 1:  # Second requested item is always Item 1A (Risk Factors)  
                        section_number = 'Item 1A'
                        section_alias = 'Risk Factors'
                    # Fallback to text-based parsing for other sections
                    elif 'Item 1A' in section_raw or 'Item 1a' in section_raw:
                        section_number = 'Item 1A'  
                        section_alias = 'Risk Factors'
                    elif 'Item 1' in section_raw:
                        section_number = 'Item 1'
                        section_alias = 'Business'
                    elif section_raw.startswith('Item'):
                        section_number = section_raw.split()[0] + ' ' + section_raw.split()[1]  # e.g., "Item 7"
                        section_alias = section_raw.split()[1] if len(section_raw.split()) > 1 else section_raw
                    else:
                        section_number = f'Item {idx+1}'
                        section_alias = section_raw[:30]
                    
                    # Add to sections.json with proper format
                    sections_data["sections"].append({
                        "name": section_number,
                        "alias": section_alias,
                        "start": current_pos,
                        "end": current_pos + len(section_content) if idx < len(filing_data.get('items', [])) - 1 else None
                    })
                    current_pos += len(section_content)
                    
                    # Split content into paragraphs for chunks.json - use multiple splitting strategies
                    # First try double newlines, then single newlines, then sentences
                    paragraphs = []
                    if '\n\n' in section_content:
                        paragraphs = section_content.split('\n\n')
                    elif '\n' in section_content:
                        paragraphs = section_content.split('\n')
                    else:
                        # Split by sentences for very long continuous text
                        sentences = section_content.replace('. ', '.\n').split('\n')
                        paragraphs = sentences
                    
                    para_counter = 0
                    for paragraph in paragraphs:
                        paragraph = paragraph.strip()
                        if paragraph and len(paragraph) > 30:  # Only include substantial content
                            # Create section alias for span IDs
                            if section_number == 'Item 1':
                                span_prefix = 'biz'
                            elif section_number == 'Item 1A': 
                                span_prefix = 'risks'
                            else:
                                span_prefix = f'sec{idx}'
                                
                            chunks_data["paragraphs"].append({
                                "span_id": f"{span_prefix}::p{para_counter:03d}",
                                "section": section_number,
                                "text": paragraph,
                                "start_pos": 0,  # Not needed for Option 2
                                "end_pos": len(paragraph)
                            })
                            para_counter += 1
                
                # Write sections.json and chunks.json using hybrid storage
                sections_path = f"{output_dir}/sections.json"
                chunks_path = f"{output_dir}/chunks.json"
                
                storage.write_json(sections_data, sections_path)
                storage.write_json(chunks_data, chunks_path)
                
            except Exception as e:
                return f"❌ Failed to create structured data from Option 2: {e}", None
        
        # Step 3: AI Analysis
        progress(0.6, desc="🤖 Starting AI analysis...")
        
        # Get sections from configuration
        all_sections = get_enabled_sections()
        sections_str = " ".join([f'"{s}"' for s in all_sections])
        
        # Set environment variable for the subprocess
        env = os.environ.copy()
        env['OPENAI_API_KEY'] = os.getenv('OPENAI_API_KEY')
        
        if not env['OPENAI_API_KEY']:
            return "❌ OpenAI API key not configured. Please set OPENAI_API_KEY environment variable.", None
        
        # Use optimized runner with parallel processing and batch caching
        if use_async:
            progress(0.8, desc="🚀 Using async processing for maximum speed...")
            summarize_cmd = (f"python -m processing.summarize.runner_async "
                           f"{ticker} {filing_type} {year} --sections {sections_str} --max-concurrent 8")
        else:
            progress(0.8, desc="🤖 Running AI analysis...")
            summarize_cmd = (f"python -m processing.summarize.runner "
                           f"{ticker} {filing_type} {year} --sections {sections_str}")
        
        # Run the command synchronously
        success, output = run_command(summarize_cmd, "AI Analysis", env=env)
        
        if not success:
            if "OPENAI_API_KEY" in output:
                return "❌ OpenAI API key error. Please check your OPENAI_API_KEY environment variable.", None
            else:
                return f"❌ Processing failed: {output}", None
        
        progress(1.0, desc="✅ Analysis completed successfully!")
        
        # Load and return results
        summaries = load_results(ticker, filing_type, year)
        if summaries:
            # Check if summaries actually have content
            has_content = any(
                section.get('bullets') or section.get('key_numbers') or section.get('uncertainties')
                for section in summaries.get('sections', [])
            )
            
            if has_content:
                formatted_output = format_summaries(summaries, ticker)
                return "🎉 Analysis completed successfully!", formatted_output
            else:
                error_msg = "⚠️ Processing completed but no meaningful summaries were generated. This might be due to:\n"
                error_msg += "• OpenAI API key not configured properly\n"
                error_msg += "• Network connectivity issues\n" 
                error_msg += "• Selected sections contain very little analyzable content"
                
                # Show API key warnings from the file
                for section in summaries.get('sections', []):
                    if section.get('warnings'):
                        error_msg += "\n\nAPI Key Issues Found:\n"
                        for warning in section['warnings'][:3]:  # Show first 3 warnings
                            if 'API key' in warning or 'api_key' in warning:
                                error_msg += f"• {warning}\n"
                        break
                return error_msg, None
        else:
            return "❌ Failed to load summaries. Please try running the analysis again.", None
        
    except Exception as e:
        return f"❌ An unexpected error occurred during analysis: {str(e)}", None


def check_existing_results(ticker, year):
    """Check for existing analysis results"""
    try:
        filing_type = "10-K"
        summaries = load_results(ticker, filing_type, year)
        
        if summaries:
            # Check if summaries actually have content
            has_content = any(
                section.get('bullets') or section.get('key_numbers') or section.get('uncertainties')
                for section in summaries.get('sections', [])
            )
            
            if has_content:
                formatted_output = format_summaries(summaries, ticker)
                return "📋 Previous analysis found. Displaying cached results:", formatted_output
            else:
                return f"Previous analysis found for {ticker} {year} but summaries are still being generated.", None
        else:
            return f"No previous analysis found for {ticker} {year}. Click 'Analyze' to start analysis.", None
    except Exception as e:
        return f"❌ Error loading existing results: {str(e)}", None


def get_system_status():
    """Get system status information"""
    api_key = os.getenv('FINANCIAL_DATASETS_API_KEY')
    openai_key = os.getenv('OPENAI_API_KEY')
    
    enabled_sections = get_enabled_sections()
    section_descriptions = {
        "Item 1": "Business Overview",
        "Item 1A": "Risk Factors", 
        "Item 7": "Management Discussion"
    }
    
    sections_info = "**📋 Sections Analyzed:**\n"
    for section in enabled_sections:
        desc = section_descriptions.get(section, section.replace("Item ", ""))
        sections_info += f"• {desc}\n"
    sections_info += "*Optimized for quick analysis*\n\n"
    
    if api_key and openai_key:
        status_info = "✅ All systems operational\n\n"
    else:
        status_info = "⚠️ Some API keys may need configuration\n"
        if not openai_key:
            status_info += "❌ OpenAI API key missing - required for AI analysis\n"
        status_info += "Contact system administrator if analysis fails\n\n"
    
    return sections_info + status_info


# Create Gradio interface
with gr.Blocks(title="AlphaLoom - Company Filing Analysis", theme=gr.themes.Soft()) as app:
    
    gr.Markdown("# 📈 AlphaLoom")
    gr.Markdown("**AI-powered analysis of company SEC filings**")
    gr.Markdown("Get clear, easy-to-understand summaries of complex financial documents")
    
    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("## Select Company & Year")
            
            ticker = gr.Dropdown(
                choices=[("🍎 Apple Inc.", "AAPL"), ("🖥️ Microsoft Corp.", "MSFT"), 
                        ("🚀 NVIDIA Corp.", "NVDA"), ("🚗 Tesla Inc.", "TSLA")],
                value="AAPL",
                label="📊 Company"
            )
            
            year = gr.Dropdown(
                choices=[("2023", 2023), ("2022", 2022), ("2021", 2021), ("2020", 2020)],
                value=2023,
                label="📅 Filing Year",
                info="Choose the year of the annual report you want to analyze"
            )
            
            gr.Markdown("**ℹ️ What is a 10-K?**")
            gr.Markdown("A comprehensive annual report that provides a detailed overview of a company's business, risks, and financial performance.")
            
            with gr.Accordion("⚙️ Advanced Options", open=False):
                use_async = gr.Checkbox(
                    label="🚀 Use Async Processing", 
                    value=False,
                    info="Enable async processing for maximum speed (experimental)"
                )
                
            with gr.Accordion("⚙️ System Status", open=False):
                status_output = gr.Markdown(value=get_system_status())
        
        with gr.Column(scale=2):
            gr.Markdown("## Analysis Results")
            
            analyze_btn = gr.Button("📊 Analyze Annual Report", variant="primary", size="lg")
            status_msg = gr.Textbox(label="Status", interactive=False, visible=True)
            results_output = gr.Markdown(value="Select a company and year, then click 'Analyze' to start analysis.")
    
    # Event handlers
    def on_inputs_change(ticker_val, year_val):
        status, results = check_existing_results(ticker_val, int(year_val))
        if results:
            return status, results
        else:
            return status, "Select a company and year, then click 'Analyze' to start analysis."
    
    # Update results when inputs change
    for input_component in [ticker, year]:
        input_component.change(
            fn=on_inputs_change,
            inputs=[ticker, year],
            outputs=[status_msg, results_output]
        )
    
    # Analyze button click
    analyze_btn.click(
        fn=analyze_filing,
        inputs=[ticker, year, use_async],
        outputs=[status_msg, results_output]
    )
    
    gr.Markdown("---")
    gr.Markdown("**AlphaLoom** makes complex financial documents easy to understand")

if __name__ == "__main__":
    # Create necessary directories
    os.makedirs("data/raw/filings", exist_ok=True)
    os.makedirs("data/processed", exist_ok=True)
    os.makedirs("data/cache/summaries", exist_ok=True)
    
    app.launch(server_name="0.0.0.0", server_port=7860, share=False)