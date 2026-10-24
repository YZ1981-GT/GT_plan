#!/usr/bin/env python
"""由 ``backend/data/wp_account_mapping.json`` 生成前端挂凭推荐表 ``views/ledger/accountToWpMapping.ts``。

取数：D~N 循环各底稿主条目（编码形如 ``D2`` / ``G14``）的 ``account_codes``，一码一行；函证底稿（``D0`` / ``E0`` …）
不列（挂凭推荐的是实质性底稿）；科目为空的主条目（没有标准科目，如 D5 / K4 / L7 / M8）不列。
底稿名取主条目的 ``account_name``。输出幂等（无时间戳），``--check`` 漂移 exit 2。

原文件头注释指向的 ``scripts/analyze/gen_account_to_wp_ts.py`` 从未存在，表是手写的，与映射表脱节
（D5 写 1124、M 循环整体错一格、H8 写 1901 等）。spec: .kiro/specs/formula-fetch-followup-defect-closure/ R1.5

用法（cwd 任意）::

    python backend/scripts/gen/gen_account_to_wp_ts.py --check
    python backend/scripts/gen/gen_account_to_wp_ts.py --write
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MAPPING_PATH = ROOT / "backend" / "data" / "wp_account_mapping.json"
OUTPUT_PATH = ROOT / "audit-platform" / "frontend" / "src" / "views" / "ledger" / "accountToWpMapping.ts"

_MAIN_RE = re.compile(r"^([D-N])(\d+)$")
CYCLE_LABELS = {
    "D": "销售循环", "E": "货币资金", "F": "存货与采购", "G": "投资", "H": "固定资产", "I": "无形资产",
    "J": "薪酬", "K": "管理", "L": "筹资", "M": "权益", "N": "税费",
}

_HEADER = """/**
 * accountToWpMapping.ts — 科目编码前缀 → 底稿推荐映射（由 wp_account_mapping.json 生成）
 *
 * 用途：挂凭弹窗根据凭证涉及的科目自动推荐相关底稿。
 * 来源：backend/data/wp_account_mapping.json 中 D~N 循环各底稿主条目的 account_codes（{n_wp} 张底稿、{n_rows} 行）；
 *       函证底稿（D0 / E0 …）与没有标准科目的底稿不列。
 * 维护：映射表更新后运行 `python backend/scripts/gen/gen_account_to_wp_ts.py --write` 重新生成，`--check` 校验一致。
 *
 * 🔴 本文件由脚本生成，禁止手工编辑。
 */

export interface AccountWpMapping {
  /** 四位科目编码前缀（如 '1001'、'1601'） */
  prefix: string
  /** 底稿编码（如 'E1'、'H1'） */
  wpCode: string
  /** 底稿名称 */
  wpName: string
  /** 审计循环 */
  cycle: string
}

/**
 * 科目前缀 → 底稿映射表。同一前缀可对应多张底稿（调用方按 startsWith 匹配，见 findWpCodesByAccountCode）。
 */
export const ACCOUNT_WP_MAPPINGS: AccountWpMapping[] = [
"""

_FOOTER = """]

// 按前缀长度降序排列，匹配时优先匹配最长前缀
const SORTED_MAPPINGS = [...ACCOUNT_WP_MAPPINGS].sort(
  (a, b) => b.prefix.length - a.prefix.length || a.prefix.localeCompare(b.prefix),
)

/**
 * 根据科目编码查找推荐底稿编码（可能多个）。
 *
 * @param accountCode 四位或更长的科目编码（如 '1002.01'）
 * @returns 匹配到的 wp_code 数组（去重），空数组表示无映射
 */
export function findWpCodesByAccountCode(accountCode: string): string[] {
  const code = accountCode.trim()
  if (!code) return []
  const matched = new Set<string>()
  for (const m of SORTED_MAPPINGS) {
    if (code.startsWith(m.prefix)) {
      matched.add(m.wpCode)
    }
  }
  return [...matched]
}

/**
 * 批量推荐：给定多个科目编码，返回所有推荐底稿编码（去重）。
 *
 * 适用于多对多凭证场景：一张凭证借贷两侧涉及多个科目，
 * 每个科目可能映射到不同的底稿。
 */
export function findAllRecommendedWpCodes(accountCodes: string[]): string[] {
  const result = new Set<string>()
  for (const code of accountCodes) {
    for (const wp of findWpCodesByAccountCode(code)) {
      result.add(wp)
    }
  }
  return [...result]
}
"""


def _ts_str(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def main_entries(mappings: list[dict]) -> list[dict]:
    """D~N 主条目（非函证、有科目），按循环字母、底稿序号排序。"""
    picked = []
    for e in mappings:
        m = _MAIN_RE.match(str(e.get("wp_code") or ""))
        if not m or m.group(2) == "0" or not e.get("account_codes"):
            continue
        picked.append((m.group(1), int(m.group(2)), e))
    return [e for _c, _n, e in sorted(picked, key=lambda t: (t[0], t[1]))]


def render(mappings: list[dict]) -> str:
    entries = main_entries(mappings)
    lines: list[str] = []
    cycle = None
    n_rows = 0
    for e in entries:
        wp = e["wp_code"]
        if wp[0] != cycle:
            cycle = wp[0]
            lines.append(f"  // {cycle} {CYCLE_LABELS[cycle]}")
        name = e.get("account_name") or e.get("wp_name") or wp
        for code in e["account_codes"]:
            lines.append(
                f"  {{ prefix: {_ts_str(code)}, wpCode: {_ts_str(wp)}, wpName: {_ts_str(name)}, cycle: {_ts_str(cycle)} }},"
            )
            n_rows += 1
    header = _HEADER.replace("{n_wp}", str(len(entries))).replace("{n_rows}", str(n_rows))
    return header + "\n".join(lines) + "\n" + _FOOTER


def _load() -> list[dict]:
    return json.loads(MAPPING_PATH.read_text(encoding="utf-8"))["mappings"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="与现有文件比对，漂移 exit 2")
    g.add_argument("--write", action="store_true", help="写回文件（保持原文件换行风格）")
    args = ap.parse_args(argv)

    content = render(_load())
    existing = OUTPUT_PATH.read_bytes().decode("utf-8") if OUTPUT_PATH.exists() else ""
    if args.check:
        if existing.replace("\r\n", "\n") == content:
            print(f"accountToWpMapping.ts 与映射表一致（{content.count('{ prefix: ')} 行）")
            return 0
        print("accountToWpMapping.ts 与映射表不一致：运行 --write 重新生成", file=sys.stderr)
        return 2
    newline = "\r\n" if "\r\n" in existing else "\n"
    OUTPUT_PATH.write_bytes(content.replace("\n", newline).encode("utf-8"))
    print(f"已生成 {OUTPUT_PATH}（{content.count('{ prefix: ')} 行）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
