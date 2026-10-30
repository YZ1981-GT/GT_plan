"""生成合并附注 section_id → 单体附注 note_section 映射配置文件。

用法：
  python scripts/seed/gen_consol_standalone_note_mapping.py
  python scripts/seed/gen_consol_standalone_note_mapping.py --dry-run

输出：backend/data/consol_note_section_mapping.json

映射逻辑（逐张合并表）：
1. 表标题 = 单体模板某张子表的表名（规范化口径与运行时读取层 ``_table_key`` 同源）→
   该子表所在单体章节（主章节优先：soe 八、/ listed 五、）。match_type=table_title
2. 「续：」类泛标题跟随同一合并章节上一张表：取单体同章节里紧随其后的续表。match_type=continuation
3. 其余表取同一合并章节（五-N）里表标题命中最多的单体章节，子表名留空。match_type=chapter
4. 整个合并章节都没有表标题命中：按 parent_section（中文科目名）匹配单体 section_title
   （精确 → 规范化 → 前缀）。match_type=exact / normed / fuzzy
5. 仍未匹配的标为 consol_only（合并特有章节，无单体对应）
6. 定了单体章节后，子表名再按标题行库选一次（``note_table_header_match.choose_unit``：名字缩小候选、
   列语义键重合度定，与运行时读取层同一函数）—— 只按表名会把国企 五-4-3（期初数续表）对到同名的
   「（续）」单项计提表。按表头改了子表名的标 match_type=structure

表标题优先、parent_section 兜底：表名比章节名具体（同一合并章节的表可能分属单体不同子表）。国企合并种子的章节号
与父章节曾自 五-10 起错后一章，R7.6 已按 Word 重对齐（守卫 ``test_consol_note_seed_word_identity.py``）。
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
sys.path.insert(0, str(ROOT))

from app.services.note_table_header_library import (  # noqa: E402  与运行时读取层同口径（续表只认标记）
    column_keys,
    table_identity,
    table_key as _table_key,
)
from app.services.note_table_header_match import choose_unit  # noqa: E402

# ─── 规范化函数（与 consol_note_formula_service.label_key 同源） ──────────

_WS = re.compile(r"[\s\u3000]+")
_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
# 去行首序号/标记（△ * 减： 其中：等）——与 consol_elimination_sheet_service.clean_row_name 同源
_PREFIX = re.compile(r"^[△*＊·•\s]*(\d+[.、．]?\s*)?")
_MARK = re.compile(r"^(减：|减:|加：|加:|其中：|其中:)")


def _norm(text: str) -> str:
    """去空白、HTML 标签、行首序号/标记。"""
    s = _BR.sub("", str(text or ""))
    s = _WS.sub("", s)
    s = _PREFIX.sub("", s)
    s = _MARK.sub("", s)
    return s.strip()


def _load_json(path: Path) -> list | dict:
    return json.loads(path.read_text(encoding="utf-8"))


#: 单体附注主章节（报表项目注释）：同名子表出现在多章时取它（母公司报表注释等不覆盖）
_MAIN_CHAPTER = {"soe": "八", "listed": "五"}

#: 章节标题清理后暴露的同名跨章节歧义。key = 合并表 section_id，value = 单体章节号。
#: 只登记已经按合并模板结构和单体母公司章逐张核过的项；不存在或不唯一时生成器拒绝，不按主章节猜。
_SECTION_TARGET_OVERRIDES: dict[str, dict[str, str]] = {
    "soe": {"十二-投资收益-1": "十二、投资收益"},
    "listed": {},
}

#: 合并表标题与单体表名说法不同、按名字认不出的对照：{口径: {合并表标题: (单体章节号, 单体表名)}}。
#: 2026-10-25（R8.4 批 9b-2）：合并种子的表标题照搬合并 Word 表前那段文字（不少是编制提示句，或「期末本公司已质押…」
#: 这类与底稿不同的说法）；单体表名按底稿披露表 / 前端推送名复位后（5914e315b 曾把单体表名同步成同一段 Word 文字、
#: 上市 五、4 另有一组照搬 应收款项融资 的 Word 名重复表，两边才「同名」），这些表只能靠这里对上。
#: 只补名字证据（加进表标题索引）：定章投票、章节内取表、续表跟随照常走 —— 同一合并标题在别章另有真同名表时
#: （上市「期末本公司已质押的应收票据」五、6 也有）按本合并章节取。条目失效（合并标题 / 单体章节 / 表不在了）生成即报错。
#: 国企 五-54-4「设定受益计划净负债（净资产）」不登记：单体按底稿是一张「设定受益计划情况」三组列合表，没有一一对应的表。
_TITLE_ALIASES: dict[str, dict[str, tuple[str, str]]] = {
    "listed": {
        "期末本公司已质押的应收票据": ("五、4", "期末已质押的应收票据"),
        "期末本公司已背书或贴现但尚未到期的应收票据": ("五、4", "期末已背书或贴现但尚未到期的应收票据"),
        "期末本公司因出票人未履约而将其转应收账款的票据": ("五、4", "期末因出票人未履约而其转应收账款的票据"),
        "按坏账计提方法分类": ("五、4", "按坏账计提方法分类（期末余额）"),
        "按单项计提坏账准备的应收票据": ("五、4", "按单项计提坏账准备的应收票据（期末余额）"),
        "转回或收回金额重要的坏账准备": ("五、4", "本期转回或收回金额重要的坏账准备"),
        "如果企业经常贴现或背书信用等级较高的银行承兑的汇票，则其业务模式可能是既以收取合同现金流量为目标又以出售该金融资产"
        "为目标，从而可能需要在“应收款项融资”项目列报。】": ("五、6", "应收款项融资"),
        "（采用公允价值计量模式的投资性房地产，分类列示期初余额、期末余额和本期增减变动情况。）": (
            "五、21", "按公允价值计量的投资性房地产"),
        "（披露期末未办妥产权证书的固定资产账面价值及原因。）": ("五、22", "未办妥产权证书的固定资产情况"),
        "⑥（按照《知识产权相关会计信息披露规定》（财会〔2018〕30号），应当单独披露对企业财务报表具有重要影响的单项无形资产的"
        "内容、账面价值和剩余摊销期限。）": ("五、26", "重要单项无形资产"),
        "资产组的可收回金额是依据管理层编制的五年期预测，采用未来现金流量折合现值计算。超过该五年期的现金流量采用以下所述的"
        "估计增长率作出推算。采用未来现金流量折现方法所运用的假设主要包括：": ("五、28", "商誉减值测试关键假设"),
        "业绩承诺完成及对应商誉减值情况如下：": ("五、28", "业绩承诺完成及商誉减值情况"),
    },
    "soe": {
        "（1）商誉账面原值": ("八、29", "（1）商誉账面价值"),
    },
}


def _add_title_aliases(template_type: str, consol_tables: list, singles: list[dict],
                       by_table: dict[str, list[tuple[dict, str]]]) -> None:
    """把 ``_TITLE_ALIASES`` 加进表标题索引；条目失效即报错（不静默放过对照表过期）。"""
    titles = {_table_key(t.get("title")) for t in consol_tables}
    by_number = {s.get("section_number"): s for s in singles}
    for title, (number, name) in _TITLE_ALIASES.get(template_type, {}).items():
        single = by_number.get(number)
        if _table_key(title) not in titles or single is None or name not in {
                t.get("name") for t in single.get("tables") or []}:
            raise ValueError(f"合并↔单体表名对照失效（{template_type}）：「{title}」→ {number}「{name}」")
        by_table.setdefault(_table_key(title), []).append((single, name))


def _is_generic_continuation(title: str) -> bool:
    """「续：」这类只表示接上一张表的泛标题。"""
    return _norm(title).rstrip(":：") in ("续", "")


_STANDALONE_TABLES: dict[str, dict[str, list[dict]]] = {}


def _standalone_tables(template_type: str, section_number: str) -> list[dict]:
    """子企业单体附注实际有的表（单体口径章节；与库目录、运行时读取同一来源）。"""
    if template_type not in _STANDALONE_TABLES:
        from app.services.note_table_header_catalog import standalone_sections

        _STANDALONE_TABLES[template_type] = dict(standalone_sections(template_type))
    return _STANDALONE_TABLES[template_type].get(section_number) or []


def _choose_table(template_type: str, consol_table: dict, single: dict, table_name: str | None) -> tuple[str | None, str]:
    """在已定的单体章节里按标题行库选子表（与运行时读取层同一个 choose_unit）。返回 (子表名, 选表方式)。

    只用单体口径章节的表（子企业单体附注里没有的表选了也拉不到）；章节只有一张表、一列金额都对不上时
    不硬填表名。
    """
    tables = _standalone_tables(template_type, str(single.get("section_number") or ""))
    if not tables:
        return table_name, ""
    target = column_keys(
        consol_table,
        identity=table_identity(f"{template_type}_consolidated", str(consol_table.get("section_id") or "")),
    ) if consol_table.get("headers") else None
    choice = choose_unit(
        tables, target_keys=target, table_name=table_name, title=consol_table.get("title"),
        section_title=single.get("section_title"),
    )
    if choice.primary is None:
        return table_name, ""
    amounts = [k for k in (target or [])[1:] if k.kind == "amount" and (k.period or k.measure)]
    if choice.method == "single_table" and amounts and not (choice.match and choice.match.col_map):
        return table_name, ""
    return tables[choice.primary].get("name"), choice.method


def _continuation_of(template_type: str, section_number: str, prev_table: str | None) -> str | None:
    """「续：」接上一张：取单体同章节里续上一张子表（或与它同基名的表）的续表；不唯一返回 None。"""
    from app.services.note_table_header_library import base_key, continuation_links

    tables = _standalone_tables(template_type, section_number)
    if not tables or not prev_table:
        return None
    base = base_key(prev_table)
    owners = {i for i, t in enumerate(tables) if _table_key(t.get("name")) == _table_key(prev_table) or (
        base and base_key(t.get("name")) == base)}
    conts = sorted(i for i, lk in continuation_links(tables).items() if lk.of in owners)
    if len(conts) == 1:
        return tables[conts[0]].get("name")
    exact = [i for i in sorted(owners) if _table_key(tables[i].get("name")) == _table_key(prev_table)]
    after = [i for i in conts if exact and i > exact[0]]
    # 多张续表：取紧跟上一张子表（表名精确相同的第一张）之后的那张
    return tables[after[0]].get("name") if after else None


def generate(template_type: str) -> tuple[list[dict], Counter]:
    # 合并模板
    consol_path = DATA / f"consol_note_sections_{template_type}.json"
    consol_tables = _load_json(consol_path)
    if not isinstance(consol_tables, list):
        consol_tables = []

    # 单体模板
    single_path = DATA / f"note_template_{template_type}.json"
    single_data = _load_json(single_path)
    single_sections = single_data.get("sections", []) if isinstance(single_data, dict) else []
    # 只取有表格的章节；主章节优先，其余按文档顺序
    main = _MAIN_CHAPTER.get(template_type, "八")
    sorted_singles = sorted(
        (s for s in single_sections if s.get("tables")),
        key=lambda s: (0 if str(s.get("section_number", "")).startswith(main) else 1, s.get("sort_order", 9999)),
    )
    singles_by_number = {str(s.get("section_number") or ""): s for s in sorted_singles}
    for consol_id, target_code in _SECTION_TARGET_OVERRIDES.get(template_type, {}).items():
        if target_code not in singles_by_number:
            raise ValueError(f"合并↔单体章节覆盖失效（{template_type}）：{consol_id} → {target_code}")

    # 子表名索引：规范化表名 → [(单体章节, 子表名)]（主章节在前）
    by_table: dict[str, list[tuple[dict, str]]] = {}
    for s in sorted_singles:
        for t in s.get("tables") or []:
            key = _table_key(t.get("name"))
            if key and not _is_generic_continuation(t.get("name", "")):
                by_table.setdefault(key, []).append((s, t.get("name")))
    _add_title_aliases(template_type, consol_tables, sorted_singles, by_table)

    # 按 section_title 索引单体（精确 + 规范化两份索引）——合并章节没有任何表标题命中时兜底
    single_exact: dict[str, dict] = {}
    single_normed: dict[str, dict] = {}
    for s in sorted_singles:
        title = s.get("section_title", "")
        if title:
            # 八章优先：如果已有八章的映射，不被十章等覆盖
            if title not in single_exact:
                single_exact[title] = s
            normed_title = _norm(title)
            if normed_title not in single_normed:
                single_normed[normed_title] = s
        # 也按 account_name 索引
        acct = s.get("account_name", "")
        if acct and acct != title:
            if acct not in single_exact:
                single_exact[acct] = s
            normed_acct = _norm(acct)
            if normed_acct not in single_normed:
                single_normed[normed_acct] = s

    def _by_parent(parent: str) -> tuple[dict | None, str]:
        if parent in single_exact:
            return single_exact[parent], "exact"
        normed_parent = _norm(parent)
        if normed_parent in single_normed:
            return single_normed[normed_parent], "normed"
        for sk, sv in single_normed.items():  # 前缀匹配（处理截断名）
            if sk and normed_parent and (sk.startswith(normed_parent) or normed_parent.startswith(sk)):
                return sv, "fuzzy"
        return None, "consol_only"

    # 按合并章节（五-N）分组，保持模板顺序
    chapters: dict[str, list[dict]] = {}
    for t in consol_tables:
        sid = str(t.get("section_id") or "")
        if sid:
            chapters.setdefault(sid.rsplit("-", 1)[0], []).append(t)

    mappings: list[dict] = []
    stats: Counter = Counter()
    for tables in chapters.values():
        # 1. 逐表按表标题找单体子表
        hits_per_table = [
            [] if _is_generic_continuation(t.get("title", "")) else by_table.get(_table_key(t.get("title")), [])
            for t in tables
        ]
        # 2. 本合并章节的单体章节：只按「表名全模板唯一」的命中投票（同名子表散在多章，如
        #    「收回或转回的坏账准备」八、5 / 八、9 都有，不能参与定章）；全无命中按 parent_section 兜底
        votes = Counter(
            {s["section_number"] for s, _ in hits}.pop()
            for hits in hits_per_table if hits and len({s["section_number"] for s, _ in hits}) == 1
        )
        if votes:
            top = votes.most_common(1)[0][0]
            chapter_single = next(s for hits in hits_per_table for s, _ in hits if s["section_number"] == top)
            fallback_how = "chapter"
        else:
            chapter_single, fallback_how = _by_parent(str(tables[0].get("parent_section") or ""))
        # 定章兜底只认报表项目注释主章节：合并特有章节（合并范围变更等）里标题没命中的表
        # 没有单体对应，不能因为同章有一两张表重名就整章挂到单体某节
        fallback_single = (
            chapter_single
            if chapter_single is not None and str(chapter_single.get("section_number", "")).startswith(main)
            else None
        )

        # 3. 同名子表散在多章时取本章节那一张，否则取主章节在前的那张
        resolved: list[tuple[dict | None, str | None, str]] = []
        for hits in hits_per_table:
            if not hits:
                resolved.append((None, None, ""))
                continue
            in_chapter = [h for h in hits if chapter_single is not None and h[0] is chapter_single]
            s, name = (in_chapter or hits)[0]
            resolved.append((s, name, "table_title"))

        for i, t in enumerate(tables):
            single, table_name, how = resolved[i]
            override_code = _SECTION_TARGET_OVERRIDES.get(template_type, {}).get(str(t.get("section_id") or ""))
            if override_code:
                single, how = singles_by_number[override_code], "section_override"
            if single is None and fallback_single is not None:
                single, how = fallback_single, fallback_how
                # 「续：」接上一张表：取单体同章节里续上一张子表的续表（标题行库认续表，不按「紧随其后」猜）
                prev_single, prev_table, _ = resolved[i - 1] if i else (None, None, "")
                if _is_generic_continuation(t.get("title", "")) and prev_single is single and prev_table:
                    cont = _continuation_of(template_type, str(single.get("section_number") or ""), prev_table)
                    if cont:
                        table_name, how = cont, "continuation"
            if single is not None:
                chosen, method = _choose_table(template_type, t, single, table_name)
                if chosen and _table_key(chosen) != _table_key(table_name or "") and method in ("structure", "name"):
                    table_name, how = chosen, "structure" if method == "structure" else how
                elif chosen and not table_name:
                    table_name = chosen
            resolved[i] = (single, table_name, how)  # 下一张「续：」按改过的子表名接
            stats[how or "consol_only"] += 1
            mappings.append({
                "consol_section_id": t.get("section_id", ""),
                "consol_parent": t.get("parent_section", ""),
                "consol_title": t.get("title", ""),
                "consol_seq": t.get("seq", 0),
                "standalone_note_section": single.get("section_number", "") if single else None,
                "standalone_section_title": single.get("section_title", "") if single else None,
                "match_type": how if single else "consol_only",
                "standalone_table_name": table_name if single else None,
            })

    return mappings, stats


def main():
    dry_run = "--dry-run" in sys.argv

    result = {"version": 1, "description": "合并附注 → 单体附注章节映射（自动生成）", "mappings": {}}

    for tt in ("soe", "listed"):
        mappings, stats = generate(tt)
        result["mappings"][tt] = mappings
        total = sum(stats.values())
        print(f"\n{tt.upper()}: {total} 张合并表")
        for k, v in stats.most_common():
            print(f"  {k}: {v}")
        resolved = total - stats.get("consol_only", 0)
        print(f"  已映射: {resolved}/{total} ({resolved*100//max(total,1)}%)")

    # 统计映射条目总数
    total_entries = sum(len(v) for v in result["mappings"].values())
    print(f"\n映射条目总数: {total_entries}")

    out_path = DATA / "consol_note_section_mapping.json"
    if dry_run:
        print(f"\n[DRY RUN] 不写入 {out_path}")
        # 打印几条样例
        for tt in ("soe",):
            print(f"\n{tt} 样例（前 5 条）:")
            for entry in result["mappings"][tt][:5]:
                print(f"  {entry['consol_section_id']}: {entry['consol_parent']}"
                      f" → {entry['standalone_note_section'] or '(无)'}"
                      f" [{entry['match_type']}]")
            # consol_only 的
            only = [e for e in result["mappings"][tt] if e["match_type"] == "consol_only"]
            if only:
                print(f"\n{tt} consol_only（前 5 条）:")
                for entry in only[:5]:
                    print(f"  {entry['consol_section_id']}: {entry['consol_parent']}")
    else:
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已写入 {out_path}")


if __name__ == "__main__":
    main()
