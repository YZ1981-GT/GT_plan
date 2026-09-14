/**
 * H7 生产性生物资产 附注披露（国有企业）数据模型
 *
 * 源模板 `H7 生产性生物资产.xlsx` / `附注披露信息（国有企业）`：
 * 两张 5 列单级表（项目 / 期初账面价值 / 本期增加额 / 本期减少额 / 期末账面价值），
 * 行 = 4 个产业行（R9/R12/R15/R18）+ 每产业「其中：N．」可扩类别行 + 合计（R21）。
 *
 * 源模板 R11/R14/R17/R20 的 `……` 是**行形态的「可继续加行」标记**，在动态类别行模型下
 * 不需要（每个类别行都有真实名称）→ 模板 seed 删除。这与**上市**表里的 `……`
 * 不同：上市那三处在模型里有对应的 `*_ellipsis` 键、参与小计，必须保留。
 *
 * spec: h7-biological-assets-disclosure-rebuild (Task 3)
 */
import { H7_INDUSTRIES, num, type H7IndustryKey } from './h7ListedDisclosureModel'

/** 源模板 R9/R12/R15/R18 的行标签（带中文序号） */
export const H7_SOE_INDUSTRIES = [
  { key: 'crop', label: '一、种植业', shortLabel: '种植业' },
  { key: 'livestock', label: '二、畜牧养殖业', shortLabel: '畜牧养殖业' },
  { key: 'forestry', label: '三、林业', shortLabel: '林业' },
  { key: 'aquatic', label: '四、水产业', shortLabel: '水产业' },
] as const satisfies readonly { key: H7IndustryKey; label: string; shortLabel: string }[]

/** 源模板 R21 合计行字面（模板 JSON 归一为「合计」） */
export const H7_SOE_TOTAL_LABEL = '合计'

/** 源模板 R10 首个类别槽位字面（seed 用；实际录入时审计师输入真实类别名） */
export const H7_SOE_CATEGORY_SEED_LABEL = '其中：1．'

export interface H7SoeAmounts {
  begin: number
  increase: number
  decrease: number
}

export interface H7SoeCategory extends H7SoeAmounts {
  /** 稳定 id（`{industryKey}-{seq}`，seq 不复用） */
  id: string
  /** 类别名称（新增时必须先输入，平台交互铁律） */
  name: string
}

export interface H7SoeIndustryBlock {
  key: H7IndustryKey
  /** 无类别行时该产业自身可直接录入的金额 */
  selfAmounts: H7SoeAmounts
  categories: H7SoeCategory[]
}

export function emptyAmounts(): H7SoeAmounts {
  return { begin: 0, increase: 0, decrease: 0 }
}

export function createDefaultSoeBlocks(): H7SoeIndustryBlock[] {
  return H7_SOE_INDUSTRIES.map((ind) => ({
    key: ind.key,
    selfAmounts: emptyAmounts(),
    categories: [],
  }))
}

/** 期末账面价值 = 期初 + 增 − 减（**恒派生，不持久化**） */
export function soeEnd(a: H7SoeAmounts): number {
  return num(a.begin) + num(a.increase) - num(a.decrease)
}

/** 产业行金额：有类别行取类别之和（只读派生），无类别行取自身录入值 */
export function industryTotals(block: H7SoeIndustryBlock): H7SoeAmounts {
  if (!block.categories.length) {
    return {
      begin: num(block.selfAmounts.begin),
      increase: num(block.selfAmounts.increase),
      decrease: num(block.selfAmounts.decrease),
    }
  }
  return block.categories.reduce<H7SoeAmounts>(
    (acc, c) => ({
      begin: acc.begin + num(c.begin),
      increase: acc.increase + num(c.increase),
      decrease: acc.decrease + num(c.decrease),
    }),
    emptyAmounts(),
  )
}

/** 该产业行是否可直接录入（无类别行时可录，有类别行时只读派生） */
export function isIndustryEditable(block: H7SoeIndustryBlock): boolean {
  return block.categories.length === 0
}

/** 合计 = 4 个产业行之和 */
export function grandTotal(blocks: readonly H7SoeIndustryBlock[]): H7SoeAmounts {
  return blocks.reduce<H7SoeAmounts>((acc, b) => {
    const t = industryTotals(b)
    return {
      begin: acc.begin + t.begin,
      increase: acc.increase + t.increase,
      decrease: acc.decrease + t.decrease,
    }
  }, emptyAmounts())
}

/** 为某产业分配下一个不冲突的类别 id（seq 取最大值 +1，不复用已删除的） */
export function nextSoeCategoryId(
  block: H7SoeIndustryBlock,
  industry: H7IndustryKey,
): string {
  const prefix = `${industry}-`
  let max = 0
  for (const c of block.categories) {
    if (!c.id.startsWith(prefix)) continue
    const seq = Number(c.id.slice(prefix.length))
    if (Number.isFinite(seq) && seq > max) max = seq
  }
  return `${prefix}${max + 1}`
}

export type H7SoeRowKind = 'industry' | 'category' | 'total'

export interface H7SoeDisplayRow {
  label: string
  begin: number
  increase: number
  decrease: number
  /** 派生列 */
  end: number
  kind: H7SoeRowKind
  industryKey?: H7IndustryKey
  categoryId?: string
  /** 产业行是否可直接录入（无类别行时） */
  editable: boolean
}

/** 行序：4 产业（各自后跟其类别行）+ 合计 —— 与源模板 R9–R21 同构 */
export function buildSoeDisplayRows(
  blocks: readonly H7SoeIndustryBlock[],
): H7SoeDisplayRow[] {
  const out: H7SoeDisplayRow[] = []
  for (const ind of H7_SOE_INDUSTRIES) {
    const block = blocks.find((b) => b.key === ind.key)
      || { key: ind.key, selfAmounts: emptyAmounts(), categories: [] as H7SoeCategory[] }
    const t = industryTotals(block)
    out.push({
      label: ind.label,
      begin: t.begin,
      increase: t.increase,
      decrease: t.decrease,
      end: soeEnd(t),
      kind: 'industry',
      industryKey: ind.key,
      editable: isIndustryEditable(block),
    })
    for (const c of block.categories) {
      out.push({
        label: c.name,
        begin: num(c.begin),
        increase: num(c.increase),
        decrease: num(c.decrease),
        end: soeEnd(c),
        kind: 'category',
        industryKey: ind.key,
        categoryId: c.id,
        editable: true,
      })
    }
  }
  const g = grandTotal(blocks)
  out.push({
    label: H7_SOE_TOTAL_LABEL,
    begin: g.begin,
    increase: g.increase,
    decrease: g.decrease,
    end: soeEnd(g),
    kind: 'total',
    editable: false,
  })
  return out
}

/** 产业 key → 源模板行标签 */
export function soeIndustryLabel(key: string): string {
  return H7_SOE_INDUSTRIES.find((i) => i.key === key)?.label || String(key)
}

/** 与上市模型共享的 4 产业口径（防两侧漂移） */
export function assertIndustryParity(): boolean {
  return H7_SOE_INDUSTRIES.every((s, i) => s.key === H7_INDUSTRIES[i].key)
}

export interface H7SoeSyncSnapshot {
  cost: H7SoeIndustryBlock[]
  fair: H7SoeIndustryBlock[]
  notePolicy: string
  noteFairBasis: string
  noteSupplement: string
}

/** 持久化键（checklist_responses item_id） */
export const H7_SOE_KEYS = {
  cost: 'H7-disc-soe-cost',
  fair: 'H7-disc-soe-fair',
  notePolicy: 'H7-disc-soe-policy',
  noteFairBasis: 'H7-disc-soe-fair-basis',
  noteSupplement: 'H7-disc-soe-text',
} as const

/** 源模板红字（R22/R23/R39/R40）作方法论上下文 / placeholder */
export const H7_SOE_GUIDANCE = {
  supplement:
    '①各类生物资产的期末实物数量，如有天然起源的生物资产，还应披露该资产的类别、取得方式和数量等。'
    + '②各类生产性生物资产的预计使用寿命、预计净残值、折旧方法、累计折旧和减值准备累计金额。',
  fairBasis: '注：应披露公允价值确认依据。',
  risk: '（3）说明生产性生物资产相关的风险情况与管理措施。',
} as const
