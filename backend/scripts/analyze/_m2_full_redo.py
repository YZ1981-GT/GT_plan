# -*- coding: utf-8 -*-
"""M2 全链重做：重生成 contract → 回填 sha256 → 重发布 → 重试首版。"""
import sys, json, importlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.workpaper_sync.contracts import canonical_digest

mod = importlib.import_module("app.services.workpaper_sync.phase5_m2_paid_in_capital")
importlib.reload(mod)
cfg = mod.CONFIG
orch = mod._P.orch
payload = mod.build_contract_payload()

tpl_sha = canonical_digest(orch.template_definition_payload())
instr_sha = canonical_digest(orch.instrumentation_definition_payload())
payload["template_definition_sha256"] = tpl_sha
payload["instrumentation_definition_sha256"] = instr_sha
tp = orch.template_definition_payload()
if "normalized_structure_hash" in tp:
    payload["template"]["normalized_structure_hash"] = tp["normalized_structure_hash"]

out = Path(__file__).resolve().parents[2] / "data" / "workpaper_sync_contracts" / "m2.paid_in_capital.json"
out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")
print(f"Contract: {out.stat().st_size} bytes, tpl_sha={tpl_sha[:16]}...")
