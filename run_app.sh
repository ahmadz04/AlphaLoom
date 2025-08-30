#!/bin/bash

# AlphaLoom Gradio App Launcher
# This script launches the Gradio frontend for testing the pipeline

echo "🔍 Starting AlphaLoom Frontend..."
echo "============================================"

# Load environment variables
if [ -f "config/.env" ]; then
    echo "✅ Loading environment variables from config/.env"
    export $(cat config/.env | xargs)
else
    echo "⚠️  Warning: config/.env not found"
    echo "   Copy config/.env.sample to config/.env and configure your API keys"
fi

# Check if gradio is installed
if ! python -c "import gradio" &> /dev/null; then
    echo "❌ Gradio not found. Installing dependencies..."
    pip install -r requirements.txt
fi

# Create necessary directories
echo "📁 Creating necessary directories..."
mkdir -p data/raw/filings
mkdir -p data/processed
mkdir -p data/cache/summaries

echo "🚀 Launching Gradio app..."
echo "   The app will be available at http://localhost:7860"
echo "   Press Ctrl+C to stop the app"
echo ""

# Launch gradio
python app.py