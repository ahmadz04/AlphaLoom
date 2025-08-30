#!/usr/bin/env python3
"""
AlphaLoom Terminal Application
AI-powered analysis of company SEC filings via command line interface
"""

import os
import sys
import time
import subprocess
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv('config/.env')

# Add project root to Python path
sys.path.append('.')

from config.sections_config import get_enabled_sections

def get_user_input():
    """Get user selection for company and year"""
    companies = [
        ("AAPL", "🍎 Apple Inc."),
        ("MSFT", "💻 Microsoft Corp."),
        ("NVDA", "🚀 NVIDIA Corp."),
        ("TSLA", "🚗 Tesla Inc.")
    ]
    
    print("\nAvailable Companies:")
    for i, (ticker, name) in enumerate(companies, 1):
        print(f"{i}. {name}")
    
    while True:
        try:
            choice = input("\nSelect company (1-4): ").strip()
            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(companies):
                ticker, company_name = companies[choice_idx]
                print(f"Selected: {company_name}")
                break
            else:
                print("❌ Please select a number between 1 and 4")
        except (ValueError, KeyboardInterrupt):
            print("\n👋 Goodbye!")
            sys.exit(0)
    
    while True:
        try:
            year_input = input("\nEnter filing year (2020-2025) [default: 2023]: ").strip()
            year = int(year_input) if year_input else 2023
            
            if 2020 <= year <= 2025:
                print(f"Selected year: {year}")
                return ticker, year
            else:
                print("❌ Please enter a year between 2020 and 2025")
        except (ValueError, KeyboardInterrupt):
            print("\n👋 Goodbye!")
            sys.exit(0)

def check_existing_analysis(ticker, filing_type, year):
    """Check if analysis already exists"""
    summaries_path = f"data/processed/{ticker}/{filing_type}/{year}/summaries.json"
    
    print("🔍 Checking for existing analysis...")
    print()
    
    if os.path.exists(summaries_path):
        try:
            with open(summaries_path, 'r') as f:
                summaries = json.load(f)
            
            # Check if analysis has actual content
            if summaries and any(section.get('bullets') or section.get('key_numbers') or section.get('uncertainties') 
                               for section in summaries.get('sections', [])):
                return summaries
        except:
            pass
    
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

def display_summaries(summaries, ticker):
    """Display analysis results in a user-friendly format"""
    if not summaries or 'sections' not in summaries:
        print("❌ No analysis results to display.")
        return
    
    # Get company name
    company_names = {
        "AAPL": "Apple Inc.",
        "MSFT": "Microsoft Corp.", 
        "NVDA": "NVIDIA Corp.",
        "TSLA": "Tesla Inc."
    }
    company_name = company_names.get(ticker, ticker)
    year = summaries.get('year', 'Unknown')
    
    print()
    print("=" * 80)
    print(f"📋 {company_name} - {year} Annual Report Analysis")
    print("Clear, jargon-free summaries of key business information")
    print("=" * 80)
    
    # Show timestamp
    if summaries.get('sections') and summaries['sections'][0].get('created_at'):
        from datetime import datetime
        timestamp = summaries['sections'][0]['created_at']
        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        print(f"📅 Analysis generated: {dt.strftime('%B %d, %Y at %I:%M %p')} UTC")
        print()
    
    for i, section in enumerate(summaries['sections'], 1):
        section_name = section.get('section_name', 'Unknown Section')
        section_alias = section.get('section_alias', '')
        
        # Get user-friendly title
        display_title = get_section_title(section_name, section_alias)
        
        print("-" * 80)
        print(f"SECTION {i}: {display_title}")
        print("-" * 80)
        
        # Display bullet points
        bullets = section.get('bullets', [])
        if bullets:
            print("\n📌 WHAT YOU NEED TO KNOW:")
            for j, bullet in enumerate(bullets, 1):
                text = bullet.get('text', '').strip()
                if text:
                    print(f"  {j}. {text}")
        
        # Display key numbers
        key_numbers = section.get('key_numbers', [])
        if key_numbers:
            print("\n💰 IMPORTANT NUMBERS:")
            for number in key_numbers:
                text = number.get('text', '').strip()
                if text:
                    print(f"  • {text}")
        
        # Display uncertainties/challenges
        uncertainties = section.get('uncertainties', [])
        if uncertainties:
            print("\n⚠️ POTENTIAL CHALLENGES:")
            for uncertainty in uncertainties:
                text = uncertainty.get('text', '').strip()
                if text:
                    print(f"  • {text}")
        
        print()

def run_command(cmd, description, env=None):
    """Run a shell command and return success status and output"""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, 
            timeout=300, env=env  # 5 minute timeout
        )
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return False, "Command timed out after 5 minutes"
    except Exception as e:
        return False, str(e)

def analyze_filing(ticker, filing_type="10-K", year=2023):
    """Main analysis pipeline with Option 2 integration and improved polling"""
    try:
        print(f"\n🚀 Starting analysis for {ticker} {year} {filing_type}...")
        
        # Step 1: Fetch filing data
        ingest_cmd = f"python -m ingestion.run_filings --ticker {ticker} --filing-type {filing_type} --year {year}"
        success, output = run_command(ingest_cmd, f"Downloading {ticker} {filing_type} {year}")
        
        if not success:
            print("❌ Unable to download the annual report. Please check if the filing exists for this year.")
            return
        
        # Step 2: Check if we need sectionization (Option 2 bypass)
        txt_path = f"data/raw/filings/{ticker}/{year}_{filing_type}_{year}_filing.txt"
        if not os.path.exists(txt_path):
            print("❌ Downloaded file is not available for processing.")
            return
        
        output_dir = f"data/processed/{ticker}/{filing_type}/{year}"
        os.makedirs(output_dir, exist_ok=True)
        
        # Check if we're using Option 2 (targeted extraction)
        json_path = f"data/raw/filings/{ticker}/{year}_{filing_type}_{year}_filing.json"
        skip_sectionizer = False
        
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r') as f:
                    filing_data = json.load(f)
                # Check if this is Option 2 structured data
                if (filing_data.get('meta', {}).get('extraction_method') == 'option_2_targeted' and 
                    len(filing_data.get('items', [])) <= 3):
                    print("🚀 Using Option 2 structured data - bypassing sectionizer")
                    skip_sectionizer = True
            except:
                pass
        
        if not skip_sectionizer:
            # Traditional sectionization for Option 1 or fallback
            sectionize_cmd = (f"python processing/sectionize.py "
                             f"--ticker {ticker} --form {filing_type} --year {year} "
                             f"--input-text {txt_path} --out-dir {output_dir}")
            
            success, _ = run_command(sectionize_cmd, "Processing document structure")
            
            if not success:
                print("❌ Unable to process the document structure.")
                return
        else:
            # Create minimal sections.json and chunks.json for Option 2 structured data
            print("✅ Creating sections.json from Option 2 structured data")
            try:
                with open(json_path, 'r') as f:
                    filing_data = json.load(f)
                
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
                para_counter = 0
                
                for idx, item in enumerate(filing_data.get('items', [])):
                    section_raw = item.get('item', f'Item {idx+1}')
                    section_content = item.get('content', '')
                    
                    # Normalize section names using position-based logic
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
                        section_number = section_raw.split()[0] + ' ' + section_raw.split()[1]
                        section_alias = section_raw.split()[1] if len(section_raw.split()) > 1 else section_raw
                    else:
                        section_number = f'Item {idx+1}'
                        section_alias = section_raw[:30]
                        
                    print(f"[DEBUG] Mapped '{section_raw[:50]}...' -> '{section_number}' ({section_alias})")
                    
                    # Add to sections.json with proper format
                    sections_data["sections"].append({
                        "name": section_number,
                        "alias": section_alias,
                        "start": current_pos,
                        "end": current_pos + len(section_content) if idx < len(filing_data.get('items', [])) - 1 else None
                    })
                    current_pos += len(section_content)
                    
                    # Split content into paragraphs for chunks.json - use multiple splitting strategies
                    paragraphs = []
                    if '\n\n' in section_content:
                        paragraphs = section_content.split('\n\n')
                    elif '\n' in section_content:
                        paragraphs = section_content.split('\n')
                    else:
                        # Split by sentences for very long continuous text
                        sentences = section_content.replace('. ', '.\n').split('\n')
                        paragraphs = sentences
                    
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
                
                # Write sections.json and chunks.json
                sections_path = f"{output_dir}/sections.json"
                chunks_path = f"{output_dir}/chunks.json"
                
                with open(sections_path, 'w') as f:
                    json.dump(sections_data, f, indent=2)
                
                with open(chunks_path, 'w') as f:
                    json.dump(chunks_data, f, indent=2)
                
                print(f"✅ Created {sections_path} and {chunks_path} from Option 2 data")
                
            except Exception as e:
                print(f"❌ Failed to create sections.json from Option 2 data: {e}")
                return
        
        # Step 3: AI Analysis with improved polling
        all_sections = get_enabled_sections()
        sections_str = " ".join([f'"{s}"' for s in all_sections])
        
        # Set environment variables for the subprocess
        env = os.environ.copy()
        env['OPENAI_API_KEY'] = os.getenv('OPENAI_API_KEY')
        
        print(f"🤖 Starting AI analysis for sections: {all_sections}")
        
        # Use standard optimized version
        summarize_cmd = (f"python -m processing.summarize.runner "
                        f"{ticker} {filing_type} {year} --sections {sections_str}")
        
        # Start processing
        process = subprocess.Popen(
            summarize_cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env
        )
        
        print("⚡ AI analysis running... This may take 30-60 seconds...")
        
        # Poll for completion with reduced noise
        max_wait_time = 120
        start_time = time.time()
        last_status_time = 0
        
        while time.time() - start_time < max_wait_time:
            # Check if process is still running
            poll_result = process.poll()
            
            elapsed_time = time.time() - start_time
            
            # Show status every 15 seconds instead of 10 to reduce noise
            if elapsed_time > 15 and elapsed_time - last_status_time >= 15:
                print(f"⏳ Still processing... {int(elapsed_time)}s elapsed")
                last_status_time = elapsed_time
            
            # Check for results file directly (without verbose load_results)
            summaries_path = f"data/processed/{ticker}/{filing_type}/{year}/summaries.json"
            if os.path.exists(summaries_path):
                try:
                    with open(summaries_path, 'r') as f:
                        temp_summaries = json.load(f)
                    
                    # Check if analysis is complete (has actual content)
                    if temp_summaries and any(section.get('bullets') or section.get('key_numbers') or section.get('uncertainties') 
                                            for section in temp_summaries.get('sections', [])):
                        print("✅ Analysis completed! Terminating subprocess...")
                        process.terminate()
                        try:
                            process.communicate(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                        break
                except:
                    pass  # File might be incomplete, continue waiting
            
            if poll_result is not None:  # Process finished
                stdout, stderr = process.communicate()
                if poll_result != 0 or stderr:
                    print(f"❌ Processing failed:")
                    print(f"Return code: {poll_result}")
                    print(f"STDOUT: {stdout}")
                    print(f"STDERR: {stderr}")
                    return
                break
                
            time.sleep(5)  # Check every 5 seconds instead of 2
        
        elapsed_total = time.time() - start_time
        print(f"⏱️ Total processing time: {elapsed_total:.1f} seconds")
        
        # Load and display final results
        print("\n🔄 Loading final results...")
        time.sleep(1)  # Brief delay to ensure file I/O is complete
        
        # Load results quietly (without debug messages) 
        summaries_path = f"data/processed/{ticker}/{filing_type}/{year}/summaries.json"
        final_summaries = None
        
        for retry in range(3):
            try:
                with open(summaries_path, 'r') as f:
                    final_summaries = json.load(f)
                if final_summaries:
                    break
            except FileNotFoundError:
                if retry < 2:  # Only show retry message if not the last attempt
                    print(f"⏳ File not found, retry {retry + 1}/3...")
                time.sleep(1)
            except Exception as e:
                if retry < 2:
                    print(f"⏳ Error loading file, retry {retry + 1}/3: {e}")
                time.sleep(1)
        
        if final_summaries:
            sections_with_content = [
                section for section in final_summaries['sections'] 
                if (section.get('bullets') or section.get('key_numbers') or section.get('uncertainties'))
            ]
            
            if sections_with_content:
                print("🎉 Analysis completed successfully!")
                display_summaries(final_summaries, ticker)
            else:
                print("⚠️ Analysis completed but no significant content found.")
                print("This could be due to:")
                print("• OpenAI API key issues")
                print("• Network connectivity problems")
                print("• Selected sections contain very little analyzable content")
        else:
            print("❌ Failed to load summaries after multiple retries.")
            print("Check if the summaries.json file was created properly.")
            
    except Exception as e:
        print(f"❌ An unexpected error occurred: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")

def main():
    """Main application entry point"""
    print("=" * 60)
    print("📈 AlphaLoom Terminal - SEC Filing Analysis")
    print("AI-powered analysis of company SEC filings")
    print("=" * 60)
    
    # Check API keys
    api_key = os.getenv('FINANCIAL_DATASETS_API_KEY')
    openai_key = os.getenv('OPENAI_API_KEY')
    
    if api_key and openai_key:
        print("✅ API keys configured")
    else:
        print("⚠️ Missing API keys:")
        if not api_key:
            print("❌ FINANCIAL_DATASETS_API_KEY not found")
        if not openai_key:
            print("❌ OPENAI_API_KEY not found")
        print("Please check your config/.env file")
        return
    
    try:
        # Get user input
        ticker, year = get_user_input()
        filing_type = "10-K"
        
        # Check for existing analysis
        existing_summaries = check_existing_analysis(ticker, filing_type, year)
        if existing_summaries:
            print(f"✅ Found existing analysis for {ticker} {year}")
            display_summaries(existing_summaries, ticker)
            return
        
        # Run new analysis
        analyze_filing(ticker, filing_type, year)
        
    except KeyboardInterrupt:
        print("\n\n👋 Analysis cancelled. Goodbye!")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")

if __name__ == "__main__":
    main()