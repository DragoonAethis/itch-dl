import os
import json
import re
import logging
import urllib.parse
from typing import List, Dict, TypedDict, Optional, Union

from bs4 import BeautifulSoup
from requests.exceptions import HTTPError

from tqdm import tqdm
from tqdm.contrib.concurrent import thread_map

from .api import ItchApiClient
from .utils import ItchDownloadError, get_int_after_marker_in_json
from .consts import ITCH_GAME_URL_REGEX
from .config import Settings
from .infobox import parse_infobox, InfoboxMetadata

TARGET_PATHS = {
    'site': 'site.html',
    'cover': 'cover',
    'metadata': 'metadata.json',
    'files': 'files',
    'screenshots': 'screenshots'
}


class DownloadResult:
    def __init__(self, url: str, success: bool, errors, external_urls: List[str]):
        self.url = url
        self.success = success
        self.errors = errors or []
        self.external_urls = external_urls or []


class GameMetadata(TypedDict, total=False):
    game_id: int
    title: str
    url: str

    errors: List[str]
    external_downloads: List[str]

    author: str
    author_url: str

    cover_url: Optional[str]
    screenshots: List[str]
    description: Optional[str]

    rating: Dict[str, Union[float, int]]
    extra: InfoboxMetadata

    created_at: str
    updated_at: str
    released_at: str
    published_at: str


class GameDownloader:
    def __init__(self, download_to: str, mirror_web: bool, settings: Settings, keys: Dict[int, str]):
        self.download_to = download_to
        self.mirror_web = mirror_web

        self.download_keys = keys
        self.client = ItchApiClient(settings.api_key, settings.user_agent)

    @staticmethod
    def get_rating_json(site) -> Optional[dict]:
        for ldjson_node in site.find_all("script", type="application/ld+json"):
            try:
                ldjson: dict = json.loads(ldjson_node.text.strip())
                if ldjson.get("@type") == "Product":
                    return ldjson
            except json.JSONDecodeError:
                continue  # Can't do much with this...

        return None

    @staticmethod
    def get_meta(site, **kwargs) -> Optional[str]:
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
        rating_json: Optional[dict] = self.get_rating_json(site)
        title = rating_json.get("name") if rating_json else None

        description: Optional[str] = self.get_meta(site, property="og:description")
        if not description:
            description = self.get_meta(site, name="description")

        screenshot_urls: List[str] = []
        screenshots_node = site.find("div", class_="screenshot_list")
        if screenshots_node:
            screenshot_urls = [a['href'] for a in screenshots_node.find_all('a')]

        metadata = GameMetadata(
            game_id=game_id,
            title=title or site.find("h1", class_="game_title").text.strip(),
            url=url,
            cover_url=self.get_meta(site, property="og:image"),
            screenshots=screenshot_urls,
            description=description,
        )

        infobox_div = site.find("div", class_="game_info_panel_widget")
        if infobox_div:
            infobox = parse_infobox(infobox_div)
            for dt in ('created_at', 'updated_at', 'released_at', 'published_at'):
                if dt in infobox:
                    metadata[dt] = infobox[dt].isoformat()  # noqa (non-literal TypedDict keys)
                    del infobox[dt]  # noqa (non-literal TypedDict keys)

            if 'author' in infobox:
                metadata['author'] = infobox['author']['author']
                metadata['author_url'] = infobox['author']['author_url']
                del infobox['author']

            if 'authors' in infobox and 'author' not in metadata:
                # Some games may have multiple authors (ex. compilations).
                metadata['author'] = "Multiple authors"
                metadata['author_url'] = f"https://{urllib.parse.urlparse(url).netloc}"

            metadata['extra'] = infobox

        agg_rating = rating_json.get('aggregateRating') if rating_json else None
        if agg_rating:
            try:
                metadata['rating'] = {
                    'average': float(agg_rating['ratingValue']),
                    'votes': agg_rating['ratingCount']
                }
            except:  # noqa
                logging.exception("Could not extract the rating metadata...")
                pass  # Nope, just, don't

        return metadata

    def get_credentials(self, title: str, game_id: int) -> dict:
        credentials = {}
        if game_id in self.download_keys:
            credentials['download_key_id'] = self.download_keys[game_id]
            logging.debug("Got credentials for %s: %s", title, str(credentials))

        return credentials

    def download_file(self, url: str, download_path: Optional[str], credentials: dict) -> str:
        """Performs a request to download a given file, optionally saves the
        file to the provided path and returns the final URL that was downloaded."""
        try:
            # No timeouts, chunked uploads, default retry strategy, should be all good?
            with self.client.get(url, data=credentials, stream=True, guess_encoding=True) as r:
                r.raise_for_status()

                if download_path is not None:  # ...and it will be for external downloads.
                    with tqdm.wrapattr(open(download_path, "wb"), "write",
                                       miniters=1, desc=url,
                                       total=int(r.headers.get('content-length', 0))) as f:
                        for chunk in r.iter_content(chunk_size=1048576):  # 1MB chunks
                            f.write(chunk)

                return r.url
        except HTTPError as e:
            raise ItchDownloadError(f"Unrecoverable download error: {e}")

    def download_file_by_upload_id(self, upload_id: int, download_path: Optional[str], credentials: dict) -> str:
        """Performs a request to download a given upload by its ID."""
        return self.download_file(f"/uploads/{upload_id}/download", download_path, credentials)

    def download(self, url: str, skip_downloaded: bool = True):
        match = re.match(ITCH_GAME_URL_REGEX, url)
        if not match:
            return DownloadResult(url, False, [f"Game URL is invalid: {url} - please file a new issue."], [])

        author, game = match['author'], match['game']

        download_path = os.path.join(self.download_to, author, game)
        os.makedirs(download_path, exist_ok=True)

        paths: Dict[str, str] = {k: os.path.join(download_path, v) for k, v in TARGET_PATHS.items()}

        if os.path.exists(paths['metadata']) and skip_downloaded:
            # As metadata is the final file we write, all the files
            # should already be downloaded at this point.
            logging.info("Skipping already-downloaded game for URL: %s", url)
            return DownloadResult(url, True, [f"Game already downloaded."], [])

        try:
            logging.info("Downloading %s", url)
            r = self.client.get(url, append_api_key=False)
            r.raise_for_status()
        except Exception as e:
            return DownloadResult(url, False, [f"Could not download the game site for {url}: {e}"], [])

        site = BeautifulSoup(r.text, features="lxml")
        try:
            game_id = self.get_game_id(url, site)
            metadata = self.extract_metadata(game_id, url, site)
            title = metadata['title'] or game
        except ItchDownloadError as e:
            return DownloadResult(url, False, [str(e)], [])

        credentials = self.get_credentials(title, game_id)
        try:
            game_uploads_req = self.client.get(f"/games/{game_id}/uploads", data=credentials, timeout=15)
            game_uploads_req.raise_for_status()
        except Exception as e:
            return DownloadResult(url, False, [f"Could not fetch game uploads for {title}: {e}"], [])

        game_uploads = game_uploads_req.json()['uploads']
        logging.debug("Found %d upload(s): %s", len(game_uploads), str(game_uploads))

        external_urls = []
        errors = []

        try:
            os.makedirs(paths['files'], exist_ok=True)
            for upload in game_uploads:
                if any([key not in upload for key in ('id', 'filename', 'storage')]):
                    errors.append(f"Upload metadata incomplete: {upload}")
                    continue

                upload_id = upload['id']
                file_name = upload['filename']
                file_size = upload.get('size')
                upload_is_external = upload['storage'] == 'external'

                logging.debug("Downloading '%s' (%d), %s",
                              file_name, upload_id,
                              f"{file_size} bytes" if file_size is not None else "unknown size")

                target_path = None if upload_is_external else os.path.join(paths['files'], file_name)

                try:
                    target_url = self.download_file_by_upload_id(upload_id, target_path, credentials)
                except ItchDownloadError as e:
                    errors.append(f"Download failed for upload {upload}: {e}")
                    continue

                if upload_is_external:
                    logging.debug("Found external download URL for %s: %s", target_url)
                    external_urls.append(target_url)

                try:
                    downloaded_file_size = os.stat(target_path).st_size
                    if target_path is not None and file_size is not None and downloaded_file_size != file_size:
                        errors.append(f"File size is {downloaded_file_size}, expected {file_size} for upload {upload}")
                except FileNotFoundError:
                    errors.append(f"Downloaded file not found for upload {upload}")

            logging.debug("Done downloading files for %s", title)
        except Exception as e:
            errors.append(f"Download failed for {title}: {e}")

        metadata['errors'] = errors
        metadata['external_downloads'] = external_urls

        if len(external_urls) > 0:
            logging.warning(f"Game {title} has external download URLs: {external_urls}")

        # TODO: Mirror JS/CSS assets
        if self.mirror_web:
            os.makedirs(paths['screenshots'], exist_ok=True)
            for screenshot in metadata['screenshots']:
                if not screenshot:
                    continue

                file_name = os.path.basename(screenshot)
                try:
                    self.download_file(screenshot, os.path.join(paths['screenshots'], file_name), credentials={})
                except Exception as e:
                    errors.append(f"Screenshot download failed (this is not fatal): {e}")

        cover_url = metadata.get('cover_url')
        if cover_url:
            try:
                self.download_file(cover_url, paths['cover'] + os.path.splitext(cover_url)[-1], credentials={})
            except Exception as e:
                errors.append(f"Cover art download failed (this is not fatal): {e}")

        with open(paths['site'], 'wb') as f:
            f.write(site.prettify(encoding='utf-8'))

        with open(paths['metadata'], 'w') as f:
            json.dump(metadata, f, indent=4)

        if len(errors) > 0:
            logging.error(f"Game {title} has download errors: {errors}")

        logging.info("Finished job %s (%s)", url, title)
        return DownloadResult(url, len(errors) == 0, errors, external_urls)


def drive_downloads(
        jobs: List[str],
        download_to: str,
        mirror_web: bool,
        settings: Settings,
        keys: Dict[int, str],
        parallel: int = 1
):
    downloader = GameDownloader(download_to, mirror_web, settings, keys)
    tqdm_args = {
        "desc": "Games",
        "unit": "game",
    }

    if parallel > 1:
        results = thread_map(downloader.download, jobs, max_workers=parallel, **tqdm_args)
    else:
        results = [downloader.download(job) for job in tqdm(jobs, **tqdm_args)]

    print("Download complete!")
    for result in results:
        if not result.errors and not result.external_urls:
            continue

        if result.success:
            print(f"\nNotes for {result.url}:")
        else:
            print(f"\nDownload failed for {result.url}:")

        for error in result.errors:
            print(f"- {error}")

        for ext_url in result.external_urls:
            print(f"- External download URL (download manually!): {ext_url}")
