"""守卫：单体与合并附注模板列名对齐。

扫描两版（listed / soe）单体模板的全部子表，与合并模板按表名匹配后逐列对比
（去掉期间前缀）。白名单外的差异（列名不一致 OR 列数不同）必须为 0。

白名单 = 已知的结构性差异（合并与单体的表体设计不同，非列名替换能修），
按 (template_type, consol_section_id) 登记。白名单不允许失效条目。

spec: note-template-header-alignment-between-standalone-and-consol
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[1] / "data"

_PERIOD_PREFIXES = sorted([
    "期末余额", "期初余额", "上年年末余额", "期末数", "期初数",
    "期末金额", "上年年末金额", "本期金额", "上期金额",
    "本年发生额", "上年发生额", "本期发生额", "上期发生额",
    "年初余额", "年末余额", "本年数", "上年数", "期末",
    "期初", "年初", "年末", "本期", "上期", "本年", "上年",
    "上年年末", "本期末", "上期末", "报告期末", "报告年初",
    "本年度", "上年度", "当期", "前期",
], key=len, reverse=True)


def _strip_period(col: str) -> str:
    for pfx in _PERIOD_PREFIXES:
        if col.startswith(pfx + "/"):
            return col[len(pfx) + 1:]
    return col


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s).replace("（", "(").replace("）", ")").strip()


def _consol_paths(sec: dict) -> list[str]:
    hdrs = sec.get("headers", [])
    return [_norm(h) for h in hdrs[1:]] if len(hdrs) > 1 else []


def _standalone_paths(sub: dict) -> list[str]:
    hdrs = sub.get("headers", [])
    cg = sub.get("_column_groups")
    if len(hdrs) <= 1:
        return []
    base = hdrs[1:]
    if not cg:
        return [_norm(h) for h in base]
    paths = []
    for i, h in enumerate(base):
        col_idx = i + 1
        group = ""
        for g in cg:
            if g.get("start", 0) <= col_idx < g.get("start", 0) + g.get("span", 1):
                group = g.get("group", "")
                break
        paths.append(_norm(f"{group}/{h}") if group else _norm(h))
    return paths


def _build_sub_index(tmpl: dict) -> dict[str, list[tuple[str, dict]]]:
    idx: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for sec in tmpl.get("sections", []):
        sid = sec.get("section_id", "")
        for st in sec.get("sub_tables") or sec.get("tables") or []:
            name = st.get("name", st.get("title", ""))
            if name:
                idx[_norm(name)].append((sid, st))
    return idx


# ── 白名单：已知结构性差异（列数不同 OR 列名语义完全不同，非列名替换能修）──
# 2026-10-23 初始登记 122 条。修好一处后删除对应条目。
# 格式: ("listed"|"soe", "consol_section_id")
_KNOWN_STRUCTURAL_DIFFS: set[tuple[str, str]] = {
    # --- listed ---
    ("listed", "五-10-1"), ("listed", "五-10-2"), ("listed", "五-10-6"),
    ("listed", "五-10-7"), ("listed", "五-10-8"), ("listed", "五-11-1"),
    ("listed", "五-11-2"), ("listed", "五-12-2"), ("listed", "五-13-2"),
    ("listed", "五-14-11"), ("listed", "五-14-5"), ("listed", "五-15-12"),
    ("listed", "五-15-2"), ("listed", "五-15-6"), ("listed", "五-16-1"),
    ("listed", "五-18-1"), ("listed", "五-19-2"), ("listed", "五-22-2"),
    ("listed", "五-23-3"), ("listed", "五-23-5"), ("listed", "五-24-1"),
    ("listed", "五-24-2"), ("listed", "五-25-1"), ("listed", "五-26-1"),
    ("listed", "五-27-1"), ("listed", "五-28-1"), ("listed", "五-28-2"),
    ("listed", "五-28-3"), ("listed", "五-28-4"), ("listed", "五-29-1"),
    ("listed", "五-30-2"), ("listed", "五-31-2"), ("listed", "五-32-1"),
    ("listed", "五-34-2"), ("listed", "五-34-3"), ("listed", "五-4-10"),
    ("listed", "五-4-12"), ("listed", "五-4-5"), ("listed", "五-4-7"),
    ("listed", "五-4-9"), ("listed", "五-43-4"), ("listed", "五-45-1"),
    ("listed", "五-49-1"), ("listed", "五-49-6"), ("listed", "五-49-7"),
    ("listed", "五-5-12"), ("listed", "五-57-1"), ("listed", "五-57-2"),
    ("listed", "五-62-1"), ("listed", "五-62-2"), ("listed", "五-62-3"),
    ("listed", "五-62-6"),
    ("listed", "五-74-2"),
    ("listed", "五-78-9"), ("listed", "五-8-10"), ("listed", "五-8-11"),
    ("listed", "五-8-12"), ("listed", "五-8-13"), ("listed", "五-8-14"),
    ("listed", "五-8-17"), ("listed", "五-8-8"), ("listed", "五-8-9"),
    ("listed", "六-1-2"), ("listed", "十一-关联交易情况-13"),
    ("listed", "十一-关联方应收应付款-1"), ("listed", "十七-净资产收益率和每股收益-1"),
    ("listed", "十七-境内外会计准则下会计数据差异-1"),
    ("listed", "十七-境内外会计准则下会计数据差异-2"), ("listed", "十六-1"),
    # --- soe ---
    ("soe", "七-本期发生的非同一-1"), ("soe", "七-重要非全资子公司-2"),
    ("soe", "五-10-2"), ("soe", "五-11-2"), ("soe", "五-12-2"),
    ("soe", "五-17-3"), ("soe", "五-18-3"), ("soe", "五-18-5"),
    ("soe", "五-18-7"), ("soe", "五-18-8"), ("soe", "五-24-1"),
    ("soe", "五-24-2"), ("soe", "五-27-1"), ("soe", "五-31-1"),
    ("soe", "五-31-2"), ("soe", "五-32-2"), ("soe", "五-33-2"),
    ("soe", "五-34-2"), ("soe", "五-4-10"), ("soe", "五-4-3"),
    ("soe", "五-4-6"), ("soe", "五-4-7"), ("soe", "五-4-9"),
    ("soe", "五-41-1"), ("soe", "五-49-1"), ("soe", "五-5-1"),
    ("soe", "五-5-2"), ("soe", "五-5-4"), ("soe", "五-5-5"),
    ("soe", "五-5-7"), ("soe", "五-50-2"), ("soe", "五-51-2"),
    ("soe", "五-54-3"), ("soe", "五-54-4"), ("soe", "五-54-5"),
    ("soe", "五-54-6"), ("soe", "五-57-1"), ("soe", "五-64-1"),
    ("soe", "五-64-2"), ("soe", "五-9-10"), ("soe", "五-9-12"),
    ("soe", "五-9-4"), ("soe", "五-9-6"), ("soe", "五-90-1"),
    ("soe", "十一-关联交易情况-1"), ("soe", "十一-关联交易情况-2"),
    ("soe", "十一-关联交易情况-3"), ("soe", "十一-关联方应收应付款-1"),
    ("soe", "十一-本公司的合营企业-1"),
}


def _scan():
    """返回 (diffs_outside_whitelist, actual_diff_sections)"""
    configs = [
        ("listed", "consol_note_sections_listed.json", "note_template_listed.json"),
        ("soe", "consol_note_sections_soe.json", "note_template_soe.json"),
    ]
    outside: list[dict] = []
    actual: set[tuple[str, str]] = set()

    for ttype, consol_file, standalone_file in configs:
        consol = json.loads((DATA / consol_file).read_bytes())
        standalone = json.loads((DATA / standalone_file).read_bytes())
        sub_idx = _build_sub_index(standalone)

        for csec in consol:
            csid = csec.get("section_id", "")
            ctitle = csec.get("title", "")
            c_paths = _consol_paths(csec)
            if not c_paths:
                continue
            key = _norm(ctitle)
            cands = sub_idx.get(key, [])
            if not cands:
                clean = re.sub(r"^续[：:]\s*", "", ctitle)
                cands = sub_idx.get(_norm(clean), [])
            if not cands:
                continue
            _, s_table = cands[0]
            s_paths = _standalone_paths(s_table)
            if not s_paths:
                continue

            wl_key = (ttype, csid)
            has_diff = False

            if len(c_paths) != len(s_paths):
                has_diff = True
                if wl_key not in _KNOWN_STRUCTURAL_DIFFS:
                    outside.append({"type": ttype, "section": csid, "title": ctitle[:40],
                                    "detail": f"列数 {len(c_paths)} vs {len(s_paths)}"})
            else:
                for ci in range(len(c_paths)):
                    cc = _strip_period(c_paths[ci])
                    sc = _strip_period(s_paths[ci])
                    if _norm(cc) != _norm(sc):
                        has_diff = True
                        if wl_key not in _KNOWN_STRUCTURAL_DIFFS:
                            outside.append({"type": ttype, "section": csid,
                                            "title": ctitle[:40],
                                            "detail": f"col{ci+1}: '{c_paths[ci]}' ↔ '{s_paths[ci]}'"})
                            break  # 同一 section 只报第一处
            if has_diff:
                actual.add(wl_key)

    return outside, actual


class TestNoteTemplateHeaderAlignment:

    def test_no_diffs_outside_whitelist(self):
        """白名单外的列差异（列名不一致或列数不同）必须为 0。"""
        outside, _ = _scan()
        if outside:
            details = "\n".join(
                f"  {d['type']} {d['section']} '{d['title']}': {d['detail']}"
                for d in outside[:30]
            )
            pytest.fail(
                f"白名单外差异 {len(outside)} 处（前 30 条）：\n{details}\n\n"
                f"修复方式：改单体模板 headers / _column_groups，或加入 _KNOWN_STRUCTURAL_DIFFS"
            )

    def test_no_stale_whitelist(self):
        """白名单无失效条目——两侧已一致的 section 必须从白名单删除。"""
        _, actual = _scan()
        stale = _KNOWN_STRUCTURAL_DIFFS - actual
        if stale:
            details = "\n".join(f"  {t} {s}" for t, s in sorted(stale))
            pytest.fail(
                f"白名单有 {len(stale)} 条失效条目（两侧已一致，应删除）：\n{details}"
            )
