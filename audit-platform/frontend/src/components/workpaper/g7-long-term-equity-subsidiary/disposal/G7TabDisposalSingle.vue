<template>
  <div class="g7-tab-disposal-single">
    <div class="section-head">
      <div>
        <h3 class="sheet-title">G7-11 处置检查（非一揽子交易）</h3>
        <div class="sheet-subtitle">个别损益 = 对价 − 账面 − 股利 + 可转OCI；合并另加减调整与净资产份额</div>
      </div>
      <div class="head-actions">
        <GtIndexChip value="wp:G7-11" :context-project-id="projectId" />
        <el-button size="small" :disabled="isReadonly" @click="addRow">新增行</el-button>
        <el-button size="small" :disabled="isReadonly || !rows.length" @click="syncBookFromG710">从 G7-10 带入账面</el-button>
        <el-button size="small" :disabled="isReadonly" :loading="investeeLoading" @click="loadG74Investees(true)">刷新 G7-4</el-button>
        <el-dropdown @command="handleImportExportCommand">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export">导出数据</el-dropdown-item>
              <el-dropdown-item v-if="!isReadonly" command="import">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" type="primary" plain :disabled="isReadonly" :loading="aiLoading" @click="handleAi">
          <el-icon><MagicStick /></el-icon> AI结论
        </el-button>
        <el-button size="small" @click="openReviewDialog('G7-11-disposal-single')">💬 复核</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      审计目标：确认非一揽子交易下处置子公司股权的处置损益计算准确（个别报表=对价−账面−应收股利+可转损益OCI；合并层面另加合并调整与净资产份额影响），会计处理符合 CAS2/CAS33。
      处置比例须在 0～1（可等于 1 即 100%）。「其他综合收益累计」仅留痕，公式取「可转OCI」。
    </el-alert>

    <el-alert
      v-if="ratioWarnings.length"
      type="warning"
      :closable="false"
      show-icon
      class="validation-alert"
    >
      <template #title>处置比例校验</template>
      <div v-for="message in ratioWarnings.slice(0, 6)" :key="message">• {{ message }}</div>
    </el-alert>

    <el-tag v-if="investeeOptions.length" size="small" type="success" class="investee-tag">
      G7-4 子公司 {{ investeeOptions.length }} 家
    </el-tag>

    <el-skeleton v-if="loading" :rows="6" animated />
    <div v-else class="disposal-single-content">
      <input ref="fileInputRef" type="file" accept=".xlsx,.xls" class="hidden-input" @change="handleFileChange" />

      <el-table :data="rows" border size="small" max-height="580" highlight-current-row row-key="id" style="font-size: 13px">
        <el-table-column type="index" label="#" width="45" fixed />
        <el-table-column label="被投资单位" width="160" fixed>
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly && investeeOptions.length"
              :model-value="row.investeeId || row.investeeName"
              filterable
              allow-create
              default-first-option
              clearable
              size="small"
              placeholder="选择或输入"
              style="width: 100%"
              @change="(id: string) => onInvesteePick(row, id)"
            >
              <el-option v-for="opt in investeeOptions" :key="opt.id" :label="opt.name" :value="opt.id" />
            </el-select>
            <el-input
              v-else
              v-model="row.investeeName"
              size="small"
              :disabled="isReadonly"
              @change="onRowEdit(row)"
            />
          </template>
        </el-table-column>
        <el-table-column label="处置日" width="140">
          <template #default="{ row }">
            <el-date-picker
              v-model="row.disposalDate"
              type="date"
              value-format="YYYY-MM-DD"
              size="small"
              :disabled="isReadonly"
              style="width: 100%"
              @change="saveRows"
            />
          </template>
        </el-table-column>
        <el-table-column label="处置比例" width="110" align="right">
          <template #default="{ row }">
            <RatioInput v-model="row.disposalRatio" :disabled="isReadonly" @change="onRatioChange(row)" />
          </template>
        </el-table-column>
        <el-table-column label="处置对价" width="120" align="right">
          <template #default="{ row }">
            <MoneyInput v-model="row.disposalPrice" :disabled="isReadonly" @change="onFormulaEdit(row)" />
          </template>
        </el-table-column>
        <el-table-column label="处置日账面" width="120" align="right">
          <template #default="{ row }">
            <MoneyInput v-model="row.disposalDateBookValue" :disabled="isReadonly" @change="onFormulaEdit(row)" />
          </template>
        </el-table-column>
        <el-table-column label="应收股利" width="110" align="right">
          <template #default="{ row }">
            <MoneyInput v-model="row.disposalDateDividend" :disabled="isReadonly" @change="onFormulaEdit(row)" />
          </template>
        </el-table-column>
        <el-table-column width="120" align="right">
          <template #header>
            <el-tooltip content="仅作留痕；个别处置损益公式使用「可转OCI」" placement="top">
              <span>OCI累计</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <MoneyInput v-model="row.priorOCICumulative" :disabled="isReadonly" @change="saveRows" />
          </template>
        </el-table-column>
        <el-table-column label="可转OCI" width="110" align="right">
          <template #default="{ row }">
            <MoneyInput v-model="row.transferableOCI" :disabled="isReadonly" @change="onFormulaEdit(row)" />
          </template>
        </el-table-column>
        <el-table-column label="个别处置损益" width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="= 对价 − 账面 − 应收股利 + 可转OCI">
              {{ row.individualGain.toFixed(2) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="合并调整" width="110" align="right">
          <template #default="{ row }">
            <MoneyInput v-model="row.consolidationAdjustment" :disabled="isReadonly" @change="onFormulaEdit(row)" />
          </template>
        </el-table-column>
        <el-table-column label="净资产份额" width="110" align="right">
          <template #default="{ row }">
            <MoneyInput v-model="row.consolidatedNetAssetShare" :disabled="isReadonly" @change="onFormulaEdit(row)" />
          </template>
        </el-table-column>
        <el-table-column min-width="150" align="right">
          <template #header>
            <el-tooltip content="默认 = 个别损益 + 合并调整 − 净资产份额；可手工覆盖后点「按公式」恢复" placement="top">
              <span>合并处置损益</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <div class="consol-gain-cell">
              <MoneyInput
                :model-value="row.consolidatedGain"
                :disabled="isReadonly"
                @update:model-value="(v: number) => onConsolGainEdit(row, v)"
                @change="saveRows"
              />
              <el-button
                v-if="row.consolidatedGainManual && !isReadonly"
                link
                type="primary"
                size="small"
                @click="clearConsolOverride(row)"
              >按公式</el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="审计结论" min-width="140">
          <template #default="{ row }">
            <el-input v-model="row.auditConclusion" size="small" :disabled="isReadonly" @change="saveRows" />
          </template>
        </el-table-column>
        <el-table-column label="索引" width="90">
          <template #default="{ row }">
            <el-input v-model="row.indexRef" size="small" :disabled="isReadonly" @change="saveRows" />
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="70" fixed="right">
          <template #default="{ $index }">
            <el-button link type="danger" size="small" @click="removeRow($index)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-card class="audit-note-card" shadow="never">
      <template #header>
        <div class="conclusion-header"><span>审计说明</span></div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：可概述所执行程序、测试情况及结果，拟调整/未调整事项及其影响。"
        @change="saveAuditNote"
      />
    </el-card>

    <el-card class="conclusion-card" shadow="never">
      <template #header>
        <div class="conclusion-header">
          <span>审计结论</span>
          <el-button size="small" type="primary" plain :disabled="isReadonly" :loading="aiLoading" @click="handleAi">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="对非一揽子处置的审计结论..."
        @change="saveAuditConclusion"
      />
    </el-card>

    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>个别处置损益 = 处置对价 − 处置日账面价值 − 应收股利 + 可转损益 OCI（CAS2）</li>
        <li>合并处置损益默认 = 个别损益 + 合并调整 − 净资产份额；可手工覆盖</li>
        <li>「OCI累计」不参与公式，仅底稿留痕；请填「可转OCI」</li>
        <li>被投资单位优先从 G7-4 选择；「从 G7-10 带入账面」匹配 companyName/investeeName，优先取不丧失控制权处置后剩余账面 ①×(1−③/②)</li>
        <li>处置比例以小数填写（如 0.30 = 30%），范围 0～1</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G7TabDisposalSingle — G7-11 处置（非一揽子）
 * 字段与后端 _G7_11_KEYS / g7DisposalSingleModel 对齐
 */
import { ref, computed, inject, onMounted, defineComponent, h } from 'vue'
import { ElMessage, ElInputNumber } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import http from '@/utils/http'
import { extractG7AiText } from '../../composables/g7AiText'
import { api } from '@/services/apiProxy'
import GtIndexChip from '../../GtIndexChip.vue'
import { useG7SubFormData } from '../../composables/useG7SubFormData'
import { useG7SubImportExport } from '../../composables/useG7SubImportExport'
import { WorkpaperRuntimeContextKey } from '../../composables/useWorkpaperScaffold'
import { loadSubsidiaryInvestees, type G7SubsidiaryInvesteeOption } from '../../composables/g7EquityMethodCrossSheet'
import { emitG7SourceRowsSaved } from '../../composables/g7DisclosureCrossSheet'
import {
  createEmptyDisposalSingleRow,
  hydrateDisposalSingleRows,
  recalcDisposalSingleRow,
  validateDisposalRatio,
  clearConsolidatedGainManual,
  setConsolidatedGainManual,
  pickBookValueFromG710,
  type G7DisposalSingleRow,
} from './g7DisposalSingleModel'

const props = defineProps<{
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const isReadonly = computed(() => !!props.readonly)
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const runtime = inject(WorkpaperRuntimeContextKey, null)
const scheduleAutoSnapshot = runtime?.version?.scheduleAutoSnapshot ?? (() => undefined)

const formData = useG7SubFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  onAfterSave: () => {
    scheduleAutoSnapshot()
    emitG7SourceRowsSaved({
      projectId: props.projectId,
      wpId: props.wpId,
      itemIds: [DATA_KEY],
    })
  },
})
const importExport = useG7SubImportExport({ wpId: computed(() => props.wpId) })

const DATA_KEY = 'G7-11-rows'
const NOTE_KEY = 'G7-11-disposal-single-audit-note'
const CONCLUSION_KEY = 'G7-11-disposal-single-audit-conclusion'
const G7_4_ROWS_KEY = 'G7-4-rows'
const G7_10_ROWS_KEY = 'G7-10-rows'

const rows = ref<G7DisposalSingleRow[]>([])
const loading = ref(true)
const auditNote = ref('')
const conclusion = ref('')
const aiLoading = ref(false)
const investeeLoading = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)
const investeeOptions = ref<G7SubsidiaryInvesteeOption[]>([])
const g710Cache = ref<unknown>(null)

const ratioWarnings = computed(() => {
  const msgs: string[] = []
  for (const row of rows.value) {
    if (!row.investeeName && !row.disposalRatio) continue
    const v = validateDisposalRatio(row.disposalRatio)
    if (!v.valid) {
      msgs.push(`${row.investeeName || `第${row.seq}行`}：${v.message}`)
    }
  }
  return msgs
})

const MoneyInput = defineComponent({
  props: { modelValue: { type: Number, default: 0 }, disabled: Boolean },
  emits: ['update:modelValue', 'change'],
  setup(p, { emit }) {
    return () => h(ElInputNumber, {
      modelValue: p.modelValue,
      disabled: p.disabled,
      controls: false,
      precision: 2,
      onUpdateModelValue: (v: number | undefined) => emit('update:modelValue', v ?? 0),
      onChange: () => emit('change'),
      style: 'width:100%',
    })
  },
})
const RatioInput = defineComponent({
  props: { modelValue: { type: Number, default: 0 }, disabled: Boolean },
  emits: ['update:modelValue', 'change'],
  setup(p, { emit }) {
    return () => h(ElInputNumber, {
      modelValue: p.modelValue,
      disabled: p.disabled,
      min: 0,
      max: 1,
      step: 0.01,
      precision: 4,
      controls: false,
      onUpdateModelValue: (v: number | undefined) => emit('update:modelValue', v ?? 0),
      onChange: () => emit('change'),
      style: 'width:100%',
    })
  },
})

function parseJson(raw: string | null | undefined): unknown {
  if (!raw) return null
  try { return JSON.parse(raw) } catch { return null }
}

function saveRows(): void {
  if (isReadonly.value) return
  formData.debouncedSave(DATA_KEY, { conclusion: JSON.stringify(rows.value), remark: null })
}

function onRowEdit(row: G7DisposalSingleRow): void {
  void row
  saveRows()
}

function onFormulaEdit(row: G7DisposalSingleRow): void {
  recalcDisposalSingleRow(row)
  saveRows()
}

function onRatioChange(row: G7DisposalSingleRow): void {
  const v = validateDisposalRatio(row.disposalRatio)
  if (!v.valid) ElMessage.warning(v.message || '处置比例无效')
  saveRows()
}

function onConsolGainEdit(row: G7DisposalSingleRow, value: number): void {
  setConsolidatedGainManual(row, value)
}

function clearConsolOverride(row: G7DisposalSingleRow): void {
  clearConsolidatedGainManual(row)
  saveRows()
}

function onInvesteePick(row: G7DisposalSingleRow, id: string): void {
  const opt = investeeOptions.value.find(o => o.id === id)
  if (opt) {
    row.investeeId = opt.id
    row.investeeName = opt.name
  } else if (id) {
    row.investeeId = id
    row.investeeName = id
  } else {
    row.investeeId = undefined
    row.investeeName = ''
  }
  saveRows()
}

function addRow(): void {
  rows.value.push(createEmptyDisposalSingleRow(rows.value.length + 1))
  saveRows()
}

function removeRow(index: number): void {
  rows.value.splice(index, 1)
  rows.value.forEach((row, i) => { row.seq = i + 1 })
  if (!rows.value.length) addRow()
  saveRows()
}

function saveAuditNote(value: string): void {
  if (!isReadonly.value) formData.debouncedSave(NOTE_KEY, { remark: value, conclusion: null })
}

function saveAuditConclusion(value: string): void {
  if (!isReadonly.value) formData.debouncedSave(CONCLUSION_KEY, { remark: value, conclusion: null })
}

async function loadG74Investees(showToast = false): Promise<void> {
  if (!props.wpId) return
  investeeLoading.value = true
  try {
    const res = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
    const item = responses.find((r: any) => r.item_id === G7_4_ROWS_KEY)
    investeeOptions.value = loadSubsidiaryInvestees(item?.conclusion)
    const g10 = responses.find((r: any) => r.item_id === G7_10_ROWS_KEY)
    if (g10?.conclusion) g710Cache.value = parseJson(String(g10.conclusion)) ?? g10.conclusion
    if (showToast && investeeOptions.value.length) {
      ElMessage.success(`已加载 G7-4 子公司 ${investeeOptions.value.length} 家`)
    }
  } catch {
    investeeOptions.value = []
  } finally {
    investeeLoading.value = false
  }
}

function syncBookFromG710(): void {
  const source = g710Cache.value ?? formData.data.value.get(G7_10_ROWS_KEY)?.conclusion
  if (!source) {
    ElMessage.info('未找到 G7-10 数据，请先编制「不丧失控制权」表或刷新 G7-4')
    return
  }
  let n = 0
  for (const row of rows.value) {
    const book = pickBookValueFromG710(source, row.investeeName, row.investeeId)
    if (book != null) {
      row.disposalDateBookValue = book
      recalcDisposalSingleRow(row)
      n++
    }
  }
  if (n) saveRows()
  ElMessage.success(n ? `已从 G7-10 带入 ${n} 行账面价值` : '未匹配到同名被投资单位')
}

async function handleAi(): Promise<void> {
  aiLoading.value = true
  try {
    const response = await http.post(`/api/workpapers/${props.wpId}/g7-sub/ai/disposal-conclusion`, {
      existingContent: conclusion.value,
      relatedContext: {
        sheet: 'G7-11',
        ratioWarnings: ratioWarnings.value,
        rows: rows.value,
        g74Investees: investeeOptions.value.map(o => ({ id: o.id, name: o.name })),
      },
    })
    const text = extractG7AiText(response?.data)
    if (text) {
      conclusion.value = text
      saveAuditConclusion(text)
      ElMessage.success('AI结论已生成')
    } else {
      ElMessage.warning('AI辅助暂未连接，请手动填写')
    }
  } catch {
    ElMessage.warning('AI辅助暂未连接，请手动填写')
  } finally {
    aiLoading.value = false
  }
}

function handleImportExportCommand(command: string): void {
  if (command === 'template') void importExport.exportTemplate('G7-11')
  else if (command === 'export') void importExport.exportData('G7-11')
  else if (command === 'import') fileInputRef.value?.click()
}

async function handleFileChange(ev: Event): Promise<void> {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  try {
    await importExport.importData('G7-11', file)
    await formData.load()
    const saved = formData.data.value.get(DATA_KEY)
    const loaded = hydrateDisposalSingleRows(parseJson(saved?.conclusion as string | undefined))
    if (loaded.length) {
      rows.value = loaded
      ElMessage.success(`导入完成，已刷新 ${loaded.length} 行`)
    } else {
      ElMessage.success('导入完成，请核对数据')
    }
  } catch {
    ElMessage.error('导入失败')
  }
}

onMounted(async () => {
  await formData.load()
  await loadG74Investees(false)
  const saved = formData.data.value.get(DATA_KEY)
  let loaded = hydrateDisposalSingleRows(parseJson(saved?.conclusion as string | undefined))
  if (!loaded.length) {
    const snapshot = props.htmlData?.responses_snapshot?.[DATA_KEY]
    loaded = hydrateDisposalSingleRows(parseJson(snapshot?.conclusion))
  }
  if (!loaded.length) {
    loaded = hydrateDisposalSingleRows(props.htmlData?.disposalSingle)
  }
  rows.value = loaded.length ? loaded : [createEmptyDisposalSingleRow(1)]
  if (loaded.length && !saved?.conclusion) saveRows()
  auditNote.value = formData.data.value.get(NOTE_KEY)?.remark
    || props.htmlData?.responses_snapshot?.[NOTE_KEY]?.remark
    || ''
  conclusion.value = formData.data.value.get(CONCLUSION_KEY)?.remark
    || props.htmlData?.responses_snapshot?.[CONCLUSION_KEY]?.remark
    || ''
  loading.value = false
})
</script>

<style scoped>
.g7-tab-disposal-single { padding: 12px; font-size: var(--wp-font-size, 13px); }
.hidden-input { display: none; }
.section-head, .conclusion-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.sheet-title { margin: 0; font-size: 16px; font-weight: 600; }
.sheet-subtitle { margin-top: 4px; color: #909399; font-size: 12px; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.audit-objective, .validation-alert { margin: 12px 0; }
.investee-tag { margin-bottom: 8px; }
.formula-cell { border-bottom: 1px dashed #909399; color: #303133; cursor: help; font-variant-numeric: tabular-nums; }
.consol-gain-cell { display: flex; flex-direction: column; align-items: flex-end; gap: 2px; }
.conclusion-card, .audit-note-card { margin-top: 16px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #606266; }
.prep-hint summary { cursor: pointer; font-weight: 500; color: #409eff; }
.prep-hint ul { margin: 4px 0 0 16px; line-height: 1.8; }
:deep(.el-table .cell) { line-height: 1.35; }
:deep(.el-date-editor.el-input) { width: 130px; }
</style>
