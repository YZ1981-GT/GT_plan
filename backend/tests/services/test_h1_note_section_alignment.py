"""H1 固定资产附注章节结构契约.

锁定 ``backend/scripts/fix/fix_h1_note_section_alignment.py`` 的对齐结果，
权威源 = ``H1 固定资产.xlsx`` 的 ``附注披露信息（上市公司）`` / ``附注披露信息（国有企业）``。

锁定四件事：
1. §五、22（6 表）/ §八、22（5 表）表清单与列头逐字对齐源模板；
2. 上市「固定资产情况」列头已展开 ``……`` 占位列，与前端
   ``buildH1ListedColumns``（H1_LISTED_DEFAULT_CATEGORIES 顺序）逐字一致；
3. 11 张表 ``guidance`` 齐备（TAB 页签编制提示），且无空列名、无
   「可无限量添加行」占位假数据行；
4. ``text_sections`` 的小节标题能被 ``_match_title_to_table_idx`` 映射到
   每一张表（上市政府补助小节不再被吞成表标题、国企汇总表标题已补）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.disclosure_engine import (
    _carry_seed_table_guidance,
    _match_title_to_table_idx,
    classify_template_content,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LISTED_SECTION = "五、22"
SOE_SECTION = "八、22"

PLACEHOLDER_ROW_LABEL = "可无限量添加行"

#: 源模板「附注披露信息（上市公司）」逐表列头（R7 / R13 / R60 / R69 / R79 / R87）
#: 「固定资产情况」的 `……` 占位列展开为平台五类（H1_FA_CATEGORIES 口径）
LISTED_TABLES: dict[str, list[str]] = {
    "固定资产": ["项目", "期末余额", "上年年末余额"],
    "固定资产情况": [
        "项目", "房屋及建筑物", "机器设备", "运输设备", "办公设备", "其他设备", "合计",
    ],
    "暂时闲置的固定资产情况": ["项目", "账面原值", "累计折旧", "减值准备", "账面价值", "备注"],
    "通过经营租赁租出的固定资产": ["项目", "账面价值"],
    "未办妥产权证书的固定资产情况": ["项目", "账面价值", "未办妥产权证书原因"],
    "固定资产清理": ["项目", "期末余额", "上年年末余额", "转入清理的原因"],
}

#: 源模板「附注披露信息（国有企业）」逐表列头（R7 / R13 / R60 / R66 / R72）
#: 国企无「通过经营租赁租出的固定资产」，汇总/清理用「账面价值」口径
SOE_TABLES: dict[str, list[str]] = {
    "固定资产": ["项目", "期末账面价值", "期初账面价值"],
    "固定资产情况": ["项目", "期初余额", "本期增加", "本期减少", "期末余额"],
    "暂时闲置的固定资产情况": ["项目", "账面原值", "累计折旧", "减值准备", "账面价值", "备注"],
    "未办妥产权证书的固定资产情况": ["项目", "账面价值", "未办妥产权证书原因"],
    "固定资产清理": ["项目", "期末账面价值", "期初账面价值", "转入清理的原因"],
}

#: 国企「固定资产情况」五层结构标题（源模板 R14/R23/R32/R41/R50）
SOE_MOVEMENT_LAYERS = [
    "一、账面原值合计",
    "二、累计折旧合计",
    "三、固定资产账面净值合计",
    "四、固定资产减值准备合计",
    "五、固定资产账面价值合计",
]

#: 国企各层「其中：」类别（源模板 R15–R22）
SOE_MOVEMENT_CATEGORIES = [
    "其中：土地资产", "房屋、建筑物", "机器设备", "运输工具",
    "电子设备", "办公设备", "酒店业家具", "其他",
]


def _section(std: str) -> dict:
    path = DATA_DIR / f"note_template_{std}.json"
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    target = LISTED_SECTION if std == "listed" else SOE_SECTION
    hit = [s for s in raw["sections"] if str(s.get("section_number", "")).strip() == target]
    assert hit, f"{path.name} 缺少章节 {target}"
    return hit[0]


@pytest.fixture(scope="module")
def listed() -> dict:
    return _section("listed")


@pytest.fixture(scope="module")
def soe() -> dict:
    return _section("soe")


def _by_name(section: dict) -> dict[str, dict]:
    return {t["name"]: t for t in section.get("tables") or []}


# ─── 表清单与列头 ────────────────────────────────────────────────────────────

def test_listed_table_list(listed: dict) -> None:
    assert [t["name"] for t in listed["tables"]] == list(LISTED_TABLES)


def test_soe_table_list(soe: dict) -> None:
    assert [t["name"] for t in soe["tables"]] == list(SOE_TABLES)


def test_soe_has_no_operating_lease_table(soe: dict) -> None:
    """源模板国企 sheet 无「通过经营租赁租出的固定资产」段，不得凭空补表。"""
    assert "通过经营租赁租出的固定资产" not in _by_name(soe)


@pytest.mark.parametrize("name,headers", sorted(LISTED_TABLES.items()))
def test_listed_table_headers(listed: dict, name: str, headers: list[str]) -> None:
    assert _by_name(listed)[name]["headers"] == headers


@pytest.mark.parametrize("name,headers", sorted(SOE_TABLES.items()))
def test_soe_table_headers(soe: dict, name: str, headers: list[str]) -> None:
    assert _by_name(soe)[name]["headers"] == headers


def test_listed_movement_has_no_ellipsis_column(listed: dict) -> None:
    """`……` 占位列会让底稿同步出孤儿列（附注 TAB 永空 + 数据丢失）。"""
    assert "……" not in _by_name(listed)["固定资产情况"]["headers"]


# ─── 行结构 ──────────────────────────────────────────────────────────────────

def test_no_placeholder_data_rows(listed: dict, soe: dict) -> None:
    """源模板 A65/A74 的「可无限量添加行」是模板占位说明，不得渲染成披露数据行。"""
    offenders: list[str] = []
    for sec in (listed, soe):
        for t in sec["tables"]:
            for r in t.get("rows") or []:
                if str(r.get("label") or "").strip() == PLACEHOLDER_ROW_LABEL:
                    offenders.append(t["name"])
    assert not offenders, f"存在占位假数据行：{offenders}"


def test_listed_movement_row_structure(listed: dict) -> None:
    """上市①表：原值/累计折旧/减值准备三层 + 账面价值层（源模板 R14–R50）。"""
    labels = [r["label"] for r in _by_name(listed)["固定资产情况"]["rows"]]
    for head in ("一、账面原值：", "二、累计折旧", "三、减值准备", "四、账面价值"):
        assert head in labels, f"缺层次标题 {head}"
    assert labels.count("4.期末余额") == 3, "原值/折旧/减值三层各应有期末余额行"
    assert "1.期末账面价值" in labels and "2.期初账面价值" in labels


def test_soe_movement_five_layers(soe: dict) -> None:
    """国企①表：五层合计行 + 每层 8 个「其中：」类别（源模板 R14–R58）。"""
    rows = _by_name(soe)["固定资产情况"]["rows"]
    labels = [r["label"] for r in rows]
    assert [lab for lab in labels if lab in SOE_MOVEMENT_LAYERS] == SOE_MOVEMENT_LAYERS
    for layer in SOE_MOVEMENT_LAYERS:
        assert next(r for r in rows if r["label"] == layer).get("is_total") is True, layer
    for cat in SOE_MOVEMENT_CATEGORIES:
        assert labels.count(cat) == len(SOE_MOVEMENT_LAYERS), f"{cat} 应在 5 层各出现一次"


def test_soe_movement_uses_soe_category_terms(soe: dict) -> None:
    """国企术语与上市不同：房屋、建筑物 / 运输工具（非 房屋及建筑物 / 运输设备）。"""
    labels = [r["label"] for r in _by_name(soe)["固定资产情况"]["rows"]]
    assert "房屋及建筑物" not in labels
    assert "运输设备" not in labels


# ─── guidance / 列名 ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("std", ["listed", "soe"])
def test_every_table_has_guidance(std: str, listed: dict, soe: dict) -> None:
    sec = listed if std == "listed" else soe
    missing = [t["name"] for t in sec["tables"] if not str(t.get("guidance") or "").strip()]
    assert not missing, f"{std} 缺 guidance：{missing}"


def test_headers_have_no_blank(listed: dict, soe: dict) -> None:
    for sec in (listed, soe):
        for t in sec["tables"]:
            for h in t.get("headers") or []:
                assert str(h).strip(), f'{t["name"]} 存在空列名'


def test_listed_guidance_carries_source_red_text(listed: dict) -> None:
    """减值测试 / 抵押担保 / 高价出售 / 政府补助 / 并购净额 五段红字须落在①表提示。"""
    g = _by_name(listed)["固定资产情况"]["guidance"]
    for keyword in (
        "15号文第十九条（十九）",
        "重置成本法",
        "抵押、担保",
        "明显高于账面价值",
        "其他减少",
        "非同一控制下企业合并",
    ):
        assert keyword in g, f"①表 guidance 缺源模板红字要点：{keyword}"


def test_soe_guidance_states_na_conventions(soe: dict) -> None:
    """国企①表源模板列示约定：净值/账面价值层增减填「—」、土地不提折旧。"""
    g = _by_name(soe)["固定资产情况"]["guidance"]
    assert "土地资产不计提折旧" in g
    assert "本期增加 / 本期减少" in g


# ─── text_sections ↔ 表标题映射 ──────────────────────────────────────────────

@pytest.mark.parametrize("std", ["listed", "soe"])
def test_text_section_titles_cover_every_table(std: str, listed: dict, soe: dict) -> None:
    """每张表都应有一行小节标题能映射到它，否则渲染时该表无标题锚点。"""
    sec = listed if std == "listed" else soe
    names = [t["name"] for t in sec["tables"]]
    hit: set[int] = set()
    cursor = 0
    for line in sec.get("text_sections") or []:
        s = line.strip()
        if not s.startswith("#"):
            continue
        idx = _match_title_to_table_idx(s, names, cursor)
        if idx is not None:
            cursor = idx
            hit.add(idx)
    missing = [names[i] for i in range(len(names)) if i not in hit]
    assert not missing, f"{std} text_sections 缺小节标题：{missing}"


def test_listed_gov_subsidy_line_is_substantive_text(listed: dict) -> None:
    """源模板 R84 是⑤小节正文；带 `####` 前缀会被当标题**丢弃**导致披露文本消失。"""
    ts = listed.get("text_sections") or []
    assert "本期冲减固定资产账面价值的政府补助金额为XXX元，具体情况见附注八、政府补助。" in ts
    assert not any(
        s.startswith("#") and "政府补助金额为XXX元" in s for s in ts
    ), "政府补助正文不得作为表标题"

    substantive, _guidance, _per_table = classify_template_content(
        ts, listed.get("text_template"), listed.get("tables"),
    )
    assert substantive and "政府补助金额为XXX元" in substantive


def test_soe_summary_heading_present(soe: dict) -> None:
    """源模板 R6「15、固定资产」→ 汇总表小节标题，缺失会让 tables[0] 无标题。"""
    assert "### 固定资产" in (soe.get("text_sections") or [])


def test_soe_clearing_progress_note_retained(soe: dict) -> None:
    joined = "\n".join(soe.get("text_sections") or [])
    assert "转入固定资产清理起始时间已超过1年" in joined


# ─── 生成期透传（复刻 disclosure_engine 多表分支的 guidance 归属链）────────────

def _replay_generation(section: dict) -> list[dict]:
    """复刻 ``disclosure_engine`` 生成期的 guidance 归属顺序（不依赖 DB）。

    顺序与产线一致：段落游标推断 → seed 显式 guidance 覆盖。
    """
    tables_list = section["tables"]
    built = [
        {"name": t.get("name", ""), "headers": list(t.get("headers") or []), "rows": []}
        for t in tables_list
    ]
    _substantive, _section_guidance, per_table = classify_template_content(
        section.get("text_sections"), section.get("text_template"), tables_list,
    )
    for idx, g in per_table.items():
        if 0 <= idx < len(built) and g:
            built[idx]["guidance"] = g
    _carry_seed_table_guidance(tables_list, built)
    return built


@pytest.mark.parametrize("std", ["listed", "soe"])
def test_generated_tables_all_carry_guidance(std: str, listed: dict, soe: dict) -> None:
    """新建项目 / 重新生成附注时，每个 TAB 页签都应带上编制提示。"""
    built = _replay_generation(listed if std == "listed" else soe)
    missing = [t["name"] for t in built if not str(t.get("guidance") or "").strip()]
    assert not missing, f"{std} 生成期缺 guidance：{missing}"


def test_listed_cursor_inference_leaves_gaps_and_misattribution(listed: dict) -> None:
    """记录段落游标推断的既有缺陷，说明为何必须显式声明 guidance。

    实测（`classify_template_content`）：
    - 表 0「固定资产」汇总表与表 3「通过经营租赁租出的固定资产」推断结果为**空**
      —— 源模板这两段没有跟随的括注，TAB 页签会没有任何编制提示；
    - 源模板 R85「对于冲减无形资产或其他资产账面价值的政府补助…」属于⑤政府补助小节
      （无表），却被游标归到表 4「未办妥产权证书的固定资产情况」。
    """
    _substantive, _sg, per_table = classify_template_content(
        listed.get("text_sections"), listed.get("text_template"), listed["tables"],
    )
    assert not per_table.get(0), "汇总表推断应为空（故需 seed 显式声明）"
    assert not per_table.get(3), "经营租出表推断应为空（故需 seed 显式声明）"
    assert "冲减无形资产" in per_table.get(4, ""), "政府补助提示被错落到表 4（既有行为）"


def test_seed_guidance_overrides_listed_misattribution(listed: dict) -> None:
    """seed 显式 guidance 须覆盖推断结果：表 4 不再残留政府补助比照披露提示。"""
    built = _replay_generation(listed)
    by_name = {t["name"]: t["guidance"] for t in built}

    assert "合计 = 资产负债表" in by_name["固定资产"]
    assert "租赁准则" in by_name["通过经营租赁租出的固定资产"]

    title_guidance = by_name["未办妥产权证书的固定资产情况"]
    assert "未办妥产权证书" in title_guidance
    assert "冲减无形资产" not in title_guidance, "未办证表 guidance 不应残留政府补助提示"


def test_listed_gov_subsidy_amount_line_reaches_text_content(listed: dict) -> None:
    """R84 那句实质披露文本应进入正文（text_content），而非被当标题丢弃。"""
    substantive, _sg, _per = classify_template_content(
        listed.get("text_sections"), listed.get("text_template"), listed["tables"],
    )
    assert substantive and "政府补助金额为XXX元" in substantive


def test_soe_generated_guidance_matches_seed(soe: dict) -> None:
    """国企 5 表的生成期 guidance 应逐字等于模板 seed（不被段落推断污染）。

    国企源模板红字极少，段落游标推断结果为**空**（实测 per_table_guidance == {}），
    5 个 TAB 页签的提示完全依赖 seed 显式声明。
    """
    _substantive, _sg, per_table = classify_template_content(
        soe.get("text_sections"), soe.get("text_template"), soe["tables"],
    )
    assert per_table == {}, "国企推断应为空（提示全部来自 seed）"

    built = _replay_generation(soe)
    seed = {t["name"]: t["guidance"] for t in soe["tables"]}
    for t in built:
        assert t["guidance"] == seed[t["name"]], t["name"]
