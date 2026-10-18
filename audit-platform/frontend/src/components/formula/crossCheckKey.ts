/**
 * 表间审核树节点 key ↔ 规则 map key 的**唯一生成函数**（MEDIUM-2 响应）。
 *
 * spec: formula-manager-closure Phase 6 Task 6.2（需求 7.4 / design §5 步骤 6）
 *
 * 🔴 **为什么要单一真源**：历史实现里，表间审核树（`acnrDrivenTree` 下的
 * `cross_check` 分组）的父节点 key 与规则存储 `crossCheckRulesMap` 的 key 是
 * **两处各自硬编码**的字符串。一旦有人改了其中一处（比如把 `cross_report_note`
 * 改成 `cross_rn`），树点得到的 `selectedNodeKey` 就取不到对应规则集 ——
 * 右栏恒空却不报错（契约静默断裂）。需求 7.4 要求「树的父/叶 key 与规则 map 的
 * key 一致」，本模块把 key 生成收敛成**一个函数**，树与规则 map 都只经它产出，
 * 使「不一致」在结构上不可能发生。
 *
 * 分组域（domain）稳定枚举：三类跨表勾稽 + 合并勾稽。
 */

/** 表间审核分组域（与后端 logic_check 勾稽类型 source↔target 对齐）。 */
export type CrossCheckDomain =
  | 'report_note'
  | 'report_wp'
  | 'note_wp'
  | 'consol'

/** 全部分组域（树构建与规则 map 初始化都遍历此清单，保证两侧节点集合一致）。 */
export const CROSS_CHECK_DOMAINS: readonly CrossCheckDomain[] = [
  'report_note',
  'report_wp',
  'note_wp',
  'consol',
] as const

/**
 * 由分组域生成**唯一** key。树父节点 key 与规则 map key 都调用本函数，
 * 任何一侧绕开它直接写字符串都会被 `sheetKeyNormalizationParity` 同款单测抓到。
 *
 * 当前实现：`cross_${domain}`（与历史 key `cross_report_note` 等逐字一致，
 * 零行为变化；收敛的是「生成口径」而非「值」）。
 */
export function crossCheckNodeKey(domain: CrossCheckDomain): string {
  return `cross_${domain}`
}

/** 便捷索引：domain → key（树与规则 map 初始化时共用，避免重复调用散落）。 */
export const CROSS_CHECK_NODE_KEYS: Record<CrossCheckDomain, string> =
  CROSS_CHECK_DOMAINS.reduce((acc, domain) => {
    acc[domain] = crossCheckNodeKey(domain)
    return acc
  }, {} as Record<CrossCheckDomain, string>)
