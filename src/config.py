# src/config.py
"""
Central configuration module for the EY Project - Work Order Extraction pipeline.
Loads all settings from .env file located in the project root.
All sensitive values (keys, endpoints) MUST come from .env — never hard-code them here.

Current mode: Local PDF files only (no Azure Blob Storage).
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ────────────────────────────────────────────────
# Load .env file from project root
# ────────────────────────────────────────────────
env_path = Path(__file__).parent.parent / '.env'

if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    print(f"Warning: .env file not found at {env_path}")
    # Continue anyway – os.getenv() will return None for missing keys

# ────────────────────────────────────────────────
# Azure AI Document Intelligence (required)
# ────────────────────────────────────────────────
DI_ENDPOINT = os.getenv("DOCUMENT_INTELLIGENCE_ENDPOINT")
DI_KEY = os.getenv("DOCUMENT_INTELLIGENCE_KEY")
DI_MODEL = os.getenv("DI_MODEL_ID", "prebuilt-layout")  # default model

# ────────────────────────────────────────────────
# Azure OpenAI (optional – only used if LLM fallback is enabled)
# ────────────────────────────────────────────────
OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1")
OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")

# LLM fallback control
USE_LLM_FALLBACK = os.getenv("USE_LLM_FALLBACK", "true").lower() in ("true", "1", "yes")
LLM_CONFIDENCE_THRESHOLD = float(os.getenv("LLM_CONFIDENCE_THRESHOLD", "0.75"))

# ────────────────────────────────────────────────
# Output & Runtime Settings
# ────────────────────────────────────────────────
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output/extracted")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ────────────────────────────────────────────────
# Configuration validation (optional – call from main.py if needed)
# ────────────────────────────────────────────────
def validate_config(print_details: bool = True) -> bool:
    """
    Validate required configuration settings.
    Returns True if valid, False otherwise.
    """
    issues = []

    # Document Intelligence – always required
    if not DI_ENDPOINT:
        issues.append("DOCUMENT_INTELLIGENCE_ENDPOINT is missing")
    if not DI_KEY:
        issues.append("DOCUMENT_INTELLIGENCE_KEY is missing")

    # OpenAI – required only if LLM fallback is turned on
    if USE_LLM_FALLBACK:
        if not OPENAI_ENDPOINT:
            issues.append("AZURE_OPENAI_ENDPOINT is missing (LLM fallback enabled)")
        if not OPENAI_KEY:
            issues.append("AZURE_OPENAI_KEY is missing (LLM fallback enabled)")

    if issues:
        print("⚠️  Configuration validation failed:")
        for issue in issues:
            print(f"  • {issue}")
        print("\nPlease check and update your .env file.")
        return False

    if print_details:
        print("Configuration validation passed.")
        print("Loaded settings (sensitive values hidden):")
        print(f"  • DI_MODEL                  = {DI_MODEL}")
        print(f"  • USE_LLM_FALLBACK          = {USE_LLM_FALLBACK}")
        print(f"  • LLM_CONFIDENCE_THRESHOLD = {LLM_CONFIDENCE_THRESHOLD}")
        print(f"  • OUTPUT_DIR                = {OUTPUT_DIR}")

    return True


# Optional: run validation when file is executed directly (for debugging)
if __name__ == "__main__":
    print("Validating config...")
    validate_config(print_details=True)