/**
 * B50 认定层次风险评估「填写完成度」纯函数。
 *
 * spec: procedure-trimming-and-delegation-intelligence — Task 3 / Requirements 2.1–2.7
 * Property 24（B50 完成度三态与前后端同口径）。
 *
 * ## 为什么需要它
 *
 * 程序裁剪的风险维度判据来自 B50 认定层次矩阵（`max_risk` / `has_special`），而真实库
 * 全部项目的 `B50-T3-*` 均为 0 行（从未有人填过）。若裁剪页不区分「B50 未填」与
 * 「B50 已填且风险为低」，就会把「未评估」当成「低风险」处理 —— 那正是本 spec 要
 * 消除的错误。故裁剪页需要一个与 B50 面板同源的完成度判定。
 *
 * ## 🔴 与既有 `incompleteAccounts` 的口径差异（不得合并）
 *
 * `useB50RiskMatrix.incompleteAccounts` 的判据是「**任一**认定的 combinedRisk 为 null
 * 即算未填完」= 要求六个认定全部填写，服务于「矩阵填写完整性」提示。
 *
 * 本模块 `assessedCount` 的判据是「**至少一个**认定有 RMM 即算已评估」，服务于
 * 「该科目的风险数据是否可用于裁剪判据」—— 裁剪只消费 `max_risk` 与 `has_special`，
 * 有一个认定就已可派生。
 *
 * 两者是不同粒度、**同时成立**的判据（一个科目可以「已评估」但「矩阵未填满」）。
 * 守卫 `b50Completeness.spec.ts` 有一条断言把这个差异钉死，防后续会话"统一"它们 ——
 * 统一到严格口径会让「只填了关键认定」的项目被判成完全没做风险评估，进而在裁剪页
 * 恒显示「B50 未填」而无法使用风险维度。
 *
 * ## 输入的两种来源（两侧同一函数，Property 24 的「同口径」即由此保证）
 *
 * - 后端 `load_b50_accounts()` 形态：`{account, cells: {assertion: {rmm, special}}}`
 * - 前端 `useB50RiskMatrix.accounts` 形态：`{name, cells: {assertion: {combinedRisk}}}`
 *
 * 分别用 `normalizeFromReader` / `normalizeFromMatrixRows` 归一后喂给同一个
 * `resolveB50Completeness`，禁止任一侧另写一份判定。
 */

/** 完成度三态 */
export type B50CompletenessState = 'not_started' | 'partial' | 'completed'

/** 归一化后的最小科目形态（完成度判定只需要这两项） */
export interface B50NormalizedAccount {
  /** 科目名（后端 `account` / 前端 `name`） */
  account: string
  /** 该科目是否至少有一个认定填了综合风险等级（RMM） */
  hasAnyRmm: boolean
}

export interface B50CompletenessResult {
  state: B50CompletenessState
  /** 已导入（出现在矩阵里）的科目数 */
  importedCount: number
  /** 已评估（至少一个认定有 RMM）的科目数 */
  assessedCount: number
  /** 未评估科目名清单（顺序与输入一致，供点击定位） */
  unassessedAccounts: string[]
}

/** 合法风险等级取值（与后端 `LEVEL_CN` / 前端 `RiskLevel` 一致） */
const VALID_LEVELS = new Set(['H', 'M', 'L'])

function isRmmFilled(v: unknown): boolean {
  return typeof v === 'string' && VALID_LEVELS.has(v)
}

/**
 * 后端 `load_b50_accounts()` 返回项 → 归一形态。
 *
 * 只读 `cells[*].rmm`；`max_risk` 虽然也能用，但它是后端派生值，直接读派生值会让
 * 「后端派生逻辑变了」与「数据变了」不可区分 —— 判据一律取最原始的那一层。
 */
export function normalizeFromReader(
  items: readonly { account?: unknown; cells?: unknown }[] | null | undefined,
): B50NormalizedAccount[] {
  if (!Array.isArray(items)) return []
  const out: B50NormalizedAccount[] = []
  for (const it of items) {
    const account = typeof it?.account === 'string' ? it.account : ''
    if (!account) continue
    const cells = it?.cells
    let hasAnyRmm = false
    if (cells && typeof cells === 'object') {
      for (const cell of Object.values(cells as Record<string, unknown>)) {
        if (cell && typeof cell === 'object' && isRmmFilled((cell as { rmm?: unknown }).rmm)) {
          hasAnyRmm = true
          break
        }
      }
    }
    out.push({ account, hasAnyRmm })
  }
  return out
}

/**
 * 前端 `useB50RiskMatrix.accounts`（`AccountRow[]`）→ 归一形态。
 *
 * 前端字段名是 `name` 与 `cells[a].combinedRisk`（不是 `account` / `rmm`）——
 * 这两处命名差异是把两侧接到同一函数时最容易写错的地方。
 */
export function normalizeFromMatrixRows(
  rows: readonly { name?: unknown; cells?: unknown }[] | null | undefined,
): B50NormalizedAccount[] {
  if (!Array.isArray(rows)) return []
  const out: B50NormalizedAccount[] = []
  for (const row of rows) {
    const account = typeof row?.name === 'string' ? row.name : ''
    if (!account) continue
    const cells = row?.cells
    let hasAnyRmm = false
    if (cells && typeof cells === 'object') {
      for (const cell of Object.values(cells as Record<string, unknown>)) {
        if (
          cell &&
          typeof cell === 'object' &&
          isRmmFilled((cell as { combinedRisk?: unknown }).combinedRisk)
        ) {
          hasAnyRmm = true
          break
        }
      }
    }
    out.push({ account, hasAnyRmm })
  }
  return out
}

/**
 * 完成度三态判定（纯函数，零 Vue 依赖）。
 *
 * - `importedCount === 0` → `not_started`
 * - 每个导入科目都已评估 → `completed`
 * - 其余 → `partial`
 *
 * 注意 `not_started` 与「导入了但一个都没评估」是**不同**状态：后者是 `partial`，
 * 因为审计师已经做了「确定审计范围」这一步，引导语应当不同（前者引导导入科目，
 * 后者引导逐科目评估）。
 */
export function resolveB50Completeness(
  input: { accounts?: readonly B50NormalizedAccount[] | null } | null | undefined,
): B50CompletenessResult {
  const accounts = Array.isArray(input?.accounts) ? input!.accounts! : []
  const importedCount = accounts.length
  const unassessedAccounts: string[] = []
  let assessedCount = 0
  for (const a of accounts) {
    if (a.hasAnyRmm) assessedCount += 1
    else unassessedAccounts.push(a.account)
  }
  const state: B50CompletenessState =
    importedCount === 0 ? 'not_started' : assessedCount === importedCount ? 'completed' : 'partial'
  return { state, importedCount, assessedCount, unassessedAccounts }
}

/** 三态中文标签（UI 全中文化；徽标与裁剪页共用一份） */
export const B50_COMPLETENESS_LABEL: Record<B50CompletenessState, string> = {
  not_started: '未开始',
  partial: '部分完成',
  completed: '已完成',
}

/** 三态 el-tag type（未开始用 info 而非 danger —— 未填是待办不是错误） */
export const B50_COMPLETENESS_TAG_TYPE: Record<B50CompletenessState, 'info' | 'warning' | 'success'> = {
  not_started: 'info',
  partial: 'warning',
  completed: 'success',
}

/**
 * 引导文案：三态各自的下一步动作提示。
 *
 * `not_started` 指向既有的「从试算表导入科目」入口（不新建导入能力）。
 */
export const B50_COMPLETENESS_HINT: Record<B50CompletenessState, string> = {
  not_started: '尚未导入需评估的科目。可从试算表一键导入重要科目，再逐科目做认定层次评估。',
  partial: '部分科目尚未评估综合风险等级（RMM）。未评估科目的风险维度无法用于程序裁剪判据。',
  completed: '全部导入科目均已评估，风险维度可用于程序裁剪判据。',
}
