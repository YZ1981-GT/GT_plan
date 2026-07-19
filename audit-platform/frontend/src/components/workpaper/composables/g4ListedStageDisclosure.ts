/**
 * G4 上市公司附注 — 三阶段减值「其中」动态明细
 * 对齐 Excel「按单项/按组合 → 其中行可扩展」结构；默认 1 行，可无限增删。
 */
export type G4EclStage = 1 | 2 | 3
export type G4StagePeriod = 'ending' | 'prior'
export type G4StageMethod = 'individual' | 'portfolio'

export interface G4StageDetailRow {
  id: string
  name: string
  bookBalance: number
  impairment: number
  /** 理由 / 划分依据 */
  reason: string
}

export interface G4StageMethodBlock {
  method: G4StageMethod
  details: G4StageDetailRow[]
}

export interface G4StageBlock {
  id: string
  period: G4StagePeriod
  stage: G4EclStage
  title: string
  /** 阶段1：未来12个月；阶段2/3：整个存续期 */
  rateLabel: string
  reasonHeader: string
  individual: G4StageMethodBlock
  portfolio: G4StageMethodBlock
}

function uid(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

export function emptyDetail(name = '其中：'): G4StageDetailRow {
  return { id: uid('d'), name, bookBalance: 0, impairment: 0, reason: '' }
}

export function eclRatePct(impairment: number, bookBalance: number): number | null {
  if (!bookBalance) return null
  return (impairment / bookBalance) * 100
}

export function bookValue(bookBalance: number, impairment: number): number {
  return bookBalance - impairment
}

function sumDetails(details: G4StageDetailRow[]) {
  return details.reduce(
    (acc, d) => {
      acc.bookBalance += Number(d.bookBalance) || 0
      acc.impairment += Number(d.impairment) || 0
      return acc
    },
    { bookBalance: 0, impairment: 0 },
  )
}

export function methodTotals(block: G4StageMethodBlock) {
  const s = sumDetails(block.details)
  return {
    bookBalance: s.bookBalance,
    impairment: s.impairment,
    bookValue: bookValue(s.bookBalance, s.impairment),
    ratePct: eclRatePct(s.impairment, s.bookBalance),
  }
}

export function stageTotals(block: G4StageBlock) {
  const a = methodTotals(block.individual)
  const b = methodTotals(block.portfolio)
  const bookBalance = a.bookBalance + b.bookBalance
  const impairment = a.impairment + b.impairment
  return {
    bookBalance,
    impairment,
    bookValue: bookValue(bookBalance, impairment),
    ratePct: eclRatePct(impairment, bookBalance),
  }
}

function makeBlock(
  period: G4StagePeriod,
  stage: G4EclStage,
  title: string,
  rateLabel: string,
  reasonHeader: string,
): G4StageBlock {
  return {
    id: `${period}-s${stage}`,
    period,
    stage,
    title,
    rateLabel,
    reasonHeader,
    individual: { method: 'individual', details: [emptyDetail('其中：')] },
    portfolio: { method: 'portfolio', details: [emptyDetail('其中：')] },
  }
}

export function buildDefaultStageBlocks(): G4StageBlock[] {
  return [
    makeBlock('ending', 1, '期末处于第一阶段的债权投资的减值准备', '未来12个月内预期信用损失率(%)', '理由'),
    makeBlock('ending', 2, '期末处于第二阶段的债权投资的减值准备', '整个存续期预期信用损失率(%)', '划分依据'),
    makeBlock('ending', 3, '期末处于第三阶段的债权投资的减值准备', '整个存续期预期信用损失率(%)', '划分依据'),
    makeBlock('prior', 1, '上年年末处于第一阶段的债权投资的减值准备', '未来12个月内预期信用损失率(%)', '划分依据'),
    makeBlock('prior', 2, '上年年末处于第二阶段的债权投资的减值准备', '整个存续期预期信用损失率(%)', '划分依据'),
    makeBlock('prior', 3, '上年年末处于第三阶段的债权投资的减值准备', '整个存续期预期信用损失率(%)', '划分依据'),
  ]
}

/** 国企附注：仅期末三阶段，理由列统一为「理由」 */
export function buildDefaultSoeStageBlocks(): G4StageBlock[] {
  return [
    makeBlock('ending', 1, '期末，处于第一阶段的债权投资的减值准备：', '未来12个月内预期信用损失率(%)', '理由'),
    makeBlock('ending', 2, '期末，处于第二阶段的债权投资的减值准备：', '整个存续期预期信用损失率(%)', '理由'),
    makeBlock('ending', 3, '期末，处于第三阶段的债权投资的减值准备：', '整个存续期预期信用损失率(%)', '理由'),
  ]
}

export function serializeStageBlocks(blocks: G4StageBlock[]): string {
  return JSON.stringify({ version: 1, blocks })
}

export function parseStageBlocks(raw: string | null | undefined): G4StageBlock[] | null {
  if (!raw?.trim()) return null
  try {
    const parsed = JSON.parse(raw)
    if (!parsed?.blocks || !Array.isArray(parsed.blocks)) return null
    const defaults = buildDefaultStageBlocks()
    return defaults.map((def) => {
      const found = parsed.blocks.find((b: G4StageBlock) => b.id === def.id)
      if (!found) return def
      return {
        ...def,
        ...found,
        id: def.id,
        title: def.title,
        rateLabel: def.rateLabel,
        reasonHeader: def.reasonHeader,
        individual: {
          method: 'individual' as const,
          details:
            Array.isArray(found.individual?.details) && found.individual.details.length
              ? found.individual.details.map((d: G4StageDetailRow) => ({
                  id: d.id || uid('d'),
                  name: d.name ?? '其中：',
                  bookBalance: Number(d.bookBalance) || 0,
                  impairment: Number(d.impairment) || 0,
                  reason: d.reason ?? '',
                }))
              : [emptyDetail('其中：')],
        },
        portfolio: {
          method: 'portfolio' as const,
          details:
            Array.isArray(found.portfolio?.details) && found.portfolio.details.length
              ? found.portfolio.details.map((d: G4StageDetailRow) => ({
                  id: d.id || uid('d'),
                  name: d.name ?? '其中：',
                  bookBalance: Number(d.bookBalance) || 0,
                  impairment: Number(d.impairment) || 0,
                  reason: d.reason ?? '',
                }))
              : [emptyDetail('其中：')],
        },
      }
    })
  } catch {
    return null
  }
}

export function addStageDetail(
  blocks: G4StageBlock[],
  blockId: string,
  method: G4StageMethod,
  name?: string,
): G4StageBlock[] {
  return blocks.map((b) => {
    if (b.id !== blockId) return b
    const key = method === 'individual' ? 'individual' : 'portfolio'
    const n = b[key].details.length + 1
    return {
      ...b,
      [key]: {
        ...b[key],
        details: [...b[key].details, emptyDetail(name || `其中${n}：`)],
      },
    }
  })
}

export function removeStageDetail(
  blocks: G4StageBlock[],
  blockId: string,
  method: G4StageMethod,
  detailId: string,
): G4StageBlock[] {
  return blocks.map((b) => {
    if (b.id !== blockId) return b
    const key = method === 'individual' ? 'individual' : 'portfolio'
    const next = b[key].details.filter((d) => d.id !== detailId)
    return {
      ...b,
      [key]: {
        ...b[key],
        details: next.length ? next : [emptyDetail('其中：')],
      },
    }
  })
}

export function patchStageDetail(
  blocks: G4StageBlock[],
  blockId: string,
  method: G4StageMethod,
  detailId: string,
  patch: Partial<Pick<G4StageDetailRow, 'name' | 'bookBalance' | 'impairment' | 'reason'>>,
): G4StageBlock[] {
  return blocks.map((b) => {
    if (b.id !== blockId) return b
    const key = method === 'individual' ? 'individual' : 'portfolio'
    return {
      ...b,
      [key]: {
        ...b[key],
        details: b[key].details.map((d) =>
          d.id === detailId
            ? {
                ...d,
                ...patch,
                bookBalance:
                  patch.bookBalance != null ? Number(patch.bookBalance) || 0 : d.bookBalance,
                impairment:
                  patch.impairment != null ? Number(patch.impairment) || 0 : d.impairment,
              }
            : d,
        ),
      },
    }
  })
}

/** 期末三阶段减值准备合计（用于与主表减值勾稽） */
export function endingImpairmentTotal(blocks: G4StageBlock[]): number {
  return blocks
    .filter((b) => b.period === 'ending')
    .reduce((s, b) => s + stageTotals(b).impairment, 0)
}
