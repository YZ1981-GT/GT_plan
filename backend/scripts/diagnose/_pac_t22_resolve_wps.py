# -*- coding: utf-8 -*-
import json
import urllib.request
from pathlib import Path

base = "http://127.0.0.1:9980"
login = json.loads(
    urllib.request.urlopen(
        urllib.request.Request(
            base + "/api/auth/login",
            data=json.dumps({"username": "admin", "password": "admin123"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
    ).read()
)
token = login["data"]["access_token"]
H = {"Authorization": "Bearer " + token}
pid = "0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49"
wanted = {"D2", "B50-1", "A14-4", "D0", "B50"}
found = []
for page in range(1, 20):
    url = f"/api/projects/{pid}/working-papers?page={page}&page_size=50"
    body = json.loads(
        urllib.request.urlopen(urllib.request.Request(base + url, headers=H), timeout=20).read()
    )
    items = body["data"]["items"]
    if not items:
        break
    for row in items:
        if row.get("wp_code") in wanted:
            found.append(row)

print("FOUND", [(f["wp_code"], f["wp_id"]) for f in found])
out = []
for row in found:
    cfg_url = f"/api/workpapers/{row['wp_id']}/render-config?project_id={pid}"
    try:
        cfg = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(base + cfg_url, headers=H), timeout=90
            ).read()
        )
        data = cfg.get("data", cfg)
        out.append(
            {
                "wp_code": row["wp_code"],
                "wp_id": row["wp_id"],
                "project_id": pid,
                "decision_trace_len": len(data.get("decision_trace") or []),
                "sheet_types": sorted(
                    {
                        s.get("componentType")
                        for s in (data.get("sheets") or [])
                        if s.get("componentType")
                    }
                ),
            }
        )
    except Exception as exc:  # noqa: BLE001
        out.append({"wp_code": row["wp_code"], "error": str(exc)})

path = Path(".kiro/specs/platform-architecture-convergence/basis/T22-playwright/live-wp-resolve.json")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=2))
