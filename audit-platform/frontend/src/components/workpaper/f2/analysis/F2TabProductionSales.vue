<script setup lang="ts">
/** F2TabProductionSales — F2-19 产销量变动 | Task 17.3 */
import { inject, toRef, type Ref } from 'vue'
import { useF2ProductionSales } from '../../composables/useF2Analysis'
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

const { activeSegment, enrichedRows, useVirtualScroll, conclusion, addRow, removeRow, updateCell } = useF2ProductionSales({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2AiGenerate(toRef(props, 'wpId') as Ref<string>)

async function generatePsConclusion() {
  const lowRateCount = enrichedRows.value.filter((r) => r.isLowSalesRate).length
  const unbalanced = enrichedRows.value.filter((r) => !r.stockBalanced).length
  const text = await generateAndConfirm(
    'production-sales-conclusion',
    conclusion.value,
    { productCount: enrichedRows.value.length, lowRateCount, unbalancedCount: unbalanced },
    'AI 生成 · 产销量分析结论',
  )
  if (text) conclusion.value = text
}

const segmentOptions = [
  { label: '产量变动', value: 'production' },
  { label: '销量变动', value: 'sales' },
  { label: '库存变动', value: 'inventory' },
]
</script>

<template>
  <div class="f2-production-sales">
    <details class="guidance-details"><summary>📋 编制提示</summary><p>三区段对比：产量/销量/库存变动；产销率＜80%橙色标记滞销风险；库存平衡=期初+入库-出库=期末。</p></details>
    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 新增产品</el-button>
      <CycleImportExportDropdown
        :wp-id="wpId"
        api-prefix="f2"
        sheet="F2-19"
        :disabled="isReadonly"
        @imported="onImported"
      />
    </div>
    <el-segmented v-model="activeSegment" :options="segmentOptions" size="small" class="segment-bar" />

    <el-alert v-if="useVirtualScroll" type="info" :closable="false" class="virtual-hint">
      行数较多（{{ enrichedRows.length }} 行），已启用虚拟滚动优化
    </el-alert>

    <el-table :data="enrichedRows" border size="small" :max-height="useVirtualScroll ? 560 : 480">
      <el-table-column label="产品名称" width="140" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.productName" size="small" @change="(v: string) => updateCell(row.rowId, 'productName', v)" />
          <span v-else>{{ row.productName }}</span>
        </template>
      </el-table-column>

      <template v-if="activeSegment === 'production'">
        <el-table-column label="本期产量" width="110">
          <template #default="{ row }">
            <el-input-number :model-value="row.currentProduction" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => updateCell(row.rowId, 'currentProduction', v ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="上期产量" width="110">
          <template #default="{ row }">
            <el-input-number :model-value="row.priorProduction" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => updateCell(row.rowId, 'priorProduction', v ?? 0)" />
          </template>
        </el-table-column>
      </template>

      <template v-else-if="activeSegment === 'sales'">
        <el-table-column label="本期销量" width="110">
          <template #default="{ row }">
            <el-input-number :model-value="row.currentSales" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => updateCell(row.rowId, 'currentSales', v ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="上期销量" width="110">
          <template #default="{ row }">
            <el-input-number :model-value="row.priorSales" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => updateCell(row.rowId, 'priorSales', v ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="产销率" width="90">
          <template #default="{ row }">
            <span :class="{ 'low-rate': row.isLowSalesRate }">{{ row.productionRate.toFixed(1) }}%</span>
          </template>
        </el-table-column>
      </template>

      <template v-else>
        <el-table-column label="期初库存" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.openingStock" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => updateCell(row.rowId, 'openingStock', v ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="入库" width="90">
          <template #default="{ row }">
            <el-input-number :model-value="row.inbound" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => updateCell(row.rowId, 'inbound', v ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="出库" width="90">
          <template #default="{ row }">
            <el-input-number :model-value="row.outbound" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => updateCell(row.rowId, 'outbound', v ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="期末库存" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.closingStock" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => updateCell(row.rowId, 'closingStock', v ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="平衡" width="70">
          <template #default="{ row }">
            <span :class="{ 'stock-error': !row.stockBalanced }">{{ row.stockBalanced ? '✓' : '✗' }}</span>
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
          <F2ReviewChip section-id="F2-19-conclusion" />
          <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="generatePsConclusion">AI 生成</el-button>
        </div>
      </div>
      <el-input v-model="conclusion" type="textarea" :rows="3" :disabled="isReadonly" />
    </div>
  </div>
</template>

<style scoped>
.f2-production-sales { padding: 12px; font-size: 13px; }
.toolbar { margin-bottom: 8px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.segment-bar { margin-bottom: 12px; }
.virtual-hint { margin-bottom: 8px; }
.low-rate { color: #e6a23c; font-weight: 600; }
.stock-error { color: #f56c6c; font-weight: 600; }
.conclusion h4 { margin: 0; font-size: 13px; }
.conclusion-header { display: flex; justify-content: space-between; align-items: center; margin: 16px 0 8px; }
.header-actions { display: flex; gap: 8px; align-items: center; }
.guidance-details { margin-bottom: 8px; font-size: 12px; color: #606266; }
</style>
