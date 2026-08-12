/**
 * 裁剪理由码前端镜像（纯常量 + 纯函数，零 Vue 依赖、零 IO）。
 *
 * spec: procedure-trimming-and-delegation-intelligence — Task 12
 * 守卫: `__tests__/trimReasonCodes.spec.ts`（读后端 py 源码抽枚举逐值比对）
 * Requirements: 8.1 / 8.2 / 8.3 / 8.4 / 8.5
 *
 * ## 为什么要有这份镜像，以及为什么它必须被守卫钉死
 *
 * 理由码的**唯一真源是后端** `app/services/procedure_trim_engine.py::TrimReasonCode`。
 * 前端需要它做两件事：把码翻成中文标签给审计师看、把决策内核产出的码提交给后端。
 * 于是同一套取值不可避免地存在两份。
 *
 * 平台已经反复吃过「同一不变式两处各写一份 ⇒ 改一处另一处不动」的亏，故本模块的
 * 存在前提是**跨前后端交叉锁死**：守卫读后端 `.py` 源码抽出 enum 全部取值，与本文件
 * `TRIM_REASON_CODES` 逐值比对，任一侧新增而另一侧未跟进即打红。这样「两份」在
 * 一致性上等价于「一份」，而不需要引入运行时的跨端取数。
 *
 * ## 七个取值分两类，来源完全不同
 *
 * | 取值 | 谁产出 | 语义 |
 * |---|---|---|
 * | `no_data` | 决策内核自动 | 科目在试算平衡表中无数据 ⇒ 无可实施程序的对象 |
 * | `below_trivial` | 决策内核建议 | 余额低于明显微小错报临界值 |
 * | `below_materiality` | 决策内核建议 | 余额低于实际执行重要性 |
 * | `covered_elsewhere` | 人工选择 | 相关认定已由其他底稿覆盖 |
 * | `no_related_business` | 人工选择 | 被审计单位无此类业务 |
 * | `low_risk_assessment` | 人工选择 | 经风险评估该程序不适用 |
 * | `control_test_effective` | 人工选择 | 控制测试有效，可缩小实质性程序范围 |
 * | `other` | 人工选择 | 其他（须在理由文本中说明） |
 *
 * 前三个是本 spec 新增的**机器判据**（`MACHINE_REASON_CODES`），只由 `decideTrim`
 * 产出；其余是审计师在下拉里选的**人工判据**。区分这两类的用处：复核视图统计
 * 「有多少裁剪是系统建议的、有多少是人工判断的」，以及汇总闸只对重要性类计数
 * （见 `trimAggregateGate` 的 `MATERIALITY_REASON_CODES`）。
 *
 * ## 存量兼容（R8.4）
 *
 * 改造前粗裁只有自由文本 `skip_reason`、没有理由码。故：
 *
 * - `reasonCodeLabel(null)` 返回 `null` 而**不是**「未知理由」—— 存量记录必须按
 *   原文显示 `skip_reason`，显示成「未知理由」等于把「有理由但没有码」谎报成
 *   「没有理由」，会让复核视图的「缺理由」计数虚高。
 * - 未登记的码原样回显（`reasonCodeLabel('xyz') === 'xyz'`）而不是丢弃 —— 后端
 *   若先行新增取值，前端在守卫打红之前至少不会把它显示成空白。
 */

// ═══════════════════════════════════════════════════════════════════════════
// 取值域（后端 TrimReasonCode 的镜像；守卫逐值比对）
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 全部理由码，**顺序与后端 enum 声明顺序一致**（守卫按顺序比对，便于定位漂移）。
 *
 * 🔴 新增取值必须两侧同改：后端 `TrimReasonCode` + 本常量 + `TRIM_REASON_LABELS`。
 * 少改任一处，`trimReasonCodes.spec.ts` 会打红。
 */
export const TRIM_REASON_CODES = [
  'no_related_business',
  'low_risk_assessment',
  'control_test_effective',
  'other',
  'no_data',
  'below_trivial',
  'below_materiality',
  'covered_elsewhere',
] as const

export type TrimReasonCodeValue = (typeof TRIM_REASON_CODES)[number]

/**
 * 由决策内核自动产出的理由码（其余为人工选择）。
 *
 * 🔴 这不只是个分类标签：复核视图靠它区分「系统建议的裁剪」与「人工判断的裁剪」，
 * 两者的复核关注点不同 —— 前者要看判据数值对不对，后者要看理由是否充分。
 */
export const MACHINE_REASON_CODES: ReadonlySet<string> = new Set([
  'no_data',
  'below_trivial',
  'below_materiality',
])

/**
 * 中文标签。每个取值都必须有标签（守卫断言无缺无余）。
 *
 * 措辞取自审计实务用语，且与 `ProcedureTrimming.vue` 既有的 `COMMON_SKIP_REASONS`
 * 下拉措辞对齐 —— 两处指同一件事时用同一句话，复核时才好对上。
 */
export const TRIM_REASON_LABELS: Readonly<Record<TrimReasonCodeValue, string>> = {
  no_related_business: '被审计单位无此类业务',
  low_risk_assessment: '经风险评估该程序不适用',
  control_test_effective: '控制测试有效，可缩小实质性程序范围',
  other: '其他（见理由说明）',
  no_data: '科目在试算表中无数据（无余额/未发生）',
  below_trivial: '金额低于明显微小错报临界值',
  below_materiality: '金额低于实际执行重要性',
  covered_elsewhere: '相关认定已在其他底稿覆盖',
}

// ═══════════════════════════════════════════════════════════════════════════
// 纯函数
// ═══════════════════════════════════════════════════════════════════════════

const _CODE_SET: ReadonlySet<string> = new Set<string>(TRIM_REASON_CODES)

/** 该字符串是否为已登记的理由码。 */
export function isTrimReasonCode(value: unknown): value is TrimReasonCodeValue {
  return typeof value === 'string' && _CODE_SET.has(value)
}

/**
 * 理由码 → 中文标签。
 *
 * 🔴 三态语义，不得退化：
 * - `null` / `undefined` / 空串 → 返回 `null`（存量只有自由文本，调用方须回退显示
 *   `skip_reason` 原文；返回「未知理由」会让存量裁剪被误判成缺理由）
 * - 已登记 → 中文标签
 * - 未登记 → **原样回显**（后端先行新增时不至于显示空白）
 */
export function reasonCodeLabel(code: string | null | undefined): string | null {
  if (code === null || code === undefined) return null
  const text = String(code).trim()
  if (!text) return null
  if (isTrimReasonCode(text)) return TRIM_REASON_LABELS[text]
  return text
}

/**
 * 组装展示用理由：优先「中文标签」，附上自由文本补充说明。
 *
 * 用于裁剪页与复核视图的「理由」列 —— 审计师既要看到规范化的理由类别，也要看到
 * 本科目的具体判据数值（`decideTrim` 的 narrative 会被写进 `skip_reason`）。
 *
 * 两者相同或文本已包含标签时不重复拼接。
 */
export function formatTrimReason(args: {
  reasonCode?: string | null
  skipReason?: string | null
}): string {
  const label = reasonCodeLabel(args?.reasonCode)
  const text = String(args?.skipReason ?? '').trim()
  if (!label) return text
  if (!text) return label
  if (text === label || text.includes(label)) return text
  return `${label}：${text}`
}

/** 该理由码是否由决策内核自动产出（用于复核视图分类统计）。 */
export function isMachineReasonCode(code: string | null | undefined): boolean {
  if (code === null || code === undefined) return false
  return MACHINE_REASON_CODES.has(String(code).trim())
}

/** 下拉选项（`{value, label}`），供 el-select 直接消费。 */
export function trimReasonOptions(): Array<{ value: TrimReasonCodeValue; label: string }> {
  return TRIM_REASON_CODES.map((value) => ({ value, label: TRIM_REASON_LABELS[value] }))
}
