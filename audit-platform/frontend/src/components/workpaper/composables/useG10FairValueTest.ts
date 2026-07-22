/**
 * useG10FairValueTest — G10-5 公允价值测试（2区段Tab，Level3必填校验）
 *
 * 联动：超阈值差异推送 G10-3（FVTPL：Dr 6101 / Cr 2101）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { parseNum, calcSubtotal } from './useG10FormulaEngine'
import { G10_FV_LEVEL_OPTIONS, G10_VALUATION_METHOD_OPTIONS } from './g10Constants'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'
import { matchG10LiabilityKey } from './g10AccountMatch'
import { G10_DETAIL_ROWS_KEY, parseG10DetailRows, pushG10FvToDetail } from './g10CrossHelpers'
import {
  G10_FV_DIFF_THRESHOLD,
  calcG10FairValueDiff,
  calcG10FvDiffWarning,
  fetchG10PerformanceMateriality,
  hasG10FairValueDifference,
  pushG10FvDiffToAdjustment,
  selectG10FvDiffTargets,
  G10A_FV_MARK_KEY,
  G10A_FV_PROGRAM_NOS,
  buildG10FvProcedureSummary,
  markG10AProcedureSteps,
} from './g10FvCrossHelpers'

export interface G10FairValueRow {
  rowId: string
  seq: number
  liabilityName: string
  initialDate: string
  closingUnadjustedQty: number
  closingUnadjustedPrice: number
  closingUnadjustedFV: number
  closingAuditedQty: number
  closingAuditedPrice: number
  closingAuditedFV: number
  fairValueLevel: string
  valuationMethod: string
  methodConsistentWithPrior: 'yes' | 'no' | ''
  valuationSource: string
  inputSourceAndAdjustment: string
  valuationTechnique: string
  unobservableInputDesc: string
  unobservableInputValue: string
  sensitivityAnalysis: string
  valuationDocIndex: string
}

export type G10FairValueEnrichedRow = G10FairValueRow & {
  fairValueDiff: number
}

const ITEM_ID = 'G10-fv-test-rows'
const CONCLUSION_ID = 'G10-fv-test-conclusion'

function genId() { return `g10fv-${Date.now().toString(36)}` }

function enrich(raw: Partial<G10FairValueRow> & { rowId: string }): G10FairValueEnrichedRow {
  const uq = parseNum(raw.closingUnadjustedQty)
  const up = parseNum(raw.closingUnadjustedPrice)
  const aq = parseNum(raw.closingAuditedQty)
  const ap = parseNum(raw.closingAuditedPrice)
  const closingUnadjustedFV = parseNum(raw.closingUnadjustedFV) || uq * up
  const closingAuditedFV = parseNum(raw.closingAuditedFV) || aq * ap
  return {
    rowId: raw.rowId,
    seq: parseNum(raw.seq) || 0,
    liabilityName: raw.liabilityName ?? '',
    initialDate: raw.initialDate ?? '',
    closingUnadjustedQty: uq,
    closingUnadjustedPrice: up,
    closingUnadjustedFV,
    closingAuditedQty: aq,
    closingAuditedPrice: ap,
    closingAuditedFV,
    fairValueDiff: calcG10FairValueDiff(closingAuditedFV, closingUnadjustedFV),
    fairValueLevel: raw.fairValueLevel ?? 'Level2',
    valuationMethod: raw.valuationMethod ?? '',
    methodConsistentWithPrior: (raw.methodConsistentWithPrior as G10FairValueRow['methodConsistentWithPrior']) ?? '',
    valuationSource: raw.valuationSource ?? '',
    inputSourceAndAdjustment: raw.inputSourceAndAdjustment ?? '',
    valuationTechnique: raw.valuationTechnique ?? '',
    unobservableInputDesc: raw.unobservableInputDesc ?? '',
    unobservableInputValue: raw.unobservableInputValue ?? '',
    sensitivityAnalysis: raw.sensitivityAnalysis ?? '',
    valuationDocIndex: raw.valuationDocIndex ?? '',
  }
}

export function validateG10Level3Row(row: G10FairValueRow): string[] {
  if (row.fairValueLevel !== 'Level3') return []
  const missing: string[] = []
  if (!row.valuationTechnique?.trim()) missing.push('估值技术')
  if (!row.unobservableInputDesc?.trim()) missing.push('不可观察输入值描述')
  return missing
}

export function useG10FairValueTest(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
  wpId?: Ref<string>
  projectId?: Ref<string> | ComputedRef<string>
}) {
  const rows = ref<G10FairValueEnrichedRow[]>([])
  const activeTab = ref<'basic' | 'valuation'>('basic')
  const selectedRowId = ref('')
  const conclusion = ref('')
  const aiLoading = ref(false)
  const performanceMateriality = ref(0)
  const pmLoading = ref(false)
  const procedureMarking = ref(false)

  watch(() => opts.allResponses.value.get(ITEM_ID)?.remark, (j) => {
    try {
      rows.value = j
        ? JSON.parse(j).map((r: any, i: number) => enrich({ ...r, rowId: r.rowId || genId(), seq: r.seq ?? i + 1 }))
        : []
    } catch { rows.value = [] }
  }, { immediate: true })
  watch(() => opts.allResponses.value.get(CONCLUSION_ID)?.conclusion, (v) => {
    conclusion.value = v ?? ''
  }, { immediate: true })

  watch(
    () => opts.projectId?.value,
    (pid) => {
      if (pid && !performanceMateriality.value) void loadPerformanceMateriality()
    },
    { immediate: true },
  )

  const level3Violations = computed(() =>
    rows.value.flatMap((r) => {
      const missing = validateG10Level3Row(r)
      return missing.length ? [{ rowId: r.rowId, liabilityName: r.liabilityName, missing }] : []
    }),
  )

  const level3Count = computed(() =>
    rows.value.filter((r) => r.fairValueLevel === 'Level3').length,
  )

  const procedureMarked = computed(() =>
    !!opts.allResponses.value.get(G10A_FV_MARK_KEY)?.remark
    || opts.allResponses.value.get(G10A_FV_MARK_KEY)?.conclusion === 'completed',
  )

  const totals = computed(() => ({
    closingUnadjustedFV: calcSubtotal(rows.value.map((r) => r.closingUnadjustedFV)),
    closingAuditedFV: calcSubtotal(rows.value.map((r) => r.closingAuditedFV)),
    fairValueDiff: calcSubtotal(rows.value.map((r) => r.fairValueDiff)),
  }))

  const diffRows = computed(() => rows.value.filter(hasG10FairValueDifference))
  const diffCount = computed(() => diffRows.value.length)

  const materialDiffCount = computed(() => {
    const pm = performanceMateriality.value
    const threshold = pm > 0 ? pm : G10_FV_DIFF_THRESHOLD
    return diffRows.value.filter((r) => Math.abs(r.fairValueDiff) > threshold).length
  })

  const exceedsB15 = computed(() =>
    performanceMateriality.value > 0 && Math.abs(totals.value.fairValueDiff) >= performanceMateriality.value,
  )

  const diffWarningLevel = computed(() =>
    calcG10FvDiffWarning(Math.abs(totals.value.fairValueDiff), totals.value.closingUnadjustedFV, {
      hardAbs: performanceMateriality.value,
    }),
  )

  const diffRatioPct = computed(() => {
    const base = Math.abs(totals.value.closingUnadjustedFV)
    if (base <= G10_FV_DIFF_THRESHOLD) return '100.0'
    return ((Math.abs(totals.value.fairValueDiff) / base) * 100).toFixed(1)
  })

  const detailRows = computed(() =>
    parseG10DetailRows(opts.allResponses.value.get(G10_DETAIL_ROWS_KEY)?.remark),
  )

  const detailClosingAdjustedTotal = computed(() =>
    calcSubtotal(detailRows.value.map((r) => parseNum(r.closingAdjusted ?? r.closingBalance))),
  )

  const crossRefVariance = computed(() =>
    totals.value.closingAuditedFV - detailClosingAdjustedTotal.value,
  )

  const hasCrossRefIssue = computed(() =>
    rows.value.length > 0
    && detailRows.value.length > 0
    && Math.abs(crossRefVariance.value) > G10_FV_DIFF_THRESHOLD,
  )

  /** G10-5 行 → G10-2 逐行匹配（审定 FV vs 明细审定） */
  const detailLinkByRowId = computed(() => {
    const map = new Map<string, { detailRowId: string; variance: number }>()
    const byKey = new Map(
      detailRows.value
        .filter((d) => d.liabilityName?.trim())
        .map((d) => [matchG10LiabilityKey(d.liabilityName), d]),
    )
    for (const row of rows.value) {
      const hit = byKey.get(matchG10LiabilityKey(row.liabilityName))
      if (!hit) continue
      map.set(row.rowId, {
        detailRowId: hit.rowId,
        variance: parseNum(hit.closingAdjusted ?? hit.closingBalance) - row.closingAuditedFV,
      })
    }
    return map
  })

  function persist() {
    opts.debouncedSave(ITEM_ID, { remark: JSON.stringify(rows.value) })
  }

  function updateCell(rowId: string, field: keyof G10FairValueRow, value: unknown) {
    if (opts.isReadonly.value) return
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    const next = [...rows.value]
    next[idx] = enrich({ ...next[idx], [field]: value })
    rows.value = next
    persist()
  }

  async function addRow() {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('负债名称', '新增FV测试行', { inputPattern: /\S+/ })
      const row = enrich({ rowId: genId(), seq: rows.value.length + 1, liabilityName: value ?? '' })
      rows.value = [...rows.value, row]
      selectedRowId.value = row.rowId
      persist()
    } catch { /* cancel */ }
  }

  function removeRow(rowId: string) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.filter((r) => r.rowId !== rowId).map((r, i) => enrich({ ...r, seq: i + 1 }))
    persist()
  }

  function updateConclusion(v: string) {
    if (opts.isReadonly.value) return
    conclusion.value = v
    opts.debouncedSave(CONCLUSION_ID, { conclusion: v })
  }

  function validateLevel3(): boolean {
    const v = level3Violations.value
    if (v.length) {
      ElMessage.warning(`Level3 行缺少必填项：${v.map((x) => x.liabilityName).join('、')}`)
      return false
    }
    return true
  }

  async function loadPerformanceMateriality(): Promise<number> {
    const pid = opts.projectId?.value
    if (!pid) return 0
    pmLoading.value = true
    try {
      performanceMateriality.value = await fetchG10PerformanceMateriality(pid)
      return performanceMateriality.value
    } finally {
      pmLoading.value = false
    }
  }

  function syncFromDetail(): void {
    if (opts.isReadonly.value) return
    const details = detailRows.value.filter((r) => r.liabilityName?.trim())
    if (!details.length) {
      ElMessage.warning('G10-2 明细表暂无数据，请先编制明细')
      return
    }

    const existing = new Map(
      rows.value.map((r) => [matchG10LiabilityKey(r.liabilityName), r]),
    )
    let added = 0
    let updated = 0

    for (const d of details) {
      const name = String(d.liabilityName ?? '')
      const key = matchG10LiabilityKey(name)
      const audited = parseNum(d.closingAdjusted ?? d.closingBalance)
      const unadj = parseNum(d.closingBalance ?? d.closingAdjusted)
      const patch: Partial<G10FairValueRow> = {
        liabilityName: name,
        initialDate: String(d.contractDate ?? d.maturityDate ?? ''),
        closingUnadjustedFV: unadj,
        closingAuditedFV: audited,
        fairValueLevel: String(d.fairValueLevel || 'Level2'),
        valuationMethod: String(d.valuationMethod || ''),
      }

      if (existing.has(key)) {
        const prev = existing.get(key)!
        existing.set(key, enrich({ ...prev, ...patch }))
        updated += 1
      } else {
        existing.set(key, enrich({
          rowId: genId(),
          seq: existing.size + 1,
          liabilityName: name,
          ...patch,
        }))
        added += 1
      }
    }

    rows.value = [...existing.values()].map((r, i) => enrich({ ...r, seq: i + 1 }))
    persist()
    ElMessage.success(`已从 G10-2 同步：新增 ${added} 行，更新 ${updated} 行`)
  }

  function pushToDetail(): number {
    if (opts.isReadonly.value) return 0
    if (!rows.value.length) {
      ElMessage.warning('G10-5 暂无数据可回写')
      return 0
    }
    const n = pushG10FvToDetail(
      opts.allResponses.value,
      opts.debouncedSave,
      rows.value.map((r) => ({
        liabilityName: r.liabilityName,
        fairValueLevel: r.fairValueLevel,
        valuationMethod: r.valuationMethod,
      })),
    )
    if (!n) {
      ElMessage.warning('未匹配到 G10-2 行，请先编制明细或核对负债名称')
      return 0
    }
    ElMessage.success(`已回写 G10-2 ${n} 行（层次/估值方法）`)
    return n
  }

  async function pushDiffToAdjustment(forceAll = false): Promise<number> {
    if (opts.isReadonly.value) return 0
    if (!performanceMateriality.value && opts.projectId?.value) {
      await loadPerformanceMateriality()
    }

    let { targets, skipped, threshold } = selectG10FvDiffTargets({
      rows: rows.value,
      performanceMateriality: performanceMateriality.value,
      onlyMaterial: !forceAll,
    })

    if (!targets.length) {
      if (!skipped.length && !rows.value.some(hasG10FairValueDifference)) {
        ElMessage.info('无超阈值差异，无需推送调整分录')
        return 0
      }
      try {
        await ElMessageBox.confirm(
          skipped.length
            ? `无超过 B15（阈值 ${threshold.toFixed(2)}）的差异（跳过 ${skipped.length} 项）。是否按全部可识别差异（>|0.01|）推送？`
            : '无超过 B15 的差异。是否按全部可识别差异推送？',
          '推送差异至 G10-3',
          { type: 'warning', confirmButtonText: '全部推送', cancelButtonText: '取消' },
        )
      } catch {
        return 0
      }
      ;({ targets, skipped, threshold } = selectG10FvDiffTargets({
        rows: rows.value,
        performanceMateriality: performanceMateriality.value,
        onlyMaterial: false,
      }))
    }

    if (!targets.length) {
      ElMessage.info('无可推送差异')
      return 0
    }

    const n = pushG10FvDiffToAdjustment(
      opts.allResponses.value,
      opts.debouncedSave,
      targets.map((r) => ({
        summary: `G10-5 公允测试差异：${r.liabilityName || '未命名'}`,
        amount: r.fairValueDiff,
        liabilityName: r.liabilityName,
        indexRef: 'G10-5',
        remark: [
          `审定 ${r.closingAuditedFV} − 未审 ${r.closingUnadjustedFV}`,
          performanceMateriality.value > 0 ? `B15=${performanceMateriality.value}` : '',
        ].filter(Boolean).join('；'),
      })),
      'G10-5',
    )
    const skipHint = skipped.length ? `（另跳过 ${skipped.length} 项未超 B15）` : ''
    ElMessage.success(`已推送 ${n} 笔差异至 G10-3，并回写 G10-1 期末账项调整${skipHint}`)
    return n
  }

  async function markProcedureComplete(): Promise<number> {
    if (opts.isReadonly.value) return -1
    const pid = opts.projectId?.value || ''
    if (!pid) {
      ElMessage.warning('缺少项目 ID，无法回填 G10A')
      return -1
    }
    if (!rows.value.length) {
      ElMessage.warning('请先编制 G10-5 后再回填程序表')
      return -1
    }
    if (level3Violations.value.length) {
      try {
        await ElMessageBox.confirm(
          `仍有 ${level3Violations.value.length} 项 Level3 校验未通过，是否仍标记 G10A 公允测试程序为已完成？`,
          '回填 G10A',
          { type: 'warning', confirmButtonText: '仍标记完成', cancelButtonText: '取消' },
        )
      } catch {
        return -1
      }
    }

    let l3RowCount = 0
    try {
      const l3Json = opts.allResponses.value.get('G10-l3-rows')?.remark
      if (l3Json) {
        const parsed = JSON.parse(l3Json)
        if (Array.isArray(parsed)) l3RowCount = parsed.length
      }
    } catch { /* silent */ }

    procedureMarking.value = true
    try {
      const summary = buildG10FvProcedureSummary({
        rowCount: rows.value.length,
        diffCount: diffCount.value,
        level3Count: level3Count.value,
        auditedTotal: totals.value.closingAuditedFV,
        l3RowCount,
        validationErrors: level3Violations.value.length,
      })
      const n = await markG10AProcedureSteps({
        projectId: pid,
        programNos: [...G10A_FV_PROGRAM_NOS],
        status: 'completed',
        linkedWorkpapers: 'G10-5/G10-6',
        executionSummary: summary,
      })
      opts.debouncedSave(G10A_FV_MARK_KEY, {
        conclusion: 'completed',
        remark: JSON.stringify({
          at: new Date().toISOString(),
          summary,
          programNos: [...G10A_FV_PROGRAM_NOS],
        }),
      })
      ElMessage.success(
        n > 0
          ? `已回填 G10A 程序步骤 ${[...G10A_FV_PROGRAM_NOS].join('/')}（公允价值测试）为已完成`
          : '已记录完成标记（程序表字段写入可能需刷新 G10A 查看）',
      )
      return Math.max(n, 1)
    } finally {
      procedureMarking.value = false
    }
  }

  async function generateAiConclusion(): Promise<void> {
    if (opts.isReadonly.value || !opts.wpId?.value) return
    aiLoading.value = true
    try {
      const res = await api.post(
        `/api/workpapers/${opts.wpId.value}/g10/ai/fair-value-conclusion`,
        { existingContent: conclusion.value, rows: rows.value },
        { _silent: true } as any,
      )
      const text = res?.data?.content ?? res?.content ?? ''
      if (text) updateConclusion(text)
    } catch { /* AI optional */ }
    finally { aiLoading.value = false }
  }

  return {
    rows,
    activeTab,
    selectedRowId,
    conclusion,
    aiLoading,
    level3Violations,
    level3Count,
    procedureMarked,
    procedureMarking,
    totals,
    diffCount,
    materialDiffCount,
    exceedsB15,
    diffWarningLevel,
    diffRatioPct,
    performanceMateriality,
    pmLoading,
    detailClosingAdjustedTotal,
    crossRefVariance,
    hasCrossRefIssue,
    detailLinkByRowId,
    updateCell,
    addRow,
    removeRow,
    updateConclusion,
    validateLevel3,
    syncFromDetail,
    pushToDetail,
    loadPerformanceMateriality,
    pushDiffToAdjustment,
    markProcedureComplete,
    generateAiConclusion,
    persist,
    ITEM_ID,
    G10_FV_LEVEL_OPTIONS,
    G10_VALUATION_METHOD_OPTIONS,
  }
}
