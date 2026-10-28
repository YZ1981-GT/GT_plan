"""从附注模板 JSON 生成子表级公式推送规则。

读取 note_template_{soe|listed}.json 的子表结构，为每张有 columns 的子表
生成一条推送规则（只生成，不写入 formula_push_rules.json——需人工审核后追加）。

用法：
    python scripts/gen/gen_subtable_push_rules.py [--write] [--wp-code D2]

不带 --write 则只打印到 stdout；--write 追加到 formula_push_rules.json。
--wp-code 可过滤只生成指定底稿的规则。

⚠ 2026-10-25（spec consol-note-header-library-and-node-reaggregate R8.4 批 9b-2）：子表规则与主表共用 binding 的取数行
（科目合计），命中合计行兜底的规则会把科目合计写进子表合计行 ⇒ 由 ``tests/test_formula_push_subtable_total_fallback.py``
逐条裁决（当日删掉的 22 条写错数规则重跑本脚本会补回，守卫会点名）。
2026-10-27（spec note-pull-followup-closure R2.2）：①只生成字段取得到值（映射到 ending / opening）的规则 ②``section_by_template``
只给模板章节里真有这张同名表的那一版（原先两版都填，引擎在另一版回退写首表）③``EXCLUDED_RULES`` 按语义删除过的不补回。
引擎侧子表规则只按精确表名定位（``note_writer.locate_table(exact=True)``），守卫 ``tests/test_formula_push_note_rule_targets.py``。

spec: formula-push-subtable-expansion Phase 1
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RULES_PATH = DATA / "formula_push_rules.json"
REGISTRY_PATH = DATA / "note_workpaper_sync_registry.json"

# NOTE_FIELDS 中已注册的字段（子表级规则只用已注册的）——必须与 note_writer.NOTE_FIELDS 同步
KNOWN_FIELDS = {
    "end_amount", "prior_amount",
    "end_balance", "end_provision", "end_book_value",
    "prior_balance", "prior_provision", "prior_book_value",
    "opening", "ending",
    "increase_provision", "increase_other",
    "decrease_reversal", "decrease_writeoff", "decrease_other",
    "provision_amount", "reversal_amount", "writeoff_amount", "transfer_amount",
    "ratio", "loss_rate", "carrying_value", "book_amount",
    "prior_ratio", "prior_loss_rate", "prior_carrying_value", "prior_book_amount",
    "end_gross", "end_impairment", "end_net",
    "prior_gross", "prior_impairment", "prior_net",
    # Phase 2 新增
    "end_revenue", "end_cost", "prior_revenue", "prior_cost",
    "cat_1_revenue", "cat_1_cost", "cat_2_revenue", "cat_2_cost",
    "cat_3_revenue", "cat_3_cost", "cat_4_revenue", "cat_4_cost",
    "year1", "year2", "total",
    "end_book_balance", "prior_book_balance",
    "end_provision_rate", "prior_provision_rate",
    "end_loss_rate",
    # D2 应收账款子表
    "balance", "provision", "book_value",
    "reversal", "write_off", "amount",
    "cumulative_provision", "end_ratio",
    "ar_amount", "contract_asset_amount", "total_amount",
    "gain_loss", "asset_amount", "liability_amount",
}

# 表名最大长度——超长的表名通常是指引文本误入，跳过
_MAX_TABLE_NAME_LEN = 60

#: 子表规则与主表共用 binding 的取数行：除 D1 主表外，取数行只有 ``ending`` / ``opening`` 两个值（tier_a / note_direct /
#: balance_adj / e1 / k1 同口径）⇒ 字段经 ``note_writer.NOTE_FIELDS`` 映射不到这两个值的，规则永远写不出数（2026-10-27
#: 清点 99 条，且取数行对上附注行时原来还会 KeyError 让整张底稿回滚 —— spec note-pull-followup-closure R2.2）
_ACCOUNT_VALUE_KEYS = frozenset({"ending", "opening"})

#: 字段映射得到期末 / 期初、但写进去就是错数 / 永远写不出的子表（按（底稿, 表名）认 —— rule_id 里的表序号随模板改表序会漂）；
#: 重跑本脚本不得补回（2026-10-27 起由本表拦住；此前「当日删掉的规则重跑会补回、靠守卫点名」—— note-pull-followup-closure R2.2）
_NOT_ACCOUNT_TOTAL = "科目合计不是这张表的合计（部分 / 明细 / 变动 / 前 N 名 / 账龄超 1 年 / 逾期 / 继续涉入），合计行兜底写进去就是错数"
EXCLUDED_TABLES: dict[tuple[str, str], str] = {
    # 2026-10-27 语义裁决（design §3.1）
    ("F2", "存货跌价准备及合同履约成本减值准备"): "binding 不给子表出行（账面价值口径），且科目余额不是减值准备变动",
    ("F2", "开发产品"): "binding 不给子表出行（账面价值口径）",
    ("F2", "周转房"): "binding 不给子表出行（账面价值口径）",
    ("K2", "碳排放配额变动情况"): "其他流动资产科目余额不是配额变动",
    ("M2", "股本（单位：万股）"): "试算表金额是元，写进万股表就是错数",
    # 2026-10-25 删除的写错数规则（consol-note-header-library-and-node-reaggregate R8.4 批 9b-2）
    ("D2", "（1）按账龄披露应收账款"): "与主表 D2.note.main 同表同字段，重复推送",
    **dict.fromkeys((
        ("E1", "受限制的货币资金明细"), ("D2", "期末单项计提坏账准备的应收账款"),
        ("D2", "组合计提项目：应收中央企业客户"), ("D2", "组合计提项目：应收中央企业客户（续：期初数）"),
        ("D2", "组合计提项目：应收海外企业客户"), ("D2", "组合计提项目：应收海外企业客户（续：期初数）"),
        ("D2", "采用余额百分比或其他组合方法计提坏账准备的应收账款"), ("D2", "（3）本期计提、收回或转回的坏账准备情况"),
        ("F1", "按欠款方归集的期末余额前五名的预付款项"), ("K6", "持有待售资产减值准备"),
        ("G5", "转移长期应收款且继续涉入形成的资产、负债的金额"), ("L1", "已逾期未偿还的短期借款情况"),
        ("F4", "账龄超过1 年的重要应付账款"), ("D3", "账龄超过1年的重要预收账款"), ("K3", "账龄超过1年的重要其他应付款项"),
        ("L5", "①长期应付款项期末余额最大的前5 项"), ("L5", "①专项应付款期末余额最大的前5 项"),
        ("K7", "其中：递延收益-政府补助情况"), ("G4", "债权投资减值准备本期变动情况"), ("G6", "其他债权投资减值准备本期变动情况"),
        ("D7", "账龄超过1年的重要合同负债"), ("K3", "其中，账龄超过1年的重要其他应付款"),
        ("M9", "资产负债表中归属于母公司的其他综合收益："),
        # 2026-10-27 按口径生成后另一版里冒出来的同类表（同一裁决）
        ("D2", "组合计提项目：应收地方国有企业客户"), ("D2", "组合计提项目：组合4"), ("D2", "组合计提项目：组合5"),
        ("F1", "按预付对象归集的预付款项期末余额前五名单位情况"), ("L1", "（2）逾期借款情况"),
        ("F4", "其中，账龄超过1年的重要应付账款"), ("D3", "账龄超过1年的重要预收款项"),
    ), _NOT_ACCOUNT_TOTAL),
    ("D2", "按账龄披露"): "上市版主表（D2.note.main 已推），重复推送",
    ("M2", "实收资本"): "国企版主表（M2.note.main 已推），重复推送",
    ("K6", "持有待售负债"): "binding 取数行是持有待售资产 + 负债两个科目（合计 = 两者之和），不是负债表的合计",
    ("L5", "长期应付款（按款项性质列示）"): "L5 只有主表规则；按性质分类表未裁决合计口径，宁缺勿造",
    ("L5", "专项应付款"): "按项目列示的变动表（期初 / 增加 / 减少 / 期末），L5 取数行不是它的合计",
}


def _note_value_key(field: str) -> str | None:
    """规则字段 → 取数行值键（与引擎同一张 ``NOTE_FIELDS``；脚本独立运行时导入不到 app 就按同名退化）。"""
    try:
        from app.services.formula_push.note_writer import NOTE_FIELDS
    except ImportError:  # pragma: no cover —— 脚本从仓库根以外运行
        sys.path.insert(0, str(ROOT))
        from app.services.formula_push.note_writer import NOTE_FIELDS
    entry = NOTE_FIELDS.get(field)
    return entry[0] if entry else None


def load_registry() -> dict[str, dict[str, str]]:
    doc = json.loads(REGISTRY_PATH.read_text("utf-8"))
    out: dict[str, dict[str, str]] = {}
    for e in doc.get("entries") or []:
        code = str(e.get("wp_code") or "").strip()
        if code:
            out[code] = {k: str(e.get(k) or "").strip() for k in ("listed", "soe") if str(e.get(k) or "").strip()}
    return out


def load_existing_rules() -> set[str]:
    """已有规则的 rule_id 集合。"""
    doc = json.loads(RULES_PATH.read_text("utf-8"))
    return {r["rule_id"] for r in doc.get("rules", [])}


def table_fields(tbl: dict) -> list[str]:
    """从子表的 columns 提取数值字段（排除 is_label；只留取数行取得到值的字段，见 ``_ACCOUNT_VALUE_KEYS``）。"""
    cols = tbl.get("columns", [])
    fields = []
    for c in cols:
        if not isinstance(c, dict) or c.get("is_label"):
            continue
        key = c.get("key", "")
        if key and key in KNOWN_FIELDS and _note_value_key(key) in _ACCOUNT_VALUE_KEYS:
            fields.append(key)
    return fields


def _section_tables(template: dict, section_number: str | None) -> set[str]:
    for sec in template.get("sections", []):
        if section_number and sec.get("section_number") == section_number:
            return {str(t.get("name") or "") for t in sec.get("tables", [])}
    return set()


def _load_existing_main_derivations() -> dict[str, tuple[str, str]]:
    """从现有规则中提取每个 wp_code 的主表 (rows, source.name) 对。

    rows = target.rows（用于新规则的 target.rows）
    source_name = source.name（用于新规则的 source.name，校验器按此查已实现列表）
    """
    doc = json.loads(RULES_PATH.read_text("utf-8"))
    out: dict[str, tuple[str, str]] = {}
    for r in doc.get("rules", []):
        if r.get("target", {}).get("domain") != "note":
            continue
        pk = r.get("page_key", "")
        if not pk.startswith("workpaper:"):
            continue
        code = pk.split(":", 1)[1]
        rows = r.get("target", {}).get("rows")
        source_name = r.get("source", {}).get("name")
        if rows and source_name and code not in out:
            out[code] = (rows, source_name)
    return out


def _load_existing_note_tables() -> set[tuple[str, str, str]]:
    """现有规则已推的（口径, 章节, 表名）—— 表名按口径取（``table_by_template`` 优先），用于检测跨 wp_code 的同章节同表名
    冲突（如 K3 子表「应付利息」与 L2 主表撞同一章节）与同一张表换了口径名的规则。"""
    doc = json.loads(RULES_PATH.read_text("utf-8"))
    out: set[tuple[str, str, str]] = set()
    for r in doc.get("rules", []):
        target = r.get("target", {})
        if target.get("domain") != "note":
            continue
        for std, sec in (target.get("section_by_template") or {}).items():
            name = (target.get("table_by_template") or {}).get(std) or target.get("table")
            if name and sec:
                out.add((std, sec, name))
    return out


def generate_rules(wp_code_filter: str | None = None) -> list[dict]:
    """生成子表级推送规则。"""
    registry = load_registry()
    existing = load_existing_rules()
    main_derivations = _load_existing_main_derivations()
    existing_tables = _load_existing_note_tables()
    # 已生成的 (wp_code, table_name) 对——跨准则模板去重
    generated_tables: set[tuple[str, str]] = set()
    new_rules: list[dict] = []
    templates = {
        std: json.loads((DATA / f"note_template_{std}.json").read_text("utf-8"))
        for std in ("soe", "listed") if (DATA / f"note_template_{std}.json").exists()
    }

    for std in ("soe", "listed"):
        tpl = templates.get(std)
        if tpl is None:
            continue

        for sec in tpl.get("sections", []):
            sn = sec.get("section_number", "")
            if not sn:
                continue

            # 反查 wp_code
            wp_code = None
            for code, mapping in registry.items():
                if mapping.get(std) == sn:
                    wp_code = code
                    break
            if not wp_code:
                continue
            if wp_code_filter and wp_code != wp_code_filter:
                continue

            for ti, tbl in enumerate(sec.get("tables", [])):
                tname = tbl.get("name", "")
                if not tname:
                    continue

                # 过滤超长表名（指引文本误入模板的 name 字段）
                if len(tname) > _MAX_TABLE_NAME_LEN:
                    continue

                fields = table_fields(tbl)
                if not fields:
                    # 无已注册字段 → 跳过（该表可能纯文本或格式未知）
                    continue

                # 生成 rule_id：{WP_CODE}.note.subtable_{表序号}
                rule_id = f"{wp_code}.note.subtable_{ti}"
                if rule_id in existing or (wp_code, tname) in EXCLUDED_TABLES:
                    continue  # 已存在 / 按语义裁决删除过

                # section_by_template：只给模板章节里真有这张表（同名）的那一版 —— 原先两版都填，另一版里没有这张表时引擎
                # 回退写首表（2026-10-27 清点 74 个口径对表名错版，spec note-pull-followup-closure R2.2）
                sbt: dict[str, str] = {}
                for v in ("listed", "soe"):
                    sec_v = registry.get(wp_code, {}).get(v)
                    if sec_v and tname in _section_tables(templates.get(v) or {}, sec_v):
                        sbt[v] = sec_v

                # 排除现有规则已推的（口径, 章节, 表名）
                sbt = {v: s for v, s in sbt.items() if (v, s, tname) not in existing_tables}
                if not sbt:
                    continue

                # 跨准则模板去重：同一 (wp_code, table_name) 只生成一条
                if (wp_code, tname) in generated_tables:
                    continue

                # 复用主表规则的 derivation 名（子表取数走同一 binding 的 note_rows）
                main_info = main_derivations.get(wp_code)
                if not main_info:
                    continue  # 无主表规则的科目暂不生成子表规则
                main_rows, main_source_name = main_info

                rule = {
                    "rule_id": rule_id,
                    "page_key": f"workpaper:{wp_code}",
                    "stage": "note",
                    "policy": "editable",
                    "target": {
                        "domain": "note",
                        "section_by_template": sbt,
                        "table": tname,
                        "rows": main_rows,
                        "fields": fields,
                    },
                    "source": {
                        "kind": "derivation",
                        "name": main_source_name,
                        "formula_text": (
                            f"数据来源：披露表 → 附注。从底稿 {wp_code} 的子表"
                            f"「{tname}」读取行数据，按 {'/'.join(fields)} 字段写入附注"
                        ),
                    },
                    "triggers": ["WORKPAPER_SAVED", "manual"],
                    "description": (
                        f"{tname}子表推送（{'/'.join(sbt.values())}）"
                        f"{'/'.join(fields)}；数据来源：披露表"
                    ),
                }
                new_rules.append(rule)
                existing.add(rule_id)  # 防同一规则ID重复
                generated_tables.add((wp_code, tname))  # 跨准则模板去重

    return new_rules


def main():
    parser = argparse.ArgumentParser(description="生成子表级公式推送规则")
    parser.add_argument("--write", action="store_true", help="追加到 formula_push_rules.json")
    parser.add_argument("--wp-code", type=str, default=None, help="只生成指定底稿的规则")
    args = parser.parse_args()

    rules = generate_rules(args.wp_code)
    print(f"生成了 {len(rules)} 条子表级规则")

    if not rules:
        return

    if args.write:
        doc = json.loads(RULES_PATH.read_text("utf-8"))
        doc["rules"].extend(rules)
        RULES_PATH.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"已追加到 {RULES_PATH.name}（总规则数 {len(doc['rules'])}）")
    else:
        # 打印前 5 条示例
        for r in rules[:5]:
            print(f"  {r['rule_id']}: {r['description'][:80]}")
        if len(rules) > 5:
            print(f"  ... 共 {len(rules)} 条")
        print("\n加 --write 写入文件")


if __name__ == "__main__":
    main()
