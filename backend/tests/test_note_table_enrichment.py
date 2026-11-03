"""附注读时增强 ``note_table_enrichment.carry_template_table_names`` 守卫（R8.4 批 9b-2）。

- 同名优先：表名已是模板表名的表对齐到同名模板表，不按位置改名换表头（推送只带部分表 / 表序不同时按位置会串表）；
- 位置兜底：名字对不上模板的旧表（泄漏名）仍按位置回填模板表名；
- 分组跟模板走：模板生成的表换上模板表头时，模板已改一层的旧两层分组去掉（L3 长期借款）；底稿推送投影出来的表不动。

用真实种子（国企 八、18 / 八、49），表结构取自种子本身，不手抄。
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from app.services.note_table_enrichment import carry_template_table_names

_SOE = Path(__file__).resolve().parents[1] / "data" / "note_template_soe.json"


def _tables(section: str) -> list[dict]:
    doc = json.loads(_SOE.read_text(encoding="utf-8"))
    return next(s for s in doc["sections"] if s["section_number"] == section)["tables"]


def _projected(tpl: dict) -> dict:
    """底稿推送投影出来的表形态（投影器给 _source_sub_table_key）。"""
    return {
        "name": tpl["name"], "headers": list(tpl["headers"]), "rows": [],
        "_source_sub_table_key": tpl["name"], "_column_groups": copy.deepcopy(tpl.get("_column_groups") or []),
    }


def test_same_named_table_is_not_renamed_by_position() -> None:
    tpl = _tables("八、18")
    first_h0 = tpl[0]["headers"][0]
    # 前提：后面有一张首列与第 0 张同名的表 ⇒ 只按位置时它会被改名成第 0 张（判据非空转）
    k = next(i for i in range(1, len(tpl)) if tpl[i]["headers"][0] == first_h0)
    td = {"_tables": [_projected(tpl[k]), _projected(tpl[0])]}
    carry_template_table_names(td, "soe", "八、18")
    assert [t["name"] for t in td["_tables"]] == [tpl[k]["name"], tpl[0]["name"]]
    assert td["_tables"][0]["headers"] == tpl[k]["headers"]


def test_unknown_name_still_aligned_by_position() -> None:
    tpl = _tables("八、18")
    leaked = {"name": tpl[0]["headers"][0], "headers": list(tpl[0]["headers"]), "rows": []}
    td = {"_tables": [leaked]}
    carry_template_table_names(td, "soe", "八、18")
    assert td["_tables"][0]["name"] == tpl[0]["name"]


def test_stale_groups_follow_flat_template_but_projected_groups_kept() -> None:
    (tpl,) = _tables("八、49")
    assert not tpl.get("_column_groups"), "前提：八、49 长期借款已是一层表头"
    stale = [{"group": "期末余额", "start": 1, "span": 2}, {"group": "期初余额", "start": 3, "span": 2}]
    generated = {"name": tpl["name"], "headers": ["借款类别", "余额", "利率区间", "余额", "利率区间"],
                 "rows": [], "_column_groups": copy.deepcopy(stale)}
    projected = dict(_projected(tpl), _column_groups=copy.deepcopy(stale))
    td_gen, td_proj = {"_tables": [generated]}, {"_tables": [projected]}
    carry_template_table_names(td_gen, "soe", "八、49")
    carry_template_table_names(td_proj, "soe", "八、49")
    assert td_gen["_tables"][0]["headers"] == tpl["headers"]
    assert td_gen["_tables"][0]["_column_groups"] == []
    assert td_proj["_tables"][0]["_column_groups"] == stale


def _d2_tables() -> list[dict]:
    return _tables("八、5")


def test_leaked_name_with_other_first_header_is_not_renamed_by_position() -> None:
    """泄漏名（表名 = 自己首列表头）不再单独放行（R3.2）：存量 11 表旧结构第 3 张「债务人名称」表原先按位置被改成
    「（2）…（续：期初数）」并换上类别 / 金额表头，库里的数显示在错的列下。"""
    tpl = _d2_tables()
    assert _norm(tpl[2]["headers"][0]) != "债务人名称", "前提：同位置模板表的首列不是债务人名称"
    leaked = [{"name": "账  龄", "headers": list(tpl[0]["headers"]), "rows": []},
              {"name": "类  别", "headers": list(tpl[1]["headers"]), "rows": []},
              {"name": "债务人名称", "headers": ["债务人名称", "账面余额", "坏账准备", "账龄", "计提比例", "计提理由"],
               "rows": []}]
    td = {"_tables": copy.deepcopy(leaked)}
    carry_template_table_names(td, "soe", "八、5")
    assert td["_tables"][2]["name"] == "债务人名称" and td["_tables"][2]["headers"] == leaked[2]["headers"]
    assert td["_tables"][0]["name"] == tpl[0]["name"], "首列与列数都对得上的仍按位置回填表名"


def test_position_fallback_needs_the_same_column_count() -> None:
    tpl = _d2_tables()
    wider = {"name": "账龄（旧）", "headers": [tpl[0]["headers"][0], "期末数", "期初数", "备注"], "rows": []}
    td = {"_tables": [copy.deepcopy(wider)]}
    carry_template_table_names(td, "soe", "八、5")
    assert td["_tables"][0]["name"] == "账龄（旧）" and td["_tables"][0]["headers"] == wider["headers"]


def test_headerless_table_named_like_template_gets_headers() -> None:
    tpl = _d2_tables()
    td = {"_tables": [{"name": tpl[0]["name"], "rows": [{"label": "1年以内（含1年）", "values": [1.0, 2.0]}]}]}
    carry_template_table_names(td, "soe", "八、5")
    assert td["_tables"][0]["headers"] == tpl[0]["headers"]


def _norm(text: str) -> str:
    return "".join(str(text or "").split())
