#!/usr/bin/env python
"""披露表 _columns 覆盖守卫（disclosure-table-sync-convergence Task 13）

扫描前端全部 `disclosure-notes/sync-from-workpaper` / `sync-batch-from-workpaper`
调用点，核对其推送载荷是否携带 `columns` 列头元数据（供附注模块投影渲染源模板表样）。

- 已覆盖：文件含 `columns` 载荷字段（显式键 `columns:` 或 ES6 对象简写 `columns,`
  ——后者是 `const { sub_table_data, columns } = build*SyncPayload()` 的常见形态），
  或引用已知会附带 columns 的构造器（buildF2SyncPayload / buildSyncColumns / build*Columns）。
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
    "buildD1SyncPayload",          # D1 应收票据（listed+soe，按 variant 附 columns）
    "buildD2SyncPayload",          # D2 应收账款（listed+soe，按 variant 附 columns）
    "buildD3SyncPayload",          # D3 预收款项（listed+soe，按 variant 附 columns）
    "buildD5SyncPayload",          # D5 应收款项融资（listed+soe，按 variant 附 columns）
    "buildD6SyncPayload",          # D6 合同资产（listed+soe，按 variant 附 columns）
    "buildD4SyncPayload",          # D4 营业收入/营业成本（listed+soe，按 variant 附 columns）
    "buildD7SyncPayload",          # D7 合同负债（listed+soe，按 variant 附 columns）
    "buildE1SyncPayload",          # E1 货币资金（listed+soe，按 variant 附 columns）
    "buildN1SyncPayload",          # N1 递延所得税资产（listed+soe，与 N3 共用章节，owner=N1）
    "buildH3SyncPayload",          # H3 投资性房地产（listed+soe，按计量模式推表）
    "buildH5SyncPayload",          # H5 油气资产 soe（listed 无独立章节）
    "buildK2SyncPayload",          # K2 其他流动资产（listed+soe）
    "buildK3SyncPayload",          # K3 其他应付款（listed+soe）
    "buildK4SyncPayload",          # K4 其他流动负债（listed+soe）
    "buildK5SyncPayload",          # K5 预计负债（listed+soe）
    "buildK6SyncPayload",          # K6 持有待售资产（listed+soe）
    "buildK7SyncPayload",          # K7 递延收益（listed+soe）
    "buildK8SyncPayload",          # K8 销售费用（listed+soe）
    "buildK9SyncPayload",          # K9 管理费用（listed+soe）
    "buildK10SyncPayload",         # K10 其他收益（listed+soe）
    "buildK11SyncPayload",         # K11 资产减值损失（listed+soe）
    "buildK12SyncPayload",         # K12 营业外收入（listed+soe）
    "buildK13SyncPayload",         # K13 营业外支出（listed+soe）
    # ── 批 1~3 收口（逐个核对过实现确实输出 columns，非仅凭命名登记）──
    "buildL1SyncPayload",          # L1 短期借款（listed+soe，逾期表条件推送时 columns 成对）
    "buildL3SyncPayload",          # L3 长期借款（listed+soe）
    "buildF4ListedSyncPayload",    # F4 应付账款 listed（f4NoteSectionMap 4 组列头）
    "buildF4SoeSyncPayload",       # F4 应付账款 soe
    "buildJ1SyncPayload",          # J1 应付职工薪酬（listed+soe，3 表共用 j1MovementColumns）
    "buildH4ListedSyncPayloads",   # H4 工程物资 listed（复用 H2 五、23 列头，按实际推送键取子集）
)
_BUILDER_RE = re.compile(r"build[A-Z]\w*Columns\b")

# ── allowlist：显式豁免（组件相对 FRONTEND_SRC 的 posix 路径 → 原因）──
# 分波推进（Wave4/5）尚未接入 _columns 的披露组件登记于此，使剩余工作可见。
# 迁移完成后从此移除；新组件默认不得进入 allowlist（须直接携带 columns）。
#
# 🔴 **原因必填**：值为空串 / 空白 / None 视为**未登记**，该项仍计入未覆盖并在
# --strict 下阻断（disclosure-columns-coverage-rollout R4.3）。防「先占位再补原因」
# 变成永久豁免 —— 豁免必须写清是哪一波待迁移、依据什么源模板。
ALLOWLIST: dict[str, str] = {
    # 示例（实际填充见首次运行报告）：
    # "components/workpaper/g14-credit-impairment-loss/G14TabDisclosureListed.vue":
    #     "Wave4 pending — 需按 G14 源模板提取列头",
}


def allowlist_reason(rel: str) -> str:
    """返回该路径的豁免原因；未登记或原因空白 → 空串（= 不豁免）。"""
    return str(ALLOWLIST.get(rel) or "").strip()


def is_allowlisted(rel: str) -> bool:
    """豁免生效 = 已登记 **且** 原因非空白。"""
    return bool(allowlist_reason(rel))


def blank_reason_entries() -> list[str]:
    """已登记但原因空白的条目（供报告单列，提示补原因而非静默失效）。"""
    return sorted(rel for rel in ALLOWLIST if not allowlist_reason(rel))


def _iter_source_files():
    for path in FRONTEND_SRC.rglob("*"):
        if path.suffix not in (".vue", ".ts"):
            continue
        if "__tests__" in path.parts or path.name.endswith(".spec.ts"):
            continue
        yield path


def _rel(path: Path) -> str:
    return path.relative_to(FRONTEND_SRC).as_posix()


# 🔴 载荷字段既可能写成显式键（``sub_table_data:``），也可能是 **ES6 对象简写**
# （``sub_table_data,`` / ``columns,`` / 换行后紧跟 ``}``）——L1/L3 四个 Tab 用的正是简写，
# 旧正则只认冒号故把它们误报为「缺 columns」（假阴性）。故两种写法都认：
# 后随字符限定为 ``, : } 换行``，以免把 ``columns.forEach`` / ``columnsRef`` 之类误当字段。
_SUBTABLE_FIELD_RE = re.compile(r"\bsub_table_data\s*[,:}\n]")
_COLUMNS_FIELD_RE = re.compile(r"\bcolumns\s*[,:}\n]")

# 邻近窗口半径：``columns`` 须与 ``sub_table_data`` 落在同一载荷对象/解构语句附近
_PROXIMITY_WINDOW = 400


def _is_covered(text: str) -> bool:
    # 1) 引用已知会附带 columns 的构造器（payload 由 builder 组装，.vue 内无内联字段）
    if any(b in text for b in COLUMN_BUILDERS):
        return True
    if _BUILDER_RE.search(text):
        return True
    # 2) 内联载荷：``columns`` 必须与 ``sub_table_data`` 邻近（同一 payload 对象/解构窗口内），
    #    避免误把 el-table summary-method 的 ``{ columns }: { columns: ... }`` 类型注解
    #    当成覆盖（假阳性会低估 backlog）。
    #    反之，通篇没有 ``columns`` 的调用点仍判未覆盖 —— 简写只放宽写法，不放宽实质要求。
    for m in _SUBTABLE_FIELD_RE.finditer(text):
        window = text[max(0, m.start() - _PROXIMITY_WINDOW): m.end() + _PROXIMITY_WINDOW]
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
        elif is_allowlisted(rel):
            allowlisted.append(rel)
        else:
            # 含「已登记但原因空白」——按未覆盖处理（R4.3）
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
            print(f"  [~] {rel}  # {allowlist_reason(rel)}")

    blank = blank_reason_entries()
    if blank:
        print("\n-- allowlist 原因空白（视为未登记，豁免不生效）--")
        for rel in blank:
            print(f"  [!] {rel}  # 请补写豁免原因（哪一波待迁移 / 依据哪个源模板）")

    if uncovered:
        print("\n-- 未覆盖（须携带 columns 或登记 allowlist 注明原因）--")
        for rel in sorted(uncovered):
            hint = "  ← allowlist 已登记但原因空白" if rel in ALLOWLIST else ""
            print(f"  [ ] {rel}{hint}")

    if strict and uncovered:
        print(f"\n[FAIL] {len(uncovered)} 个同步调用点缺少 columns 且未豁免（--strict）")
        return 1
    print("\n[OK] 覆盖守卫通过" if not uncovered else "\n[WARN] 存在未覆盖项（非 strict 不阻断）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
