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

// G1 交易性金融资产 / G10 交易性金融负债 披露 sheet：底稿实际 tab 名为
// 「附注披露信息（上市公司）」/「附注披露信息（国企）」（全角括号，见 workpaper_sheet_classification
// wp_code=G1/G10）。此前误设为 '附注上市'/'附注国企'（那是 OnlyOffice sheet-name 映射，非分类 tab 名）
// 导致 GtWpRenderer 的 ?sheet= 精确匹配失败 → 回退到首个 sheet（底稿目录）。靠章节号区分 G1/G10。
export const G1_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const G1_DISCLOSURE_SHEET_SOE = '附注披露信息（国企）'

export const G10_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const G10_DISCLOSURE_SHEET_SOE = '附注披露信息（国企）'

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

export const I1_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const I1_DISCLOSURE_SHEET_SOE = '附注披露信息（国有企业）'

export const I5_DISCLOSURE_SHEET_LISTED = '附注披露（上市公司）'
export const I5_DISCLOSURE_SHEET_SOE = '附注披露（国有企业）'

export const K11_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const K11_DISCLOSURE_SHEET_SOE = '附注披露信息（国有企业）'

export const K13_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const K13_DISCLOSURE_SHEET_SOE = '附注披露信息（国有企业）'

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
  wpCode?: 'D1' | 'E1' | 'F1' | 'F2' | 'G1' | 'G7' | 'G10' | 'G11' | 'G13' | 'G14' | 'H1' | 'H2' | 'H8' | 'H9' | 'H10' | 'I1' | 'I2' | 'I3' | 'I4' | 'I5' | 'I6' | 'K1' | 'K11' | 'K13'
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

/** 是否像 H1 固定资产相关附注节 */
export function isH1FixedAssetNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、15' || s.startsWith('五、15')) return true
  if (s === '五、22' || s.startsWith('五、22')) return true
  if (s === '八、22' || s.startsWith('八、22')) return true
  if (s === '固定资产' || (s.includes('固定资产') && !s.includes('清理') && !s.includes('在建'))) return true
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
