/**
 * H1 附注披露 JSON 导入导出包（上市 / 国企）
 * 对齐 H1-5 PolicyCheck 的 versioned pack 模式。
 */

import { H1_LISTED_ITEM } from './h1ListedDisclosureModel'
import { H1_SOE_KEYS } from './h1SoeDisclosureModel'

export const H1_LISTED_PACK_VERSION = 1
export const H1_SOE_PACK_VERSION = 1

export interface H1ListedDisclosurePack {
  version: typeof H1_LISTED_PACK_VERSION
  variant: 'listed'
  exportedAt: string
  summary: unknown
  categories: unknown
  movement: unknown
  idle: unknown
  leaseOut: unknown
  titleCert: unknown
  clearing: unknown
  mortgage: unknown
  govSubsidy: unknown
  notes: {
    impairment: string
    mortgage: string
    sale: string
    clearing: string
  }
}

export interface H1SoeDisclosurePack {
  version: typeof H1_SOE_PACK_VERSION
  variant: 'soe'
  exportedAt: string
  summary: unknown
  movement: unknown
  idle: unknown
  title: unknown
  clearing: unknown
  clearingNote: string
}

export function buildListedDisclosurePack(data: Omit<H1ListedDisclosurePack, 'version' | 'variant' | 'exportedAt'>): H1ListedDisclosurePack {
  return {
    version: H1_LISTED_PACK_VERSION,
    variant: 'listed',
    exportedAt: new Date().toISOString(),
    ...data,
  }
}

export function buildSoeDisclosurePack(data: Omit<H1SoeDisclosurePack, 'version' | 'variant' | 'exportedAt'>): H1SoeDisclosurePack {
  return {
    version: H1_SOE_PACK_VERSION,
    variant: 'soe',
    exportedAt: new Date().toISOString(),
    ...data,
  }
}

export function parseListedDisclosurePack(raw: unknown): { ok: true; pack: H1ListedDisclosurePack } | { ok: false; message: string } {
  const pack = raw as Partial<H1ListedDisclosurePack>
  if (!pack || pack.version !== H1_LISTED_PACK_VERSION) {
    return { ok: false, message: '无效的上市附注导出包（需要 version=1）' }
  }
  if (pack.variant && pack.variant !== 'listed') {
    return { ok: false, message: '导出包 variant 不是 listed' }
  }
  return { ok: true, pack: pack as H1ListedDisclosurePack }
}

export function parseSoeDisclosurePack(raw: unknown): { ok: true; pack: H1SoeDisclosurePack } | { ok: false; message: string } {
  const pack = raw as Partial<H1SoeDisclosurePack>
  if (!pack || pack.version !== H1_SOE_PACK_VERSION) {
    return { ok: false, message: '无效的国企附注导出包（需要 version=1）' }
  }
  if (pack.variant && pack.variant !== 'soe') {
    return { ok: false, message: '导出包 variant 不是 soe' }
  }
  return { ok: true, pack: pack as H1SoeDisclosurePack }
}

/** 上市包写入 checklist 键（仅新键） */
export function listedPackPersistEntries(pack: H1ListedDisclosurePack): Array<{ itemId: string; value: unknown }> {
  return [
    { itemId: H1_LISTED_ITEM.summary, value: pack.summary },
    { itemId: H1_LISTED_ITEM.categories, value: pack.categories },
    { itemId: H1_LISTED_ITEM.movement, value: pack.movement },
    { itemId: H1_LISTED_ITEM.idle, value: pack.idle },
    { itemId: H1_LISTED_ITEM.leaseOut, value: pack.leaseOut },
    { itemId: H1_LISTED_ITEM.titleCert, value: pack.titleCert },
    { itemId: H1_LISTED_ITEM.clearing, value: pack.clearing },
    { itemId: H1_LISTED_ITEM.mortgageRows, value: pack.mortgage },
    { itemId: H1_LISTED_ITEM.govSubsidy, value: pack.govSubsidy },
    { itemId: H1_LISTED_ITEM.noteImpairment, value: pack.notes?.impairment ?? '' },
    { itemId: H1_LISTED_ITEM.noteMortgage, value: pack.notes?.mortgage ?? '' },
    { itemId: H1_LISTED_ITEM.noteSale, value: pack.notes?.sale ?? '' },
    { itemId: H1_LISTED_ITEM.noteClearing, value: pack.notes?.clearing ?? '' },
  ]
}

/** 国企包写入 checklist 键（H1-soe-*） */
export function soePackPersistEntries(pack: H1SoeDisclosurePack): Array<{ itemId: string; value: unknown }> {
  return [
    { itemId: H1_SOE_KEYS.summary, value: pack.summary },
    { itemId: H1_SOE_KEYS.movement, value: pack.movement },
    { itemId: H1_SOE_KEYS.idle, value: pack.idle },
    { itemId: H1_SOE_KEYS.title, value: pack.title },
    { itemId: H1_SOE_KEYS.clearing, value: pack.clearing },
    { itemId: H1_SOE_KEYS.clearingNote, value: pack.clearingNote ?? '' },
  ]
}

export function downloadJsonPack(filename: string, pack: unknown): void {
  const blob = new Blob([JSON.stringify(pack, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
