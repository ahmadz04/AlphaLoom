# Alpha Loom Quick Start Guide

## Environment Setup

### 1. Copy Environment Variables

Duplicate the sample environment file to create your local configuration:

```bash
cp config/.env.sample config/.env
```

**Note:** The `.env` file is git-ignored and contains your actual API keys and configuration.

### 2. Configure Your Environment

Edit `config/.env` with your actual API keys:

- `FINANCIAL_DATASETS_API_KEY`: Your financialdatasets.ai API key for SEC filings
- `DEFAULT_TICKER`: Default stock ticker (defaults to AAPL)
- `DEFAULT_FILING_TYPE`: Default SEC filing type (defaults to 10-K)
- `NEWS_WINDOW_DAYS`: Number of days to look back for news (defaults to 7)
- Legacy SeekingAlpha API keys (if using transcript ingestion)

### 3. Point Your Editor to Environment File

Most IDEs and editors can automatically load environment variables from `.env` files:

- **VS Code**: Install the "DotENV" extension
- **PyCharm**: Environment variables are automatically loaded from `.env` files
- **Vim/Neovim**: Use plugins like `vim-dotenv` or `dotenv.nvim`
- **Terminal**: Use `source config/.env` or `export $(cat config/.env | xargs)`

### 4. Verify Setup

Check that your environment variables are loaded:

```bash
python -c "import os; print('DEFAULT_TICKER:', os.getenv('DEFAULT_TICKER'))"
```

## Next Steps

- Review `docs/data-contracts.md` for data structure information
- Check `docs/runbook-ingestion.md` for ingestion workflow details
- Explore the `ingestion/` and `processing/` directories for implementation details
