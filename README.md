# KinDER site

Static site for KinDER. Pages are generated from markdown files in [environments/](environments/) and Jupyter notebooks pulled in from the `kindergarden` and `kinder-baselines` submodules.

## Setup

Clone with submodules:

```bash
git clone --recurse-submodules <repo-url>
cd kinder-site
```

If you already cloned without `--recurse-submodules`:

```bash
git submodule update --init --recursive
```

Install Python dependencies (using [uv](https://github.com/astral-sh/uv)):

```bash
uv venv
uv pip install -r requirements.txt
```

Plain `pip` works too:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Develop

Run the dev server — it regenerates pages on source changes and live-reloads the browser:

```bash
uv run python dev_server.py
```

Then open http://localhost:8000. Use `--port 8080` to pick a different port, or `--no-initial-regen` to skip the build on startup.

The server watches [index_template.html](index_template.html), [generate_pages.py](generate_pages.py), [env_whitelist.txt](env_whitelist.txt), [styles.css](styles.css), and the markdown/notebook sources under the submodules. CSS-only changes reload without a rebuild.

## Manual build and serve

If you'd rather not use the dev server, you can build and serve in two separate steps.

Regenerate the HTML from the markdown and notebook sources:

```bash
uv run python generate_pages.py
```

You only need to run this when source content changes — the generated HTML is committed to the repo.

Then serve the static files:

```bash
uv run python -m http.server 8000
```

Open http://localhost:8000. You'll need to re-run `generate_pages.py` and refresh the browser yourself when sources change.
