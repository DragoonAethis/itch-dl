# itch-dl

Bulk download games from [itch.io](https://itch.io/).

- Can download game jams, browse pages (popular, newest, browse by tag...) and individual games.
- Requires Python 3.8+, grab it from PyPI: `pip install itch-dl`
- For development, use [Poetry](https://python-poetry.org/).
- Optionally requires wget for site mirroring.

How to use this:

- Log into itch.io with the account you'd like to use for downloading.
- Generate a new API key on your user account page: https://itch.io/user/settings/api-keys
- Run the downloader: `itch-dl --api-key <KEY> https://itch.io/jam/yourjamhere`
- Wait. This is going to take a while.

The downloader is able to grab more or less everything you can download via the itch app.

The input URL can be any "Browse" page (top, popular, newest, filtered by tags, etc) or any
game jam. The input can also be a path to a itch.io JSON file with game jam entries, or just
a list of itch.io game URLs (not browse/jam pages!) to download.

**It's expected that the downloader output will not be complete** - logs are stupidly verbose
and it prints a report on successful/failed downloads, so you must manually grab whatever was
not handled for you automatically for some reason.

The downloader also grabs the entry page HTML, which usually comes with controls and such. By
default, it does not download images, assets and so on, just the text - use `--mirror-web` to
try and download these as well. This requires `wget` to be available in your `PATH`.


## Game Jam Entries JSON

Downloader can parse and download games from a game jam entries JSON file if you need it.
(The script basically automates the steps below, so if it's not able to do the same, please
create an issue!)

- Go to your jam's page, ex. https://itch.io/jam/gbcompo21 and right-click -> View Source.
- Ctrl-F for `"id":` - it should find that text once, followed by a number. Write it down.
- (It you found it multiple times, grab the one after I.ViewJam something something.)
- Download https://itch.io/jam/ID/entries.json (replacing ID with what you wrote down).
- Feed that to `itch-dl`!
