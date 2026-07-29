/**
 * 附注模块 → 底稿「披露表」跳转：从 note 元数据/章节号推断 G7/G10/G13/G14 披露 sheet。
 * 不改附注表结构；仅导航。
 */

export const G7_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const G7_DISCLOSURE_SHEET_SOE = '附注披露信息（国企）'

// E1 货币资金 披露 sheet：底稿实际 tab 名为「附注披露信息(上市公司)」/「附注披露信息(国企)」（半角括号，
// 见 workpaper_sheet_classification）。此前误设为 '附注上市'/'附注国企'（不存在的 sheet 名）导致
// GtWpRenderer 精确匹配失败 → 回退到首个 sheet（底稿目录）。靠章节号（五、1/八、1）区分归属。
export const E1_DISCLOSURE_SHEET_LISTED = '附注披露信息(上市公司)'
export const E1_DISCLOSURE_SHEET_SOE = '附注披露信息(国企)'

// D1 应收票据 披露 sheet：底稿实际 tab 名为「附注披露信息（上市公司）」/「附注披露信息（国企）」
// （全角括号，见 workpaper_sheet_classification wp_code=D1）。靠章节号（五、4/八、4）区分归属。
export const D1_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const D1_DISCLOSURE_SHEET_SOE = '附注披露信息（国企）'

// D2 应收账款 披露 sheet：底稿实际 tab 名为「附注披露信息(上市公司)」/「附注披露信息(国企)」
// （半角括号，与 workpaper_sheet_classification wp_code=D2 一致）。靠章节号（五、5/八、5）区分归属。
export const D2_DISCLOSURE_SHEET_LISTED = '附注披露信息(上市公司)'
export const D2_DISCLOSURE_SHEET_SOE = '附注披露信息(国企)'

// D3~D7 披露 sheet：真实 tab 名逐字取自 workpaper_sheet_classification（半/全角括号各科目不一，
// 尤其 D6 上市为半角左+全角右混合，错一字符 GtWpRenderer ?sheet= 精确匹配失败会回退底稿目录）。
export const D3_DISCLOSURE_SHEET_LISTED = '附注披露信息(上市公司)'
export const D3_DISCLOSURE_SHEET_SOE = '附注披露信息(国企)'
export const D5_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const D5_DISCLOSURE_SHEET_SOE = '附注披露信息（国企）'
export const D6_DISCLOSURE_SHEET_LISTED = '附注披露信息(上市公司）'
export const D6_DISCLOSURE_SHEET_SOE = '附注披露信息（国企）'
export const D7_DISCLOSURE_SHEET_LISTED = '附注披露信息(上市公司)'
export const D7_DISCLOSURE_SHEET_SOE = '附注披露信息(国企)'
export const D4_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const D4_DISCLOSURE_SHEET_SOE = '附注披露信息（国企）'

// G1 交易性金融资产 / G10 交易性金融负债 披露 sheet：底稿实际 tab 名为
// 「附注披露信息（上市公司）」/「附注披露信息（国企）」（全角括号，见 workpaper_sheet_classification
// wp_code=G1/G10）。此前误设为 '附注上市'/'附注国企'（那是 OnlyOffice sheet-name 映射，非分类 tab 名）
// 导致 GtWpRenderer 的 ?sheet= 精确匹配失败 → 回退到首个 sheet（底稿目录）。靠章节号区分 G1/G10。
export const G1_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const G1_DISCLOSURE_SHEET_SOE = '附注披露信息（国企）'

export const G10_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const G10_DISCLOSURE_SHEET_SOE = '附注披露信息（国企）'

// J1 应付职工薪酬 披露 sheet：底稿实际 tab 名为「附注披露信息（上市公司）」/「附注披露信息（国有企业）」
// （全角括号，见 workpaper_sheet_classification wp_code=J1，与 D1 同款命名）。靠章节号区分 J1。
export const J1_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const J1_DISCLOSURE_SHEET_SOE = '附注披露信息（国有企业）'

// L1 短期借款 披露 sheet：底稿实际 tab 名为「附注披露信息核对（上市公司）」/「附注披露信息核对（国企）」
export const L1_DISCLOSURE_SHEET_LISTED = '附注披露信息核对（上市公司）'
export const L1_DISCLOSURE_SHEET_SOE = '附注披露信息核对（国企）'

export const L3_DISCLOSURE_SHEET_LISTED = '附注披露信息核对（上市公司）'
export const L3_DISCLOSURE_SHEET_SOE = '附注披露信息核对（国企）'

export const L5_DISCLOSURE_SHEET_LISTED = '附注披露信息核对（上市公司）'
export const L5_DISCLOSURE_SHEET_SOE = '附注披露信息核对（国企）'

export const L7_DISCLOSURE_SHEET_LISTED = '附注披露信息核对（上市公司）'
export const L7_DISCLOSURE_SHEET_SOE = '附注披露信息核对（国企）'

// M 循环权益类：披露 sheet 名 = 各科目底稿内附注tab真实名（与 L 循环同名）
export const M_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const M_DISCLOSURE_SHEET_SOE = '附注披露信息（国企）'

export const G13_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const G13_DISCLOSURE_SHEET_SOE = '附注披露信息（国企）'

export const G14_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const G14_DISCLOSURE_SHEET_SOE = '附注披露信息（国企）'

export const H1_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const H1_DISCLOSURE_SHEET_SOE = '附注披露信息（国有企业）'

export const H8_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const H8_DISCLOSURE_SHEET_SOE = '附注披露信息（国企）'

export const H9_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const H9_DISCLOSURE_SHEET_SOE = '附注披露信息（国企）'

export const H10_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const H10_DISCLOSURE_SHEET_SOE = '附注披露信息（国有企业）'

export const H5_DISCLOSURE_SHEET_LISTED = '' // 上市版无独立油气资产章节
export const H5_DISCLOSURE_SHEET_SOE = '附注披露信息（国有企业）'

export const I1_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const I1_DISCLOSURE_SHEET_SOE = '附注披露信息（国有企业）'

export const I5_DISCLOSURE_SHEET_LISTED = '附注披露（上市公司）'
export const I5_DISCLOSURE_SHEET_SOE = '附注披露（国有企业）'

export const K11_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const K11_DISCLOSURE_SHEET_SOE = '附注披露信息（国有企业）'

export const K13_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const K13_DISCLOSURE_SHEET_SOE = '附注披露信息（国有企业）'

// K2-K9 披露 sheet：底稿实际 tab 名(半角括号，workpaper_sheet_classification)
export const K2_DISCLOSURE_SHEET_LISTED = '附注披露信息(上市公司)'
export const K2_DISCLOSURE_SHEET_SOE = '附注披露信息(国企)'
export const K3_DISCLOSURE_SHEET_LISTED = '附注披露信息(上市公司)'
export const K3_DISCLOSURE_SHEET_SOE = '附注披露信息(国企)'
export const K4_DISCLOSURE_SHEET_LISTED = '附注披露信息(上市公司)'
export const K4_DISCLOSURE_SHEET_SOE = '附注披露信息(国企)'
export const K5_DISCLOSURE_SHEET_LISTED = '附注披露信息(上市公司)'
export const K5_DISCLOSURE_SHEET_SOE = '附注披露信息(国企)'
export const K6_DISCLOSURE_SHEET_LISTED = '附注披露信息(上市公司)'
export const K6_DISCLOSURE_SHEET_SOE = '附注披露信息(国企)'
export const K7_DISCLOSURE_SHEET_LISTED = '附注披露信息(上市公司)'
export const K7_DISCLOSURE_SHEET_SOE = '附注披露信息(国企)'
export const K8_DISCLOSURE_SHEET_LISTED = '附注披露信息(上市公司)'
export const K8_DISCLOSURE_SHEET_SOE = '附注披露信息(国企)'
export const K9_DISCLOSURE_SHEET_LISTED = '附注披露信息(上市公司)'
export const K9_DISCLOSURE_SHEET_SOE = '附注披露信息(国企)'

// 以下为「有底稿→附注 sync 但附注侧原无『跳转至披露表』入口」的 9 个专有章节科目。
// 真实 tab 名取自 workpaper_sheet_classification（各循环命名不统一：F1/K1 半角括号，
// H2 soe=国有企业，I2/I3/I4/I6 无『信息』二字，K1 listed 为半角左+全角右混合括号）。
export const F1_DISCLOSURE_SHEET_LISTED = '附注披露信息(上市公司)'
export const F1_DISCLOSURE_SHEET_SOE = '附注披露信息(国企)'

export const F2_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const F2_DISCLOSURE_SHEET_SOE = '附注披露信息（国企）'

export const G11_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const G11_DISCLOSURE_SHEET_SOE = '附注披露信息（国企）'

export const H2_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const H2_DISCLOSURE_SHEET_SOE = '附注披露信息（国有企业）'

export const I2_DISCLOSURE_SHEET_LISTED = '附注披露（上市公司）'
export const I2_DISCLOSURE_SHEET_SOE = '附注披露（国有企业）'

export const I3_DISCLOSURE_SHEET_LISTED = '附注披露（上市公司）'
export const I3_DISCLOSURE_SHEET_SOE = '附注披露（国有企业）'

export const I4_DISCLOSURE_SHEET_LISTED = '附注披露（上市公司）'
export const I4_DISCLOSURE_SHEET_SOE = '附注披露（国有企业）'

export const I6_DISCLOSURE_SHEET_LISTED = '附注披露（上市公司）'
export const I6_DISCLOSURE_SHEET_SOE = '附注披露（国有企业）'

// K1 其他应收款 listed tab 为半角左括号+全角右括号混合（见 workpaper_sheet_classification）。
export const K1_DISCLOSURE_SHEET_LISTED = '附注披露信息(上市公司）'
export const K1_DISCLOSURE_SHEET_SOE = '附注披露信息（国企）'

// N1 递延所得税资产（全角括号，实测 workpaper_sheet_classification wp_code=N1）。
// 该章节由 N1/N3 共用，正向跳转默认落 N1（spec n1-disclosure-note-linkage · Decision 2）；
// N3 若将来补披露表，可在此加 N3 常量与备选入口。
export const N1_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const N1_DISCLOSURE_SHEET_SOE = '附注披露信息（国企）'

export const N2_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const N2_DISCLOSURE_SHEET_SOE = '附注披露信息（国企）'

export const N4_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'

export const N5_DISCLOSURE_SHEET_SOE = '附注披露信息（国企）'

// F3 应付票据（五、36 / 八、36）。真实 tab 名取自 f3NoteSectionMap.F3_DISCLOSURE_SHEET_NAME。
export const F3_DISCLOSURE_SHEET_LISTED = '附注披露信息(上市公司)'
export const F3_DISCLOSURE_SHEET_SOE = '附注披露信息(国企)'

// G8 其他权益工具投资（五、19 / 八、19）。
export const G8_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const G8_DISCLOSURE_SHEET_SOE = '附注披露信息（国企）'

// G9 其他非流动金融资产（五、20 / 八、20）。
export const G9_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const G9_DISCLOSURE_SHEET_SOE = '附注披露信息（国企）'

// G12 套期净损益（五、70 / 八、71）。
export const G12_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const G12_DISCLOSURE_SHEET_SOE = '附注披露信息（国企）'

export interface NoteDisclosureJumpTarget {
  /** 底稿 sheet 名（传给 ?sheet=） */
  sheet: string
  /** 已知同步 wp_id（可空，空则走 ACNR 解析） */
  wpId: string | null
  /** listed | soe */
  variant: 'listed' | 'soe'
  /** 推断依据说明 */
  reason: string
  /** 底稿族代码（ACNR 回退解析） */
  wpCode?: 'D1' | 'D3' | 'D4' | 'D5' | 'D6' | 'D7' | 'E1' | 'F1' | 'F2' | 'F3' | 'G1' | 'G7' | 'G8' | 'G9' | 'G10' | 'G11' | 'G12' | 'G13' | 'G14' | 'H1' | 'H2' | 'H3' | 'H8' | 'H9' | 'H10' | 'I1' | 'I2' | 'I3' | 'I4' | 'I5' | 'I6' | 'J1' | 'K1' | 'K11' | 'K13' | 'L1' | 'N1' | 'N2' | 'N4' | 'N5'
}

function asRecord(raw: unknown): Record<string, unknown> | null {
  return raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : null
}

/**
 * 是否像 E1 货币资金相关附注节（五、1 / 八、1）。
 * 权威 note_template_variant_matrix.json · huo_bi_zi_jin：上市→五、1，国企→八、1。
 * 单字数字须**精确**匹配（禁 startsWith：'五、1' 会误伤 五、10~五、19，含 G7 的 五、18）。
 */
export function isE1MonetaryFundNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、1' || s === '八、1') return true
  if (s === '货币资金') return true
  return false
}

/**
 * 是否 J1 应付职工薪酬相关附注节（五、40 / 八、40）。
 * 权威 note_template_variant_matrix.json · ying_fu_zhi_gong_xin_chou。
 * 须**精确===**匹配（禁 startsWith：'五、4' 是应收票据 D1；'五、40x' 不存在但防御性排除）。
 */
export function isJ1EmployeeBenefitsNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、40' || s === '八、40') return true
  if (s.includes('应付职工薪酬')) return true
  return false
}

/**
 * 是否 L1 短期借款相关附注节（五、33 / 八、33）。
 * 权威 note_template_variant_matrix.json · duan_qi_jie_kuan。
 * 须**精确===**匹配（五、33≠五、3 衍生金融资产；八、33≠八、3）。
 */
export function isL1ShortTermLoanNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、33' || s === '八、33') return true
  if (s === '短期借款') return true
  return false
}

/**
 * 是否 L3 长期借款相关附注节（五、45 / 八、49）。
 * 权威 note_template_variant_matrix.json · chang_qi_jie_kuan。
 */
export function isL3LongTermLoanNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、45' || s === '八、49') return true
  if (s === '长期借款') return true
  return false
}

/**
 * 是否 L5 长期应付款相关附注节（五、48 / 八、53）。
 * 权威 note_template_variant_matrix.json · chang_qi_ying_fu_kuan。
 */
export function isL5LongTermPayableNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、48' || s === '八、53') return true
  if (s === '长期应付款') return true
  return false
}

/**
 * 是否 L7 其他非流动负债相关附注节（五、52 / 八、57）。
 * 权威 note_template_variant_matrix.json · qi_ta_fei_liu_dong_fu_zhai。
 */
export function isL7OtherNoncurrentLiabilityNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、52' || s === '八、57') return true
  if (s === '其他非流动负债') return true
  return false
}

// ─── M 循环（权益类）──────────────────────────────────────────────────────────

/** M2 实收资本（仅国企八、58） */
export function isM2PaidInCapitalNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  return s === '八、58' || s === '实收资本'
}
/** M3 库存股（仅上市五、56） */
export function isM3TreasuryStockNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  return s === '五、56' || s === '库存股'
}
/** M4 资本公积（五、55 / 八、60） */
export function isM4CapitalReserveNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  return s === '五、55' || s === '八、60' || s === '资本公积'
}
/** M5 盈余公积（五、59 / 八、62） */
export function isM5SurplusReserveNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  return s === '五、59' || s === '八、62' || s === '盈余公积'
}
/** M6 未分配利润（五、61 / 八、63） */
export function isM6UndistributedProfitNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  return s === '五、61' || s === '八、63' || s === '未分配利润'
}
/** M7 专项储备（五、58 / 八、61） */
export function isM7SpecialReserveNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  return s === '五、58' || s === '八、61' || s === '专项储备'
}
/** M9 其他综合收益（仅上市五、57） */
export function isM9OciNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  return s === '五、57' || s === '其他综合收益'
}
/** M10 其他权益工具（五、54 / 八、59） */
export function isM10OtherEquityInstrumentNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  return s === '五、54' || s === '八、59' || s === '其他权益工具'
}

/**
 * 是否像 N1 递延所得税资产相关附注节（五、30 / 八、31）。
 * 权威 note_template_variant_matrix.json · di_yan_suo_de_shui_zi_chan_he_di_yan_suo_de。
 * 须**精确**匹配（禁 startsWith：'五、3' 是衍生金融资产、'八、3' 亦然；
 * 反之 '五、30' 用 startsWith 会误吞将来的 五、300 类章节）。
 * 该章节 N1（资产）与 N3（负债）共用，跳转默认落 N1。
 */
export function isN1DeferredTaxNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、30' || s === '八、31') return true
  if (s === '递延所得税资产和递延所得税负债' || s === '递延所得税资产与递延所得税负债') return true
  return false
}

/**
 * 是否像 D1 应收票据相关附注节（五、4 / 八、4）。
 * 单字数字须**精确**匹配（禁 startsWith：'五、4' 会误伤 五、40~五、49）。
 * 关键词精确匹配"应收票据"（区别于"应收账款"/"应收款项融资"）。
 */
export function isD1NotesReceivableNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、4' || s === '八、4') return true
  if (s === '应收票据') return true
  return false
}

/**
 * 是否像 D2 应收账款相关附注节（五、5 / 八、5）。
 * 单字数字须**精确===**匹配（禁 startsWith：五、5 会误伤 五、50~五、59）。
 * 关键词精确匹配"应收账款"（区别于"应收票据"/"应收款项融资"）。
 */
export function isD2AccountsReceivableNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、5' || s === '八、5') return true
  if (s === '应收账款') return true
  return false
}

/**
 * 是否像 D3 预收款项相关附注节（五、38 / 八、38）。
 * 纯编号须**精确===**匹配（禁 startsWith：五、38 会误伤 五、380+；且区别于 五、39 合同负债）。
 */
export function isD3PrepaymentNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、38' || s === '八、38') return true
  if (s === '预收款项' || s === '预收账款') return true
  return false
}

/**
 * 是否像 D5 应收款项融资相关附注节（五、6 / 八、6）。
 * 单字数字须**精确===**匹配（禁 startsWith：五、6 会误伤 五、60~五、69）。
 */
export function isD5ReceivablesFinancingNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、6' || s === '八、6') return true
  if (s === '应收款项融资') return true
  return false
}

/**
 * 是否像 D6 合同资产相关附注节（五、10 / 八、11）。
 * 纯编号须**精确===**匹配（禁 startsWith：五、10 会误伤 五、100+；且区别于 五、1 货币资金）。
 */
export function isD6ContractAssetNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、10' || s === '八、11') return true
  if (s === '合同资产') return true
  return false
}

/**
 * 是否像 D7 合同负债相关附注节（五、39 / 八、39）。
 * 纯编号须**精确===**匹配（禁 startsWith；区别于 五、38 预收款项）。
 */
export function isD7ContractLiabilityNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、39' || s === '八、39') return true
  if (s === '合同负债') return true
  return false
}

/**
 * 是否像 D4 营业收入/营业成本相关附注节（五、62 / 八、64）。
 * 纯编号须**精确===**匹配；关键词兜底"营业收入"（损益类，区别于其它科目）。
 */
export function isD4RevenueNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、62' || s === '八、64') return true
  if (s === '营业收入和营业成本' || s === '营业收入、营业成本' || s === '营业收入与营业成本') return true
  return false
}

/** 是否像 G13 公允价值变动收益相关附注节 */
export function isG13FairValueNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '三、公允价值变动收益' || s.startsWith('三、公允价值变动')) return true
  if (s === '八、72' || s.startsWith('八、72')) return true
  return false
}

/** 是否像 G14 信用减值损失相关附注节 */
export function isG14CreditImpairmentNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '三、信用减值损失' || s.startsWith('三、信用减值')) return true
  if (s === '八、73' || s.startsWith('八、73')) return true
  return false
}

/**
 * 是否像 G1 交易性金融资产相关附注节（五、2 / 八、2）。
 * 单字数字须**精确**匹配（禁 startsWith：'五、2' 会误伤 五、20~五、29）。
 * 关键词"交易性金融资产"作兜底，并显式排除"交易性金融负债"（G10）。
 */
export function isG1TradingFinancialAssetNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、2' || s === '八、2') return true
  if (s.includes('交易性金融负债')) return false
  if (s.includes('交易性金融资产')) return true
  return false
}

/**
 * 是否像 衍生金融资产 相关附注节（五、3 / 八、3）。
 * 权威 note_template_variant_matrix.json · yan_sheng_jin_rong_zi_chan：上市→五、3，国企→八、3。
 * 衍生金融资产归属 G1 交易性金融资产底稿（含 G1-14 衍生工具核查 + 附注上市②衍生工具 /
 * 附注国企表2衍生金融资产），跳转目标与交易性金融资产同为 G1 披露 sheet。
 * 单字数字须**精确**匹配（禁 startsWith：'五、3' 会误伤 五、30~五、39）。
 * 关键词"衍生金融资产"兜底，并显式排除"衍生金融负债"（G10 五、35/八、35）。
 */
export function isDerivativeFinancialAssetNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、3' || s === '八、3') return true
  if (s.includes('衍生金融负债')) return false
  if (s.includes('衍生金融资产')) return true
  return false
}

/** 是否像 G10 交易性金融负债相关附注节 */
export function isG10TradingLiabilityNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、34' || s.startsWith('五、34')) return true
  if (s === '八、34' || s.startsWith('八、34')) return true
  if (s === '五、35' || s.startsWith('五、35')) return true
  if (s === '八、35' || s.startsWith('八、35')) return true
  return false
}

/** 是否像 G7 长期股权投资相关附注节 */
export function isG7EquityNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、18' || s.startsWith('五、18')) return true
  if (s === '八、18' || s.startsWith('八、18')) return true
  if (s === '七' || s.startsWith('七、') || s.startsWith('七 ')) return true
  return false
}

/**
 * 是否像 H1 固定资产相关附注节（listed 五、22 / soe 八、22，纯编号精确匹配）。
 * 注意「五、15」是其他债权投资，绝不可命中固定资产（曾误列，会把该章节跳到 H1 披露表）。
 */
export function isH1FixedAssetNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、22' || s === '八、22') return true
  if (s === '固定资产' || (s.includes('固定资产') && !s.includes('清理') && !s.includes('在建'))) return true
  return false
}

/**
 * 是否像 H3 投资性房地产相关附注节（五、21 / 八、22）。
 * 权威 note_template_variant_matrix.json · tou_zi_xing_fang_di_chan：上市→五、21，国企→八、22。
 * 单/双位数字须**精确===**匹配（五、21 禁 startsWith，防误伤五、210 类未来章节）。
 * 关键词"投资性房地产"兜底。
 */
export function isH3InvestmentPropertyNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、21' || s === '八、22') return true
  if (s === '投资性房地产' || (s.includes('投资性房地产') && !s.includes('累计折旧'))) return true
  return false
}

// H3 投资性房地产 披露 sheet：底稿实际 tab 名为「附注披露信息（上市公司）」/「附注披露信息（国有企业）」
// （全角括号，见 workpaper_sheet_classification wp_code=H3）。靠章节号（五、21/八、22）区分归属。
export const H3_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const H3_DISCLOSURE_SHEET_SOE = '附注披露信息（国有企业）'

/**
 * 是否像 H5 油气资产相关附注节（八、25 国企专属）。
 * 权威 note_template_variant_matrix.json · you_qi_zi_chan：soe→八、25，listed→null（上市无独立油气章节）。
 * 精确匹配 === 禁 startsWith（八、25 ≠ 八、2）。
 * 关键词"油气资产"兜底。
 */
export function isH5OilGasAssetNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '八、25') return true
  if (s === '油气资产' || (s.includes('油气资产') && !s.includes('折耗'))) return true
  return false
}

/** 是否像 H8 使用权资产相关附注节 */
export function isH8RouNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、25' || s.startsWith('五、25')) return true
  if (s === '八、26' || s.startsWith('八、26')) return true
  if (s === '三、使用权资产' || s.startsWith('三、使用权')) return true
  if (s === '四、使用权资产' || s.startsWith('四、使用权')) return true
  if (s === '使用权资产' || (s.includes('使用权资产') && !s.includes('改良'))) return true
  return false
}

/** 是否像 H9 租赁负债相关附注节 */
export function isH9LeaseLiabilityNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、47' || s.startsWith('五、47')) return true
  if (s === '八、52' || s.startsWith('八、52')) return true
  if (s === '租赁负债' || (s.includes('租赁负债') && !s.includes('使用权'))) return true
  return false
}

/** 是否像 H10 资产处置收益相关附注节 */
export function isH10AssetDisposalNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '三、资产处置收益' || s.startsWith('三、资产处置')) return true
  if (s === '八、75' || s.startsWith('八、75')) return true
  if (s === '资产处置收益' || s === '资产处置损益' || (s.includes('资产处置') && !s.includes('清理'))) return true
  return false
}

/** 是否像 I1 无形资产相关附注节 */
export function isI1IntangibleNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、26' || s.startsWith('五、26')) return true
  if (s === '八、27' || s.startsWith('八、27')) return true
  if (s === '三、无形资产' || s.startsWith('三、无形资产')) return true
  if (s === '四、无形资产' || s.startsWith('四、无形资产')) return true
  // 避免误伤「研发支出」等：仅精确/强匹配
  if (s === '无形资产') return true
  return false
}

/**
 * 是否像 K11 资产减值损失相关附注节（6701）。
 * 权威 note_template_variant_matrix.json · zi_chan_jian_zhi_sun_shi：
 *   上市 → 三、资产减值损失（损益表附注，listed 无 五/八 编号，靠 section_title 关键词）
 *   国企 → 八、74（国企报表项目附注）
 * 注：此前误用 五、73/五、75（五、73 实为「外币货币性项目」），已修正为关键词 + 八、74。
 */
export function isK11AssetImpairmentNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  // 标题关键词（"三、资产减值损失（损失以…）" / "加：资产减值损失" 等，不含"信用减值损失"）
  if (s.includes('资产减值损失')) return true
  if (s === '八、74' || s.startsWith('八、74')) return true
  return false
}

/**
 * 是否像 K13 营业外支出相关附注节（6711）。
 * 权威 zi_chan：上市 → 三、营业外支出；国企 → 八、77。
 * 关键词"营业外支出"（区别于 K12"营业外收入"6301）。
 */
export function isK13NonOperatingExpenseNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  // 精确排除"营业外收入"（K12），仅匹配"营业外支出"
  if (s.includes('营业外收入')) return false
  if (s.includes('营业外支出')) return true
  if (s === '八、77' || s.startsWith('八、77')) return true
  return false
}

// ─── K2-K9 章节谓词（精确编号匹配，禁 startsWith 避串科目）────────────────────
export function isK2OtherCurrentAssetNoteSection(s: string): boolean { return s === '五、13' || s === '八、14' }
export function isK3OtherPayableNoteSection(s: string): boolean { return s === '五、42' || s === '八、42' }
export function isK4OtherCurrentLiabilityNoteSection(s: string): boolean { return s === '五、44' || s === '八、48' }
export function isK5ProvisionsNoteSection(s: string): boolean { return s === '五、50' || s === '八、55' }
export function isK6HeldForSaleNoteSection(s: string): boolean { return s === '持有待售资产' || s === '八、12' }
export function isK7DeferredRevenueNoteSection(s: string): boolean { return s === '五、51' || s === '八、56' }
export function isK8SellingExpenseNoteSection(s: string): boolean { return s === '五、64' || s === '八、65' }
export function isK9AdminExpenseNoteSection(s: string): boolean { return s === '五、65' || s === '八、66' }
export function isK10OtherIncomeNoteSection(s: string): boolean { return s === '五、68' || s === '八、69' }

/** 是否像 I5 其他非流动资产相关附注节 */
export function isI5OtherNoncurrentNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、31' || s.startsWith('五、31')) return true
  if (s === '八、32' || s.startsWith('八、32')) return true
  if (s === '其他非流动资产' || s.includes('其他非流动资产')) return true
  return false
}

// ── 以下 9 个「有 sync 但原无跳转入口」的专有章节科目（章节号权威取自 DB note_section↔section_title
//    与各科目 NoteSectionMap.ts）。纯编号一律**精确**匹配（禁 startsWith：八、7≠八、70=G11，
//    五、8≠五、80+，八、9≠八、90+）。应收利息(G2)/应收股利(G3)/工程物资(H4)/固定资产清理(H6)
//    无专有章节（并入 K1 五、8 / 三、工程物资【不适用】 / H1 五、22），故不做独立跳转目标。 ──

/** F1 预付款项（五、7 / 八、7）。 */
export function isF1PrepaymentNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、7' || s === '八、7') return true
  if (s === '预付款项' || s === '预付账款') return true
  return false
}

/** F2 存货（五、9 / 八、10）。 */
export function isF2InventoryNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、9' || s === '八、10') return true
  if (s === '存货') return true
  return false
}

/** G11 投资收益（五、69 / 八、70）。 */
export function isG11InvestmentIncomeNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、69' || s === '八、70') return true
  if (s === '投资收益' || s.startsWith('投资收益')) return true
  return false
}

/** H2 在建工程（五、23 / 八、23）——排除「工程物资」（H4，无专有章节）。 */
export function isH2CipNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、23' || s === '八、23') return true
  if (s.includes('工程物资')) return false
  if (s === '在建工程' || s.includes('在建工程')) return true
  return false
}

/** I2 开发支出（五、27 / 八、28）。 */
export function isI2DevelopmentExpenseNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、27' || s === '八、28') return true
  if (s === '开发支出') return true
  return false
}

/** I3 商誉（五、28 / 八、29）。 */
export function isI3GoodwillNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、28' || s === '八、29') return true
  if (s === '商誉') return true
  return false
}

/** I4 长期待摊费用（五、29 / 八、30）。 */
export function isI4LongTermPrepaidNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、29' || s === '八、30') return true
  if (s === '长期待摊费用') return true
  return false
}

/** I6 研发费用（五、66 / 八、67）。 */
export function isI6ResearchExpenseNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、66' || s === '八、67') return true
  if (s === '研发费用') return true
  return false
}

/** K1 其他应收款（五、8 / 八、9）——应收利息(G2)/应收股利(G3) 作为行并入本节，跳转以 K1 为节主。 */
export function isK1OtherReceivableNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、8' || s === '八、9') return true
  if (s === '其他应收款') return true
  return false
}

/**
 * 是否像 F3 应付票据相关附注节（五、36 / 八、36）。
 * 权威 note_template_variant_matrix.json · ying_fu_piao_ju：上市→五、36，国企→八、36。
 * 纯编号须**精确===**匹配（禁 startsWith：五、36≠五、3 衍生金融资产；八、36≠八、3）。
 */
export function isF3NotesPayableNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、36' || s === '八、36') return true
  if (s === '应付票据') return true
  return false
}

/**
 * 是否像 G8 其他权益工具投资相关附注节（五、19 / 八、19）。
 * 权威 note_template_variant_matrix.json · qi_ta_quan_yi_gong_ju_tou_zi。
 * 纯编号须**精确===**匹配（禁 startsWith：五、19≠五、1 货币资金；八、19≠八、1）。
 */
export function isG8OtherEquityInstrumentNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、19' || s === '八、19') return true
  if (s === '其他权益工具投资') return true
  return false
}

/**
 * 是否像 G9 其他非流动金融资产相关附注节（五、20 / 八、20）。
 * 权威 note_template_variant_matrix.json · qi_ta_fei_liu_dong_jin_rong_zi_chan。
 * 纯编号须**精确===**匹配（禁 startsWith：五、20≠五、2 交易性金融资产）。
 */
export function isG9OtherNoncurrentFinancialNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、20' || s === '八、20') return true
  if (s === '其他非流动金融资产') return true
  return false
}

/**
 * 是否像 G12 套期净损益相关附注节（五、70 / 八、71）。
 * 权威 note_template_variant_matrix.json · tao_qi_jing_sun_yi（又名净敞口套期收益）。
 * 纯编号须**精确===**匹配（禁 startsWith：五、70≠五、7 预付款项；八、71≠八、7）。
 */
export function isG12HedgingGainsNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、70' || s === '八、71') return true
  if (s === '套期净损益' || s === '净敞口套期收益') return true
  return false
}

/** N2 应交税费（五、41 / 八、41）。权威 ying_jiao_shui_fei。精确===匹配。 */
export function isN2TaxesPayableNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、41' || s === '八、41') return true
  if (s === '应交税费') return true
  return false
}

/** N4 税金及附加（仅上市 五、63；国企 null 无独立章节）。权威 shui_jin_ji_fu_jia。精确===。 */
export function isN4TaxesAndSurchargesNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、63') return true
  if (s === '税金及附加') return true
  return false
}

/** N5 所得税费用（仅国企 八、78；上市 null 无独立章节）。权威 suo_de_shui_fei_yong。精确===。 */
export function isN5IncomeTaxExpenseNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '八、78') return true
  if (s === '所得税费用') return true
  return false
}

/**
 * 从当前附注记录推断「跳转至披露表」目标。
 * 优先 last_sync 元数据，其次章节号 / source_template / _current_standard。
 */
export function resolveNoteDisclosureJumpTarget(note: unknown): NoteDisclosureJumpTarget | null {
  const n = asRecord(note)
  if (!n) return null
  const table = asRecord(n.table_data) || {}
  const section = String(n.note_section || '').trim()
  const syncedSheet = String(table._last_sync_sheet || table._last_sync_sheet_name || '').trim()
  const wpId = String(
    n.last_sync_wp_id
    || table._last_sync_wp_id
    || '',
  ).trim() || null
  const std = String(
    table._current_standard
    || n.source_template
    || '',
  ).toLowerCase()

  // G13/G14 须先于 G7：sheet 名相同，靠章节号区分
  if (isG13FairValueNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? G13_DISCLOSURE_SHEET_LISTED : G13_DISCLOSURE_SHEET_SOE,
      wpId,
      variant,
      reason: `章节 ${section}`,
      wpCode: 'G13',
    }
  }

  if (isG14CreditImpairmentNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? G14_DISCLOSURE_SHEET_LISTED : G14_DISCLOSURE_SHEET_SOE,
      wpId,
      variant,
      reason: `章节 ${section}`,
      wpCode: 'G14',
    }
  }

  if (isH3InvestmentPropertyNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? H3_DISCLOSURE_SHEET_LISTED : H3_DISCLOSURE_SHEET_SOE,
      wpId,
      variant,
      reason: `章节 ${section}`,
      wpCode: 'H3' as any,
    }
  }

  if (isH1FixedAssetNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? H1_DISCLOSURE_SHEET_LISTED : H1_DISCLOSURE_SHEET_SOE,
      wpId,
      variant,
      reason: `章节 ${section}`,
      wpCode: 'H1',
    }
  }

  // H8 须在通用「附注披露信息」sheet 回退之前（与 G7 sheet 名重叠）
  if (isH8RouNoteSection(section)) {
    const variant = section.startsWith('八') || section.startsWith('四') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? H8_DISCLOSURE_SHEET_LISTED : H8_DISCLOSURE_SHEET_SOE,
      wpId,
      variant,
      reason: `章节 ${section}`,
      wpCode: 'H8',
    }
  }

  // H9 租赁负债（五、47 / 八、52）须在通用 sheet 回退之前
  if (isH9LeaseLiabilityNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? H9_DISCLOSURE_SHEET_LISTED : H9_DISCLOSURE_SHEET_SOE,
      wpId,
      variant,
      reason: `章节 ${section}`,
      wpCode: 'H9',
    }
  }

  // H10 资产处置收益（三、资产处置收益 / 八、75）
  if (isH10AssetDisposalNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? H10_DISCLOSURE_SHEET_LISTED : H10_DISCLOSURE_SHEET_SOE,
      wpId,
      variant,
      reason: `章节 ${section}`,
      wpCode: 'H10',
    }
  }

  // H5 油气资产（八、25 国企专属，上市无独立章节）— 行业限定底稿 oil_gas/mining
  if (isH5OilGasAssetNoteSection(section)) {
    // 油气资产仅国企有独立章节，上市版不跳转
    if (!section.startsWith('八') && !std.startsWith('soe')) return null
    return {
      sheet: H5_DISCLOSURE_SHEET_SOE,
      wpId,
      variant: 'soe',
      reason: `章节 ${section}`,
      wpCode: 'H5',
    }
  }

  // I1 无形资产（五、26 / 八、27）须在通用 sheet 回退之前
  if (isI1IntangibleNoteSection(section)) {
    const variant = section.startsWith('八') || section.startsWith('四') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? I1_DISCLOSURE_SHEET_LISTED : I1_DISCLOSURE_SHEET_SOE,
      wpId,
      variant,
      reason: `章节 ${section}`,
      wpCode: 'I1',
    }
  }

  // I5 其他非流动资产（五、31 / 八、32）
  if (isI5OtherNoncurrentNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? I5_DISCLOSURE_SHEET_LISTED : I5_DISCLOSURE_SHEET_SOE,
      wpId,
      variant,
      reason: `章节 ${section}`,
      wpCode: 'I5',
    }
  }

  // ─── K2-K10 精确编号章节（须在通用「附注披露信息」sheet 回退之前）───────────────
  if (isK2OtherCurrentAssetNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return { sheet: variant === 'listed' ? K2_DISCLOSURE_SHEET_LISTED : K2_DISCLOSURE_SHEET_SOE, wpId, variant, reason: `章节 ${section}`, wpCode: 'K2' }
  }
  if (isK3OtherPayableNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return { sheet: variant === 'listed' ? K3_DISCLOSURE_SHEET_LISTED : K3_DISCLOSURE_SHEET_SOE, wpId, variant, reason: `章节 ${section}`, wpCode: 'K3' }
  }
  if (isK4OtherCurrentLiabilityNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return { sheet: variant === 'listed' ? K4_DISCLOSURE_SHEET_LISTED : K4_DISCLOSURE_SHEET_SOE, wpId, variant, reason: `章节 ${section}`, wpCode: 'K4' }
  }
  if (isK5ProvisionsNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return { sheet: variant === 'listed' ? K5_DISCLOSURE_SHEET_LISTED : K5_DISCLOSURE_SHEET_SOE, wpId, variant, reason: `章节 ${section}`, wpCode: 'K5' }
  }
  if (isK6HeldForSaleNoteSection(section)) {
    const variant = section === '八、12' || std.startsWith('soe') ? 'soe' : 'listed'
    return { sheet: variant === 'listed' ? K6_DISCLOSURE_SHEET_LISTED : K6_DISCLOSURE_SHEET_SOE, wpId, variant, reason: `章节 ${section}`, wpCode: 'K6' }
  }
  if (isK7DeferredRevenueNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return { sheet: variant === 'listed' ? K7_DISCLOSURE_SHEET_LISTED : K7_DISCLOSURE_SHEET_SOE, wpId, variant, reason: `章节 ${section}`, wpCode: 'K7' }
  }
  if (isK8SellingExpenseNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return { sheet: variant === 'listed' ? K8_DISCLOSURE_SHEET_LISTED : K8_DISCLOSURE_SHEET_SOE, wpId, variant, reason: `章节 ${section}`, wpCode: 'K8' }
  }
  if (isK9AdminExpenseNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return { sheet: variant === 'listed' ? K9_DISCLOSURE_SHEET_LISTED : K9_DISCLOSURE_SHEET_SOE, wpId, variant, reason: `章节 ${section}`, wpCode: 'K9' }
  }
  if (isK10OtherIncomeNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return { sheet: variant === 'listed' ? K2_DISCLOSURE_SHEET_LISTED : K2_DISCLOSURE_SHEET_SOE, wpId, variant, reason: `章节 ${section}`, wpCode: 'K10' }
  }

  // K11 资产减值损失（关键词=上市三、资产减值损失 / 八、74=国企）——须在通用「附注披露信息」sheet 回退之前
  if (isK11AssetImpairmentNoteSection(section)) {
    const variant = section.startsWith('八、74') || section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? K11_DISCLOSURE_SHEET_LISTED : K11_DISCLOSURE_SHEET_SOE,
      wpId,
      variant,
      reason: `章节 ${section || '资产减值损失'}`,
      wpCode: 'K11',
    }
  }

  // K13 营业外支出（关键词"营业外支出"，区别于 K12 营业外收入）——须在通用「附注披露信息」sheet 回退之前
  if (isK13NonOperatingExpenseNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? K13_DISCLOSURE_SHEET_LISTED : K13_DISCLOSURE_SHEET_SOE,
      wpId,
      variant,
      reason: `章节 ${section || '营业外支出'}`,
      wpCode: 'K13',
    }
  }

  // ── 9 个专有章节科目（纯编号精确匹配，须在通用「附注披露信息」sheet 回退之前） ──
  if (isK1OtherReceivableNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? K1_DISCLOSURE_SHEET_LISTED : K1_DISCLOSURE_SHEET_SOE,
      wpId, variant, reason: `章节 ${section || '其他应收款'}`, wpCode: 'K1',
    }
  }

  if (isF1PrepaymentNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? F1_DISCLOSURE_SHEET_LISTED : F1_DISCLOSURE_SHEET_SOE,
      wpId, variant, reason: `章节 ${section || '预付款项'}`, wpCode: 'F1',
    }
  }

  if (isF2InventoryNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? F2_DISCLOSURE_SHEET_LISTED : F2_DISCLOSURE_SHEET_SOE,
      wpId, variant, reason: `章节 ${section || '存货'}`, wpCode: 'F2',
    }
  }

  if (isG11InvestmentIncomeNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? G11_DISCLOSURE_SHEET_LISTED : G11_DISCLOSURE_SHEET_SOE,
      wpId, variant, reason: `章节 ${section || '投资收益'}`, wpCode: 'G11',
    }
  }

  if (isH2CipNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? H2_DISCLOSURE_SHEET_LISTED : H2_DISCLOSURE_SHEET_SOE,
      wpId, variant, reason: `章节 ${section || '在建工程'}`, wpCode: 'H2',
    }
  }

  if (isI2DevelopmentExpenseNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? I2_DISCLOSURE_SHEET_LISTED : I2_DISCLOSURE_SHEET_SOE,
      wpId, variant, reason: `章节 ${section || '开发支出'}`, wpCode: 'I2',
    }
  }

  if (isI3GoodwillNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? I3_DISCLOSURE_SHEET_LISTED : I3_DISCLOSURE_SHEET_SOE,
      wpId, variant, reason: `章节 ${section || '商誉'}`, wpCode: 'I3',
    }
  }

  if (isI4LongTermPrepaidNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? I4_DISCLOSURE_SHEET_LISTED : I4_DISCLOSURE_SHEET_SOE,
      wpId, variant, reason: `章节 ${section || '长期待摊费用'}`, wpCode: 'I4',
    }
  }

  if (isI6ResearchExpenseNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? I6_DISCLOSURE_SHEET_LISTED : I6_DISCLOSURE_SHEET_SOE,
      wpId, variant, reason: `章节 ${section || '研发费用'}`, wpCode: 'I6',
    }
  }

  // N1 递延所得税资产（五、30 / 八、31，与 N3 共用章节，默认落 N1）——sheet 名为通用
  // 「附注披露信息（上市公司/国企）」，须在通用回退之前靠章节号精确命中。
  if (isN1DeferredTaxNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? N1_DISCLOSURE_SHEET_LISTED : N1_DISCLOSURE_SHEET_SOE,
      wpId,
      variant,
      reason: `章节 ${section || '递延所得税资产'}`,
      wpCode: 'N1',
    }
  }

  // F3 应付票据（五、36 / 八、36）——精确===匹配（五、36≠五、3；八、36≠八、3）
  if (isF3NotesPayableNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? F3_DISCLOSURE_SHEET_LISTED : F3_DISCLOSURE_SHEET_SOE,
      wpId, variant, reason: `章节 ${section || '应付票据'}`, wpCode: 'F3',
    }
  }

  // G8 其他权益工具投资（五、19 / 八、19）——精确===匹配（五、19≠五、1）
  if (isG8OtherEquityInstrumentNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? G8_DISCLOSURE_SHEET_LISTED : G8_DISCLOSURE_SHEET_SOE,
      wpId, variant, reason: `章节 ${section || '其他权益工具投资'}`, wpCode: 'G8',
    }
  }

  // G9 其他非流动金融资产（五、20 / 八、20）——精确===匹配（五、20≠五、2）
  if (isG9OtherNoncurrentFinancialNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? G9_DISCLOSURE_SHEET_LISTED : G9_DISCLOSURE_SHEET_SOE,
      wpId, variant, reason: `章节 ${section || '其他非流动金融资产'}`, wpCode: 'G9',
    }
  }

  // G12 套期净损益（五、70 / 八、71）——精确===匹配（五、70≠五、7）
  if (isG12HedgingGainsNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? G12_DISCLOSURE_SHEET_LISTED : G12_DISCLOSURE_SHEET_SOE,
      wpId, variant, reason: `章节 ${section || '套期净损益'}`, wpCode: 'G12',
    }
  }

  // N2 应交税费（五、41 / 八、41）——sheet 名通用，靠章节号精确命中。
  if (isN2TaxesPayableNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? N2_DISCLOSURE_SHEET_LISTED : N2_DISCLOSURE_SHEET_SOE,
      wpId,
      variant,
      reason: `章节 ${section || '应交税费'}`,
      wpCode: 'N2' as any,
    }
  }

  // N4 税金及附加（仅上市 五、63；国企无独立章节→国企不跳转）
  if (isN4TaxesAndSurchargesNoteSection(section)) {
    if (std.startsWith('soe') && !section.startsWith('五')) return null
    return {
      sheet: N4_DISCLOSURE_SHEET_LISTED,
      wpId,
      variant: 'listed' as const,
      reason: `章节 ${section || '税金及附加'}`,
      wpCode: 'N4' as any,
    }
  }

  // N5 所得税费用（仅国企 八、78；上市无独立章节→上市不跳转）
  if (isN5IncomeTaxExpenseNoteSection(section)) {
    if (!section.startsWith('八') && !std.startsWith('soe')) return null
    return {
      sheet: N5_DISCLOSURE_SHEET_SOE,
      wpId,
      variant: 'soe' as const,
      reason: `章节 ${section || '所得税费用'}`,
      wpCode: 'N5' as any,
    }
  }

  // E1 货币资金（五、1 / 八、1）——sheet 名（附注上市/附注国企）与 G1/G10 相同，
  // 须在 syncedSheet.includes('附注上市') 回退之前，靠章节号精确命中（五、1 exact，不误伤五、18=G7）。
  if (isE1MonetaryFundNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? E1_DISCLOSURE_SHEET_LISTED : E1_DISCLOSURE_SHEET_SOE,
      wpId,
      variant,
      reason: `章节 ${section || '货币资金'}`,
      wpCode: 'E1',
    }
  }

  // J1 应付职工薪酬（五、40 / 八、40）——精确匹配（禁 startsWith：五、4 是应收票据、五、400 不存在）
  if (isJ1EmployeeBenefitsNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? J1_DISCLOSURE_SHEET_LISTED : J1_DISCLOSURE_SHEET_SOE,
      wpId,
      variant,
      reason: `章节 ${section || '应付职工薪酬'}`,
      wpCode: 'J1',
    }
  }

  // L1 短期借款（五、33 / 八、33）——精确===匹配（五、33≠五、3；八、33≠八、3）
  if (isL1ShortTermLoanNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? L1_DISCLOSURE_SHEET_LISTED : L1_DISCLOSURE_SHEET_SOE,
      wpId,
      variant,
      reason: `章节 ${section || '短期借款'}`,
      wpCode: 'L1',
    }
  }

  // L3 长期借款（五、45 / 八、49）
  if (isL3LongTermLoanNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? L3_DISCLOSURE_SHEET_LISTED : L3_DISCLOSURE_SHEET_SOE,
      wpId,
      variant,
      reason: `章节 ${section || '长期借款'}`,
      wpCode: 'L3' as any,
    }
  }

  // L5 长期应付款（五、48 / 八、53）
  if (isL5LongTermPayableNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? L5_DISCLOSURE_SHEET_LISTED : L5_DISCLOSURE_SHEET_SOE,
      wpId,
      variant,
      reason: `章节 ${section || '长期应付款'}`,
      wpCode: 'L5' as any,
    }
  }

  // L7 其他非流动负债（五、52 / 八、57）
  if (isL7OtherNoncurrentLiabilityNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? L7_DISCLOSURE_SHEET_LISTED : L7_DISCLOSURE_SHEET_SOE,
      wpId,
      variant,
      reason: `章节 ${section || '其他非流动负债'}`,
      wpCode: 'L7' as any,
    }
  }

  // ─── M 循环权益类 ─────────────────────────────────────────────────────────
  if (isM2PaidInCapitalNoteSection(section)) {
    return { sheet: M_DISCLOSURE_SHEET_SOE, wpId, variant: 'soe', reason: `章节 ${section || '实收资本'}`, wpCode: 'M2' as any }
  }
  if (isM3TreasuryStockNoteSection(section)) {
    return { sheet: M_DISCLOSURE_SHEET_LISTED, wpId, variant: 'listed', reason: `章节 ${section || '库存股'}`, wpCode: 'M3' as any }
  }
  if (isM4CapitalReserveNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return { sheet: variant === 'listed' ? M_DISCLOSURE_SHEET_LISTED : M_DISCLOSURE_SHEET_SOE, wpId, variant, reason: `章节 ${section || '资本公积'}`, wpCode: 'M4' as any }
  }
  if (isM5SurplusReserveNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return { sheet: variant === 'listed' ? M_DISCLOSURE_SHEET_LISTED : M_DISCLOSURE_SHEET_SOE, wpId, variant, reason: `章节 ${section || '盈余公积'}`, wpCode: 'M5' as any }
  }
  if (isM6UndistributedProfitNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return { sheet: variant === 'listed' ? M_DISCLOSURE_SHEET_LISTED : M_DISCLOSURE_SHEET_SOE, wpId, variant, reason: `章节 ${section || '未分配利润'}`, wpCode: 'M6' as any }
  }
  if (isM7SpecialReserveNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return { sheet: variant === 'listed' ? M_DISCLOSURE_SHEET_LISTED : M_DISCLOSURE_SHEET_SOE, wpId, variant, reason: `章节 ${section || '专项储备'}`, wpCode: 'M7' as any }
  }
  if (isM9OciNoteSection(section)) {
    return { sheet: M_DISCLOSURE_SHEET_LISTED, wpId, variant: 'listed', reason: `章节 ${section || '其他综合收益'}`, wpCode: 'M9' as any }
  }
  if (isM10OtherEquityInstrumentNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return { sheet: variant === 'listed' ? M_DISCLOSURE_SHEET_LISTED : M_DISCLOSURE_SHEET_SOE, wpId, variant, reason: `章节 ${section || '其他权益工具'}`, wpCode: 'M10' as any }
  }

  // D1 应收票据（五、4 / 八、4）——sheet 名为通用「附注披露信息（上市公司/国企）」，
  // 须在通用回退之前靠章节号精确命中（五、4 exact，不误伤 五、40~五、49）。
  if (isD1NotesReceivableNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? D1_DISCLOSURE_SHEET_LISTED : D1_DISCLOSURE_SHEET_SOE,
      wpId,
      variant,
      reason: `章节 ${section || '应收票据'}`,
      wpCode: 'D1',
    }
  }

  // D2 应收账款（五、5 / 八、5）——单字数字须精确===（五、5≠五、50~五、59）。
  if (isD2AccountsReceivableNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? D2_DISCLOSURE_SHEET_LISTED : D2_DISCLOSURE_SHEET_SOE,
      wpId,
      variant,
      reason: `章节 ${section || '应收账款'}`,
      wpCode: 'D2',
    }
  }

  // D3 预收款项（五、38 / 八、38）
  if (isD3PrepaymentNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? D3_DISCLOSURE_SHEET_LISTED : D3_DISCLOSURE_SHEET_SOE,
      wpId, variant, reason: `章节 ${section || '预收款项'}`, wpCode: 'D3',
    }
  }

  // D5 应收款项融资（五、6 / 八、6）
  if (isD5ReceivablesFinancingNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? D5_DISCLOSURE_SHEET_LISTED : D5_DISCLOSURE_SHEET_SOE,
      wpId, variant, reason: `章节 ${section || '应收款项融资'}`, wpCode: 'D5',
    }
  }

  // D6 合同资产（五、10 / 八、11）
  if (isD6ContractAssetNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? D6_DISCLOSURE_SHEET_LISTED : D6_DISCLOSURE_SHEET_SOE,
      wpId, variant, reason: `章节 ${section || '合同资产'}`, wpCode: 'D6',
    }
  }

  // D7 合同负债（五、39 / 八、39）
  if (isD7ContractLiabilityNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? D7_DISCLOSURE_SHEET_LISTED : D7_DISCLOSURE_SHEET_SOE,
      wpId, variant, reason: `章节 ${section || '合同负债'}`, wpCode: 'D7',
    }
  }

  // D4 营业收入/营业成本（五、62 / 八、64）——损益类
  if (isD4RevenueNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? D4_DISCLOSURE_SHEET_LISTED : D4_DISCLOSURE_SHEET_SOE,
      wpId, variant, reason: `章节 ${section || '营业收入'}`, wpCode: 'D4',
    }
  }

  // G1 交易性金融资产（五、2 / 八、2）——sheet 名与 G10 相同，须在 G10
  // syncedSheet.includes('附注上市') 回退之前，靠章节号精确命中。
  if (isG1TradingFinancialAssetNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? G1_DISCLOSURE_SHEET_LISTED : G1_DISCLOSURE_SHEET_SOE,
      wpId,
      variant,
      reason: `章节 ${section || '交易性金融资产'}`,
      wpCode: 'G1',
    }
  }

  // 衍生金融资产（五、3 / 八、3）——归属 G1 底稿，与交易性金融资产同为 G1 披露 sheet
  // （附注上市②衍生工具 / 附注国企表2衍生金融资产），须精确命中，不误伤 衍生金融负债（G10）。
  if (isDerivativeFinancialAssetNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? G1_DISCLOSURE_SHEET_LISTED : G1_DISCLOSURE_SHEET_SOE,
      wpId,
      variant,
      reason: `章节 ${section || '衍生金融资产'}`,
      wpCode: 'G1',
    }
  }

  // 注意：不能用 syncedSheet 包含披露 sheet 名来判定 G10——G1/G10/E1/D1/F1/H1... 的披露 sheet
  // 名都叫「附注披露信息（上市公司/国企）」，用它判定会误伤所有循环。G10 仅靠章节号（五/八、34/35）判定。
  if (section === '五、34' || section.startsWith('五、34') || section === '五、35' || section.startsWith('五、35')) {
    return {
      sheet: G10_DISCLOSURE_SHEET_LISTED,
      wpId,
      variant: 'listed',
      reason: section ? `章节 ${section}` : 'listed 准则',
      wpCode: 'G10',
    }
  }

  if (section === '八、34' || section.startsWith('八、34') || section === '八、35' || section.startsWith('八、35')) {
    return {
      sheet: G10_DISCLOSURE_SHEET_SOE,
      wpId,
      variant: 'soe',
      reason: section ? `章节 ${section}` : 'soe 准则',
      wpCode: 'G10',
    }
  }

  // 注意：所有循环（G1/G10/E1/D1/F1/H1/H8/K11...）的披露 sheet 名都叫「附注披露信息（上市公司/国企）」，
  // 不能用 syncedSheet 包含该名来判定任何底稿，必须靠章节号精确命中。

  // G7 长期股权投资：必须章节号精确命中（五、18 / 八、18 / 七、），
  // 不能仅凭 std='listed'/'soe' 判定（所有附注都有 source_template，会误伤 E1/D1/F1 等）
  if (isG7EquityNoteSection(section)) {
    const variant = section.startsWith('八') || section.startsWith('七') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? G7_DISCLOSURE_SHEET_LISTED : G7_DISCLOSURE_SHEET_SOE,
      wpId,
      variant,
      reason: `章节 ${section}`,
      wpCode: 'G7',
    }
  }

  return null
}
