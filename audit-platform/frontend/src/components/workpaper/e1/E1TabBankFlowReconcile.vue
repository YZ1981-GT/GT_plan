<script setup lang="ts">
/**
 * E1TabBankFlowReconcile.vue — E1-31 银行流水双向核对表
 * （一）月度汇总 （二）账→流 （三）流→账 + OCR流水 + 覆盖率/结论
 */
import { computed, inject, ref, toRef, watch, type Ref } from 'vue'
import { MagicStick, Paperclip } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useE1BankFlowReconcile,
  diffPair,
  type BidirectCheckRow,
  type YesNo,
  type CheckReason,
  type FlowDirection,
  type AutoMatchMode,
} from '../composables/useE1BankFlowReconcile'
import { useE1AiGenerate } from '../composables/useE1AiGenerate'
import { useE1ImportExport } from '../composables/useE1ImportExport'
import type { UseE1BaseOptions } from '../composables/useE1Adjudication'
import type { SampledVoucher, FillMode } from '../composables/useSamplingAlgorithms'
import E1StatementOcrConfirmDialog, {
  type StatementOcrFields,
} from './E1StatementOcrConfirmDialog.vue'
import GtVoucherSamplingEngine from '../voucher-sampling/GtVoucherSamplingEngine.vue'
import E1IpoSheetChrome from './E1IpoSheetChrome.vue'
import http from '@/utils/http'
import { amountFormatter, amountParser } from '../composables/wpAmountInput'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveImmediate: (items: any[]) => Promise<void>
  debouncedSave: (items: any[]) => Promise<void>
  isReadonly: boolean
  sheetName?: string
  bsDate?: string
}>()

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)

/**
 * 金额格式单一真源 = `stores/displayPrefs` 的 `fmtAmount()`（千分符 + 2 位小数 + 单位偏好）。
 * **必须在 setup 顶层取**（`useDisplayPrefsStore` 是 setup 作用域 composable，写进函数体静默失效）。
 */
const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

const options: UseE1BaseOptions = {
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
  bsDate: toRef(props, 'bsDate') as unknown as Ref<string>,
}

const {
  pack,
  auditNote,
  auditConclusion,
  isLoading,
  isApplicable,
  monthlyTotals,
  coverage,
  mismatchMonthlyCount,
  setApplicable,
  updateMeta,
  setThreshold,
  updateMonthly,
  recalcMonthlyFromLines,
  addStatementLine,
  removeStatementLine,
  updateStatementLine,
  mergeOcrStatementLines,
  addJournalLine,
  removeJournalLine,
  updateJournalLine,
  mergeJournalLines,
  updateCheckRow,
  addCheckRow,
  removeCheckRow,
  previewMatch,
  autoMatchBoth,
  updateTip,
  setCoverageLowReason,
  saveNote,
  saveConclusion,
  hydrate,
} = useE1BankFlowReconcile(options)

const { generateText, isGenerating } = useE1AiGenerate(toRef(props, 'wpId') as Ref<string>)
const sheetCode = computed(() => 'E1-31')
const { exportTemplate, exportData, importData, isImporting } = useE1ImportExport({
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  sheet: sheetCode as unknown as Ref<string>,
})

const activeTab = ref('monthly')
const stmtFilter = ref('')
const checkFilter = ref<'all' | 'unmatched' | 'third'>('all')
const stmtPage = ref(1)
const journalPage = ref(1)
const b2bPage = ref(1)
const s2bPage = ref(1)
const pageSize = ref(50)

const ocrVisible = ref(false)
const ocrLoading = ref(false)
const ocrFields = ref<Partial<StatementOcrFields>>({})
const ocrConfidence = ref<number | undefined>()
const ocrPreview = ref('')
const ocrFileName = ref('')
const ocrAttachmentId = ref('')
const ocrSkippedCount = ref(0)

const lastOcrHint = computed(() => {
  const jobs = pack.value.ocrJobs || []
  if (!jobs.length) return ''
  const j = jobs[jobs.length - 1]
  const when = j.at ? j.at.slice(0, 16).replace('T', ' ') : ''
  return `最近OCR：${j.fileName || '未命名'} · ${j.lineCount}笔`
    + (j.skippedCount ? `/跳过${j.skippedCount}` : '')
    + (when ? ` · ${when}` : '')
})

const samplingVisible = ref(false)
const samplingPhase = ref<'final' | 'preliminary'>('final')
const year = computed(() => {
  const bs = props.bsDate || ''
  if (bs.length >= 4) {
    const y = parseInt(bs.slice(0, 4), 10)
    if (Number.isFinite(y) && y > 1900) return y
  }
  return new Date().getFullYear() - 1
})

function openSampling(): void {
  if (props.isReadonly) return
  samplingVisible.value = true
}

function onSampleFilled(payload: { samples: SampledVoucher[]; fillMode: FillMode }): void {
  const { samples, fillMode } = payload
  if (!samples?.length) return
  const mapped = samples.map(s => ({
    date: s.voucherDate || '',
    voucherNo: s.voucherNo || '',
    businessContent: s.summary || '',
    counterAccount: s.counterpartAccount || '',
    counterparty: '',
    debit: s.debitAmount ? Number(s.debitAmount) : 0,
    credit: s.creditAmount ? Number(s.creditAmount) : 0,
    source: '抽凭',
  }))
  const mode = fillMode === 'replace' ? 'replace' : fillMode === 'merge' ? 'merge' : 'append'
  const n = mergeJournalLines(mapped, mode)
  samplingVisible.value = false
  ElMessage.success(`已回填 ${n} 笔日记账（${mode === 'replace' ? '替换' : mode === 'merge' ? '合并' : '追加'}）`)
  activeTab.value = 'lines'
}

const ynOptions = [
  { label: '是', value: '是' },
  { label: '否', value: '否' },
]
const reasonOptions = [
  { label: '大额', value: '大额' },
  { label: '关联交易', value: '关联交易' },
  { label: '双向交易', value: '双向交易' },
  { label: '其他', value: '其他' },
]
const directionOptions = [
  { label: '收入', value: '收入' },
  { label: '支出', value: '支出' },
]

const conclusionTemplates = [
  {
    value: 'A',
    label: 'A—核对一致',
    text: '银行流水与账面日记账已按账户执行双向核对，月度发生额/余额差异在可接受范围；抽样核查未见未入账流水或账外资金，第三方回款/付款已识别并说明，资金往来真实完整。',
  },
  {
    value: 'B',
    label: 'B—差异已说明',
    text: '除已识别并记录的差异及第三方回款/付款事项外，银行流水与账面双向核对未见其他重大异常；相关事项原因合理或已提请进一步核查。',
  },
  {
    value: 'C',
    label: 'C—需扩大核查',
    text: '因存在月度重大差异、未匹配大额流水或覆盖率偏低等情形，已扩大抽样/询问范围，结果见审计说明；必要时交叉其他IPO舞弊应对程序。',
  },
]

function fmtRate(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return `${(v * 100).toFixed(2)}%`
}

/** 只读金额一律走平台单一真源（原自造 `toLocaleString` 绕过了单位/showZero 偏好）。 */
function fmtAmt(v: number): string {
  return displayPrefs.fmtAmount(v)
}

const filteredStatements = computed(() => {
  const q = stmtFilter.value.trim()
  if (!q) return pack.value.statementLines
  return pack.value.statementLines.filter(r =>
    [r.date, r.summary, r.counterparty, String(r.amount)].some(x => String(x).includes(q)),
  )
})

function filterChecks(rows: BidirectCheckRow[]): BidirectCheckRow[] {
  if (checkFilter.value === 'unmatched') return rows.filter(r => r.infoConsistent !== '是')
  if (checkFilter.value === 'third') return rows.filter(r => r.thirdParty === '是')
  return rows
}

const bookToBankView = computed(() => filterChecks(pack.value.bookToBank))
const bankToBookView = computed(() => filterChecks(pack.value.bankToBook))

const pagedStatements = computed(() => {
  const start = (stmtPage.value - 1) * pageSize.value
  return filteredStatements.value.slice(start, start + pageSize.value)
})
const pagedJournals = computed(() => {
  const start = (journalPage.value - 1) * pageSize.value
  return pack.value.journalLines.slice(start, start + pageSize.value)
})
const pagedBookToBank = computed(() => {
  const start = (b2bPage.value - 1) * pageSize.value
  return bookToBankView.value.slice(start, start + pageSize.value)
})
const pagedBankToBook = computed(() => {
  const start = (s2bPage.value - 1) * pageSize.value
  return bankToBookView.value.slice(start, start + pageSize.value)
})

watch(stmtFilter, () => { stmtPage.value = 1 })
watch(checkFilter, () => { b2bPage.value = 1; s2bPage.value = 1 })
watch(activeTab, () => {
  stmtPage.value = 1
  journalPage.value = 1
  b2bPage.value = 1
  s2bPage.value = 1
})

function aiContext(): Record<string, unknown> {
  return {
    底稿: 'E1-31 银行流水双向核对',
    开户银行: pack.value.bank,
    账号: pack.value.accountNo,
    流水笔数: pack.value.statementLines.length,
    日记账笔数: pack.value.journalLines.length,
    月度差异月数: mismatchMonthlyCount.value,
    账到流抽样: pack.value.bookToBank.length,
    流到账抽样: pack.value.bankToBook.length,
    覆盖率: coverage.value,
    已勾选红旗: pack.value.tips.filter(t => t.checked).map(t => t.label),
  }
}

function sanitize(raw: string, kind: 'note' | 'conclusion'): string {
  let t = String(raw || '').trim()
  if (kind === 'note') {
    t = t.replace(/^\*{0,2}审计说明\*{0,2}\s*/i, '')
    t = t.replace(/\n+\s*\*{0,2}审计结论\*{0,2}.*$/s, '')
  } else {
    t = t.replace(/^\*{0,2}审计结论\*{0,2}\s*/i, '')
    t = t.replace(/^[ABC]、\s*/i, '')
  }
  return t.trim()
}

async function generateAuditNote(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateText({
    section: 'e1-31-audit-note',
    prompt: [
      '你是注册会计师助理。请撰写 E1-31「审计说明」，只描述双向核对过程与发现，不要写审计结论。',
      '应概括：账户、流水取数/OCR、月度对碰、双向抽样、第三方回款、覆盖率及已勾选红旗。',
      '严禁 markdown；约 180～320 字。',
    ].join(''),
    context: aiContext(),
    existingContent: auditNote.value,
    confirmTitle: 'AI 生成 · 审计说明',
  })
  if (text) saveNote(sanitize(text, 'note'))
}

async function generateAuditConclusion(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateText({
    section: 'e1-31-audit-conclusion',
    prompt: [
      '你是注册会计师助理。请撰写 E1-31「审计结论」。',
      '可参考：A 核对一致；B 差异已说明；C 需扩大核查。',
      '只写结论；严禁 markdown；约 60～150 字。',
    ].join(''),
    context: aiContext(),
    existingContent: auditConclusion.value,
    confirmTitle: 'AI 生成 · 审计结论',
  })
  if (text) saveConclusion(sanitize(text, 'conclusion'))
}

function applyConclusionTemplate(code: string): void {
  const t = conclusionTemplates.find(i => i.value === code)
  if (t) saveConclusion(t.text)
}

async function handleImport(file: File): Promise<boolean> {
  const res = await importData(file)
  if (res.success) {
    ElMessage.success(res.message || '导入成功')
    await reloadWorkpaperData?.()
    hydrate()
  } else {
    ElMessage.warning(res.message || '导入失败')
  }
  return false
}

async function runOcr(file: File): Promise<boolean> {
  if (props.isReadonly) return false
  ocrLoading.value = true
  try {
    const form = new FormData()
    form.append('file', file)
    const { data } = await http.post(`/api/workpapers/${props.wpId}/e1/statement-ocr`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    const fields = data?.extracted_fields || {}
    if (!Array.isArray(fields.lines) || !fields.lines.length) {
      ElMessage.warning('OCR 完成，未识别到流水明细')
    }
    ocrFields.value = fields
    ocrConfidence.value = typeof data?.confidence === 'number' ? data.confidence : undefined
    ocrPreview.value = String(data?.ocr_text || '').slice(0, 2000)
    ocrFileName.value = file.name
    ocrAttachmentId.value = String(data?.attachment_id || '')
    ocrSkippedCount.value = Number(data?.skipped_line_count ?? fields.skippedLineCount ?? 0) || 0
    ocrVisible.value = true
  } catch {
    ElMessage.error('流水 OCR 识别失败')
  } finally {
    ocrLoading.value = false
  }
  return false
}

function onOcrConfirm(fields: StatementOcrFields): void {
  const confirmed = fields.lines?.length || 0
  const n = mergeOcrStatementLines(fields.lines, {
    bank: fields.bank,
    accountNo: fields.accountNo,
    ocrJob: {
      fileName: ocrFileName.value,
      attachmentId: ocrAttachmentId.value || undefined,
      lineCount: confirmed,
      skippedCount: ocrSkippedCount.value,
      confidence: ocrConfidence.value || 0,
      bank: fields.bank,
      accountNo: fields.accountNo,
    },
  })
  ElMessage.success(`已回填 ${n} 笔流水`)
}

function onRecalcMonthly(): void {
  recalcMonthlyFromLines()
  ElMessage.success('已按明细回填月度发生额')
}

async function onAutoMatch(mode: AutoMatchMode = 'replace'): Promise<void> {
  const preview = previewMatch()
  try {
    await ElMessageBox.confirm(
      `匹配预览：账→流 ${preview.bookToBank}（命中 ${preview.matchedBook}/未匹配 ${preview.unmatchedBook}）；流→账 ${preview.bankToBook}（命中 ${preview.matchedBank}/未匹配 ${preview.unmatchedBank}）。`
      + (mode === 'merge' ? '将增量合并并尽量保留人工填写。' : '将覆盖（二）（三）抽样表。')
      + '是否继续？',
      mode === 'merge' ? '增量匹配' : '覆盖匹配',
      { type: 'warning', confirmButtonText: '执行', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  const r = autoMatchBoth(mode)
  ElMessage.success(
    `匹配完成：账→流 ${r.bookToBank} / 流→账 ${r.bankToBook}`
    + `（账面侧命中 ${r.matchedBook}，流水侧命中 ${r.matchedBank}`
    + (r.preserved ? `，保留人工 ${r.preserved}` : '')
    + '）',
  )
  activeTab.value = 'bookToBank'
}

function checkSums(side: 'bookToBank' | 'bankToBook') {
  const rows = pack.value[side]
  return {
    debit: rows.reduce((s, r) => s + (Number(r.debit) || 0), 0),
    credit: rows.reduce((s, r) => s + (Number(r.credit) || 0), 0),
    stmt: rows.reduce((s, r) => s + (Number(r.stmtAmount) || 0), 0),
  }
}
</script>

<template>
  <div class="e1-tab-bank-flow">
    <E1IpoSheetChrome
      title="银行流水双向核对 (E1-31)"
      :is-applicable="isApplicable"
      :is-readonly="isReadonly"
      :is-loading="isLoading"
      :project-id="projectId"
      :index-chips="['wp:E1-6', 'wp:E1-23', 'wp:D4-32']"
      :is-importing="isImporting"
      :skeleton-rows="14"
      @update:applicable="setApplicable"
      @export-template="exportTemplate"
      @export-data="exportData"
      @import="handleImport"
    >
      <template #guidance>
        <details class="guidance-details">
          <summary>📋 编制提示</summary>
          <div class="guidance-content">
            <p>1. 按账户编制：先填开户银行/账号，上传对账单或流水做 OCR，确认后进入流水库。</p>
            <p>2. 录入或抽凭日记账明细；可「按明细回填月度」生成（一）发生额对碰。</p>
            <p>3. 设置大额门槛后执行「自动匹配」（增量/覆盖），生成（二）（三）抽样后再人工核第三方回款。</p>
            <p>4. 原所内「流水核查工具」能力由平台 OCR + 匹配替代；提示区红旗逐项排查后写入说明。</p>
          </div>
        </details>
      </template>

      <template #goal>
        <el-alert type="info" :closable="false" class="mb8" title="一、审计目标">
          <p>验证资产负债表中记录的货币资金存在且完整，资金往来真实，披露恰当。</p>
        </el-alert>
      </template>

      <template #status>
        <el-tag v-if="isApplicable && mismatchMonthlyCount" size="small" type="danger">月度差异 {{ mismatchMonthlyCount }} 月</el-tag>
        <el-tag v-if="isApplicable" size="small">流水 {{ pack.statementLines.length }}</el-tag>
        <el-tag v-if="isApplicable" size="small">日记账 {{ pack.journalLines.length }}</el-tag>
      </template>

      <template #actions>
        <el-upload :show-file-list="false" accept=".pdf,.png,.jpg,.jpeg,.xlsx,.xls" :before-upload="runOcr" :disabled="isReadonly || !isApplicable || ocrLoading">
          <el-button size="small" type="primary" plain :loading="ocrLoading" :disabled="isReadonly || !isApplicable">
            <el-icon><Paperclip /></el-icon> 流水 OCR
          </el-button>
        </el-upload>
        <el-tag v-if="lastOcrHint" size="small" type="info" effect="plain">{{ lastOcrHint }}</el-tag>
        <el-button size="small" :disabled="isReadonly || !isApplicable" @click="onRecalcMonthly">回填月度</el-button>
        <el-button size="small" type="primary" :disabled="isReadonly || !isApplicable" @click="openSampling">抽凭→日记账</el-button>
        <el-dropdown size="small" trigger="click" :disabled="isReadonly || !isApplicable">
          <el-button size="small" type="success" plain>自动匹配 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="onAutoMatch('merge')">增量合并（保留人工）</el-dropdown-item>
              <el-dropdown-item @click="onAutoMatch('replace')">覆盖重建</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </template>

        <el-card shadow="never" class="section-card meta-card">
          <el-form inline size="small">
            <el-form-item label="开户银行">
              <el-input :model-value="pack.bank" :disabled="isReadonly" style="width: 200px"
                @change="(v: string) => updateMeta('bank', v)" />
            </el-form-item>
            <el-form-item label="账号">
              <el-input :model-value="pack.accountNo" :disabled="isReadonly" style="width: 200px"
                @change="(v: string) => updateMeta('accountNo', v)" />
            </el-form-item>
          </el-form>
        </el-card>

        <el-tabs v-model="activeTab" type="border-card" class="flow-tabs">
          <!-- （一） -->
          <el-tab-pane label="（一）月度汇总核对" name="monthly">
            <el-table :data="pack.monthly" border size="small" max-height="480">
              <el-table-column prop="month" label="月" width="50" fixed />
              <el-table-column label="银行对账单/流水" align="center">
                <el-table-column label="收入" width="110" align="right">
                  <template #default="{ row }">
                    <el-input-number :model-value="row.stmtIncome" :disabled="isReadonly" :controls="false" :precision="2" :formatter="amountFormatter" :parser="amountParser" size="small" style="width: 100%"
                      @change="(v: number) => updateMonthly(row.month, 'stmtIncome', v ?? 0)" />
                  </template>
                </el-table-column>
                <el-table-column label="支出" width="110" align="right">
                  <template #default="{ row }">
                    <el-input-number :model-value="row.stmtExpense" :disabled="isReadonly" :controls="false" :precision="2" :formatter="amountFormatter" :parser="amountParser" size="small" style="width: 100%"
                      @change="(v: number) => updateMonthly(row.month, 'stmtExpense', v ?? 0)" />
                  </template>
                </el-table-column>
                <el-table-column label="余额" width="110" align="right">
                  <template #default="{ row }">
                    <el-input-number :model-value="row.stmtBalance" :disabled="isReadonly" :controls="false" :precision="2" :formatter="amountFormatter" :parser="amountParser" size="small" style="width: 100%"
                      @change="(v: number) => updateMonthly(row.month, 'stmtBalance', v ?? 0)" />
                  </template>
                </el-table-column>
              </el-table-column>
              <el-table-column label="银行日记账" align="center">
                <el-table-column label="借方发生额" width="110" align="right">
                  <template #default="{ row }">
                    <el-input-number :model-value="row.journalDebit" :disabled="isReadonly" :controls="false" :precision="2" :formatter="amountFormatter" :parser="amountParser" size="small" style="width: 100%"
                      @change="(v: number) => updateMonthly(row.month, 'journalDebit', v ?? 0)" />
                  </template>
                </el-table-column>
                <el-table-column label="贷方发生额" width="110" align="right">
                  <template #default="{ row }">
                    <el-input-number :model-value="row.journalCredit" :disabled="isReadonly" :controls="false" :precision="2" :formatter="amountFormatter" :parser="amountParser" size="small" style="width: 100%"
                      @change="(v: number) => updateMonthly(row.month, 'journalCredit', v ?? 0)" />
                  </template>
                </el-table-column>
                <el-table-column label="余额" width="110" align="right">
                  <template #default="{ row }">
                    <el-input-number :model-value="row.journalBalance" :disabled="isReadonly" :controls="false" :precision="2" :formatter="amountFormatter" :parser="amountParser" size="small" style="width: 100%"
                      @change="(v: number) => updateMonthly(row.month, 'journalBalance', v ?? 0)" />
                  </template>
                </el-table-column>
              </el-table-column>
              <el-table-column label="借方发生额" align="center">
                <el-table-column label="差额" width="90" align="right">
                  <template #default="{ row }">{{ fmtAmt(diffPair(row.stmtIncome, row.journalDebit).amount) }}</template>
                </el-table-column>
                <el-table-column label="差异率" width="80" align="right">
                  <template #default="{ row }">{{ fmtRate(diffPair(row.stmtIncome, row.journalDebit).rate) }}</template>
                </el-table-column>
              </el-table-column>
              <el-table-column label="贷方发生额" align="center">
                <el-table-column label="差额" width="90" align="right">
                  <template #default="{ row }">{{ fmtAmt(diffPair(row.stmtExpense, row.journalCredit).amount) }}</template>
                </el-table-column>
                <el-table-column label="差异率" width="80" align="right">
                  <template #default="{ row }">{{ fmtRate(diffPair(row.stmtExpense, row.journalCredit).rate) }}</template>
                </el-table-column>
              </el-table-column>
              <el-table-column label="余额" align="center">
                <el-table-column label="差额" width="90" align="right">
                  <template #default="{ row }">{{ fmtAmt(diffPair(row.stmtBalance, row.journalBalance).amount) }}</template>
                </el-table-column>
                <el-table-column label="差异率" width="80" align="right">
                  <template #default="{ row }">{{ fmtRate(diffPair(row.stmtBalance, row.journalBalance).rate) }}</template>
                </el-table-column>
              </el-table-column>
            </el-table>
            <p class="sum-hint" style="margin-top: 8px">
              合计 · 对账单收入 {{ fmtAmt(monthlyTotals.stmtIncome) }} / 支出 {{ fmtAmt(monthlyTotals.stmtExpense) }}
              · 日记账借方 {{ fmtAmt(monthlyTotals.journalDebit) }} / 贷方 {{ fmtAmt(monthlyTotals.journalCredit) }}
            </p>
          </el-tab-pane>

          <!-- 明细库 -->
          <el-tab-pane :label="`流水/日记账明细 (${pack.statementLines.length}/${pack.journalLines.length})`" name="lines">
            <el-row :gutter="12">
              <el-col :span="12">
                <div class="sub-toolbar">
                  <b>银行流水库</b>
                  <el-input v-model="stmtFilter" size="small" clearable placeholder="筛选" style="width: 140px" />
                  <el-button size="small" :disabled="isReadonly" @click="addStatementLine()">+ 行</el-button>
                </div>
                <el-table :data="pagedStatements" border size="small" max-height="420">
                  <el-table-column label="日期" width="120">
                    <template #default="{ row }">
                      <el-input :model-value="row.date" :disabled="isReadonly" size="small"
                        @change="(v: string) => updateStatementLine(row.id, 'date', v)" />
                    </template>
                  </el-table-column>
                  <el-table-column label="摘要" min-width="90">
                    <template #default="{ row }">
                      <el-input :model-value="row.summary" :disabled="isReadonly" size="small"
                        @change="(v: string) => updateStatementLine(row.id, 'summary', v)" />
                    </template>
                  </el-table-column>
                  <el-table-column label="对方" min-width="90">
                    <template #default="{ row }">
                      <el-input :model-value="row.counterparty" :disabled="isReadonly" size="small"
                        @change="(v: string) => updateStatementLine(row.id, 'counterparty', v)" />
                    </template>
                  </el-table-column>
                  <el-table-column label="方向" width="88">
                    <template #default="{ row }">
                      <el-select :model-value="row.direction" :disabled="isReadonly" size="small" clearable
                        @change="(v: string) => updateStatementLine(row.id, 'direction', (v || '') as FlowDirection)">
                        <el-option v-for="o in directionOptions" :key="o.value" :label="o.label" :value="o.value" />
                      </el-select>
                    </template>
                  </el-table-column>
                  <el-table-column label="金额" width="100" align="right">
                    <template #default="{ row }">
                      <el-input-number :model-value="row.amount" :disabled="isReadonly" :controls="false" :precision="2" :formatter="amountFormatter" :parser="amountParser" size="small" style="width: 100%"
                        @change="(v: number) => updateStatementLine(row.id, 'amount', v ?? 0)" />
                    </template>
                  </el-table-column>
                  <el-table-column width="50">
                    <template #default="{ row }">
                      <el-button type="danger" text size="small" :disabled="isReadonly" @click="removeStatementLine(row.id)">删</el-button>
                    </template>
                  </el-table-column>
                </el-table>
                <div class="pager-row">
                  <el-pagination
                    v-model:current-page="stmtPage"
                    v-model:page-size="pageSize"
                    :total="filteredStatements.length"
                    :page-sizes="[30, 50, 100, 200]"
                    layout="total, sizes, prev, pager, next"
                    small
                    background
                  />
                </div>
              </el-col>
              <el-col :span="12">
                <div class="sub-toolbar">
                  <b>银行日记账</b>
                  <el-button size="small" type="primary" plain :disabled="isReadonly" @click="openSampling">抽凭回填</el-button>
                  <el-button size="small" :disabled="isReadonly" @click="addJournalLine()">+ 行</el-button>
                </div>
                <el-table :data="pagedJournals" border size="small" max-height="420">
                  <el-table-column label="日期" width="110">
                    <template #default="{ row }">
                      <el-input :model-value="row.date" :disabled="isReadonly" size="small"
                        @change="(v: string) => updateJournalLine(row.id, 'date', v)" />
                    </template>
                  </el-table-column>
                  <el-table-column label="凭证号" width="90">
                    <template #default="{ row }">
                      <el-input :model-value="row.voucherNo" :disabled="isReadonly" size="small"
                        @change="(v: string) => updateJournalLine(row.id, 'voucherNo', v)" />
                    </template>
                  </el-table-column>
                  <el-table-column label="业务内容" min-width="80">
                    <template #default="{ row }">
                      <el-input :model-value="row.businessContent" :disabled="isReadonly" size="small"
                        @change="(v: string) => updateJournalLine(row.id, 'businessContent', v)" />
                    </template>
                  </el-table-column>
                  <el-table-column label="往来" min-width="80">
                    <template #default="{ row }">
                      <el-input :model-value="row.counterparty" :disabled="isReadonly" size="small"
                        @change="(v: string) => updateJournalLine(row.id, 'counterparty', v)" />
                    </template>
                  </el-table-column>
                  <el-table-column label="借方" width="90" align="right">
                    <template #default="{ row }">
                      <el-input-number :model-value="row.debit" :disabled="isReadonly" :controls="false" :precision="2" :formatter="amountFormatter" :parser="amountParser" size="small" style="width: 100%"
                        @change="(v: number) => updateJournalLine(row.id, 'debit', v ?? 0)" />
                    </template>
                  </el-table-column>
                  <el-table-column label="贷方" width="90" align="right">
                    <template #default="{ row }">
                      <el-input-number :model-value="row.credit" :disabled="isReadonly" :controls="false" :precision="2" :formatter="amountFormatter" :parser="amountParser" size="small" style="width: 100%"
                        @change="(v: number) => updateJournalLine(row.id, 'credit', v ?? 0)" />
                    </template>
                  </el-table-column>
                  <el-table-column width="50">
                    <template #default="{ row }">
                      <el-button type="danger" text size="small" :disabled="isReadonly" @click="removeJournalLine(row.id)">删</el-button>
                    </template>
                  </el-table-column>
                </el-table>
                <div class="pager-row">
                  <el-pagination
                    v-model:current-page="journalPage"
                    v-model:page-size="pageSize"
                    :total="pack.journalLines.length"
                    :page-sizes="[30, 50, 100, 200]"
                    layout="total, sizes, prev, pager, next"
                    small
                    background
                  />
                </div>
              </el-col>
            </el-row>
          </el-tab-pane>

          <!-- （二） -->
          <el-tab-pane :label="`（二）账→流 (${pack.bookToBank.length})`" name="bookToBank">
            <div class="sub-toolbar">
              <span>大额标准：大于</span>
              <el-input-number
                :model-value="pack.largeThresholdBookToBank"
                :disabled="isReadonly"
                :controls="false"
                :precision="2"
                :formatter="amountFormatter"
                :parser="amountParser"
                size="small"
                style="width: 140px"
                @change="(v: number) => setThreshold('bookToBank', v ?? 0)"
              />
              <span>元</span>
              <el-radio-group v-model="checkFilter" size="small">
                <el-radio-button label="all">全部</el-radio-button>
                <el-radio-button label="unmatched">未一致</el-radio-button>
                <el-radio-button label="third">第三方</el-radio-button>
              </el-radio-group>
              <el-button size="small" :disabled="isReadonly" @click="addCheckRow('bookToBank')">+ 行</el-button>
              <span class="sum-hint">合计借 {{ fmtAmt(checkSums('bookToBank').debit) }} / 贷 {{ fmtAmt(checkSums('bookToBank').credit) }} / 流水 {{ fmtAmt(checkSums('bookToBank').stmt) }}</span>
            </div>
            <div class="table-scroll">
              <el-table :data="pagedBookToBank" border size="small" max-height="480">
                <el-table-column label="检查原因" width="100" fixed>
                  <template #default="{ row }">
                    <el-select :model-value="row.checkReason" :disabled="isReadonly" size="small" clearable
                      @change="(v: string) => updateCheckRow('bookToBank', row.id, 'checkReason', (v || '') as CheckReason)">
                      <el-option v-for="o in reasonOptions" :key="o.value" :label="o.label" :value="o.value" />
                    </el-select>
                  </template>
                </el-table-column>
                <el-table-column label="记账凭证" align="center">
                  <el-table-column label="日期" width="110">
                    <template #default="{ row }">
                      <el-input :model-value="row.vDate" :disabled="isReadonly" size="small"
                        @change="(v: string) => updateCheckRow('bookToBank', row.id, 'vDate', v)" />
                    </template>
                  </el-table-column>
                  <el-table-column label="凭证号" width="90">
                    <template #default="{ row }">
                      <el-input :model-value="row.voucherNo" :disabled="isReadonly" size="small"
                        @change="(v: string) => updateCheckRow('bookToBank', row.id, 'voucherNo', v)" />
                    </template>
                  </el-table-column>
                  <el-table-column label="业务内容" min-width="100">
                    <template #default="{ row }">
                      <el-input :model-value="row.businessContent" :disabled="isReadonly" size="small"
                        @change="(v: string) => updateCheckRow('bookToBank', row.id, 'businessContent', v)" />
                    </template>
                  </el-table-column>
                  <el-table-column label="往来单位" min-width="90">
                    <template #default="{ row }">
                      <el-input :model-value="row.counterparty" :disabled="isReadonly" size="small"
                        @change="(v: string) => updateCheckRow('bookToBank', row.id, 'counterparty', v)" />
                    </template>
                  </el-table-column>
                  <el-table-column label="借方" width="95" align="right">
                    <template #default="{ row }">
                      <el-input-number :model-value="row.debit" :disabled="isReadonly" :controls="false" :precision="2" :formatter="amountFormatter" :parser="amountParser" size="small" style="width: 100%"
                        @change="(v: number) => updateCheckRow('bookToBank', row.id, 'debit', v ?? 0)" />
                    </template>
                  </el-table-column>
                  <el-table-column label="贷方" width="95" align="right">
                    <template #default="{ row }">
                      <el-input-number :model-value="row.credit" :disabled="isReadonly" :controls="false" :precision="2" :formatter="amountFormatter" :parser="amountParser" size="small" style="width: 100%"
                        @change="(v: number) => updateCheckRow('bookToBank', row.id, 'credit', v ?? 0)" />
                    </template>
                  </el-table-column>
                </el-table-column>
                <el-table-column label="银行对账单" align="center">
                  <el-table-column label="收付日期" width="110">
                    <template #default="{ row }">
                      <el-input :model-value="row.sDate" :disabled="isReadonly" size="small"
                        @change="(v: string) => updateCheckRow('bookToBank', row.id, 'sDate', v)" />
                    </template>
                  </el-table-column>
                  <el-table-column label="摘要" min-width="90">
                    <template #default="{ row }">
                      <el-input :model-value="row.summary" :disabled="isReadonly" size="small"
                        @change="(v: string) => updateCheckRow('bookToBank', row.id, 'summary', v)" />
                    </template>
                  </el-table-column>
                  <el-table-column label="收付款方" min-width="90">
                    <template #default="{ row }">
                      <el-input :model-value="row.payerPayee" :disabled="isReadonly" size="small"
                        @change="(v: string) => updateCheckRow('bookToBank', row.id, 'payerPayee', v)" />
                    </template>
                  </el-table-column>
                  <el-table-column label="金额" width="95" align="right">
                    <template #default="{ row }">
                      <el-input-number :model-value="row.stmtAmount" :disabled="isReadonly" :controls="false" :precision="2" :formatter="amountFormatter" :parser="amountParser" size="small" style="width: 100%"
                        @change="(v: number) => updateCheckRow('bookToBank', row.id, 'stmtAmount', v ?? 0)" />
                    </template>
                  </el-table-column>
                </el-table-column>
                <el-table-column label="一致" width="78">
                  <template #default="{ row }">
                    <el-select :model-value="row.infoConsistent" :disabled="isReadonly" size="small" clearable
                      @change="(v: string) => updateCheckRow('bookToBank', row.id, 'infoConsistent', (v || '') as YesNo)">
                      <el-option v-for="o in ynOptions" :key="o.value" :label="o.label" :value="o.value" />
                    </el-select>
                  </template>
                </el-table-column>
                <el-table-column label="第三方" width="78">
                  <template #default="{ row }">
                    <el-select :model-value="row.thirdParty" :disabled="isReadonly" size="small" clearable
                      @change="(v: string) => updateCheckRow('bookToBank', row.id, 'thirdParty', (v || '') as YesNo)">
                      <el-option v-for="o in ynOptions" :key="o.value" :label="o.label" :value="o.value" />
                    </el-select>
                  </template>
                </el-table-column>
                <el-table-column label="不一致原因" min-width="100">
                  <template #default="{ row }">
                    <el-input :model-value="row.inconsistencyReason" :disabled="isReadonly" size="small"
                      @change="(v: string) => updateCheckRow('bookToBank', row.id, 'inconsistencyReason', v)" />
                  </template>
                </el-table-column>
                <el-table-column label="支持文件" min-width="100">
                  <template #default="{ row }">
                    <el-input :model-value="row.supportDocs" :disabled="isReadonly" size="small"
                      @change="(v: string) => updateCheckRow('bookToBank', row.id, 'supportDocs', v)" />
                  </template>
                </el-table-column>
                <el-table-column label="结论" min-width="90">
                  <template #default="{ row }">
                    <el-input :model-value="row.conclusion" :disabled="isReadonly" size="small"
                      @change="(v: string) => updateCheckRow('bookToBank', row.id, 'conclusion', v)" />
                  </template>
                </el-table-column>
                <el-table-column width="50" fixed="right">
                  <template #default="{ row }">
                    <el-button type="danger" text size="small" :disabled="isReadonly" @click="removeCheckRow('bookToBank', row.id)">删</el-button>
                  </template>
                </el-table-column>
              </el-table>
              <div class="pager-row">
                <el-pagination
                  v-model:current-page="b2bPage"
                  v-model:page-size="pageSize"
                  :total="bookToBankView.length"
                  :page-sizes="[30, 50, 100, 200]"
                  layout="total, sizes, prev, pager, next"
                  small
                  background
                />
              </div>
            </div>
          </el-tab-pane>

          <!-- （三） -->
          <el-tab-pane :label="`（三）流→账 (${pack.bankToBook.length})`" name="bankToBook">
            <div class="sub-toolbar">
              <span>大额标准：大于</span>
              <el-input-number
                :model-value="pack.largeThresholdBankToBook"
                :disabled="isReadonly"
                :controls="false"
                :precision="2"
                :formatter="amountFormatter"
                :parser="amountParser"
                size="small"
                style="width: 140px"
                @change="(v: number) => setThreshold('bankToBook', v ?? 0)"
              />
              <span>元</span>
              <el-radio-group v-model="checkFilter" size="small">
                <el-radio-button label="all">全部</el-radio-button>
                <el-radio-button label="unmatched">未一致</el-radio-button>
                <el-radio-button label="third">第三方</el-radio-button>
              </el-radio-group>
              <el-button size="small" :disabled="isReadonly" @click="addCheckRow('bankToBook')">+ 行</el-button>
              <span class="sum-hint">合计流水 {{ fmtAmt(checkSums('bankToBook').stmt) }} / 借 {{ fmtAmt(checkSums('bankToBook').debit) }} / 贷 {{ fmtAmt(checkSums('bankToBook').credit) }}</span>
            </div>
            <div class="table-scroll">
              <el-table :data="pagedBankToBook" border size="small" max-height="480">
                <el-table-column label="检查原因" width="100" fixed>
                  <template #default="{ row }">
                    <el-select :model-value="row.checkReason" :disabled="isReadonly" size="small" clearable
                      @change="(v: string) => updateCheckRow('bankToBook', row.id, 'checkReason', (v || '') as CheckReason)">
                      <el-option v-for="o in reasonOptions" :key="o.value" :label="o.label" :value="o.value" />
                    </el-select>
                  </template>
                </el-table-column>
                <el-table-column label="银行对账单" align="center">
                  <el-table-column label="收付日期" width="110">
                    <template #default="{ row }">
                      <el-input :model-value="row.sDate" :disabled="isReadonly" size="small"
                        @change="(v: string) => updateCheckRow('bankToBook', row.id, 'sDate', v)" />
                    </template>
                  </el-table-column>
                  <el-table-column label="摘要" min-width="90">
                    <template #default="{ row }">
                      <el-input :model-value="row.summary" :disabled="isReadonly" size="small"
                        @change="(v: string) => updateCheckRow('bankToBook', row.id, 'summary', v)" />
                    </template>
                  </el-table-column>
                  <el-table-column label="收付款方" min-width="90">
                    <template #default="{ row }">
                      <el-input :model-value="row.payerPayee" :disabled="isReadonly" size="small"
                        @change="(v: string) => updateCheckRow('bankToBook', row.id, 'payerPayee', v)" />
                    </template>
                  </el-table-column>
                  <el-table-column label="金额" width="95" align="right">
                    <template #default="{ row }">
                      <el-input-number :model-value="row.stmtAmount" :disabled="isReadonly" :controls="false" :precision="2" :formatter="amountFormatter" :parser="amountParser" size="small" style="width: 100%"
                        @change="(v: number) => updateCheckRow('bankToBook', row.id, 'stmtAmount', v ?? 0)" />
                    </template>
                  </el-table-column>
                </el-table-column>
                <el-table-column label="记账凭证" align="center">
                  <el-table-column label="日期" width="110">
                    <template #default="{ row }">
                      <el-input :model-value="row.vDate" :disabled="isReadonly" size="small"
                        @change="(v: string) => updateCheckRow('bankToBook', row.id, 'vDate', v)" />
                    </template>
                  </el-table-column>
                  <el-table-column label="凭证号" width="90">
                    <template #default="{ row }">
                      <el-input :model-value="row.voucherNo" :disabled="isReadonly" size="small"
                        @change="(v: string) => updateCheckRow('bankToBook', row.id, 'voucherNo', v)" />
                    </template>
                  </el-table-column>
                  <el-table-column label="业务内容" min-width="100">
                    <template #default="{ row }">
                      <el-input :model-value="row.businessContent" :disabled="isReadonly" size="small"
                        @change="(v: string) => updateCheckRow('bankToBook', row.id, 'businessContent', v)" />
                    </template>
                  </el-table-column>
                  <el-table-column label="往来单位" min-width="90">
                    <template #default="{ row }">
                      <el-input :model-value="row.counterparty" :disabled="isReadonly" size="small"
                        @change="(v: string) => updateCheckRow('bankToBook', row.id, 'counterparty', v)" />
                    </template>
                  </el-table-column>
                  <el-table-column label="借方" width="95" align="right">
                    <template #default="{ row }">
                      <el-input-number :model-value="row.debit" :disabled="isReadonly" :controls="false" :precision="2" :formatter="amountFormatter" :parser="amountParser" size="small" style="width: 100%"
                        @change="(v: number) => updateCheckRow('bankToBook', row.id, 'debit', v ?? 0)" />
                    </template>
                  </el-table-column>
                  <el-table-column label="贷方" width="95" align="right">
                    <template #default="{ row }">
                      <el-input-number :model-value="row.credit" :disabled="isReadonly" :controls="false" :precision="2" :formatter="amountFormatter" :parser="amountParser" size="small" style="width: 100%"
                        @change="(v: number) => updateCheckRow('bankToBook', row.id, 'credit', v ?? 0)" />
                    </template>
                  </el-table-column>
                </el-table-column>
                <el-table-column label="一致" width="78">
                  <template #default="{ row }">
                    <el-select :model-value="row.infoConsistent" :disabled="isReadonly" size="small" clearable
                      @change="(v: string) => updateCheckRow('bankToBook', row.id, 'infoConsistent', (v || '') as YesNo)">
                      <el-option v-for="o in ynOptions" :key="o.value" :label="o.label" :value="o.value" />
                    </el-select>
                  </template>
                </el-table-column>
                <el-table-column label="第三方" width="78">
                  <template #default="{ row }">
                    <el-select :model-value="row.thirdParty" :disabled="isReadonly" size="small" clearable
                      @change="(v: string) => updateCheckRow('bankToBook', row.id, 'thirdParty', (v || '') as YesNo)">
                      <el-option v-for="o in ynOptions" :key="o.value" :label="o.label" :value="o.value" />
                    </el-select>
                  </template>
                </el-table-column>
                <el-table-column label="不一致原因" min-width="100">
                  <template #default="{ row }">
                    <el-input :model-value="row.inconsistencyReason" :disabled="isReadonly" size="small"
                      @change="(v: string) => updateCheckRow('bankToBook', row.id, 'inconsistencyReason', v)" />
                  </template>
                </el-table-column>
                <el-table-column label="支持文件" min-width="100">
                  <template #default="{ row }">
                    <el-input :model-value="row.supportDocs" :disabled="isReadonly" size="small"
                      @change="(v: string) => updateCheckRow('bankToBook', row.id, 'supportDocs', v)" />
                  </template>
                </el-table-column>
                <el-table-column label="结论" min-width="90">
                  <template #default="{ row }">
                    <el-input :model-value="row.conclusion" :disabled="isReadonly" size="small"
                      @change="(v: string) => updateCheckRow('bankToBook', row.id, 'conclusion', v)" />
                  </template>
                </el-table-column>
                <el-table-column width="50" fixed="right">
                  <template #default="{ row }">
                    <el-button type="danger" text size="small" :disabled="isReadonly" @click="removeCheckRow('bankToBook', row.id)">删</el-button>
                  </template>
                </el-table-column>
              </el-table>
              <div class="pager-row">
                <el-pagination
                  v-model:current-page="s2bPage"
                  v-model:page-size="pageSize"
                  :total="bankToBookView.length"
                  :page-sizes="[30, 50, 100, 200]"
                  layout="total, sizes, prev, pager, next"
                  small
                  background
                />
              </div>
            </div>
          </el-tab-pane>

          <!-- 说明结论 -->
          <el-tab-pane label="覆盖率 / 说明结论" name="audit">
            <el-card shadow="never" class="section-card">
              <template #header><span>三、审计说明 · 本期发生额核查比例</span></template>
              <el-table :data="[
                { side: '本期借方', book: coverage.bookDr, r1: coverage.bookToBankDr, r2: coverage.bankToBookDr, p1: coverage.ratio1Dr, p2: coverage.ratio2Dr },
                { side: '本期贷方', book: coverage.bookCr, r1: coverage.bookToBankCr, r2: coverage.bankToBookCr, p1: coverage.ratio1Cr, p2: coverage.ratio2Cr },
              ]" border size="small" style="max-width: 900px; margin-bottom: 12px">
                <el-table-column prop="side" label="" width="100" />
                <el-table-column label="账面发生额" align="right">
                  <template #default="{ row }">{{ fmtAmt(row.book) }}</template>
                </el-table-column>
                <el-table-column label="日记账→流水核查" align="right">
                  <template #default="{ row }">{{ fmtAmt(row.r1) }}</template>
                </el-table-column>
                <el-table-column label="流水→日记账核查" align="right">
                  <template #default="{ row }">{{ fmtAmt(row.r2) }}</template>
                </el-table-column>
                <el-table-column label="核查比例1" align="right">
                  <template #default="{ row }">{{ fmtRate(row.p1) }}</template>
                </el-table-column>
                <el-table-column label="核查比例2" align="right">
                  <template #default="{ row }">{{ fmtRate(row.p2) }}</template>
                </el-table-column>
              </el-table>
              <el-input
                type="textarea"
                :model-value="pack.coverageLowReason"
                :disabled="isReadonly"
                :autosize="{ minRows: 2 }"
                placeholder="如果检查比例较低/大额抽样总量说明原因…"
                @change="(v: string) => setCoverageLowReason(v)"
              />
            </el-card>

            <el-card shadow="never" class="section-card">
              <template #header><span>提示 · 异常红旗</span></template>
              <div v-for="t in pack.tips" :key="t.key" class="tip-row">
                <el-checkbox
                  :model-value="t.checked"
                  :disabled="isReadonly"
                  @change="(v: string | number | boolean) => updateTip(t.key, 'checked', Boolean(v))"
                >
                  {{ t.label }}
                </el-checkbox>
                <el-input
                  v-if="t.checked"
                  :model-value="t.note"
                  :disabled="isReadonly"
                  size="small"
                  placeholder="说明/索引"
                  style="max-width: 360px"
                  @change="(v: string) => updateTip(t.key, 'note', v)"
                />
              </div>
            </el-card>

            <el-card shadow="never" class="audit-note-card">
              <template #header>
                <div class="card-header">
                  <span>三、审计说明</span>
                  <el-button size="small" type="primary" plain :disabled="isReadonly" :loading="isGenerating('e1-31-audit-note')" @click="generateAuditNote">
                    <el-icon><MagicStick /></el-icon> AI辅助
                  </el-button>
                </div>
              </template>
              <el-input
                type="textarea"
                :model-value="auditNote"
                :disabled="isReadonly"
                :autosize="{ minRows: 4 }"
                placeholder="说明OCR取数、月度对碰、双向抽样、第三方回款及覆盖率…"
                @update:model-value="(v: string) => { if (!isReadonly) auditNote = v }"
                @change="(v: string) => saveNote(v)"
              />
            </el-card>

            <el-card shadow="never" class="audit-note-card">
              <template #header>
                <div class="card-header">
                  <span>四、审计结论</span>
                  <div class="header-actions">
                    <el-select size="small" placeholder="结论模板" style="width: 140px" :disabled="isReadonly" @change="applyConclusionTemplate">
                      <el-option v-for="t in conclusionTemplates" :key="t.value" :label="t.label" :value="t.value" />
                    </el-select>
                    <el-button size="small" type="primary" plain :disabled="isReadonly" :loading="isGenerating('e1-31-audit-conclusion')" @click="generateAuditConclusion">
                      <el-icon><MagicStick /></el-icon> AI辅助
                    </el-button>
                  </div>
                </div>
              </template>
              <el-input
                type="textarea"
                :model-value="auditConclusion"
                :disabled="isReadonly"
                :autosize="{ minRows: 3 }"
                placeholder="填写审计结论…"
                @update:model-value="(v: string) => { if (!isReadonly) auditConclusion = v }"
                @change="(v: string) => saveConclusion(v)"
              />
            </el-card>
          </el-tab-pane>
        </el-tabs>
    </E1IpoSheetChrome>

    <E1StatementOcrConfirmDialog
      v-model="ocrVisible"
      :fields="ocrFields"
      :confidence="ocrConfidence"
      :ocr-preview="ocrPreview"
      :file-name="ocrFileName"
      @confirm="onOcrConfirm"
    />

    <el-dialog
      v-model="samplingVisible"
      title="抽凭回填 · 银行日记账（E1-31）"
      width="960px"
      destroy-on-close
      top="4vh"
    >
      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="sampling-tip"
        title="建议科目范围 1002（银行存款）；确认后样本写入「流水/日记账明细」中的日记账侧，再执行自动匹配。"
      />
      <GtVoucherSamplingEngine
        v-if="samplingVisible"
        account-code="1002"
        :phase="samplingPhase"
        default-method="random"
        :workpaper-id="wpId"
        :project-id="projectId"
        :year="year"
        @filled="onSampleFilled"
      />
    </el-dialog>
  </div>
</template>

<style scoped>
.e1-tab-bank-flow { padding: 12px 0; }
.guidance-details {
  margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff;
  border-radius: 4px; padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.mb8 { margin-bottom: 8px; }
.tab-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  flex-wrap: wrap; gap: 8px; margin-bottom: 12px;
}
.toolbar-left, .toolbar-right, .card-header, .header-actions, .sub-toolbar {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
}
.sub-toolbar { margin-bottom: 8px; font-size: 13px; }
.sum-hint { color: #909399; margin-left: auto; }
.sampling-tip { margin-bottom: 12px; }
.chip-wrap { display: inline-flex; }
.not-applicable { padding: 48px 0; text-align: center; }
.section-card { margin-bottom: 12px; }
.meta-card { margin-bottom: 8px; }
.flow-tabs { margin-bottom: 12px; }
.table-scroll { overflow-x: auto; }
.pager-row { display: flex; justify-content: flex-end; margin-top: 8px; margin-bottom: 4px; }
.tip-row {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  margin-bottom: 8px; font-size: var(--wp-font-size, 13px);
}
.audit-note-card { margin-top: 12px; }
.card-header { font-weight: 500; width: 100%; justify-content: space-between; }
</style>
