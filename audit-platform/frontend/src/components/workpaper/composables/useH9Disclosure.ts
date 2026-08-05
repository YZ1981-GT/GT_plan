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
        // 🔴 迁移零丢数 + 不撞键：
        //    ① 已有 `rowId` 的**原样保留**（改造后的行、改名过的行都靠它定位）；
        //    ② 历史行（改造前只有 label）补一个**不与现存 rowId 冲突**的新号 ——
        //       不能按索引补 `H9-listed-{i+1}`：删掉前几行后剩下的行会被改号，
        //       与将来新增的行撞键，按 rowId 查行会命中错行。
        const used = new Set<string>(
          pack.rows.map((r: any) => String(r?.rowId ?? '')).filter(Boolean),
        )
        let seq = 0
        const allocate = (): string => {
          do {
            seq += 1
          } while (used.has(`H9-listed-${seq}`))
          const id = `H9-listed-${seq}`
          used.add(id)
          return id
        }
        next.rows = pack.rows.map((r: any) => ({
          rowId: String(r.rowId || allocate()),
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

  /**
   * 新增租赁类别行（源模板 `A8:A10` 是空白自由列示区，行数由实际数据决定）。
   *
   * 🔴 **撞名拒绝**：附注同步按行标签匹配，同名行会互相覆盖丢数据。
   * 🔴 **稳定 key 用 `rowId` 不用 label** —— 改名不丢数据、同名不撞键。
   *
   * @returns ``{ ok, message }``；`ok=false` 时调用方须提示且不落库。
   */
  function addCategory(item?: string): { ok: boolean; message: string } {
    const name = (item ?? '').trim()
    if (!name) {
      return { ok: false, message: '请输入租赁类别名称' }
    }
    if (state.value.rows.some((r) => String(r.item ?? '').trim() === name)) {
      return { ok: false, message: `已存在同名类别「${name}」，请换一个名称` }
    }
    state.value.rows.push({
      rowId: nextListedRowId(state.value.rows),
      item: name,
      endBalance: null,
      lastYearEnd: null,
    })
    persist()
    return { ok: true, message: `已新增「${name}」` }
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

/**
 * 生成下一个稳定行 key（`H9-listed-{seq}`）。
 *
 * 取现存最大 seq + 1，**不用行数** —— 删中间行后行数会回退导致 key 重用，
 * 让新行"继承"被删行的持久化数据。
 */
export function nextListedRowId(rows: readonly { rowId?: string }[]): string {
  let max = 0
  for (const r of rows || []) {
    const m = /^H9-listed-(\d+)$/.exec(String(r?.rowId ?? ''))
    if (m) max = Math.max(max, Number(m[1]) || 0)
  }
  return `H9-listed-${max + 1}`
}

/**
 * 生成下一个国企侧续加扣减项 key（`H9-soe-extra-{seq}`）。
 *
 * 对应源模板 `A11` 的 `……` 可续扣减行。
 */
export function nextSoeExtraRowId(rows: readonly { rowId?: string }[]): string {
  let max = 0
  for (const r of rows || []) {
    const m = /^H9-soe-extra-(\d+)$/.exec(String(r?.rowId ?? ''))
    if (m) max = Math.max(max, Number(m[1]) || 0)
  }
  return `H9-soe-extra-${max + 1}`
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
        // 🔴 固定三行按 key 去重合并；`extra` 行**必须按 rowId 保留全部**
        //    （按 key 去重会把 N 个续加扣减项压成一行 → 丢数据）
        const byKey = new Map<string, H9SoeLineRow>()
        for (const d of next.rows) byKey.set(d.key, { ...d })
        const extras: H9SoeLineRow[] = []
        for (const r of pack.rows) {
          const key = (r.key as H9SoeLineRow['key'])
            || (String(r.item || '').includes('未确认')
              ? 'unearned'
              : String(r.item || '').includes('一年内') || String(r.item || '').includes('重分类')
                ? 'reclass'
                : 'payment')
          const row: H9SoeLineRow = {
            key,
            item: String(r.item || byKey.get(key)?.item || ''),
            endBalance: r.endBalance == null || r.endBalance === '' ? null : num(r.endBalance),
            beginBalance: r.beginBalance == null || r.beginBalance === '' ? null : num(r.beginBalance),
          }
          if (key === 'extra') {
            row.rowId = String(r.rowId || nextSoeExtraRowId(extras))
            extras.push(row)
          } else {
            byKey.set(key, row)
          }
        }
        next.rows = [
          ...createDefaultSoeState().rows.map((d) => byKey.get(d.key) || { ...d }),
          ...extras,
        ]
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

  /** 续加扣减项也允许改名（固定三行不可改，源模板行名是准则用语） */
  function updateExtraItem(index: number, value: any): { ok: boolean; message: string } {
    const row = state.value.rows[index]
    if (!row || row.key !== 'extra') {
      return { ok: false, message: '仅续加扣减项可改名' }
    }
    const name = String(value ?? '').trim()
    if (!name) return { ok: false, message: '名称不能为空' }
    if (state.value.rows.some((r, i) => i !== index && String(r.item ?? '').trim() === name)) {
      return { ok: false, message: `已存在同名行「${name}」` }
    }
    row.item = name
    persist()
    return { ok: true, message: '' }
  }

  /**
   * 续加扣减项（源模板 `A11` 的 `……` 可续行）。
   *
   * 固定三行（`payment` / `unearned` / `reclass`）是准则规定项不可增删；
   * 本函数只在其后追加 `extra` 行。
   */
  function addExtraDeduction(item?: string): { ok: boolean; message: string } {
    const name = (item ?? '').trim()
    if (!name) return { ok: false, message: '请输入扣减项名称' }
    if (state.value.rows.some((r) => String(r.item ?? '').trim() === name)) {
      return { ok: false, message: `已存在同名行「${name}」，请换一个名称` }
    }
    state.value.rows.push({
      key: 'extra',
      rowId: nextSoeExtraRowId(state.value.rows),
      item: name,
      endBalance: null,
      beginBalance: null,
    } as H9SoeLineRow)
    persist()
    return { ok: true, message: `已新增扣减项「${name}」` }
  }

  /** 删除续加扣减项（固定三行拒绝删除） */
  function removeExtraDeduction(index: number): { ok: boolean; message: string } {
    const row = state.value.rows[index]
    if (!row) return { ok: false, message: '行不存在' }
    if (row.key !== 'extra') {
      return { ok: false, message: '源模板固定行不可删除' }
    }
    state.value.rows.splice(index, 1)
    persist()
    return { ok: true, message: '已删除' }
  }

  return {
    state,
    load,
    persist,
    pullFromSources,
    updateLine,
    updateExtraItem,
    addExtraDeduction,
    removeExtraDeduction,
  }
}
