#!/usr/bin/env python3
# Python 3.8+ and dependencies listed below required.
import os
import sys
import json
import time
import shutil
import hashlib
import argparse
import traceback
import subprocess
from enum import Enum

import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

from slugify import slugify

WGET_PATH = shutil.which("wget")
if WGET_PATH is None:
	print(f"Warning: wget not available, site mirroring will not work!")

# Try to download all site assets, images etc included.
# You probably don't want this, but here you go!
PEDANTIC_MIRRORING = False

ITCH_API = "https://api.itch.io"


class ItchDownloadResult(Enum):
	SUCCESS = 0
	FAILURE = 1
	MISSING_DOWNLOAD = 2
	DOWNLOAD_TIMEOUT = 3


class ItchDownloadError(Exception):
	pass


class ItchApiClient():
	def __init__(self, base_url: str, api_key: str):
		self.base_url = base_url
		self.api_key = api_key

		self.requests = requests.Session()

		retry_strategy = Retry(
			total=5,
			backoff_factor=10,
			allowed_methods=["HEAD", "GET"],
			status_forcelist=[429, 500, 502, 503, 504]
		)

		# No timeouts - set them explicitly on API calls below!
		adapter = HTTPAdapter(max_retries=retry_strategy)
		self.requests.mount("https://", adapter)
		self.requests.mount("http://", adapter)

	def add_api_key(self, kwargs):
		# Adds the API key to request params, if one was not
		# already provided outside of the client.
		if 'data' in kwargs:
			params = kwargs['data']
		else:
			params = {}
			kwargs['data'] = params

		if 'api_key' not in params:
			params['api_key'] = self.api_key

	def get(self, endpoint: str, *args, **kwargs):
		self.add_api_key(kwargs)
		return self.requests.get(self.base_url + endpoint, *args, **kwargs)


def download_file(client: ItchApiClient, upload_id: int, download_path: str, print_url: bool=False):
	# No timeouts, chunked uploads, default retry strategy, should be all good?
	try:
		with client.get(f"/uploads/{upload_id}/download", stream=True) as r:
			r.raise_for_status()
			if print_url:
				print(f"Download URL: {r.url}")

			with open(download_path, 'wb') as f:
				for chunk in r.iter_content(chunk_size=1048576):  # 1MB chunks
					f.write(chunk)
	except requests.exceptions.HTTPError as e:
		raise ItchDownloadError(f"Unrecoverable download error: {e}")


def get_download_keys(client: ItchApiClient):
	print("Fetching all download keys...")
	download_keys = {}
	page = 1

	while True:
		print(f"Downloading page {page}...")
		try:
			r = client.get("/profile/owned-keys", data={"page": page}, timeout=15)
			r.raise_for_status()
		except Exception as e:
			print(f"Got error while fetching download keys: {e}")
			print(f"Let's just pretend this is enough and move on...")
			break

		data = r.json()
		if 'owned_keys' not in data:
			break  # Assuming we're out of keys already...

		for key in data['owned_keys']:
			download_keys[key['game_id']] = key['id']

		if len(data['owned_keys']) == data['per_page']:
			page += 1
		else:
			break

	print(f"Fetched {len(download_keys)} download keys.")
	return download_keys


def parse_jobs(jam_json: dict) -> list[tuple[int, str, str]]:
	if 'jam_games' not in jam_json:
		raise Exception("Provided JSON is not a valid itch.io jam JSON.")

	# Extract (id, url) pairs from all the entries.
	return [(int(e['game']['id']), e['game']['title'], e['game']['url']) for e in jam_json['jam_games']]


def download_jam(path_to_json: str, download_to: str, api_key: str, continue_from: str=None):
	try:
		with open(path_to_json) as f:
			jam_json = json.load(f)
	except FileNotFoundError:
		print(f"File {path_to_json} not found.")
	except json.decoder.JSONDecodeError:
		print(F"Provided entries file is not a valid JSON file.")

	client = ItchApiClient(ITCH_API, api_key)

	# Check API key validity:
	profile_req = client.get("/profile")
	if not profile_req.ok:
		print(f"Provided API key appears to be invalid: {profile_req.text}")
		exit(1)

	jobs = parse_jobs(jam_json)
	jobs_successful = []
	jobs_failed = []

	download_keys = get_download_keys(client)
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
		if game_id in download_keys:
			creds['download_key_id'] = download_keys[game_id]
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
					download_file(client, upload_id, target_path, print_url=upload_is_external)
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


def get_parser():
	parser = argparse.ArgumentParser(description="Downloads games from public Itch.io game jams.")
	parser.add_argument("entries", help="path to the game jam entries.json file")
	parser.add_argument("--api-key", metavar="key", required=True, help="itch.io API key from https://itch.io/user/settings/api-keys")
	parser.add_argument("--download-to", metavar="path", help="directory to save results into (default: current dir)")
	parser.add_argument("--continue-from", metavar="id", type=int, help="skip all entries until the provided entry ID is found")
	return parser


def get_download_dir(args: argparse.Namespace) -> str:
	download_to = os.getcwd()
	if args.download_to is not None:
		download_to = os.path.normpath(args.download_to)
		os.makedirs(download_to)


if __name__ == "__main__":
	args = get_parser().parse_args()
	download_to = get_download_dir(args)
	download_jam(args.entries, download_to, args.api_key, continue_from=args.continue_from)
