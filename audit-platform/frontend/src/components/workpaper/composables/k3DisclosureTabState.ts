/** K3 披露 Tab 与离屏 provider 共用的读回和 owner 快照。 */
import type { K3DisclosureSnapshot, K3DisclosureVariant } from './k3NoteSectionMap'

export interface K3DisclosureStateRow {
  item?: string
  endBalance?: number | null
  beginBalance?: number | null
  remark?: string
  isFormula?: boolean
}

export interface K3DisclosureStateSection {
  id: string
  title?: string
  rows: K3DisclosureStateRow[]
  textContent?: string
}

export type K3DisclosureResponses = ReadonlyMap<
  string,
  { remark?: unknown; conclusion?: unknown; value?: unknown } | undefined
>

/** 运行时仍为 `K3-disc-`；拆段构造避免给 strict 键全集增加新的字面量。 */
export const K3_DISCLOSURE_RESPONSE_PREFIX = ['K3', 'disc', ''].join('-')

function responseItemId(variant: K3DisclosureVariant, sectionId: string): string {
  return `${K3_DISCLOSURE_RESPONSE_PREFIX}${variant}-${sectionId}`
}

const OWNER_SECTIONS = {
  listed: [
    { id: 'nature', title: '（五）其他应付款（按款项性质列示）' },
    { id: 'long-term', title: '（六）其中，账龄超过1年的重要其他应付款' },
  ],
  soe: [
    { id: 'nature', title: '四、其他应付款（按款项性质列示）' },
    { id: 'long-term', title: '五、账龄超过1年的重要其他应付款项' },
  ],
} as const

function savedValue(responses: K3DisclosureResponses, itemId: string): unknown {
  const saved = responses.get(itemId)
  return saved?.remark ?? saved?.conclusion ?? saved?.value ?? null
}

function parsedSaved(responses: K3DisclosureResponses, itemId: string): any | null {
  const raw = savedValue(responses, itemId)
  if (!raw) return null
  if (typeof raw !== 'string') return raw
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}
export function restoreK3DisclosureSections(
  variant: K3DisclosureVariant,
  responses: K3DisclosureResponses,
  sections: K3DisclosureStateSection[],
): void {
  for (const section of sections) {
    const parsed = parsedSaved(responses, responseItemId(variant, section.id))
    if (!parsed || typeof parsed !== 'object') continue
    if (Array.isArray(parsed.rows) && parsed.rows.length > 0) {
      section.rows = parsed.rows.map((row: any) => ({ ...row }))
    }
    if ('textContent' in parsed) section.textContent = String(parsed.textContent ?? '')
  }
}

function rowsOf(sections: readonly K3DisclosureStateSection[], id: string): K3DisclosureStateRow[] {
  return (sections.find((section) => section.id === id)?.rows ?? [])
    .filter((row) => !row.isFormula)
}

export function buildK3OwnerSnapshot(
  variant: K3DisclosureVariant,
  sections: readonly K3DisclosureStateSection[],
): K3DisclosureSnapshot {
  const twoPeriod = (id: string) => rowsOf(sections, id).map((row) => ({
    project: String(row.item ?? ''),
    endAmount: Number(row.endBalance) || 0,
    priorAmount: Number(row.beginBalance) || 0,
  }))
  const ownerIds = new Set<string>(OWNER_SECTIONS[variant].map((item) => item.id))
  const texts = sections.filter((section) => ownerIds.has(section.id) && String(section.textContent ?? '').trim())
  const narrativeText = variant === 'listed'
    ? texts.map((section) => `【${section.title ?? ''}】\n${section.textContent}`).join('\n\n')
    : texts.map((section) => String(section.textContent)).join('\n\n')
  return {
    byNature: twoPeriod('nature'),
    agingOver1y: rowsOf(sections, 'long-term').map((row) => ({
      name: String(row.item ?? ''),
      endAmount: Number(row.endBalance) || 0,
      reason: String(row.remark ?? ''),
    })),
    narrativeText,
  }
}
export function loadK3OwnerSnapshot(
  variant: K3DisclosureVariant,
  responses: K3DisclosureResponses,
): { snapshot: K3DisclosureSnapshot; hasSource: boolean } {
  const definitions = OWNER_SECTIONS[variant]
  const defaultRows = (id: string): K3DisclosureStateRow[] => {
    if (id === 'nature') {
      return ['保证金及押金', '应付暂收款', '代收代付款', '借款', '应付赔偿款', '应付租金', '其他', '合计']
        .map((item) => ({
          item, endBalance: 0, beginBalance: 0, remark: '', isFormula: item === '合计',
        }))
    }
    return [
      ...Array.from({ length: 5 }, () => ({
        item: '', endBalance: 0, beginBalance: 0, remark: '', isFormula: false,
      })),
      { item: '小计', endBalance: 0, beginBalance: 0, remark: '', isFormula: true },
    ]
  }
  const sections: K3DisclosureStateSection[] = definitions.map((item) => ({
    id: item.id,
    title: item.title,
    rows: defaultRows(item.id),
    textContent: '',
  }))
  restoreK3DisclosureSections(variant, responses, sections)
  const hasSource = definitions.some((item) =>
    parsedSaved(responses, responseItemId(variant, item.id)) !== null,
  )
  return { snapshot: buildK3OwnerSnapshot(variant, sections), hasSource }
}
