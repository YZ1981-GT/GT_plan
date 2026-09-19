/**
 * K1 底稿内行级跳转（K1-1 ↔ K1-2/5/7/8/10/11/12）
 */
import { ref, type InjectionKey, type Ref } from 'vue'
import { relatedPartyNameMatches } from './useF1RelatedParty'
import { comboNamesMatch } from './k1PolicyCrossHelpers'
import { K1_PORTFOLIO_ROW_DEFS } from './k1AdjudicationModel'

export type K1NavSheet = 'K1-1' | 'K1-2' | 'K1-5' | 'K1-7' | 'K1-8' | 'K1-10' | 'K1-11' | 'K1-12'

export type K1CalcSection = 'single' | 'credit' | 'aging'

export interface K1RowFocusTarget {
  sheet: K1NavSheet
  rowId?: string
  counterparty?: string
  /** 来源表编码，用于目标表提示条 */
  sourceSheet?: string
  /** K1-12：优先定位的测试区段 */
  section?: 'occurrence' | 'post'
  /** K1-1 ↔ K1-8 组合名称 */
  portfolioLabel?: string
  groupId?: string
  calcSection?: K1CalcSection
}

export interface K1RowNavigation {
  highlightRowId: Ref<string>
  navigateToRow: (target: K1RowFocusTarget) => void
  navigateToDetailRow: (target: Omit<K1RowFocusTarget, 'sheet'> & { sheet?: 'K1-2' }) => void
  consumeFocus: (sheet: K1NavSheet) => K1RowFocusTarget | null
  focusRow: (rowId: string) => void
  rowHighlightClass: (rowId: string) => string
}

export const K1RowNavigationKey: InjectionKey<K1RowNavigation> = Symbol('k1RowNavigation')

const SHEET_LABEL: Record<K1NavSheet, string> = {
  'K1-1': '审定表K1-1',
  'K1-2': 'K1-2 明细表',
  'K1-5': 'K1-5',
  'K1-7': 'K1-7',
  'K1-8': '坏账准备测算K1-8',
  'K1-10': 'K1-10',
  'K1-11': 'K1-11',
  'K1-12': 'K1-12',
}

/** 按 rowId / 名称模糊匹配目标行（通用） */
export function resolveK1NamedFocusRow(
  rows: Array<{ id: string }>,
  focus: Pick<K1RowFocusTarget, 'rowId' | 'counterparty'>,
  nameOf: (row: { id: string }) => string,
): { rowId: string; counterparty: string } | null {
  if (focus.rowId) {
    const byId = rows.find((r) => r.id === focus.rowId)
    if (byId) return { rowId: byId.id, counterparty: nameOf(byId) }
  }
  const name = String(focus.counterparty ?? '').trim()
  if (name) {
    const byName = rows.find((r) => relatedPartyNameMatches(nameOf(r), name))
    if (byName) return { rowId: byName.id, counterparty: nameOf(byName) }
    return { rowId: '', counterparty: name }
  }
  return null
}

/** 根据 rowId / 往来对象名称解析 K1-2 目标行 */
export function resolveK1DetailFocusRow(
  rows: Array<{ id: string; counterparty: string }>,
  focus: K1RowFocusTarget,
): { rowId: string; counterparty: string } | null {
  return resolveK1NamedFocusRow(rows, focus, (r) => (r as { counterparty: string }).counterparty)
}

/** K1-1 组合行 label → rowKey */
export function resolveK11PortfolioRowKey(portfolioLabel: string): string | null {
  const label = portfolioLabel.trim()
  if (!label) return null
  const def = K1_PORTFOLIO_ROW_DEFS.find((d) => comboNamesMatch(d.label, label))
  return def?.rowKey ?? null
}

function parseK18Payload(map: Map<string, any>): Record<string, any> | null {
  const raw = map.get('K1-8-bad-debt-calc')?.remark
  if (!raw) return null
  try {
    return typeof raw === 'string' ? JSON.parse(raw) : raw
  } catch {
    return null
  }
}

/** K1-8 组合名称 → groupId + section */
export function resolveK18GroupFocus(
  map: Map<string, any>,
  portfolioLabel: string,
): { groupId: string; calcSection: K1CalcSection } | null {
  const payload = parseK18Payload(map)
  if (!payload) return null
  const label = portfolioLabel.trim()
  if (!label) return null

  if (comboNamesMatch(label, '单项计提')) {
    const first = payload.singleRows?.[0]
    if (first?.rowId) return { groupId: String(first.rowId), calcSection: 'single' }
  }

  for (const g of payload.creditGroups ?? []) {
    const name = String(g.groupName ?? '')
    if (comboNamesMatch(name, label) || comboNamesMatch(label, '押金') || comboNamesMatch(label, '保证金')) {
      return { groupId: String(g.groupId), calcSection: 'credit' }
    }
  }

  for (const g of payload.agingGroups ?? []) {
    if (comboNamesMatch(String(g.groupName ?? ''), label)) {
      return { groupId: String(g.groupId), calcSection: 'aging' }
    }
  }

  if (comboNamesMatch(label, '账龄组合') && payload.agingGroups?.[0]) {
    return { groupId: String(payload.agingGroups[0].groupId), calcSection: 'aging' }
  }
  if (comboNamesMatch(label, '其他组合') && payload.agingGroups?.length) {
    const last = payload.agingGroups[payload.agingGroups.length - 1]
    return { groupId: String(last.groupId), calcSection: 'aging' }
  }

  return null
}

/** 目标表 onMounted 时消费 pending focus 并回调 */
export function applyK1IncomingFocus(opts: {
  sheet: K1NavSheet
  k1Nav: K1RowNavigation | null
  rows: Array<{ id: string }>
  nameOf: (row: { id: string }) => string
  onResolved: (resolved: { rowId: string; counterparty: string }, focus: K1RowFocusTarget) => void
}): void {
  const focus = opts.k1Nav?.consumeFocus(opts.sheet)
  if (!focus) return
  const resolved = resolveK1NamedFocusRow(opts.rows, focus, opts.nameOf)
  if (!resolved) return
  opts.onResolved(resolved, focus)
}

export function buildK1DeeplinkHint(focus: K1RowFocusTarget, counterparty: string): string {
  const from = focus.sourceSheet ? `${focus.sourceSheet} 跳转定位` : '跨表跳转定位'
  return `${from}：${counterparty}`
}

export function buildK1PortfolioDeeplinkHint(focus: K1RowFocusTarget): string {
  const from = focus.sourceSheet ? `${focus.sourceSheet} 跳转` : '跨表跳转'
  const label = focus.portfolioLabel ?? focus.counterparty ?? ''
  return `${from}：${label}`
}

export function createK1RowNavigation(
  emitNavigate: (sheetName: string) => void,
): K1RowNavigation {
  const pendingFocus = ref<K1RowFocusTarget | null>(null)
  const highlightRowId = ref('')
  let clearTimer: ReturnType<typeof setTimeout> | null = null

  function flashRow(rowId: string): void {
    if (!rowId) return
    highlightRowId.value = rowId
    if (clearTimer) clearTimeout(clearTimer)
    clearTimer = setTimeout(() => {
      if (highlightRowId.value === rowId) highlightRowId.value = ''
    }, 5000)
  }

  function navigateToRow(target: K1RowFocusTarget): void {
    pendingFocus.value = { ...target }
    emitNavigate(SHEET_LABEL[target.sheet])
  }

  function navigateToDetailRow(
    target: Omit<K1RowFocusTarget, 'sheet'> & { sheet?: 'K1-2' },
  ): void {
    navigateToRow({
      sheet: target.sheet ?? 'K1-2',
      rowId: target.rowId,
      counterparty: target.counterparty,
      sourceSheet: target.sourceSheet,
      section: target.section,
    })
  }

  function consumeFocus(sheet: K1NavSheet): K1RowFocusTarget | null {
    const f = pendingFocus.value
    if (!f || f.sheet !== sheet) return null
    pendingFocus.value = null
    return f
  }

  function focusRow(rowId: string): void {
    flashRow(rowId)
  }

  function rowHighlightClass(rowId: string): string {
    return highlightRowId.value && highlightRowId.value === rowId ? 'k1-row-deeplink-hl' : ''
  }

  return {
    highlightRowId,
    navigateToRow,
    navigateToDetailRow,
    consumeFocus,
    focusRow,
    rowHighlightClass,
  }
}
