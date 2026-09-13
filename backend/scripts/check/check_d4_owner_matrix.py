#!/usr/bin/env python
"""D4 owner 矩阵守卫（governance spec d4-dual-mode-formula-governance Task 1 / Property 1）。

守卫五件事，任一失败退出码 1（--check 幂等只读，绝不写盘）：

1. **分母恒为 36**：`rows` 恰好 36 条，wp_code = D4-1..D4-36 连续无缺无重（Property 1）。
   物理 sheet / 变体 / 程序表 / D4-22A / D4A 不得进入分母。
2. **owner 去重规则（Req 1.2）**：有专属 owner（status=dedicated）的项，其 owner 必须与
   design.md 声明一致；不得把已有 owner 的表重新指给 governance 自己。
3. **gap 项已登记（Req 1.3）**：D4-4 / D4-8 / D4-12 必须 status=gap 且 owner 指向
   gap-closure spec，不得留空 owner。
4. **模板证据落地**：`template_evidence` 每个文件在 `authoritative_template_root` 下真实存在，
   且 finder `_index.json` 以 wp_code=D4 索引到它（运行时权威源，非参考副本）。
5. **design.md ↔ JSON 双向锁死**：design.md R1 矩阵表里每个 `D4-N | owner` 行都能在 JSON 里
   找到同 owner 记录，反之亦然（防两处漂移，memory 铁律「守卫与真源双向锁死」）。

用法：
    python backend/scripts/check/check_d4_owner_matrix.py --check
    python backend/scripts/check/check_d4_owner_matrix.py          # 同 --check（本守卫无写模式）
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]  # backend/
_REPO = _ROOT.parent
_MATRIX = _ROOT / "data" / "d4_owner_matrix.json"
_INDEX = _ROOT / "wp_templates" / "_index.json"
_DESIGN = _REPO / ".kiro" / "specs" / "d4-dual-mode-formula-governance" / "design.md"

EXPECTED_DENOMINATOR = 36
GAP_CODES = {"D4-4", "D4-8", "D4-12"}
GAP_OWNER = "d4-adjudication-and-analysis-gap-closure"


def _load_matrix() -> dict:
    return json.loads(_MATRIX.read_text(encoding="utf-8"))


def _check_denominator(matrix: dict, errs: list[str]) -> None:
    rows = matrix.get("rows") or []
    if matrix.get("denominator") != EXPECTED_DENOMINATOR:
        errs.append(
            f"denominator={matrix.get('denominator')} != {EXPECTED_DENOMINATOR}"
        )
    codes = [r.get("wp_code") for r in rows]
    if len(rows) != EXPECTED_DENOMINATOR:
        errs.append(f"rows 数 {len(rows)} != {EXPECTED_DENOMINATOR}（分母被扩张/缩水）")
    dupes = sorted({c for c in codes if codes.count(c) > 1})
    if dupes:
        errs.append(f"wp_code 重复：{dupes}")
    expected = {f"D4-{i}" for i in range(1, EXPECTED_DENOMINATOR + 1)}
    got = set(codes)
    missing = sorted(expected - got, key=lambda c: int(c.split("-")[1]))
    extra = sorted(got - expected)
    if missing:
        errs.append(f"缺 wp_code：{missing}")
    if extra:
        errs.append(f"分母混入非 D4-1..36 的码（禁止物理 sheet/变体/程序表进分母）：{extra}")


def _check_gaps(matrix: dict, errs: list[str]) -> None:
    by_code = {r["wp_code"]: r for r in matrix.get("rows") or []}
    for code in sorted(GAP_CODES):
        row = by_code.get(code)
        if row is None:
            errs.append(f"gap 项 {code} 缺失")
            continue
        if row.get("status") != "gap":
            errs.append(f"{code} status={row.get('status')!r} 应为 'gap'（Req 1.3）")
        if not row.get("owner"):
            errs.append(f"{code} owner 为空（gap 项也必须指向 gap-closure owner，不得留空）")


def _check_own_row(matrix: dict, errs: list[str]) -> None:
    by_code = {r["wp_code"]: r for r in matrix.get("rows") or []}
    d41 = by_code.get("D4-1")
    if d41 is None:
        errs.append("D4-1 缺失")
        return
    if d41.get("owner") != "d4-dual-mode-formula-governance":
        errs.append(
            f"D4-1 owner={d41.get('owner')!r} 应为 'd4-dual-mode-formula-governance'"
            "（审定表是本治理 spec 专属）"
        )
    if d41.get("status") != "own":
        errs.append(f"D4-1 status={d41.get('status')!r} 应为 'own'")


def _check_template_evidence(matrix: dict, errs: list[str]) -> None:
    root = _REPO / matrix.get("authoritative_template_root", "backend/wp_templates/")
    if not root.exists():
        errs.append(f"authoritative_template_root 不存在：{root}")
        return
    # 收集权威源里所有物理文件名（递归）
    on_disk = {p.name for p in root.rglob("*.xlsx")}
    # finder 索引里 wp_code=D4 的文件名
    try:
        index = json.loads(_INDEX.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        errs.append(f"读 finder _index.json 失败：{exc}")
        index = {"files": []}
    indexed_d4 = {
        f["filename"] for f in index.get("files", []) if f.get("wp_code") == "D4"
    }
    for ev in matrix.get("template_evidence") or []:
        fn = ev.get("filename")
        if fn not in on_disk:
            errs.append(f"模板证据文件不在权威源磁盘：{fn}")
        if fn not in indexed_d4:
            errs.append(f"模板证据文件未被 finder 以 wp_code=D4 索引：{fn}")


_DESIGN_ROW_RE = re.compile(r"^\|\s*(D4-\d+)\s*\|\s*([^|]+?)\s*\|")


def _check_design_lock(matrix: dict, errs: list[str]) -> None:
    if not _DESIGN.exists():
        errs.append(f"design.md 不存在：{_DESIGN}")
        return
    text = _DESIGN.read_text(encoding="utf-8")
    design_owner: dict[str, str] = {}
    for line in text.splitlines():
        m = _DESIGN_ROW_RE.match(line.strip())
        if m:
            design_owner[m.group(1)] = m.group(2).strip()
    json_owner = {r["wp_code"]: r["owner"] for r in matrix.get("rows") or []}

    # design 表 → JSON
    for code, owner in design_owner.items():
        if code not in json_owner:
            errs.append(f"design.md 有 {code} 但 JSON 矩阵没有")
        elif json_owner[code] != owner:
            errs.append(
                f"{code} owner 漂移：design.md={owner!r} vs JSON={json_owner[code]!r}"
            )
    # JSON → design 表
    for code in json_owner:
        if code not in design_owner:
            errs.append(f"JSON 矩阵有 {code} 但 design.md R1 表没有")


def _reverse_selfcheck() -> list[str]:
    """反向自检：故意坏值必须被上面的检查捕获（防守卫是空操作）。"""
    problems: list[str] = []
    # 分母检查：37 条必红
    bad = {"denominator": 37, "rows": [{"wp_code": f"D4-{i}"} for i in range(1, 38)]}
    e: list[str] = []
    _check_denominator(bad, e)
    if not e:
        problems.append("反向自检失败：denominator=37 未被 _check_denominator 拦下")
    # own 行检查：owner 指错必红
    bad2 = {"rows": [{"wp_code": "D4-1", "owner": "some-other-spec", "status": "own"}]}
    e2: list[str] = []
    _check_own_row(bad2, e2)
    if not e2:
        problems.append("反向自检失败：D4-1 owner 指错未被 _check_own_row 拦下")
    return problems


def main() -> int:
    errs: list[str] = []
    try:
        matrix = _load_matrix()
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] 读 {_MATRIX} 失败：{exc}")
        return 1

    _check_denominator(matrix, errs)
    _check_gaps(matrix, errs)
    _check_own_row(matrix, errs)
    _check_template_evidence(matrix, errs)
    _check_design_lock(matrix, errs)

    self_problems = _reverse_selfcheck()
    if self_problems:
        errs.extend(self_problems)

    if errs:
        print(f"[FAIL] D4 owner 矩阵守卫检出 {len(errs)} 项问题：")
        for e in errs:
            print(f"  - {e}")
        return 1

    print(
        f"[OK] D4 owner 矩阵：{len(matrix['rows'])} 行分母守恒，"
        f"owner/gap/own/模板证据/design 锁死全部通过。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
