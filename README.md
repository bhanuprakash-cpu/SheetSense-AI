# SheetSense-AI

SheetSense AI is an AI-powered data analytics dashboard that lets users analyze data without formulas or code.

## Features

- Upload CSV and Excel files (`.csv`, `.xls`, `.xlsx`)
- Load spreadsheet data directly from CSV/Excel URLs
- Upload screenshots/images with table-like data for OCR extraction
- Ask natural-language questions to generate:
  - summaries and quick insights
  - preview tables
  - line/bar chart visualizations
- Includes roadmap callouts for:
  - automated insights
  - advanced visualizations
  - PDF report exports

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Test

```bash
pytest -q
```