/**
 * 三阶段（CAS 22）减值披露 —「按单项 / 按组合 → 其中行可扩展」动态明细模型。
 *
 * 🔴 **G4 债权投资与 G6 其他债权投资共用本模型**（源模板两者的阶段表结构完全同构：
 * 类别 / 账面余额 / 预期信用损失率 / 减值准备 / 账面价值 / 理由或划分依据；
 * 上市 6 张（期末 + 上年年末各三阶段）、国企 3 张（仅期末））。
 * 文件名保留 `g4*` 是历史命名，改名会波及 G4 两版组件与其契约测试，
 * 故以 `buildStageBlocks(account, …)` 泛化，`buildDefaultStageBlocks` 等保留为 G4 薄包装。
 *
 * 对齐 Excel「预留区可插行」：其中行默认 1 行，可无限增删。
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

/**
 * 「其中：」是源模板父行与明细之间的**结构标签行**，由载荷构建器单独发一行
 * （`whichRow()` / `G4_WHICH_LABEL`），**不能同时当明细行的默认名**：
 * 否则附注里会出现两行「其中：」——一行结构行 + 一行全零的幽灵数据行
 * （浏览器实测 G6 §五、15 期末第一阶段表中招）。新明细行留空，由 UI 占位符引导。
 */
export function emptyDetail(name = ''): G4StageDetailRow {
  return { id: uid('d'), name, bookBalance: 0, impairment: 0, reason: '' }
}

/** 结构标签字面量（去空白后比较），与各循环载荷的 `X_WHICH_LABEL` 同源 */
const WHICH_LABELS = new Set(['其中', '其中：', '其中:'])

/**
 * 空白骨架明细行：无名（或名字就是结构标签）且金额全零 → 不推给附注。
 * 附注是交付物，推空行会渲染出一行没有含义的披露数据。
 */
export function isPlaceholderStageDetail(d: {
  name?: unknown
  bookBalance?: unknown
  impairment?: unknown
}): boolean {
  const name = String(d?.name ?? '').replace(/\s+/g, '')
  if (name && !WHICH_LABELS.has(name)) return false
  return !Number(d?.bookBalance) && !Number(d?.impairment)
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
    // 明细行默认留空（「其中：」由载荷的结构行单独发，见 emptyDetail 注释）
    individual: { method: 'individual', details: [emptyDetail()] },
    portfolio: { method: 'portfolio', details: [emptyDetail()] },
  }
}

const RATE_12M = '未来12个月内预期信用损失率(%)'
const RATE_LIFETIME = '整个存续期预期信用损失率(%)'
const STAGE_CN = ['', '第一阶段', '第二阶段', '第三阶段'] as const

/**
 * 泛化的上市侧 6 张阶段表（期末三阶段 + 上年年末三阶段）。
 *
 * 🔴 末列口径按权威模板逐格核对：**只有「期末第一阶段」是「理由」**，
 * 其余 5 张是「划分依据」（G4 R39 vs R56/R73/R92/R109/R126；G6 R46 vs R63/R80/…）。
 *
 * @param account 科目名，如 `债权投资` / `其他债权投资`
 */
export function buildStageBlocks(account: string): G4StageBlock[] {
  const stages: G4EclStage[] = [1, 2, 3]
  const blocks: G4StageBlock[] = []
  for (const period of ['ending', 'prior'] as const) {
    const prefix = period === 'ending' ? '期末' : '上年年末'
    for (const stage of stages) {
      blocks.push(
        makeBlock(
          period,
          stage,
          `${prefix}处于${STAGE_CN[stage]}的${account}的减值准备`,
          stage === 1 ? RATE_12M : RATE_LIFETIME,
          period === 'ending' && stage === 1 ? '理由' : '划分依据',
        ),
      )
    }
  }
  return blocks
}

/** G4 债权投资（上市）——保留原名供既有组件与契约测试引用 */
export function buildDefaultStageBlocks(): G4StageBlock[] {
  return buildStageBlocks('债权投资')
}

/** G6 其他债权投资（上市） */
export function buildG6ListedStageBlocks(): G4StageBlock[] {
  return buildStageBlocks('其他债权投资')
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

/**
 * @param defaults 骨架（决定表名 / 损失率列名 / 末列名，**始终以骨架为准**，
 *   避免历史持久化里的旧表名把已修正的模板表名带回去）。默认 G4 上市 6 张。
 */
export function parseStageBlocks(
  raw: string | null | undefined,
  defaults: G4StageBlock[] = buildDefaultStageBlocks(),
): G4StageBlock[] | null {
  if (!raw?.trim()) return null
  try {
    const parsed = JSON.parse(raw)
    if (!parsed?.blocks || !Array.isArray(parsed.blocks)) return null
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
