# itch-dl

[![PyPI](https://img.shields.io/pypi/v/itch-dl)](https://pypi.org/project/itch-dl/)

Bulk download games from [itch.io](https://itch.io/)

- Can handle links with:
  - [Game jams](https://itch.io/jams) (ex. https://itch.io/jam/gmtk-2023 or https://itch.io/jam/gbcompo23),
  - [Browse pages](https://itch.io/games) (popular, newest, browse by tag...),
  - [Collections](https://itch.io/my-collections) (ex. https://itch.io/c/4187503/test-collection),
  - [Your library](https://itch.io/my-purchases),
  - Individual games and titles (ex. https://maddymakesgamesinc.itch.io/celeste,
    https://dragonruby.itch.io/dragonruby-gtk, or https://supergiant-games.itch.io/pyre).
- Currently **NOT** supported:
  - Bundles ([#11](https://github.com/DragoonAethis/itch-dl/issues/11))
  - Access restricted games ([#16](https://github.com/DragoonAethis/itch-dl/issues/16))
- Requires Python 3.8+, grab it from [PyPI](https://pypi.org/project/itch-dl/): `pip install itch-dl`
- For development, use [Poetry](https://python-poetry.org/).

> [!WARNING]
> This tool does not let you download paid games for free. To download paid games, you must have
> them attached in [your library](https://itch.io/my-purchases).


## How to use

- Log into itch.io with the account you'd like to use for downloading.
- Generate [a new API key](https://itch.io/user/settings/api-keys) on your user account page.
- Optional: Save the API key in the [itch-dl configuration file](https://github.com/DragoonAethis/itch-dl/wiki/Configuration-Files).
- Run the downloader: `itch-dl https://itch.io/jam/yourjamhere` (add `--api-key <KEY>` if you did not save the API key).
- Wait. This is going to take a while.

More arguments are available - check them out with `itch-dl --help`.

The downloader is able to grab more or less everything you can download via the itch app.

The input URL can be one of the supported link formats listed above, a path to a itch.io JSON
file with game jam entries, a list of itch.io game URLs (not browse/jam pages!) to download.

**It's expected that the downloader output will not be complete** - logs are stupidly verbose
and it prints a report on failed downloads and external URLs (links to files that are not on
itch.io itself, but rather on an external host like Google Drive, Dropbox, etc), so you must
manually grab whatever was not handled for you automatically.

The downloader also grabs the entry page HTML, which usually comes with controls and such. By
default, it does not download images, assets and so on, just the text - use `--mirror-web` to
try and download these as well. This does not work very well yet, but gets the basics done.


## Game Jam Entries JSON

Downloader can parse and download games from a game jam entries JSON file if you need it.
(The script basically automates the steps below, so if it's not able to do the same, please
create an issue!)

- Go to your jam's page, ex. https://itch.io/jam/gbcompo21 and right-click -> View Source.
- Ctrl-F for `"id":` - it should find that text once, followed by a number. Write it down.
- (It you found it multiple times, grab the one after I.ViewJam something something.)
- Download https://itch.io/jam/ID/entries.json (replacing ID with what you wrote down).
- Feed that to `itch-dl`!
