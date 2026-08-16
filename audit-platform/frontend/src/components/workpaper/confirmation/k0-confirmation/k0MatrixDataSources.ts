/**
 * k0MatrixDataSources.ts — K0-1 矩阵账面金额取数 + 手工覆盖键
 *
 * spec: k0-confirmation-source-alignment · Task 11（Requirements 4.2 / 4.3 / 4.4 / 4.6）
 *
 * ─── 🔴🔴 落手时实测推翻的 spec 描述（勿按旧描述实现）────────────────────────
 * tasks.md Task 11 写「从 K1 / K3 render-config **既有出口**取数」，而逐个读 render
 * 源码实测：**两侧出口键名完全不同，且 K1 压根没有 `tb_amount`**
 * （同族已登记：F1/F3/F4 的 TB 核对标量键名三者各不相同 —— 统一读
 *  `project_context.tb_amount` 只有一个命中，另两个静默落空）。
 *
 * | 循环 | 有 `tb_amount`? | 本 spec 采用的口径 | 实测出处 |
 * |------|-----------------|--------------------|----------|
 * | K1   | **无**（全文只有形参 `tb_amounts`） | `adjudication_prefill.fs_reconciliation.report_total` | `_k1_other_receivables.py::_build_fs_reconciliation` |
 * | K3   | 有（`= tb_values.payable_unadjusted`，**默认 0**） | `tb_values.other_payable_2241_closing` | `_k3_other_payables.py::build_tb_values` |
 *
 * 选这两个键的理由：
 * 1. **K1 的 `report_total` 就是 BS-009 净额口径** —— 它按报表公式里每个 `TB()` 的
 *    **前置运算符**加权求和（`TB('1221') − TB('1231-03') + TB('1131')`），与报表引擎同口径；
 *    而 `tb_values.receivable_unadjusted` 是**原值**（不减备抵），直接拿来当账面金额
 *    会让「发函金额占账面比例」系统性偏低。Requirement 4.2 明确要求净额口径。
 * 2. **一律取叶子期末口径，不取 `trial_balance` 标量** —— `K3.tb_amount` 源自
 *    `trial_balance` 的未审数，平台已实测该表存在**父子双算**（H2/H8/F1/F3/F4 五处
 *    实测正好是叶子和的 2 倍）；`other_payable_2241_closing` 是 `aggregate_leaves`
 *    的叶子期末合计（负债取绝对值），是安全口径。
 * 3. K1 的 `adjudication_prefill` 在「全零」或「已有持久化审定数」时返回 `{}` ⇒
 *    取不到时**返回 `null`（本项目无此科目/未编制）而不是 0**，与 Requirement 4.4 一致。
 *
 * ─── 🔴 已登记的口径缺口（溯源必须让审计师看见，不静默）────────────────────────
 * **2026-08-12 更新**：`K_CYCLE_SPECS['K3']` 的 row_code 已由 `BS-053`/`BS-075`
 * （两者 formula 均 NULL；BS-053 实为其他流动负债、BS-075 在 listed 侧竟是股本）
 * 改正为 **`BS-050`**，溯源失真已消除 —— 但**账面金额可能偏小的缺口依然成立**，
 * 理由变了：`BS-050` 的 standalone 变体是 `TB('2241')+TB('2231')`，而 `2231`
 * 在后端按 `extra_standard_codes` 声明，`report_line_accounts` 会把它**从 `gross`
 * 里摘出去单列 `extra`**（源码实证：附加科目不参与原值口径）⇒ K3 下发的
 * `other_payable_2241_closing` 只含 2241 族叶子，**不含 2231 应付利息**。
 * 故 `knownGap` 提示保留（只更新理由），修复 = 让 K0 账面金额补加 extra 段，
 * 归 K 循环侧后续 spec；本模块只如实登记，不静默。
 *
 * ─── 🔴🔴 HTTP 客户端选型（F0 那轮的 P0，照抄结论）────────────────────────────
 * 必须用 `@/services/apiProxy` 的 `api`（**直接返回业务数据**），
 * 不能用 `@/utils/http`（返回 `AxiosResponse`，业务数据在 `.data`）。
 * 写错时响应体在 TS 里是 `any` ⇒ `get_diagnostics` / vitest / Vite 200 全绿，
 * **只有浏览器能发现**（表现为账面金额全部静默取空、比例行恒「-」）。
 *
 * 🔴 **禁并行请求同一 URL** —— `utils/http` 的去重键是
 * `method:url:JSON.stringify(params)`，命中即 `abort()` **先发的那个**。
 * 本模块两次请求的 `wp_code` 不同（K1 / K3）⇒ params 不同 ⇒ 键不同 ⇒ 安全；
 * 将来若新增同 wp_code 的第二次取数，必须合并成一次请求。
 */

import { api } from '@/services/apiProxy'
import {
  K0_MATRIX_CATEGORIES,
  K0_CATEGORY_NAMES,
  k0MatrixOverrideItemId,
  type K0CategoryName,
} from './k0MatrixSpec'
import type { K0MetricKey } from './k0SummaryMatrix'

/** 手工覆盖 item_id 前缀（与 `k0MatrixSpec.k0MatrixOverrideItemId` 同源） */
export const K0_MATRIX_KEY_PREFIX = 'K0-1-matrix'

/** 手工覆盖键（转发真源，避免第二处拼串） */
export function matrixOverrideItemId(category: string, metric: K0MetricKey): string {
  return k0MatrixOverrideItemId(category, metric)
}

/** 账面金额的手工覆盖键（矩阵 8 指标里唯一可覆盖的一行） */
export function bookAmountOverrideItemId(category: string): string {
  return matrixOverrideItemId(category, 'book_amount')
}

// ─── 逐品种的取数口径声明（键名各不相同，必须逐个声明，禁统一假设） ─────────────

/** 一条取数尝试：从某 sheet 的 `html_data` 里挑一个数 */
interface PickAttempt {
  /** 口径名（写进 `resolvedBy`，供溯源展示 —— 审计 UI 必须能追溯取的是哪个口径） */
  caliber: string
  pick: (hd: Record<string, any>) => unknown
}

export interface K0BookSourceSpec {
  category: K0CategoryName
  /** 提供账面金额的底稿 wp_code */
  wpCode: 'K1' | 'K3'
  /** 报表行（溯源展示；**按 row_code 精确匹配**，不按 row_name） */
  reportRowCode: string
  /** 按优先级尝试的取数口径 */
  attempts: readonly PickAttempt[]
  /** 已登记的口径缺口（非空时溯源必须显示） */
  knownGap?: string
}

const num = (v: unknown): number | null => {
  if (v === null || v === undefined || v === '') return null
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : null
}

export const K0_BOOK_SOURCE_SPECS: readonly K0BookSourceSpec[] = Object.freeze([
  Object.freeze({
    category: '其他应收款' as K0CategoryName,
    wpCode: 'K1' as const,
    reportRowCode: 'BS-009',
    attempts: Object.freeze([
      {
        // 首选：BS-009 公式符号加权净额（含 −1231-03 备抵、+1131 应收股利）
        caliber: "K1 报表核对数 report_total（BS-009 净额：TB('1221')−TB('1231-03')+TB('1131')）",
        pick: (hd) => hd?.adjudication_prefill?.fs_reconciliation?.report_total,
      },
      {
        // 退化：叶子期末原值 − 叶子期末备抵（**不含**应收股利/应收利息）
        caliber: 'K1 叶子期末净额（原值 − 坏账准备；不含应收股利/应收利息）',
        pick: (hd) => {
          const gross = num(hd?.tb_values?.receivable_unadjusted_closing)
          if (gross === null) return null
          const prov = num(hd?.tb_values?.bad_debt_unadjusted_closing) ?? 0
          return gross - prov
        },
      },
    ]) as readonly PickAttempt[],
  }),
  Object.freeze({
    category: '其他应付款' as K0CategoryName,
    wpCode: 'K3' as const,
    reportRowCode: 'BS-050',
    attempts: Object.freeze([
      {
        // 首选：叶子期末合计（负债取绝对值）
        caliber: 'K3 叶子期末合计 other_payable_2241_closing（负债口径取绝对值）',
        pick: (hd) => hd?.tb_values?.other_payable_2241_closing,
      },
      {
        // 退化：trial_balance 未审数（⚠ 该表存在父子双算的平台级已知问题）
        caliber: 'K3 试算平衡表未审数 tb_amount（⚠ trial_balance 口径，存在父子双算风险）',
        pick: (hd) => hd?.tb_amount,
      },
    ]) as readonly PickAttempt[],
    knownGap:
      "K3 账面金额为 **2241 口径**：BS-050 的 standalone 公式是 TB('2241')+TB('2231')，" +
      "而 2231 应付利息在后端按 extra_standard_codes **单列、不并入原值口径**" +
      "（`report_line_accounts` 将 extra 从 gross 摘出）→ 本行可能少算 2231，" +
      "请与 K3-1 审定表及附注「应付利息并入其他应付款列报」（财会[2018]15 号）核对",
  }),
]) as readonly K0BookSourceSpec[]

// import 期交叉锁死：声明表必须与矩阵品种一一对应（多一个/少一个都打红）
{
  const declared = K0_BOOK_SOURCE_SPECS.map((s) => s.category).join('|')
  const expected = K0_CATEGORY_NAMES.join('|')
  if (declared !== expected) {
    throw new Error(`[k0MatrixDataSources] 取数声明与矩阵品种不一致：${declared} != ${expected}`)
  }
  for (const s of K0_BOOK_SOURCE_SPECS) {
    const cat = K0_MATRIX_CATEGORIES.find((c) => c.category === s.category)
    if (!cat) continue
    if (cat.reportRowCode !== s.reportRowCode) {
      throw new Error(
        `[k0MatrixDataSources] ${s.category} 的 reportRowCode 与 k0MatrixSpec 分叉：` +
          `${s.reportRowCode} != ${cat.reportRowCode}`,
      )
    }
    if (cat.bookAmountFrom !== s.wpCode) {
      throw new Error(
        `[k0MatrixDataSources] ${s.category} 的 bookAmountFrom 与 k0MatrixSpec 分叉：` +
          `${s.wpCode} != ${cat.bookAmountFrom}`,
      )
    }
  }
}

// ─── 三态视图 ────────────────────────────────────────────────────────────────

/** 账面金额取数三态（`not_fetched` 与 `absent` 必须可区分，Requirement 4.4） */
export type K0BookAmountState = 'not_fetched' | 'absent' | 'value'

/** 三态文案（UI 全中文化；三者互不相同是守卫的断言点） */
export const K0_BOOK_STATE_TEXT: Readonly<Record<K0BookAmountState, string>> = Object.freeze({
  not_fetched: '未取数（可手填）',
  absent: '本项目无此科目或未编制该审定表',
  value: '',
})

export interface K0BookAmountView {
  category: string
  state: K0BookAmountState
  /** `state==='value'` 时为数值；否则 `null`（绝不用 0 冒充） */
  value: number | null
  /** 实际命中的取数口径（溯源可追溯性；未命中为 `null`） */
  resolvedBy: string | null
  /** 报表行（溯源展示） */
  reportRowCode: string
  /** 来源底稿 wp_code */
  wpCode: string
  /** 已登记的口径缺口（非空必须渲染） */
  knownGap?: string
  /** UI 文案（`state==='value'` 时为空串） */
  text: string
}

export interface K0MatrixDiagnostics {
  /**
   * 🔴 必须有渲染出口 —— F0 那轮的教训：`_silent` 取数的 `errors` 只收集不渲染，
   * 让「链路失效」与「本项目确实没这科目」不可区分，掩盖了一个 http 客户端错配 P0。
   */
  errors: string[]
  /** 成功取到的品种 */
  resolved: string[]
  /** 未取到的品种 */
  missing: string[]
  /** 已登记的口径缺口提示（必须可见） */
  knownGaps: string[]
}

export interface K0MatrixSources {
  /**
   * 账面金额映射。
   *
   * 🔴 三态语义：
   * - **整个字段为 `undefined`** = 取数链路未跑（缺 projectId / 请求全失败）
   * - 键存在值为 `null`         = 该品种取不到（本项目无此科目 / 未编制审定表）
   * - 键存在值为数字            = 取到（可能是 0，即科目存在且余额为 0）
   *
   * 调用方**禁写 `?? {}` 兜底** —— 那会把第一种变成第二种，让全部品种显示「无此科目」。
   */
  bookAmounts: Record<string, number | null> | undefined
  views: K0BookAmountView[]
  diagnostics: K0MatrixDiagnostics
}

// ─── 取数 ────────────────────────────────────────────────────────────────────

/** 从 render-config 响应体里逐 sheet 试取（render 对每个 sheet 注入同一份 html_data 键） */
function pickFromConfig(cfg: any, attempts: readonly PickAttempt[]): { value: number | null; caliber: string | null } {
  const sheets = cfg?.sheets ?? []
  for (const attempt of attempts) {
    for (const sheet of sheets) {
      const hd = sheet?.html_data ?? sheet?.htmlData
      if (!hd || typeof hd !== 'object') continue
      const v = num(attempt.pick(hd as Record<string, any>))
      if (v !== null) return { value: v, caliber: attempt.caliber }
    }
  }
  return { value: null, caliber: null }
}

/**
 * 拉某底稿的 render-config 并按声明的口径链取账面金额。
 *
 * 🔴 `api.get` 直接返回业务数据（拦截器已剥 `{code,message,data}` 信封）；
 * 写成 `@/utils/http` 的 `http.get` 就必须再 `.data`，否则恒 `undefined`。
 */
async function fetchBookAmount(
  projectId: string,
  spec: K0BookSourceSpec,
): Promise<{ value: number | null; caliber: string | null }> {
  const idRes = await api.get<{ wp_id?: string }>('/api/custom-query/wp-id-by-code', {
    params: { project_id: projectId, wp_code: spec.wpCode },
    _silent: true,
  } as any)
  const wpId = idRes?.wp_id
  if (!wpId) return { value: null, caliber: null }

  const cfg = await api.get<any>(`/api/workpapers/${wpId}/render-config`, {
    _silent: true,
  } as any)
  return pickFromConfig(cfg, spec.attempts)
}

/**
 * 加载矩阵账面金额（K1 / K3 并行；两者 wp_code 不同故不触发请求去重 abort）。
 *
 * @param projectId 项目 ID；缺失时返回 `bookAmounts: undefined`（未取数态）
 */
export async function loadK0MatrixSources(projectId: string | undefined): Promise<K0MatrixSources> {
  const diagnostics: K0MatrixDiagnostics = { errors: [], resolved: [], missing: [], knownGaps: [] }

  for (const spec of K0_BOOK_SOURCE_SPECS) {
    if (spec.knownGap) diagnostics.knownGaps.push(`${spec.category}：${spec.knownGap}`)
  }

  if (!projectId?.trim()) {
    diagnostics.errors.push('缺少 projectId，账面金额未取数（可手工填写）')
    diagnostics.missing.push(...K0_CATEGORY_NAMES)
    return { bookAmounts: undefined, views: buildK0BookAmountViews(undefined, {}), diagnostics }
  }

  const amounts: Record<string, number | null> = {}
  const calibers: Record<string, string | null> = {}

  const tasks = K0_BOOK_SOURCE_SPECS.map(async (spec) => {
    try {
      const { value, caliber } = await fetchBookAmount(projectId, spec)
      amounts[spec.category] = value
      calibers[spec.category] = caliber
      if (value === null) {
        diagnostics.missing.push(spec.category)
        diagnostics.errors.push(
          `${spec.category}：未从 ${spec.wpCode} 取到账面金额（报表行 ${spec.reportRowCode}）—— 可手工填写`,
        )
      } else {
        diagnostics.resolved.push(spec.category)
      }
    } catch (e: any) {
      // 🔴 请求失败不写入 amounts ⇒ 该品种保持「未取数」而不是「无此科目」
      diagnostics.missing.push(spec.category)
      diagnostics.errors.push(`${spec.category}(${spec.wpCode})：${e?.message || '取数失败'}`)
    }
  })
  await Promise.allSettled(tasks)

  return {
    bookAmounts: amounts,
    views: buildK0BookAmountViews(amounts, calibers),
    diagnostics,
  }
}

/** 逐品种解析三态视图（供矩阵单元格与溯源提示共用）。 */
export function buildK0BookAmountViews(
  amounts: Record<string, number | null> | undefined,
  calibers: Record<string, string | null> = {},
): K0BookAmountView[] {
  return K0_BOOK_SOURCE_SPECS.map((spec) => {
    const base = {
      category: spec.category as string,
      reportRowCode: spec.reportRowCode,
      wpCode: spec.wpCode as string,
      ...(spec.knownGap ? { knownGap: spec.knownGap } : {}),
    }
    if (!amounts || !(spec.category in amounts)) {
      return { ...base, state: 'not_fetched' as const, value: null, resolvedBy: null, text: K0_BOOK_STATE_TEXT.not_fetched }
    }
    const v = num(amounts[spec.category])
    if (v === null) {
      return { ...base, state: 'absent' as const, value: null, resolvedBy: null, text: K0_BOOK_STATE_TEXT.absent }
    }
    return { ...base, state: 'value' as const, value: v, resolvedBy: calibers[spec.category] ?? null, text: '' }
  })
}

/** 是否存在需要提示用户的诊断（供 UI 决定是否渲染提示条） */
export function hasK0MatrixDiagnostics(d: K0MatrixDiagnostics): boolean {
  return d.errors.length > 0 || d.knownGaps.length > 0
}

// ─── 手工覆盖的读取 ──────────────────────────────────────────────────────────

/**
 * 从 checklist responses 解析矩阵手工覆盖值。
 *
 * 只有「本期（期末）账面金额」行可手工覆盖（其余 7 项是派生值，源模板有公式）。
 * 兼容 `Map` 与普通对象两种载荷形态（平台既有两种都在用）。
 */
export function parseK0ManualOverrides(
  allResponses: Map<string, any> | Record<string, any> | undefined | null,
): Record<string, number> {
  const result: Record<string, number> = {}
  if (!allResponses) return result

  const readValue = (itemId: string): unknown => {
    if (allResponses instanceof Map) {
      const entry = allResponses.get(itemId)
      return entry?.value ?? entry?.remark ?? entry?.conclusion ?? entry
    }
    const entry = (allResponses as Record<string, any>)[itemId]
    return entry?.value ?? entry?.remark ?? entry?.conclusion ?? entry
  }

  for (const category of K0_CATEGORY_NAMES) {
    const itemId = bookAmountOverrideItemId(category)
    const v = num(readValue(itemId))
    if (v !== null) result[itemId] = v
  }
  return result
}
