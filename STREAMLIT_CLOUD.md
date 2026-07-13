# Deploy NETO to Streamlit Community Cloud

This directory is a self-contained deployment snapshot. Treat its contents as
the root of the repository that will be connected to Streamlit Community Cloud.

## Repository settings

- Repository root: this directory's contents, not the parent `neto/` folder.
- Default branch: `main`.
- App entrypoint: `app.py`.
- Python version: `3.12` in **Advanced settings**.
- Secrets: none required.
- System packages: none required.

## Deploy

1. Upload every file and directory in this folder to the root of a GitHub
   repository, including `.streamlit/config.toml`.
2. In Streamlit Community Cloud, choose **Create app** and select that
   repository and its `main` branch.
3. Set **Main file path** to `app.py`.
4. Open **Advanced settings**, choose Python 3.12, and deploy.

`requirements.txt` is pinned to the versions used to validate this snapshot.
The app needs outbound HTTPS access for official website ingestion but does not
use credentials, cookies, a database, or a secrets file.
