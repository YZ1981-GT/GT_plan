"""子企业附注保存时保护集团下推的固定行（spec note-pull-followup-closure R13）。

合并负责人「📤 下推模板」在子企业单体附注对应表上给模板行打行身份（``_pushed_row_id`` / ``_pushed_category``），合并拉数按
行身份对应合并模板行（``exact_id``）。固定行（``_pushed_category = required``）被子企业删掉、改名或去掉下推标记 ⇒ 合并
拉数对不上、少一行数，而且没有任何提示。保存时比对新旧表格数据：

- 旧数据里每个固定下推行，新数据里必须仍有同一 ``_pushed_row_id`` 的行；
- 该行的行名比较键（去空白）不变，``_pushed_category`` 仍是 required；
- 否则拒绝保存（409 ``PUSHED_ROW_PROTECTED``），逐行列出表名、行名与原因。

加行、改数、可选行（``optional``）的「本企业不适用」开关照常；旧数据没有固定下推行时不检查。下推服务自己写表格
（去掉已不在模板里的下推行标记）不经过这里。
"""
from __future__ import annotations

from typing import Any

__all__ = ["PUSHED_ROW_PROTECTED", "pushed_row_violations"]

PUSHED_ROW_PROTECTED = "PUSHED_ROW_PROTECTED"


def _tables(td: Any) -> list[dict]:
    from app.services.note_formula_tables import iter_note_tables

    return [t for _i, t in iter_note_tables(td)]


def _key(label: Any) -> str:
    return "".join(str(label or "").split())


def _fixed_rows(td: Any) -> dict[str, tuple[str, str]]:
    """固定下推行：行身份 → (表名, 行名)。"""
    out: dict[str, tuple[str, str]] = {}
    for table in _tables(td):
        for row in table.get("rows") or []:
            if (isinstance(row, dict) and row.get("_pushed_row_id")
                    and str(row.get("_pushed_category") or "required") == "required"):
                out.setdefault(str(row["_pushed_row_id"]), (str(table.get("name") or ""), str(row.get("label") or "")))
    return out


def pushed_row_violations(old_td: Any, new_td: Any) -> list[dict[str, str]]:
    """新数据里被删 / 改名 / 去掉下推标记的固定下推行 → ``[{table, row, problem}]``（没有违规返回空）。"""
    fixed = _fixed_rows(old_td)
    if not fixed:
        return []
    by_id: dict[str, dict] = {}
    for table in _tables(new_td):
        for row in table.get("rows") or []:
            if isinstance(row, dict) and row.get("_pushed_row_id"):
                by_id.setdefault(str(row["_pushed_row_id"]), row)
    out: list[dict[str, str]] = []
    for rid, (table, label) in fixed.items():
        row = by_id.get(rid)
        if row is None:
            out.append({"table": table, "row": label, "problem": "行被删除或去掉了集团下推标记"})
        elif _key(row.get("label")) != _key(label):
            out.append({"table": table, "row": label, "problem": f"行名被改成「{row.get('label') or ''}」"})
        elif str(row.get("_pushed_category") or "required") != "required":
            out.append({"table": table, "row": label, "problem": "固定行被改成了可选行"})
    return out
