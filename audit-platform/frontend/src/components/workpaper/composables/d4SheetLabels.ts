/**
 * D4 sheet 编码 → render-config sheet_name 默认映射
 */
export const D4_SHEET_LABEL_MAP: Record<string, string> = {
  'D4-目录': 'D4',
  D4: 'D4',
  D4A: '营业收入审计程序表D4A',
  'D4-1': '营业收入审定表D4-1',
  'D4-2': '主营业务收入明细表D4-2',
  'D4-3': '其他业务收入明细表D4-3',
  'D4-4': '营业收入调整分录汇总D4-4',
  'D4-5': '营业收入会计政策检查D4-5',
  'D4-6': '重要指标分析D4-6',
  'D4-7': '毛利率分析表D4-7',
  'D4-8': '重要产品毛利分析D4-8',
  'D4-9': '重要客户结构分析D4-9',
  'D4-10': '重要客户销售价格分析D4-10',
  'D4-11': '产品销售价格分析D4-11',
  'D4-12': '合同检查表D4-12',
  'D4-13': '营业收入账面金额与ERP系统核对记录D4-13',
  'D4-14': '营业收入发生检查表D4-14',
  'D4-15': '营业收入完整性检查表D4-15',
  'D4-16': '出口收入电子口岸系统核对D4-16',
  'D4-17': '营业收入截止测试（账到单据）D4-17',
  'D4-18': '营业收入截止测试（单据到账）D4-18',
  'D4-19': '销售折扣与折让检查D4-19',
  'D4-20': '销售退货检查表 D4-20',
  'D4-21': '关联方销售情况及价格分析D4-21',
  'D4-22A': '程序表D4-22A',
  'D4-22': '重要指标分析表D4-22',
  'D4-23': '收入与开具发票金额比较分析D4-23',
  'D4-24': '第三方回款检查D4-24',
  'D4-25': '经销商检查D4-25',
  'D4-26': '境外销售收入检查D4-26',
  'D4-27': '识别未披露的关联方D4-27',
  'D4-28': '客户信息核查清单D4-28',
  'D4-29': '客户信息检查表D4-29',
  'D4-30': '客户访谈记录汇总表D4-30',
  'D4-31': '客户访谈记录 D4-31',
  'D4-31T': '访谈记录与核对示例',
  'D4-访谈模板': '访谈记录与核对示例',
  'D4-32': '客户、供应商等资金流水检查D4-32',
  'D4-33': '其他业务毛利率分析表D4-33',
  'D4-34': '其他业务收入合同测算表D4-34',
  'D4-35': '其他业务收入检查表D4-35',
  'D4-36': '其他业务收入截止性测试D4-36',
  'D4-附注上市': '附注披露信息（上市公司）',
  'D4-附注国企': '附注披露信息（国有企业）',
}

/** 程序表索引号 → sheet_label */
export const D4_PROC_INDEX_SHEET_MAP: Record<string, string> = {
  'D4-1': D4_SHEET_LABEL_MAP['D4-1'],
  'D4-2': D4_SHEET_LABEL_MAP['D4-2'],
  'D4-6': D4_SHEET_LABEL_MAP['D4-6'],
  'D4-12': D4_SHEET_LABEL_MAP['D4-12'],
  'D4-14': D4_SHEET_LABEL_MAP['D4-14'],
  'D4-15': D4_SHEET_LABEL_MAP['D4-15'],
  'D4-17': D4_SHEET_LABEL_MAP['D4-17'],
  'D4-18': D4_SHEET_LABEL_MAP['D4-18'],
}

export function resolveD4SheetLabel(
  code: string,
  availableSheets?: Array<{ sheet_name?: string }>,
): string {
  if (availableSheets?.length) {
    const codeRe = new RegExp(`${code.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*$`)
    const hit = availableSheets.find(s => s.sheet_name && codeRe.test(s.sheet_name))
    if (hit?.sheet_name) return hit.sheet_name
    if (code === 'D4-附注上市' || code === '附注上市') {
      const d = availableSheets.find(s => s.sheet_name?.includes('附注') && s.sheet_name?.includes('上市'))
      if (d?.sheet_name) return d.sheet_name
    }
    if (code === 'D4-附注国企' || code === '附注国企') {
      const d = availableSheets.find(s => s.sheet_name?.includes('附注') && (s.sheet_name?.includes('国企') || s.sheet_name?.includes('国有')))
      if (d?.sheet_name) return d.sheet_name
    }
    if (code === 'D4-访谈模板' || code === 'D4-31T') {
      const d = availableSheets.find(s => s.sheet_name?.includes('访谈记录与核对'))
      if (d?.sheet_name) return d.sheet_name
    }
  }
  return D4_SHEET_LABEL_MAP[code] ?? code
}
