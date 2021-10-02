#!/usr/bin/env python3
# Python 3.8+ and dependencies listed below required.
import os
import sys
import json
import time
import hashlib
import argparse
import traceback
from enum import Enum
from multiprocessing import Pool

import requests
from slugify import slugify

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException


class ItchDownloadResult(Enum):
	SUCCESS = 0
	FAILURE = 1
	MISSING_DOWNLOAD = 2
	DOWNLOAD_TIMEOUT = 3


def parse_jobs(jam_json: dict) -> list[tuple[int, str, str]]:
	if 'jam_games' not in jam_json:
		raise Exception("Provided JSON is not a valid itch.io jam JSON.")

	# Extract (id, url) pairs from all the entries.
	return [(e['game']['id'], e['game']['title'], e['game']['url']) for e in jam_json['jam_games']]


def try_extract_download_links(driver: webdriver.Chrome, title_url: str) -> list[str]:
	elems = driver.find_elements(By.CLASS_NAME, "download_btn")
	if len(elems) == 0:
		raise NoSuchElementException("No download links found.")

	cookie = driver.get_cookie("itchio_token")['value']
	file_ids = [elem.get_attribute("data-upload_id") for elem in elems]
	file_urls = []

	for file_id in file_ids:
		meta_url = f"{title_url}/file/{file_id}"
		r = requests.post(meta_url, data={"csrf_token": cookie})
		if r.ok:
			file_urls.append(r.json()['url'])
		else:
			print(f"Error downloading metadata for file {file_id} (status {r.status_code}): {r.text}")

	print(f"Extracted URLs: {file_urls}")
	return file_urls


def download_link(link: str, path: str) -> tuple[bool, str]:
	r = requests.get(link)
	if not r.ok:
		return (False, r.reason)

	# The bytes we need:
	content = r.content

	# Figure out the filename:
	if 'Content-Disposition' in r.headers:
		name = r.headers['Content-Disposition']
		name = name.removeprefix('attachment; filename="').removesuffix('"')
	else:  # uhhhh random bullshit go, good luck?
		md5 = hashlib.md5()
		md5.update(content)
		name = md5.hexdigest()

	# Make sure we don't overwrite files with the same name.
	fcounter = 1
	filename = f"{path}/{name}"
	while os.path.exists(filename):
		fcounter += 1
		filename = f"{path}/{name}.{fcounter}"

	try:
		with open(filename, 'wb') as f:
			f.write(content)
	except Exception as e:
		return (False, f"Cannot write output file: {e}")

	return (True, "Success")


def download_files(links, path) -> list[tuple[bool, str]]:
	if len(links) == 0:
		print(f"Nothing to download into {path}")
		return []

	with Pool(len(links)) as p:
		results = p.starmap(download_link, [(link, path) for link in links])
		return results


def parse_download_results(results, method) -> tuple[ItchDownloadResult, str]:
	global_success = True
	for success, reason in results:
		if not success:
			print(f"Download failed: {reason}")
			global_success = False

	if global_success:
		return (ItchDownloadResult.SUCCESS, f"Method #{method} successful.")
	else:
		return (ItchDownloadResult.FAILURE, f"Method #{method} partially successful (downloads failed).")


def download_title(title_id: int, title_url: str, download_path: str) -> (ItchDownloadResult, str):
	options = Options()
	options.add_argument("--headless")

	with webdriver.Chrome(options=options) as driver:
		wait = WebDriverWait(driver, timeout=15)
		driver.get(title_url)

		with open(f"{download_path}/index.html", 'w') as f:
			f.write(driver.page_source)

		skip_purchase_locator = (By.CLASS_NAME, "direct_download_btn")

		try:
			print("Trying method #1: Purchase Workflow")
			elem = driver.find_element(By.CLASS_NAME, "buy_btn")
			elem.click()

			elem = wait.until(EC.presence_of_element_located(skip_purchase_locator))
			elem.click()

			wait.until(EC.number_of_windows_to_be(2))
			time.sleep(1)
			
			first_tab = driver.current_window_handle
			for window_handle in driver.window_handles:
				if window_handle != first_tab:
					driver.switch_to.window(window_handle)
					break

			# We're now on the main downloads page.
			download_links = try_extract_download_links(driver, title_url)
			results = download_files(download_links, download_path)
			return parse_download_results(results, 1)
		except TimeoutException:
			print("Method #1 took too long - sleeping for 1m to avoid ~ mystery funsies ~")
			time.sleep(60)

			return ItchDownloadResult.DOWNLOAD_TIMEOUT, "Download timed out"
		except NoSuchElementException:
			print("Method #1 failed.")

		try:
			print("Trying method #2: Direct Download Workflow")
			download_links = try_extract_download_links(driver, title_url)
			results = download_files(download_links, download_path)
			return parse_download_results(results, 2)
		except NoSuchElementException:
			print("Method #2 failed.")

		print("File links missing/no method able to handle target URL.")
		return ItchDownloadResult.MISSING_DOWNLOAD, "No download method worked."

def download_jam(path_to_json: str, continue_from: str=None):
	try:
		with open(path_to_json) as f:
			jam_json = json.load(f)
	except FileNotFoundError:
		print(f"File {path_to_json} not found.")
	except json.decoder.JSONDecodeError:
		print(F"Provided file is not a valid JSON file.")

	jobs = parse_jobs(jam_json)
	jobs_successful = []
	jobs_failed = []

	# No "continue from"? Yep, start right away.
	should_process_jobs = continue_from is None

	for job in jobs:
		game_id, title, url = job
		if not should_process_jobs:
			if game_id == continue_from:
				should_process_jobs = True
			else:
				continue

		r = requests.get(f"{url}/data.json")
		if r.status_code != 200:
			print(f"Missing data for {url}, probably invalid")
			failed_jobs += url
			continue

		download_path = os.path.join(os.getcwd(), slugify(title))
		print(f"Trying to download {title} ({game_id}) to {download_path}")

		if not os.path.isdir(download_path):
			os.mkdir(download_path)

		try:
			status, message = download_title(game_id, url, download_path)
			print(f"{title}: {status}, {message}")

			if status == ItchDownloadResult.SUCCESS:
				jobs_successful.append((title, download_path))
			else:
				jobs_failed.append((status, title, url, message))
		except Exception as e:
			print(f"Download failed for {title} ({game_id}): {e}")
			traceback.print_exc()
			continue

	print(f"\nAll done, downloaded files successfully for {len(jobs_successful)} title(s):")
	for title, download_path in jobs_successful:
		print(title)

	print(f"\nDownloads failed for {len(jobs_failed)} title(s):")
	for status, title, url, message in jobs_failed:
		print(f"{title} - {url} - {status}: {message}")


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Downloads games from public Itch.io game jams.")
	parser.add_argument("entries", help="path to the game jam entries.json file")
	parser.add_argument("--continue-from", metavar="ID", help="skip all entries until the provided entry ID is found")
	args = parser.parse_args()

	continue_id = args.continue_from
	if continue_id is not None:
		try:
			continue_id = int(continue_id)
		except:
			print("ID to continue from must be an integer.")
			exit(1)

	download_jam(args.entries, continue_from=continue_id)
