"""修复合并附注模板中 A 类缺陷表：row0 是子表头行但缺 multi_header。

规则（从已正确的 55 张 mh 表归纳）：
1. headers 作为 mh[0]（分组行）
2. row0 副本、首列置空 作为 mh[1]（子列标题行）
3. rows 中移除 row0
4. 从 mh[0] 推导 _column_groups：连续的非空→空 区间构成一个 group

识别条件（A 类）：
- section_id 以 五- 开头
- 无 multi_header
- headers 有空列名（empty > 0）
- rows[0][0] == headers[0]（row0 首列与 headers 首列相同 → row0 是子表头行）

Usage:
    python _fix_missing_multi_header.py --dry-run   # 只输出修复计划
    python _fix_missing_multi_header.py              # 执行修复并写回
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

FILES = [
    ROOT / "data/consol_note_sections_soe.json",
    ROOT / "data/consol_note_sections_listed.json",
]


def _build_mh_and_cg(headers: list[str], row0: list[str]) -> tuple[list[list[str]], list[dict]]:
    """从 headers（分组行）和 row0（子列标题行）推导正确的 multi_header 和 _column_groups。

    策略：
    1. 从 headers 提取分组标题和它们的原始位置
    2. row0 中非空子列的总数 ÷ 分组数 = 每组子列数（均分）
    3. 如果不能均分，用"按子列内容相似度分组"作为回退
    4. 生成 mh_row0（分组标题按正确 span 放置）+ mh_row1（row0 首列置空）
    """
    n = len(headers)

    # Step 1: 提取分组标题
    group_labels = []
    for i in range(1, n):
        s = str(headers[i]).strip()
        if s:
            group_labels.append(s)

    if not group_labels:
        # 无分组标题 → 全部子列属于一个隐含分组
        mh_row1 = list(row0)
        mh_row1[0] = ""
        return [list(headers), mh_row1], []

    # Step 2: 统计 row0 中非空子列
    sub_cols = []
    for i in range(1, len(row0)):
        v = str(row0[i]).strip()
        sub_cols.append((i, v))

    non_empty_count = sum(1 for _, v in sub_cols if v)

    # Step 3: 尝试均分
    num_groups = len(group_labels)
    cols_per_group = 0
    if non_empty_count > 0 and non_empty_count % num_groups == 0:
        cols_per_group = non_empty_count // num_groups
    else:
        # 不能均分 → 用每个子列段的长度来推断
        # 找连续非空子列段
        segs = []
        i = 1
        while i < len(row0):
            if str(row0[i]).strip():
                start = i
                while i < len(row0) and str(row0[i]).strip():
                    i += 1
                segs.append((start, i - start))
            else:
                i += 1

        if len(segs) == num_groups:
            # 刚好分段数等于分组数
            cols_per_group = -1  # 标记用分段长度
            mh_row0 = [""] * n
            mh_row0[0] = str(headers[0])
            groups = []
            for g_idx, (seg_start, seg_len) in enumerate(segs):
                label = group_labels[g_idx] if g_idx < len(group_labels) else ""
                mh_row0[seg_start] = label
                groups.append({"group": label, "start": seg_start, "span": seg_len})
            mh_row1 = list(row0)
            mh_row1[0] = ""
            return [mh_row0, mh_row1], groups
        elif len(segs) == 1 and num_groups >= 2:
            # 所有子列连在一起，用均分（向下取整+末尾分组取余）
            total = segs[0][1]
            cols_per_group = total // num_groups

    if cols_per_group <= 0:
        # 回退：简单均分
        usable = n - 1  # 去掉首列
        cols_per_group = max(1, usable // max(num_groups, 1))

    # Step 4: 生成 mh_row0
    mh_row0 = [""] * n
    mh_row0[0] = str(headers[0])
    groups = []
    pos = 1
    for g_idx, label in enumerate(group_labels):
        if g_idx == num_groups - 1:
            # 最后一个分组：如果 row0 末尾有空列，裁掉
            remaining = n - pos
            span = remaining
            # 裁剪尾部空列
            while span > 1 and not str(row0[pos + span - 1]).strip():
                span -= 1
        else:
            span = cols_per_group
        mh_row0[pos] = label
        groups.append({"group": label, "start": pos, "span": span})
        pos += span

    mh_row1 = list(row0)
    mh_row1[0] = ""

    return [mh_row0, mh_row1], groups


def fix_table(table: dict) -> dict | None:
    """对单张表执行修复，返回修复信息 dict；不符合条件返回 None。"""
    sid = table.get("section_id", "")
    if not sid.startswith("五-"):
        return None

    headers = table.get("headers", [])
    mh = table.get("multi_header")
    rows = table.get("rows", [])

    # 已有 mh → 跳过
    if mh:
        return None

    # 无空列名 → 跳过
    empty_count = sum(1 for h in headers if not str(h).strip())
    if empty_count == 0:
        return None

    # rows 为空 → 无法修复
    if not rows:
        return None

    # 检查 row0 是否是子表头行
    row0 = rows[0]
    if not isinstance(row0, list):
        return None

    # A 类条件：row0[0] == headers[0]（行标题列相同）
    h0 = str(headers[0]).strip() if headers else ""
    r0 = str(row0[0]).strip() if row0 else ""
    if not h0 or h0 != r0:
        return None

    # 列数必须一致
    if len(row0) != len(headers):
        return None

    # ===== 执行修复 =====

    new_mh, new_cg = _build_mh_and_cg(headers, row0)

    # 用平台标准函数重算 cg，确保与守卫测试一致
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from app.services.consol_note_formula_service import multi_header_to_column_groups
    canonical_cg = multi_header_to_column_groups(new_mh)
    if canonical_cg is not None:
        new_cg = canonical_cg

    # rows 移除首行
    new_rows = rows[1:]

    return {
        "section_id": sid,
        "title": table.get("title", ""),
        "col_count": len(headers),
        "empty_count": empty_count,
        "old_row_count": len(rows),
        "new_row_count": len(new_rows),
        "mh": new_mh,
        "cg": new_cg,
        "new_rows": new_rows,
    }


def main():
    dry_run = "--dry-run" in sys.argv

    for path in FILES:
        label = "国企" if "soe" in path.name else "上市"
        with open(path, encoding="utf-8") as f:
            tables = json.load(f)

        fixed_count = 0
        print(f"\n{'='*80}")
        print(f"📋 合并{label}: {path.name}")
        print(f"{'='*80}")

        for table in tables:
            result = fix_table(table)
            if result is None:
                continue

            fixed_count += 1
            sid = result["section_id"]
            print(f"  [{fixed_count:2d}] {sid:22s} {result['col_count']:2d}列"
                  f" 空{result['empty_count']}"
                  f" 行{result['old_row_count']}→{result['new_row_count']}"
                  f" cg={len(result['cg'])}组")

            if not dry_run:
                table["multi_header"] = result["mh"]
                table["_column_groups"] = result["cg"]
                table["rows"] = result["new_rows"]

        print(f"\n  合计: {fixed_count} 张表{'（dry-run 未写入）' if dry_run else '已修复'}")

        if not dry_run and fixed_count > 0:
            # 写回（保持格式）
            text = json.dumps(tables, ensure_ascii=False, indent=2)
            path.write_text(text, encoding="utf-8")
            print(f"  ✅ 已写回 {path.name}")


if __name__ == "__main__":
    main()
