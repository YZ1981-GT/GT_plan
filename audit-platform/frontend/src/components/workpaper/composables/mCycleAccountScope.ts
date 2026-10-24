/**
 * M 类循环（M1~M10，股东权益）的科目口径单一来源 + `tb_source_codes` 提取器。
 *
 * ## 科目码（试算表 `standard_account_code` 口径）
 *
 * 与后端 `backend/app/services/four_table/m_cycle_specs.py` 的 `M_CYCLE_SPECS` 兜底码逐项一致
 * （守卫 `__tests__/mCycleAccountCodes.spec.ts` 解析后端源码比对）。
 *
 * 🔴 2026-10-24 前各组合函数 / 页签写死的码整体错位：M3 写 4002（资本公积）、M7 写 4201（库存股）、
 * M8 写 4104（利润分配）、M9 写 4103（本年利润）、M10 写 4003（其他综合收益）。审定数发布按
 * `standard_account_code` 精确匹配、不校验归属，于是 M3 发布会覆盖资本公积的试算表行、M8 覆盖利润分配……
 * （spec formula-fetch-followup-defect-closure R1.4）。M 循环组合函数与页签里不再写科目码字面量，一律取本表。
 *
 * M8 一般风险准备没有标准科目（各项目科目表都没有该科目，后端不给兜底码）⇒ 码为空：只认 render 下发的
 * 语义定位结果（`tb_source_codes.gross_standard`），定位不到就不能发布到试算表、不带入调整分录。
 *
 * ## `tb_source_codes`
 *
 * 从 render-config 返回的 `htmlData` 中提取，供 provide/inject 注入给子组件。
 *
 * spec: voucher-attach-account-mapping-closure（批次 6，任务 19）
 */
import { computed, hasInjectionContext, inject, unref, type ComputedRef, type Ref } from 'vue'
import type { TbSourceCodes } from './shared/tbSourceCodes'

export type MCycleWpCode = 'M1' | 'M2' | 'M3' | 'M4' | 'M5' | 'M6' | 'M7' | 'M8' | 'M9' | 'M10'

export interface MCycleAccount {
  /** 标准科目码；空串 = 没有标准科目（M8） */
  readonly code: string
  /** 科目名 —— 与后端语义槽 `label` 逐字一致（`mAccountCodeOf` 据此认定溯源归属） */
  readonly name: string
  /** 界面展示名（缺省 = name） */
  readonly display?: string
}

export const M_CYCLE_ACCOUNT: Readonly<Record<MCycleWpCode, MCycleAccount>> = Object.freeze({
  M1: { code: '2232', name: '应付股利' },
  M2: { code: '4001', name: '实收资本', display: '实收资本/股本' },
  M3: { code: '4201', name: '库存股' },
  M4: { code: '4002', name: '资本公积' },
  M5: { code: '4101', name: '盈余公积' },
  M6: { code: '4104', name: '利润分配', display: '未分配利润' },
  M7: { code: '4301', name: '专项储备' },
  M8: { code: '', name: '一般风险准备' },
  M9: { code: '4003', name: '其他综合收益' },
  M10: { code: '4401', name: '其他权益工具' },
})

/**
 * 溯源是否属于本循环：语义解析结果的主槽 `slots.gross.label` 必须是本循环科目名。
 *
 * 🔴 `tbSourceCodes` 是全平台共用的 provide 键 —— M 页签被别的底稿嵌入时注入到的可能是宿主循环的溯源
 * （例如 G8 的「其他权益工具投资」），拿它的 `gross_standard` 发布会写到别的科目。不认归属一律不用。
 */
export function isOwnMSource(wp: MCycleWpCode, src?: TbSourceCodes | null): src is TbSourceCodes {
  return !!src && src.slots?.gross?.label === M_CYCLE_ACCOUNT[wp].name
}

/** 本循环溯源里的标准码（去重、去空；溯源不属于本循环时为空） */
function ownStandardCodes(wp: MCycleWpCode, src?: TbSourceCodes | null): string[] {
  if (!isOwnMSource(wp, src)) return []
  const codes = (src.gross_standard || []).map((c) => String(c ?? '').trim()).filter(Boolean)
  return [...new Set(codes)]
}

/**
 * 运行态科目码：render 下发的本循环语义定位结果（`gross_standard` 第一个）优先，否则本表兜底码。
 * M8 定位不到时返回空串 —— 调用方据此不发布、不带入（不要拿别的科目顶替）。
 */
export function mAccountCodeOf(wp: MCycleWpCode, src?: TbSourceCodes | null): string {
  return (ownStandardCodes(wp, src)[0] || M_CYCLE_ACCOUNT[wp].code).trim()
}

/**
 * 审定数不能发布到试算表的原因（中文整句）；可以发布时返回空串。
 *
 * 只有没有统一标准码的循环（M8）会拦：定位不到 / 定位到多个标准码都不发布 ——
 * 发布按 `standard_account_code` 精确写行，写错码会覆盖别的科目，写一个码会漏掉其余码。
 */
export function mPublishBlockReason(wp: MCycleWpCode, src?: TbSourceCodes | null): string {
  const { name } = M_CYCLE_ACCOUNT[wp]
  const own = ownStandardCodes(wp, src)
  if (own.length > 1) {
    return `本项目「${name}」对应多个标准科目（${own.join('、')}），无法确定审定数发布到哪一个；请先在科目映射中归并后再发布。`
  }
  if (mAccountCodeOf(wp, src)) return ''
  if (!isOwnMSource(wp, src)) {
    return `未取到本底稿「${name}」的科目定位结果，审定数不能发布到试算表；请刷新页面后重试。`
  }
  if (src.chart_available === false) {
    return `本项目科目表未导入，定位不到「${name}」科目，审定数不能发布到试算表。`
  }
  return `本项目科目表中没有「${name}」科目，审定数不能发布到试算表（不会用其他科目代替）。`
}

/**
 * 其他综合收益（M9 口径）—— G8 / G9 / G12 / G14 调整分录的 OCI 对方科目共用。
 *
 * 🔴 2026-10-24 前这四处写的是 4002（资本公积）/ 4104（利润分配）：手工公允变动分录组、
 * 从核对表生成的 AJE 会把 OCI 记到资本公积 / 利润分配，按前缀认领中央调整时也认错科目。
 */
export const OCI_ACCOUNT_CODE = M_CYCLE_ACCOUNT.M9.code

/** 科目展示名：「库存股(4201)」；没有科目码时「一般风险准备（本项目无此科目）」 */
export function mAccountLabel(wp: MCycleWpCode, code: string = M_CYCLE_ACCOUNT[wp].code): string {
  const { name, display } = M_CYCLE_ACCOUNT[wp]
  const label = display || name
  return code ? `${label}(${code})` : `${label}（本项目无此科目）`
}

/**
 * 组合函数取 render 溯源：显式传入优先；在组件 setup 内调用时取主入口 provide 的 `tbSourceCodes`
 * （GtM{n} provide 的是 computed）；单测直接调用组合函数时没有注入上下文 ⇒ null。
 */
export function useMTbSource(
  explicit?: Ref<TbSourceCodes | null | undefined> | null,
): ComputedRef<TbSourceCodes | null> {
  if (explicit) return computed(() => explicit.value ?? null)
  if (!hasInjectionContext()) return computed(() => null)
  const injected = inject<Ref<TbSourceCodes | null> | TbSourceCodes | null>('tbSourceCodes', null)
  return computed(() => (unref(injected) as TbSourceCodes | null) ?? null)
}

/**
 * 从 htmlData 提取 `tb_source_codes`（与 D/E/F/G/H/I/J/K 循环同构）。
 *
 * 顶层 `htmlData.tb_source_codes` 优先；兼容 `htmlData.project_context.tb_source_codes`。
 * 两处都读、不做假设，返回 null 时调用方退到兜底码。
 */
export function pickMTbSourceCodes(htmlData: unknown): TbSourceCodes | null {
  if (!htmlData || typeof htmlData !== 'object') return null
  const hd = htmlData as Record<string, any>
  const fromTop = hd.tb_source_codes
  if (fromTop && typeof fromTop === 'object') return fromTop as TbSourceCodes
  const pc = hd.project_context
  if (pc && typeof pc === 'object') {
    const fromPc = (pc as Record<string, any>).tb_source_codes
    if (fromPc && typeof fromPc === 'object') return fromPc as TbSourceCodes
  }
  return null
}
