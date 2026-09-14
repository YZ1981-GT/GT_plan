#!/usr/bin/env python
"""生成附注「多段共享表」清单 → `backend/data/note_shared_table_segments.json`。

**用途**：清单只供**守卫与前端**消费（前端据此判定「推这张表必须带 `_row_scope`」）。
🔴 **服务端运行期直接读模板**，不读本清单 —— 清单陈旧会让 fail closed 误判，
把正常同步挡掉。

**判据**：同一张表的 `rows[]` 中出现 ≥2 个不同的 `report_row_code`
（段首行标记，模板里本就存在）。

用法：
    python backend/scripts/gen/gen_note_shared_table_segments.py --check   # drift 检查
    python backend/scripts/gen/gen_note_shared_table_segments.py --write   # 重新生成

spec: .kiro/specs/disclosure-note-row-level-merge/ Requirements 8.1, 8.4 / Property 14
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.services.note_shared_table_segments import (  # noqa: E402
    VARIANTS,
    iter_shared_tables,
)

OUT_PATH = _ROOT / "data" / "note_shared_table_segments.json"

#: 实测基线（Property 14）：变了就要在此同步更新并说明原因
#:
#: 2026-08-12 由 23/6 调为 24/8（+3 张表），原因 = K 循环补齐共享表段首码
#: （`fix_note_k_report_row_codes.py`，spec `k-cycle-extraction-formula-and-disclosure-closure`
#: Task 14）。此前这 3 张表的 `report_row_code` 全缺 ⇒ 段数 0 ⇒ owner 推送
#: `_row_scope` 时 `find_segment` 返 None ⇒ **整表 fail-closed 跳过写入**。补码后：
#:   - listed `五、42 其他应付款`：应付股利 BS-055(M1) + 其他应付款 BS-050(K3)
#:   - soe    `八、42 其他应付款`：应付股利 BS-076(M1) + 其他应付款项 BS-050(K3)
#:   - soe    `八、9  其他应收款`：应收股利 BS-016(G3) + 其他应收款项 BS-009(K1)
#: listed `五、8 其他应收款` **有意只有 1 个段首码**（其他应收款 BS-009）——
#: 应收利息/应收股利在 listed 侧 `report_config` 零命中，宁缺勿造，故它不计入共享表。
EXPECTED_COUNTS = {"listed": 24, "soe": 8}


def build_payload() -> dict:
    """构造清单（**不含时间戳** —— 否则每次生成都 drift）。"""
    tables: list[dict] = []
    for variant in VARIANTS:
        for section_number, section_title, table_name, rows, segs in iter_shared_tables(variant):
            tables.append(
                {
                    "variant": variant,
                    "section_number": section_number,
                    "section_title": section_title,
                    "table_name": table_name,
                    "row_count": len(rows),
                    "segments": [
                        {
                            "row_code": s.row_code,
                            "label": s.label,
                            "start": s.start,
                            # `end` = 到下一个段首前；`data_end` = 可写区右界
                            # （排除段尾的表级汇总行 —— 合计/小计不属于任何 owner）。
                            # 行级合并替换 [start, data_end)，故 end != data_end 的段
                            # 就是「尾部挂着合计行」的段（实测 13 个）。
                            "end": s.end,
                            "data_end": s.data_end,
                        }
                        for s in segs
                    ],
                }
            )
    return {
        "_source": "note_template_listed.json + note_template_soe.json",
        "_generator": "backend/scripts/gen/gen_note_shared_table_segments.py",
        "_criterion": "同一张表的 rows[] 中出现 >=2 个不同的 report_row_code",
        "_note": (
            "本清单只供守卫与前端消费；服务端运行期直接读模板，"
            "不读本清单（清单陈旧会让 fail closed 误判）。"
        ),
        "counts": {v: sum(1 for t in tables if t["variant"] == v) for v in VARIANTS},
        "tables": tables,
    }


def dump(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def _utf8_stdout() -> None:
    """把 stdout/stderr 钉成 UTF-8。

    🔴 2026-08-12 实测：本脚本成功分支打印 `✓`（U+2713），Windows GBK 控制台下
    `--check` 会以 ``UnicodeEncodeError`` 崩掉、退出码非 0 ⇒ 从命令行看「清单明明
    是最新的却报失败」。既有守卫 `test_check_passes` 是**进程内**调 `main()`
    （monkeypatch argv），pytest 捕获的 stdout 不是 GBK 控制台，故一直没暴露 ——
    典型的「守卫覆盖了逻辑但没覆盖调用形态」。在脚本内自愈，三条调用路径
    （CI / 人工命令行 / 守卫）都受益。
    """
    for s in (sys.stdout, sys.stderr):
        rc = getattr(s, "reconfigure", None)
        if rc is None:
            continue
        try:
            rc(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def main() -> int:
    _utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="写入清单")
    ap.add_argument("--check", action="store_true", help="drift 检查（默认）")
    args = ap.parse_args()

    payload = build_payload()
    text = dump(payload)
    counts = payload["counts"]

    problems: list[str] = []
    for variant, expected in EXPECTED_COUNTS.items():
        actual = counts.get(variant, 0)
        if actual != expected:
            problems.append(
                f"{variant} 共享表数 {actual} != 基线 {expected} "
                f"—— 模板结构变了？请核实后更新 EXPECTED_COUNTS 并说明原因"
            )

    if args.write:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(text, encoding="utf-8")
        print(f"已写入 {OUT_PATH.relative_to(_ROOT.parent)}")
        print(f"  共享表：{counts}（合计 {sum(counts.values())} 张）")
        for p in problems:
            print(f"  ⚠ {p}")
        return 1 if problems else 0

    # --check（默认）
    if not OUT_PATH.exists():
        print(f"✗ 清单不存在：{OUT_PATH}；请先 --write")
        return 1
    current = OUT_PATH.read_text(encoding="utf-8")
    if current != text:
        problems.append("清单与模板不一致（drift）—— 请重跑 --write")
        # 给出可读的差异摘要（不打印整份 JSON）
        try:
            old = json.loads(current)
        except ValueError:
            problems.append("现有清单不是合法 JSON")
        else:
            old_keys = {
                (t["variant"], t["section_number"], t["table_name"])
                for t in old.get("tables") or []
            }
            new_keys = {
                (t["variant"], t["section_number"], t["table_name"])
                for t in payload["tables"]
            }
            for k in sorted(new_keys - old_keys):
                problems.append(f"  + 新增：{k}")
            for k in sorted(old_keys - new_keys):
                problems.append(f"  - 消失：{k}")
            if old_keys == new_keys:
                problems.append("  表集合相同 → 差异在段区间 / 行数 / 标题")

    if problems:
        print("✗ 共享表清单检查未通过：")
        for p in problems:
            print(f"  {p}")
        return 1
    print(f"✓ 共享表清单与模板一致：{counts}（合计 {sum(counts.values())} 张）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
