# EY Work Order Extraction Pipeline

Automated pipeline for extracting structured data from Indian coal transportation work order PDFs and exporting results to a formatted Excel workbook.

---

## Overview

This tool processes multi-page, scanned work order PDFs using a three-stage pipeline:

1. **Azure Document Intelligence** — extracts key-value pairs from structured pages
2. **Rule-based extraction** — applies regex and heuristics across the full PDF text (via `pypdf`)
3. **LLM fallback** (optional) — uses Azure OpenAI to fill gaps when rule-based extraction is incomplete

Output is a polished, multi-sheet Excel file.

---

## Project Structure

```
project/
├── main.py                  # Entry point — orchestrates the full pipeline
├── src/
│   ├── azure_di.py          # Azure Document Intelligence client
│   ├── azure_openai.py      # Azure OpenAI client + prompts
│   ├── rule_extractor.py    # Rule-based field extraction (header, services, pricing, etc.)
│   ├── pdf_extractor.py     # Direct PDF text extraction using pypdf
│   ├── llm_fallback.py      # LLM gap-fill logic and merge strategy
│   ├── cleaner.py           # OCR noise cleaning utilities
│   └── config.py            # Configuration loader from .env
├── output/extracted/        # Default output directory for Excel files
├── .env                     # Environment variables (not committed)
└── README.md
```

---

## Setup

### 1. Install dependencies

```bash
pip install azure-ai-documentintelligence azure-core openai pypdf openpyxl python-dotenv
```

### 2. Configure environment variables

Create a `.env` file in the project root:

```env
# Azure Document Intelligence (required)
DOCUMENT_INTELLIGENCE_ENDPOINT=https://<your-resource>.cognitiveservices.azure.com/
DOCUMENT_INTELLIGENCE_KEY=<your-key>
DI_MODEL_ID=prebuilt-layout

# Azure OpenAI (required only if USE_LLM_FALLBACK=true)
AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com/
AZURE_OPENAI_KEY=<your-key>
AZURE_OPENAI_DEPLOYMENT=gpt-4.1
AZURE_OPENAI_API_VERSION=2024-02-15-preview

# Pipeline settings
USE_LLM_FALLBACK=true
LLM_CONFIDENCE_THRESHOLD=0.75
OUTPUT_DIR=output/extracted
```

---

## Usage

**Process a single PDF:**
```bash
python main.py path/to/workorder.pdf
```

**Process a folder of PDFs:**
```bash
python main.py path/to/folder/
```

Output Excel files are saved to `output/extracted/` (or the path set in `OUTPUT_DIR`) with a timestamped filename:
```
<pdf_name>_extracted_YYYYMMDD_HHMMSS.xlsx
```

---

## Output Excel Structure

| Sheet | Contents |
|---|---|
| **Header** | Order number, dates, vendor info, GST, validity period |
| **Services** | Service line items with descriptions, rates, and units |
| **Pricing** | Diesel PVC component, HSD reference, gross price, ceiling value |
| **Text Blocks** | Scope of work, safety norms, exit clause, payment terms detail |
| **Change Orders** | Contract amendments with dates, types, and ceiling changes |
| **Metadata** | Source file, extraction time, DI model, page/table/KV counts |

---

## Pipeline Details

### Stage 1 — Azure Document Intelligence
Sends the PDF to the `prebuilt-layout` model to extract key-value pairs from the structured first pages. Used primarily for header field detection.

### Stage 2 — Rule-based Extraction
Extracts all text directly from the PDF using `pypdf` (all pages). Applies targeted regex patterns for:
- Header fields (order number, dates, vendor code, GST, validity)
- Service line items (item codes, descriptions, rates, units)
- Pricing (HSD base rate, diesel component %, ceiling values)
- Text blocks (scope of work, safety norms, exit clause, payment terms)
- Change orders (C/O blocks with amendment types and ceiling changes)

Also handles the **two-column layout** on page 1, where pypdf reads left-column labels and right-column values separately.

### Stage 3 — LLM Gap-fill (optional)
If mandatory fields are missing after Stage 2, the pipeline sends a token-efficient slice of the document to Azure OpenAI (GPT-4.1). The LLM output is merged carefully — **rule-based values always take priority** over LLM values.

LLM is triggered when any of the following are missing:
- Header: Order Number, Order Date, Validity From/To, Vendor Code, Payment Terms
- Pricing: Diesel Component %, Base HSD, Gross Price
- Services: any items at all

To disable the LLM entirely, set `USE_LLM_FALLBACK=false` in `.env`.

---

## OCR Noise Handling

The `cleaner.py` module handles common artefacts in scanned Indian work order PDFs:
- Letter-spaced words (e.g. `W O R K O R D E R` → `WORK ORDER`)
- Redacted placeholders (`< VENDOR NAME >` → `<VENDOR NAME>`)
- Separator noise (`:-` → `:`)
- Repeated hash characters (`###`)
- Short noise lines and page header/footer boilerplate

---

## Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `DOCUMENT_INTELLIGENCE_ENDPOINT` | — | Azure DI endpoint (required) |
| `DOCUMENT_INTELLIGENCE_KEY` | — | Azure DI API key (required) |
| `DI_MODEL_ID` | `prebuilt-layout` | DI model to use |
| `AZURE_OPENAI_ENDPOINT` | — | Azure OpenAI endpoint |
| `AZURE_OPENAI_KEY` | — | Azure OpenAI API key |
| `AZURE_OPENAI_DEPLOYMENT` | `gpt-4.1` | Deployment name |
| `AZURE_OPENAI_API_VERSION` | `2024-02-15-preview` | API version |
| `USE_LLM_FALLBACK` | `true` | Enable/disable LLM gap-fill |
| `LLM_CONFIDENCE_THRESHOLD` | `0.75` | Threshold for triggering LLM |
| `OUTPUT_DIR` | `output/extracted` | Directory for Excel output |

---



- All sensitive credentials must be stored in `.env` — never hard-coded.
- The pipeline is designed for **local PDF files only** (no Azure Blob Storage).
- The LLM prompt is tuned specifically for Indian coal transportation work orders with heavy OCR noise.