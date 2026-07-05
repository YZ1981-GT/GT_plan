<template>
  <div class="g11-return-rate">
    <div class="methodology-panel">
      <strong>收益率分析方法</strong>
      <p>平均投资余额 = (期初投资余额 + 期末投资余额) / 2</p>
      <p>投资收益率 = 本期投资收益 / 平均投资余额 × 100%</p>
      <p>收益率变动超过 5 个百分点视为异常波动，需追查原因。</p>
    </div>
    <div class="section-head">
      <h3 class="sheet-title">G11-4 投资收益分析 — 投资收益率</h3>
      <div class="head-actions">
        <G11ImportExportDropdown :wp-id="wpId" sheet="G11-4" @imported="onImported" />
        <GtReviewTrigger section-id="G11-4-return-rate" />
        <el-button size="small" :loading="rr.aiLoading.value" :disabled="isReadonly" @click="rr.generateAiConclusion()">🤖 AI</el-button>
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="rr.addRow()">+ 新增</el-button>
      </div>
    </div>
    <el-alert v-if="rr.abnormalCount.value > 0" type="warning" :closable="false">
      {{ rr.abnormalCount.value }} 个项目收益率异常波动（|变动|&gt;5pp）
    </el-alert>
    <el-table :data="rr.rows.value" border size="small" style="font-size:13px" max-height="520" data-testid="g11-return-rate-table"
      :row-class-name="({ row }) => row.abnormalHighlight ? 'abnormal-row' : ''">
      <el-table-column label="项目名称" prop="itemName" min-width="160" fixed />
      <el-table-column label="本期数" align="center">
        <el-table-column label="发生额" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.currentIncome" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => rr.updateRow(row.id, { currentIncome: v ?? 0 })" />
            <span v-else>{{ fmt(row.currentIncome) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.currentOpening" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => rr.updateBalance(row.id, 'currentOpening', v ?? 0)" />
            <span v-else>{{ fmt(row.currentOpening) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.currentClosing" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => rr.updateBalance(row.id, 'currentClosing', v ?? 0)" />
            <span v-else>{{ fmt(row.currentClosing) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="平均投资" width="96" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="(期初+期末)/2">{{ fmt(row.currentAvgBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="收益率" width="80" align="right">
          <template #default="{ row }">
            <el-tooltip v-if="row.currentReturnRate === null" content="平均余额为零，无法计算收益率">
              <span>N/A</span>
            </el-tooltip>
            <span v-else class="formula-cell">{{ fmtPct(row.currentReturnRate) }}</span>
          </template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="上期数" align="center">
        <el-table-column label="审定数" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.priorAudited" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => rr.updateRow(row.id, { priorAudited: v ?? 0 })" />
            <span v-else>{{ fmt(row.priorAudited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.priorOpening" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => rr.updateBalance(row.id, 'priorOpening', v ?? 0)" />
            <span v-else>{{ fmt(row.priorOpening) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.priorClosing" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => rr.updateBalance(row.id, 'priorClosing', v ?? 0)" />
            <span v-else>{{ fmt(row.priorClosing) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="平均投资" width="96" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.priorAvgBalance) }}</span></template>
        </el-table-column>
        <el-table-column label="收益率" width="80" align="right">
          <template #default="{ row }">{{ row.priorReturnRate === null ? 'N/A' : fmtPct(row.priorReturnRate) }}</template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="收益率变动" width="88" align="right">
        <template #default="{ row }">
          <el-tooltip v-if="row.abnormalHighlight" content="收益率异常波动">
            <span class="rate-warn">{{ row.returnRateChange === null ? 'N/A' : fmtPctPoint(row.returnRateChange) }}</span>
          </el-tooltip>
          <span v-else>{{ row.returnRateChange === null ? 'N/A' : fmtPctPoint(row.returnRateChange) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="异常说明" min-width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.abnormalNote" type="textarea" :autosize="{ minRows: 1, maxRows: 2 }" size="small"
            @update:model-value="(v: string) => rr.updateRow(row.id, { abnormalNote: v })" />
          <span v-else>{{ row.abnormalNote }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="56" v-if="!isReadonly" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="rr.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-card shadow="never" class="conclusion-card">
      <template #header>审计结论</template>
      <el-input :model-value="rr.conclusion.value" type="textarea" :autosize="{ minRows: 3, maxRows: 6 }"
        :disabled="isReadonly" @update:model-value="rr.updateConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useG11ReturnRateAnalysis } from '../../composables/useG11ReturnRateAnalysis'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import G11ImportExportDropdown from '../G11ImportExportDropdown.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const rr = useG11ReturnRateAnalysis({
  wpId: toRef(props, 'wpId'),
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

async function onImported() {
  emit('imported')
  rr.reloadFromStore()
}

function fmt(v: number) { return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
function fmtPct(r: number) { return (r * 100).toFixed(2) + '%' }
function fmtPctPoint(r: number) { return (r * 100).toFixed(2) + 'pp' }
</script>

<style scoped>
.g11-return-rate { font-size: 13px; }
.methodology-panel { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 10px 12px; margin-bottom: 10px; font-size: 12px; }
.methodology-panel p { margin: 4px 0; }
.section-head { display: flex; justify-content: space-between; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.formula-cell { border-bottom: 1px dashed #999; cursor: help; }
.rate-warn { color: #e6a23c; font-weight: 600; }
.conclusion-card { margin-top: 8px; }
:deep(.abnormal-row) { background-color: #fdf6ec !important; }
</style>
