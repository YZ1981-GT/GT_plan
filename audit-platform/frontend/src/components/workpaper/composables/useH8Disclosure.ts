/**
 * useH8Disclosure — H8 上市/国企附注披露取数与持久化
 *
 * 从 H8-1 审定 / H8-2 明细 / H8-10 减值 / H8-13 简化 带入；持久化 checklist_responses。
 */
import { ref, watch, type Ref } from 'vue'
import {
  H8_LISTED_DEFAULT_CATEGORIES,
  H8_LISTED_KEYS,
  mapToListedCategoryKey,
  num,
  setCell,
  type H8ListedCategory,
  type MovementCellMap,
} from './h8ListedDisclosureModel'
import {
  H8_SOE_CATEGORIES,
  H8_SOE_KEYS,
  createDefaultSoeLayers,
  mapToSoeCategoryKey,
  recomputeDerivedLayers,
  type H8SoeLayerBlock,
} from './h8SoeDisclosureModel'
import { H810_ROWS_KEY } from './useH8Impairment'

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

/** H8-10 按披露类别汇总：⑦已提 → 期初；⑧补提 → 本期计提 */
export interface H810ImpairmentAgg {
  begin: number
  provision: number
  required: number
}

export function aggregateH810ImpairmentByCategory(
  rows: any[],
  mapCat: (name: string) => string,
): { byCat: Record<string, H810ImpairmentAgg>; noteDraft: string; rowCount: number } {
  const byCat: Record<string, H810ImpairmentAgg> = {}
  const indicationLines: string[] = []
  let rowCount = 0
  let totalSupplement = 0
  let totalRequired = 0
  let tested = 0

  for (const r of rows) {
    if (!r || typeof r !== 'object') continue
    const name = String(r.assetName || r.contractNo || '').trim()
    const already = num(r.alreadyProvided)
    const supplement = num(r.supplement)
    const required = num(r.impairmentAmount)
    const has = r.hasIndication === 'Y' || r.hasIndication === '是' || r.hasIndication === true
    // 跳过完全空行
    if (!name && !already && !supplement && !required && !has) continue
    rowCount++
    tested++
    const key = mapCat(String(r.assetName || r.contractNo || r.leaseType || r.assetCategory || ''))
    if (!byCat[key]) byCat[key] = { begin: 0, provision: 0, required: 0 }
    byCat[key].begin += already
    // 优先⑧补提；若未算补提但⑥>⑦，用差额兜底
    const prov = supplement > 0
      ? supplement
      : Math.max(required - already, 0)
    byCat[key].provision += prov
    byCat[key].required += required
    totalSupplement += prov
    totalRequired += required
    if (has) {
      const desc = String(r.indicationDesc || '').trim()
      indicationLines.push(
        `· ${name || key}${desc ? `：${desc}` : '（有减值迹象）'}；应提 ${required.toFixed(2)}，已提 ${already.toFixed(2)}，补提 ${prov.toFixed(2)}`,
      )
    }
  }

  const fmt = (n: number) => n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  let noteDraft = ''
  if (rowCount > 0) {
    noteDraft = `本期对 ${tested} 项使用权资产执行减值测试（来源 H8-10）。本期补提减值准备合计 ${fmt(totalSupplement)} 元；按可收回金额计算的应有减值准备合计 ${fmt(totalRequired)} 元。`
    if (indicationLines.length) {
      noteDraft += `\n有减值迹象项目：\n${indicationLines.join('\n')}`
    } else {
      noteDraft += '\n本期未发现重大减值迹象；即使未计提减值，亦已按准则要求执行测试（可收回金额方法见 H8-11）。'
    }
    noteDraft += '\n可收回金额按公允价值减处置费用与预计未来现金流量现值孰高确定，关键参数及与以前年度差异（如有）详见 H8-11。'
  }

  return { byCat, noteDraft, rowCount }
}

function _applyH810ToListedMovement(
  map: MovementCellMap,
  byCat: Record<string, H810ImpairmentAgg>,
  categoryKeys: Set<string>,
): { map: MovementCellMap; applied: number } {
  let applied = 0
  let next = { ...map }
  for (const [key, a] of Object.entries(byCat)) {
    if (!categoryKeys.has(key)) continue
    next = setCell(next, 'imp_begin', key, a.begin)
    next = setCell(next, 'imp_inc_provision', key, a.provision)
    applied++
  }
  return { map: next, applied }
}

export function useH8ListedDisclosure(params: {
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params
  const categories = ref<H8ListedCategory[]>([...H8_LISTED_DEFAULT_CATEGORIES])
  const movement = ref<MovementCellMap>({})
  const noteShortLow = ref('')
  const noteImpairment = ref('')
  const auditNote = ref('')
  const auditConclusion = ref('')

  function load(): void {
    const catRaw = _parseJson(_getRemark(allResponses.value, H8_LISTED_KEYS.categories))
    if (Array.isArray(catRaw) && catRaw.length) {
      categories.value = catRaw.map((c: any) => ({
        key: String(c.key || ''),
        label: String(c.label || c.key || ''),
      })).filter((c: H8ListedCategory) => c.key)
    } else {
      categories.value = [...H8_LISTED_DEFAULT_CATEGORIES]
    }
    const mov = _parseJson(_getRemark(allResponses.value, H8_LISTED_KEYS.movement))
    movement.value = mov && typeof mov === 'object' ? mov : {}
    noteShortLow.value = _getRemark(allResponses.value, H8_LISTED_KEYS.noteShortLow) || ''
    noteImpairment.value = _getRemark(allResponses.value, H8_LISTED_KEYS.noteImpairment) || ''
    auditNote.value = _getRemark(allResponses.value, H8_LISTED_KEYS.auditNote) || ''
    auditConclusion.value = _getRemark(allResponses.value, H8_LISTED_KEYS.auditConclusion) || ''
  }

  watch(allResponses, () => load(), { immediate: true })

  function persist(): void {
    if (!onSave) return
    onSave(H8_LISTED_KEYS.categories, categories.value)
    onSave(H8_LISTED_KEYS.movement, movement.value)
    onSave(H8_LISTED_KEYS.noteShortLow, noteShortLow.value)
    onSave(H8_LISTED_KEYS.noteImpairment, noteImpairment.value)
    onSave(H8_LISTED_KEYS.auditNote, auditNote.value)
    onSave(H8_LISTED_KEYS.auditConclusion, auditConclusion.value)
  }

  function updateMovement(rowKey: string, catKey: string, value: number): void {
    movement.value = setCell(movement.value, rowKey, catKey, value)
    persist()
  }

  function addCategory(label: string): void {
    const key = `cat_${Date.now().toString(36)}`
    categories.value = [...categories.value, { key, label: label.trim() || '其他' }]
    persist()
  }

  function removeCategory(key: string): void {
    if (H8_LISTED_DEFAULT_CATEGORIES.some((c) => c.key === key)) return
    categories.value = categories.value.filter((c) => c.key !== key)
    persist()
  }

  /** 从 H8-1 / H8-2 / H8-10 / H8-13 带入 */
  function pullFromSources(): { message: string } {
    let moved = 0
    const parts: string[] = []
    const h81 = _parseJson(_getRemark(allResponses.value, 'H8-1-rows'))
    const h82 = _parseJson(_getRemark(allResponses.value, 'H8-2-rows'))

    // H8-2 按类别汇总
    if (Array.isArray(h82) && h82.length) {
      const agg: Record<string, { costBegin: number; costInc: number; costDec: number; depBegin: number; depInc: number; depDec: number }> = {}
      for (const r of h82) {
        const key = mapToListedCategoryKey(String(r.leaseType || r.assetName || r.assetCategory || ''))
        if (!agg[key]) agg[key] = { costBegin: 0, costInc: 0, costDec: 0, depBegin: 0, depInc: 0, depDec: 0 }
        const init = num(r.initialAmount ?? r.h9InitialAmount)
        const beginCost = num(r.beginCost ?? r.costBegin)
        const accBegin = num(r.accDepBegin)
        const depCur = num(r.depCurrentPeriod ?? r.currentDep)
        const accEnd = num(r.accDepEnd ?? r.accDep)
        agg[key].costBegin += beginCost > 0 ? beginCost : 0
        // 无期初原值时：用入账值近似作本期租入增加
        if (beginCost <= 0 && init > 0) agg[key].costInc += init
        else if (init > beginCost && beginCost > 0) agg[key].costInc += init - beginCost
        else if (beginCost <= 0 && init <= 0) { /* skip */ }
        else agg[key].costInc += Math.max(num(r.debitAmount), 0)
        agg[key].costDec += Math.max(num(r.creditAmount), 0)
        agg[key].depBegin += accBegin
        agg[key].depInc += depCur > 0 ? depCur : Math.max(accEnd - accBegin, 0)
        agg[key].depDec += Math.max(accBegin + (depCur || 0) - accEnd, 0)
      }
      let map = { ...movement.value }
      for (const [key, a] of Object.entries(agg)) {
        if (!categories.value.some((c) => c.key === key)) continue
        map = setCell(map, 'cost_begin', key, a.costBegin)
        map = setCell(map, 'cost_inc_lease', key, a.costInc)
        map = setCell(map, 'cost_dec_other', key, a.costDec)
        map = setCell(map, 'dep_begin', key, a.depBegin)
        map = setCell(map, 'dep_inc_provision', key, a.depInc)
        map = setCell(map, 'dep_dec_other', key, a.depDec)
        moved++
      }
      movement.value = map
      parts.push('H8-2')
    } else if (Array.isArray(h81) && h81.length) {
      // 无明细时：审定表合计落入「其他」
      const costRows = h81.filter((r: any) => r.block === 'cost' && !r.isSubtotal)
      const depRows = h81.filter((r: any) => r.block === 'accDep' && !r.isSubtotal)
      let map = { ...movement.value }
      const put = (rowKey: string, catKey: string, v: number) => {
        map = setCell(map, rowKey, catKey, v)
      }
      if (costRows.length === 1) {
        const r = costRows[0]
        const cat = mapToListedCategoryKey(String(r.name || ''))
        put('cost_begin', cat, num(r.beginBalance))
        put('cost_inc_lease', cat, num(r.debitAmount))
        put('cost_dec_other', cat, num(r.creditAmount))
        moved++
      } else {
        for (const r of costRows) {
          const cat = mapToListedCategoryKey(String(r.name || ''))
          put('cost_begin', cat, num(r.beginBalance) + num(movement.value.cost_begin?.[cat]))
          put('cost_inc_lease', cat, num(r.debitAmount) + num(movement.value.cost_inc_lease?.[cat]))
          put('cost_dec_other', cat, num(r.creditAmount) + num(movement.value.cost_dec_other?.[cat]))
          moved++
        }
      }
      for (const r of depRows) {
        const cat = mapToListedCategoryKey(String(r.name || ''))
        put('dep_begin', cat, num(r.beginBalance) + num(movement.value.dep_begin?.[cat]))
        put('dep_inc_provision', cat, num(r.creditAmount) + num(movement.value.dep_inc_provision?.[cat]))
        put('dep_dec_other', cat, num(r.debitAmount) + num(movement.value.dep_dec_other?.[cat]))
        moved++
      }
      movement.value = map
      parts.push('H8-1')
    }

    // H8-10 减值明细 → 减值准备期初/本期计提 + 披露说明
    const h810 = _parseJson(_getRemark(allResponses.value, H810_ROWS_KEY))
    if (Array.isArray(h810) && h810.length) {
      const { byCat, noteDraft, rowCount } = aggregateH810ImpairmentByCategory(h810, mapToListedCategoryKey)
      if (rowCount > 0) {
        const catKeys = new Set(categories.value.map((c) => c.key))
        const applied = _applyH810ToListedMovement(movement.value, byCat, catKeys)
        movement.value = applied.map
        moved += applied.applied
        if (noteDraft) {
          noteImpairment.value = noteDraft
          moved++
        }
        parts.push('H8-10')
      }
    }

    // H8-13 简化费用提示
    const h813 = _parseJson(_getRemark(allResponses.value, 'H8-13-rows'))
    if (Array.isArray(h813) && h813.length) {
      const expense = h813
        .filter((r: any) => r.simplifiedType && r.simplifiedType !== '不符合')
        .reduce((s: number, r: any) => s + num(r.expectedExpense || r.bookExpense || r.annualRental), 0)
      if (expense > 0 && !noteShortLow.value.trim()) {
        noteShortLow.value = `本期确认短期租赁/低价值资产租赁相关费用 ${expense.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} 元（来源 H8-13），详见附注五、82。`
        moved++
        parts.push('H8-13')
      }
    }

    persist()
    const src = parts.length ? parts.join('/') : 'H8-1/H8-2/H8-10'
    return {
      message: moved
        ? `已从 ${src} 带入（更新 ${moved} 处）`
        : 'H8-1/H8-2/H8-10 暂无可带入数据，请先完成审定、明细或减值测算',
    }
  }

  return {
    categories,
    movement,
    noteShortLow,
    noteImpairment,
    auditNote,
    auditConclusion,
    load,
    persist,
    updateMovement,
    addCategory,
    removeCategory,
    pullFromSources,
  }
}

export function useH8SoeDisclosure(params: {
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params
  const layers = ref<H8SoeLayerBlock[]>(createDefaultSoeLayers())
  const noteImpairment = ref('')
  const auditNote = ref('')
  const auditConclusion = ref('')

  function load(): void {
    const raw = _parseJson(_getRemark(allResponses.value, H8_SOE_KEYS.layers))
    if (Array.isArray(raw) && raw.length) {
      layers.value = recomputeDerivedLayers(raw as H8SoeLayerBlock[])
    } else {
      layers.value = createDefaultSoeLayers()
    }
    noteImpairment.value = _getRemark(allResponses.value, H8_SOE_KEYS.noteImpairment) || ''
    auditNote.value = _getRemark(allResponses.value, H8_SOE_KEYS.auditNote) || ''
    auditConclusion.value = _getRemark(allResponses.value, H8_SOE_KEYS.auditConclusion) || ''
  }

  watch(allResponses, () => load(), { immediate: true })

  function persist(): void {
    if (!onSave) return
    onSave(H8_SOE_KEYS.layers, layers.value)
    onSave(H8_SOE_KEYS.noteImpairment, noteImpairment.value)
    onSave(H8_SOE_KEYS.auditNote, auditNote.value)
    onSave(H8_SOE_KEYS.auditConclusion, auditConclusion.value)
  }

  function updateCell(layer: string, catKey: string, field: 'begin' | 'increase' | 'decrease', value: number): void {
    const next = layers.value.map((l) => {
      if (l.layer !== layer) return l
      return {
        ...l,
        categories: l.categories.map((c) =>
          c.key === catKey ? { ...c, [field]: num(value) } : c,
        ),
      }
    })
    layers.value = recomputeDerivedLayers(next)
    persist()
  }

  function pullFromSources(): { message: string } {
    const h82 = _parseJson(_getRemark(allResponses.value, 'H8-2-rows'))
    const h81 = _parseJson(_getRemark(allResponses.value, 'H8-1-rows'))
    const h810 = _parseJson(_getRemark(allResponses.value, H810_ROWS_KEY))
    let moved = 0
    const parts: string[] = []
    const base = createDefaultSoeLayers()
    const cost = base.find((l) => l.layer === 'cost')!
    const dep = base.find((l) => l.layer === 'dep')!
    const impair = base.find((l) => l.layer === 'impair')!

    const bump = (
      block: H8SoeLayerBlock,
      catKey: string,
      field: 'begin' | 'increase' | 'decrease',
      v: number,
    ) => {
      const c = block.categories.find((x) => x.key === catKey)
      if (!c) return
      c[field] = num(c[field]) + num(v)
      moved++
    }

    if (Array.isArray(h82) && h82.length) {
      for (const r of h82) {
        const key = mapToSoeCategoryKey(String(r.leaseType || r.assetName || ''))
        const init = num(r.initialAmount ?? r.h9InitialAmount)
        const beginCost = num(r.beginCost ?? r.costBegin)
        bump(cost, key, 'begin', beginCost)
        bump(cost, key, 'increase', beginCost > 0 ? Math.max(init - beginCost, 0) : init)
        bump(dep, key, 'begin', num(r.accDepBegin))
        bump(dep, key, 'increase', num(r.depCurrentPeriod ?? r.currentDep))
        // 明细上的减值字段若有则先带；随后 H8-10 覆盖为权威值
        bump(impair, key, 'begin', num(r.impairmentBegin))
        bump(impair, key, 'increase', num(r.impairmentCurrent))
      }
      parts.push('H8-2')
    } else if (Array.isArray(h81) && h81.length) {
      for (const r of h81) {
        if (r.isSubtotal) continue
        const key = mapToSoeCategoryKey(String(r.name || ''))
        if (r.block === 'cost') {
          bump(cost, key, 'begin', num(r.beginBalance))
          bump(cost, key, 'increase', num(r.debitAmount))
          bump(cost, key, 'decrease', num(r.creditAmount))
        } else if (r.block === 'accDep') {
          bump(dep, key, 'begin', num(r.beginBalance))
          bump(dep, key, 'increase', num(r.creditAmount))
          bump(dep, key, 'decrease', num(r.debitAmount))
        }
      }
      parts.push('H8-1')
    }

    // H8-10 权威覆盖减值层（⑦→期初，⑧→本期增加）
    if (Array.isArray(h810) && h810.length) {
      const { byCat, noteDraft, rowCount } = aggregateH810ImpairmentByCategory(h810, mapToSoeCategoryKey)
      if (rowCount > 0) {
        for (const c of impair.categories) {
          c.begin = 0
          c.increase = 0
          c.decrease = 0
          c.end = 0
        }
        for (const [key, a] of Object.entries(byCat)) {
          const cell = impair.categories.find((x) => x.key === key)
          if (!cell) continue
          cell.begin = a.begin
          cell.increase = a.provision
          moved++
        }
        if (noteDraft) {
          noteImpairment.value = noteDraft
          moved++
        }
        parts.push('H8-10')
      }
    }

    layers.value = recomputeDerivedLayers(base)
    persist()
    const src = parts.length ? parts.join('/') : 'H8-1/H8-2/H8-10'
    return {
      message: moved
        ? `已从 ${src} 带入（更新 ${moved} 处）`
        : 'H8-1/H8-2/H8-10 暂无可带入数据',
    }
  }

  return {
    layers,
    noteImpairment,
    auditNote,
    auditConclusion,
    categories: H8_SOE_CATEGORIES,
    load,
    persist,
    updateCell,
    pullFromSources,
  }
}
