"""Smoke/load helper for ledger import jobs.

Example:
    python scripts/import_load_smoke.py \
      --base-url http://localhost:8000 \
      --token "$TOKEN" \
      --project-id "$PROJECT_ID" \
      --year 2025 \
      --file ./samples/ledger.csv \
      --concurrency 2

The script submits existing local files and polls job status. It does not
generate large files, so production-like 500MB/1GB inputs can be supplied by
the environment without committing bulky artifacts.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import time
from pathlib import Path
from typing import Any

import httpx


def _submit_and_wait(args: argparse.Namespace, index: int) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {args.token}"}
    started = time.time()
    with httpx.Client(base_url=args.base_url, headers=headers, timeout=args.timeout) as client:
        files = [("files", (Path(file_path).name, open(file_path, "rb"))) for file_path in args.file]
        try:
            response = client.post(
                f"/api/projects/{args.project_id}/ledger/smart-import",
                params={"year": args.year},
                files=files,
            )
        finally:
            for _, file_tuple in files:
                file_tuple[1].close()
        response.raise_for_status()
        payload = response.json().get("data") or response.json()
        job_id = payload.get("job_id")
        if not job_id:
            return {"index": index, "status": "submitted_without_job_id", "payload": payload}

        polls = 0
        while polls < args.max_polls:
            polls += 1
            status_resp = client.get(f"/api/projects/{args.project_id}/ledger-import/jobs/{job_id}")
            status_resp.raise_for_status()
            status = status_resp.json().get("data") or status_resp.json()
            if status.get("status") in {"completed", "failed", "timed_out", "canceled"}:
                return {
                    "index": index,
                    "job_id": job_id,
                    "status": status.get("status"),
                    "elapsed_seconds": round(time.time() - started, 3),
                    "polls": polls,
                    "message": status.get("message") or status.get("error_message"),
                }
            time.sleep(args.poll_interval)
    return {"index": index, "job_id": job_id, "status": "poll_timeout", "elapsed_seconds": round(time.time() - started, 3)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Submit and poll ledger import load smoke jobs")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--file", action="append", required=True, help="Input file path; repeat for multi-file import")
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--poll-interval", type=float, default=3.0)
    parser.add_argument("--max-polls", type=int, default=400)
    args = parser.parse_args()

    start = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as executor:
        results = list(executor.map(lambda idx: _submit_and_wait(args, idx), range(args.concurrency)))
    report = {
        "concurrency": args.concurrency,
        "files": args.file,
        "elapsed_seconds": round(time.time() - start, 3),
        "results": results,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
