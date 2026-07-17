# Deploy NETO to Streamlit Community Cloud

This directory is a self-contained deployment snapshot. Treat its contents as
the root of the repository that will be connected to Streamlit Community Cloud.

## Repository settings

- Repository root: this directory's contents, not the parent `neto/` folder.
- Default branch: `main`.
- App entrypoint: `app.py`.
- Python version: `3.12` in **Advanced settings**.
- Secrets: none required for the preliminary release.
- System packages: none required.

## Deploy

1. Upload every file and directory in this folder to the root of a GitHub
   repository, including `.streamlit/config.toml`.
2. In Streamlit Community Cloud, choose **Create app** and select that
   repository and its `main` branch.
3. Set **Main file path** to `app.py`.
4. Open **Advanced settings**, choose Python 3.12, and deploy.

`requirements.txt` is pinned to the versions used to validate this snapshot.
The app needs outbound HTTPS access for the existing official-site adapters and
`lol.fandom.com` for Leaguepedia. It does not call GitHub APIs, does not expose
Liquipedia ingestion, and does not require a database, cookies, credentials, or
a browser runtime.

## Preliminary-release boundaries

- Restrict the Streamlit app to the intended internal viewers.
- ParserKey uploads are stored only in Streamlit session state. They disappear
  when that browser session or the app process restarts and are not shared with
  other users.
- Liquipedia URLs are rejected. Only Leaguepedia / LoL Fandom tournament pages
  are accepted by the wiki workflow.
- XLSX uploads are limited to 25 MB. NETO also rejects encrypted archives,
  excessive expanded size, excessive compression ratios, and oversized
  ParserKey execution plans before parsing.

See `docs/parserkey_registration.md` and `docs/tournament_wikis.md` for the
runtime contracts and known limitations.
