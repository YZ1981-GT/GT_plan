/**
 * useI1Disclosure — I1 上市/国企附注披露取数与持久化
 *
 * 从 I1-2 / I1-9 / I1-6 / I1-8 / I1-12 带入；金额覆盖、文字保留；
 * 审定勾稽 + 同步前校验；数据资源子表；分类精简/全量。
 */
import { computed, ref, watch, type Ref } from 'vue'
import {
  I1_LISTED_DEFAULT_CATEGORIES,
  I1_LISTED_KEYS,
  mapCostDecreaseMethod,
  mapCostIncreaseMethod,
  mapToI1ListedCategoryKey,
  num,
  setCell,
  type I1ImportantItemRow,
  type I1ListedCategory,
  type I1TitleCertRow,
  type MovementCellMap,
} from './i1ListedDisclosureModel'
import {
  I1_SOE_CATEGORIES,
  I1_SOE_KEYS,
  addI1SoeCategory,
  createDefaultI1SoeLayers,
  mapToI1SoeCategoryKey,
  // 🔴 曾漏这一行 ⇒ 国企版披露 tab 挂载即崩「maxI1SoeCustomSeq is not defined」。
  //    vitest（测的是 model 层，自己 import 了）/ vite transform（单文件编译不解析
  //    跨模块符号）/ get_diagnostics 四层全绿，只有浏览器实测暴露。见下方 487/546 行用法。
  maxI1SoeCustomSeq,
  recomputeI1SoeDerivedLayers,
  removeI1SoeCategory,
  type I1SoeCategoryMove,
  type I1SoeLayerBlock,
} from './i1SoeDisclosureModel'
import {
  I1_LISTED_COMPACT_CATEGORIES,
  aggregateI19AmortAlloc,
  buildI1ListedCrossCheck,
  buildI1SoeCrossCheck,
  draftImpairmentNoteFromI112,
  draftMortgageNoteFromI18,
  draftSaleNoteFromI16,
  draftTitleRowsFromI18,
  emptyDataResourceMove,
  fillNoteIfEmpty,
  formatAmortAllocNote,
  preferAuditedAmount,
  pullDataResourceFromListedMovement,
  readI1AdjAudited,
  validateI1ListedPrep,
  validateI1SoePrep,
  type I1AmortAllocSummary,
  type I1DataResourceMove,
  type I1ListedCategoryPreset,
} from './i1DisclosureEnhance'

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

function _loadRows(map: Map<string, any>, key: string): any[] {
  const raw = _parseJson(_getRemark(map, key))
  return Array.isArray(raw) ? raw : []
}

const DATA_RESOURCE_KEY = 'I1-listed-data-resource'
const CATEGORY_PRESET_KEY = 'I1-listed-category-preset'
const AMORT_ALLOC_KEY = 'I1-listed-amort-alloc'
const SOE_AMORT_ALLOC_KEY = 'I1-soe-amort-alloc'
// 🔴 自定义类别单调计数器（持久化）：防「删掉最大号后 max 回退 → 下一个 key 复用已删序号」
// （Property 23 / R7.6）。只增不减，删类别不回退它。
const SOE_CAT_SEQ_KEY = 'I1-soe-cat-seq'

// ─── Listed ──────────────────────────────────────────────────────────────────

export function useI1ListedDisclosure(params: {
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params
  const categoryPreset = ref<I1ListedCategoryPreset>('full')
  const categories = ref<I1ListedCategory[]>([...I1_LISTED_DEFAULT_CATEGORIES])
  const movement = ref<MovementCellMap>({})
  const noteRdRatio = ref('')
  const noteIndefinite = ref('')
  const noteMortgage = ref('')
  const noteImpairment = ref('')
  const noteSale = ref('')
  const noteImportant = ref('')
  const noteDataResource = ref('')
  const titleCertRows = ref<I1TitleCertRow[]>([])
  const importantRows = ref<I1ImportantItemRow[]>([])
  const dataResource = ref<I1DataResourceMove>(emptyDataResourceMove())
  const amortAlloc = ref<I1AmortAllocSummary>(aggregateI19AmortAlloc([]))
  const auditNote = ref('')
  const auditConclusion = ref('')

  function load(): void {
    const preset = (_getRemark(allResponses.value, CATEGORY_PRESET_KEY) || 'full') as I1ListedCategoryPreset
    categoryPreset.value = preset === 'compact' ? 'compact' : 'full'
    const catRaw = _parseJson(_getRemark(allResponses.value, I1_LISTED_KEYS.categories))
    if (Array.isArray(catRaw) && catRaw.length) {
      categories.value = catRaw.map((c: any) => ({
        key: String(c.key || ''),
        label: String(c.label || c.key || ''),
      })).filter((c: I1ListedCategory) => c.key)
    } else {
      categories.value = categoryPreset.value === 'compact'
        ? [...I1_LISTED_COMPACT_CATEGORIES]
        : [...I1_LISTED_DEFAULT_CATEGORIES]
    }
    const mov = _parseJson(_getRemark(allResponses.value, I1_LISTED_KEYS.movement))
    movement.value = mov && typeof mov === 'object' ? mov : {}
    noteRdRatio.value = _getRemark(allResponses.value, I1_LISTED_KEYS.noteRdRatio) || ''
    noteIndefinite.value = _getRemark(allResponses.value, I1_LISTED_KEYS.noteIndefinite) || ''
    noteMortgage.value = _getRemark(allResponses.value, I1_LISTED_KEYS.noteMortgage) || ''
    noteImpairment.value = _getRemark(allResponses.value, I1_LISTED_KEYS.noteImpairment) || ''
    noteSale.value = _getRemark(allResponses.value, I1_LISTED_KEYS.noteSale) || ''
    noteImportant.value = _getRemark(allResponses.value, I1_LISTED_KEYS.noteImportant) || ''
    const titleRaw = _parseJson(_getRemark(allResponses.value, I1_LISTED_KEYS.titleCertRows))
    titleCertRows.value = Array.isArray(titleRaw) ? titleRaw : []
    const impRaw = _parseJson(_getRemark(allResponses.value, I1_LISTED_KEYS.importantRows))
    importantRows.value = Array.isArray(impRaw) ? impRaw : []
    const dr = _parseJson(_getRemark(allResponses.value, DATA_RESOURCE_KEY))
    dataResource.value = dr && typeof dr === 'object' ? { ...emptyDataResourceMove(), ...dr } : emptyDataResourceMove()
    noteDataResource.value = String(dataResource.value.note || '')
    const aa = _parseJson(_getRemark(allResponses.value, AMORT_ALLOC_KEY))
    amortAlloc.value = aa && typeof aa === 'object' ? { ...aggregateI19AmortAlloc([]), ...aa } : aggregateI19AmortAlloc([])
    auditNote.value = _getRemark(allResponses.value, I1_LISTED_KEYS.auditNote) || ''
    auditConclusion.value = _getRemark(allResponses.value, I1_LISTED_KEYS.auditConclusion) || ''
  }

  watch(allResponses, () => load(), { immediate: true })

  function persist(): void {
    if (!onSave) return
    dataResource.value = { ...dataResource.value, note: noteDataResource.value }
    onSave(CATEGORY_PRESET_KEY, categoryPreset.value)
    onSave(I1_LISTED_KEYS.categories, categories.value)
    onSave(I1_LISTED_KEYS.movement, movement.value)
    onSave(I1_LISTED_KEYS.noteRdRatio, noteRdRatio.value)
    onSave(I1_LISTED_KEYS.noteIndefinite, noteIndefinite.value)
    onSave(I1_LISTED_KEYS.noteMortgage, noteMortgage.value)
    onSave(I1_LISTED_KEYS.noteImpairment, noteImpairment.value)
    onSave(I1_LISTED_KEYS.noteSale, noteSale.value)
    onSave(I1_LISTED_KEYS.noteImportant, noteImportant.value)
    onSave(I1_LISTED_KEYS.titleCertRows, titleCertRows.value)
    onSave(I1_LISTED_KEYS.importantRows, importantRows.value)
    onSave(DATA_RESOURCE_KEY, dataResource.value)
    onSave(AMORT_ALLOC_KEY, amortAlloc.value)
    onSave(I1_LISTED_KEYS.auditNote, auditNote.value)
    onSave(I1_LISTED_KEYS.auditConclusion, auditConclusion.value)
  }

  const crossCheck = computed(() =>
    buildI1ListedCrossCheck(movement.value, categories.value, readI1AdjAudited(allResponses.value)),
  )

  const prepValidation = computed(() =>
    validateI1ListedPrep({
      movement: movement.value,
      categories: categories.value,
      titleCertRows: titleCertRows.value,
      cross: crossCheck.value,
    }),
  )

  function updateMovement(rowKey: string, catKey: string, value: number): void {
    movement.value = setCell(movement.value, rowKey, catKey, value)
    persist()
  }

  /**
   * 新增自定义类别列（源模板「……」可扩位）。
   *
   * 🔴 撞名拒绝 → 返回 false，与国企版 `addCategory` 同构（调用方据此提示）。
   *    旧实现 `label.trim() || '其他'` 有两个缺陷：
   *    ① 空名/纯空白**兜底成「其他」**，而「其他」是源模板固定类别 ⇒ 静默造出重复列，
   *       违反「不产生无名行」口径（国企版是拒绝，两版行为不一致）；
   *    ② 无撞名检测 ⇒ 同名类别列可无限叠加，而 label 是推附注与交叉核对的匹配键。
   */
  function addCategory(label: string): boolean {
    const trimmed = (label || '').trim()
    if (!trimmed) return false
    if (categories.value.some((c) => String(c.label || '').trim() === trimmed)) return false
    const key = `cat_${Date.now().toString(36)}`
    categories.value = [...categories.value, { key, label: trimmed }]
    persist()
    return true
  }

  function removeCategory(key: string): void {
    const defaults = categoryPreset.value === 'compact' ? I1_LISTED_COMPACT_CATEGORIES : I1_LISTED_DEFAULT_CATEGORIES
    if (defaults.some((c) => c.key === key)) return
    categories.value = categories.value.filter((c) => c.key !== key)
    persist()
  }

  function setCategoryPreset(preset: I1ListedCategoryPreset): void {
    categoryPreset.value = preset
    categories.value = preset === 'compact'
      ? [...I1_LISTED_COMPACT_CATEGORIES]
      : [...I1_LISTED_DEFAULT_CATEGORIES]
    persist()
  }

  function addTitleCertRow(): void {
    titleCertRows.value = [
      ...titleCertRows.value,
      { rowId: `tc-${Date.now()}`, name: '', bookValue: 0, reason: '' },
    ]
    persist()
  }

  function removeTitleCertRow(idx: number): void {
    titleCertRows.value = titleCertRows.value.filter((_, i) => i !== idx)
    persist()
  }

  function addImportantRow(): void {
    importantRows.value = [
      ...importantRows.value,
      { rowId: `imp-${Date.now()}`, name: '', bookValue: 0, remainingAmortMonths: 0 },
    ]
    persist()
  }

  function removeImportantRow(idx: number): void {
    importantRows.value = importantRows.value.filter((_, i) => i !== idx)
    persist()
  }

  function updateDataResource(field: keyof I1DataResourceMove, value: number | string): void {
    dataResource.value = { ...dataResource.value, [field]: value }
    persist()
  }

  /**
   * 从 I1-2/6/8/9/12 带入。
   * 默认：金额覆盖；已填文字说明保留（仅空位补草稿）。
   */
  function pullFromSources(opts?: { overwriteNotes?: boolean }): { message: string; count: number } {
    const overwriteNotes = opts?.overwriteNotes === true
    const detail = _loadRows(allResponses.value, 'I1-2-rows')
    if (!detail.length) {
      return { message: 'I1-2 明细无数据，请先编制明细表', count: 0 }
    }

    const kept = {
      noteRdRatio: noteRdRatio.value,
      noteIndefinite: noteIndefinite.value,
      noteMortgage: noteMortgage.value,
      noteImpairment: noteImpairment.value,
      noteSale: noteSale.value,
      noteImportant: noteImportant.value,
      noteDataResource: noteDataResource.value,
    }

    type Agg = Record<string, number>
    const make = (): Agg => ({})
    const add = (bag: Agg, key: string, v: number) => { bag[key] = (bag[key] || 0) + v }

    const costBegin = make()
    const costInc: Record<string, Agg> = {}
    const costDec: Record<string, Agg> = {}
    const amortBegin = make()
    const amortProv = make()
    const amortOtherInc = make()
    const amortDisp = make()
    const amortOtherDec = make()
    const impBegin = make()
    const impProv = make()
    const impOtherInc = make()
    const impDisp = make()
    const impOtherDec = make()

    let rdCostEnd = 0
    let totalCostEnd = 0
    let mortgaged = 0
    const indefiniteNames: string[] = []
    const titleSeed: I1TitleCertRow[] = []

    for (const r of detail) {
      const cat = mapToI1ListedCategoryKey(String(r.category || r.name || ''))
      if (!categories.value.some((c) => c.key === cat)) continue

      const cBegin = preferAuditedAmount(r, 'auditedCostBegin', 'costBegin')
      const cInc = preferAuditedAmount(r, 'auditedCostIncrease', 'costIncrease')
      const cDec = preferAuditedAmount(r, 'auditedCostDecrease', 'costDecrease')
      const cEnd = preferAuditedAmount(r, 'auditedCostEnd', 'costEnd')
      add(costBegin, cat, cBegin)
      const incKey = mapCostIncreaseMethod(String(r.costIncreaseMethod || ''))
      if (!costInc[incKey]) costInc[incKey] = make()
      add(costInc[incKey], cat, cInc)
      const decKey = mapCostDecreaseMethod(String(r.costDecreaseMethod || ''))
      if (!costDec[decKey]) costDec[decKey] = make()
      add(costDec[decKey], cat, cDec)
      totalCostEnd += cEnd
      if (/内部研发|自行研发/.test(String(r.costIncreaseMethod || '')) || /研发/i.test(String(r.name || ''))) {
        rdCostEnd += cEnd
      }

      add(amortBegin, cat, preferAuditedAmount(r, 'auditedAccAmortBegin', 'accAmortBegin'))
      add(amortProv, cat, num(r.amortProvision))
      add(amortOtherInc, cat, num(r.amortOtherIncrease))
      if (num(r.amortDisposal) || num(r.amortOtherDecrease)) {
        add(amortDisp, cat, num(r.amortDisposal))
        add(amortOtherDec, cat, num(r.amortOtherDecrease))
      } else {
        add(amortDisp, cat, num(r.amortTransferOut))
      }

      add(impBegin, cat, preferAuditedAmount(r, 'auditedImpairmentBegin', 'impairmentBegin'))
      add(impProv, cat, num(r.impairmentProvision))
      add(impOtherInc, cat, num(r.impairOtherIncrease))
      if (num(r.impairDisposal) || num(r.impairOtherDecrease)) {
        add(impDisp, cat, num(r.impairDisposal))
        add(impOtherDec, cat, num(r.impairOtherDecrease))
      } else {
        add(impDisp, cat, num(r.impairmentReversal))
      }

      if (r.indefiniteLife === 'Y' || num(r.usefulLifeMonths) <= 0) {
        indefiniteNames.push(String(r.name || cat))
      }
      if (r.mortgageRestricted === 'Y') mortgaged++
      if (r.hasTitleEvidence === 'N') {
        titleSeed.push({
          rowId: `tc-${r.rowId || Date.now()}`,
          name: String(r.name || ''),
          bookValue: preferAuditedAmount(r, 'auditedNetEnd', 'netValue'),
          reason: '',
        })
      }
    }

    let map: MovementCellMap = {}
    const putAll = (rowKey: string, bag: Agg) => {
      for (const [k, v] of Object.entries(bag)) map = setCell(map, rowKey, k, v)
    }
    putAll('cost_begin', costBegin)
    for (const [rowKey, bag] of Object.entries(costInc)) putAll(rowKey, bag)
    for (const [rowKey, bag] of Object.entries(costDec)) putAll(rowKey, bag)
    putAll('amort_begin', amortBegin)
    putAll('amort_inc_provision', amortProv)
    putAll('amort_inc_other', amortOtherInc)
    putAll('amort_dec_dispose', amortDisp)
    putAll('amort_dec_other', amortOtherDec)
    putAll('imp_begin', impBegin)
    putAll('imp_inc_provision', impProv)
    putAll('imp_inc_other', impOtherInc)
    putAll('imp_dec_dispose', impDisp)
    putAll('imp_dec_other', impOtherDec)
    movement.value = map

    // 数据资源子表：从 data 列回填
    dataResource.value = {
      ...pullDataResourceFromListedMovement(map),
      note: overwriteNotes ? '' : kept.noteDataResource,
    }

    // I1-9 摊销归属
    amortAlloc.value = aggregateI19AmortAlloc(_loadRows(allResponses.value, 'I1-9-rows'))

    // 文字：空位补草稿；overwriteNotes 时强制覆盖自动草稿
    const applyNote = (cur: string, draft: string) =>
      overwriteNotes ? (draft || cur) : fillNoteIfEmpty(cur, draft)

    let rdDraft = ''
    if (totalCostEnd > 0) {
      rdDraft = `本期通过公司内部研发形成的无形资产占无形资产期末账面价值的比例为 ${((rdCostEnd / totalCostEnd) * 100).toFixed(2)}%。`
    }
    noteRdRatio.value = applyNote(kept.noteRdRatio, rdDraft)

    noteIndefinite.value = applyNote(
      kept.noteIndefinite,
      indefiniteNames.length
        ? `使用寿命不确定的无形资产共 ${indefiniteNames.length} 项（${indefiniteNames.slice(0, 5).join('、')}${indefiniteNames.length > 5 ? '等' : ''}），判断依据详见 I1-4/I1-7。`
        : '',
    )

    const i18 = _loadRows(allResponses.value, 'I1-8-rows')
    const mortgageDraft = draftMortgageNoteFromI18(i18)
      || (mortgaged > 0
        ? `明细表中标记抵押受限的无形资产共 ${mortgaged} 项，具体情况见 I1-8 权属检查。`
        : '')
    noteMortgage.value = applyNote(kept.noteMortgage, mortgageDraft)

    noteImpairment.value = applyNote(
      kept.noteImpairment,
      draftImpairmentNoteFromI112(_loadRows(allResponses.value, 'I1-12-rows')),
    )
    noteSale.value = applyNote(
      kept.noteSale,
      draftSaleNoteFromI16(_loadRows(allResponses.value, 'I1-6-rows')),
    )

    const titleFrom8 = draftTitleRowsFromI18(i18)
    if (!titleCertRows.value.length) {
      titleCertRows.value = titleFrom8.length ? titleFrom8 : titleSeed
    } else if (overwriteNotes && titleFrom8.length) {
      titleCertRows.value = titleFrom8
    }

    noteDataResource.value = applyNote(
      kept.noteDataResource,
      Math.abs(dataResource.value.costBegin) + Math.abs(dataResourceCostInc(dataResource.value)) > 0.005
        ? '确认为无形资产的数据资源变动见上表；使用寿命、摊销方法、减值及受限情况按《企业数据资源相关会计处理暂行规定》披露（可索引会计政策）。'
        : '',
    )

    persist()
    return { message: `已从 I1-2/检查表带入 ${detail.length} 项（金额已更新，文字说明${overwriteNotes ? '已覆盖' : '已保留'}）`, count: detail.length }
  }

  return {
    categoryPreset,
    categories,
    movement,
    noteRdRatio,
    noteIndefinite,
    noteMortgage,
    noteImpairment,
    noteSale,
    noteImportant,
    noteDataResource,
    titleCertRows,
    importantRows,
    dataResource,
    amortAlloc,
    auditNote,
    auditConclusion,
    crossCheck,
    prepValidation,
    persist,
    updateMovement,
    addCategory,
    removeCategory,
    setCategoryPreset,
    addTitleCertRow,
    removeTitleCertRow,
    addImportantRow,
    removeImportantRow,
    updateDataResource,
    pullFromSources,
  }
}

function dataResourceCostInc(m: I1DataResourceMove): number {
  return num(m.costIncPurchase) + num(m.costIncRd) + num(m.costIncOther)
}

// ─── SOE ─────────────────────────────────────────────────────────────────────

export function useI1SoeDisclosure(params: {
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params
  const layers = ref<I1SoeLayerBlock[]>(createDefaultI1SoeLayers())
  const noteIndefinite = ref('')
  const noteMortgage = ref('')
  const noteValuation = ref('')
  const noteImpairment = ref('')
  const noteNotReady = ref('')
  const noteSale = ref('')
  const noteTitle = ref('')
  const amortAlloc = ref<I1AmortAllocSummary>(aggregateI19AmortAlloc([]))
  const auditNote = ref('')
  const auditConclusion = ref('')
  // 自定义类别单调计数器（持久化 → 删掉最大号后新增不复用已删序号，Task 13 / R7.6）
  const catSeqCounter = ref(0)

  function load(): void {
    const raw = _parseJson(_getRemark(allResponses.value, I1_SOE_KEYS.layers))
    if (Array.isArray(raw) && raw.length) {
      layers.value = recomputeI1SoeDerivedLayers(raw)
    } else {
      layers.value = createDefaultI1SoeLayers()
    }
    noteIndefinite.value = _getRemark(allResponses.value, I1_SOE_KEYS.noteIndefinite) || ''
    noteMortgage.value = _getRemark(allResponses.value, I1_SOE_KEYS.noteMortgage) || ''
    noteValuation.value = _getRemark(allResponses.value, I1_SOE_KEYS.noteValuation) || ''
    noteImpairment.value = _getRemark(allResponses.value, I1_SOE_KEYS.noteImpairment) || ''
    noteNotReady.value = _getRemark(allResponses.value, I1_SOE_KEYS.noteNotReady) || ''
    noteSale.value = _getRemark(allResponses.value, I1_SOE_KEYS.noteSale) || ''
    noteTitle.value = _getRemark(allResponses.value, I1_SOE_KEYS.noteTitle) || ''
    const aa = _parseJson(_getRemark(allResponses.value, SOE_AMORT_ALLOC_KEY))
    amortAlloc.value = aa && typeof aa === 'object' ? { ...aggregateI19AmortAlloc([]), ...aa } : aggregateI19AmortAlloc([])
    // 单调计数器：优先取持久化值，兜底取数据里出现的最大 custom seq（防旧数据无计数器时回退）
    const persistedSeq = Number(_getRemark(allResponses.value, SOE_CAT_SEQ_KEY) || 0)
    catSeqCounter.value = Math.max(
      Number.isFinite(persistedSeq) ? persistedSeq : 0,
      maxI1SoeCustomSeq(layers.value),
    )
    auditNote.value = _getRemark(allResponses.value, I1_SOE_KEYS.auditNote) || ''
    auditConclusion.value = _getRemark(allResponses.value, I1_SOE_KEYS.auditConclusion) || ''
  }

  watch(allResponses, () => load(), { immediate: true })

  function persist(): void {
    if (!onSave) return
    onSave(I1_SOE_KEYS.layers, layers.value)
    onSave(I1_SOE_KEYS.noteIndefinite, noteIndefinite.value)
    onSave(I1_SOE_KEYS.noteMortgage, noteMortgage.value)
    onSave(I1_SOE_KEYS.noteValuation, noteValuation.value)
    onSave(I1_SOE_KEYS.noteImpairment, noteImpairment.value)
    onSave(I1_SOE_KEYS.noteNotReady, noteNotReady.value)
    onSave(I1_SOE_KEYS.noteSale, noteSale.value)
    onSave(I1_SOE_KEYS.noteTitle, noteTitle.value)
    onSave(SOE_AMORT_ALLOC_KEY, amortAlloc.value)
    onSave(SOE_CAT_SEQ_KEY, String(catSeqCounter.value))
    onSave(I1_SOE_KEYS.auditNote, auditNote.value)
    onSave(I1_SOE_KEYS.auditConclusion, auditConclusion.value)
  }

  const crossCheck = computed(() =>
    buildI1SoeCrossCheck(layers.value, readI1AdjAudited(allResponses.value)),
  )

  const prepValidation = computed(() =>
    validateI1SoePrep({ layers: layers.value, cross: crossCheck.value }),
  )

  function updateCategory(
    layer: I1SoeLayerBlock['layer'],
    catKey: string,
    field: keyof I1SoeCategoryMove,
    value: number,
  ): void {
    if (field === 'key') return
    layers.value = recomputeI1SoeDerivedLayers(layers.value.map((block) => {
      if (block.layer !== layer) return block
      return {
        ...block,
        categories: block.categories.map((c) =>
          c.key === catKey ? { ...c, [field]: value } : c,
        ),
      }
    }))
    persist()
  }

  /**
   * 新增自定义类别（源模板国企四层末 `……` 可扩位，Task 13 / R7.1）。
   * 撞名拒绝 → 返回 false（调用方据此提示）；成功则四层同时加行并持久化。
   */
  function addCategory(label: string): boolean {
    // 单调计数器作 seqFloor：删掉最大号后新增不复用该号（Property 23）
    const next = addI1SoeCategory(layers.value, label, catSeqCounter.value)
    if (!next) return false
    // 🔴 `addI1SoeCategory` 返回的是 `{ layers, key, seq }` **对象**，不是数组。
    //    曾写成 `maxI1SoeCustomSeq(next)` / `recomputeI1SoeDerivedLayers(next)`
    //    ⇒ 对象喂给 `for...of` 抛 `TypeError: layers is not iterable`，
    //    再被组件 `handleAddSoeCat` 的裸 `catch { /* cancelled */ }` 静默吞掉
    //    ⇒ 「+ 增加资产类别」点确认后**无提示、无新行、无库写入、控制台无 error**。
    //    四层守卫全绿的原因：model 层 vitest 用的是正确写法（`res!.layers` / `a.seq`），
    //    composable 层无测试；`get_diagnostics` 对该类型不匹配**漏报**，
    //    只有 `tsc --noEmit` 报 TS2345（550/551 两行）。
    //    seq 直接用返回值，不再从数据反算（doc 明写「调用方据 seq 回写持久化计数器」）。
    catSeqCounter.value = next.seq
    layers.value = recomputeI1SoeDerivedLayers(next.layers)
    persist()
    return true
  }

  /** 删除自定义类别（默认 12 类不可删 → 返回 false）。 */
  function removeCategory(key: string): boolean {
    const next = removeI1SoeCategory(layers.value, key)
    if (!next) return false
    layers.value = recomputeI1SoeDerivedLayers(next)
    persist()
    return true
  }

  function pullFromSources(opts?: { overwriteNotes?: boolean }): { message: string; count: number } {
    const overwriteNotes = opts?.overwriteNotes === true
    const detail = _loadRows(allResponses.value, 'I1-2-rows')
    if (!detail.length) {
      return { message: 'I1-2 明细无数据，请先编制明细表', count: 0 }
    }

    const kept = {
      noteIndefinite: noteIndefinite.value,
      noteMortgage: noteMortgage.value,
      noteImpairment: noteImpairment.value,
      noteNotReady: noteNotReady.value,
      noteSale: noteSale.value,
      noteTitle: noteTitle.value,
    }

    const emptyCats = (): I1SoeCategoryMove[] =>
      I1_SOE_CATEGORIES.map((c) => ({ key: c.key, begin: 0, increase: 0, decrease: 0, end: 0 }))

    const costCats = emptyCats()
    const amortCats = emptyCats()
    const impairCats = emptyCats()
    const find = (arr: I1SoeCategoryMove[], key: string) => arr.find((c) => c.key === key)!

    let notReady = 0
    let noTitle = 0
    const indefiniteNames: string[] = []

    for (const r of detail) {
      const key = mapToI1SoeCategoryKey(String(r.category || r.name || ''))
      const cc = find(costCats, key)
      const ac = find(amortCats, key)
      const ic = find(impairCats, key)

      cc.begin += preferAuditedAmount(r, 'auditedCostBegin', 'costBegin')
      cc.increase += preferAuditedAmount(r, 'auditedCostIncrease', 'costIncrease')
      cc.decrease += preferAuditedAmount(r, 'auditedCostDecrease', 'costDecrease')

      ac.begin += preferAuditedAmount(r, 'auditedAccAmortBegin', 'accAmortBegin')
      ac.increase += num(r.amortProvision) + num(r.amortOtherIncrease)
      {
        const split = num(r.amortDisposal) + num(r.amortOtherDecrease)
        ac.decrease += split > 0 ? split : num(r.amortTransferOut)
      }

      ic.begin += preferAuditedAmount(r, 'auditedImpairmentBegin', 'impairmentBegin')
      ic.increase += num(r.impairmentProvision) + num(r.impairOtherIncrease)
      {
        const split = num(r.impairDisposal) + num(r.impairOtherDecrease)
        ic.decrease += split > 0 ? split : num(r.impairmentReversal)
      }

      if (r.indefiniteLife === 'Y' || num(r.usefulLifeMonths) <= 0) {
        indefiniteNames.push(String(r.name || key))
      }
      if (r.notReadyForUse === 'Y') notReady++
      if (r.hasTitleEvidence === 'N') noTitle++
    }

    layers.value = recomputeI1SoeDerivedLayers([
      { layer: 'cost', categories: costCats },
      { layer: 'amort', categories: amortCats },
      { layer: 'impair', categories: impairCats },
      { layer: 'carrying', categories: emptyCats() },
    ])

    amortAlloc.value = aggregateI19AmortAlloc(_loadRows(allResponses.value, 'I1-9-rows'))

    const applyNote = (cur: string, draft: string) =>
      overwriteNotes ? (draft || cur) : fillNoteIfEmpty(cur, draft)

    noteIndefinite.value = applyNote(
      kept.noteIndefinite,
      indefiniteNames.length
        ? `使用寿命不确定的无形资产共 ${indefiniteNames.length} 项，判断依据详见 I1-4/I1-7。`
        : '',
    )
    const i18 = _loadRows(allResponses.value, 'I1-8-rows')
    noteMortgage.value = applyNote(kept.noteMortgage, draftMortgageNoteFromI18(i18))
    noteImpairment.value = applyNote(
      kept.noteImpairment,
      draftImpairmentNoteFromI112(_loadRows(allResponses.value, 'I1-12-rows')),
    )
    noteNotReady.value = applyNote(
      kept.noteNotReady,
      notReady > 0
        ? `尚未达到可使用状态的无形资产 ${notReady} 项，已按要求执行减值测试，详见 I1-12/I1-13。`
        : '',
    )
    noteSale.value = applyNote(
      kept.noteSale,
      draftSaleNoteFromI16(_loadRows(allResponses.value, 'I1-6-rows')),
    )
    noteTitle.value = applyNote(
      kept.noteTitle,
      noTitle > 0
        ? `未办妥权属证书的土地使用权/无形资产 ${noTitle} 项，账面价值及原因详见 I1-8。`
        : '',
    )

    persist()
    return { message: `已从 I1-2/检查表带入 ${detail.length} 项（金额已更新，文字说明${overwriteNotes ? '已覆盖' : '已保留'}）`, count: detail.length }
  }

  return {
    layers,
    noteIndefinite,
    noteMortgage,
    noteValuation,
    noteImpairment,
    noteNotReady,
    noteSale,
    noteTitle,
    amortAlloc,
    auditNote,
    auditConclusion,
    crossCheck,
    prepValidation,
    persist,
    updateCategory,
    addCategory,
    removeCategory,
    pullFromSources,
  }
}

export { formatAmortAllocNote }
export default { useI1ListedDisclosure, useI1SoeDisclosure }
