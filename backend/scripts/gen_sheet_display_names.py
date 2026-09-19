"""生成 ACNR sheet 显示名映射（sheet_code → 规范底稿名）。

数据源：workpaper_sheet_classification（权威真源，每张 sheet 的真实 tab 名
是 sheet_name 以自身 wp_code 结尾的那条，如「应收账款检查表D2-7」→ D2-7）。

catalog.list_sheets 会读取产出的 backend/data/acnr/sheet_display_names.json，
为导航树/选字段树补齐重名 sheet 的可区分名称（补 wp_account_mapping 的缺口）。

用法（cwd=backend）：python scripts/gen_sheet_display_names.py
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings

# 末尾底稿编码：字母(1~3)+数字[-数字]，如 D2-7 / N1-5 / A18 / IC1
_CODE_RE = re.compile(r"^(.*?)\s*([A-Za-z]{1,3}\d+(?:-\d+)?)$")

_OUT = Path(__file__).resolve().parents[1] / "data" / "acnr" / "sheet_display_names.json"


def _prefer(new_base: str, cur_base: str) -> bool:
    """同一 code 有多个候选名（如公允价值/成本模式变体）时的取舍：
    优先无括号变体，其次更短，保证确定性。"""
    new_paren = ("（" in new_base) or ("(" in new_base)
    cur_paren = ("（" in cur_base) or ("(" in cur_base)
    if new_paren != cur_paren:
        return not new_paren  # 无括号者优先
    return len(new_base) < len(cur_base)


_PREFILL_PATH = Path(__file__).resolve().parents[1] / "data" / "prefill_formula_mapping.json"


def _merge_prefill_names(code_names: dict[str, str]) -> int:
    """用 prefill_formula_mapping.json 的 wp_name 补齐 classification 未覆盖的
    纯编码 sheet（如上市损益类 K14~K18=资产处置收益/其他收益/投资收益/公允价值
    变动收益/递延收益审定表）。仅填缺，不覆盖 classification 已有真名。返回补入条数。
    """
    if not _PREFILL_PATH.exists():
        return 0
    try:
        with open(_PREFILL_PATH, encoding="utf-8-sig") as f:
            data = json.load(f)
    except Exception:  # pragma: no cover - 降级不阻断
        return 0
    filled = 0
    for m in data.get("mappings", []):
        code = (m.get("wp_code") or "").upper()
        name = (m.get("wp_name") or "").strip()
        if not code or not name or code in code_names:
            continue
        # 去掉可能的尾部编码后缀，保持与 classification 名称风格一致
        base = _CODE_RE.match(name)
        cleaned = base.group(1).strip() if base and base.group(1).strip() else name
        code_names[code] = cleaned
        filled += 1
    return filled


async def main() -> None:
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text("SELECT DISTINCT sheet_name FROM workpaper_sheet_classification")
                )
            ).fetchall()
    finally:
        await engine.dispose()

    code_names: dict[str, str] = {}
    for (name,) in rows:
        if not name:
            continue
        m = _CODE_RE.match(name.strip())
        if not m:
            continue
        base, code = m.group(1).strip(), m.group(2).upper()
        if not base:
            continue  # 纯编码（如 A18/K14），无描述名，跳过
        cur = code_names.get(code)
        if cur is None or _prefer(base, cur):
            code_names[code] = base

    # 兜底补名：prefill_formula_mapping.json（策管，含 wp_name/account_codes），
    # 仅填 classification 未覆盖的纯编码 sheet（如上市损益类 K14~K18）。
    filled = _merge_prefill_names(code_names)

    code_names = dict(sorted(code_names.items()))
    _OUT.write_text(
        json.dumps(code_names, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[OK] wrote {len(code_names)} sheet display names -> {_OUT} (prefill 补 {filled} 条)")


if __name__ == "__main__":
    asyncio.run(main())
