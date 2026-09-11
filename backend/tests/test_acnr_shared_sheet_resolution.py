"""跨循环共享页（函证族）在 ACNR 目录中的可定位性守卫 —— 离线、可 CI。

背景（用户实测缺陷）：D2 应收账款页里的子页 `核实被函证单位信息D0-2` 打开公式管理后，
左树定位不到、右侧列出 D2-1 等全册公式。运行时取证：该页在 ACNR 目录里
`parent_wp_code = D0`（它的原生工作簿），而宿主 wp_code 是 D2；前端此前按
「sheet 的父编码必须等于宿主 wp_code」判归属 ⇒ 必然落空 ⇒ 静默退成全册。

前端修复改为「按 sheet_code 跨工作簿唯一匹配 + 宿主 render-config 的 sheet 集定归属」。
本文件锁死该修复依赖的**数据前提**，避免数据侧漂移把修复悄悄变回全册兜底：

1. `wp` 域 sheet_code 全局唯一 —— 唯一性是跨工作簿按编码定位的前提；一旦出现重复，
   前端为避免误定位会放弃匹配，用户又会看到「全册公式冒充本页公式」。
2. 共享函证族（*0-2 等）在目录中存在且父编码指向自己的原生工作簿 —— 即
   「父 ≠ 宿主」这一形态是常态，不是异常数据。
3. 已登记盲区（manifest 声明了共享页、但目录里没有对应条目）数量与清单锁死：
   新增盲区打红；修好后也打红，提醒摘掉登记（防永久盲区）。
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPO_ROOT / "backend" / "data" / "acnr" / "global_catalog.json"
MANIFEST_PATH = (
    REPO_ROOT / "backend" / "data" / "workpaper_sync_abcs_cycle_manifest_slice.json"
)

# manifest 声明了共享页、但 ACNR 目录尚无对应 sheet 条目 ⇒ 这些页若被注入宿主，
# 公式中心无法定位到具体页（现在会显式告警，不再伪装成本页公式）。
KNOWN_UNCATALOGED_SHARED_CODES = {"D0-4B", "F0-4B", "G0-3S", "G0-4", "G0-8"}

# D0-2 缺陷所属的共享族：每个循环的「核实被函证单位信息」页。
ENTITY_VERIFY_CODES = ("D0-2", "E0-2", "F0-2", "G0-2", "H0-2", "K0-2")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _wp_sheets() -> list[dict]:
    sheets = _load(CATALOG_PATH)["sheets"]
    if isinstance(sheets, dict):
        sheets = list(sheets.values())
    return [s for s in sheets if s.get("domain") == "wp"]


def extract_sheet_code(label: str) -> str:
    """从页名或编码里抽索引号（与前端 `extractSheetIndexNo` 同口径 + 容忍 b/S 后缀）。

    manifest 的 ``wp_codes`` 混装了编码（``D0-2``）与完整页名
    （``核实被函证单位信息E0-2``），必须先归一再比对，否则「缺失」数会被口径
    错误放大（实测未归一时 16，归一后 5）。
    """
    text = str(label or "").strip()
    tail = re.search(r"([A-Z]\d+[A-Z]?(?:-\d+[A-Za-z]?)*)\s*$", text)
    if tail:
        return tail.group(1).upper()
    inner = re.search(r"([A-Z]\d+[A-Z]?(?:-\d+[A-Za-z]?)*)", text)
    return inner.group(1).upper() if inner else ""


def _declared_shared_codes() -> dict[str, list[str]]:
    """manifest 里 confirmation-* 族声明的共享页 → {归一编码: [原始声明串]}。"""

    def walk(node):
        if isinstance(node, dict):
            ct = str(node.get("component_type") or "")
            codes = node.get("wp_codes")
            if ct.startswith("confirmation-") and isinstance(codes, list):
                yield [str(c) for c in codes]
            for value in node.values():
                yield from walk(value)
        elif isinstance(node, list):
            for value in node:
                yield from walk(value)

    grouped: dict[str, list[str]] = {}
    for group in walk(_load(MANIFEST_PATH)):
        for raw in group:
            code = extract_sheet_code(raw)
            if code:
                grouped.setdefault(code, []).append(raw)
    return grouped


def test_extractor_self_check() -> None:
    """反向自检：抽取器必须真的抽到编码，否则下面的比对会空转成假绿。"""
    assert extract_sheet_code("核实被函证单位信息D0-2") == "D0-2"
    assert extract_sheet_code("函证差异核对表G0-4(非证券投资)") == "G0-4"
    assert extract_sheet_code("D0-4b") == "D0-4B"
    assert extract_sheet_code("底稿目录") == ""


def test_wp_sheet_code_globally_unique() -> None:
    """跨工作簿按 sheet_code 定位的前提：wp 域编码不得重复。"""
    counter = Counter(
        (s.get("sheet_code") or "").strip().upper()
        for s in _wp_sheets()
        if (s.get("sheet_code") or "").strip()
    )
    duplicates = {code: n for code, n in counter.items() if n > 1}
    assert not duplicates, (
        "wp 域出现重复 sheet_code，跨工作簿定位会退化为全册兜底："
        f"{sorted(duplicates.items())[:10]}"
    )


def test_duplicate_detector_is_not_vacuous() -> None:
    """反向自检：重复检测逻辑本身对合成重复必须报警（不碰共享数据文件）。"""
    synthetic = [
        {"domain": "wp", "sheet_code": "D0-2"},
        {"domain": "wp", "sheet_code": "d0-2"},
    ]
    counter = Counter(
        (s.get("sheet_code") or "").strip().upper() for s in synthetic
    )
    assert {c: n for c, n in counter.items() if n > 1} == {"D0-2": 2}


def test_entity_verify_family_parent_is_its_own_workbook() -> None:
    """共享页的父编码指向原生工作簿（D0-2 → D0），即「父 ≠ 宿主」是常态形态。"""
    by_code = {
        (s.get("sheet_code") or "").strip().upper(): s for s in _wp_sheets()
    }
    for code in ENTITY_VERIFY_CODES:
        entry = by_code.get(code)
        assert entry is not None, f"ACNR 目录缺共享页 {code}，宿主页将无法定位到具体页"
        parent = str(entry.get("parent_wp_code") or "").strip().upper()
        expected_parent = code.split("-")[0]
        assert parent == expected_parent, (
            f"{code} 的 parent_wp_code 期望 {expected_parent}，实际 {parent}"
        )


def test_known_uncataloged_shared_codes_locked() -> None:
    """盲区清单双向锁死：新增盲区打红；补齐后也打红以摘掉登记。"""
    declared = _declared_shared_codes()
    catalog_codes = {
        (s.get("sheet_code") or "").strip().upper() for s in _wp_sheets()
    }
    missing = {code for code in declared if code not in catalog_codes}

    new_blind_spots = missing - KNOWN_UNCATALOGED_SHARED_CODES
    assert not new_blind_spots, (
        "新增共享页未登记进 ACNR 目录，公式中心将无法定位该页（会退回全册并告警）："
        f"{sorted((c, declared[c][:2]) for c in new_blind_spots)}"
    )

    fixed = KNOWN_UNCATALOGED_SHARED_CODES - missing
    assert not fixed, (
        "以下盲区已被补齐，请从 KNOWN_UNCATALOGED_SHARED_CODES 摘掉登记，"
        f"避免它变成永久盲区：{sorted(fixed)}"
    )
