<script setup lang="ts">
/** F2TabProductionSales — F2-19 产销量变动 | Task 17.3 */
import { inject, toRef, type Ref } from 'vue'
import { useF2ProductionSales } from '../../composables/useF2Analysis'
import { useF2AiGenerate } from '../../composables/useF2AiGenerate'
import type { ChecklistResponse } from '../../composables/useF2FormData'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'
import F2ReviewChip from '../shared/F2ReviewChip.vue'
import GtIndexChip from '../../GtIndexChip.vue'

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
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 三区段对比产量、销量、库存变动，可切换查看；产销率 = 销量 ÷ 产量。</p>
        <p>2. 产销率 ＜ 80% 橙色标记滞销风险；库存平衡校验：期初 + 入库 − 出库 = 期末，不平衡红色标记。</p>
        <p>3. 依《企业会计准则第 1 号——存货》，产销量异常与库存积压是存货跌价的重要信号。</p>
        <p>4. 结合量本关系分析产销匹配性，为可变现净值与跌价准备计提提供依据。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：验证产量、销量、库存变动的勾稽关系，识别滞销与积压风险。"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 新增产品</el-button>
      </div>
      <div class="toolbar-right">
        <CycleImportExportDropdown
          :wp-id="wpId"
          api-prefix="f2"
          sheet="F2-19"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:F2-2" /></span>
        <el-tag size="small" type="info">共 {{ enrichedRows.length }} 行</el-tag>
      </div>
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
        <el-table-column label="产销率" width="90" align="right" class-name="auto-calc-col">
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
        <el-table-column label="平衡" width="70" align="center" class-name="auto-calc-col">
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

    <!-- 审计意见区（卡片式） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">分析结论</span>
          <div class="opinion-actions">
            <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="generatePsConclusion">🤖 AI辅助</el-button>
            <F2ReviewChip section-id="F2-19-conclusion" />
          </div>
        </div>
      </template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly" placeholder="请输入产销量分析结论..." />
    </el-card>
  </div>
</template>

<style scoped>
.f2-production-sales { padding: 12px; font-size: 13px; }
.f2-production-sales :deep(.el-table) { --el-table-font-size: 13px; font-size: 13px; }
.f2-production-sales :deep(.el-table .cell) { font-size: 13px !important; }
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.segment-bar { margin-bottom: 12px; }
.virtual-hint { margin-bottom: 8px; }
.low-rate { color: #e6a23c; font-weight: 600; }
.stock-error { color: #f56c6c; font-weight: 600; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-actions { display: flex; gap: 6px; align-items: center; }
</style>
