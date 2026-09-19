<template>
<div class="d3-analysis">
  <!-- 审计目标 -->
  <el-alert type="info" :closable="false" show-icon class="audit-objective">
    <template #title>
      <strong>审计目标</strong>：通过借贷方发生额分析与 Top5 预收客户集中度分析，识别预收账款的异常波动、大额集中与舞弊风险，为实质性程序提供方向（CAS 1231 分析程序）。
    </template>
  </el-alert>

  <!-- 集中度警告 -->
  <el-alert
    v-if="top5ConcentrationWarning"
    type="warning"
    :title="top5ConcentrationWarning"
    :closable="false"
    show-icon
    style="margin-bottom: 12px"
  />

  <!-- 区块一：借方发生额分析 -->
  <div class="analysis-card">
    <div class="card-header-row">
      <h4 class="card-title">(一) 借方发生额分析</h4>
      <el-button-group size="small">
        <el-button @click="onExportDebitTemplate">借方模板</el-button>
        <el-button @click="onExportDebitData">借方导出</el-button>
        <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportDebitFile">
          <el-button :disabled="isReadonly">借方导入</el-button>
        </el-upload>
      </el-button-group>
    </div>
    <el-table :data="debitTableData" size="small" border stripe>
      <el-table-column prop="label" label="项目" width="180" />
      <el-table-column label="金额" width="130" align="right">
        <template #default="{ row }">
          <span :class="{ 'diff-red': row.rowKey === 'debit-diff' && row.amount !== 0 }">
            {{ fmtAmount(row.amount) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="source" label="来源" width="140" />
      <el-table-column prop="remark" label="备注" min-width="120" />
    </el-table>
  </div>

  <!-- 区块二：贷方发生额分析 -->
  <div class="analysis-card">
    <div class="card-header-row">
      <h4 class="card-title">(二) 贷方发生额分析</h4>
      <el-button-group size="small">
        <el-button @click="onExportCreditTemplate">贷方模板</el-button>
        <el-button @click="onExportCreditData">贷方导出</el-button>
        <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportCreditFile">
          <el-button :disabled="isReadonly">贷方导入</el-button>
        </el-upload>
      </el-button-group>
    </div>
    <el-table :data="creditTableData" size="small" border stripe>
      <el-table-column prop="label" label="项目" width="180" />
      <el-table-column label="金额" width="130" align="right">
        <template #default="{ row }">
          <span :class="{ 'diff-red': row.rowKey === 'credit-diff' && row.amount !== 0 }">
            {{ fmtAmount(row.amount) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="source" label="来源" width="140" />
      <el-table-column prop="remark" label="备注" min-width="120" />
    </el-table>
  </div>

  <!-- 区块三：Top5预收客户 -->
  <div class="analysis-card">
    <h4 class="card-title">(三) 期末主要预收客户分析</h4>
    <el-table :data="top5Debtors" size="small" border stripe>
      <el-table-column type="index" label="序号" width="50" />
      <el-table-column prop="customerName" label="预收客户名称" width="160">
        <template #default="{ row }">
          <span>{{ row.customerName }}</span>
          <GtIndexChip target="D3-2" :label="row.customerName" />
        </template>
      </el-table-column>
      <el-table-column label="期末余额" width="120" align="right">
        <template #default="{ row }">{{ fmtAmount(row.endAudited) }}</template>
      </el-table-column>
      <el-table-column label="期初余额" width="120" align="right">
        <template #default="{ row }">{{ fmtAmount(row.priorAudited) }}</template>
      </el-table-column>
      <el-table-column label="变动金额" width="120" align="right">
        <template #default="{ row }">{{ fmtAmount(row.changeAmount) }}</template>
      </el-table-column>
      <el-table-column label="变动比例" width="90">
        <template #default="{ row }">
          <span :class="{ 'rate-exceed': isRateHigh(row.changeRate) }">
            {{ fmtRate(row.changeRate) }}
          </span>
        </template>
      </el-table-column>
    </el-table>
  </div>

  <!-- 区块四：审计说明 -->
  <div class="analysis-card">
    <h4 class="card-title section-header-row">
      三、审计说明
      <GtReviewTrigger section-id="D3-analysis-header" />
    </h4>
    <div class="note-block">
      <div class="note-label">
        分析性复核说明
        <el-button
          size="small"
          :disabled="isReadonly || !aiAvailable || aiLoading"
          :loading="aiLoading"
          @click="genAnalysisNote"
        >🤖AI</el-button>
      </div>
      <el-input
        v-model="auditNote"
        type="textarea"
        :rows="4"
        :disabled="isReadonly"
        placeholder="对预收账款借贷方发生额变动、Top5集中度等进行分析性复核说明..."
      />
    </div>

    <!-- 编制提示 -->
    <details class="guidance-fold">
      <summary>📋 编制提示（CAS 1231 分析程序）</summary>
      <p>1. 借/贷方发生额分析：与序时账发生额、收入确认（D4）勾稽，差额行标红须查明原因；</p>
      <p>2. Top5 预收客户集中度超阈值时，关注大额预收的商业实质与后续履约能力；</p>
      <p>3. 变动比例超 30% 的预收客户应结合合同与业务背景分析，异常波动纳入进一步检查范围。</p>
    </details>
  </div>
</div>
</template>

<script setup lang="ts">
/**
 * D3TabAnalysis.vue — D3-4 分析表
 * 4区块卡片：借方/贷方/Top5/审计说明
 */
import { computed, toRef, type Ref } from 'vue'
import { isChangeRateExceeding } from '../composables/useD3FormulaEngine'
import { useD3Analysis } from '../composables/useD3Analysis'
import { useD3AiGenerate } from '../composables/useD3AiGenerate'
import { useD3TabImportExport } from '../composables/useD3TabImportExport'
import type { useD3CrossSheet } from '../composables/useD3CrossSheet'
import type { ChecklistResponse } from '../composables/useD3FormData'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  crossSheet: ReturnType<typeof useD3CrossSheet>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

// 父级经模板传入的是解包后的普通值（非 ref），此处重新包成 ref 供 composable 使用
const allResponsesRef = toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>
const wpIdRef = toRef(props, 'wpId') as Ref<string>
const projectIdRef = toRef(props, 'projectId') as Ref<string>

const {
  sections,
  top5Debtors,
  top5ConcentrationWarning,
  auditNote,
  debitRows,
  creditRows,
} = useD3Analysis({
  allResponses: allResponsesRef,
  wpId: wpIdRef,
  projectId: projectIdRef,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  crossSheet: props.crossSheet,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})

const { generateAndConfirm, aiAvailable, loading: aiLoading } = useD3AiGenerate(wpIdRef)

const debitImportExport = useD3TabImportExport(wpIdRef, 'D3-4-debit')
const creditImportExport = useD3TabImportExport(wpIdRef, 'D3-4-credit')
const onExportDebitTemplate = debitImportExport.onExportTemplate
const onExportDebitData = debitImportExport.onExportData
const onImportDebitFile = debitImportExport.onImportFile
const onExportCreditTemplate = creditImportExport.onExportTemplate
const onExportCreditData = creditImportExport.onExportData
const onImportCreditFile = creditImportExport.onImportFile

async function genAnalysisNote() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('analysis-note', auditNote.value, {
    task: '预收账款分析性复核说明',
    top5Count: top5Debtors.value.length,
    top5ConcentrationWarning: top5ConcentrationWarning.value || '',
  }, 'AI · 分析性复核')
  if (text) auditNote.value = text
}

// Build table data for debit/credit including total + diff rows
const debitTableData = computed(() => {
  const sec = sections.value[0]
  if (!sec) return []
  return [...sec.rows, ...(sec.totalRow ? [sec.totalRow] : []), ...(sec.diffRow ? [sec.diffRow] : [])]
})

const creditTableData = computed(() => {
  const sec = sections.value[1]
  if (!sec) return []
  return [...sec.rows, ...(sec.totalRow ? [sec.totalRow] : []), ...(sec.diffRow ? [sec.diffRow] : [])]
})

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function fmtRate(rate: number | '' | 'N/A'): string {
  if (rate === '' || rate === 'N/A') return String(rate)
  return `${(rate * 100).toFixed(1)}%`
}

function isRateHigh(rate: number | '' | 'N/A'): boolean {
  return isChangeRateExceeding(rate, 0.3)
}
</script>

<style scoped>
.d3-analysis { padding: 16px; }
.audit-objective { margin-bottom: 12px; }
.guidance-fold { margin-top: 16px; font-size: 12px; color: #606266; background: #f9fafb; border: 1px solid #ebeef5; border-radius: 6px; padding: 8px 12px; }
.guidance-fold summary { cursor: pointer; font-weight: 600; color: #409eff; }
.guidance-fold p { margin: 6px 0 0; line-height: 1.6; }
.analysis-card { margin-bottom: 20px; padding: 16px; background: #fff; border: 1px solid #ebeef5; border-radius: 6px; }
.card-header-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.card-header-row .card-title { margin-bottom: 0; }
.card-title { font-size: 14px; font-weight: 600; margin-bottom: 12px; color: #303133; }
.section-header-row { display: flex; align-items: center; gap: 8px; }
.diff-red { color: #f56c6c; font-weight: 600; }
.rate-exceed { color: #f56c6c; font-weight: 600; }
.note-block { margin-top: 8px; }
.note-label { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
</style>
