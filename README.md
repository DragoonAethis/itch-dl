# Itch Jam Downloader

Downloads all games from a public Itch.io Game Jam.

What you'll need:

- Python 3.8+
- `pip install -r requirements.txt`
- For site mirroring, [wget](https://www.gnu.org/software/wget/) in your PATH.

On Arch, `pacman -S wget python python-requests python-slugify` works.

How to use this:

- Go to your jam's page, ex. https://itch.io/jam/gbcompo21 and right-click -> View Source.
- Ctrl-F for `"id":` - it should find that text once, followed by a number. Write it down.
- (It you found it multiple times, grab the one after ViewJam something something.)
- Download https://itch.io/jam/NUMBER/entries.json (replacing NUMBER with what you wrote down)
- Generate a new API key on your user account page: https://itch.io/user/settings/api-keys
- Run the downloader: `python downloader.py --api-key <KEY> entries.json`
- Wait. This is going to take a while.

The downloader is able to grab more or less everything you can download via the itch app.

It's expected that the downloader output will not be complete - logs are stupidly verbose and
it prints a report on successful/failed downloads, so you must manually grab whatever was not
handled for you automatically for some reason.

The downloader also grabs the entry page HTML, which usually comes with controls and such. It
does not download images, external assets and so on, just the text - if the Itch page dies,
so will most elements on those downloaded pages. Controls should survive, though.

(There's a pedantic mirroring toggle in the script, if you know what you're doing though.)
