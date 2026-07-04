<template>
  <div class="f2-cutoff-sheet">
    <h3 class="sheet-title">{{ config.title }} {{ config.sheetCode }}</h3>
    <details class="guidance-details"><summary>📋 编制提示</summary><p>正向测试：期末后N天单据→检查是否已入账；反向测试：期末前N天入账→检查是否有单据。截止不正确行红色高亮。</p></details>
    <div class="meta">
      <el-tag size="small">{{ config.direction === 'inbound' ? '入库' : '出库' }}</el-tag>
      <el-tag size="small" type="info">{{ config.testType === 'forward' ? '正向测试' : '反向测试' }}</el-tag>
      <el-button size="small" type="primary" :disabled="isReadonly" @click="cutoff.addRow()">新增行</el-button>
      <CycleImportExportDropdown
        v-if="wpId"
        :wp-id="wpId"
        api-prefix="f2"
        :sheet="config.sheetCode"
        :disabled="isReadonly"
        @imported="onImported"
      />
      <el-tag size="small">共 {{ cutoff.cutoffSummary.total }} 笔</el-tag>
      <el-tag v-if="cutoff.cutoffSummary.errorCount > 0" size="small" type="danger">
        错误 {{ cutoff.cutoffSummary.errorCount }} 笔 / {{ cutoff.cutoffSummary.errorAmount.toLocaleString() }} 元
      </el-tag>
    </div>

    <div v-if="!isReadonly && wpId && projectId" class="auto-extract">
      <el-collapse>
        <el-collapse-item title="⚡ 自动提取凭证" name="auto-extract">
          <GtCutoffAutoSampling
            :account-code="F2_INVENTORY_ACCOUNT_CODES"
            :cutoff-direction="samplingParams.cutoffDirection"
            :workpaper-id="wpId"
            :project-id="projectId"
            :year="year"
            :default-conditions="{ directionFilter: samplingParams.directionFilter, daysBefore: 5, daysAfter: 5 }"
            @filled="handleAutoExtractFilled"
          />
        </el-collapse-item>
      </el-collapse>
    </div>

    <el-table
      :data="cutoff.rows"
      border
      size="small"
      max-height="480"
      :row-class-name="({ row }) => !row.isCorrect ? 'error-row' : ''"
    >
      <el-table-column prop="seq" label="序号" width="55" />
      <el-table-column :label="config.direction === 'inbound' ? '供应商' : '领用部门'" width="120">
        <template #default="{ row }">
          <el-input v-model="row.party" size="small" :disabled="isReadonly" @change="cutoff.updateRow(row.id, { party: row.party })" />
        </template>
      </el-table-column>
      <el-table-column :label="config.direction === 'inbound' ? '入库单号' : '出库单号'" width="110">
        <template #default="{ row }">
          <el-input v-model="row.docNo" size="small" :disabled="isReadonly" @change="cutoff.updateRow(row.id, { docNo: row.docNo })" />
        </template>
      </el-table-column>
      <el-table-column label="单据日期" width="120">
        <template #default="{ row }">
          <el-date-picker v-model="row.docDate" type="date" size="small" value-format="YYYY-MM-DD" :disabled="isReadonly" @change="cutoff.updateRow(row.id, { docDate: row.docDate })" />
        </template>
      </el-table-column>
      <el-table-column label="品名" width="120">
        <template #default="{ row }">
          <el-input v-model="row.itemName" size="small" :disabled="isReadonly" @change="cutoff.updateRow(row.id, { itemName: row.itemName })" />
        </template>
      </el-table-column>
      <el-table-column label="数量" width="90">
        <template #default="{ row }">
          <el-input-number v-model="row.quantity" size="small" :controls="false" :disabled="isReadonly" @change="cutoff.updateRow(row.id, { quantity: row.quantity })" />
        </template>
      </el-table-column>
      <el-table-column label="金额" width="100">
        <template #default="{ row }">
          <el-input-number v-model="row.amount" size="small" :controls="false" :disabled="isReadonly" @change="cutoff.updateRow(row.id, { amount: row.amount })" />
        </template>
      </el-table-column>
      <el-table-column label="凭证号" width="100">
        <template #default="{ row }">
          <el-tooltip v-if="row.source === '自动提取'" content="来自自动提取" placement="top">
            <el-input v-model="row.voucherNo" size="small" :disabled="isReadonly" @change="cutoff.updateRow(row.id, { voucherNo: row.voucherNo })" />
          </el-tooltip>
          <el-input v-else v-model="row.voucherNo" size="small" :disabled="isReadonly" @change="cutoff.updateRow(row.id, { voucherNo: row.voucherNo })" />
        </template>
      </el-table-column>
      <el-table-column label="记账日期" width="120">
        <template #default="{ row }">
          <el-date-picker v-model="row.bookDate" type="date" size="small" value-format="YYYY-MM-DD" :disabled="isReadonly" @change="cutoff.updateRow(row.id, { bookDate: row.bookDate })" />
        </template>
      </el-table-column>
      <el-table-column label="截止正确" width="110">
        <template #default="{ row }">
          <el-tooltip
            :content="row.isCorrectOverride !== null
              ? `公式判定: ${row.autoCorrect ? '正确' : '不正确'} → 已手动覆盖`
              : `公式自动判定（基于单据日期/记账日期 vs 期末）`"
            placement="top"
          >
            <el-switch
              v-model="row.isCorrect"
              :disabled="isReadonly"
              active-text="✓"
              inactive-text="✗"
              :style="row.isCorrectOverride !== null ? 'opacity: 0.8' : ''"
              @change="(val: boolean) => cutoff.updateRow(row.id, { isCorrectOverride: val !== row.autoCorrect ? val : null })"
            />
          </el-tooltip>
          <el-tag v-if="row.isCorrectOverride !== null" size="small" type="warning" style="margin-left: 4px; font-size: 10px;">覆盖</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="100">
        <template #default="{ row }">
          <el-input v-model="row.remark" size="small" :disabled="isReadonly" @change="cutoff.updateRow(row.id, { remark: row.remark })" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" size="small" type="danger" link @click="cutoff.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="summary-footer">
      正确 {{ cutoff.cutoffSummary.correctCount }} 笔 /
      错误 {{ cutoff.cutoffSummary.errorCount }} 笔 /
      涉及金额 {{ cutoff.cutoffSummary.errorAmount.toLocaleString() }} 元
    </div>

    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="conclusion-header">
          <span class="conclusion-title">截止测试结论</span>
          <div class="header-actions">
            <F2ReviewChip :section-id="`${config.sheetCode}-conclusion`" />
            <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="generateCutoffConclusion">AI 生成</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="cutoff.cutoffConclusion" type="textarea" :rows="3" :disabled="isReadonly" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, toRef, type Ref } from 'vue'
import { useF2CutoffSheet } from '../../composables/useF2CutoffSheet'
import { useF2AiGenerate } from '../../composables/useF2AiGenerate'
import {
  F2_INVENTORY_ACCOUNT_CODES,
  getF2CutoffSamplingParams,
  type F2CutoffSheetConfig,
} from './f2CutoffSheetConfigs'
import type { ChecklistResponse } from '../../composables/useF2FormData'
import type { ExtractedVoucher, FillMode } from '../../composables/useCutoffAutoSampling'
import GtCutoffAutoSampling from '../../cutoff/GtCutoffAutoSampling.vue'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'
import F2ReviewChip from '../shared/F2ReviewChip.vue'

const props = defineProps<{
  config: F2CutoffSheetConfig
  wpId?: string
  projectId?: string
  bsDate?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
async function onImported() { await reloadWorkpaperData?.() }

const configRef = computed(() => props.config)
const samplingParams = computed(() => getF2CutoffSamplingParams(props.config))

const year = computed(() => {
  const d = props.bsDate || ''
  if (d.length >= 4) return parseInt(d.slice(0, 4), 10)
  return new Date().getFullYear() - 1
})

const cutoff = useF2CutoffSheet({
  config: configRef,
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  periodEnd: computed(() => props.bsDate || ''),
})

function handleAutoExtractFilled(payload: { samples: ExtractedVoucher[]; fillMode: FillMode }) {
  cutoff.fillFromExtracted(payload.samples, payload.fillMode)
}

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2AiGenerate(
  toRef(() => props.wpId || '') as Ref<string>,
)

async function generateCutoffConclusion() {
  const text = await generateAndConfirm(
    'cutoff-conclusion',
    cutoff.cutoffConclusion.value,
    {
      sheet: props.config.sheetCode,
      total: cutoff.cutoffSummary.value.total,
      errorCount: cutoff.cutoffSummary.value.errorCount,
      errorAmount: cutoff.cutoffSummary.value.errorAmount,
    },
    `AI 生成 · ${props.config.title}结论`,
  )
  if (text) cutoff.cutoffConclusion.value = text
}
</script>

<style scoped>
.f2-cutoff-sheet { padding: 12px; font-size: 13px; }
.sheet-title { margin: 0 0 8px; }
.meta { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
.auto-extract { margin-bottom: 12px; }
.summary-footer { margin-top: 12px; font-size: 12px; color: #606266; }
.conclusion-card { margin-top: 16px; }
.conclusion-header { display: flex; justify-content: space-between; align-items: center; }
.conclusion-title { font-weight: 600; font-size: 13px; }
.header-actions { display: flex; gap: 8px; align-items: center; }
.guidance-details { margin-bottom: 8px; font-size: 12px; color: #606266; }
:deep(.error-row) { background: #fef0f0; }
</style>
