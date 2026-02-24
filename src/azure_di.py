# src/azure_di.py
"""
Azure AI Document Intelligence client — local PDF files only.

NOTE: Full text extraction is handled by src/pdf_extractor.py (pypdf),
not by DI paragraphs. This module is used only for KV pair detection
from the structured first pages.
"""

import os
from typing import Optional

from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import (
    AnalyzeResult,
   # AnalyzeDocumentRequest,
    DocumentAnalysisFeature
)

from src.config import DI_ENDPOINT, DI_KEY, DI_MODEL


def get_di_client() -> DocumentIntelligenceClient:
    if not DI_ENDPOINT or not DI_KEY:
        raise ValueError(
            "Missing Azure DI credentials.\n"
            "Set DOCUMENT_INTELLIGENCE_ENDPOINT and DOCUMENT_INTELLIGENCE_KEY in .env"
        )
    return DocumentIntelligenceClient(
        endpoint=DI_ENDPOINT,
        credential=AzureKeyCredential(DI_KEY),
    )


def analyze_pdf(
    pdf_path: str,
    model_id: Optional[str] = None,
) -> AnalyzeResult:
    """
    Analyze a PDF with Azure Document Intelligence.
    Returns AnalyzeResult used only for KV pairs and table structure.
    Full text comes from src/pdf_extractor.py instead.
    """
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    model_id = model_id or DI_MODEL
    print(f"\n-> Azure DI  |  {os.path.basename(pdf_path)}  "
          f"({os.path.getsize(pdf_path) / 1024:.0f} KB)  |  model={model_id}")

    client = get_di_client()

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    try:
        poller = client.begin_analyze_document(
            model_id=model_id,
            body=pdf_bytes,
            features=[DocumentAnalysisFeature.KEY_VALUE_PAIRS],
        )

        print("-> Waiting for result...")
        result: AnalyzeResult = poller.result()

        print(f"-> Done  |  pages={len(result.pages or [])}  "
              f"kv={len(result.key_value_pairs or [])}  "
              f"tables={len(result.tables or [])}")

        return result

    except Exception as e:
        raise RuntimeError(f"Document Intelligence analysis failed: {e}") from e


if __name__ == "__main__":
    import sys
    r = analyze_pdf(sys.argv[1] if len(sys.argv) > 1 else "Sample.pdf")
    print(f"Pages: {len(r.pages or [])}  KV: {len(r.key_value_pairs or [])}")