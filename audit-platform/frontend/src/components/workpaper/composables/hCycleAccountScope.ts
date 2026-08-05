/**
 * H 类循环科目真源工厂（零 Vue 依赖纯函数）。
 *
 * 10 个循环形态统一：语义槽声明 + 兜底码 + 运行态取 `tb_source_codes`。
 * 各循环只需导入工厂并声明自己的常量即可。
 *
 * 🔴 运行态一律取 render 下发的 `tb_source_codes`，常量只作兜底与展示。
 * 🔴 `writebackTB` 目标必须走 scope（H8 曾往 `1901` 写审定数污染 K2）。
 *
 * spec: .kiro/specs/h-cycle-four-table-extraction-and-account-mapping/
 */
import type { TbSourceCodes, TbSemanticSlot } from './shared/tbSourceCodes'

/** 单个 H 循环的科目声明 */
export interface HCycleAccountDef {
  /** 循环标识（如 'H1'） */
  cycle: string
  /** 报表行次（如 'BS-028'），H5 为 null（无 BS 行） */
  reportRowCode: string | null
  /** 各语义槽的兜底码（key = slot key，value = 兜底标准码列表） */
  slotFallbacks: Record<string, readonly string[]>
  /** gross 槽的兜底标准码（writebackTB / 查询用） */
  grossFallback: string
  /** 旧错误码（守卫用：源码不得出现这些字面量作科目码） */
  wrongLegacyCodes?: readonly string[]
}

/** 运行时 scope（由工厂生成） */
export interface HCycleScope {
  def: HCycleAccountDef
  /** 运行态取某槽的科目码列表（溯源优先，回退兜底） */
  slotCodes(src: TbSourceCodes | null | undefined, slotKey: string): string[]
  /** 取 gross 槽首个码（writebackTB / 请求参数用） */
  grossCode(src?: TbSourceCodes | null): string
  /** 本项目是否确实没有 gross 科目（`found=false`） */
  isGrossAbsent(src?: TbSourceCodes | null): boolean
  /** 取某槽的解析详情 */
  slot(src: TbSourceCodes | null | undefined, slotKey: string): TbSemanticSlot | undefined
}

/** 工厂函数 */
export function createHCycleScope(def: HCycleAccountDef): HCycleScope {
  return {
    def,
    slotCodes(src, slotKey) {
      const slotData = src?.slots?.[slotKey]
      if (slotData?.codes?.length) return [...slotData.codes]
      // 回退兜底码
      const fb = def.slotFallbacks[slotKey]
      return fb ? [...fb] : []
    },
    grossCode(src) {
      const codes = this.slotCodes(src, 'gross')
      return codes[0] || def.grossFallback
    },
    isGrossAbsent(src) {
      if (!src?.slots) return false // render 未下发 ≠ 无此科目
      const gross = src.slots['gross']
      return gross?.found === false
    },
    slot(src, slotKey) {
      return src?.slots?.[slotKey]
    },
  }
}

// ─── 各循环声明 ──────────────────────────────────────────────────────────────

export const H1_ACCOUNT_DEF: HCycleAccountDef = {
  cycle: 'H1',
  reportRowCode: 'BS-028',
  slotFallbacks: { gross: ['1601'], accum_dep: ['1602'], impairment: ['1603'] },
  grossFallback: '1601',
}

export const H2_ACCOUNT_DEF: HCycleAccountDef = {
  cycle: 'H2',
  reportRowCode: 'BS-029',
  slotFallbacks: { gross: ['1604'], eng_mat: ['1605'], impairment: [] },
  grossFallback: '1604',
}

export const H3_ACCOUNT_DEF: HCycleAccountDef = {
  cycle: 'H3',
  reportRowCode: 'BS-027',
  slotFallbacks: { gross: ['1521'], accum_dep: ['1525'], accum_amort: ['1526'], impairment: ['1527'] },
  grossFallback: '1521',
  wrongLegacyCodes: ['1503', '1504'],
}

export const H4_ACCOUNT_DEF: HCycleAccountDef = {
  cycle: 'H4',
  reportRowCode: 'BS-029',
  slotFallbacks: { gross: ['1605'], cip: ['1604'] },
  grossFallback: '1605',
}

export const H5_ACCOUNT_DEF: HCycleAccountDef = {
  cycle: 'H5',
  reportRowCode: null, // 油气资产无 BS 行
  slotFallbacks: { gross: ['1631'], accum_depletion: ['1632'], impairment: [] },
  grossFallback: '1631',
  wrongLegacyCodes: ['1611'],
}

export const H6_ACCOUNT_DEF: HCycleAccountDef = {
  cycle: 'H6',
  reportRowCode: 'BS-028',
  slotFallbacks: { gross: ['1606'] },
  grossFallback: '1606',
}

export const H7_ACCOUNT_DEF: HCycleAccountDef = {
  cycle: 'H7',
  reportRowCode: 'BS-030',
  slotFallbacks: { gross: ['1621'], accum_dep: ['1622'], impairment: [] },
  grossFallback: '1621',
}

export const H8_ACCOUNT_DEF: HCycleAccountDef = {
  cycle: 'H8',
  reportRowCode: 'BS-031',
  slotFallbacks: { gross: ['1641'], accum_dep: ['1642'], impairment: ['1643'] },
  grossFallback: '1641',
  wrongLegacyCodes: ['1901', '190101'],
}

export const H9_ACCOUNT_DEF: HCycleAccountDef = {
  cycle: 'H9',
  reportRowCode: 'BS-063',
  slotFallbacks: { gross: ['2601'], unearned_finance: ['2602'] },
  grossFallback: '2601',
  wrongLegacyCodes: ['2205'],
}

export const H10_ACCOUNT_DEF: HCycleAccountDef = {
  cycle: 'H10',
  reportRowCode: 'IS-018',
  slotFallbacks: { gross: ['6115'] },
  grossFallback: '6115',
}

// ─── 预构建 scope 实例 ──────────────────────────────────────────────────────

export const h1Scope = createHCycleScope(H1_ACCOUNT_DEF)
export const h2Scope = createHCycleScope(H2_ACCOUNT_DEF)
export const h3Scope = createHCycleScope(H3_ACCOUNT_DEF)
export const h4Scope = createHCycleScope(H4_ACCOUNT_DEF)
export const h5Scope = createHCycleScope(H5_ACCOUNT_DEF)
export const h6Scope = createHCycleScope(H6_ACCOUNT_DEF)
export const h7Scope = createHCycleScope(H7_ACCOUNT_DEF)
export const h8Scope = createHCycleScope(H8_ACCOUNT_DEF)
export const h9Scope = createHCycleScope(H9_ACCOUNT_DEF)
export const h10Scope = createHCycleScope(H10_ACCOUNT_DEF)

/** 全量注册表（守卫按循环标识索引） */
export const H_CYCLE_SCOPES: Record<string, HCycleScope> = {
  H1: h1Scope,
  H2: h2Scope,
  H3: h3Scope,
  H4: h4Scope,
  H5: h5Scope,
  H6: h6Scope,
  H7: h7Scope,
  H8: h8Scope,
  H9: h9Scope,
  H10: h10Scope,
}
