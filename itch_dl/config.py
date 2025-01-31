import os
import json
import logging
import platform
import argparse
from typing import Optional

import requests
from pydantic import BaseModel

from . import __version__

OVERRIDABLE_SETTINGS = (
    "api_key",
    "user_agent",
    "download_to",
    "mirror_web",
    "urls_only",
    "parallel",
    "filter_files_glob",
    "filter_files_regex",
    "verbose",
)


class Settings(BaseModel):
    """Available settings for itch-dl. Make sure all of them
    have default values, as the config file may not exist."""

    api_key: Optional[str] = None
    user_agent: str = f"python-requests/{requests.__version__} itch-dl/{__version__}"

    download_to: Optional[str] = None
    mirror_web: bool = False
    urls_only: bool = False
    parallel: int = 1

    filter_files_glob: Optional[str] = None
    filter_files_regex: Optional[str] = None

    verbose: bool = False


def create_and_get_config_path() -> str:
    """Returns the configuration directory in the appropriate
    location for the current OS. The directory may not exist."""
    system = platform.system()
    if system == "Linux":
        base_path = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config/")
    elif system == "Darwin":
        base_path = os.path.expanduser("~/Library/Application Support/")
    elif system == "Windows":
        base_path = os.environ.get("APPDATA") or os.path.expanduser("~/AppData/Roaming/")
    else:
        raise NotImplementedError(f"Unknown platform: {system}")

    return os.path.join(base_path, "itch-dl")


def load_config(args: argparse.Namespace, profile: Optional[str] = None) -> Settings:
    """Loads the configuration from the file system if it exists,
    the returns a Settings object."""
    config_path = create_and_get_config_path()
    config_file_path = os.path.join(config_path, "config.json")
    profile_file_path = os.path.join(config_path, "profiles", profile or "")

    if os.path.isfile(config_file_path):
        logging.debug("Found config file: %s", config_file_path)
        with open(config_file_path) as f:
            config_data = json.load(f)
    else:
        config_data = {}

    if os.path.isfile(profile_file_path):
        logging.debug("Found profile: %s", profile_file_path)
        with open(config_file_path) as f:
            profile_data = json.load(f)

        config_data.update(profile_data)

    # All settings from the base file:
    settings = Settings(**config_data)

    # Apply overrides from CLI args:
    for key in OVERRIDABLE_SETTINGS:
        value = getattr(args, key)
        if value:
            setattr(settings, key, value)

    return settings
