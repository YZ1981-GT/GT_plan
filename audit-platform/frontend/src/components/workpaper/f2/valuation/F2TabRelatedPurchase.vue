<template>
  <div class="f2-related-purchase">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表分析向关联方采购的价格公允性，逐笔录入关联方、品名、关联价、可比价、数量。</p>
        <p>2. 金额为自动计算列（关联价 × 数量），偏差率＝(关联价−可比价)/可比价，偏差 ＞ 10% 的行自动标红。</p>
        <p>3. 可比价应取市场公允价或非关联方同类交易价，缺乏可比价时须说明定价依据。</p>
        <p>4. 依《企业会计准则第 36 号——关联方披露》，关注关联采购是否以公允价格进行、是否需披露。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：评价向关联方采购定价的公允性，识别显著偏离市场价的关联交易，确认关联采购披露充分。"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="rp.addRow()">+ 新增行</el-button>
        <el-tag size="small">采购合计: {{ rp.totalAmount.value.toLocaleString() }}</el-tag>
        <el-tag v-if="rp.highDeviationCount.value > 0" size="small" type="danger">
          偏差&gt;10%: {{ rp.highDeviationCount.value }} 笔
        </el-tag>
      </div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-val"
          sheet="F2-52"
          :disabled="isReadonly"
          ai-section="fairness-evaluation"
          :existing-content="rp.auditNote.value"
          :related-context="{ highDeviationCount: rp.highDeviationCount.value }"
          ai-title="AI 生成 · 关联采购公允性评价"
          review-section="F2-52-conclusion"
          @ai-filled="(t: string) => { rp.auditNote.value = t }"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:F2-1" /></span>
        <el-tag size="small" type="info">共 {{ rp.enrichedRows.value.length }} 行</el-tag>
      </div>
    </div>
    <el-table :data="rp.enrichedRows.value" border size="small" max-height="480"
      :row-class-name="({ row }) => row.isHighDeviation ? 'error-row' : ''">
      <el-table-column label="关联方" width="120" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.relatedParty" size="small"
            @change="(v: string) => rp.updateRow(row.rowId, { relatedParty: v })" />
          <span v-else>{{ row.relatedParty }}</span>
        </template>
      </el-table-column>
      <el-table-column label="品名" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.itemName" size="small"
            @change="(v: string) => rp.updateRow(row.rowId, { itemName: v })" />
          <span v-else>{{ row.itemName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="关联价" width="90">
        <template #default="{ row }">
          <el-input-number :model-value="row.relatedPrice" size="small" :controls="false" :disabled="isReadonly"
            @change="(v: number) => rp.updateRow(row.rowId, { relatedPrice: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="可比价" width="90">
        <template #default="{ row }">
          <el-input-number :model-value="row.comparablePrice" size="small" :controls="false" :disabled="isReadonly"
            @change="(v: number) => rp.updateRow(row.rowId, { comparablePrice: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="偏差%" width="80" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <el-tooltip content="(关联价 − 可比价) / 可比价 × 100%" placement="top">
            <span v-if="typeof row.deviation === 'number'" class="formula">{{ row.deviation.toFixed(1) }}%</span>
            <span v-else>—</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="数量" width="80">
        <template #default="{ row }">
          <el-input-number :model-value="row.quantity" size="small" :controls="false" :disabled="isReadonly"
            @change="(v: number) => rp.updateRow(row.rowId, { quantity: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="金额" width="100" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <el-tooltip content="关联价 × 数量" placement="top">
            <span class="formula">{{ row.amount.toLocaleString() }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="公允性评价" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.fairnessEval" size="small"
            @change="(v: string) => rp.updateRow(row.rowId, { fairnessEval: v })" />
          <span v-else>{{ row.fairnessEval }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="55">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="rp.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
    <!-- 审计意见区（卡片式） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header"><span class="opinion-title">审计说明</span></div>
      </template>
      <el-input v-model="rp.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly" placeholder="请输入关联采购公允性评价说明..." />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useF2RelatedPurchase } from '../../composables/useF2RelatedPurchase'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
import GtIndexChip from '../../GtIndexChip.vue'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const rp = useF2RelatedPurchase({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})
</script>

<style scoped>
.f2-related-purchase { padding: 12px; font-size: 13px; }
.f2-related-purchase :deep(.el-table) { --el-table-font-size: 13px; font-size: 13px; }
.f2-related-purchase :deep(.el-table .cell) { font-size: 13px !important; }
/* 编制提示（蓝色） */
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
/* 工具栏 */
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
/* 计算列灰底 + 公式虚线 */
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.formula { text-decoration: underline dotted #909399; cursor: help; }
:deep(.error-row) { background: #fef0f0; }
/* 审计意见卡片 */
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
</style>
