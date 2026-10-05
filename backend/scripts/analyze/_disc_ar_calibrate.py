"""AR 四组 binding 校准脚本。

逐组对照模板补齐缺失表、修正国企错位、对齐行标签全角空格。
支持 --check（只检查不写入）和 --write（写入）。

Spec: disclosure-multitable-refresh-and-edit-writeback Task 3 (R2)
"""
from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BINDINGS_PATH = ROOT / "backend/data/note_template_bindings.json"

# AR 四组目标章节
AR_SECTIONS = ("八、5", "十二、应收账款", "五、5", "十六、应收账款")

# 国企模板尾部 2 张表（index 11, 12）在 binding 中缺失
SOE_TAIL_TABLES = [
    {
        "table_index": 11,
        "table_name": "（6）由金融资产转移而终止确认的应收账款",
        "header_normalize": [
            {"text": "债务人名称", "semantic": "row_label"},
            {"text": "终止确认金额", "semantic": "derecognition_amount"},
            {"text": '与终止确认相关的利得或损失（损失以"-"填列）', "semantic": "gain_or_loss"},
        ],
        "rows": {
            "合计": {"row_type": "total"},
        },
    },
    {
        "table_index": 12,
        "table_name": "（7）应收账款转移继续涉入形成的资产、负债的金额",
        "header_normalize": [
            {"text": "项目", "semantic": "row_label"},
            {"text": "期末金额", "semantic": "closing_amount"},
        ],
        "rows": {
            "资产小计": {"row_type": "total"},
            "负债小计": {"row_type": "total"},
        },
    },
]

# 上市模板尾部 2 张表（index 15, 16）在 binding 中缺失
LISTED_TAIL_TABLES = [
    {
        "table_index": 15,
        "table_name": "因金融资产转移而终止确认的应收账款情况",
        "header_normalize": [
            {"text": "项目", "semantic": "row_label"},
            {"text": "转移方式", "semantic": "transfer_method"},
            {"text": "终止确认金额", "semantic": "derecognition_amount"},
            {"text": "与终止确认相关的利得或损失", "semantic": "gain_or_loss"},
        ],
        "rows": {
            "合计": {"row_type": "total"},
        },
    },
    {
        "table_index": 16,
        "table_name": "转移应收账款且继续涉入形成的资产、负债的金额",
        "header_normalize": [
            {"text": "项目", "semantic": "row_label"},
            {"text": "资产转移方式", "semantic": "transfer_method"},
            {"text": "继续涉入形成的资产金额", "semantic": "continued_asset"},
            {"text": "继续涉入形成的负债金额", "semantic": "continued_liability"},
        ],
        "rows": {
            "合计": {"row_type": "total"},
        },
    },
]


def _normalize_label(label: str) -> str:
    """全角空格归一化为半角空格后 strip。"""
    return label.replace("\u3000", " ").replace("  ", " ").strip()


def calibrate_binding(data: dict) -> tuple[dict, list[str]]:
    """校准 AR 四组 binding，返回 (新 data, 变更日志)。"""
    data = deepcopy(data)
    bindings = data.get("bindings", {})
    log: list[str] = []

    # 加载模板用于 table_name 同步
    tmpl_tables_map: dict[str, list[dict]] = {}
    for fname in ("note_template_soe.json", "note_template_listed.json"):
        fp = ROOT / "backend/data" / fname
        if fp.exists():
            tdata = json.loads(fp.read_text("utf-8"))
            for sec in tdata.get("sections", []):
                sn = sec.get("section_number", "") or sec.get("note_section", "")
                if sn in AR_SECTIONS:
                    tmpl_tables_map[sn] = sec.get("tables", [])

    for sec_name in AR_SECTIONS:
        if sec_name not in bindings:
            log.append(f"⚠️ {sec_name}: 不在 bindings 中，跳过")
            continue

        sec = bindings[sec_name]
        tables = sec.get("tables", [])
        is_soe = sec_name.startswith("八") or sec_name.startswith("十二")
        is_listed = sec_name.startswith("五") or sec_name.startswith("十六")

        old_count = len(tables)

        if is_soe:
            # 国企：模板 13 表，binding 原始 11 表
            # 缺失：[2] 期初分类续表 + [12] 继续涉入
            # 策略：在 index=2 插入续表 + 尾部补齐到 13
            existing_names = {t.get("table_name", "") for t in tables}
            
            # 1. 在 index=2 插入期初分类续表（国企特有）
            needs_insert = (
                len(tables) >= 3
                and "续" not in tables[2].get("table_name", "")
                and "期初" not in tables[2].get("table_name", "")
            )
            if needs_insert:
                cont_table = {
                    "table_index": 2,
                    "table_name": "（2）按坏账准备计提方法分类披露应收账款（续：期初数）",
                    "header_normalize": [
                        {"text": "类别", "semantic": "row_label"},
                        {"text": "期初数", "semantic": "opening_balance"},
                    ],
                    "rows": {
                        "合计": {"row_type": "total"},
                    },
                }
                tables.insert(2, cont_table)
                log.append(f"✅ {sec_name}: 在 index=2 插入期初分类续表")

            # 2. 尾部补齐到模板表数（13）
            target_count = 13
            while len(tables) < target_count:
                tail_idx = len(tables)
                # 按模板 index 对应的尾部表名
                tail_defs = {
                    11: SOE_TAIL_TABLES[0],  # （6）终止确认
                    12: SOE_TAIL_TABLES[1],  # （7）继续涉入
                }
                if tail_idx in tail_defs:
                    t = deepcopy(tail_defs[tail_idx])
                    t["table_index"] = tail_idx
                    tables.append(t)
                    log.append(f"✅ {sec_name}: 补 [{tail_idx}] {t['table_name']}")
                else:
                    break  # 安全退出

            if len(tables) != old_count:
                log.append(f"  {sec_name}: {old_count} → {len(tables)} 表")

        elif is_listed:
            # 上市：模板 17 表，补尾部 2 张（已有则跳过）
            existing_names = {t.get("table_name", "") for t in tables}
            tail_tables = deepcopy(LISTED_TAIL_TABLES)
            added = 0
            for t in tail_tables:
                if t["table_name"] not in existing_names:
                    t["table_index"] = len(tables)
                    tables.append(t)
                    added += 1
            if added:
                log.append(f"✅ {sec_name}: 补 {added} 张尾部表 ({old_count} → {len(tables)})")

        # 修正所有表的 table_index 使之连续
        for i, t in enumerate(tables):
            if t.get("table_index") != i:
                log.append(f"  [{sec_name}] table_index {t.get('table_index')} → {i}")
                t["table_index"] = i

        # 行标签归一化（全角空格 → 半角）
        for t in tables:
            rows = t.get("rows", {})
            if isinstance(rows, dict):
                new_rows: dict = {}
                for label, val in rows.items():
                    norm = _normalize_label(label)
                    if norm != label:
                        log.append(f"  [{sec_name}] 行标签归一: {label!r} → {norm!r}")
                    new_rows[norm] = val
                t["rows"] = new_rows

        # table_name 同步：以模板 name 为准（不影响按 index 匹配，只改日志可读性）
        tmpl_tables = tmpl_tables_map.get(sec_name, [])
        for i, t in enumerate(tables):
            if i < len(tmpl_tables):
                tmpl_name = tmpl_tables[i].get("name", "")
                cur_name = t.get("table_name", "")
                if tmpl_name and cur_name != tmpl_name:
                    t["table_name"] = tmpl_name
                    log.append(f"  [{sec_name}][{i}] table_name 同步: {cur_name!r} → {tmpl_name!r}")

        # header_normalize.text 全角空格归一化
        for t in tables:
            hn = t.get("header_normalize", [])
            for h in hn:
                if isinstance(h, dict) and "text" in h:
                    norm = _normalize_label(h["text"])
                    if norm != h["text"]:
                        log.append(f"  [{sec_name}] header text 归一: {h['text']!r} → {norm!r}")
                        h["text"] = norm

        sec["tables"] = tables

    return data, log


def main():
    parser = argparse.ArgumentParser(description="AR 四组 binding 校准")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="只检查，不写入")
    group.add_argument("--write", action="store_true", help="写入校准后的文件")
    args = parser.parse_args()

    data = json.loads(BINDINGS_PATH.read_text("utf-8"))
    new_data, log = calibrate_binding(data)

    for line in log:
        print(line)

    if args.check:
        # 再次校准看是否幂等
        new_data2, log2 = calibrate_binding(new_data)
        # 幂等 = 第二次校准不产生任何"补表"或"归一"日志（只有 table_index 微调）
        meaningful_changes = [l for l in log2 if "补" in l or "归一" in l]
        if meaningful_changes:
            print("\n❌ 非幂等：重复校准仍有变更")
            for line in meaningful_changes:
                print(f"  {line}")
            sys.exit(1)
        else:
            print("\n✅ 幂等检查通过")
            # 比较 JSON 是否有 diff
            old_text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
            new_text = json.dumps(new_data, ensure_ascii=False, indent=2, sort_keys=True)
            if old_text == new_text:
                print("无 diff（已校准）")
            else:
                print(f"有 diff（需要 --write）")
                sys.exit(2)
    elif args.write:
        BINDINGS_PATH.write_text(
            json.dumps(new_data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"\n✅ 已写入 {BINDINGS_PATH}")


if __name__ == "__main__":
    main()
