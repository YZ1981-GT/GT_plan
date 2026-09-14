/**
 * replyStatus — 「是否已回函」(`is_replied`) 三态归一的**单一真源**
 *
 * ## 为什么需要这个模块
 *
 * `is_replied` 在平台里存在**两种持久化形态**，且都是真实存在的历史数据：
 *
 * | 写入方 | 形态 | 出处 |
 * |--------|------|------|
 * | 完整表格视图 `ConfirmationFullGrid.vue` | `boolean` | `confirmationColumnSpec` 声明 `kind: 'bool'` → `el-checkbox` |
 * | 明细面板 / Excel 导入 / 早期实现 | `'是'` / `'否'` | 源模板 X0-1「是否收到回函」列的数据有效性就是 `是,否` |
 *
 * 于是同一个字段被多处用不同口径读，其中**两处恒不成立**（2026-08-05 实证）：
 * - `GtConfirmationSummary.vue` ×3：`r.is_replied === '是' || r.is_replied === true` 兼容两形态（但是第三份口径）
 * - `ConfirmationDetail.vue` ×2：`row.is_replied === '否'` —— 布尔 `false` 永不命中
 *   ⇒ 「消极式未回函 → 视同相符」/「积极式未回函 → 需替代程序」两条派生提示**从未渲染过**
 * - `importFromSummary.defaultUnrepliedFilter`：`r.is_replied === false` —— 字符串 `'否'` 永不命中
 *
 * **数据零丢失是硬红线** ⇒ 不迁移已持久化的值，一律**读时归一**。
 *
 * ## 三态必须保留，禁把「未填」折叠成「否」
 *
 * `undefined`（未填）与 `false`/`'否'`（明确未回函）是**两种不同的审计事实**：
 * - 未填 = 审计师还没判断，UI 应显示空白、不做任何派生
 * - 明确未回函 = 审计事实，必须进 F0-5/F0-6 替代程序清单、必须显示替代程序提示
 *
 * 若折叠成 false，新建的空行会立刻被当成「未回函」带进替代程序底稿（凭空造披露内容）。
 * 故 {@link isReplied} 返回 `boolean | undefined`，而 {@link isNotReplied} 只在
 * **显式为否**时返回 true。
 *
 * ## 消费方（改动此处必须同步核对）
 *
 * - `ConfirmationDetail.vue`：`is_replied` 录入控件 / 回函信息块 `v-show` / 两条派生提示
 * - `GtConfirmationSummary.vue`：三处 AI 上下文「已回函行数」统计
 * - `coordination/importFromSummary.ts`：`defaultUnrepliedFilter`（F0-5「从 F0-1 带入」的判据）
 * - `g0-confirmation/alternativeG06`、`alternativeH05`：各自的「从 X0-1 带入」内联过滤
 *
 * spec: f0-confirmation-linkage-and-structural-enhancement（Wave 9 / Defect 2）
 */

/** `is_replied` 的全部合法持久化形态（两种历史写入口径并存，不迁移） */
export type ReplyFlag = boolean | '是' | '否' | null | undefined

/** 明细面板 `el-select` 用的选项（值即持久化字面，与源模板 X0-1 数据有效性 `是,否` 一致） */
export const REPLY_FLAG_OPTIONS: ReadonlyArray<{ label: string; value: '是' | '否' }> = Object.freeze([
  Object.freeze({ label: '是', value: '是' as const }),
  Object.freeze({ label: '否', value: '否' as const }),
])

// 两张 token 表必须声明在 normalizeReplyFlag **之前**：模块级 const 有 TDZ，
// 若某天有人在模块初始化期（如另一个模块级常量的初始值）调用归一函数，
// 声明在后面会抛 ReferenceError（memory 已记同款：watch 依赖数组在 setup 期求值）。
const TRUE_TOKENS = new Set(['是', 'y', 'yes', 'true', '1', '√', '是的', '已回函'])
const FALSE_TOKENS = new Set(['否', 'n', 'no', 'false', '0', '×', 'x', '未回函'])

/**
 * 归一「是否已回函」为三态。
 *
 * @returns `true` = 已回函 / `false` = 明确未回函 / `undefined` = 未填（**不可当 false 用**）
 *
 * 认以下形态（做 trim，Excel 导入常带空白）：
 * - `true` / `'是'` / `'Y'` / `'yes'` / `'true'` / `'1'` / `'√'` → `true`
 * - `false` / `'否'` / `'N'` / `'no'` / `'false'` / `'0'` / `'×'` / `'x'` → `false`
 * - `undefined` / `null` / `''` / 其它无法识别的文本 → `undefined`
 */
export function normalizeReplyFlag(value: unknown): boolean | undefined {
  if (value === true || value === false) return value
  if (value == null) return undefined
  const text = String(value).trim()
  if (!text) return undefined
  if (TRUE_TOKENS.has(text) || TRUE_TOKENS.has(text.toLowerCase())) return true
  if (FALSE_TOKENS.has(text) || FALSE_TOKENS.has(text.toLowerCase())) return false
  return undefined
}

/** 行的回函三态（`undefined` = 未填，调用方不得当 false 用） */
export function isReplied(row: { is_replied?: ReplyFlag } | null | undefined): boolean | undefined {
  if (!row) return undefined
  return normalizeReplyFlag(row.is_replied)
}

/** 是否**显式**已回函（未填返回 false —— 用于「已回函行数」这类计数口径） */
export function isRepliedTrue(row: { is_replied?: ReplyFlag } | null | undefined): boolean {
  return isReplied(row) === true
}

/**
 * 是否**显式**未回函。
 *
 * 未填（`undefined`）返回 **false** —— 空行不得被当成未回函带进替代程序底稿。
 */
export function isNotReplied(row: { is_replied?: ReplyFlag } | null | undefined): boolean {
  return isReplied(row) === false
}

/**
 * 「回函信息」区块是否应可见。
 *
 * 判据 = 已回函 **或** 相符情况已给出回函结论（相符/不符）——
 * 后者是为了兼容「只填了相符情况没填是否回函」的既有数据，
 * 否则那些行的回函金额/回函日期会被藏起来读不到（数据零丢失）。
 */
export function shouldShowReplyBlock(
  row: { is_replied?: ReplyFlag; match_status?: string } | null | undefined,
): boolean {
  if (!row) return false
  if (isReplied(row) === true) return true
  const status = String(row.match_status ?? '').trim()
  return status === '相符' || status === '不符'
}
