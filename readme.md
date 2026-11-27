![Conventional Commits](https://img.shields.io/badge/Conventional_Commits-FE5196?style=flat&logo=conventionalcommits&logoColor=white)

# Samsung Frame Art

Gets and optimizes artwork for Samsung Frame TVs, bypassing the subscription.

`get.py` finds each painting in `artlist.json` on Wikimedia Commons, WikiArt, or museum open-access APIs, then picks the most detailed and warmest reproduction, crops it to 16:9 at `3840×2160`, and saves it to `art/` as `Artist (year) - Title.jpg`

`optimize.py` does the same crop and sizing for your own images: anything in `raw/` is saved to `art/` under the same name.

Downloaded art can be synced to TV via USB or SmartThings App.

### Usage

Requires Python ≥ 3.10
After cloning this repo get art like:

**Using `uv`:**
```sh
uv run get.py # get all of artlist.json
uv run get.py --only Vermeer # get partial match (supports comma delimited)
uv run get.py -r # replace images already in art/ (default skips them)
uv run get.py --matte # also make matted variants of portrait works
```
**Using `pip`:**
```sh
pip3 install requests pillow numpy && python3 get.py
```
**Arguments:**
- Works already in `art/` are skipped before any lookup, so edited images are safe; `-r` (`--replace`) re-fetches and overwrites them
- Output is edge to edge; matted variants are only made with `--matte`
- `--list` and `--out` point at a different list or output folder
- For fewer Wikimedia rate limits provide contact info like `FRAME_ART_UA="FrameArtPrep/1.0 (you@foo.com)" uv run get.py`

**Your own images:**
```sh
uv run optimize.py # crop and size everything in raw/ into art/
uv run optimize.py --only Magritte # partial match, like get.py
uv run optimize.py --anchor 0.3 # fixed crop position instead of focal area (0 = left/top, 1 = right/bottom)
```

- `-r` and `--matte` work the same as in `get.py`; files in `raw/` are never changed
- Hyphenated names like `Leonora-Carrington-(1953)---Title.jpg` are saved as `Leonora Carrington (1953) - Title.jpg`

### Directories

- `art/`: finished `3840×2160` images, plus custom added artwork named the same way
- `raw/`: your own images for `optimize.py`
- `temp/`: downloads, lookup cache, `get.log`, `report.json`, and `review.html` (each pick next to the alternatives it beat)

### Art selection

The process runs like:
1. Matches painting on Wikidata by title/artist/date, fetches every such matching copy to temp
2. Drops area outside shot, framed shots, look-alikes, alternate versions, and proportions that don't match
3. If Commons has nothing big enough for a `2160px`-tall crop, also checks the Met, Art Institute of Chicago and Cleveland Museum of Art (public-domain images only) and WikiArt
4. Ranks by resolution, museum scans, color warmth (yellows > whites)
5. Crops to 16:9 around focal area

### Struct

Target art can live in `artlist.json` and be structured like:

```json
{"artist": "Johannes Vermeer", "year": 1669, "title": "The Geographer"}
```

| Field | |
| --- | --- |
| `artist`, `year`, `title` | make up the filename; also used to find the work |
| `queries` | extra search terms, e.g. original-language titles |
| `note` | shown on the review page |
| `exclude` | regex of look-alike source filenames to reject |
| `match` | name sources must contain, if not the artist's last word |
| `file` | use this exact Commons file (`"File:…"`) |
| `local` | use a file on disk instead |
| `url` | download this image URL instead (any site) |
| `anchor` | crop position, 0 (left/top) to 1 (right/bottom) |

Keys starting with `_` are ignored. The `manual` list is for works you add to `art/` yourself; `review.html` shows which are there.

### Commit messages

Commits must use a conventional prefix, `.githooks/` rejects anything else.

Allowed types: `feat`, `fix`, `hotfix`, `refactor`, `style`, `chore`, `cleanup`, `perf`, `test`, `docs`, `content`

`changelog.md` tracks these changes, generate commits with [git-cliff](https://git-cliff.org):

```sh
git cliff -o changelog.md
```

Commit types map to sections: `feat` to _Added_, `refactor` / `cleanup` / `style` to _Changed_, `fix` / `hotfix` to _Fixed_, `perf` to _Performance_, `docs` / `content` to _Documentation_, `test` to _Tests_. `chore` commits are left out.
