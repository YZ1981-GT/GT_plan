"""生成器发布流程（design §5.3 / §5.6，T07）：--check、幂等、门禁违规不写、R2-F11 沿用来源。

全部在临时副本上跑（monkeypatch 生成器的产物路径常量），不写仓库文件；真实发布用脚本运行生成器，不在测试里运行。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
_ACNR = _BACKEND / "data" / "acnr"
_SCHEMA = _BACKEND.parent / "docs" / "acnr" / "schemas" / "global_catalog.schema.json"
sys.path.insert(0, str(_BACKEND / "scripts" / "acnr"))

import generate_catalog as gc  # noqa: E402

from app.services.acnr import catalog_build  # noqa: E402
from app.services.acnr.catalog_integrity import content_sha256  # noqa: E402


@pytest.fixture()
def tmp_release(tmp_path, monkeypatch):
    acnr = tmp_path / "acnr"
    (acnr / "catalog_snapshots").mkdir(parents=True)
    for name in ("global_catalog.json", "catalog_report.json", "release_exceptions.json"):
        shutil.copyfile(_ACNR / name, acnr / name)
    for p in (_ACNR / "catalog_snapshots").glob("*.json"):
        shutil.copyfile(p, acnr / "catalog_snapshots" / p.name)
    schema = tmp_path / "global_catalog.schema.json"
    shutil.copyfile(_SCHEMA, schema)
    monkeypatch.setattr(gc, "_ACNR_DATA_DIR", acnr)
    monkeypatch.setattr(gc, "_CATALOG_PATH", acnr / "global_catalog.json")
    monkeypatch.setattr(gc, "_REPORT_PATH", acnr / "catalog_report.json")
    monkeypatch.setattr(gc, "_SNAPSHOTS_DIR", acnr / "catalog_snapshots")
    monkeypatch.setattr(gc, "_SCHEMA_PATH", schema)
    return acnr, schema


def _digest(acnr: Path, schema: Path) -> dict[str, str]:
    files = [acnr / "global_catalog.json", acnr / "catalog_report.json", schema, *sorted((acnr / "catalog_snapshots").glob("*.json"))]
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def test_committed_release_passes_check(tmp_release, capsys):
    assert gc.run_check() == 0
    assert "发布门禁 0 违规" in capsys.readouterr().out


def test_release_section_is_consistent_with_artifacts():
    report = json.loads((_ACNR / "catalog_report.json").read_text(encoding="utf-8"))
    rel = report["release"]
    catalog_raw = (_ACNR / "global_catalog.json").read_bytes()
    assert rel["registry_version"] == json.loads(catalog_raw)["registry_version"]
    assert rel["catalog_sha256"] == content_sha256(catalog_raw)
    assert rel["schema_sha256"] == content_sha256(_SCHEMA.read_bytes())
    snap = _ACNR / "catalog_snapshots" / f"{rel['registry_version']}.json"
    assert content_sha256(snap.read_bytes()) == rel["catalog_sha256"], "当前版本快照须与目录同字节"
    exc = catalog_build.load_release_exceptions(_ACNR)["exceptions"][0]
    assert (rel["previous_version"], rel["previous_catalog_sha256"]) == (exc["registry_version"], exc["snapshot_content_sha256"])
    fp, rows = catalog_build.inputs_fingerprint([(r["path"], _BACKEND.parent / r["path"]) for r in rel["inputs"]])
    assert (fp, rows) == (rel["inputs_fingerprint"], rel["inputs"]), "输入指纹须可由记录的输入清单复算"


def test_alias_added_only_in_catalog_is_drift(tmp_release, capsys):
    """R2-F11：只在目录给某 sheet 加一个别名（不改任何输入与上一批次快照）→ --check 退出 2 并点名该字段。"""
    acnr, _ = tmp_release
    p = acnr / "global_catalog.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    target = next(s for s in data["sheets"] if s["addr_id"] == "D2/D2-2")
    target["sheet_name_aliases"] = list(target.get("sheet_name_aliases") or []) + ["手工别名"]
    p.write_text(catalog_build.deterministic_json(data), encoding="utf-8")
    assert gc.run_check() == 2
    assert "D2/D2-2: sheet_name_aliases" in capsys.readouterr().err


def test_second_write_is_idempotent(tmp_release, capsys):
    acnr, schema = tmp_release
    before = _digest(acnr, schema)
    assert gc.run_write(None) == 0
    assert "不写任何文件" in capsys.readouterr().out
    assert _digest(acnr, schema) == before


def test_gate_violation_writes_nothing_and_names_addr_id(tmp_release, monkeypatch, capsys):
    """删 I6-7 的 sheet 判定 → 门禁报孤儿 / 判定并点名 I6/I6-7，退出 1，不写任何文件（T05 变异的常驻版）。"""
    acnr, schema = tmp_release
    real = catalog_build.load_sheet_verdicts

    def without_i6_7(path=None):
        v = real(path)
        v.sheet_verdicts = [s for s in v.sheet_verdicts if s.addr_id != "I6/I6-7"]
        return v

    monkeypatch.setattr(catalog_build, "load_sheet_verdicts", without_i6_7)
    before = _digest(acnr, schema)
    assert gc.run_write("20991231000000") == 1
    err = capsys.readouterr().err
    assert "orphan" in err and "I6/I6-7" in err
    assert _digest(acnr, schema) == before
