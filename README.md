# Instagram Dump Converter

This project converts Instagram media into a printable/browsable HTML timeline.

It supports export-based input modes only:

- Local Instagram data export JSON files (`media.json`)
- **Browser web app** (`webapp/`) for visitors: ZIP-only, runs entirely in the tab (no upload to your server)

## Contributor Quick Start

```bash
python -m pip install --upgrade pip
pip install -e .
pip install playwright
python -m playwright install --with-deps chromium
python -m unittest discover -s tests -v
```

Notes:

- Use Python 3.12+ to match CI.
- `pip install -e .` installs the local package in editable mode.
- Playwright + Chromium are required for `tests/test_webapp_smoke.py`.

## Usage

### 1) Convert local Instagram export (legacy mode)

```bash
python -m instagramdumpconverter -i <inputdir>
# after `pip install -e .`, you can also run:
instagramdumpconverter -i <inputdir>
```

`<inputdir>` should contain one or more extracted Instagram export folders where each folder includes a `media.json`.

Optional CLI flags:

```bash
python -m instagramdumpconverter -i <inputdir> --theme memory-book --layout grid
python -m instagramdumpconverter -i <inputdir> --doctor
python -m instagramdumpconverter -i <inputdir> --doctor-json
python -m instagramdumpconverter -i <inputdir> --doctor-json-format pretty
python -m instagramdumpconverter -i <inputdir> --doctor-json-pretty
python -m instagramdumpconverter -i <inputdir> --strict --strict-max-missing-media 0
```

- `--doctor` runs input validation + diagnostics only and skips HTML generation.
- `--doctor-json` emits diagnostics as JSON (machine-readable, implies `--doctor`).
- `--doctor-json-format` controls JSON style (`compact` default for CI logs, `pretty` for humans).
- `--doctor-json-pretty` is a shortcut for `--doctor-json-format pretty`.
- `--strict` fails when missing media exceeds threshold.

### 2) Browser web app (random visitors, export-only)

Upload the `webapp/` folder to Hostinger (or any static host). Open `index.html` over **HTTPS** or a local static server (ES module CDN may not work from `file://`).

```bash
cd webapp
python -m http.server 8080
```

Then open `http://localhost:8080/`. Visitors select Instagram export **ZIP** files; processing uses **fflate** in the browser and produces a preview plus a downloadable ZIP containing `index.html`, styles, scripts, and media.

## Output

For local export conversion, the tool writes:

- `index.html`
- `blog.css`
- `css/` and `js/` assets

Output is written into the input directory.

## Compatibility Matrix

| Source | Input format | Status | Notes |
| --- | --- | --- | --- |
| Local export (legacy) | `media.json` + `media/*` files | Supported | Reads extracted folder trees recursively. |
| Local export (newer) | `your_instagram_activity/media/posts_*.json` + `media/posts/...` | Supported | Paths are resolved relative to the export root. |
| Standalone comments/reactions files | e.g. `comments/*.json` sidecar exports | Not rendered per post | Current renderer only uses post/media objects from main posts JSON/API response. |

## Browser App vs CLI

| Capability | Browser app (`webapp/`) | CLI (`python -m instagramdumpconverter`) |
| --- | --- | --- |
| Runs entirely local/no upload | Yes | Yes |
| Input type | ZIP files | Extracted directories |
| Diagnostics summary | Yes (status banner) | Yes (console line before render) |
| Output | Preview tab + downloadable ZIP | Files written to disk |

## Troubleshooting

- **`No Instagram export JSON found`**
  - Select all ZIP parts in browser mode, or point `-i` to the extracted folder containing `your_instagram_activity`.
- **`No posts could be built`**
  - JSON was detected, but media paths were missing from provided ZIPs/folders; include all parts of the export.
- **High missing-media count in diagnostics**
  - Some archives are incomplete or partially extracted; re-download and unzip fully.
- **`E_SCHEMA_POST`**
  - A loader produced malformed post data. This usually indicates an unsupported export structure or corrupted JSON.

## Notes

- Local-export mode still reads local files from extracted dumps.
- Shared parser contract lives in `shared/post_contract.json` (mirrored to `webapp/assets/post_contract.json` for browser validation).
- HTML render snapshot checks live in `tests/test_render_snapshots.py`.
- Web parser/render smoke tests live in `tests/test_webapp_smoke.py` (requires Playwright in the local environment).
- CI runs via `.github/workflows/ci.yml` (syntax check + full unittest suite + Playwright smoke tests).