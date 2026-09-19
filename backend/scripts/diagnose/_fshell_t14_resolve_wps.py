"""Resolve F-SHELL T14 host representatives against a live project."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = (
    ROOT
    / ".kiro/specs/workpaper-page-formula-toolbar-closure/basis/T14-playwright/live-wp-resolve.json"
)
BASE = "http://127.0.0.1:9980"
PID = "0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49"
WANTED = ("B50-1", "D2", "D0", "A14-4", "E1")


def main() -> int:
    try:
        login = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    BASE + "/api/auth/login",
                    data=json.dumps({"username": "admin", "password": "admin123"}).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                ),
                timeout=10,
            ).read()
        )
    except Exception as exc:  # noqa: BLE001
        print("BACKEND_UNREACHABLE", exc)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(
            json.dumps({"status": "backend_unreachable", "error": str(exc)}, indent=2),
            encoding="utf-8",
        )
        return 2

    token = login["data"]["access_token"]
    headers = {"Authorization": "Bearer " + token}
    found = []
    for page in range(1, 20):
        url = f"/api/projects/{PID}/working-papers?page={page}&page_size=50"
        body = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(BASE + url, headers=headers), timeout=20
            ).read()
        )
        items = body["data"]["items"]
        if not items:
            break
        for row in items:
            if row.get("wp_code") in WANTED:
                found.append(row)

    out = []
    for row in found:
        cfg_url = f"/api/workpapers/{row['wp_id']}/render-config?project_id={PID}"
        try:
            cfg = json.loads(
                urllib.request.urlopen(
                    urllib.request.Request(BASE + cfg_url, headers=headers), timeout=90
                ).read()
            )
            data = cfg.get("data", cfg)
            out.append(
                {
                    "wp_code": row["wp_code"],
                    "wp_id": row["wp_id"],
                    "project_id": PID,
                    "sheet_types": sorted(
                        {
                            s.get("componentType")
                            for s in (data.get("sheets") or [])
                            if s.get("componentType")
                        }
                    ),
                }
            )
        except urllib.error.HTTPError as exc:
            out.append({"wp_code": row["wp_code"], "error": str(exc)})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
