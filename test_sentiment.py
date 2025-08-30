#!/usr/bin/env python3
"""
Quick test script for FinBERT sentiment analysis functionality
"""

import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

def test_sentiment_analyzer():
    """Test the FinBERT analyzer with sample text"""
    print("🧪 Testing FinBERT Sentiment Analysis")
    print("=" * 50)
    
    # Sample Risk Factors text (negative sentiment expected)
    sample_text = """
    The company faces significant risks that could materially adversely affect our business, 
    financial condition, and results of operations. These risks include intense competition, 
    regulatory changes, supply chain disruptions, cybersecurity threats, and market volatility.
    
    Our business is subject to numerous risks and uncertainties, including those described below, 
    that could cause actual results to differ materially from expectations. The trading price 
    of our common stock could decline due to any of these risks, and investors may lose part or 
    all of their investment.
    
    We operate in highly competitive markets and face significant competition from larger, 
    more established companies with greater resources. This competitive pressure may result 
    in reduced market share and declining profitability.
    """
    
    try:
        # Test the convenience function
        from processing.sentiment.finbert_analyzer import analyze_risk_factors_sentiment
        
        print("📝 Analyzing sample Risk Factors text...")
        print(f"📏 Text length: {len(sample_text)} characters")
        print("\n" + "─" * 50)
        
        result = analyze_risk_factors_sentiment(sample_text)
        
        print("✅ Analysis Results:")
        print(f"   Sentiment: {result['sentiment_label']}")
        print(f"   Overall Score: {result['overall_score']:.3f} (-1 to +1)")
        print(f"   Confidence: {result['confidence']:.1%}")
        print(f"   Model: {result['model_used']}")
        print(f"   Chunks Analyzed: {result['chunks_analyzed']}")
        print(f"   Device: {result['device_used']}")
        
        print(f"\n📊 Probability Breakdown:")
        print(f"   🔴 Negative: {result['negative']:.1%}")
        print(f"   🟡 Neutral:  {result['neutral']:.1%}")
        print(f"   🟢 Positive: {result['positive']:.1%}")
        
        # Test with a positive example
        print("\n" + "=" * 50)
        print("📝 Testing with positive text...")
        
        positive_text = """
        The company has strong fundamentals and excellent growth prospects. Our robust 
        financial position, innovative products, and experienced management team position 
        us well for future success. We have successfully navigated market challenges 
        and continue to deliver strong results for our shareholders.
        """
        
        positive_result = analyze_risk_factors_sentiment(positive_text)
        
        print("✅ Positive Text Results:")
        print(f"   Sentiment: {positive_result['sentiment_label']}")
        print(f"   Overall Score: {positive_result['overall_score']:.3f}")
        print(f"   🔴 Negative: {positive_result['negative']:.1%} | "
              f"🟡 Neutral: {positive_result['neutral']:.1%} | "
              f"🟢 Positive: {positive_result['positive']:.1%}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_schema_integration():
    """Test the schema integration"""
    print("\n" + "=" * 50)
    print("🧪 Testing Schema Integration")
    print("=" * 50)
    
    try:
        from processing.summarize.schema import SentimentAnalysis, SummariesSection
        
        # Create sample sentiment data
        sentiment = SentimentAnalysis(
            negative=0.7,
            neutral=0.2,
            positive=0.1,
            overall_score=-0.6,
            sentiment_label="Negative",
            confidence=0.7,
            model_used="yiyanghkust/finbert-tone",
            chunks_analyzed=5
        )
        
        print("✅ SentimentAnalysis schema validation passed")
        print(f"   Model dump: {sentiment.model_dump()}")
        
        return True
        
    except Exception as e:
        print(f"❌ Schema integration error: {e}")
        return False

if __name__ == "__main__":
    print("🚀 AlphaLoom FinBERT Integration Test Suite")
    print("=" * 60)
    
    # Check dependencies first
    try:
        import torch
        import transformers
        print(f"✅ PyTorch version: {torch.__version__}")
        print(f"✅ Transformers version: {transformers.__version__}")
        print(f"✅ CUDA available: {torch.cuda.is_available()}")
        print()
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("💡 Run: pip install -r requirements.txt")
        sys.exit(1)
    
    # Run tests
    sentiment_test = test_sentiment_analyzer()
    schema_test = test_schema_integration()
    
    print("\n" + "=" * 60)
    print("📋 Test Summary:")
    print(f"   Sentiment Analysis: {'✅ PASS' if sentiment_test else '❌ FAIL'}")
    print(f"   Schema Integration: {'✅ PASS' if schema_test else '❌ FAIL'}")
    
    if sentiment_test and schema_test:
        print("\n🎉 All tests passed! FinBERT integration is ready.")
        print("\n💡 Next steps:")
        print("   1. Install dependencies: pip install -r requirements.txt")
        print("   2. Run analysis pipeline with Risk Factors section enabled")
        print("   3. Check frontend for sentiment analysis display")
    else:
        print("\n❌ Some tests failed. Please check the errors above.")
        sys.exit(1)