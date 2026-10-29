# Data setup

This directory intentionally does not include downloaded benchmark data.

- Run `python scripts/download_access_control_dataset.py` to install the pinned Spider access-control JSONL at `data/access_control_dataset.jsonl`.
- Download Spider 1.0 from the [official Spider project page](https://yale-lily.github.io/spider), then run `python scripts/install_spider_database.py --archive "C:\path\to\spider.zip"` to install the SQLite databases under `data/spider/database/`.

The downloader verifies the D1 input hash used by the released result files. Do not silently replace the dataset and reuse old manifests. The released execution-audit CSV can be joined to the downloaded JSONL by `scenario_id`.
