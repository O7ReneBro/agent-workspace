"""
Environment variable loader for trading config.
Use this to avoid hardcoding API keys in YAML.

Usage:
    from env_loader import load_config_with_env
    config = load_config_with_env()
"""

import os
import yaml


def load_config_with_env(path: str = "config/trading_config.yaml") -> dict:
    """Load YAML config and override sensitive fields from environment variables."""
    with open(path, "r") as f:
        config = yaml.safe_load(f)

    # Override API keys from environment
    if os.environ.get("KRAKEN_API_KEY"):
        config["kraken"]["api_key"] = os.environ["KRAKEN_API_KEY"]
    if os.environ.get("KRAKEN_API_SECRET"):
        config["kraken"]["api_secret"] = os.environ["KRAKEN_API_SECRET"]

    # Override Ollama settings from environment
    if os.environ.get("OLLAMA_HOST"):
        config["ollama"]["host"] = os.environ["OLLAMA_HOST"]
    if os.environ.get("OLLAMA_MODEL"):
        config["ollama"]["model"] = os.environ["OLLAMA_MODEL"]

    return config
