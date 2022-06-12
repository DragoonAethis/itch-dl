import os
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
    parser = argparse.ArgumentParser(description="Bulk download stuff from Itch.io.")
    parser.add_argument("url_or_path",
                        help="itch.io URL or path to a game jam entries.json file")
    parser.add_argument("--api-key", metavar="key", default=None,
                        help="itch.io API key - https://itch.io/user/settings/api-keys")
    parser.add_argument("--profile", metavar="profile", default=None,
                        help="configuration profile to load")
    parser.add_argument("--urls-only", action="store_true",
                        help="print scraped game URLs without downloading them")
    parser.add_argument("--download-to", metavar="path",
                        help="directory to save results into (default: current dir)")
    parser.add_argument("--parallel", metavar="parallel", type=int, default=1,
                        help="how many threads to use for downloading games (default: 1)")
    parser.add_argument("--mirror-web", action="store_true",
                        help="try to fetch assets on game sites")
    parser.add_argument("--verbose", action="store_true",
                        help="print verbose logs")
    return parser.parse_args()


def apply_args_on_settings(args: argparse.Namespace, settings: Settings):
    if args.api_key:
        settings.api_key = args.api_key


def run() -> int:
    args = parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    settings = load_config(profile=args.profile)
    apply_args_on_settings(args, settings)

    if not settings.api_key:
        exit("You did not provide an API key which itch-dl requires.\n"
             "See https://github.com/DragoonAethis/itch-dl/wiki/API-Keys for more info.")

    # Check API key validity:
    client = ItchApiClient(settings.api_key, settings.user_agent)
    profile_req = client.get("/profile")
    if not profile_req.ok:
        exit(f"Provided API key appears to be invalid: {profile_req.text}\n"
             "See https://github.com/DragoonAethis/itch-dl/wiki/API-Keys for more info.")

    jobs = get_jobs_for_url_or_path(args.url_or_path, settings)
    jobs = list(set(jobs))  # Deduplicate, just in case...
    logging.info(f"Found {len(jobs)} URL(s).")

    if len(jobs) == 0:
        exit("No URLs to download.")

    if args.urls_only:
        for job in jobs:
            print(job)

        return 0

    download_to = os.getcwd()
    if args.download_to is not None:
        download_to = os.path.normpath(args.download_to)
        os.makedirs(download_to, exist_ok=True)

    # Grab all the download keys (there's no way to fetch them per title...):
    keys = get_download_keys(client)

    return drive_downloads(jobs, download_to, args.mirror_web, settings, keys, parallel=args.parallel)
