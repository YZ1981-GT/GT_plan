"""global_catalog.overrides.json 可伪证（design §5.4，T07）。

每条 override 有 owner / reason / 可识别的 source；所指 sheet 在 classification 骨架中存在；
`fix_acnr_catalog_ie_gap:SAFE:{前缀}` 来源的条目与该脚本同一 AST 抽取口径现算逐字段相等；
迁回后已发布目录的这些 sheet 的 import_export 与 override 值相等（生成器确实消费了它）。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
_ACNR = _BACKEND / "data" / "acnr"
sys.path.insert(0, str(_BACKEND / "scripts" / "fix"))

import fix_acnr_catalog_ie_gap as gap  # noqa: E402

_SOURCE_RE = re.compile(r"^fix_acnr_catalog_ie_gap:SAFE:[a-z0-9-]+$")


def _overrides() -> dict:
    return json.loads((_ACNR / "global_catalog.overrides.json").read_text(encoding="utf-8"))


def test_every_override_has_owner_reason_recognizable_source():
    rows = _overrides()["overrides"]
    assert len(rows) == 38, f"迁回的 SAFE 档外科补丁应为 H4 + I24 + L8 + N2 = 38 条，现 {len(rows)}"
    for e in rows:
        assert e.get("owner") and e.get("reason"), e.get("addr_id")
        assert _SOURCE_RE.match(e.get("source", "")), e
    assert {e["addr_id"][0] for e in rows} == {"H", "I", "L", "N"}


def test_override_targets_exist_in_classification_skeleton():
    from app.services.acnr.loaders.from_classification import load_sheet_skeletons_from_classification

    records = json.loads((_ACNR / "sources" / "classification_cache.json").read_text(encoding="utf-8"))
    skeleton = {s.addr_id for s in load_sheet_skeletons_from_classification(records)}
    missing = [e["addr_id"] for e in _overrides()["overrides"] if e["addr_id"] not in skeleton]
    assert not missing, f"override 所指 sheet 不在 classification 骨架：{missing}"


def test_safe_overrides_equal_script_recomputation():
    assert gap.verify_overrides() == []


def test_verify_overrides_detects_tampering():
    """反向：改一条 item_id → 现算比对报出该 addr_id（判据不是恒真）。"""
    data = _overrides()
    data["overrides"][0]["fields"]["import_export"]["item_id"] = "tampered-rows"
    problems = gap.verify_overrides(data)
    assert len(problems) == 1 and data["overrides"][0]["addr_id"] in problems[0]


def test_published_catalog_consumes_overrides():
    catalog = json.loads((_ACNR / "global_catalog.json").read_text(encoding="utf-8"))
    by_id = {s["addr_id"]: s for s in catalog["sheets"]}
    bad = [e["addr_id"] for e in _overrides()["overrides"]
           if by_id.get(e["addr_id"], {}).get("import_export") != e["fields"]["import_export"]]
    assert not bad, f"已发布目录与 override 值不等：{bad}"
