import os
import shutil
import logging
import traceback
import subprocess
from typing import Tuple, List, Dict, TypedDict, Optional

from slugify import slugify
from requests.exceptions import HTTPError

from tqdm import tqdm
from tqdm.contrib.concurrent import thread_map

from .api import ItchApiClient
from .consts import ItchDownloadError, ItchDownloadResult


# ------------------------------
# --- OLD STUFF --- CUT HERE ---
# ------------------------------


WGET_PATH = shutil.which("wget")
if WGET_PATH is None:
    print(f"Warning: wget not available, site mirroring will not work!")


def download_file(client: ItchApiClient, upload_id: int, download_path: str, creds: dict, print_url: bool=False):
    # No timeouts, chunked uploads, default retry strategy, should be all good?
    try:
        with client.get(f"/uploads/{upload_id}/download", data=creds, stream=True) as r:
            r.raise_for_status()
            if print_url:
                print(f"Download URL: {r.url}")

            with open(download_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1048576):  # 1MB chunks
                    f.write(chunk)
    except HTTPError as e:
        raise ItchDownloadError(f"Unrecoverable download error: {e}")


def get_meta_for_game_url(game_url: str) -> Tuple[int, str]:
    """Finds the Game ID and Title for a Game URL."""
    data_url = game_url.rstrip("/") + "/data.json"
    data_req = requests.get(data_url)
    r.raise_for_status()

    data_json = data_req.json()
    if not 'id' in data_json:
        raise ItchDownloadError(f"Cannot fetch the Game ID for URL: {game_url}")

    return data_json['id']







def download_jam(jam_path: str, download_to: str, api_key: str, continue_from: str=None):
    client = ItchApiClient(api_key)
    jam_json = get_game_jam_json(jam_path)

    # Check API key validity:
    profile_req = client.get("/profile")
    if not profile_req.ok:
        print(f"Provided API key appears to be invalid: {profile_req.text}")
        exit(1)

    jobs = parse_jobs(jam_json)
    jobs_successful = []
    jobs_failed = []

    game_id_to_meta = {}  # dict[game_id: int, (title: str, url: str)]

    for game_id, title, url in jobs:
        game_id_to_meta[game_id] = (title, url)

    failed_game_ids = set()

    # No "continue from"? Yep, start right away.
    should_process_jobs = continue_from is None

    for game_id, title, url in jobs:
        label = f"{title} ({game_id})"
        if not should_process_jobs:
            if game_id == continue_from:
                should_process_jobs = True
            else:
                continue

        try:
            download_path = os.path.join(download_to, slugify(title))
            if PEDANTIC_MIRRORING:
                site_mirror_path = os.path.join(download_to, "_sites")
            else:
                site_mirror_path = os.path.join(download_path, "site")
            os.makedirs(download_path, exist_ok=True)
            os.makedirs(site_mirror_path, exist_ok=True)
        except:
            raise ItchDownloadError(f"Could not create download directory: {download_path}")

        print(f"Trying to download {label} to {download_path}")

        if WGET_PATH is not None:
            print("Downloading site...")
            if PEDANTIC_MIRRORING:
                extra_wget_args = [
                    "--timestamping",
                    "--span-hosts",
                    "--convert-links",
                    "--adjust-extension",
                    "--page-requisites",
                ]
            else:
                extra_wget_args = []

            wget = subprocess.run([
                WGET_PATH,
                *extra_wget_args,
                "--quiet",
                url
            ], cwd=site_mirror_path)

            if wget.returncode != 0:
                print(f"Warning: Site mirroring failed/incomplete.")

        creds = {}
        if game_id in self.download_keys:
            creds['download_key_id'] = self.download_keys[game_id]
            print("Using {creds} for private uploads")

        game_uploads_req = client.get(f"/games/{game_id}/uploads", data=creds, timeout=15)
        if not game_uploads_req.ok:
            raise ItchDownloadError(f"Could not fetch game uploads for {label}: {game_uploads_req.text}")

        game_uploads = game_uploads_req.json()['uploads']
        print(f"Found {len(game_uploads)} upload(s)")

        try:
            for upload in game_uploads:
                upload_id = upload['id']
                file_name = upload['filename']
                file_size = upload['size']
                upload_is_external = upload['storage'] == 'external'

                print(f"Downloading '{file_name}' ({upload_id}), {file_size} bytes...")
                if upload_is_external:
                    print("***********************************************************")
                    print("*                                                         *")
                    print("* WARNING: External storage - downloads will likely fail. *")
                    print("*         Check the URL displayed below manually!         *")
                    print("*                                                         *")
                    print("***********************************************************")

                target_path = os.path.join(download_path, file_name)
                try:
                    download_file(client, upload_id, target_path, creds, print_url=upload_is_external)
                except ItchDownloadError as e:
                    jobs_failed.append((game_id, file_name, str(e)))
                    print(f"Download failed for {file_name}: {e}")
                    continue

                try:
                    actual_file_size = os.stat(target_path).st_size
                    if actual_file_size == file_size:
                        jobs_successful.append((game_id, file_name))
                    else:
                        jobs_failed.append((game_id, file_name, f"File size is {actual_file_size}, expected {file_size}"))
                except FileNotFoundError:
                    jobs_failed.append((game_id, file_name, "Could not download file"))

            print(f"Done downloading {label}")
        except ItchDownloadError as e:
            failed_game_ids.append((game_id, str(e)))
            print(message)
            continue
        except Exception as e:
            print(f"Critical error while downloading {label}: {e}")
            failed_game_ids.append((game_id, str(e)))
            traceback.print_exc()
            print(message)
            continue

    successful_titles = {}
    for game_id, file_name in jobs_successful:
        if game_id not in successful_titles:
            successful_titles[game_id] = [file_name]

    if any(successful_titles):
        print(f"\nAll done, downloaded files for {len(successful_titles)} title(s):")
        for game_id, files in successful_titles.items():
            print(f"{game_id_to_meta[game_id][0]}, {len(files)} file(s)")

    if any(jobs_failed):
        print(f"\nDownloads failed for {len(jobs_failed)} file(s):")
        for game_id, file_name, message in jobs_failed:
            title, url = game_id_to_meta[game_id]
            print(f"{title} - {file_name} - {message}")
            print(f"Title URL: {url}")

    if any(failed_game_ids):
        print(f"\nCompletely failed downloads for {len(failed_game_ids)} titles:")
        for game_id, message in failed_game_ids:
            title, url = game_id_to_meta[game_id]
            print(f"{title} ({game_id}) - {url} - {message}")


# ------------------------------
# --- OLD STUFF --- CUT HERE ---
# ------------------------------


class GameAuthor(TypedDict, total=False):
    name: str
    url: str


class GameMetadata(TypedDict, total=False):
    description: str


class GameDownloadJob(TypedDict, total=False):
    url: str
    game_id: int
    title: str
    author: GameAuthor
    metadata: GameMetadata


class GameDownloader:
    def __init__(self, download_to: str, api_key: str, keys: Dict[int, str]):
        self.download_to = download_to
        self.download_keys = keys

        self.client = ItchApiClient(api_key)

    def download(self, url: str):
        job = GameDownloadJob(url=url)
        raise NotImplementedError("Not yet!")


def drive_downloads(jobs: List[str], download_to: str, api_key: str, keys: Dict[int, str], parallel: int = 1):
    downloader = GameDownloader(download_to, api_key, keys)

    if parallel > 1:
        thread_map(downloader.download, jobs, max_workers=parallel, )
    else:
        for job in tqdm(jobs):
            downloader.download(job)
