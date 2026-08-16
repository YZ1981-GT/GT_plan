"""fix_l0a_program_template.py — 往 `tables` 增补 `L0A` 条目（幂等）.

spec: l0-confirmation-source-alignment
  Requirements 1.1 / 1.3 / 1.4 / 1.5 / 1.6 / 1.7 / 1.8 / 1.9
  Property 1 / 3 / 4

## 问题

`get_template('L0A')` 返回 **None** —— `L0A` 只存在于 `procedure_table_templates.json`
的**根级**（10 items，名「筹资循环函证实质性程序表」，内容为自造非源模板忠实版），
而 `get_template` 只读 `tables`。

后果链：L0 的程序表 sheet 名是 `函证程序表F0A`（源模板索引号笔误）→
`resolve_program_template_code('函证程序表F0A', 'L0')` 提取到 `F0A`，发现循环前缀
不同后尝试 `L0A`，但 `get_template('L0A')` 为 None → **回退 `F0A`** →
L0 程序表实际加载「采购存货循环函证程序表」12 条，`ref_index` 全为 `F0-1`/`F0-2`。

## 处置

按源模板 `函证程序表F0A!A7:G18` 重建 12 items 写入 `tables.L0A`。

🔴 **加法式**：只增 `tables.L0A`，不动 `tables` 内既有 121 条中任何一条；
根级既有 `L0A` 保持不动（那 57 条与 `tables` 分叉的重复条目属平台级议题，
需另立 spec 收敛，本脚本不碰）。

🔴 **字段名以 `tables` 既有形态为准**（实证 `tables.F0A`）：
`content` 是 `ProcedureTableService` 的**必填**读取（`item["content"]` 而非 `.get`），
写成 `description` 会 KeyError；`program_category` 走
`item.get("category") or item.get("program_category")`。

🔴 **源模板 G 列批注承载在 `content` 末尾的 `\\n【提示】…`** —— item 输出字段恒为
`{_key, seq, content, ref_index, phase, category, **merged}`，**没有 `hint` 透传通道**，
新增字段会被静默丢弃。

用法::

    python backend/scripts/fix/fix_l0a_program_template.py --check
    python backend/scripts/fix/fix_l0a_program_template.py --dry-run
    python backend/scripts/fix/fix_l0a_program_template.py --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATES_JSON = _REPO_ROOT / "backend" / "data" / "procedure_table_templates.json"

WP_CODE = "L0A"
TABLE_NAME = "长期应付款/应付债券函证程序"  # 源 A2 逐字
AUTO_SOURCE = "confirmation_summary_for_cycle"

#: 源模板 `函证程序表F0A!A7:G18` 逐字。
#: (seq, B列程序描述, D列程序分类, E列底稿索引号, G列批注)
SOURCE_ITEMS: list[tuple[int, str, str, str | None, str | None]] = [
    (
        1,
        "以积极方式对长期应付款、应付债券进行函证。",
        "常规★",
        "L0-1",
        "本函证不包含银行长期借款、银行短期借款函证，与银行借款相关函证详见货币资金循环",
    ),
    (
        2,
        "比较当年度及以前年度长期应付款、应付债券的增减变动、具体构成、账龄及主要供货商的变化，"
        "针对舞弊风险较大的债权人，考虑对合同条款、是否存在关联方关系及是否存在补充协议实施函证程序。",
        "舞弊应对/IPO/上市/新三板/重组",
        "L0-1",
        None,
    ),
    (
        3,
        "设计询证函，考虑制作询证函防伪标识，并在发函前核实被函证单位信息"
        "（函证科目、单位名称、地址、联系人、联系电话、邮政编码、函证人等），"
        "对于函证地址与注册地址、办公地址等不一致，不同客户或供应商的函证地址相近、电话号段相邻，"
        "函证联系人非被询证单位员工等情况，需核查并记录原因。",
        "常规★",
        "L0-2",
        None,
    ),
    (
        4,
        "注册会计师直接收发询证函，跟函时观察实地场所以及函证核对过程，"
        "确认处理函证的人员身份和权限，防范询证函被拦截、篡改或发生串通舞弊，"
        "并在底稿中记录或留存控制过程；",
        "常规★",
        "L0-1/L0-3",
        None,
    ),
    (
        5,
        "留存亲自寄发函证的寄送单回执及被审计单位盖章确认的询证函复印件，核实发函快递物流信息；",
        "常规★",
        "L0-1/L0-2",
        None,
    ),
    (
        6,
        "收到的回函应为被询证者书面答复，可以采取纸质、电子或其它介质等形式：\n"
        "（1）确认与发出的询证函是否为同一份、是否为原件；\n"
        "（2）检查回函发出地址、快递物流信息，核实回函地址是否与发函收件地址一致，"
        "比对回函印章和签字，确认回函的真实性；\n"
        "（3）检查函证信息是否相符，对回函不符的询证函，查明不符事项的原因确定是否存在错报，"
        "考虑是否存在舞弊的可能性；",
        "常规★",
        "L0-1/L0-2/L0-4",
        None,
    ),
    (
        7,
        "如果被询证者以传真、电子邮件等方式回函，审计项目组应当直接接收，"
        "并验证传真、电邮邮件回函的可靠性，要求被询证者在审计报告日之前寄回询证函原件",
        "备选",
        "L0-1/L0-6",
        None,
    ),
    (
        8,
        "如果利用第三方函证平台收发函证的，考虑评估第三方函证平台服务的可靠性，"
        "了解资质认证或有关控制设计及运行的有效性。",
        "备选",
        None,
        "第三方电子询证函平台的安全性评估内容相关要点详见函证技术提示3号，"
        "链接为：https://www.gt-china.com.cn/article_view.php?id=9682；",
    ),
    (
        9,
        "分析核实退回或无法寄到的函证、未回函、回函率较低的原因，考虑与被询证者联系，"
        "要求对方作出回应或再次寄发询证函，必要时增加现场走访等程序，"
        "关注是否存在账面记录与外部证据矛盾的审计证据；",
        "常规★",
        "L0-1/L0-2",
        None,
    ),
    (
        10,
        "针对再次发函未回函的项目，评价其重大错报风险以及其他审计程序的性质、"
        "时间安排和范围的影响实施替代审计程序，包括：\n"
        "（1）检查交易发生的记账凭证和相关的支持性证据； \n"
        "（2）检查资产负债表日后到付款情况或其他情况",
        "常规★",
        "L0-1/L0-5",
        None,
    ),
    (
        11,
        "结合风险评估情况及函证程序执行过程中的舞弊风险迹象，考虑串通舞弊、伪造交易的可能性等，"
        "对函证程序的舞弊风险进行评价；",
        "常规★",
        "L0-7",
        None,
    ),
    (
        12,
        "如果管理层不允许寄发询证函的原因不合理、或者认为回函不可靠，列出供应商清单，"
        "实施替代审计程序，并评价对评估的重大错报风险以及其他审计程序的性质、"
        "时间安排和范围的影响，考虑其对审计工作和审计意见的影响；",
        "常规★",
        None,
        None,
    ),
]

HINT_PREFIX = "\n【提示】"


def build_l0a_entry() -> dict:
    """按源模板构造 `tables.L0A` 条目。"""
    items = []
    for seq, desc, category, ref, hint in SOURCE_ITEMS:
        content = desc + (HINT_PREFIX + hint if hint else "")
        items.append({
            "seq": seq,
            "content": content,
            "ref_index": ref,
            "auto_data_source": AUTO_SOURCE if ref else None,
            "applicable_default": "yes",
            "program_category": category,
        })
    return {"name": TABLE_NAME, "items": items}


def diff_entry(existing: dict | None, expected: dict) -> list[str]:
    """返回欠账清单（空 = 已对齐）。"""
    gaps: list[str] = []
    if existing is None:
        gaps.append(f"tables.{WP_CODE} 缺失（get_template 会返回 None → 回退 F0A）")
        return gaps
    if existing.get("name") != expected["name"]:
        gaps.append(f"tables.{WP_CODE}.name = {existing.get('name')!r}，应为 {expected['name']!r}")
    got = existing.get("items") or []
    exp = expected["items"]
    if len(got) != len(exp):
        gaps.append(f"tables.{WP_CODE}.items 有 {len(got)} 条，应为 {len(exp)} 条")
        return gaps
    for g, e in zip(got, exp):
        for field in ("seq", "content", "ref_index", "program_category", "applicable_default"):
            if g.get(field) != e.get(field):
                gaps.append(
                    f"tables.{WP_CODE}.items[seq={e['seq']}].{field} 不符："
                    f"{str(g.get(field))[:40]!r} → {str(e.get(field))[:40]!r}"
                )
    return gaps


#: 该文件的实际序列化格式（实证：indent=2 / ensure_ascii=False / **无**末尾换行）
_DUMP_KW = {"ensure_ascii": False, "indent": 2}
_TRAILING_NEWLINE = ""


def _dump(data: dict) -> str:
    return json.dumps(data, **_DUMP_KW) + _TRAILING_NEWLINE


def _round_trip_ok(raw: str, data: dict) -> bool:
    """round-trip 自检：序列化能否逐字复现原文（防全文件重排与并发冲突）。"""
    return _dump(data) == raw


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="只报欠账，有欠账则非零退出")
    g.add_argument("--dry-run", action="store_true", help="打印将写入的内容，不落盘")
    g.add_argument("--apply", action="store_true", help="写盘")
    args = ap.parse_args()

    raw = TEMPLATES_JSON.read_text(encoding="utf-8")
    data = json.loads(raw)
    tables = data.get("tables")
    if not isinstance(tables, dict):
        print("[ERR] procedure_table_templates.json 缺少 tables 顶层键", file=sys.stderr)
        return 2

    expected = build_l0a_entry()
    gaps = diff_entry(tables.get(WP_CODE), expected)

    if args.check:
        if gaps:
            print(f"欠账 {len(gaps)} 项：")
            for gap in gaps:
                print("  -", gap)
            return 1
        print(f"[OK] tables.{WP_CODE} 已对齐源模板（0 项欠账）")
        return 0

    if not gaps:
        print(f"[OK] 已对齐，无需改动（tables.{WP_CODE} 12 items）")
        return 0

    if not _round_trip_ok(raw, data):
        print(
            "[ERR] round-trip 自检失败：json.dumps 无法逐字复现原文。\n"
            "   直接写盘会重排整个文件（并发会话冲突风险），已中止。",
            file=sys.stderr,
        )
        return 2

    tables_before = {k: json.dumps(v, ensure_ascii=False, sort_keys=True) for k, v in tables.items()}
    tables[WP_CODE] = expected

    # 加法式校验：既有条目一个都不能变
    for k, before in tables_before.items():
        if k == WP_CODE:
            continue
        after = json.dumps(tables[k], ensure_ascii=False, sort_keys=True)
        if before != after:
            print(f"[ERR] 加法式约束被破坏：tables.{k} 发生变化，已中止", file=sys.stderr)
            return 2

    out = _dump(data)

    if args.dry_run:
        print(f"[dry-run] 将写入 tables.{WP_CODE}（{len(expected['items'])} items）：")
        print(json.dumps(expected, ensure_ascii=False, indent=1)[:1200])
        print(f"\n[dry-run] 欠账 {len(gaps)} 项将被修复：")
        for gap in gaps:
            print("  -", gap)
        return 0

    if args.apply:
        TEMPLATES_JSON.write_text(out, encoding="utf-8")
        print(f"[OK] 已写入 tables.{WP_CODE}（{len(expected['items'])} items），修复 {len(gaps)} 项欠账")
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
