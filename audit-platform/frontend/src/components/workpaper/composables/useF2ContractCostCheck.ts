/**
 * useF2ContractCostCheck — F2-56 合同履约成本检查表
 *
 * 抽凭回填 / 撤销 / 年审阶段预审行只读走共享回填函数 `useVoucherCheckFill`：一个对方科目一行（后端配对），
 * 按分录指纹去重，行元数据 `_gt` 随行 JSON 落库（spec voucher-identity-writeback-and-audit-phase 任务 11）。
 */
import { ref, computed, watch, onBeforeUnmount, type MaybeRefOrGetter, type Ref } from 'vue'
import { readSpeRowJson, type ChecklistResponse } from './useF2SpecialFormData'
import {
  counterpartText, legacyIdentity, useVoucherCheckFill, withRowMeta,
  type EngineFilledPayload, type FillSample, type PreparedItem, type UndoRequestPayload,
} from './shared/voucherCheckFill'
import {
  defaultContractCostCheckSheet,
  enrichCheckSamples,
  calcCheckStats,
  migrateContractCostCheckSheet,
  emptyCheckSample,
  isBlankContractCostCheckSample,
  type ContractCostCheckSheet,
  type ContractCostCheckSample,
  type ContractCostCheckSampling,
} from './useF2ContractCostCheckFormulas'

/** @deprecated 兼容 OCR / 旧引用 */
export type ContractCostCheckRow = ContractCostCheckSample & {
  voucherDate?: string
  contractNo?: string
  amount?: number
  isCorrect?: '是' | '否'
  equipmentAmt?: number
  constructionAmt?: number
  laborAmt?: number
  otherAmt?: number
  remark?: string
}

export type SamplingParams = ContractCostCheckSampling

const PARAMS_KEY = 'F2-56-params'
const ROWS_KEY = 'F2-56-rows'
const NOTE_KEY = 'F2-56-note'
const STAT_KEY = 'F2-56-stat'

/**
 * 共享回填函数的待写入项 → 检查样本：凭证金额取样本自己那一栏，对方科目取后端配对（编码 + 名称，配不上写「多科目」）；
 * 凭证日期沿用原实现写在分配月份（本表没有凭证日期列）
 */
export function mapPreparedToContractCostCheckSample(item: PreparedItem): ContractCostCheckSample {
  const s = item.sample as PreparedItem['sample'] & { summary?: string | null; accountName?: string | null }
  const debit = Number(item.debitAmount ?? 0) || 0
  const credit = Number(item.creditAmount ?? 0) || 0
  return {
    ...emptyCheckSample(),
    projectName: s.summary || s.accountName || '',
    accountDetail: s.accountName || '1410 合同履约成本',
    voucherNo: s.voucherNo || '',
    businessContent: s.summary || '',
    offsetAccount: counterpartText(item),
    voucherAmount: debit || credit,
    allocMonth: s.voucherDate || '',
    indexRef: '抽凭',
  }
}

/** 样本上已填合同 / 验收 / 物流 / 分配证据或异常判断（替换与撤销抽凭时据此先确认） */
export function hasContractCostCheckContent(r: ContractCostCheckSample): boolean {
  return [r.offsetProject, r.contractDateNo, r.contractTerms, r.receiptProductName, r.logisticsDateNo,
    r.logisticsProductName, r.logisticsProvider, r.allocBasis, r.isAbnormal, r.issueDesc]
    .some((v) => String(v ?? '').trim() !== '')
    || [r.receiptAmount, r.logisticsQty, r.allocQty, r.allocAmount].some((n) => Number(n) !== 0)
}

export function useF2ContractCostCheck(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
  /** 项目 id（抽凭回填按项目当前审计阶段标行阶段，年审阶段预审行只读） */
  projectId?: MaybeRefOrGetter<string | null | undefined>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const sheet = ref<ContractCostCheckSheet>(defaultContractCostCheckSheet())
  const auditNote = ref('')

  // 抽凭回填 / 撤销 / 年审阶段预审行只读：共享回填函数（一张表 = sheet.samples）
  const samplesTable = computed<ContractCostCheckSample[]>({
    get: () => sheet.value.samples,
    set: (list) => {
      // 回填时去掉空白占位行（原实现追加前也先去掉）；表空了补一行空白行（表上至少一行）
      const kept = list.filter((row) => !isBlankContractCostCheckSample(row))
      sheet.value = { ...sheet.value, samples: kept.length ? kept : [emptyCheckSample()] }
    },
  })
  const voucherFill = useVoucherCheckFill<ContractCostCheckSample>({
    projectId: opts.projectId ?? null,
    tables: samplesTable,
    mapSampleToRow: (item) => mapPreparedToContractCostCheckSample(item),
    persist: () => persist(),
    hasUserContent: hasContractCostCheckContent,
    // 旧行没有 `_gt`：凭证号 + 日期（原实现写在分配月份）+ 凭证金额
    legacy: (row) => legacyIdentity({ voucherNo: row.voucherNo, voucherDate: row.allocMonth, amount: row.voucherAmount }),
    readonly: () => readonly.value,
  })
  /** 年审阶段的预审行只读（不可改、不可删） */
  function lockedId(id: string): boolean {
    const row = sheet.value.samples.find((s) => s.id === id)
    return !!row && voucherFill.isRowLocked(row)
  }

  function load(): void {
    const pRaw = readSpeRowJson(opts.allResponses.value.get(PARAMS_KEY))
    const rRaw = readSpeRowJson(opts.allResponses.value.get(ROWS_KEY))
    // 自回声守卫：persist() 写回后 watcher 会再次触发 load，
    // 若内容与内存一致则跳过，避免 migrate 的空行裁剪吃掉刚新增的空样本行。
    if (rRaw && rRaw === JSON.stringify(sheet.value)) return
    if (rRaw || pRaw) {
      try {
        const parsed = rRaw ? JSON.parse(rRaw) : null
        const migrated = migrateContractCostCheckSheet(parsed, pRaw || undefined)
        if (migrated) {
          const beforeCount = Array.isArray(parsed?.samples)
            ? parsed.samples.length
            : (Array.isArray(parsed) ? parsed.length : 0)
          sheet.value = migrated
          voucherFill.markLoaded()
          if (!readonly.value && beforeCount > migrated.samples.length) {
            opts.allResponses.value.set(ROWS_KEY, {
              item_id: ROWS_KEY,
              conclusion: null,
              remark: JSON.stringify(migrated),
            })
            if (debounceTimer) clearTimeout(debounceTimer)
            debounceTimer = setTimeout(() => {
              debounceTimer = null
              flushSave()
            }, 300)
          }
        }
      } catch { /* ignore */ }
    }
    auditNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
    const stat = opts.allResponses.value.get(STAT_KEY)?.remark
    if (stat) sheet.value.statNote = stat
  }

  watch(
    () => [
      opts.allResponses.value.get(PARAMS_KEY)?.remark,
      opts.allResponses.value.get(ROWS_KEY)?.remark,
    ],
    load,
    { immediate: true },
  )

  const enrichedSamples = computed(() => enrichCheckSamples(sheet.value.samples))
  const enrichedRows = enrichedSamples

  const stats = computed(() => calcCheckStats(enrichedSamples.value))

  const params = computed({
    get: () => sheet.value.sampling,
    set: (v: ContractCostCheckSampling) => {
      sheet.value = { ...sheet.value, sampling: v }
      persist()
    },
  })

  const checkedTotal = computed(() => stats.value.testedAmount)
  const coverageRatio = computed(() =>
    sheet.value.sampling.populationAmount
      ? (checkedTotal.value / sheet.value.sampling.populationAmount) * 100
      : 0,
  )
  const isCoverageLow = computed(() => coverageRatio.value > 0 && coverageRatio.value < 50)
  const issueCount = computed(() => stats.value.abnormalCount)

  function flushSave(): void {
    const items = [
      opts.allResponses.value.get(PARAMS_KEY),
      opts.allResponses.value.get(ROWS_KEY),
      opts.allResponses.value.get(NOTE_KEY),
      opts.allResponses.value.get(STAT_KEY),
    ].filter(Boolean)
    if (items.length) {
      window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items } }))
    }
  }

  function persist(): void {
    if (readonly.value) return
    opts.allResponses.value.set(PARAMS_KEY, {
      item_id: PARAMS_KEY,
      conclusion: null,
      remark: JSON.stringify(sheet.value.sampling),
    })
    opts.allResponses.value.set(ROWS_KEY, {
      item_id: ROWS_KEY,
      conclusion: null,
      remark: JSON.stringify({ ...sheet.value, samples: voucherFill.guardPersist(sheet.value.samples) }),
    })
    opts.allResponses.value.set(STAT_KEY, {
      item_id: STAT_KEY,
      conclusion: null,
      remark: sheet.value.statNote,
    })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function updateSampling(patch: Partial<ContractCostCheckSampling>): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      sampling: { ...sheet.value.sampling, ...patch },
    }
    persist()
  }

  function updateParams(patch: Partial<ContractCostCheckSampling>): void {
    updateSampling(patch)
  }

  function updateSample(id: string, patch: Partial<ContractCostCheckSample>): void {
    if (readonly.value || lockedId(id)) return
    sheet.value = {
      ...sheet.value,
      samples: sheet.value.samples.map((s) => (s.id === id ? withRowMeta({ ...s, ...patch }, s) : s)),
    }
    persist()
  }

  function updateRow(id: string, patch: Partial<ContractCostCheckRow>): void {
    const {
      voucherDate,
      contractNo,
      amount,
      isCorrect,
      remark,
      equipmentAmt,
      constructionAmt,
      laborAmt,
      otherAmt,
      ...rest
    } = patch
    void equipmentAmt
    void constructionAmt
    void laborAmt
    void otherAmt
    const mapped: Partial<ContractCostCheckSample> = { ...rest }
    if (contractNo) mapped.contractDateNo = contractNo
    if (voucherDate) mapped.allocMonth = voucherDate
    if (amount != null) mapped.voucherAmount = amount
    if (isCorrect != null) {
      mapped.isAbnormal = isCorrect === '否' ? '是' : isCorrect === '是' ? '否' : ''
    }
    if (remark) mapped.issueDesc = mapped.issueDesc ? `${mapped.issueDesc}; ${remark}` : remark
    updateSample(id, mapped)
  }

  function setStatNote(val: string): void {
    if (readonly.value) return
    sheet.value = { ...sheet.value, statNote: val }
    persist()
  }

  function addSample(): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      samples: [...sheet.value.samples, emptyCheckSample()],
    }
    persist()
  }

  function addRow(): void {
    addSample()
  }

  function removeSample(id: string): void {
    if (readonly.value || sheet.value.samples.length <= 1 || lockedId(id)) return
    sheet.value = {
      ...sheet.value,
      samples: sheet.value.samples.filter((s) => s.id !== id),
    }
    persist()
  }

  function removeRow(id: string): void {
    removeSample(id)
  }

  /** 回填 / 挂凭导入 / 撤销之后同步样本量（沿用原口径：有凭证号或项目名称的行数）；抽凭回填时方法记「抽凭引擎」 */
  function syncSamplingAfterFill(method?: string): void {
    sheet.value = {
      ...sheet.value,
      sampling: {
        ...sheet.value.sampling,
        sampleSize: sheet.value.samples.filter((row) => row.voucherNo || row.projectName).length,
        ...(method ? { method } : {}),
      },
    }
    persist()
  }

  /**
   * 抽凭引擎回填：一个对方科目一行（后端配对），按分录指纹去重；「替换本阶段抽凭行」只删本阶段抽凭填入的行
   * （原实现整表替换 / 按凭证号去重，已删除）。空白占位行在回填时去掉，表空了补一行空白行。
   */
  async function onEngineFilled(payload: EngineFilledPayload) {
    const out = await voucherFill.onEngineFilled(payload)
    if (!out.cancelled) syncSamplingAfterFill('抽凭引擎')
    return out
  }

  /** 从序时账挂入导入：幂等追加，与抽凭命中同一分录只留一行 */
  async function onAttachImported(samples: FillSample[]) {
    const out = await voucherFill.onAttachImported(samples)
    if (!out.cancelled) syncSamplingAfterFill()
    return out
  }

  /** 撤销抽凭批次：按批次删行（有已填内容先确认） */
  async function onUndoRequest(payload: UndoRequestPayload): Promise<boolean> {
    const ok = await voucherFill.onUndoRequest(payload)
    if (ok) syncSamplingAfterFill()
    return ok
  }

  watch(auditNote, (val) => {
    if (readonly.value) return
    opts.allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
    persist()
  })

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      flushSave()
    }
  })

  return {
    sheet,
    params,
    enrichedSamples,
    enrichedRows,
    stats,
    checkedTotal,
    coverageRatio,
    isCoverageLow,
    issueCount,
    auditNote,
    updateSampling,
    updateParams,
    updateSample,
    updateRow,
    setStatNote,
    addSample,
    addRow,
    removeSample,
    removeRow,
    // 抽凭回填 / 撤销 / 年审阶段预审行只读（共享回填函数）
    onEngineFilled,
    onAttachImported,
    onUndoRequest,
    voucherRowClass: voucherFill.rowClass,
    isVoucherRowLocked: voucherFill.isRowLocked,
    voucherFillReady: voucherFill.ready,
  }
}

export default useF2ContractCostCheck
