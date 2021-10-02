# Itch Jam Downloader

Downloads all games from a public Itch.io Game Jam.

What you'll need:

- Python 3.8+
- `pip install -r requirements.txt`
- [chromedriver](https://chromedriver.chromium.org/downloads) somewhere in your PATH

On Arch, `pacman -S python chromium python-selenium python-requests python-slugify` works.

How to use this:

- Go to your jam's page, ex. https://itch.io/jam/gbcompo21 and right-click -> View Source.
- Ctrl-F for `"id":` - it should find that text once, followed by a number. Write it down.
- Download https://itch.io/jam/NUMBER/entries.json (replacing NUMBER with what you wrote down)
- Run the downloader: `python downloader.py entries.json`
- Wait. This is going to take a while.

**This downloader does not (and probably will not) support HTML5-only games.** (For some of
these, you might get lucky by hitting F12 while the game loads and grabbing what's in there.)

It's expected that the downloader output will not be complete - logs are stupidly verbose and
it prints a report on successful/failed downloads, so you must manually grab whatever was not
handled for you automatically for some reason.

The downloader also grabs the entry page HTML, which usually comes with controls and such. It
does not download images, external assets and so on, just the text - if the Itch page dies,
so will most elements on those downloaded pages. Controls should survive, though.
