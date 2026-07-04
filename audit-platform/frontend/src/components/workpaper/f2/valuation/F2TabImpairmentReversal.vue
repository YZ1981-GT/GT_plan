<template>
  <div class="f2-reversal">
    <h3 class="title">跌价转回 F2-49</h3>
    <div class="summary">
      <el-tag size="small" type="success">可转回笔数: {{ rev.summary.value.reverseCount }}</el-tag>
      <el-tag size="small" type="info">转回合计: {{ rev.summary.value.reverseTotal.toLocaleString() }}</el-tag>
      <el-tag v-if="rev.summary.value.missingRationale > 0" size="small" type="warning">
        {{ rev.summary.value.missingRationale }} 笔缺转回依据
      </el-tag>
    </div>
    <el-segmented v-model="rev.activeSegment.value" :options="segments" size="small" class="segment-bar" />
    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="rev.addRow()">+ 新增行</el-button>
      <F2SheetToolbar
        :wp-id="wpId"
        api-prefix="f2-val"
        sheet="F2-49"
        :disabled="isReadonly"
        ai-section="reversal-evaluation"
        :existing-content="rev.auditNote.value"
        :related-context="{ reverseCount: rev.summary.value.reverseCount }"
        ai-title="AI 生成 · 跌价转回评价"
        review-section="F2-49-conclusion"
        @ai-filled="(t: string) => { rev.auditNote.value = t }"
      />
    </div>
    <el-table :data="rev.enrichedRows.value" border size="small" max-height="480"
      :row-class-name="({ row }) => row.needsRationale ? 'warn-row' : ''">
      <el-table-column label="品名" width="120" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.itemName" size="small"
            @change="(v: string) => rev.updateRow(row.rowId, { itemName: v })" />
          <span v-else>{{ row.itemName }}</span>
        </template>
      </el-table-column>

      <template v-if="rev.activeSegment.value === 'prior'">
        <el-table-column label="账面成本" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.bookCost" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => rev.updateRow(row.rowId, { bookCost: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="已计提跌价" width="110">
          <template #default="{ row }">
            <el-input-number :model-value="row.priorProvision" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => rev.updateRow(row.rowId, { priorProvision: v ?? 0 })" />
          </template>
        </el-table-column>
      </template>

      <template v-else>
        <el-table-column label="售价" width="90">
          <template #default="{ row }">
            <el-input-number :model-value="row.sellingPrice" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => rev.updateRow(row.rowId, { sellingPrice: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="完工成本" width="90">
          <template #default="{ row }">
            <el-input-number :model-value="row.completionCost" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => rev.updateRow(row.rowId, { completionCost: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="销售费用" width="90">
          <template #default="{ row }">
            <el-input-number :model-value="row.sellingExpense" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => rev.updateRow(row.rowId, { sellingExpense: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="当前NRV" width="100" align="right">
          <template #default="{ row }"><span class="formula">{{ row.currentNrv.toLocaleString() }}</span></template>
        </el-table-column>
        <el-table-column label="现需计提" width="100" align="right">
          <template #default="{ row }"><span class="formula">{{ row.currentRequired.toLocaleString() }}</span></template>
        </el-table-column>
        <el-table-column label="转回金额" width="100" align="right">
          <template #default="{ row }">
            <span v-if="row.shouldReverse" class="formula reverse">{{ row.reversalAmount.toLocaleString() }}</span>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="转回依据" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.rationale" size="small"
              @change="(v: string) => rev.updateRow(row.rowId, { rationale: v })" />
            <span v-else>{{ row.rationale }}</span>
          </template>
        </el-table-column>
      </template>

      <el-table-column label="操作" width="55">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="rev.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
    <h4>审计说明</h4>
    <el-input v-model="rev.auditNote.value" type="textarea" :rows="3" :disabled="isReadonly" />
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useF2ImpairmentReversal } from '../../composables/useF2ImpairmentReversal'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const segments = [
  { label: '期初跌价', value: 'prior' },
  { label: '当前NRV/转回', value: 'current' },
]

const rev = useF2ImpairmentReversal({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})
</script>

<style scoped>
.f2-reversal { padding: 12px; font-size: 13px; }
.title { margin: 0 0 8px; }
.summary { margin-bottom: 8px; display: flex; gap: 8px; flex-wrap: wrap; }
.segment-bar { margin-bottom: 8px; }
.toolbar { margin-bottom: 8px; }
.formula { text-decoration: underline dotted #909399; }
.reverse { color: #67c23a; }
:deep(.warn-row) { background: #fdf6ec; }
h4 { margin: 16px 0 8px; font-size: 13px; }
</style>
