![Conventional Commits](https://img.shields.io/badge/Conventional_Commits-FE5196?style=flat&logo=conventionalcommits&logoColor=white)

# Samsung Frame Art

Gets and optimizes artwork for Samsung Frame TVs, bypassing the subscription.

`get.py` finds each painting in `artlist.json` on Wikimedia Commons, picks the most detailed and warmest reproduction, crops it to 16:9 at `3840×2160`, and saves it to `art/` as `Artist (year) - Title.jpg`

Downloaded art can be synced to TV via USB or SmartThings App.

### Usage

Requires Python ≥ 3.10

(Example uses `uv` to run python)
```sh
uv run get.py # get all of artlist.json
uv run get.py --only Vermeer # get partial match (supports comma delimited)
uv run get.py --no-matte # skip matted variants
```

- Without `uv` run like: `pip3 install requests pillow numpy && python3 get.py`
- `--list` and `--out` point at a different list or output folder
- For fewer Wikipedia timeouts provide contact info like `FRAME_ART_UA="FrameArtPrep/1.0 (you@foo.com)" uv run get.py`

### Directories

- `art/`: finished `3840×2160` images
- `temp/`: downloads, lookup cache
- `manual/`: custom added artwork

### Art selection

The process runs like:
1. Matches painting on Wikidata by title/artist/date, fetches every such matching copy to temp
2. Drops area outside shot, framed shots, look-alikes, alternate versions, and proportions that don't match
3. Ranks by resolution, museum scans, color warmth (yellows > whites)
4. Crops to 16:9 around focal area

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
| `anchor` | crop position, 0 (left/top) to 1 (right/bottom) |

Keys starting with `_` are ignored

### Commit messages

Commits must use a conventional prefix, `.githooks/` rejects anything else.

Allowed types: `feat`, `fix`, `hotfix`, `refactor`, `style`, `chore`, `cleanup`, `perf`, `test`, `docs`, `content`

`changelog.md` tracks these changes, generate commits with [git-cliff](https://git-cliff.org):

```sh
git cliff -o changelog.md
```

Commit types map to sections: `feat` to _Added_, `refactor` / `cleanup` / `style` to _Changed_, `fix` / `hotfix` to _Fixed_, `perf` to _Performance_, `docs` / `content` to _Documentation_, `test` to _Tests_. `chore` commits are left out.
