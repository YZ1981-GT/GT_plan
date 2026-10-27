"""Loader: wp_account_mapping.json → 平台底稿索引名并入别名与冲突分类。

读取 `backend/data/wp_account_mapping.json` 的 `mappings`，把平台底稿索引名
（`wp_name` = 项目 `wp_index.wp_name`）并入对应 sheet 的别名；并按 design §6.3
分出两类冲突：

- **同父一名多码**（现算 9 组）：同一父级内某平台名对应 ≥ 2 个 sheet_code，
  一律记禁止别名（`exact_identity` 第 3 步据此拒绝，理由含父级与候选编码）。
- **只跨父级重名**（现算 6 组）：同一平台名在多个父级出现、每个父级内唯一，
  按父级限定别名保留（并入各父级内对应 sheet 的别名）。

并入前（§6.3）断言 `sheet_of(父级, 平台名)` 回到本 sheet（r05 现算冲突 0）。
现状（段四审计 F4-13 更正）：生成器尚未调用本 loader，这条往返只在
`tests/acnr/test_name_system.py` 里对目录副本校验；T06 / T07 接入后由生成器在合并全部
输入后用合并后目录统一校验。本 loader 只做纯结构分类，不触碰目录单例，不读 DB。

Requirements: 5.1, 5.2, 5.3（D4 / R2-F2）
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------

# loaders/from_wp_account_mapping.py → acnr → services → app → backend → data
_MAPPING_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / "data"
    / "wp_account_mapping.json"
)


# ---------------------------------------------------------------------------
# 结果对象
# ---------------------------------------------------------------------------


@dataclass
class WpNameAliasResult:
    """平台索引名并入结果。

    Attributes
    ----------
    aliases
        {sheet_code → [平台名…]}，仅含「可并入」的别名（非同父冲突、与模板名不同）。
        父级限定别名也在这里（每父级内唯一，按 sheet_code 并入即可）。
    forbidden
        {(parent_wp_code, 平台名) → [sorted sheet_code…]}，同父一名多码冲突组。
        交给 `exact_identity` 第 3 步与门禁 `alias` 检查。
    parent_qualified
        {平台名 → {parent_wp_code → sheet_code}}，只跨父级重名、每父唯一的分组
        （信息用，供报告与 alias_policy 对账；实际并入已在 `aliases`）。
    """

    aliases: dict[str, list[str]] = field(default_factory=dict)
    forbidden: dict[tuple[str, str], list[str]] = field(default_factory=dict)
    parent_qualified: dict[str, dict[str, str]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------


def load_wp_account_mapping_aliases(
    catalog_sheets: Sequence[Mapping[str, Any]],
    *,
    mapping_path: Path | None = None,
) -> WpNameAliasResult:
    """从 wp_account_mapping 并入平台索引名并分类冲突。

    Parameters
    ----------
    catalog_sheets
        目录 sheet 条目序列（每条含 `sheet_code`/`parent_wp_code`/`sheet_name`）。
        仅 wp_code 命中目录某 sheet 的 `sheet_code` 时才并入（否则不是在用 sheet）。
    mapping_path
        wp_account_mapping.json 路径（默认 `backend/data/wp_account_mapping.json`）。

    Returns
    -------
    WpNameAliasResult
    """
    path = mapping_path or _MAPPING_PATH
    mappings = _load_mapping_rows(path)

    # 目录：sheet_code → (parent_wp_code, sheet_name)
    by_code: dict[str, tuple[str, str]] = {}
    for s in catalog_sheets:
        code = s.get("sheet_code", "")
        if code:
            by_code[code] = (s.get("parent_wp_code", ""), s.get("sheet_name", ""))

    # (parent, 平台名) → {sheet_code}
    by_parent_name: dict[tuple[str, str], set[str]] = defaultdict(set)
    # 平台名 → {parent}
    name_parents: dict[str, set[str]] = defaultdict(set)

    for row in mappings:
        wp_code = row.get("wp_code", "")
        wp_name = row.get("wp_name", "")
        if not wp_code or not wp_name:
            continue
        if wp_code not in by_code:
            continue  # 不是在用 sheet，跳过
        parent, sheet_name = by_code[wp_code]
        if wp_name == sheet_name:
            continue  # 与模板名相同，不作别名（§6.3）
        by_parent_name[(parent, wp_name)].add(wp_code)
        name_parents[wp_name].add(parent)

    # 同父一名多码 → 禁止别名
    forbidden: dict[tuple[str, str], list[str]] = {
        key: sorted(codes)
        for key, codes in by_parent_name.items()
        if len(codes) >= 2
    }

    # 可并入别名（不在禁止组里）与父级限定分组
    aliases: dict[str, list[str]] = {}
    parent_qualified: dict[str, dict[str, str]] = {}

    for (parent, name), codes in by_parent_name.items():
        if (parent, name) in forbidden:
            continue  # 同父冲突，不并入
        # 此时该父级内这个名恰一个 sheet_code
        code = next(iter(codes))
        aliases.setdefault(code, [])
        if name not in aliases[code]:
            aliases[code].append(name)

    for name, parents in name_parents.items():
        if len(parents) < 2:
            continue
        per_parent = {
            p: sorted(by_parent_name[(p, name)])
            for p in parents
        }
        # 仅当每个父级内都唯一（无同父冲突）才算父级限定别名
        if all(len(c) == 1 for c in per_parent.values()):
            parent_qualified[name] = {p: c[0] for p, c in per_parent.items()}

    # 稳定输出：别名列表去重保序、键排序由调用方按需
    for code in aliases:
        aliases[code] = sorted(set(aliases[code]))

    return WpNameAliasResult(
        aliases=aliases,
        forbidden=forbidden,
        parent_qualified=parent_qualified,
    )


# ---------------------------------------------------------------------------
# 内部
# ---------------------------------------------------------------------------


def _load_mapping_rows(path: Path) -> list[dict[str, Any]]:
    """读取 wp_account_mapping.json 的 mappings 列表。"""
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("mappings", [])
    return [r for r in rows if isinstance(r, dict)]


__all__ = [
    "WpNameAliasResult",
    "load_wp_account_mapping_aliases",
]
