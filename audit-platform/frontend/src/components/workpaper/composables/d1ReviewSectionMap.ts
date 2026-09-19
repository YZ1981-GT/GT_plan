/** D1 各 sheet 默认复核 sectionId（右侧「底稿复核」入口） */
export const D1_REVIEW_SECTION_BY_SHEET: Record<string, { id: string; label: string }> = {
  directory: { id: 'D1-index-directory', label: 'D1 底稿目录' },
  D1: { id: 'D1-index-directory', label: 'D1 底稿目录' },
  D1A: { id: 'D1-procedure', label: 'D1A 程序表' },
  'D1-1': { id: 'D1-adjudication-header', label: '审定表 D1-1' },
  'D1-2': { id: 'D1-detail-cat-header', label: '明细表 D1-2' },
  'D1-3': { id: 'D1-detail-cust-header', label: '明细表 D1-3' },
  'D1-4': { id: 'D1-baddebt-header', label: '坏账明细 D1-4' },
  'D1-5': { id: 'D1-adjustment-header', label: '调整分录 D1-5' },
  'D1-6': { id: 'D1-business-mode-header', label: '业务模式 D1-6' },
  'D1-7': { id: 'D1-memo-header', label: '备查簿核对 D1-7' },
  'D1-8': { id: 'D1-endorsement-header', label: '背书明细 D1-8' },
  'D1-9': { id: 'D1-interest-header', label: '利息检查 D1-9' },
  'D1-10': { id: 'D1-inventory-header', label: '盘点检查 D1-10' },
  'D1-11': { id: 'D1-related-party-header', label: '关联方检查 D1-11' },
  'D1-12': { id: 'D1-pledge-header', label: '质押检查 D1-12' },
  'D1-13': { id: 'D1-sampling-header', label: '抽凭检查 D1-13' },
  'D1-14': { id: 'D1-policy-header', label: '政策检查 D1-14' },
  'D1-15': { id: 'D1-ecl-header', label: '坏账测算 D1-15' },
  'D1-16': { id: 'D1-writeoff-header', label: '核销检查 D1-16' },
  附注上市: { id: 'D1-disclosure-listed', label: '附注（上市）' },
  附注国企: { id: 'D1-disclosure-soe', label: '附注（国企）' },
}

export function resolveD1ReviewSection(sheetCode: string): { id: string; label: string } {
  const hit = D1_REVIEW_SECTION_BY_SHEET[sheetCode]
  if (hit) return hit
  return { id: `D1-${sheetCode}-header`, label: sheetCode || 'D1 底稿' }
}
