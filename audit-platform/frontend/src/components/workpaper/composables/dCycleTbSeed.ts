/**
 * D 循环审定表「试算平衡表数」seed 回退 —— 消除 `project_context.tb_amount` 的 dead output。
 *
 * 🔴 **本模块解决的是一个实证缺陷，不是新功能**（2026-08-06 实证）
 *
 * 7 个 D render 都已经过 `seed_tb_amount_scalars` 把三口径标量写进
 * `html_data.project_context`::
 *
 *     tb_amount              # 审定口径（默认展示口径）
 *     tb_amount_unadjusted   # 未审数
 *     tb_amount_audited      # 审定数
 *
 * 而前端只有 D1（`tbSeedAmount`）与 D7（`tbSeedAmount: d7TbAmount`）读了它；
 * **D2 / D3 / D5 / D6 的 `trialBalanceAmount` 只读 `checklist_responses`**
 * （`D2-adj-tb-amount` / `D3-adj-trial-balance-amount` / `D5-1-tb-amount` /
 * `D6-1-tb-amount`）⇒ 用户未手工填过时恒为 0 ⇒ 「审定合计 − 试算平衡表数」
 * 显示成**整额假差异**，而 render 明明已经把数取回来了。
 *
 * 这与平台已登记的 F2/F3/F4 同款（「render 已算好但前端零消费」），且四层验证全绿。
 *
 * 🔴 **手工优先是硬约束**：`checklist_responses` 里有值就用它，seed 只在「从未手工
 * 保存过」时兜底。判据必须是 **原始 remark 是否为空串/undefined**，不能用
 * `parseNum(...) === 0` —— 那会让审计师**手工填的 0**（「本项目该科目余额确实为 0」
 * 是有意义的审计结论）被 seed 覆盖掉。
 *
 * 🔴 **`null` 与 `0` 必须可区分**：后端在「本项目无此科目」时给的是 `null`
 * （`write_zero_when_missing=False` 路径）或不写该键；只有确实取到 0 才是 `0`。
 * 故 {@link pickDTbSeed} 返回 `number | null`，禁写 `Number(null) === 0`。
 *
 * spec: .kiro/specs/d-cycle-four-table-extraction-and-disclosure-completion/
 *       Requirements 4.3, 4.4, 3.1, 3.7 / Task 16
 */
import { computed, type ComputedRef, type Ref } from 'vue'

/** 三口径键名（与后端 `seed_tb_amount_scalars` 逐字一致，改一侧必改另一侧） */
export const D_TB_KEY_DEFAULT = 'tb_amount'
export const D_TB_KEY_UNADJUSTED = 'tb_amount_unadjusted'
export const D_TB_KEY_AUDITED = 'tb_amount_audited'

/** 取数口径 */
export type DTbBasis = 'default' | 'unadjusted' | 'audited'

const BASIS_KEY: Readonly<Record<DTbBasis, string>> = Object.freeze({
  default: D_TB_KEY_DEFAULT,
  unadjusted: D_TB_KEY_UNADJUSTED,
  audited: D_TB_KEY_AUDITED,
})

function toFiniteNumber(v: unknown): number | null {
  if (v == null || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

/**
 * 从 render 下发的 `html_data` 取试算平衡表标量。
 *
 * 落点是 `html_data.project_context.tb_amount*`（7 个 D render 一致）；为稳健起见
 * 也兼容顶层（与 `tb_source_codes` 那套双落点约定同理，读不到不报错）。
 *
 * @returns `null` = render 未下发 / 该项目无此科目；数值 = 已取数（含真实的 0）
 */
export function pickDTbSeed(
  htmlData: unknown,
  basis: DTbBasis = 'default',
): number | null {
  if (!htmlData || typeof htmlData !== 'object') return null
  const key = BASIS_KEY[basis] || D_TB_KEY_DEFAULT
  const hd = htmlData as Record<string, any>

  const pc = hd.project_context
  if (pc && typeof pc === 'object') {
    const v = toFiniteNumber((pc as Record<string, any>)[key])
    if (v != null) return v
  }
  return toFiniteNumber(hd[key])
}

/**
 * 判定某 `checklist_responses` 条目是否**从未被手工保存过**。
 *
 * 🔴 判据是原始 `remark` 为空，**不是** 数值为 0 —— 审计师手工填的 0 是有效结论
 * （「该科目余额确实为 0」），把它当「未填」会让 seed 反复覆盖用户判断。
 */
export function isTbCellUnset(
  responses: Map<string, any> | null | undefined,
  itemId: string,
): boolean {
  const row = responses?.get(itemId)
  if (!row) return true
  const raw = row.remark
  return raw == null || String(raw).trim() === ''
}

export interface UseDTbSeedOptions {
  /** render 下发的 `html_data`（宿主经 `:html-data` 传下来） */
  htmlData: Ref<unknown>
  /** 该审定表持久化试算平衡表数的 `item_id`（各循环不同，见调用点） */
  itemId: string
  /** 全量 checklist 响应 */
  allResponses: Ref<Map<string, any>>
  /** 取数口径；默认 `default`（`tb_amount`，与既有 D1/D7 一致） */
  basis?: DTbBasis
}

export interface DTbSeedResult {
  /** 最终展示值：手工值优先，其次 render seed，都没有则 0（供 diff 计算） */
  amount: ComputedRef<number>
  /** render 下发的 seed（`null` = 未下发或本项目无此科目） */
  seed: ComputedRef<number | null>
  /** 当前展示值是否来自 render seed（供 UI 标注「自动取数」） */
  fromSeed: ComputedRef<boolean>
  /** 是否有手工值（手工优先的判据） */
  hasManual: ComputedRef<boolean>
}

/**
 * 试算平衡表数的「手工优先 + render seed 回退」只读视图。
 *
 * 只读 —— **不写库**。审计师点「确认审定」时各循环自己的 `publishAdjudicated`
 * 会把值落库（既有行为不动），本件只负责让未手工填时也能看到正确的核对数。
 */
export function useDTbSeed(opts: UseDTbSeedOptions): DTbSeedResult {
  const seed = computed(() => pickDTbSeed(opts.htmlData.value, opts.basis))
  const hasManual = computed(() => !isTbCellUnset(opts.allResponses.value, opts.itemId))

  const manualAmount = computed(() => {
    const row = opts.allResponses.value?.get(opts.itemId)
    return toFiniteNumber(row?.remark) ?? 0
  })

  const amount = computed(() => {
    if (hasManual.value) return manualAmount.value
    return seed.value ?? 0
  })

  const fromSeed = computed(() => !hasManual.value && seed.value != null)

  return { amount, seed, fromSeed, hasManual }
}

// ─────────────────────────────────────────────────────────────────────────────
// 纯函数形态（供 composable 内的 computed 直接调用）
//
// 🔴 本节是被 useD2/D3/D5/D6Adjudication 真实消费的入口。它们在 computed 里按
// 「原始 remark + seed」两个标量算最终值，不适合用 `useDTbSeed`（后者要 Ref 入参
// 且自带 computed，在 composable 内层再包一层反而绕）。
//
// 曾踩：这四个 composable 一度 import 了一个**不存在**的 `resolveTbAmountWithSeed`
// —— `get_diagnostics` / Vite transform / vitest 四层全绿（响应体在 TS 里是 any、
// 该符号只在运行时求值时才炸），只有本文件的守卫按「导出名真实存在」断言才抓到。
// 与平台已登记的「`fmtAmount` 是 store 成员不是模块导出」同源。
// ─────────────────────────────────────────────────────────────────────────────

/** 手工值是否已录入（判据 = 原始 remark 非空；手工填的 `0` 算已录入） */
export function hasManualTbAmount(rawRemark: unknown): boolean {
  return !(rawRemark == null || String(rawRemark).trim() === '')
}

/**
 * 解析手工录入的金额文本（容忍千分符与会计式括号负数）。
 *
 * @returns `null` = 未录入或非法（调用方据此回退 seed），数值 = 已录入（含 `0`）
 */
export function parseManualTbAmount(rawRemark: unknown): number | null {
  if (!hasManualTbAmount(rawRemark)) return null
  let s = String(rawRemark).trim().replace(/,/g, '')
  let sign = 1
  if (/^\((.*)\)$/.test(s)) {
    sign = -1
    s = s.replace(/^\((.*)\)$/, '$1')
  }
  const n = Number(s)
  return Number.isFinite(n) ? sign * n : null
}

/**
 * 试算平衡表数 = 手工值优先，其次 render seed，两者都无则 `0`。
 *
 * 返回 `0` 而非 `null` 是有意的 —— 调用方都是「审定合计 − 试算平衡表数」这类
 * 数值列，`null` 会让差异变 `NaN`。「本项目无此科目」由溯源面板的三态 tag 表达，
 * 不靠这里的返回值表达。
 *
 * @param rawRemark 该 `item_id` 在 `checklist_responses` 里的原始 `remark`
 * @param seed      render 下发的 `project_context.tb_amount*`（`null` = 未下发）
 */
export function resolveTbAmountWithSeed(
  rawRemark: unknown,
  seed: number | null | undefined,
): number {
  const manual = parseManualTbAmount(rawRemark)
  if (manual != null) return manual
  const n = seed == null ? null : Number(seed)
  return n != null && Number.isFinite(n) ? n : 0
}

/** 当前展示值是否来自 render seed（供 UI 标注「自动取数」） */
export function isTbSeedFallbackActive(
  rawRemark: unknown,
  seed: number | null | undefined,
): boolean {
  if (hasManualTbAmount(rawRemark) && parseManualTbAmount(rawRemark) != null) return false
  const n = seed == null ? null : Number(seed)
  return n != null && Number.isFinite(n)
}
