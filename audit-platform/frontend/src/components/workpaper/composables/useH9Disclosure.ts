/**
 * useH9Disclosure — H9 上市/国企附注披露取数与持久化
 *
 * 取数：H9-1 审定（原值/未确认融资费用）+ H9-2 明细（重分类/利息）
 */
import { ref, watch, type Ref } from 'vue'
import {
  H9_LISTED_KEYS,
  H9_SOE_KEYS,
  createDefaultListedState,
  createDefaultSoeState,
  mapToListedCategoryItem,
  num,
  amt,
  type H9ListedCategoryRow,
  type H9ListedDisclosureState,
  type H9SoeDisclosureState,
  type H9SoeLineRow,
} from './h9DisclosureModel'

function _parseJson(raw: unknown): any {
  if (raw == null) return null
  if (typeof raw === 'object') return raw
  try { return JSON.parse(String(raw)) } catch { return null }
}

function _getRemark(map: Map<string, any>, key: string): string | null {
  const item = map.get(key)
  if (!item) return null
  const raw = item.remark ?? item.conclusion
  return raw != null ? String(raw) : null
}

function _parseH91Rows(map: Map<string, any>): any[] {
  const data = _parseJson(_getRemark(map, 'H9-1-rows'))
  return Array.isArray(data) ? data : []
}

function _parseH92Rows(map: Map<string, any>): any[] {
  const data = _parseJson(_getRemark(map, 'H9-2-rows'))
  return Array.isArray(data) ? data : []
}

function _sumReclass(h92: any[]): number {
  return amt(h92.reduce((s, r) => s + num(r?.reclassification), 0))
}

function _sumInterest(h92: any[]): number {
  return amt(h92.reduce((s, r) => {
    const audited = r?.auditedInterest
    if (audited != null && audited !== '') return s + num(audited)
    return s + num(r?.interestAccrued) + num(r?.interestAje)
  }, 0))
}

function _blockTotals(rows: any[], block: 'liability' | 'unearned') {
  const list = rows.filter((r) => (r?.block === 'unearned' ? 'unearned' : 'liability') === block && !r?.isSubtotal)
  return {
    begin: amt(list.reduce((s, r) => s + num(r.beginBalance), 0)),
    end: amt(list.reduce((s, r) => s + (num(r.audited) || num(r.endBalance)), 0)),
    rje: amt(list.reduce((s, r) => s + num(r.rje), 0)),
    items: list,
  }
}

export function useH9ListedDisclosure(params: {
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params
  const state = ref<H9ListedDisclosureState>(createDefaultListedState())

  function load(): void {
    const next = createDefaultListedState()
    const pack = _parseJson(_getRemark(allResponses.value, H9_LISTED_KEYS.pack))
    if (pack && typeof pack === 'object') {
      if (Array.isArray(pack.rows) && pack.rows.length) {
        next.rows = pack.rows.map((r: any) => ({
          item: String(r.item || ''),
          endBalance: r.endBalance == null || r.endBalance === '' ? null : num(r.endBalance),
          lastYearEnd: r.lastYearEnd == null || r.lastYearEnd === '' ? null : num(r.lastYearEnd),
        }))
      }
      if (pack.withinOneYear) {
        next.withinOneYear = {
          end: pack.withinOneYear.end == null || pack.withinOneYear.end === '' ? null : num(pack.withinOneYear.end),
          last: pack.withinOneYear.last == null || pack.withinOneYear.last === '' ? null : num(pack.withinOneYear.last),
        }
      }
      if (pack.interest && typeof pack.interest === 'object') {
        next.interest = {
          total: pack.interest.total == null || pack.interest.total === '' ? null : num(pack.interest.total),
          financeExpense: pack.interest.financeExpense == null || pack.interest.financeExpense === ''
            ? null
            : num(pack.interest.financeExpense),
          capitalized: pack.interest.capitalized == null || pack.interest.capitalized === ''
            ? null
            : num(pack.interest.capitalized),
          year: String(pack.interest.year || next.interest.year),
        }
      }
      // 兼容旧版仅存 interestNote 字符串
      if (typeof pack.interestNote === 'string' && pack.interestNote.trim()) {
        next.interestNoteOverride = pack.interestNote
      }
      if (typeof pack.interestNoteOverride === 'string') {
        next.interestNoteOverride = pack.interestNoteOverride
      }
    }
    next.auditNote = _getRemark(allResponses.value, H9_LISTED_KEYS.auditNote) || ''
    next.auditConclusion = _getRemark(allResponses.value, H9_LISTED_KEYS.auditConclusion) || ''
    state.value = next
  }

  watch(allResponses, () => load(), { immediate: true })

  function persist(): void {
    if (!onSave) return
    onSave(H9_LISTED_KEYS.pack, {
      rows: state.value.rows,
      withinOneYear: state.value.withinOneYear,
      interest: state.value.interest,
      interestNoteOverride: state.value.interestNoteOverride,
    })
    onSave(H9_LISTED_KEYS.auditNote, state.value.auditNote)
    onSave(H9_LISTED_KEYS.auditConclusion, state.value.auditConclusion)
  }

  /** 从 H9-1 / H9-2 带入 */
  function pullFromSources(): { message: string } {
    const h91 = _parseH91Rows(allResponses.value)
    const h92 = _parseH92Rows(allResponses.value)
    const liab = _blockTotals(h91, 'liability')
    const parts: string[] = []

    if (liab.items.length) {
      const agg = new Map<string, { end: number; begin: number }>()
      for (const r of liab.items) {
        const item = mapToListedCategoryItem(String(r.name || ''))
        const cur = agg.get(item) || { end: 0, begin: 0 }
        cur.end += num(r.audited) || num(r.endBalance)
        cur.begin += num(r.beginBalance)
        agg.set(item, cur)
      }
      const rows: H9ListedCategoryRow[] = []
      for (const [item, v] of agg) {
        rows.push({ item, endBalance: amt(v.end), lastYearEnd: amt(v.begin) })
      }
      // 保留默认空类目占位（无金额的仍显示）
      for (const d of createDefaultListedState().rows) {
        if (!rows.some((r) => r.item === d.item)) rows.push({ ...d })
      }
      state.value.rows = rows
      parts.push(`H9-1 分类 ${agg.size} 项`)
    }

    const reclass = _sumReclass(h92)
    const rje = liab.rje
    const withinEnd = reclass !== 0 ? reclass : rje
    if (withinEnd !== 0 || h92.length) {
      state.value.withinOneYear = {
        ...state.value.withinOneYear,
        end: withinEnd,
      }
      parts.push(reclass !== 0 ? 'H9-2 一年内重分类' : (rje !== 0 ? 'H9-1 RJE' : '一年内到期'))
    }

    const interestTotal = _sumInterest(h92)
    if (interestTotal !== 0 || h92.length) {
      state.value.interest = {
        ...state.value.interest,
        total: interestTotal,
        financeExpense: interestTotal,
        capitalized: state.value.interest.capitalized ?? 0,
      }
      // 取数后清掉旧覆盖，改用结构化生成
      state.value.interestNoteOverride = ''
      parts.push('H9-2 利息')
    }

    if (!parts.length) {
      return { message: '未找到 H9-1/H9-2 可带入数据，请先编制审定表或明细表' }
    }
    persist()
    return { message: `已从 ${parts.join('、')} 带入` }
  }

  function updateCategory(index: number, field: 'item' | 'endBalance' | 'lastYearEnd', value: any): void {
    const row = state.value.rows[index]
    if (!row) return
    if (field === 'item') row.item = String(value ?? '')
    else row[field] = value == null || value === '' ? null : num(value)
    persist()
  }

  function updateWithin(field: 'end' | 'last', value: any): void {
    state.value.withinOneYear[field] = value == null || value === '' ? null : num(value)
    persist()
  }

  function addCategory(item?: string): void {
    state.value.rows.push({
      item: item?.trim() || '其他',
      endBalance: null,
      lastYearEnd: null,
    })
    persist()
  }

  function removeCategory(index: number): void {
    if (state.value.rows.length <= 1) return
    state.value.rows.splice(index, 1)
    persist()
  }

  return {
    state,
    load,
    persist,
    pullFromSources,
    updateCategory,
    updateWithin,
    addCategory,
    removeCategory,
  }
}

export function useH9SoeDisclosure(params: {
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params
  const state = ref<H9SoeDisclosureState>(createDefaultSoeState())

  function load(): void {
    const next = createDefaultSoeState()
    const pack = _parseJson(_getRemark(allResponses.value, H9_SOE_KEYS.pack))
    if (pack && typeof pack === 'object') {
      if (Array.isArray(pack.rows) && pack.rows.length) {
        const byKey = new Map<string, H9SoeLineRow>()
        for (const d of next.rows) byKey.set(d.key, { ...d })
        for (const r of pack.rows) {
          const key = (r.key as H9SoeLineRow['key'])
            || (String(r.item || '').includes('未确认')
              ? 'unearned'
              : String(r.item || '').includes('一年内') || String(r.item || '').includes('重分类')
                ? 'reclass'
                : 'payment')
          byKey.set(key, {
            key,
            item: String(r.item || byKey.get(key)?.item || ''),
            endBalance: r.endBalance == null || r.endBalance === '' ? null : num(r.endBalance),
            beginBalance: r.beginBalance == null || r.beginBalance === '' ? null : num(r.beginBalance),
          })
        }
        next.rows = createDefaultSoeState().rows.map((d) => byKey.get(d.key) || { ...d })
      }
      if (typeof pack.supplementNote === 'string') next.supplementNote = pack.supplementNote
    }
    next.auditNote = _getRemark(allResponses.value, H9_SOE_KEYS.auditNote) || ''
    next.auditConclusion = _getRemark(allResponses.value, H9_SOE_KEYS.auditConclusion) || ''
    state.value = next
  }

  watch(allResponses, () => load(), { immediate: true })

  function persist(): void {
    if (!onSave) return
    onSave(H9_SOE_KEYS.pack, {
      rows: state.value.rows,
      supplementNote: state.value.supplementNote,
    })
    onSave(H9_SOE_KEYS.auditNote, state.value.auditNote)
    onSave(H9_SOE_KEYS.auditConclusion, state.value.auditConclusion)
  }

  function pullFromSources(): { message: string } {
    const h91 = _parseH91Rows(allResponses.value)
    const h92 = _parseH92Rows(allResponses.value)
    const liab = _blockTotals(h91, 'liability')
    const unearned = _blockTotals(h91, 'unearned')
    const reclass = _sumReclass(h92)
    const parts: string[] = []

    if (h91.length) {
      for (const row of state.value.rows) {
        if (row.key === 'payment') {
          row.endBalance = liab.end
          row.beginBalance = liab.begin
        } else if (row.key === 'unearned') {
          row.endBalance = unearned.end
          row.beginBalance = unearned.begin
        }
      }
      parts.push('H9-1 原值/未确认融资费用')
    }

    if (h92.length || reclass !== 0 || liab.rje !== 0) {
      const reclassRow = state.value.rows.find((r) => r.key === 'reclass')
      if (reclassRow) {
        reclassRow.endBalance = reclass !== 0 ? reclass : liab.rje
      }
      parts.push(reclass !== 0 ? 'H9-2 重分类' : '一年内到期')
    }

    if (!parts.length) {
      return { message: '未找到 H9-1/H9-2 可带入数据，请先编制审定表或明细表' }
    }
    persist()
    return { message: `已从 ${parts.join('、')} 带入` }
  }

  function updateLine(index: number, field: 'endBalance' | 'beginBalance', value: any): void {
    const row = state.value.rows[index]
    if (!row) return
    row[field] = value == null || value === '' ? null : num(value)
    persist()
  }

  return { state, load, persist, pullFromSources, updateLine }
}
