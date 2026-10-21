"""从附注模板 JSON 生成子表级公式推送规则。

读取 note_template_{soe|listed}.json 的子表结构，为每张有 columns 的子表
生成一条推送规则（只生成，不写入 formula_push_rules.json——需人工审核后追加）。

用法：
    python scripts/gen/gen_subtable_push_rules.py [--write] [--wp-code D2]

不带 --write 则只打印到 stdout；--write 追加到 formula_push_rules.json。
--wp-code 可过滤只生成指定底稿的规则。

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
    """从子表的 columns 提取数值字段（排除 is_label）。"""
    cols = tbl.get("columns", [])
    fields = []
    for c in cols:
        if not isinstance(c, dict) or c.get("is_label"):
            continue
        key = c.get("key", "")
        if key and key in KNOWN_FIELDS:
            fields.append(key)
    return fields


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


def _load_existing_note_tables() -> set[tuple[str, str]]:
    """从现有规则中提取 (table, section_key) 对。

    section_key = 所有 section_by_template 值拼接（如 "五、42|八、42"），用于检测
    跨 wp_code 的同章节同表名冲突（如 K3 子表「应付利息」与 L2 主表撞同一章节）。
    """
    doc = json.loads(RULES_PATH.read_text("utf-8"))
    out: set[tuple[str, str]] = set()
    for r in doc.get("rules", []):
        if r.get("target", {}).get("domain") != "note":
            continue
        table = r.get("target", {}).get("table")
        sbt = r.get("target", {}).get("section_by_template", {})
        if table and sbt:
            sec_key = "|".join(sorted(sbt.values()))
            out.add((table, sec_key))
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

    for std in ("soe", "listed"):
        tpl_path = DATA / f"note_template_{std}.json"
        if not tpl_path.exists():
            continue
        tpl = json.loads(tpl_path.read_text("utf-8"))

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
                if rule_id in existing:
                    continue  # 已存在

                # section_by_template
                sbt: dict[str, str] = {}
                for v in ("listed", "soe"):
                    sec_v = registry.get(wp_code, {}).get(v)
                    if sec_v:
                        sbt[v] = sec_v

                if not sbt:
                    continue

                # 排除与现有规则同 (table, section) 的子表（已有规则覆盖）
                sec_key = "|".join(sorted(sbt.values()))
                if (tname, sec_key) in existing_tables:
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
