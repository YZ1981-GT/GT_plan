/**
 * amountColumnSemantics — 列类型判定单一真源（可编辑金额控件选型的权威依据）
 *
 * Spec: `.kiro/specs/amount-input-migration-and-column-typing/` Task 1（R1.1~R1.5）
 *
 * ## 为什么需要这份真源
 *
 * 平台铁律：**可编辑金额输入只能用** `components/workpaper/shared/WpAmountInput.vue`
 * （失焦千分符 / 聚焦原始值 / 粘贴带逗号可解析 / 非法输入回退不写 NaN）。
 * 因为 `el-input-number` 的 `:formatter` prop 在 element-plus 2.13.6 **根本不存在**
 * （双证：`es/components/input-number/**` 全文无该 prop；浏览器实测 `:formatter` 下
 * 输 `1234567.5` 显示 `1234567.50` 无千分符）。
 *
 * 但「这一列是不是金额」此前是**各文件各写一套关键词**（H 循环
 * `hCycleAmountControlRegistry.ts` 按字段名、D 循环 `fix_d_cycle_amount_inputs.py`
 * 按内联正则），互不一致、无法跨循环复用。本模块把判定收敛到**列 label 语义**
 * 的单一真源（label 是审计师看到的、且跨循环稳定），供判据守卫与迁移脚本共同读取，
 * 避免前后端 / 各循环多份关键词副本（R1.1）。
 *
 * ## 🔴 边界声明（R1.5 / design Property 19）
 *
 * 本模块**只服务可编辑控件的选型判定**（`el-input-number` / `WpAmountInput` /
 * `el-input`）。**只读展示金额**不在本模块判定范围 —— 那部分一律走
 * `displayPrefs.fmtAmount()`（setup 顶层
 * `inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()`），
 * I 循环 Task 18 已收口 16 个 SFC 的 7 种本地 `fmtAmount`，本 spec 不重复处理。
 *
 * ## 🔴 前端运行时不消费本模块
 *
 * 本模块只服务 vitest 守卫与迁移脚本；放在 `src` 下便于 vitest 直接 import，
 * 避免关键词副本。运行时组件不应 import 本模块做渲染分支。
 *
 * ## 判定分层（design 判定链）
 *
 * - `classifyColumnLabelRaw(label)`：纯模式匹配，两类都命中 → `'ambiguous'`
 *   （**不静默二选一**，R1.3）；都不命中 → `'non_amount'`（安全默认：不是金额）
 * - `classifyColumnLabel(label, file)`：先查 `EXPLICIT_OVERRIDES` 裁决，再 fallback
 *   到 raw。歧义 label 由人工在 override 里裁决（带 evidence）。
 */

export type ColumnSemantic = 'amount' | 'non_amount' | 'ambiguous'

/**
 * 非金额语义模式（R1.2 要求覆盖至少 19 类）。
 *
 * 🔴 **每类一个独立、互不覆盖的 pattern，无宽兜底**（如通用 `/率/`）。
 * 理由：变异检验（Task 4）要求「删掉某类关键词 → 真源守卫必红」，
 * 若存在宽兜底，删「税率」后「税率」仍被 `/率/` 命中，守卫不红 = 假绿（守卫缺陷）。
 * 代价是「资本化率」等非 19 类的含率 label 需靠 `EXPLICIT_OVERRIDES` 逐项裁决。
 *
 * `sample` 是该类的 R1.2 代表词，守卫（Property 1）遍历它逐一断言命中。
 */
export interface NonAmountCategory {
  /** 语义类别名（反向失败消息里给「该列属哪类非金额语义」，Property 11） */
  readonly category: string
  readonly pattern: RegExp
  /** R1.2 代表词，供守卫遍历断言命中 */
  readonly sample: string
}

export const NON_AMOUNT_LABEL_PATTERNS: readonly NonAmountCategory[] = [
  { category: '利率', pattern: /利率/, sample: '利率' },
  { category: '汇率', pattern: /汇率/, sample: '汇率' },
  { category: '折现率', pattern: /折现率/, sample: '折现率' },
  { category: '增长率', pattern: /增长率/, sample: '增长率' },
  { category: '毛利率', pattern: /毛利率/, sample: '毛利率' },
  { category: '税率', pattern: /税率/, sample: '税率' },
  { category: '比率', pattern: /比率/, sample: '比率' },
  { category: '占比', pattern: /占比/, sample: '占比' },
  { category: '比例', pattern: /比例/, sample: '比例' },
  { category: '年限', pattern: /年限/, sample: '年限' },
  { category: '期限', pattern: /期限/, sample: '期限' },
  { category: '月份', pattern: /月份/, sample: '月份' },
  { category: '月数', pattern: /月数/, sample: '月数' },
  { category: '天数', pattern: /天数/, sample: '天数' },
  { category: '笔数', pattern: /笔数/, sample: '笔数' },
  { category: '数量', pattern: /数量/, sample: '数量' },
  { category: '股数', pattern: /股数/, sample: '股数' },
  { category: '份数', pattern: /份数/, sample: '份数' },
  // 🔴「年度」用 lookbehind 排除「本/上年度」前缀 —— 那是**时间修饰**而非计量语义，
  // 由核心词定性（「本年度审定数」是金额、「上年度审定数」是金额）。收窄前它们同时命中
  // 「年度」与「审定数」被判假歧义、需逐条 override；收窄后直接判 amount，无需 override。
  // 独立「年度」/「会计年度」（前缀非本/上）仍命中非金额（R1.2 覆盖不变）。
  // 本模块运行时不进浏览器 bundle（只服务 vitest + Python 探针），lookbehind 无兼容性顾虑。
  { category: '年度', pattern: /(?<![本上])年度/, sample: '年度' },
] as const

/**
 * 金额语义模式。保守取词：明确的金额语义，避免与非金额修饰词过度重叠。
 *
 * 「摊销 / 折旧 / 减值」这类短词会与「率 / 期限」共现（如「摊销率」「摊销期限」），
 * 此时 `classifyColumnLabelRaw` 判 `'ambiguous'` 走人工裁决 —— 这是 design 预期的
 * 「5 处歧义」来源，不是缺陷。
 */
export const AMOUNT_LABEL_PATTERNS: readonly RegExp[] = [
  /金额/,
  /余额/,
  /原值/,
  /原价/,
  /残值/,
  /成本/,
  /价值/,
  /净值/,
  /净额/,
  /账面/,
  /摊销/,
  /折旧/,
  /减值/,
  /计提/,
  /拨备/,
  /收入/,
  /费用/,
  /支出/,
  /款项/,
  /价款/,
  /货款/,
  /总额/,
  /发生额/,
  /公允价值/,
  /可回收金额/,
  /可变现净值/,
  /借方/,
  /贷方/,
  // 通用审计金额列语义（审定表、披露表结构性金额列，label 不含「金额」但均为金额）。
  // 实测依据 audit_amount_input_columns.py --json 的 formatter 空操作列分布。
  /未审/,
  /审定/,
  /账项调整/,
  /重分类调整/,
  /AJE/,
  /RJE/,
  /期初数/,
  /期末数/,
  /本期增加/,
  /本期减少/,
  /坏账/,
  /原币/,
] as const

/** override 条目：把某文件某列 label 的判定显式裁决为金额或非金额。 */
export interface OverrideEntry {
  readonly classification: 'amount' | 'non_amount'
  /** 🔴 源模板依据或实测证据，**禁止凭常识添加**（R1.4，守卫要求非空） */
  readonly evidence: string
}

/**
 * 显式裁决清单（歧义与例外）。键 = `{文件相对 components/workpaper/ 的路径}::{列 label}`。
 *
 * 🔴 每条**必带非空 `evidence`**（R1.4 / Property 3）。歧义 label
 * （`classifyColumnLabelRaw` 判 `'ambiguous'` 的）由人工在此裁决，不由脚本静默二选一。
 *
 * 当前收录的是 Task 1 落地时已实测确证的真实歧义（Task 9 会继续把探针报出的
 * `ambiguous` 逐项复核补入，使 `ambiguous` 收敛到 0）。
 */
export const EXPLICIT_OVERRIDES: Readonly<Record<string, OverrideEntry>> = Object.freeze({
  'i1/amortization/I1TabAmortizationNoImpair.vue::摊销期限(月)': {
    classification: 'non_amount',
    evidence:
      '剩余年限法摊销期限为月数（K=F÷剩余月数 J）。I1-10 源表列头「摊销期限(月)」' +
      '实测（2026-08-15）为只读派生月数列。classifyColumnLabelRaw 因同时命中金额词' +
      '「摊销」与非金额词「期限」判 ambiguous，此处裁决为非金额（月数）。',
  },
  'i1/amortization/I1TabAmortizationWithImpair.vue::摊销期限(月)': {
    classification: 'non_amount',
    evidence:
      'I1-11 含减值版摊销测算表，结构对齐 I1-10，「摊销期限(月)」同为剩余月数只读列。' +
      '同 I1-10 裁决为非金额（月数）。',
  },
  'InventoryStocktakeDialog.vue::账面数': {
    classification: 'non_amount',
    evidence:
      '存货盘点差异表「账面数」绑定 row.bookQty（账面**数量**），与「实盘数」row.actualQty ' +
      '配对算数量差异 diffOf = bookQty − actualQty，实测（2026-08-15）为数量列。因含金额词' +
      '「账面」被 raw 判 amount，此处裁决为非金额（数量），保留 el-input-number。',
  },
})

/**
 * 全局 label 裁决（不限文件）——收敛**跨文件同义**的真歧义 label
 * （`classifyColumnLabelRaw` 判 `'ambiguous'`：同时命中金额词与非金额词）。
 *
 * 查询优先级：`EXPLICIT_OVERRIDES`（文件级）> `GLOBAL_LABEL_OVERRIDES`（全局）> raw。
 * 每条同样**必带 evidence**（R1.4 / Property 3）。收录来源 = Task 9 对探针
 * `ambiguous.label_hit_both` 的逐项复核（14 个 unique label / 35 处）。
 */
export const GLOBAL_LABEL_OVERRIDES: Readonly<Record<string, OverrideEntry>> = Object.freeze({
  // —— 数量/比例/年限/期限主导 → 非金额（金额词只是修饰）——
  '账面数量': { classification: 'non_amount', evidence: '「账面」+「数量」共现歧义；实为数量列（份/股数），不加千分符。探针 label_hit_both 实测 10 处。' },
  '数量(账面)': { classification: 'non_amount', evidence: '同「账面数量」，数量列。' },
  '账面·数量': { classification: 'non_amount', evidence: '同「账面数量」，数量列。' },
  '未审数量': { classification: 'non_amount', evidence: '「未审」+「数量」；审定表数量列，非金额。' },
  '审定数量': { classification: 'non_amount', evidence: '「审定」+「数量」；审定表数量列，非金额。' },
  '计提比例': { classification: 'non_amount', evidence: '「计提」+「比例」；实为比例（%），非金额。' },
  '计提比例(%)': { classification: 'non_amount', evidence: '带 % 的计提比例列，非金额。' },
  '折旧年限': { classification: 'non_amount', evidence: '「折旧」+「年限」；实为年限（年数），非金额。' },
  '剩余摊销期限(月)': { classification: 'non_amount', evidence: '「摊销」+「期限」；实为剩余月数，非金额。' },
  // 注：「本年度审定数 / 上年度审定数 / 本年度销售金额」等原需在此裁决，
  // 建议3 收窄「年度」pattern（排除本/上前缀）后，它们的 raw 判定直接为 amount，
  // 不再是假歧义，故从 override 移除（真源更精确、维护量更小）。
})

/** override 键构造（守卫与迁移脚本共用，避免两侧各拼一份）。 */
export function overrideKey(file: string, label: string): string {
  return `${file}::${label}`
}

/** label 是否命中任一非金额语义模式。 */
export function matchesNonAmount(label: string): boolean {
  const s = String(label ?? '')
  return NON_AMOUNT_LABEL_PATTERNS.some((c) => c.pattern.test(s))
}

/** label 是否命中任一金额语义模式。 */
export function matchesAmount(label: string): boolean {
  const s = String(label ?? '')
  return AMOUNT_LABEL_PATTERNS.some((re) => re.test(s))
}

/**
 * 返回 label 命中的**第一个**非金额语义类别名（供反向失败消息用，Property 11）；
 * 未命中返回 null。
 */
export function nonAmountCategoryOf(label: string): string | null {
  const s = String(label ?? '')
  const hit = NON_AMOUNT_LABEL_PATTERNS.find((c) => c.pattern.test(s))
  return hit ? hit.category : null
}

/**
 * 纯模式判定（不查 override）。
 *
 * - 同时命中金额与非金额 → `'ambiguous'`（R1.3，不静默二选一）
 * - 仅命中非金额 → `'non_amount'`
 * - 仅命中金额 → `'amount'`
 * - 都不命中 → `'non_amount'`（安全默认：不是金额，迁移时不会被误换）
 */
export function classifyColumnLabelRaw(label: string): ColumnSemantic {
  const a = matchesAmount(label)
  const n = matchesNonAmount(label)
  if (a && n) return 'ambiguous'
  if (n) return 'non_amount'
  if (a) return 'amount'
  return 'non_amount'
}

/**
 * 判定某文件某列 label 的语义：先查 `EXPLICIT_OVERRIDES` 裁决，再 fallback 到
 * `classifyColumnLabelRaw`。探针与断言消费此函数。
 */
export function classifyColumnLabel(label: string, file?: string): ColumnSemantic {
  if (file) {
    const ov = EXPLICIT_OVERRIDES[overrideKey(file, label)]
    if (ov) return ov.classification
  }
  const g = GLOBAL_LABEL_OVERRIDES[label]
  if (g) return g.classification
  return classifyColumnLabelRaw(label)
}
