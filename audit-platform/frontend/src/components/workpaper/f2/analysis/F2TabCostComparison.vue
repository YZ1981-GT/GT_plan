<script setup lang="ts">
/** F2TabCostComparison — F2-20 成本比较 | Task 17.4 */
import { inject, toRef, type Ref } from 'vue'
import { useF2CostComparison } from '../../composables/useF2Analysis'
import { useF2AiGenerate } from '../../composables/useF2AiGenerate'
import type { ChecklistResponse } from '../../composables/useF2FormData'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'
import F2ReviewChip from '../shared/F2ReviewChip.vue'

const props = defineProps<{
  wpId: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
async function onImported() { await reloadWorkpaperData?.() }

function fmtRate(r: number | '' | 'N/A'): string {
  if (r === '' || r === 'N/A') return String(r)
  return `${(r * 100).toFixed(1)}%`
}

const { activeSegment, enrichedRows, anomalyCount, conclusion, addRow, removeRow, updateCell } = useF2CostComparison({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2AiGenerate(toRef(props, 'wpId') as Ref<string>)

async function generateCostConclusion() {
  const text = await generateAndConfirm(
    'cost-comparison-conclusion',
    conclusion.value,
    { productCount: enrichedRows.value.length, anomalyCount: anomalyCount.value },
    'AI 生成 · 成本比较结论',
  )
  if (text) conclusion.value = text
}

const segmentOptions = [
  { label: '本期成本', value: 'current' },
  { label: '变动分析', value: 'variance' },
]
</script>

<template>
  <div class="f2-cost-comparison">
    <details class="guidance-details"><summary>📋 编制提示</summary><p>按产品比较本期/上期单位成本(材料+人工+制造费用)；变动率＞20%红色标记需填异常说明。</p></details>
    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 新增产品</el-button>
      <el-tag v-if="anomalyCount > 0" type="danger" size="small">{{ anomalyCount }} 项成本异常</el-tag>
      <CycleImportExportDropdown
        :wp-id="wpId"
        api-prefix="f2"
        sheet="F2-20"
        :disabled="isReadonly"
        @imported="onImported"
      />
    </div>
    <el-segmented v-model="activeSegment" :options="segmentOptions" size="small" class="segment-bar" />

    <el-table :data="enrichedRows" border size="small" max-height="480">
      <el-table-column label="产品名称" width="140" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.productName" size="small" @change="(v: string) => updateCell(row.rowId, 'productName', v)" />
          <span v-else>{{ row.productName }}</span>
        </template>
      </el-table-column>

      <template v-if="activeSegment === 'current'">
        <el-table-column label="产量" width="90">
          <template #default="{ row }">
            <el-input-number :model-value="row.currentQty" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => updateCell(row.rowId, 'currentQty', v ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="材料" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.currentMaterial" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => updateCell(row.rowId, 'currentMaterial', v ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="人工" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.currentLabor" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => updateCell(row.rowId, 'currentLabor', v ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="制造费用" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.currentOverhead" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => updateCell(row.rowId, 'currentOverhead', v ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="合计" width="100" align="right">
          <template #default="{ row }">{{ row.currentTotal.toLocaleString() }}</template>
        </el-table-column>
      </template>

      <template v-else>
        <el-table-column label="上期合计" width="110" align="right">
          <template #default="{ row }">{{ row.priorTotal.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="变动额" width="110" align="right">
          <template #default="{ row }">{{ row.variance.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="变动率" width="90">
          <template #default="{ row }">
            <span :class="{ anomaly: row.isAnomaly }">{{ fmtRate(row.varianceRate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="异常说明" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.anomalyNote" size="small"
              :class="{ anomaly: row.isAnomaly }"
              @change="(v: string) => updateCell(row.rowId, 'anomalyNote', v)" />
            <span v-else>{{ row.anomalyNote }}</span>
          </template>
        </el-table-column>
      </template>

      <el-table-column label="操作" width="55" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="conclusion">
      <div class="conclusion-header">
        <h4>分析结论</h4>
        <div class="header-actions">
          <F2ReviewChip section-id="F2-20-conclusion" />
          <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="generateCostConclusion">AI 生成</el-button>
        </div>
      </div>
      <el-input v-model="conclusion" type="textarea" :rows="3" :disabled="isReadonly" />
    </div>
  </div>
</template>

<style scoped>
.f2-cost-comparison { padding: 12px; font-size: 13px; }
.toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.segment-bar { margin-bottom: 12px; }
.anomaly { color: #f56c6c; font-weight: 600; }
.conclusion h4 { margin: 0; font-size: 13px; }
.conclusion-header { display: flex; justify-content: space-between; align-items: center; margin: 16px 0 8px; }
.header-actions { display: flex; gap: 8px; align-items: center; }
.guidance-details { margin-bottom: 8px; font-size: 12px; color: #606266; }
</style>
