<template>
  <div class="gt-c24-journal-detail">
    <!-- 工具栏：导入导出 dropdown（readonly 时隐藏） -->
    <div v-if="!isReadonly && !isLoading" class="c24-toolbar">
      <div class="toolbar-left" />
      <div class="toolbar-right">
        <el-dropdown trigger="click" size="small" @command="onImportExportCommand">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item command="exportData">导出数据</el-dropdown-item>
              <el-dropdown-item command="importData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>
    <!-- 隐藏文件选择器 -->
    <input
      ref="fileInputRef"
      type="file"
      accept=".xlsx,.xls,.csv"
      style="display: none;"
      @change="onFileSelected"
    />

    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <!-- 顶部操作引导区 -->
      <div class="guidance-area">
        <div class="guidance-header">
          <el-icon><InfoFilled /></el-icon>
          <span>操作流程引导</span>
        </div>
        <div class="guidance-steps">
          <div class="step-item">
            <span class="step-num">①</span>
            <span class="step-text">导入分录</span>
          </div>
          <div class="step-item">
            <span class="step-num">②</span>
            <span class="step-text">完整性测试</span>
          </div>
          <div class="step-item">
            <span class="step-num">③</span>
            <span class="step-text">异常/本福特分析</span>
          </div>
          <div class="step-item">
            <span class="step-num">④</span>
            <span class="step-text">汇总结论</span>
          </div>
        </div>
      </div>

      <!-- C24A 程序表 -->
      <div v-if="currentSheet === 'C24A'" class="c24-program-console">
        <GtAProgramConsole
          :wp-id="props.wpId"
          sheet-name="C24A"
          :schema="{ columns: [], rows: [] }"
          :html-data="{ programs: [], schema: { columns: [], rows: [] } }"
          :readonly="isReadonly"
        />
      </div>

      <!-- C24-0 汇总表 -->
      <div v-else-if="currentSheet === 'C24-0'">
        <C24SummarySheet
          :form-data="summaryForm"
          :conclusions="subConclusions"
          :is-readonly="isReadonly"
          @update:field="onSummaryFieldChange"
          @ai-suggest="onAiSuggest"
        />
      </div>

      <!-- C24-1 借贷发生额完整性 -->
      <div v-else-if="currentSheet === 'C24-1'">
        <C24BalanceIntegritySheet
          :result="balanceResult"
          :conclusion="conclusions['C24-1']"
          :is-readonly="isReadonly"
          @update:conclusion="onConclusionChange('C24-1', $event)"
          @ai-suggest="onAiSuggest"
        />
      </div>

      <!-- C24-2 分录余额对比 -->
      <div v-else-if="currentSheet === 'C24-2'">
        <C24TrialBalanceSheet
          :comparisons="trialBalanceComparisons"
          :conclusion="conclusions['C24-2']"
          :is-readonly="isReadonly"
          @update:conclusion="onConclusionChange('C24-2', $event)"
          @ai-suggest="onAiSuggest"
        />
      </div>

      <!-- C24-3 跳号测试 -->
      <div v-else-if="currentSheet === 'C24-3'">
        <C24GapTestSheet
          :gaps="gapResults"
          :gap-notes="gapNotes"
          :has-data="journalEntries.length > 0"
          :conclusion="conclusions['C24-3']"
          :is-readonly="isReadonly"
          @update:conclusion="onConclusionChange('C24-3', $event)"
          @update:gap-note="onGapNoteChange"
          @ai-suggest="onAiSuggest"
        />
      </div>

      <!-- C24-4 异常账户测试 -->
      <div v-else-if="currentSheet === 'C24-4'">
        <C24AnomalyAccountSheet
          :rows="accountRows"
          :has-data="journalEntries.length > 0"
          :conclusion="conclusions['C24-4']"
          :is-readonly="isReadonly"
          @update:conclusion="onConclusionChange('C24-4', $event)"
          @update:row="onAccountRowChange"
          @ai-suggest="onAiSuggest"
        />
      </div>

      <!-- C24-5 异常分录测试 -->
      <div v-else-if="currentSheet === 'C24-5'">
        <C24AnomalyEntrySheet
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :enabled-rules="enabledRules"
          :rule-params="ruleParams"
          :anomalies="anomalyResults"
          :anomaly-notes="anomalyNotes"
          :has-data="journalEntries.length > 0"
          :conclusion="conclusions['C24-5']"
          :is-readonly="isReadonly"
          :total-entry-count="journalEntries.length"
          @update:conclusion="onConclusionChange('C24-5', $event)"
          @update:enabled-rules="onEnabledRulesChange"
          @update:rule-param="onRuleParamChange"
          @update:anomaly-note="onAnomalyNoteChange"
          @run-screen="runAnomalyScreen"
          @ai-suggest="onAiSuggest"
          @conclusion-change="onSubConclusionRefresh"
        />
      </div>

      <!-- 本福特定律测试 -->
      <div v-else-if="currentSheet === '本福特'">
        <C24BenfordSheet
          :distribution="benfordDist"
          :chi-result="benfordChi"
          :sample-count="benfordSampleCount"
          :alpha="benfordAlpha"
          :has-data="journalEntries.length > 0"
          :conclusion="conclusions['benford']"
          :is-readonly="isReadonly"
          @update:conclusion="onConclusionChange('benford', $event)"
          @ai-suggest="onAiSuggest"
        />
      </div>

      <!-- 本福特-数据 虚拟分录参考 -->
      <div v-else-if="currentSheet === '本福特-数据'">
        <el-alert type="info" :closable="false" show-icon>
          <template #title>虚拟会计分录数据参考（只读）</template>
          <p style="margin-top: 8px; color: #606266;">
            此为本福特分析参考数据，实际测试使用导入的真实分录数据。
          </p>
        </el-alert>
      </div>

      <!-- 假期清单 -->
      <div v-else-if="currentSheet === '假期清单'">
        <C24HolidaySheet
          :holidays="holidays"
          :is-readonly="isReadonly"
          @add-holiday="onAddHoliday"
          @remove-holiday="onRemoveHoliday"
          @update-holiday="onUpdateHoliday"
        />
      </div>

      <!-- Fallback -->
      <div v-else>
        <el-alert type="info" :closable="false">{{ currentSheet }} — 暂无内容</el-alert>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtC24JournalDetail — C24 会计分录细节测试专属组件
 *
 * componentType: c24-journal-entry-detail
 * 对齐 D4 标准：sheetName v-if 分发，无内部 el-tabs
 *
 * Sheets: C24A / C24-0 汇总 / C24-1~5 / 本福特 / 本福特-数据 / 假期清单
 *
 * Spec: .kiro/specs/c23-c24-journal-entry-testing/
 * Task: 4.2
 * Requirements: 1.1, 1.5, 3.4, 4.3, 4.4, 5.3, 5.4, 6.1, 6.2, 6.3
 */
import { ref, computed, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  calcBalanceIntegrity,
  compareToTrialBalance,
  detectGaps,
  screenAnomalies,
  benfordDistribution,
  benfordChiSquareTest,
  type JournalEntry,
  type BalanceIntegrityResult,
  type TrialBalanceComparison,
  type GapResult,
  type AnomalyResult,
  type AnomalyRules,
  type BenfordDigitResult,
  type BenfordTestResult,
  type TrialBalanceRow,
} from '@/composables/useC24AnalyticsEngine'
import { useWpAiSuggest } from '@/composables/useWpAiSuggest'
import { useC24ImportExport } from '@/composables/useC24ImportExport'
import type { C24SummaryFormData } from './c24/C24SummarySheet.vue'
import type { GapNote } from './c24/C24GapTestSheet.vue'
import type { AccountRow } from './c24/C24AnomalyAccountSheet.vue'
import type { RuleParams, AnomalyNote } from './c24/C24AnomalyEntrySheet.vue'
import type { HolidayRow } from './c24/C24HolidaySheet.vue'

defineOptions({ name: 'GtC24JournalDetail' })

// ─── Lazy child components ───
const GtAProgramConsole = defineAsyncComponent(() => import('./GtAProgramConsole.vue'))
const C24SummarySheet = defineAsyncComponent(() => import('./c24/C24SummarySheet.vue'))
const C24BalanceIntegritySheet = defineAsyncComponent(() => import('./c24/C24BalanceIntegritySheet.vue'))
const C24TrialBalanceSheet = defineAsyncComponent(() => import('./c24/C24TrialBalanceSheet.vue'))
const C24GapTestSheet = defineAsyncComponent(() => import('./c24/C24GapTestSheet.vue'))
const C24AnomalyAccountSheet = defineAsyncComponent(() => import('./c24/C24AnomalyAccountSheet.vue'))
const C24AnomalyEntrySheet = defineAsyncComponent(() => import('./c24/C24AnomalyEntrySheet.vue'))
const C24BenfordSheet = defineAsyncComponent(() => import('./c24/C24BenfordSheet.vue'))
const C24HolidaySheet = defineAsyncComponent(() => import('./c24/C24HolidaySheet.vue'))

// ─── Props / Emits ───
const props = defineProps<{
  wpId: string
  projectId?: string
  wpCode?: string
  year?: string
  sheetName?: string
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
}>()

// ─── State ───
const isLoading = ref(true)
const isReadonly = computed(() => !!props.readonly)

const currentSheet = computed(() => {
  const name = props.sheetName || 'C24A'
  if (name.includes('C24A') || name.includes('程序表')) return 'C24A'
  if (name === 'C24-0' || name.includes('汇总')) return 'C24-0'
  if (name === 'C24-1' || name.includes('借贷')) return 'C24-1'
  if (name === 'C24-2' || name.includes('余额')) return 'C24-2'
  if (name === 'C24-3' || name.includes('跳号')) return 'C24-3'
  if (name === 'C24-4' || name.includes('异常账户')) return 'C24-4'
  if (name === 'C24-5' || name.includes('异常分录')) return 'C24-5'
  if (name === '本福特-数据') return '本福特-数据'
  if (name.includes('本福特')) return '本福特'
  if (name.includes('假期')) return '假期清单'
  return name
})

// ─── Journal entries (core data) ───
const journalEntries = ref<JournalEntry[]>([])
const trialBalance = ref<TrialBalanceRow[]>([])

// ─── C24-0 Summary form ───
const summaryForm = ref<C24SummaryFormData>({
  sourceAppName: '', sourceAppVersion: '', sourceExportTime: '',
  sourceFileRef: '', toolUsed: '', toolName: '', toolVersion: '',
  toolTime: '', conclusion: '',
})

// ─── Conclusions ───
const conclusions = ref<Record<string, string>>({
  'C24-1': '', 'C24-2': '', 'C24-3': '', 'C24-4': '', 'C24-5': '', 'benford': '',
})
const subConclusions = computed(() => conclusions.value)

// ─── C24-1 Balance Integrity ───
const balanceResult = ref<BalanceIntegrityResult>({ debitTotal: 0, creditTotal: 0, balanced: true })

// ─── C24-2 Trial Balance Comparison ───
const trialBalanceComparisons = ref<TrialBalanceComparison[]>([])

// ─── C24-3 Gap Test ───
const gapResults = ref<GapResult[]>([])
const gapNotes = ref<GapNote[]>([])

// ─── C24-4 Anomaly Accounts ───
const accountRows = ref<AccountRow[]>([])

// ─── C24-5 Anomaly Entries ───
const enabledRules = ref<string[]>([
  'holidays', 'night', 'frequent', 'large', 'approval',
  'round', 'tail', 'duplicate', 'unusual', 'volume',
  'special', 'vague', 'empty',
])
const ruleParams = ref<RuleParams>({
  nightStartHour: 22, nightEndHour: 6,
  largeAmountThreshold: 1000000, approvalLimit: 500000,
  roundAmountDigits: 4, vagueKeywordsText: '调整,暂估,其他,冲销',
})
const anomalyResults = ref<AnomalyResult[]>([])
const anomalyNotes = ref<AnomalyNote[]>([])

// ─── Benford ───
const benfordDist = ref<BenfordDigitResult[]>([])
const benfordChi = ref<BenfordTestResult>({ chi2Total: 0, criticalValue: 15.507, significant: false })
const benfordSampleCount = ref(0)
const benfordAlpha = ref(0.05)

// ─── Holidays ───
const holidays = ref<HolidayRow[]>([])

// ─── AI ───
const ai = useWpAiSuggest({ wpId: props.wpId, sheetName: 'C24' })

// ─── Import/Export ───
const importExport = useC24ImportExport(computed(() => props.wpId))
const fileInputRef = ref<HTMLInputElement | null>(null)

function onImportExportCommand(command: string) {
  switch (command) {
    case 'exportTemplate':
      importExport.exportTemplate()
      break
    case 'exportData':
      importExport.exportData()
      break
    case 'importData':
      fileInputRef.value?.click()
      break
  }
}

async function onFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  // Reset file input so same file can be re-selected
  input.value = ''
  const result = await importExport.importData(file)
  if (result && result.rowCount > 0) {
    // Re-load data after successful import then re-run analytics
    await selfLoad()
  }
}

// ─── Debounce ───
let saveTimer: ReturnType<typeof setTimeout> | null = null

function debounceSave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => { persistAll() }, 2000)
}

function flushPendingSaves() {
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
    persistAll()
  }
}

// ─── Analytics engine runner ───
function runAllAnalytics() {
  if (journalEntries.value.length === 0) return

  // C24-1 Balance integrity
  balanceResult.value = calcBalanceIntegrity(journalEntries.value)

  // C24-2 Trial balance comparison
  trialBalanceComparisons.value = compareToTrialBalance(journalEntries.value, trialBalance.value)

  // C24-3 Gap detection
  const voucherNos = journalEntries.value.map(e => e.voucherNo).filter(Boolean)
  gapResults.value = detectGaps(voucherNos)
  // Ensure gapNotes matches length
  while (gapNotes.value.length < gapResults.value.length) {
    gapNotes.value.push({ abnormal: '', note: '' })
  }

  // C24-4 Account analysis
  buildAccountRows()

  // C24-5 Anomaly screening
  runAnomalyScreen()

  // Benford
  runBenfordAnalysis()
}

function buildAccountRows() {
  const userStats = new Map<string, { prepare: number; post: number; review: number }>()
  for (const e of journalEntries.value) {
    if (e.preparer) {
      const s = userStats.get(e.preparer) || { prepare: 0, post: 0, review: 0 }
      s.prepare++
      userStats.set(e.preparer, s)
    }
    if (e.poster) {
      const s = userStats.get(e.poster) || { prepare: 0, post: 0, review: 0 }
      s.post++
      userStats.set(e.poster, s)
    }
    if (e.reviewer) {
      const s = userStats.get(e.reviewer) || { prepare: 0, post: 0, review: 0 }
      s.review++
      userStats.set(e.reviewer, s)
    }
  }

  // Preserve existing user-editable fields
  const existingMap = new Map(accountRows.value.map(r => [r.user, r]))
  const rows: AccountRow[] = []
  for (const [user, stats] of userStats) {
    const existing = existingMap.get(user)
    rows.push({
      user,
      role: existing?.role || '',
      prepareCount: stats.prepare,
      postCount: stats.post,
      reviewCount: stats.review,
      inList: false, // TODO: cross-check with C23 personnel
      abnormal: existing?.abnormal || '',
      note: existing?.note || '',
      conclusion: existing?.conclusion || '',
      indexRef: existing?.indexRef || '',
    })
  }
  accountRows.value = rows
}

function runAnomalyScreen() {
  if (journalEntries.value.length === 0) return
  const rules: AnomalyRules = {
    holidays: enabledRules.value.includes('holidays')
      ? holidays.value.map(h => h.date).filter(Boolean)
      : [],
    nightStartHour: enabledRules.value.includes('night') ? ruleParams.value.nightStartHour : 99,
    nightEndHour: enabledRules.value.includes('night') ? ruleParams.value.nightEndHour : 0,
    largeAmountThreshold: enabledRules.value.includes('large') ? ruleParams.value.largeAmountThreshold : Infinity,
    approvalLimit: enabledRules.value.includes('approval') ? ruleParams.value.approvalLimit : 0,
    roundAmountDigits: enabledRules.value.includes('round') ? ruleParams.value.roundAmountDigits : 0,
    vagueKeywords: enabledRules.value.includes('vague')
      ? ruleParams.value.vagueKeywordsText.split(',').map(s => s.trim()).filter(Boolean)
      : [],
    checkEmptySummary: enabledRules.value.includes('empty'),
    duplicateCheck: enabledRules.value.includes('duplicate'),
  }
  anomalyResults.value = screenAnomalies(journalEntries.value, rules)
  // Preserve existing notes
  while (anomalyNotes.value.length < anomalyResults.value.length) {
    anomalyNotes.value.push({ checkContent: '', conclusion: '', indexRef: '' })
  }
  anomalyNotes.value.length = anomalyResults.value.length
}

function runBenfordAnalysis() {
  const amounts = journalEntries.value
    .map(e => Math.max(e.debit, e.credit))
    .filter(a => a > 0)
  benfordSampleCount.value = amounts.length
  benfordDist.value = benfordDistribution(amounts)
  benfordChi.value = benfordChiSquareTest(benfordDist.value, benfordAlpha.value)
}

// ─── Event handlers ───

function onSummaryFieldChange(field: keyof C24SummaryFormData, value: string) {
  (summaryForm.value as any)[field] = value
  if (field === 'conclusion') {
    saveConclusion('C24-0-conclusion', value)
  } else {
    debounceSave()
  }
}

function onConclusionChange(key: string, value: string) {
  conclusions.value[key] = value
  const itemId = key === 'benford' ? 'C24-benford-conclusion' : `${key}-conclusion`
  saveConclusion(itemId, value)
  // Req 11.2: 结论回填 C24-0 汇总表（即时保存 + 保留来源索引 Req 11.4）
  writeConclusionToSummary(key, value)
}

/**
 * Req 11.2 + 11.4: 测试项结论变更 → 回填 C24-0 汇总表对应测试项
 * 保留来源测试项索引用于双向追溯
 */
function writeConclusionToSummary(sourceKey: string, conclusionText: string) {
  if (!props.wpId || isReadonly.value) return
  // 持久化到 C24-0 summary 的 subConclusions（item_id 带来源标识）
  const sourceIndex = sourceKey === 'benford' ? 'C24-本福特' : sourceKey
  const summaryItemId = `C24-0-sub-${sourceKey}`
  // 写入 conclusion=结论文本, remark=来源测试项索引
  api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
    project_id: props.projectId || undefined,
    items: [{ item_id: summaryItemId, conclusion: conclusionText || null, remark: sourceIndex }],
  }).catch(() => { /* silent - best effort */ })
}

/** Req 11.2: 异常分录结论变更时触发刷新（来自 C24AnomalyEntrySheet） */
function onSubConclusionRefresh() {
  // 子表结论变更会触发 C24-5 整体结论的联动感知，但不自动覆盖
  // 主要通过 onConclusionChange 路径走回填
}

function onGapNoteChange(index: number, field: 'abnormal' | 'note', value: string) {
  if (!gapNotes.value[index]) gapNotes.value[index] = { abnormal: '', note: '' }
  gapNotes.value[index][field] = value
  debounceSave()
}

function onAccountRowChange(index: number, field: string, value: string) {
  if (accountRows.value[index]) {
    ;(accountRows.value[index] as any)[field] = value
    debounceSave()
  }
}

function onEnabledRulesChange(rules: string[]) {
  enabledRules.value = rules
  debounceSave()
}

function onRuleParamChange(key: keyof RuleParams, value: any) {
  ;(ruleParams.value as any)[key] = value
  debounceSave()
}

function onAnomalyNoteChange(index: number, field: string, value: string) {
  if (!anomalyNotes.value[index]) anomalyNotes.value[index] = { checkContent: '', conclusion: '' }
  ;(anomalyNotes.value[index] as any)[field] = value
  debounceSave()
}

function onAddHoliday() {
  if (isReadonly.value) return
  holidays.value.push({ date: '', name: '' })
  debounceSave()
}

function onRemoveHoliday(index: number) {
  if (isReadonly.value) return
  holidays.value.splice(index, 1)
  debounceSave()
}

function onUpdateHoliday(index: number, field: 'date' | 'name', value: string) {
  if (isReadonly.value) return
  holidays.value[index][field] = value
  debounceSave()
}

async function onAiSuggest(fieldId: string) {
  if (isReadonly.value || !ai.aiEnabled.value) return
  const fieldName = fieldId.replace('C24-', '').replace('-conclusion', '') + ' 测试结论'
  let currentVal = ''
  if (fieldId === 'C24-0-conclusion') currentVal = summaryForm.value.conclusion
  else if (fieldId === 'C24-benford-conclusion') currentVal = conclusions.value['benford']
  else {
    const key = fieldId.replace('-conclusion', '')
    currentVal = conclusions.value[key] || ''
  }
  await ai.requestSuggestion(fieldName, currentVal)
  const text = ai.adoptSuggestion()
  if (text) {
    if (fieldId === 'C24-0-conclusion') {
      summaryForm.value.conclusion = text
      saveConclusion('C24-0-conclusion', text)
    } else if (fieldId === 'C24-benford-conclusion') {
      conclusions.value['benford'] = text
      saveConclusion('C24-benford-conclusion', text)
    } else {
      const key = fieldId.replace('-conclusion', '')
      conclusions.value[key] = text
      saveConclusion(fieldId, text)
    }
  }
}

// ─── Persistence ───

async function saveConclusion(itemId: string, value: string) {
  if (!props.wpId || isReadonly.value) return
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId || undefined,
      items: [{ item_id: itemId, conclusion: value || null, remark: null }],
    })
    emit('save')
  } catch { /* silent */ }
}

async function persistAll() {
  if (!props.wpId || isReadonly.value) return
  const items: Array<{ item_id: string; conclusion?: string | null; remark?: string | null }> = []

  // C24-0 summary fields
  items.push({ item_id: 'C24-0-source-appName', conclusion: null, remark: summaryForm.value.sourceAppName || null })
  items.push({ item_id: 'C24-0-source-appVersion', conclusion: null, remark: summaryForm.value.sourceAppVersion || null })
  items.push({ item_id: 'C24-0-source-exportTime', conclusion: null, remark: summaryForm.value.sourceExportTime || null })
  items.push({ item_id: 'C24-0-source-fileRef', conclusion: null, remark: summaryForm.value.sourceFileRef || null })
  items.push({ item_id: 'C24-0-tool-used', conclusion: summaryForm.value.toolUsed || null, remark: null })
  items.push({ item_id: 'C24-0-tool-name', conclusion: summaryForm.value.toolName || null, remark: null })
  items.push({ item_id: 'C24-0-tool-version', conclusion: null, remark: summaryForm.value.toolVersion || null })
  items.push({ item_id: 'C24-0-tool-time', conclusion: null, remark: summaryForm.value.toolTime || null })
  items.push({ item_id: 'C24-0-conclusion', conclusion: summaryForm.value.conclusion || null, remark: null })

  // Conclusions
  for (const [key, val] of Object.entries(conclusions.value)) {
    const itemId = key === 'benford' ? 'C24-benford-conclusion' : `${key}-conclusion`
    items.push({ item_id: itemId, conclusion: val || null, remark: null })
  }

  // Journal entries stored as JSON in remark
  items.push({ item_id: 'C24-journal-entries', conclusion: null, remark: JSON.stringify(journalEntries.value) })

  // Gap notes
  gapNotes.value.forEach((gn, i) => {
    items.push({ item_id: `C24-3-gap-${i}-abnormal`, conclusion: gn.abnormal || null, remark: null })
    items.push({ item_id: `C24-3-gap-${i}-note`, conclusion: null, remark: gn.note || null })
  })

  // Account rows (user-editable fields only)
  accountRows.value.forEach((row, i) => {
    items.push({ item_id: `C24-4-row-${i}-role`, conclusion: null, remark: row.role || null })
    items.push({ item_id: `C24-4-row-${i}-abnormal`, conclusion: row.abnormal || null, remark: null })
    items.push({ item_id: `C24-4-row-${i}-note`, conclusion: null, remark: row.note || null })
    items.push({ item_id: `C24-4-row-${i}-conclusion`, conclusion: row.conclusion || null, remark: null })
    items.push({ item_id: `C24-4-row-${i}-indexRef`, conclusion: null, remark: row.indexRef || null })
  })

  // C24-5 rules config
  items.push({
    item_id: 'C24-5-rules',
    conclusion: null,
    remark: JSON.stringify({ enabledRules: enabledRules.value, params: ruleParams.value }),
  })

  // Anomaly notes
  anomalyNotes.value.forEach((an, i) => {
    items.push({ item_id: `C24-5-row-${i}-checkContent`, conclusion: null, remark: an.checkContent || null })
    items.push({ item_id: `C24-5-row-${i}-conclusion`, conclusion: an.conclusion || null, remark: null })
    items.push({ item_id: `C24-5-row-${i}-indexRef`, conclusion: null, remark: an.indexRef || null })
  })

  // Holidays
  items.push({ item_id: 'C24-holidays', conclusion: null, remark: JSON.stringify(holidays.value) })

  // Benford params
  items.push({ item_id: 'C24-benford-alpha', conclusion: null, remark: String(benfordAlpha.value) })

  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId || undefined,
      items,
    })
    emit('save')
  } catch (err: any) {
    ElMessage.error('保存失败，数据已保留在本地')
    console.warn('[C24] persist failed:', err)
  }
}

// ─── selfLoad ───
async function selfLoad() {
  try {
    const res = await api.get<any[]>(`/api/workpapers/${props.wpId}/checklist-responses`, { _silent: true } as any)
    const items: Array<{ item_id: string; conclusion?: string; remark?: string }> = Array.isArray(res) ? res : (res as any)?.data || []

    const map = new Map<string, { conclusion?: string; remark?: string }>()
    for (const item of items) {
      if (item.item_id?.startsWith('C24-')) {
        map.set(item.item_id, { conclusion: item.conclusion, remark: item.remark })
      }
    }

    // Summary fields
    summaryForm.value.sourceAppName = map.get('C24-0-source-appName')?.remark || ''
    summaryForm.value.sourceAppVersion = map.get('C24-0-source-appVersion')?.remark || ''
    summaryForm.value.sourceExportTime = map.get('C24-0-source-exportTime')?.remark || ''
    summaryForm.value.sourceFileRef = map.get('C24-0-source-fileRef')?.remark || ''
    summaryForm.value.toolUsed = map.get('C24-0-tool-used')?.conclusion || ''
    summaryForm.value.toolName = map.get('C24-0-tool-name')?.conclusion || ''
    summaryForm.value.toolVersion = map.get('C24-0-tool-version')?.remark || ''
    summaryForm.value.toolTime = map.get('C24-0-tool-time')?.remark || ''
    summaryForm.value.conclusion = map.get('C24-0-conclusion')?.conclusion || ''

    // Conclusions
    conclusions.value['C24-1'] = map.get('C24-1-conclusion')?.conclusion || ''
    conclusions.value['C24-2'] = map.get('C24-2-conclusion')?.conclusion || ''
    conclusions.value['C24-3'] = map.get('C24-3-conclusion')?.conclusion || ''
    conclusions.value['C24-4'] = map.get('C24-4-conclusion')?.conclusion || ''
    conclusions.value['C24-5'] = map.get('C24-5-conclusion')?.conclusion || ''
    conclusions.value['benford'] = map.get('C24-benford-conclusion')?.conclusion || ''

    // Journal entries
    const jeRemark = map.get('C24-journal-entries')?.remark
    if (jeRemark) {
      try { journalEntries.value = JSON.parse(jeRemark) } catch { journalEntries.value = [] }
    }

    // Holidays
    const holRemark = map.get('C24-holidays')?.remark
    if (holRemark) {
      try { holidays.value = JSON.parse(holRemark) } catch { holidays.value = [] }
    }

    // C24-5 rules config
    const rulesRemark = map.get('C24-5-rules')?.remark
    if (rulesRemark) {
      try {
        const parsed = JSON.parse(rulesRemark)
        if (parsed.enabledRules) enabledRules.value = parsed.enabledRules
        if (parsed.params) Object.assign(ruleParams.value, parsed.params)
      } catch { /* use defaults */ }
    }

    // Benford alpha
    const alphaStr = map.get('C24-benford-alpha')?.remark
    if (alphaStr) benfordAlpha.value = parseFloat(alphaStr) || 0.05

    // Gap notes
    const loadedGapNotes: GapNote[] = []
    for (let i = 0; i < 100; i++) {
      const abn = map.get(`C24-3-gap-${i}-abnormal`)
      const note = map.get(`C24-3-gap-${i}-note`)
      if (!abn && !note) break
      loadedGapNotes.push({ abnormal: abn?.conclusion || '', note: note?.remark || '' })
    }
    gapNotes.value = loadedGapNotes

    // Account row editable fields
    const loadedAccountEdits: Array<{ role: string; abnormal: string; note: string; conclusion: string; indexRef: string }> = []
    for (let i = 0; i < 200; i++) {
      const role = map.get(`C24-4-row-${i}-role`)
      if (!role && !map.get(`C24-4-row-${i}-abnormal`)) break
      loadedAccountEdits.push({
        role: role?.remark || '',
        abnormal: map.get(`C24-4-row-${i}-abnormal`)?.conclusion || '',
        note: map.get(`C24-4-row-${i}-note`)?.remark || '',
        conclusion: map.get(`C24-4-row-${i}-conclusion`)?.conclusion || '',
        indexRef: map.get(`C24-4-row-${i}-indexRef`)?.remark || '',
      })
    }

    // Anomaly notes
    const loadedAnomalyNotes: AnomalyNote[] = []
    for (let i = 0; i < 500; i++) {
      const cc = map.get(`C24-5-row-${i}-checkContent`)
      const conc = map.get(`C24-5-row-${i}-conclusion`)
      const idxRef = map.get(`C24-5-row-${i}-indexRef`)
      if (!cc && !conc && !idxRef) break
      loadedAnomalyNotes.push({
        checkContent: cc?.remark || '',
        conclusion: conc?.conclusion || '',
        indexRef: idxRef?.remark || '',
      })
    }
    anomalyNotes.value = loadedAnomalyNotes

    // Run analytics after loading data
    if (journalEntries.value.length > 0) {
      runAllAnalytics()
      // Merge loaded account edits into computed account rows
      accountRows.value.forEach((row, i) => {
        if (loadedAccountEdits[i]) {
          row.role = loadedAccountEdits[i].role || row.role
          row.abnormal = loadedAccountEdits[i].abnormal || row.abnormal
          row.note = loadedAccountEdits[i].note || row.note
          row.conclusion = loadedAccountEdits[i].conclusion || row.conclusion
          row.indexRef = loadedAccountEdits[i].indexRef || row.indexRef
        }
      })
    }
  } catch (err) {
    console.warn('[GtC24JournalDetail] selfLoad failed:', err)
  } finally {
    isLoading.value = false
  }
}

// ─── Lifecycle ───
onMounted(() => { selfLoad() })
onBeforeUnmount(() => { flushPendingSaves() })
defineExpose({ reload: selfLoad })
</script>

<style scoped>
.gt-c24-journal-detail {
  padding: 12px;
  font-size: 13px;
}
.c24-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  padding: 0 4px;
}
.toolbar-left {}
.toolbar-right {
  display: flex;
  gap: 8px;
}
.loading-container {
  padding: 24px;
}
.guidance-area {
  background: linear-gradient(135deg, #ecf5ff 0%, #d9ecff 100%);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}
.guidance-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 14px;
  color: #303133;
  margin-bottom: 12px;
}
.guidance-header .el-icon {
  color: #409eff;
  font-size: 16px;
}
.guidance-steps {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 16px;
}
.step-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: rgba(255, 255, 255, 0.7);
  border-radius: 6px;
}
.step-num {
  font-weight: 700;
  color: #409eff;
  font-size: 14px;
}
.step-text {
  font-size: 13px;
  color: #303133;
}
</style>
