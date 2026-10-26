#!/usr/bin/env python3
"""
FinBERT Sentiment Analysis for SEC Filings
Optimized for Risk Factors section analysis
"""

import logging
import os
from typing import Dict, List, Optional
import numpy as np
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import warnings

# Suppress transformer warnings for cleaner output
warnings.filterwarnings("ignore", category=UserWarning, module="transformers")
logging.getLogger("transformers").setLevel(logging.WARNING)


class FinBERTAnalyzer:
    """
    FinBERT-based sentiment analyzer optimized for financial text.
    Uses yiyanghkust/finbert-tone model for sentiment classification.
    """
    
    def __init__(self, model_name: str = "yiyanghkust/finbert-tone", cache_dir: Optional[str] = None):
        """
        Initialize FinBERT analyzer.
        
        Args:
            model_name: HuggingFace model name
            cache_dir: Optional cache directory for model files
        """
        self.model_name = model_name
        self.cache_dir = cache_dir or os.path.join(os.getcwd(), ".cache", "finbert")
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        # Lazy loading - models loaded on first use
        self._tokenizer = None
        self._model = None
        
        # Index -> label mapping, read from the model config on load
        # (finbert-tone uses 0=Neutral, 1=Positive, 2=Negative)
        self._label_map = None
    
    @property
    def tokenizer(self):
        """Lazy load tokenizer"""
        if self._tokenizer is None:
            print(f"Loading FinBERT tokenizer: {self.model_name}")
            self._tokenizer = AutoTokenizer.from_pretrained(
                self.model_name,
                cache_dir=self.cache_dir
            )
        return self._tokenizer
    
    @property  
    def model(self):
        """Lazy load model"""
        if self._model is None:
            print(f"Loading FinBERT model: {self.model_name}")
            self._model = AutoModelForSequenceClassification.from_pretrained(
                self.model_name,
                cache_dir=self.cache_dir
            )
            self._model.to(self.device)
            self._model.eval()  # Set to evaluation mode
        return self._model

    @property
    def label_map(self) -> Dict[int, str]:
        """Index -> lowercase label, taken from the model's own id2label config"""
        if self._label_map is None:
            id2label = self.model.config.id2label
            self._label_map = {int(idx): label.lower() for idx, label in id2label.items()}
            expected = {"negative", "neutral", "positive"}
            if set(self._label_map.values()) != expected:
                raise ValueError(f"Unexpected FinBERT labels {self._label_map}; expected {sorted(expected)}")
        return self._label_map

    def analyze_section_sentiment(self, section_text: str, section_name: str = "Risk Factors") -> Dict:
        """
        Analyze sentiment for a complete SEC filing section.
        
        Args:
            section_text: Full section text to analyze
            section_name: Name of the section (for metadata)
            
        Returns:
            Dict with sentiment scores and metadata
        """
        if not section_text or len(section_text.strip()) < 10:
            return self._empty_sentiment_result(section_name, "Text too short")
        
        # Split text into manageable chunks
        chunks = self._smart_chunk_text(section_text)
        
        if not chunks:
            return self._empty_sentiment_result(section_name, "No valid chunks")
        
        print(f"Analyzing {len(chunks)} chunks for {section_name} sentiment...")
        
        # Analyze each chunk
        chunk_sentiments = []
        for i, chunk in enumerate(chunks, 1):
            try:
                sentiment = self._analyze_chunk_sentiment(chunk)
                chunk_sentiments.append(sentiment)
                
                if i % 5 == 0:  # Progress update every 5 chunks
                    print(f"  Processed {i}/{len(chunks)} chunks...")
                    
            except Exception as e:
                print(f"  Warning: Error analyzing chunk {i}: {e}")
                continue
        
        if not chunk_sentiments:
            return self._empty_sentiment_result(section_name, "No chunks analyzed successfully")
        
        # Aggregate chunk results
        aggregated = self._aggregate_chunk_sentiments(chunk_sentiments)
        
        # Add metadata
        result = {
            **aggregated,
            "section_name": section_name,
            "text_length": len(section_text),
            "chunks_analyzed": len(chunk_sentiments),
            "model_used": self.model_name,
            "device_used": str(self.device)
        }
        
        print(f"✅ Sentiment analysis complete: {result['sentiment_label']} (score: {result['overall_score']:.3f})")
        return result
    
    def _analyze_chunk_sentiment(self, text: str) -> Dict:
        """Analyze sentiment for a single text chunk"""
        # Tokenize with proper truncation
        inputs = self.tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=512,
            padding=True
        ).to(self.device)
        
        # Get model predictions
        with torch.no_grad():
            outputs = self.model(**inputs)
            predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)
        
        # Convert to probabilities
        probs = predictions.cpu().numpy()[0]

        return {self.label_map[idx]: float(prob) for idx, prob in enumerate(probs)}
    
    def _smart_chunk_text(self, text: str, max_chunk_size: int = 400) -> List[str]:
        """
        Intelligently chunk text on sentence boundaries while respecting token limits.
        
        Args:
            text: Input text to chunk
            max_chunk_size: Maximum tokens per chunk (leaving buffer for special tokens)
            
        Returns:
            List of text chunks
        """
        # Split on sentences (simple approach)
        sentences = [s.strip() for s in text.split('.') if s.strip()]
        
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            # Rough token estimation (1 token ≈ 4 characters for English)
            potential_chunk = current_chunk + sentence + ". "
            estimated_tokens = len(potential_chunk) // 4
            
            if estimated_tokens <= max_chunk_size:
                current_chunk = potential_chunk
            else:
                # Add current chunk if it has content
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                
                # Start new chunk
                current_chunk = sentence + ". "
        
        # Add final chunk
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        # Filter out very short chunks (less than 20 characters)
        chunks = [chunk for chunk in chunks if len(chunk) >= 20]
        
        return chunks
    
    def _aggregate_chunk_sentiments(self, chunk_sentiments: List[Dict]) -> Dict:
        """Aggregate sentiment scores across multiple chunks"""
        if not chunk_sentiments:
            return {"negative": 0.0, "neutral": 1.0, "positive": 0.0, "overall_score": 0.0, "sentiment_label": "Neutral"}
        
        # Calculate weighted averages (equal weights for now)
        avg_negative = np.mean([s["negative"] for s in chunk_sentiments])
        avg_neutral = np.mean([s["neutral"] for s in chunk_sentiments])  
        avg_positive = np.mean([s["positive"] for s in chunk_sentiments])
        
        # Calculate overall sentiment score: -1 (very negative) to +1 (very positive)
        overall_score = avg_positive - avg_negative
        
        # Determine sentiment label
        sentiment_label = self._get_sentiment_label(avg_negative, avg_neutral, avg_positive)
        
        return {
            "negative": float(avg_negative),
            "neutral": float(avg_neutral),
            "positive": float(avg_positive),
            "overall_score": float(overall_score),
            "sentiment_label": sentiment_label,
            "confidence": float(max(avg_negative, avg_neutral, avg_positive))  # Confidence = highest probability
        }
    
    def _get_sentiment_label(self, negative: float, neutral: float, positive: float) -> str:
        """Determine sentiment label based on probabilities"""
        max_prob = max(negative, neutral, positive)
        
        if max_prob == positive:
            return "Positive"
        elif max_prob == negative:
            return "Negative" 
        else:
            return "Neutral"
    
    def _empty_sentiment_result(self, section_name: str, reason: str) -> Dict:
        """Return empty/neutral sentiment result"""
        return {
            "negative": 0.0,
            "neutral": 1.0,
            "positive": 0.0,
            "overall_score": 0.0,
            "sentiment_label": "Neutral",
            "confidence": 1.0,
            "section_name": section_name,
            "text_length": 0,
            "chunks_analyzed": 0,
            "model_used": self.model_name,
            "device_used": str(self.device),
            "error": reason
        }


def analyze_risk_factors_sentiment(section_content: str) -> Dict:
    """
    Convenience function to analyze Risk Factors sentiment.
    
    Args:
        section_content: Risk Factors section text
        
    Returns:
        Sentiment analysis results
    """
    analyzer = FinBERTAnalyzer()
    return analyzer.analyze_section_sentiment(section_content, "Risk Factors")


if __name__ == "__main__":
    # Quick test
    test_text = """
    The company faces significant risks related to market volatility, regulatory changes, 
    and competitive pressures. These factors may adversely impact our financial performance 
    and operations. However, we have implemented strong risk management practices to mitigate 
    these concerns.
    """
    
    result = analyze_risk_factors_sentiment(test_text)
    print(f"Test result: {result}")