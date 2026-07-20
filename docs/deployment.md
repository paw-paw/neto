# Deploy NETO to Streamlit Community Cloud

This public repository contains the minimum NETO runtime intended for Streamlit Community Cloud. Do not add validation workbooks, private URLs, manifests, logs, or private validation material to a deployment branch.

## App settings

- Repository: `paw-paw/neto`
- Branch: `main`
- Main file path: `app.py`
- Python: `3.12`
- Secrets: none for the current runtime
- System packages: none

In Streamlit Community Cloud, create an app from the repository, apply these settings, and deploy. `requirements.txt` contains only runtime packages and uses pinned versions for reproducibility.

## Required network access

The app needs outbound HTTPS access to:

- `docs.google.com` and Google-owned download redirect hosts;
- `lolesports.com` and `valorantesports.com`;
- `callofdutyleague.com`;
- `www.ubisoft.com`;
- `lol.fandom.com`.

NETO does not call the GitHub API at runtime. It requires no database, private Google authentication, browser automation, credentials, cookies, or analytics token. The optional `NETO_RIOT_HOME_EVENTS_HASH` environment variable is a non-secret compatibility override for Riot's public persisted query.

## Runtime boundaries

- ParserKey uploads live only in Streamlit session state. They are not written to GitHub or shared with other sessions.
- Google Sheets and uploaded XLSX files are processed in memory. Upload and archive-expansion limits are enforced before parsing.
- Only allowlisted official sources and Leaguepedia / LoL Fandom tournament URLs are accepted.
- Liquipedia and arbitrary URL fetching are disabled.
- Network successes may be cached in the Streamlit process; failures are not persisted.

Before promoting a deployment, require the public deployment-smoke workflow to pass and complete validation outside this repository. Never copy validation output or source material into a Pull Request.
