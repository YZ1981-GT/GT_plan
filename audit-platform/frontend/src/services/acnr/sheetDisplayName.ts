/**
 * ACNR sheet 显示名组建 — 单一真源
 *
 * 供公式管理树（FormulaManagerDialog.buildWpDomainTree）、公式选址器 /
 * 高级查询选字段（useAcnr.buildAddressTree）等所有从 /api/acnr/entries 建树的
 * 消费者统一调用，保证全平台 sheet 显示名一致。
 *
 * 组名规则（优先级）：
 *   mapped_sheet_name（wp_account_mapping 策管名 / classification 真名 / prefill 兜底，后端 list_sheets 注入）
 *   → cleanSheetLabelName(sheet_name)（去末尾冗余编码）
 *   → 纯编码占位则置空（仅显示编码，不渲染「编码 编码」）
 * 再补「科目简称·」前缀区分跨循环通用名（如「附注披露信息」）；
 * 最后对同一父组内仍重名者追加序号（1）（2）（各源均无 distinct 名的报告文档类）。
 */

export interface SheetNameInput {
  sheet_code?: string
  sheet_name?: string
  account_name?: string
  mapped_sheet_name?: string
  addr_id?: string
}

export interface ComposedSheetLabel<T extends SheetNameInput> {
  entry: T
  /** 名称部分（不含编码前缀，已含科目简称/序号消歧） */
  name: string
  /** 完整标签：`{sheet_code} {name}`，纯编码占位时仅 `{sheet_code}` */
  label: string
}

/**
 * 底稿编码自然排序：拆 letter/number/-number/suffix，数字段按数值比。
 * 修复 localeCompare 字符串排序导致 D2-10 排在 D2-2 之前的问题。
 */
export function wpCodeNaturalCompare(a: string, b: string): number {
  const parse = (code: string) => {
    const m = /^([A-Za-z]+)(\d+)?(?:-(\d+))?(.*)$/.exec((code || '').trim())
    if (!m) return { letter: code || '', n1: Number.MAX_SAFE_INTEGER, n2: -1, rest: '' }
    return {
      letter: m[1] || '',
      n1: m[2] ? parseInt(m[2], 10) : -1,
      n2: m[3] ? parseInt(m[3], 10) : -1,
      rest: m[4] || '',
    }
  }
  const pa = parse(a)
  const pb = parse(b)
  if (pa.letter !== pb.letter) return pa.letter.localeCompare(pb.letter)
  if (pa.n1 !== pb.n1) return pa.n1 - pb.n1
  if (pa.n2 !== pb.n2) return pa.n2 - pb.n2
  return pa.rest.localeCompare(pb.rest)
}

/**
 * 清洗 sheet 名称：去掉末尾冗余的底稿编码后缀（如「审定表D1-1」→「审定表」、
 * 「附注披露信息(上市公司）D2-1」→「附注披露信息(上市公司）」）。
 * 保留「（修订前）」等业务注解（其结尾非编码不会被误删）。
 */
export function cleanSheetLabelName(name: string): string {
  if (!name) return ''
  const cleaned = name.replace(/\s*[A-Za-z]+\d+(?:-\d+)?[A-Za-z]?$/, '').trim()
  return cleaned || name
}

/**
 * 组建一个父组内全部 sheet 的显示名（含自然排序 + 科目简称前缀 + 同名序号消歧）。
 * 返回按编码自然序排列的结果数组。
 */
export function composeSheetLabelsForGroup<T extends SheetNameInput>(
  group: T[],
): Array<ComposedSheetLabel<T>> {
  // 科目简称（父底稿维度，全组一致）
  const subjectAbbr = group.find((s) => s.account_name)?.account_name || ''

  // pass 1：算每张 sheet 的显示名
  const withNames = group
    .slice()
    .sort((a, b) => wpCodeNaturalCompare(a.sheet_code || '', b.sheet_code || ''))
    .map((entry) => {
      const code = entry.sheet_code || ''
      const mapped = (entry.mapped_sheet_name || '').trim()
      const cleanName = cleanSheetLabelName(entry.sheet_name || '')
      let name = mapped || cleanName
      // 纯编码占位（各源均无真实名，如 K14~K18）：置空，仅显示编码
      if (name === code) name = ''
      if (subjectAbbr && name && !name.includes(subjectAbbr)) {
        name = `${subjectAbbr}·${name}`
      }
      return { entry, name }
    })

  // pass 2：同组内显示名重复者追加序号（1）（2）（报告文档封面与首表同名等）
  const counts: Record<string, number> = {}
  for (const w of withNames) {
    if (w.name) counts[w.name] = (counts[w.name] || 0) + 1
  }
  const seen: Record<string, number> = {}
  return withNames.map(({ entry, name }) => {
    let n = name
    if (n && counts[n] > 1) {
      seen[n] = (seen[n] || 0) + 1
      n = `${n}（${seen[n]}）`
    }
    const code = entry.sheet_code || ''
    return { entry, name: n, label: n ? `${code} ${n}` : code }
  })
}
