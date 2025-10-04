"""
API Keys configuration file for AgenticVerifier runners.

This file stores API keys for various services used in the project.
Set your actual API keys here or use environment variables as fallback.
"""

import os

# OpenAI API Key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Meshy API Key  
MESHY_API_KEY = os.getenv("MESHY_API_KEY", "")

# VA API Key
VA_API_KEY = os.getenv("VA_API_KEY", "")

# Validation function to check if required API keys are set
def validate_api_keys():
    """Validate that required API keys are set."""
    missing_keys = []
    
    if not OPENAI_API_KEY:
        missing_keys.append("OPENAI_API_KEY")
    if not MESHY_API_KEY:
        missing_keys.append("MESHY_API_KEY")
    if not VA_API_KEY:
        missing_keys.append("VA_API_KEY")
    
    if missing_keys:
        raise ValueError(f"Missing required API keys: {', '.join(missing_keys)}")
    
    return True

# Helper function to get API key with fallback
def get_api_key(key_name: str, fallback: str = "") -> str:
    """Get API key with fallback to environment variable or provided fallback."""
    key_map = {
        "OPENAI_API_KEY": OPENAI_API_KEY,
        "MESHY_API_KEY": MESHY_API_KEY,
        "VA_API_KEY": VA_API_KEY
    }
    
    return key_map.get(key_name, fallback) or os.getenv(key_name, fallback)
