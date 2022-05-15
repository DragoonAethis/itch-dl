import os
import logging
import argparse

from .handlers import get_jobs_for_url_or_path
from .downloader import drive_downloads
from .keys import get_download_keys
from .api import ItchApiClient

logging.basicConfig()
logging.getLogger().setLevel(logging.INFO)


def parse_args():
    parser = argparse.ArgumentParser(description="Bulk download stuff from Itch.io.")
    parser.add_argument("url_or_path",
                        help="itch.io URL or path to a game jam entries.json file")
    parser.add_argument("--api-key", metavar="key", required=True,
                        help="itch.io API key - https://itch.io/user/settings/api-keys")
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


def run() -> int:
    args = parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    jobs = get_jobs_for_url_or_path(args.url_or_path, args.api_key)
    jobs = list(set(jobs))  # Deduplicate, just in case...
    logging.info(f"Found {len(jobs)} URL(s).")

    if len(jobs) == 0:
        print("No URLs to download.")
        return 1

    if args.urls_only:
        for job in jobs:
            print(job)

        return 0

    download_to = os.getcwd()
    if args.download_to is not None:
        download_to = os.path.normpath(args.download_to)
        os.makedirs(download_to, exist_ok=True)

    client = ItchApiClient(args.api_key)

    # Check API key validity:
    profile_req = client.get("/profile")
    if not profile_req.ok:
        print(f"Provided API key appears to be invalid: {profile_req.text}")
        exit(1)

    # Grab all the download keys (there's no way to fetch them per title...):
    keys = get_download_keys(client)

    return drive_downloads(jobs, download_to, args.mirror_web, args.api_key, keys, parallel=args.parallel)
