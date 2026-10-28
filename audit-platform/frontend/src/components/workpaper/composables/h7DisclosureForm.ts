/**
 * H7 生产性生物资产披露表：从 checklist 响应读回 Tab 状态 + 「同步到附注」快照。
 *
 * 底稿披露 Tab（`H7TabDisclosureListed` / `H7TabDisclosureSoe`）与附注页离屏同步共用（spec note-pull-followup-closure R1）：
 * 两个 Tab 原在组件里内联 `hydrate` 的解析与 `syncToNotes` 的快照，原样抽到这里，Tab 与离屏 provider 调同一份。
 */
import {
  H7_LISTED_KEYS,
  createDefaultH7Categories,
  emptyMovement,
  type H7ListedCategory,
  type H7ListedSyncSnapshot,
  type MovementCellMap,
} from './h7ListedDisclosureModel'
import {
  H7_SOE_INDUSTRIES,
  H7_SOE_KEYS,
  createDefaultSoeBlocks,
  type H7SoeIndustryBlock,
  type H7SoeSyncSnapshot,
} from './h7SoeDisclosureModel'

type ResponseMap = ReadonlyMap<string, { remark?: string | null; conclusion?: string | null } | undefined>

export const H7_LISTED_NOTE_KEYS = ['listed-policy', 'listed-impairment', 'listed-supplement'] as const
export type H7ListedNoteKey = (typeof H7_LISTED_NOTE_KEYS)[number]
export const H7_LISTED_NOTE_ITEM_ID: Record<H7ListedNoteKey, string> = {
  'listed-policy': H7_LISTED_KEYS.notePolicy,
  'listed-impairment': H7_LISTED_KEYS.noteImpairment,
  'listed-supplement': H7_LISTED_KEYS.noteSupplement,
}

export const H7_SOE_NOTE_KEYS = ['soe-policy', 'soe-fair-basis', 'soe-supplement'] as const
export type H7SoeNoteKey = (typeof H7_SOE_NOTE_KEYS)[number]
export const H7_SOE_NOTE_ITEM_ID: Record<H7SoeNoteKey, string> = {
  'soe-policy': H7_SOE_KEYS.notePolicy,
  'soe-fair-basis': H7_SOE_KEYS.noteFairBasis,
  'soe-supplement': H7_SOE_KEYS.noteSupplement,
}

function readRaw(responses: ResponseMap, itemId: string): string {
  const item = responses.get(itemId)
  return String(item?.remark ?? item?.conclusion ?? '')
}

function parseJson<T>(raw: string, fallback: T): T {
  if (!raw.trim()) return fallback
  try {
    const v = JSON.parse(raw)
    return (v && typeof v === 'object') ? (v as T) : fallback
  } catch { return fallback }
}

export interface H7ListedForm {
  categories: H7ListedCategory[]
  cost: MovementCellMap
  fair: MovementCellMap
  noteTexts: Record<H7ListedNoteKey, string>
}

/** 上市 Tab 的 `hydrate`：类别列 / 两张变动表 / 三段说明 */
export function readH7ListedForm(responses: ResponseMap): H7ListedForm {
  const cats = parseJson<H7ListedCategory[]>(readRaw(responses, H7_LISTED_KEYS.categories), [])
  const noteTexts = {} as Record<H7ListedNoteKey, string>
  for (const k of H7_LISTED_NOTE_KEYS) noteTexts[k] = readRaw(responses, H7_LISTED_NOTE_ITEM_ID[k])
  return {
    categories: Array.isArray(cats) && cats.length ? cats : createDefaultH7Categories(),
    cost: parseJson<MovementCellMap>(readRaw(responses, H7_LISTED_KEYS.cost), emptyMovement()),
    fair: parseJson<MovementCellMap>(readRaw(responses, H7_LISTED_KEYS.fair), emptyMovement()),
    noteTexts,
  }
}

/** 上市 Tab `syncToNotes` 的快照 */
export function h7ListedSyncSnapshot(form: {
  categories: H7ListedCategory[]
  cost: MovementCellMap
  fair: MovementCellMap
  noteTexts: Record<string, string>
}): H7ListedSyncSnapshot {
  return {
    categories: form.categories,
    cost: form.cost,
    fair: form.fair,
    notePolicy: form.noteTexts['listed-policy'] || '',
    noteImpairment: form.noteTexts['listed-impairment'] || '',
    noteSupplement: form.noteTexts['listed-supplement'] || '',
  }
}

/** 国企两张表的反序列化：缺失产业按源模板四类补空块，顺序归一 */
export function parseH7SoeBlocks(raw: string): H7SoeIndustryBlock[] {
  if (!raw.trim()) return createDefaultSoeBlocks()
  try {
    const v = JSON.parse(raw)
    if (!Array.isArray(v)) return createDefaultSoeBlocks()
    return H7_SOE_INDUSTRIES.map((ind) => {
      const hit = v.find((b: any) => b?.key === ind.key)
      return {
        key: ind.key,
        selfAmounts: {
          begin: Number(hit?.selfAmounts?.begin) || 0,
          increase: Number(hit?.selfAmounts?.increase) || 0,
          decrease: Number(hit?.selfAmounts?.decrease) || 0,
        },
        categories: Array.isArray(hit?.categories)
          ? hit.categories.map((c: any) => ({
              id: String(c?.id ?? ''),
              name: String(c?.name ?? ''),
              begin: Number(c?.begin) || 0,
              increase: Number(c?.increase) || 0,
              decrease: Number(c?.decrease) || 0,
            })).filter((c: any) => c.id && c.name)
          : [],
      }
    })
  } catch { return createDefaultSoeBlocks() }
}

export interface H7SoeForm {
  cost: H7SoeIndustryBlock[]
  fair: H7SoeIndustryBlock[]
  noteTexts: Record<H7SoeNoteKey, string>
}

/** 国企 Tab 的 `hydrate`：成本 / 公允两张表 + 三段说明 */
export function readH7SoeForm(responses: ResponseMap): H7SoeForm {
  const noteTexts = {} as Record<H7SoeNoteKey, string>
  for (const k of H7_SOE_NOTE_KEYS) noteTexts[k] = readRaw(responses, H7_SOE_NOTE_ITEM_ID[k])
  return {
    cost: parseH7SoeBlocks(readRaw(responses, H7_SOE_KEYS.cost)),
    fair: parseH7SoeBlocks(readRaw(responses, H7_SOE_KEYS.fair)),
    noteTexts,
  }
}

/** 国企 Tab `syncToNotes` 的快照 */
export function h7SoeSyncSnapshot(form: {
  cost: H7SoeIndustryBlock[]
  fair: H7SoeIndustryBlock[]
  noteTexts: Record<string, string>
}): H7SoeSyncSnapshot {
  return {
    cost: form.cost,
    fair: form.fair,
    notePolicy: form.noteTexts['soe-policy'] || '',
    noteFairBasis: form.noteTexts['soe-fair-basis'] || '',
    noteSupplement: form.noteTexts['soe-supplement'] || '',
  }
}
