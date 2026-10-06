# data/

Created by the pipeline (`infdb-uy all` / `docker compose up`). Not under version control.

- `raw/` – downloads exactly as received, with `raw/manifest.jsonl` (URL, time, size, SHA-256)
- `prepared/` – lossless, analysis-ready copies for the configured scope
- `reports/` – summaries and the QA report
- `dashboard/` – web layers for the explorer
- `state/` – markers of completed pipeline steps

INE ANDA microdata go into `raw/ine_anda/<idno>/files/` (see the README.txt there and `docs/data-downloads.md`). Their terms of use forbid redistribution: never commit or share this folder.
