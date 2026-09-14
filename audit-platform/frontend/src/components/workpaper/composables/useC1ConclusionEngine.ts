/**
 * useC1ConclusionEngine — C1 企业层面控制测试 结论聚合 / 点选合法性 / 回写事件 纯函数引擎
 *
 * 所有函数为纯函数，无副作用，无 Vue 响应式依赖，便于单元测试和 PBT。
 * 单一来源（single source）：点选字段枚举、点选值合法化、各段结论 → 整体结论自动建议、
 * 结论回写事件是否应发布（新旧值比较）统一由本模块提供，GtC1EntityControl.vue 复用。
 *
 * Spec: .kiro/specs/c1-entity-level-control/  Task 7.3
 * Requirements: 11.1, 11.3, 11.4
 * Correctness Properties: P7 点选值合法性 / P9 结论回写事件正确性
 */

// ─── 点选字段枚举（单一来源；Phase0 §5 实测取值 + design 点选控件映射） ──────────

/** 控制频率（el-select 单选） */
export const FREQ_OPTIONS = ['每月一次', '每季一次', '每年一次', '根据需要'] as const
/** 测试方法（el-checkbox-group 多选） */
export const TEST_METHOD_OPTIONS = ['询问和观察', '检查', '重新执行', '抽样'] as const
/** 测试 / 段 / 整体结论（el-select 单选） */
export const CONCLUSION_OPTIONS = ['有效', '部分有效', '无效'] as const

export type Conclusion = (typeof CONCLUSION_OPTIONS)[number]

// ─── P7 点选值合法性：将任意输入合法化为「枚举值 ∪ null」（杜绝自由文本注入） ──────

/**
 * 单选点选值合法化（Property P7）。
 *
 * 对任意输入（含自由文本 / null / 未在枚举内的值）：
 * - 值恰好属于 options → 返回该值
 * - 否则一律返回 null（不保存非法值，杜绝自由文本注入）
 *
 * 纯函数，不修改入参。
 */
export function sanitizeEnumValue(
  options: readonly string[],
  value: unknown,
): string | null {
  if (typeof value !== 'string') return null
  return options.includes(value) ? value : null
}

/**
 * 多选点选值合法化（Property P7）。
 *
 * 对任意输入数组：仅保留属于 options 的成员，去重，保持 options 顺序。
 * 非数组 / 空 → 返回空数组。保证输出 ⊆ options（无自由文本注入）。
 */
export function sanitizeMultiEnum(
  options: readonly string[],
  values: unknown,
): string[] {
  if (!Array.isArray(values)) return []
  const set = new Set(values.filter((v): v is string => typeof v === 'string' && options.includes(v)))
  // 按 options 顺序输出，稳定且去重
  return options.filter((o) => set.has(o))
}

/** 判定单个值是否为合法结论枚举 */
export function isValidConclusion(value: unknown): value is Conclusion {
  return typeof value === 'string' && (CONCLUSION_OPTIONS as readonly string[]).includes(value)
}

// ─── 各段结论 → 整体结论自动建议（Requirement 11.3） ────────────────────────────

/**
 * 汇总各要素/各段测试结论，自动建议企业层面控制整体结论（Requirement 11.3）。
 *
 * 就低（保守）聚合口径（审计判断：短板决定整体）：
 * - 忽略空 / null / 非法值（未填结论的段不参与聚合）
 * - 存在任一「无效」   → 建议「无效」
 * - 否则存在任一「部分有效」→ 建议「部分有效」
 * - 否则（全部为「有效」且至少一项）→ 建议「有效」
 * - 无任何有效结论输入 → 返回 null（无可建议，UI 不覆盖用户已选）
 *
 * 用户可在 UI 覆盖本建议（点选优先）。纯函数，不修改入参。
 */
export function suggestOverallConclusion(
  sectionConclusions: readonly (string | null | undefined)[],
): Conclusion | null {
  let hasValid = false
  let hasPartial = false
  let hasAny = false
  for (const c of sectionConclusions) {
    if (!isValidConclusion(c)) continue
    hasAny = true
    if (c === '无效') return '无效' // 就低：一票否决
    if (c === '部分有效') hasPartial = true
    if (c === '有效') hasValid = true
  }
  if (!hasAny) return null
  if (hasPartial) return '部分有效'
  if (hasValid) return '有效'
  return null
}

// ─── P9 结论回写事件正确性：仅在新旧值不同时发布 ────────────────────────────────

/** 归一化结论值：null / undefined / 纯空白统一视为空串，便于新旧值比较 */
export function normalizeConclusion(value: string | null | undefined): string {
  if (value === null || value === undefined) return ''
  return String(value).trim()
}

/**
 * 判定整体结论变更是否应发布 EventBus 事件（Property P9 / Requirement 11.4）。
 *
 * 铁律：仅在归一化后的新旧值**不同**时返回 true（避免重复/无变更事件）。
 * 纯函数。
 */
export function shouldPublishConclusion(
  oldValue: string | null | undefined,
  newValue: string | null | undefined,
): boolean {
  return normalizeConclusion(oldValue) !== normalizeConclusion(newValue)
}
