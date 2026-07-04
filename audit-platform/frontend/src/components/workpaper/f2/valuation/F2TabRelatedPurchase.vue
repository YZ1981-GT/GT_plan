<template>
  <div class="f2-related-purchase">
    <h3 class="title">关联采购公允性分析 F2-52</h3>
    <div class="summary">
      <el-tag size="small">采购合计: {{ rp.totalAmount.value.toLocaleString() }}</el-tag>
      <el-tag v-if="rp.highDeviationCount.value > 0" size="small" type="danger">
        偏差&gt;10%: {{ rp.highDeviationCount.value }} 笔
      </el-tag>
    </div>
    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="rp.addRow()">+ 新增行</el-button>
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
      <el-table-column label="偏差%" width="80" align="right">
        <template #default="{ row }">
          <span v-if="typeof row.deviation === 'number'">{{ row.deviation.toFixed(1) }}%</span>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column label="数量" width="80">
        <template #default="{ row }">
          <el-input-number :model-value="row.quantity" size="small" :controls="false" :disabled="isReadonly"
            @change="(v: number) => rp.updateRow(row.rowId, { quantity: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="金额" width="100" align="right">
        <template #default="{ row }"><span class="formula">{{ row.amount.toLocaleString() }}</span></template>
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
    <h4>审计说明</h4>
    <el-input v-model="rp.auditNote.value" type="textarea" :rows="3" :disabled="isReadonly" />
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useF2RelatedPurchase } from '../../composables/useF2RelatedPurchase'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
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
.title { margin: 0 0 8px; }
.summary { margin-bottom: 8px; display: flex; gap: 8px; flex-wrap: wrap; }
.toolbar { margin-bottom: 8px; }
.formula { text-decoration: underline dotted #909399; }
:deep(.error-row) { background: #fef0f0; }
h4 { margin: 16px 0 8px; font-size: 13px; }
</style>
