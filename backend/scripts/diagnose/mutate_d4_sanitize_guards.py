# -*- coding: utf-8 -*-
"""D4 净化守卫变异检验（四态）。

spec: d4-revenue-matrix-bidirectional · Task 4
覆盖：
  1. 内部公式误删（N 列 SUM 被干掉）→ 必须打红
  2. 坐标/受管格被改（改 product 格）→ 必须打红
  3. 只删 XML 部件不删 rels → 门必须仍 REJECT
  4. 改坏净化（中和正则放宽误伤 shared）→ 必须打红

四态：RED / GREEN / ANCHOR-MISS / WRONG-TEST。GREEN = 守卫缺陷。

用法（仓库根）：
  & .venv/Scripts/python.exe backend/scripts/diagnose/mutate_d4_sanitize_guards.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import re
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

_REPO = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO / "backend" / "scripts" / "fix" / "sanitize_d4_template_external_links.py"
_BAK = _REPO / "backend" / "wp_templates" / "D" / "D4 收入底稿.xlsx.preclean.bak"
_CLEAN = _REPO / "backend" / "wp_templates" / "D" / "D4 收入底稿.xlsx"


def _load_sanitize():
    spec = importlib.util.spec_from_file_location("sanitize_d4", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@dataclass
class Verdict:
    mutation_id: str
    expected: str
    actual: str  # RED/GREEN/ANCHOR-MISS/WRONG-TEST
    detail: str


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _assert_predicates(mod, clean: bytes, dirty: bytes) -> list[str]:
    """返回失败的判据名列表（空 = 全绿）。"""
    fails: list[str] = []
    try:
        before_snap, before_merged, before_n = mod._snapshot_managed(dirty)
        after_snap, after_merged, after_n = mod._snapshot_managed(clean)
    except Exception as exc:  # noqa: BLE001
        fails.append(f"openpyxl_load:{type(exc).__name__}")
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.xlsx"
            p.write_bytes(clean)
            ok, msg = mod._gate_pass(p)
            if not ok:
                fails.append(f"gate:{msg}")
            else:
                # 能过门但打不开 = 仍算坏产物
                fails.append("unreadable_but_gate_pass")
        return fails
    diffs = mod._internal_cell_diffs(before_snap, after_snap)
    if diffs:
        fails.append(f"internal_cell_diffs={len(diffs)}")
    if before_merged != after_merged:
        fails.append("merged_changed")
    if before_n != after_n:
        fails.append("n_column_formulas_changed")
    n_data = {
        k: v
        for k, v in after_n.items()
        if k.startswith("N") and k[1:].isdigit() and 12 <= int(k[1:]) <= 23
    }
    if not (
        len(n_data) == 12
        and all(v.startswith("=SUM(B") and ":M" in v for v in n_data.values())
    ):
        fails.append("n12_n23_sum_broken")
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "x.xlsx"
        p.write_bytes(clean)
        ok, msg = mod._gate_pass(p)
        if not ok:
            fails.append(f"gate:{msg}")
    return fails


def _mutate_delete_internal_sum(src: bytes) -> bytes | None:
    """误删 N12 shared SUM master —— 模拟中和正则过宽。"""
    zin = zipfile.ZipFile(io.BytesIO(src))
    out = io.BytesIO()
    zout = zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED)
    hit = 0
    for info in zin.infolist():
        data = zin.read(info.filename)
        if info.filename.endswith("sheet6.xml"):  # 受管 D4-2
            text = data.decode("utf-8")
            new, n = re.subn(
                r'<f t="shared" ref="N12:N23" si="0">SUM\(B12:M12\)</f>',
                "",
                text,
                count=1,
            )
            hit += n
            data = new.encode("utf-8")
        new_info = zipfile.ZipInfo(filename=info.filename, date_time=info.date_time)
        new_info.compress_type = zipfile.ZIP_DEFLATED
        zout.writestr(new_info, data)
    zout.close()
    zin.close()
    return out.getvalue() if hit == 1 else None


def _mutate_touch_managed_product(src: bytes) -> bytes | None:
    """改受管 A12 业务格。"""
    zin = zipfile.ZipFile(io.BytesIO(src))
    out = io.BytesIO()
    zout = zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED)
    hit = 0
    for info in zin.infolist():
        data = zin.read(info.filename)
        if info.filename.endswith("sheet6.xml"):
            text = data.decode("utf-8")
            # 在 sheetData 开头插入/替换 A12
            if 'r="A12"' in text:
                new, n = re.subn(
                    r'<c r="A12"[^/]*/>|<c r="A12"[^>]*>.*?</c>',
                    '<c r="A12" t="inlineStr"><is><t>MUTATED</t></is></c>',
                    text,
                    count=1,
                    flags=re.S,
                )
                hit += n
                data = new.encode("utf-8")
            else:
                # 插入到 row 12
                m = re.search(r'(<row r="12"[^>]*>)', text)
                if m:
                    text = (
                        text[: m.end(1)]
                        + '<c r="A12" t="inlineStr"><is><t>MUTATED</t></is></c>'
                        + text[m.end(1) :]
                    )
                    hit = 1
                    data = text.encode("utf-8")
        new_info = zipfile.ZipInfo(filename=info.filename, date_time=info.date_time)
        new_info.compress_type = zipfile.ZIP_DEFLATED
        zout.writestr(new_info, data)
    zout.close()
    zin.close()
    return out.getvalue() if hit == 1 else None


def _mutate_drop_parts_keep_rels(src: bytes) -> bytes | None:
    """只删 externalLink*.xml 部件，保留 workbook rels —— 门应仍红。"""
    zin = zipfile.ZipFile(io.BytesIO(src))
    out = io.BytesIO()
    zout = zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED)
    dropped = 0
    for info in zin.infolist():
        name = info.filename
        if re.match(r"^xl/externalLinks/externalLink\d+\.xml$", name):
            dropped += 1
            continue
        # 保留 _rels 与 workbook rels
        new_info = zipfile.ZipInfo(filename=name, date_time=info.date_time)
        new_info.compress_type = zipfile.ZIP_DEFLATED
        zout.writestr(new_info, zin.read(name))
    zout.close()
    zin.close()
    return out.getvalue() if dropped >= 1 else None


def _mutate_overbroad_neutralize(src: bytes) -> bytes | None:
    """把中和逻辑改成删所有含 SUM 的 f —— 直接作用在字节上模拟脚本被改坏。"""
    zin = zipfile.ZipFile(io.BytesIO(src))
    out = io.BytesIO()
    zout = zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED)
    hit = 0
    for info in zin.infolist():
        data = zin.read(info.filename)
        if info.filename.startswith("xl/worksheets/sheet") and info.filename.endswith(
            ".xml"
        ):
            text = data.decode("utf-8")
            new, n = re.subn(r"<f[^>]*>[^<]*SUM[^<]*</f>", "", text)
            hit += n
            data = new.encode("utf-8")
        new_info = zipfile.ZipInfo(filename=info.filename, date_time=info.date_time)
        new_info.compress_type = zipfile.ZIP_DEFLATED
        zout.writestr(new_info, data)
    zout.close()
    zin.close()
    return out.getvalue() if hit >= 1 else None


def main() -> int:
    mod = _load_sanitize()
    if not _BAK.is_file():
        print("ANCHOR-MISS: missing .preclean.bak —— 先 --apply 净化")
        return 2
    dirty = _BAK.read_bytes()
    clean_disk = _CLEAN.read_bytes()

    # 基线：真正 sanitize(dirty) 必须全绿
    baseline = mod.sanitize_bytes(dirty)
    baseline_fails = _assert_predicates(mod, baseline, dirty)
    if baseline_fails:
        print(json.dumps({"baseline": "FAIL", "fails": baseline_fails}, ensure_ascii=False))
        return 1

    mutations: list[tuple[str, str, Callable[[bytes], bytes | None]]] = [
        (
            "M1_delete_internal_sum",
            "n_column_or_sum",
            lambda _: _mutate_delete_internal_sum(baseline),
        ),
        (
            "M2_touch_managed_product",
            "internal_cell",
            lambda _: _mutate_touch_managed_product(baseline),
        ),
        (
            "M3_drop_parts_keep_rels",
            "gate",
            lambda _: _mutate_drop_parts_keep_rels(dirty),
        ),
        (
            "M4_overbroad_neutralize",
            "n_column_or_sum",
            lambda _: _mutate_overbroad_neutralize(dirty),
        ),
    ]

    verdicts: list[dict] = []
    green = 0
    for mid, expect_kind, apply in mutations:
        mutated = apply(dirty)
        if mutated is None:
            verdicts.append(
                {
                    "id": mid,
                    "actual": "ANCHOR-MISS",
                    "detail": "mutation did not land",
                }
            )
            continue
        fails = _assert_predicates(mod, mutated, dirty)
        if not fails:
            actual = "GREEN"
            green += 1
            detail = "predicates still all green — guard defective"
        else:
            # 期望打红的判据族
            joined = "|".join(fails)
            if expect_kind == "gate" and any(
                f.startswith("gate:") or f.startswith("openpyxl_load:") for f in fails
            ):
                actual = "RED"
                detail = joined
            elif expect_kind == "n_column_or_sum" and any(
                "n_" in f or "sum" in f for f in fails
            ):
                actual = "RED"
                detail = joined
            elif expect_kind == "internal_cell" and any(
                "internal_cell" in f for f in fails
            ):
                actual = "RED"
                detail = joined
            else:
                actual = "WRONG-TEST"
                detail = f"expected={expect_kind} fails={joined}"
        verdicts.append({"id": mid, "actual": actual, "detail": detail, "fails": fails})

    # 磁盘净化产物必须仍过门；bak 必须拒
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "clean.xlsx"
        p.write_bytes(clean_disk)
        disk_ok, disk_msg = mod._gate_pass(p)
        b = Path(tmp) / "bak.xlsx"
        b.write_bytes(dirty)
        bak_ok, bak_msg = mod._gate_pass(b)

    report = {
        "baseline_fails": baseline_fails,
        "verdicts": verdicts,
        "green_count": green,
        "disk_clean_gate": disk_msg,
        "disk_bak_gate": bak_msg,
        "disk_clean_sha256": _sha(clean_disk),
        "bak_sha256": _sha(dirty),
        "pass": green == 0
        and all(v["actual"] == "RED" for v in verdicts)
        and disk_ok
        and not bak_ok,
    }
    out_path = (
        _REPO
        / ".kiro"
        / "specs"
        / "d4-revenue-matrix-bidirectional"
        / "evidence"
        / "T04-sanitize-mutation-verdict.json"
    )
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
