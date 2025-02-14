import os
import sys
import logging
import argparse

from .handlers import get_jobs_for_url_or_path
from .downloader import drive_downloads
from .config import Settings, load_config
from .keys import get_download_keys
from .api import ItchApiClient

logging.basicConfig()
logging.getLogger().setLevel(logging.INFO)


def parse_args() -> argparse.Namespace:
    # fmt: off
    parser = argparse.ArgumentParser(description="Bulk download stuff from Itch.io.")
    parser.add_argument("url_or_path",
                        help="itch.io URL or path to a game jam entries.json file")
    parser.add_argument("--profile", metavar="profile", default=None,
                        help="configuration profile to load")

    # These args must match config.py -> Settings class. Make sure all defaults here
    # evaluate to False, or load_config will override profile settings.
    parser.add_argument("--api-key", metavar="key", default=None,
                        help="itch.io API key - https://itch.io/user/settings/api-keys")
    parser.add_argument("--user-agent", metavar="agent", default=None,
                        help="user agent to use when sending HTTP requests")
    parser.add_argument("--download-to", metavar="path", default=None,
                        help="directory to save results into (default: current working dir)")
    parser.add_argument("--mirror-web", action="store_true",
                        help="try to fetch assets on game sites")
    parser.add_argument("--urls-only", action="store_true",
                        help="print scraped game URLs without downloading them")
    parser.add_argument("--parallel", metavar="parallel", type=int, default=None,
                        help="how many threads to use for downloading games (default: 1)")
    parser.add_argument("--filter-files-glob", metavar="glob", default=None,
                        help="filter downloaded files with a shell-style glob/fnmatch (unmatched files are skipped)")
    parser.add_argument("--filter-files-regex", metavar="regex", default=None,
                        help="filter downloaded files with a Python regex (unmatched files are skipped)")
    parser.add_argument("--verbose", action="store_true",
                        help="print verbose logs")

    return parser.parse_args()
    # fmt: on


def run() -> int:
    args = parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    settings: Settings = load_config(args, profile=args.profile)
    if settings.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if not settings.api_key:
        sys.exit(
            "You did not provide an API key which itch-dl requires.\n"
            "See https://github.com/DragoonAethis/itch-dl/wiki/API-Keys for more info."
        )

    url_or_path = args.url_or_path
    del args  # Do not use `args` beyond this point.

    # Check API key validity:
    client = ItchApiClient(settings.api_key, settings.user_agent)
    profile_req = client.get("/profile")
    if not profile_req.ok:
        sys.exit(
            f"Provided API key appears to be invalid: {profile_req.text}\n"
            "See https://github.com/DragoonAethis/itch-dl/wiki/API-Keys for more info."
        )

    jobs = get_jobs_for_url_or_path(url_or_path, settings)
    jobs = list(set(jobs))  # Deduplicate, just in case...
    logging.info("Found %d URL(s).", len(jobs))

    if len(jobs) == 0:
        sys.exit("No URLs to download.")

    if settings.urls_only:
        for job in jobs:
            print(job)

        return 0

    # If the download dir is not set, use the current working dir:
    settings.download_to = os.path.normpath(settings.download_to or os.getcwd())
    os.makedirs(settings.download_to, exist_ok=True)

    # Grab all the download keys (there's no way to fetch them per title...):
    keys = get_download_keys(client)

    drive_downloads(jobs, settings, keys)
    return 0
