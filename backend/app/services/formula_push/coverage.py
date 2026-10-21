"""公式推送覆盖率（公式看板「推送覆盖率」卡片；spec formula-settings-wiring-closure R3.3）。

* 分母 = 致同 2025 编码表（``wp_account_mapping.json``）里 D~N 实质性循环、带科目码的主编码
  （``D2-1`` 归 ``D2``），剔除覆盖清册判为不适用的编码（函证中心 ``D0`` / ``E0`` …）；
* 分子 = 覆盖清册（``formula_push_coverage.json``）已登记推送的主编码；
* A / B / C / S 不产出科目数值，单列「不需推送」。

旧实现把每个循环的分母写死成与已接入数相同 ⇒ 恒 100%，看不出缺口；这里两侧都从数据文件现算，
并逐循环列出尚未接入的编码。
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA = Path(__file__).resolve().parents[3] / "data"
COVERAGE_PATH = _DATA / "formula_push_coverage.json"
MAPPING_PATH = _DATA / "wp_account_mapping.json"

SUBSTANTIVE = "DEFGHIJKLMN"
PROGRAM_TABLE = re.compile(r"^[A-Z]\d+A$")
NOT_NEEDED_REASONS: dict[str, str] = {
    "A": "报表/调整类底稿不涉及数值回写试算表",
    "B": "控制了解/计划类底稿，审计程序不产出数值",
    "C": "控制测试底稿只记录测试结论，不涉及科目金额",
    "S": "专项底稿按项目自定义，不走统一推送通道",
}
CYCLE_LABELS: dict[str, str] = {
    "A": "A 报表/调整", "B": "B 控制了解", "C": "C 控制测试",
    "D": "D 销售收入", "E": "E 货币资金", "F": "F 采购存货",
    "G": "G 投资", "H": "H 固定资产", "I": "I 无形资产",
    "J": "J 职工薪酬", "K": "K 管理", "L": "L 筹资",
    "M": "M 股东权益", "N": "N 税费", "S": "S 专项",
}


def main_code(wp_code: str) -> str:
    return (wp_code or "").strip().upper().split("-", 1)[0]


def _pct(connected: int, total: int) -> float:
    return round(connected / total * 100, 1) if total else 0.0


def compute(coverage: dict[str, Any], mapping: dict[str, Any]) -> dict[str, Any]:
    """纯函数：覆盖清册 + 编码表 → 覆盖率概览（测试直接喂数据）。"""
    registered = {main_code(c) for c in coverage.get("registered_codes") or []}
    excluded = {main_code(x.get("wp_code", "")): x.get("reason") or ""
                for x in coverage.get("not_applicable") or [] if isinstance(x, dict)}
    universe: set[str] = set()
    for row in mapping.get("mappings") or []:
        code = main_code(row.get("wp_code", ""))
        # 程序表（``M1A`` 这类审计程序清单）不产出科目数值，不进分母
        if code[:1] in SUBSTANTIVE and row.get("account_codes") and not PROGRAM_TABLE.match(code):
            universe.add(code)
    # 判为不适用、且确实没有登记推送的编码不进分母（如函证中心）；登记了的照常计入
    universe = {c for c in universe if c in registered or c not in excluded}
    universe |= {c for c in registered if c[:1] in SUBSTANTIVE}

    cycles: list[dict[str, Any]] = []
    for letter in "ABCDEFGHIJKLMNS":
        if letter in NOT_NEEDED_REASONS:
            cycles.append({"cycle": letter, "label": CYCLE_LABELS[letter], "connected": 0, "total": 0,
                           "percentage": 100.0, "not_needed": True, "reason": NOT_NEEDED_REASONS[letter],
                           "missing": []})
            continue
        codes = sorted(c for c in universe if c.startswith(letter))
        if not codes:
            continue
        connected = [c for c in codes if c in registered]
        missing = [c for c in codes if c not in registered]
        cycles.append({"cycle": letter, "label": CYCLE_LABELS[letter], "connected": len(connected),
                       "total": len(codes), "percentage": _pct(len(connected), len(codes)),
                       "not_needed": False, "reason": None, "missing": missing})
    total = len(universe)
    connected_total = len(universe & registered)
    return {"total_registered": connected_total, "total_codes": total,
            "percentage": _pct(connected_total, total), "cycles": cycles,
            "excluded": sorted(c for c in excluded if c[:1] in SUBSTANTIVE and c not in registered)}


@lru_cache(maxsize=4)
def _load(path: str, mtime: float) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read(path: Path) -> dict[str, Any]:
    try:
        return _load(str(path), path.stat().st_mtime)
    except (OSError, json.JSONDecodeError):
        return {}


def load_coverage() -> dict[str, Any]:
    return compute(_read(COVERAGE_PATH), _read(MAPPING_PATH))
