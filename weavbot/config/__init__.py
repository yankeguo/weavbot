"""Configuration module for weavbot."""

from weavbot.config.loader import get_config_path, load_config
from weavbot.config.schema import Config

__all__ = ["Config", "load_config", "get_config_path"]
