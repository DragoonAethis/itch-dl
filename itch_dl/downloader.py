import os
import json
import re
import logging
from typing import Tuple, List, Dict, TypedDict, Optional

from bs4 import BeautifulSoup
from requests.exceptions import HTTPError

from tqdm import tqdm
from tqdm.contrib.concurrent import thread_map

from .api import ItchApiClient
from .utils import ItchDownloadError, get_int_after_marker_in_json
from .consts import ITCH_GAME_URL_REGEX


TARGET_PATHS = {
    'site': 'site.html',
    'metadata': 'metadata.json',
    'files': 'files',
    'screenshots': 'screenshots'
}


class GameMetadata(TypedDict, total=False):
    game_id: int
    title: str
    url: str

    errors: List[str]
    external_downloads: List[str]

    author: str
    author_url: str

    description: str
    cover_url: str

    created_at: str
    published_at: str


class GameDownloader:
    def __init__(self, download_to: str, api_key: str, keys: Dict[int, str]):
        self.download_to = download_to
        self.download_keys = keys

        self.client = ItchApiClient(api_key)

    def get_rating_json(self, site) -> Optional[dict]:
        for ldjson_node in site.find_all("script", type="application/ld+json"):
            try:
                ldjson: dict = json.loads(ldjson_node.text.strip())
                if ldjson.get("@type") == "Product":
                    return ldjson
            except json.JSONDecodeError:
                continue  # Can't do much with this...

        return None

    def get_meta(self, site, **kwargs) -> Optional[str]:
        """Grabs <meta property="xyz" content="value"/> values."""
        node = site.find("meta", attrs=kwargs)
        if not node:
            return None

        return node.get("content")

    def get_game_id(self, url: str, site: BeautifulSoup) -> int:
        game_id: Optional[int] = None

        try:
            # Headers: <meta name="itch:path" content="games/12345" />
            itch_path = self.get_meta(site, name="itch:path")
            if itch_path is not None:
                # Its value should be "games/12345", so:
                game_id = int(itch_path.split("/")[-1])
        except ValueError:
            pass

        if game_id is None:
            # I.ViewGame has the "id" key in its config
            for script in site.find_all("script", type="text/javascript"):
                script_src = script.text.strip()
                marker = "I.ViewGame"
                if marker in script_src:
                    game_id = get_int_after_marker_in_json(script_src, marker, "id")
                    break

        if game_id is None:
            # We have to hit the server again :(
            data_url = url.rstrip('/') + "/data.json"
            data_request = self.client.get(data_url, append_api_key=False)
            if data_request.ok:
                try:
                    game_id = int(data_request.json().get("id"))
                except ValueError:
                    pass

        if game_id is None:
            raise ItchDownloadError(f"Could not get the Game ID for URL: {url}")

        return game_id

    def extract_metadata(self, game_id: int, url: str, site: BeautifulSoup) -> GameMetadata:
        description: Optional[str] = self.get_meta(site, property="og:description")
        if not description:
            description = self.get_meta(site, name="description")

        metadata = GameMetadata(
            game_id=game_id,
            title=site.find("h1", class_="game_title").text.strip(),
            url=url,
            cover_url=self.get_meta(site, property="og:image"),
            description=description
        )

        TODO_KEYS = ['author', 'author_url', 'created_at', 'published_at']
        TODO_rating_json: Optional[dict] = self.get_rating_json(site)

        return metadata

    def get_credentials(self, title: str, game_id: int) -> dict:
        credentials = {}
        if game_id in self.download_keys:
            credentials['download_key_id'] = self.download_keys[game_id]
            logging.debug("Got credentials for %s: %s", title, str(credentials))

        return credentials

    def download_file(self, upload_id: int, download_path: Optional[str], creds: dict) -> str:
        """Performs a request to download a given upload by its ID, optionally saves the
        file to the provided path and returns the final URL that was downloaded."""
        try:
            # No timeouts, chunked uploads, default retry strategy, should be all good?
            with self.client.get(f"/uploads/{upload_id}/download", data=creds, stream=True) as r:
                r.raise_for_status()

                if download_path is not None:  # ...and it will be for external downloads.
                    with tqdm.wrapattr(open(download_path, "wb"), "write",
                                       miniters=1, desc=str(upload_id),
                                       total=int(r.headers.get('content-length', 0))) as f:
                        for chunk in r.iter_content(chunk_size=1048576):  # 1MB chunks
                            f.write(chunk)

                return r.url
        except HTTPError as e:
            raise ItchDownloadError(f"Unrecoverable download error: {e}")

    def download(self, url: str, skip_downloaded: bool = True):
        match = re.match(ITCH_GAME_URL_REGEX, url)
        if not match:
            raise ItchDownloadError(f"Game URL is invalid: {url} - please file a new issue.")

        author, game = match['author'], match['game']

        download_path = os.path.join(self.download_to, author, game)
        os.makedirs(download_path, exist_ok=True)

        paths: Dict[str, str] = {k: os.path.join(download_path, v) for k, v in TARGET_PATHS.items()}

        if os.path.exists(paths['metadata']) and skip_downloaded:
            # As metadata is the final file we write, all the files
            # should already be downloaded at this point.
            logging.info("Skipping already-downloaded game for URL: %s", url)
            return

        logging.info("Downloading %s", url)
        r = self.client.get(url, append_api_key=False)
        if not r.ok:
            raise ItchDownloadError(f"Could not download the game site for {url}")

        site = BeautifulSoup(r.text, features="lxml")
        game_id = self.get_game_id(url, site)

        metadata = self.extract_metadata(game_id, url, site)
        title = metadata['title'] or game

        credentials = self.get_credentials(title, game_id)
        game_uploads_req = self.client.get(f"/games/{game_id}/uploads", data=credentials, timeout=15)
        if not game_uploads_req.ok:
            raise ItchDownloadError(f"Could not fetch game uploads for {title}: {game_uploads_req.text}")

        game_uploads = game_uploads_req.json()['uploads']
        print(f"Found {len(game_uploads)} upload(s)")
        logging.debug(str(game_uploads))

        external_urls = []
        errors = []

        try:
            os.makedirs(paths['files'], exist_ok=True)
            for upload in tqdm(game_uploads, desc=title):
                upload_id = upload['id']
                file_name = upload['filename']
                file_size = upload['size']
                upload_is_external = upload['storage'] == 'external'

                print(f"Downloading '{file_name}' ({upload_id}), {file_size} bytes...")
                target_path = None if upload_is_external else os.path.join(paths['files'], file_name)

                try:
                    target_url = self.download_file(upload_id, target_path, credentials)
                except ItchDownloadError as e:
                    errors.append(f"Download failed for upload {upload}: {e}")
                    continue

                if upload_is_external:
                    logging.info("Found external download URL for %s: %s", target_url)
                    external_urls.append(target_url)

                try:
                    actual_file_size = os.stat(target_path).st_size
                    if actual_file_size != file_size:
                        errors.append(f"File size is {actual_file_size}, but expected {file_size} for upload {upload}")
                except FileNotFoundError:
                    errors.append(f"Downloaded file not found for upload {upload}")

            logging.info("Done downloading files for %s", title)
        except Exception as e:
            error = f"Download failed for {title}: {e}"
            logging.exception(error)
            errors.append(error)

        metadata['errors'] = errors
        metadata['external_downloads'] = external_urls

        if len(external_urls) > 0:
            print(f"WARNING: Game {title} has external download URLs: {external_urls}")

        # TODO: Screenshots and site assets
        with open(paths['site'], 'w') as f:
            f.write(site.prettify())

        with open(paths['metadata'], 'w') as f:
            json.dump(metadata, f)

        logging.info("Finished job %s (%s)", url, title)


def drive_downloads(jobs: List[str], download_to: str, api_key: str, keys: Dict[int, str], parallel: int = 1):
    downloader = GameDownloader(download_to, api_key, keys)

    if parallel > 1:
        results = thread_map(downloader.download, jobs, desc="Games", max_workers=parallel)
    else:
        results = [downloader.download(job) for job in tqdm(jobs, desc="Games")]

    print(results)
