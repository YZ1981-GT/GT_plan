#!/usr/bin/env python
"""披露表 _columns 覆盖守卫（disclosure-table-sync-convergence Task 13）

扫描前端全部 `disclosure-notes/sync-from-workpaper` / `sync-batch-from-workpaper`
调用点，核对其推送载荷是否携带 `columns` 列头元数据（供附注模块投影渲染源模板表样）。

- 已覆盖：文件含 `columns:` 载荷字段，或引用已知会附带 columns 的构造器
  （buildF2SyncPayload / buildSyncColumns / build*Columns）。
- 未覆盖且不在 allowlist → --strict 退出非 0（Req5.2）。
- allowlist 显式豁免须注明原因（Req5.3）；本规格分波推进，Wave4/5 未迁移组件
  在此登记，使剩余工作可见而不阻断 CI。

用法:
    python backend/scripts/check/check_disclosure_columns_coverage.py [--strict]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# 仓库根：本文件位于 backend/scripts/check/
ROOT = Path(__file__).resolve().parents[3]
FRONTEND_SRC = ROOT / "audit-platform" / "frontend" / "src"

# 用完整 URL 路径作标记，排除仅在文档注释里提及 "sync-from-workpaper" 的非调用点
SYNC_MARKERS = (
    "disclosure-notes/sync-from-workpaper",
    "disclosure-notes/sync-batch-from-workpaper",
)

# 已验证会在载荷中附带 columns 的构造器（引用即视为覆盖）。
# 仅登记确认过其实现会输出 columns 的构造器，避免假阳性；随迁移进度扩充。
COLUMN_BUILDERS = (
    "buildF2SyncPayload",          # F2 存货（listed+soe）
    "buildSyncColumns",            # GtCNoteTable schema 派生
    "buildF3SyncPayload",          # F3 应付票据（listed+soe）
    "buildH9ListedSyncPayloads",   # H9 租赁负债 listed
    "buildH9SoeSyncPayloads",      # H9 租赁负债 soe
    "buildH10SyncPayloads",        # H10 资产处置收益（listed+soe）
    "buildG14SyncPayloads",        # G14 信用减值损失（listed+soe）
    "buildG13SyncPayloads",        # G13 公允价值变动收益（listed+soe）
    "buildG2SoeSyncPayloads",      # G2 应收利息 soe
    "buildG2ListedSyncPayloads",   # G2 应收利息 listed
    "buildG3SoeSyncPayloads",      # G3 应收股利 soe
    "buildG3ListedSyncPayloads",   # G3 应收股利 listed
    "buildG10ListedSyncPayloads",  # G10 交易性金融负债 listed
    "buildG10SoeSyncPayloads",     # G10 交易性金融负债 soe
    "buildG11ListedSyncPayloads",  # G11 投资收益 listed
    "buildG11SoeSyncPayloads",     # G11 投资收益 soe
    "buildG11SyncPayloads",        # G11 投资收益 分发器
    "buildK1ListedSyncPayloads",   # K1 其他应收款 listed
    "buildK1SoeSyncPayloads",      # K1 其他应收款 soe
    "buildI4ListedSyncPayloads",   # I4 长期待摊费用 listed
    "buildI4SoeSyncPayloads",      # I4 长期待摊费用 soe
    "buildI5ListedSyncPayloads",   # I5 递延所得税资产 listed
    "buildI5SoeSyncPayloads",      # I5 递延所得税资产 soe
    "buildI6ListedSyncPayloads",   # I6 研发费用 listed
    "buildI6SoeSyncPayloads",      # I6 研发费用 soe
    "buildI1ListedSyncPayloads",   # I1 无形资产 listed
    "buildI1SoeSyncPayloads",      # I1 无形资产 soe
    "buildI2ListedSyncPayloads",   # I2 开发支出 listed
    "buildI2SoeSyncPayloads",      # I2 开发支出 soe
    "buildI3ListedSyncPayloads",   # I3 商誉 listed
    "buildI3SoeSyncPayloads",      # I3 商誉 soe
    "buildF1SyncPayload",          # F1 预付款项（listed+soe，按 variant 附 columns）
    "buildG1SyncPayload",          # G1 交易性金融资产 listed
    "buildG1SoeSyncPayloads",      # G1 交易性金融资产 soe
    "buildH1ListedSyncPayloads",   # H1 固定资产 listed
    "buildH1SoeSyncPayload",       # H1 固定资产 soe
    "buildH2ListedSyncPayloads",   # H2 在建工程 listed
    "buildH2SoeSyncPayloads",      # H2 在建工程 soe
    "buildH6ListedSyncPayloads",   # H6 固定资产清理 listed
    "buildH6SoeSyncPayloads",      # H6 固定资产清理 soe
    "buildH8ListedSyncPayloads",   # H8 使用权资产 listed
    "buildH8SoeSyncPayloads",      # H8 使用权资产 soe
)
_BUILDER_RE = re.compile(r"build[A-Z]\w*Columns\b")
_COLUMNS_FIELD_RE = re.compile(r"\bcolumns\s*:")

# ── allowlist：显式豁免（组件相对 FRONTEND_SRC 的 posix 路径 → 原因）──
# 分波推进（Wave4/5）尚未接入 _columns 的披露组件登记于此，使剩余工作可见。
# 迁移完成后从此移除；新组件默认不得进入 allowlist（须直接携带 columns）。
ALLOWLIST: dict[str, str] = {
    # 示例（实际填充见首次运行报告）：
    # "components/workpaper/g14-credit-impairment-loss/G14TabDisclosureListed.vue":
    #     "Wave4 pending — 需按 G14 源模板提取列头",
}


def _iter_source_files():
    for path in FRONTEND_SRC.rglob("*"):
        if path.suffix not in (".vue", ".ts"):
            continue
        if "__tests__" in path.parts or path.name.endswith(".spec.ts"):
            continue
        yield path


def _rel(path: Path) -> str:
    return path.relative_to(FRONTEND_SRC).as_posix()


_SUBTABLE_FIELD_RE = re.compile(r"sub_table_data\s*:")


def _is_covered(text: str) -> bool:
    # 1) 引用已知会附带 columns 的构造器（payload 由 builder 组装，.vue 内无内联字段）
    if any(b in text for b in COLUMN_BUILDERS):
        return True
    if _BUILDER_RE.search(text):
        return True
    # 2) 内联载荷：``columns:`` 必须与 ``sub_table_data:`` 邻近（同一 payload 对象窗口内），
    #    避免误把 el-table summary-method 的 ``{ columns }: { columns: ... }`` 类型注解
    #    当成覆盖（假阳性会低估 backlog）。
    for m in _SUBTABLE_FIELD_RE.finditer(text):
        window = text[max(0, m.start() - 400): m.end() + 400]
        if _COLUMNS_FIELD_RE.search(window):
            return True
    return False


def main() -> int:
    strict = "--strict" in sys.argv
    if not FRONTEND_SRC.is_dir():
        print(f"[skip] frontend src not found: {FRONTEND_SRC}")
        return 0

    covered: list[str] = []
    uncovered: list[str] = []
    allowlisted: list[str] = []

    for path in _iter_source_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if not any(m in text for m in SYNC_MARKERS):
            continue
        rel = _rel(path)
        if _is_covered(text):
            covered.append(rel)
        elif rel in ALLOWLIST:
            allowlisted.append(rel)
        else:
            uncovered.append(rel)

    total = len(covered) + len(uncovered) + len(allowlisted)
    print("=" * 70)
    print("披露表 _columns 覆盖报告 (disclosure-table-sync-convergence)")
    print("=" * 70)
    print(f"同步调用点总数: {total}")
    print(f"  已覆盖 (含 columns): {len(covered)}")
    print(f"  allowlist 豁免:      {len(allowlisted)}")
    print(f"  未覆盖 (缺 columns):  {len(uncovered)}")

    if allowlisted:
        print("\n-- allowlist 豁免（分波待迁移）--")
        for rel in sorted(allowlisted):
            print(f"  [~] {rel}  # {ALLOWLIST[rel]}")

    if uncovered:
        print("\n-- 未覆盖（须携带 columns 或登记 allowlist 注明原因）--")
        for rel in sorted(uncovered):
            print(f"  [ ] {rel}")

    if strict and uncovered:
        print(f"\n[FAIL] {len(uncovered)} 个同步调用点缺少 columns 且未豁免（--strict）")
        return 1
    print("\n[OK] 覆盖守卫通过" if not uncovered else "\n[WARN] 存在未覆盖项（非 strict 不阻断）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
