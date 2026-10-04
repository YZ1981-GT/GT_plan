/**
 * D4 营业收入 — 程序表常量
 */
export const D4_PROCEDURE_STEPS_CONFIG: Array<{
  stepName: string
  description: string
  isRequired: boolean
  relatedTab: string | null
}> = [
  { stepName: '获取明细', description: '获取主营业务收入及其他业务收入明细，复核加计正确', isRequired: true, relatedTab: 'revenue-detail' },
  { stepName: '核对总账', description: '核对营业收入总账与明细账、报表一致', isRequired: true, relatedTab: 'adjudication' },
  { stepName: '分析程序', description: '实施毛利率、客户结构等重要指标分析', isRequired: true, relatedTab: 'indicator' },
  { stepName: '合同检查', description: '检查销售合同条款与收入确认政策一致性', isRequired: true, relatedTab: 'contract' },
  { stepName: '发生测试', description: '对重要交易实施发生认定检查', isRequired: true, relatedTab: 'occurrence' },
  { stepName: '完整性测试', description: '实施完整性认定检查程序', isRequired: true, relatedTab: 'completeness' },
  { stepName: '截止测试', description: '实施截止性测试（账到单据/单据到账）', isRequired: true, relatedTab: 'cutoff-forward' },
  { stepName: '披露检查', description: '检查营业收入附注披露完整性', isRequired: true, relatedTab: 'disclosure' },
  { stepName: '结论', description: '汇总营业收入审计发现，形成整体结论', isRequired: false, relatedTab: null },
]

/**
 * legacy OnlyOffice 通道**禁入**名单（单一真源，宿主 GtD4OperatingRevenue 消费）。
 *
 * `GtOnlyOfficeSheet` 是 legacy 单向通道（平台口径「假双向」）：能打开 OnlyOffice、能编辑、
 * 能保存，但改动**不会**回到 HTML store。因此对「有结构化 store 载荷、却尚未接双向同步桥」
 * 的表，必须挡在 legacy 通道之外 —— 静默数据丢失比「不给入口」危险得多。
 *
 * 判据（三者同时成立才入名单）：
 *   1. 该 sheet 有结构化 store item（前端 composable 有持久化键）；
 *   2. 既不在宿主桥（`isD4DetailSheet` ← `D4_SHEET_KEY_BY_CODE`），也不在子组件桥
 *      （`isD4DedicatedSyncSheet`）；
 *   3. 后端契约 `d4.revenue_detail.json` 无对应 `{code}-managed` sheet_key。
 *
 * 名单成员：
 *   - `D4-5` 会计政策检查：**历史冗余项**，已接子组件桥（`d45-managed`）故实际不可能命中
 *     legacy 分支；原宿主模板里的 `currentSheet !== 'D4-5'` 单点特判收敛到此，行为逐字等价。
 *
 * 已摘除（接桥完成）：
 *   - `D4-4` 调整分录汇总 —— 2026-09-28 落地真双向（spec
 *     `d4-4-adjustment-summary-bidirectional-writeback`）：契约新增 `d44-managed`
 *     （35→36 张 / 775→785 字段），provider `phase5_d4_adjustment_sheet`，
 *     `D4TabAdjustment.vue` 已接 `useD4SyncMode`，宿主已登记进 `isD4DedicatedSyncSheet`。
 *     🔴 摘除本项与「加进 dedicated 列表」**必须同批**：只摘名单不加 dedicated 会掉回
 *     legacy 单向通道；只加 dedicated 不摘名单会让 `renderMode` 恒 `'html'`、切换器恒
 *     disabled，新桥点不进去。
 *
 * ⚠️ 与 `isD4DedicatedSyncSheet` 的区别：后者是「已有真双向桥，宿主不介入」；本名单是
 * 「还没有桥，所以连 legacy 假桥也不给」。某表接桥后应从本名单移除并加进 dedicated 列表。
 */
export const D4_LEGACY_OO_BLOCKED_SHEETS: ReadonlySet<string> = new Set(['D4-5'])

/** 该 sheet 是否禁止走 legacy OnlyOffice 单向通道。 */
export function isD4LegacyOoBlocked(sheetCode: string | null | undefined): boolean {
  return D4_LEGACY_OO_BLOCKED_SHEETS.has(sheetCode || '')
}
