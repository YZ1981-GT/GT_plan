/**
 * useH3TitleCheck — H3-12 产权核对 composable
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH3FormData'
import {
  type TitleRow,
  isAreaAnomaly,
  isAreaAcceptableDiff,
  normalizeTitleRow,
  recomputeTitleRow,
  PROCEDURE_TEMPLATE,
} from './h3TitleRowModel'
export type { TitleRow } from './h3TitleRowModel'
export {
  calcAreaDiff,
  suggestMatchConsistent,
  normalizeTitleRow,
  isAreaAnomaly,
  isAreaAcceptableDiff,
  PROCEDURE_TEMPLATE,
} from './h3TitleRowModel'
import {
  applyAuditeeDefaults,
  applySamplePlan,
  buildCompletenessChecks,
  buildImpairmentHints,
  extractH32TitleSeeds,
  extractH39TitleSeeds,
  fetchL1PledgeSeeds,
  fillCertAreaFromBook,
  importTitleRowsFromAll,
  importTitleRowsFromH32,
  importTitleRowsFromH39,
  syncMortgageFromL1,
  syncRestrictedToDisclosure,
  syncTitleCertToH39,
  type CompletenessCheck,
  type SamplePlan,
  type TitleImportResult,
} from './useH3TitleCrossSheet'

const ITEM_ID = 'H3-12-title-rows'

export function useH3TitleCheck(params: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  getValue: (id: string) => any
  setValue: (id: string, value: any) => void
  saveImmediate: (id: string, value: any) => Promise<void>
  measurementModel?: Ref<'cost' | 'fair_value'>
  auditeeName?: Ref<string>
}) {
  const { allResponses, getValue, setValue, measurementModel, auditeeName, projectId } = params
  const rows = ref<TitleRow[]>([])
  const l1Loading = ref(false)
  const lastL1Message = ref('')

  function loadRows(): void {
    const raw = getValue(ITEM_ID)
    rows.value = Array.isArray(raw) ? raw.map((r, i) => normalizeTitleRow(r, i)) : []
  }

  const ownerAnomalies = computed(() => rows.value.filter((r) => r.isAuditEntity === '否'))
  const areaDiffRows = computed(() => rows.value.filter((r) => isAreaAnomaly(r.certArea, r.bookArea)))
  const areaAcceptableRows = computed(() => rows.value.filter((r) => isAreaAcceptableDiff(r.certArea, r.bookArea)))
  const mismatchRows = computed(() => rows.value.filter((r) => r.matchConsistent === '否'))
  const restrictedRows = computed(() => rows.value.filter((r) => r.isRestricted === '是'))
  const pendingCertRows = computed(() => rows.value.filter((r) => r.certStatus === '办证中'))
  const sampledRows = computed(() => rows.value.filter((r) => r.sampled))
  const totalMortgageValue = computed(() =>
    rows.value.reduce((sum, r) => sum + (Number(r.mortgageValue) || 0), 0),
  )
  const impairmentHints = computed(() => buildImpairmentHints(rows.value))

  const completenessChecks = computed((): CompletenessCheck[] =>
    buildCompletenessChecks(rows.value, getValue, _model()),
  )

  function addRow(assetName = ''): void {
    const name = auditeeName?.value?.trim() || ''
    rows.value.push(normalizeTitleRow({
      assetName,
      seq: rows.value.length + 1,
      bookOwner: name,
      certOwner: name,
      isAuditEntity: name ? '是' : '',
      sourceTags: '手工',
    }))
    _persist()
  }

  function removeRow(index: number): void {
    rows.value.splice(index, 1)
    rows.value.forEach((r, i) => { r.seq = i + 1 })
    _persist()
  }

  function updateCell(index: number, field: keyof TitleRow, value: any): void {
    const row = rows.value[index]
    if (!row) return
    ;(row as any)[field] = value
    recomputeTitleRow(row)
    _persist()
  }

  function updateRow(index: number, _row?: any): void {
    const row = rows.value[index]
    if (!row) return
    recomputeTitleRow(row)
    _persist()
  }

  function _model(): 'cost' | 'fair_value' {
    return measurementModel?.value === 'fair_value' ? 'fair_value' : 'cost'
  }

  function _runImport(run: () => TitleImportResult): TitleImportResult {
    const result = run()
    if (result.added || result.updated) {
      rows.value.forEach((r, i) => { r.seq = i + 1 })
      _persist()
    }
    return result
  }

  function importFromH32(mode: 'addNew' | 'fillEmpty' = 'addNew', overwrite = false): TitleImportResult {
    const seeds = extractH32TitleSeeds(getValue, _model())
    return _runImport(() => importTitleRowsFromH32(rows.value, seeds, mode, overwrite))
  }

  function importFromH39(mode: 'addNew' | 'fillEmpty' = 'fillEmpty', overwrite = false): TitleImportResult {
    const seeds = extractH39TitleSeeds(getValue)
    return _runImport(() => importTitleRowsFromH39(rows.value, seeds, mode, overwrite))
  }

  function importFromAll(): TitleImportResult {
    return _runImport(() => importTitleRowsFromAll(rows.value, getValue, _model()))
  }

  async function syncFromL1(overwrite = false): Promise<TitleImportResult & { unmatched: string[] }> {
    l1Loading.value = true
    try {
      const { seeds, message } = await fetchL1PledgeSeeds(projectId.value)
      lastL1Message.value = message
      if (!seeds.length) {
        return { added: 0, updated: 0, skipped: 0, unmatched: [], message }
      }
      const result = syncMortgageFromL1(rows.value, seeds, overwrite)
      if (result.updated) _persist()
      lastL1Message.value = result.message
      return result
    } finally {
      l1Loading.value = false
    }
  }

  function syncToDisclosure(): { count: number; message: string } {
    const result = syncRestrictedToDisclosure(rows.value, setValue)
    return result
  }

  function syncBackToH39(overwrite = false): TitleImportResult {
    return syncTitleCertToH39(rows.value, getValue, setValue, overwrite)
  }

  function fillCertAreaPending(): number {
    const n = fillCertAreaFromBook(rows.value)
    if (n) _persist()
    return n
  }

  function applyAuditee(): number {
    const n = applyAuditeeDefaults(rows.value, auditeeName?.value || '')
    if (n) _persist()
    return n
  }

  function runSample(opts?: { targetCoverage?: number; minCount?: number }): SamplePlan {
    const plan = applySamplePlan(rows.value, opts)
    _persist()
    return plan
  }

  function getProcedureTemplate(): string {
    return PROCEDURE_TEMPLATE
  }

  function buildDraftConclusion(): string {
    const total = rows.value.length
    const ownerIssues = ownerAnomalies.value.length
    const areaIssues = areaDiffRows.value.length
    const areaOk = areaAcceptableRows.value.length
    const mismatch = mismatchRows.value.length
    const restricted = restrictedRows.value.length
    const pending = pendingCertRows.value.length
    const lines = [
      `本次投资性房地产产权核对共检查 ${total} 项（抽样 ${sampledRows.value.length || total} 项）。`,
      `权属异常 ${ownerIssues} 项；面积异常 ${areaIssues} 项（可接受差异 ${areaOk} 项）；核对不一致 ${mismatch} 项；权利受限 ${restricted} 项（抵押价值合计 ${totalMortgageValue.value.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}）；办证中 ${pending} 项。`,
    ]
    if (total === 0) {
      lines.push('尚未录入产权核对明细，审计程序尚待执行。')
    } else if (ownerIssues > 0 || mismatch > 0 || pending > 0) {
      lines.push('存在权属瑕疵、证载信息不一致或办证中资产，已在检查表记录；需评估对报表认定及附注披露的影响，并与银行借款（L1）等底稿交叉核对。')
    } else if (areaIssues > 0 || restricted > 0) {
      lines.push('权属主体未见重大异常；面积差异或抵押限制已记录，需关注披露完整性。')
    } else {
      lines.push('已查验产权证书原件并与账面记录核对，权属完整合法，未见重大权利限制。')
    }
    if (impairmentHints.value.length) {
      lines.push(`减值关注：${impairmentHints.value.slice(0, 3).join('；')}${impairmentHints.value.length > 3 ? '…' : ''}`)
    }
    return lines.join('\n')
  }

  function _persist(): void { setValue(ITEM_ID, rows.value) }
  watch(allResponses, () => loadRows(), { immediate: true })

  return {
    rows,
    ownerAnomalies,
    areaDiffRows,
    areaAcceptableRows,
    mismatchRows,
    restrictedRows,
    pendingCertRows,
    sampledRows,
    totalMortgageValue,
    impairmentHints,
    completenessChecks,
    l1Loading,
    lastL1Message,
    addRow,
    removeRow,
    updateCell,
    updateRow,
    buildDraftConclusion,
    importFromH32,
    importFromH39,
    importFromAll,
    syncFromL1,
    syncToDisclosure,
    syncBackToH39,
    fillCertAreaPending,
    applyAuditee,
    runSample,
    getProcedureTemplate,
    loadRows,
  }
}

export default useH3TitleCheck
