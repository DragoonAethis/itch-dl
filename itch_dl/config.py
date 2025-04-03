import os
import json
import logging
import platform
import argparse
from dataclasses import dataclass, fields
from typing import Any, get_type_hints

import requests

from . import __version__


@dataclass
class Settings:
    """Available settings for itch-dl. Make sure all of them
    have default values, as the config file may not exist."""

    api_key: str | None = None
    user_agent: str = f"python-requests/{requests.__version__} itch-dl/{__version__}"

    download_to: str | None = None
    mirror_web: bool = False
    urls_only: bool = False
    parallel: int = 1

    filter_files_platform: list | None = None
    filter_files_type: list | None = None
    filter_files_glob: str | None = None
    filter_files_regex: str | None = None

    filter_urls_glob: str | None = None
    filter_urls_regex: str | None = None

    verbose: bool = False


def process_platform_traits(platforms: list[str]) -> list[str] | None:
    """Converts the user-friendly platform strings into itch.io upload p_traits."""
    if not platforms:
        return None

    trait_mapping = {
        "win": "p_windows",
        "lin": "p_linux",
        "mac": "p_osx",
        "osx": "p_osx",
        "darwin": "p_osx",
        "and": "p_android",
    }

    traits = set()
    for p in platforms:
        platform_trait = None
        p = p.strip().lower().removeprefix("p_")  # noqa: PLW2901

        if p.startswith("native"):
            p = platform.system().lower()  # noqa: PLW2901
            if p.endswith("bsd"):
                logging.warning("Note: Native downloads for *BSDs are not available - Linux binaries will be used.")
                p = "linux"  # noqa: PLW2901

        for key, trait in trait_mapping.items():
            if p.startswith(key):
                platform_trait = trait
                break

        if not platform_trait:
            raise ValueError(f"Platform {p} not known!")

        traits.add(platform_trait)

    return list(traits)


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


def clean_config(config_data: dict[str, Any]) -> dict[str, Any]:
    cleaned_config = {}
    settings_invalid = False
    type_hints = get_type_hints(Settings)

    # Complain about invalid types, if any:
    for key, value in config_data.items():
        if not (expected_type := type_hints.get(key)):
            logging.warning("Settings contain an unknown item, ignoring: '%s'", key)
            continue

        if not isinstance(value, expected_type):
            logging.fatal("Settings.%s has invalid type '%s', expected '%s'", key, type(value), expected_type)

            # Keep iterating to look up all the bad keys:
            settings_invalid = True
            continue

        cleaned_config[key] = value

    if settings_invalid:
        logging.fatal("Settings invalid, bailing out!")
        exit(1)

    return cleaned_config


def load_config(args: argparse.Namespace, profile: str | None = None) -> Settings:
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
    settings = Settings(**clean_config(config_data))

    # Apply overrides from CLI args on each field in Settings:
    for field in fields(Settings):
        key = field.name
        if value := getattr(args, key):
            setattr(settings, key, value)

    # Extra handling for special settings:
    settings.filter_files_platform = process_platform_traits(settings.filter_files_platform)

    return settings
