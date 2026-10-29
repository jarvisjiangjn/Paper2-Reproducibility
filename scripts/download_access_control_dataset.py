"""Download the official Spider access-control JSONL used by Paper 2.

The script preserves the source JSONL bytes so the released D1 input SHA-256 can
be checked exactly. It uses only the Python standard library.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
from urllib.request import Request, urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data" / "access_control_dataset.jsonl"
SOURCE_URL = (
    "https://raw.githubusercontent.com/klisura-code/LLM-Access-Control-Datasets/"
    "main/data/spider/spider-access-control.zip"
)
EXPECTED_SHA256 = "0e56c06e9fd526496d25dd4d5fb5bf6e88fbe518168a844cba78140f884d7ac4"
EXPECTED_RECORDS = 19624
REQUIRED_FIELDS = {
    "db_id", "user", "query", "question", "ground_truth_label",
    "access_policy_sql", "schema_ddl",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_jsonl(path: Path, expected_records: int = EXPECTED_RECORDS) -> tuple[int, str]:
    count = 0
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                raise ValueError(f"Blank line at {path}:{line_number}")
            record = json.loads(line)
            missing = REQUIRED_FIELDS - record.keys()
            if missing:
                raise ValueError(
                    f"Missing required fields at line {line_number}: {sorted(missing)}"
                )
            count += 1
    if count != expected_records:
        raise ValueError(
            f"Expected {expected_records:,} records, found {count:,}. "
            "The upstream dataset may have changed."
        )
    return count, sha256_file(path)


def download_to(url: str, target: Path) -> None:
    request = Request(url, headers={"User-Agent": "Paper2-Reproducibility/1.0"})
    with urlopen(request, timeout=120) as response, target.open("wb") as output:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)


def install_dataset(allow_updated_source: bool = False, force: bool = False) -> dict:
    DEST.parent.mkdir(parents=True, exist_ok=True)
    if DEST.exists() and not force:
        count, digest = validate_jsonl(DEST)
        print(f"Dataset already exists: {DEST}")
        print(f"Records: {count:,}\nSHA-256: {digest}")
        if digest != EXPECTED_SHA256 and not allow_updated_source:
            raise ValueError(
                "The existing dataset does not match the D1 input used for the released results. "
                "Move it aside or rerun with --allow-updated-source if you intentionally want "
                "to use this revision."
            )
        if digest != EXPECTED_SHA256:
            print("WARNING: this dataset revision differs from the released D1 input hash.")
        return {"path": str(DEST), "records": count, "sha256": digest, "downloaded": False}

    with tempfile.TemporaryDirectory(prefix="paper2_dataset_") as temp_dir:
        temp = Path(temp_dir)
        archive = temp / "spider-access-control.zip"
        extracted = temp / "access_control_dataset.jsonl"
        print(f"Downloading official Spider-ACL data from:\n{SOURCE_URL}")
        download_to(SOURCE_URL, archive)
        with zipfile.ZipFile(archive) as zipped:
            candidates = [
                name for name in zipped.namelist()
                if Path(name).name == "spider-access-control.jsonl"
            ]
            if len(candidates) != 1:
                raise ValueError(
                    "Expected exactly one spider-access-control.jsonl in the upstream ZIP; "
                    f"found {len(candidates)}. Inspect the upstream archive manually."
                )
            with zipped.open(candidates[0]) as source, extracted.open("wb") as output:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)

        count, digest = validate_jsonl(extracted)
        if digest != EXPECTED_SHA256 and not allow_updated_source:
            raise ValueError(
                "Downloaded data passed schema/count checks but does not match the exact "
                "D1 input used for the released results.\n"
                f"Expected SHA-256: {EXPECTED_SHA256}\nActual SHA-256:   {digest}\n"
                "No file was installed. If you intentionally want the upstream revision, "
                "rerun with --allow-updated-source and save results to a new output folder."
            )
        staged = DEST.with_suffix(".jsonl.tmp")
        staged.write_bytes(extracted.read_bytes())
        os.replace(staged, DEST)

    if digest != EXPECTED_SHA256:
        print("WARNING: using an updated dataset revision; existing result manifests will not match.")
    print(f"Installed: {DEST}\nRecords: {count:,}\nSHA-256: {digest}")
    return {"path": str(DEST), "records": count, "sha256": digest, "downloaded": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Replace an existing local dataset")
    parser.add_argument(
        "--allow-updated-source", action="store_true",
        help="Allow a newer upstream file whose SHA-256 differs from the paper's D1 input",
    )
    args = parser.parse_args()
    install_dataset(args.allow_updated_source, args.force)


if __name__ == "__main__":
    main()
