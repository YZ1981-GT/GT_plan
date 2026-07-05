<template>
  <div class="g2-adjudication">
    <div class="section-head">
      <h3 class="sheet-title">G2-1 应收利息审定表</h3>
      <div class="head-actions">
        <el-button size="small" @click="openReviewDialog('G2-1-adjudication')">💬复核</el-button>
      </div>
    </div>

    <el-table :data="adj.dataRows.value" border size="small" max-height="400">
      <el-table-column label="项目" prop="item" width="140" fixed>
        <template #default="{ row }">
          <span :class="{ 'row-bold': row.id === 'subtotal' }">{{ row.item }}</span>
        </template>
      </el-table-column>

      <!-- 期初4列 -->
      <el-table-column label="期初未审" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.id !== 'subtotal'"
            :model-value="row.openingUnadjusted"
            size="small" :controls="false" :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => adj.updateCell(row.id, 'openingUnadjusted', v ?? 0)"
          />
          <span v-else class="row-bold">{{ fmtNum(row.openingUnadjusted) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期初AJE" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.id !== 'subtotal'"
            :model-value="row.openingAJE"
            size="small" :controls="false" :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => adj.updateCell(row.id, 'openingAJE', v ?? 0)"
          />
          <span v-else class="row-bold">{{ fmtNum(row.openingAJE) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期初RJE" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.id !== 'subtotal'"
            :model-value="row.openingRJE"
            size="small" :controls="false" :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => adj.updateCell(row.id, 'openingRJE', v ?? 0)"
          />
          <span v-else class="row-bold">{{ fmtNum(row.openingRJE) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期初审定" width="120" align="right">
        <template #default="{ row }">
          <span :class="{ 'row-bold': row.id === 'subtotal', 'formula-cell': row.id !== 'subtotal' }"
            :title="row.id !== 'subtotal' ? '期初审定 = 期初未审 + AJE + RJE' : ''">
            {{ fmtNum(row.openingAdjusted) }}
          </span>
        </template>
      </el-table-column>

      <!-- 期末4列 -->
      <el-table-column label="期末未审" width="120" align="right">
        <template #default="{ row }">
          <span :class="{ 'row-bold': row.id === 'subtotal', 'formula-cell': row.id !== 'subtotal' }"
            :title="row.id !== 'subtotal' ? '期末未审 = 期初审定 + 借方 - 贷方' : ''">
            {{ fmtNum(row.closingUnadjusted) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="期末AJE" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.id !== 'subtotal'"
            :model-value="row.closingAJE"
            size="small" :controls="false" :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => adj.updateCell(row.id, 'closingAJE', v ?? 0)"
          />
          <span v-else class="row-bold">{{ fmtNum(row.closingAJE) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末RJE" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.id !== 'subtotal'"
            :model-value="row.closingRJE"
            size="small" :controls="false" :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => adj.updateCell(row.id, 'closingRJE', v ?? 0)"
          />
          <span v-else class="row-bold">{{ fmtNum(row.closingRJE) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末审定" width="120" align="right">
        <template #default="{ row }">
          <span :class="{ 'row-bold': row.id === 'subtotal', 'formula-cell': row.id !== 'subtotal' }"
            :title="row.id !== 'subtotal' ? '期末审定 = 期末未审 + AJE + RJE' : ''">
            {{ fmtNum(row.closingAdjusted) }}
          </span>
        </template>
      </el-table-column>

      <!-- 索引 -->
      <el-table-column label="索引" width="100">
        <template #default="{ row }">
          <el-input
            v-if="row.id !== 'subtotal'"
            :model-value="row.indexRef"
            size="small" :disabled="isReadonly"
            @change="(v: string) => adj.updateCell(row.id, 'indexRef', v)"
          />
        </template>
      </el-table-column>
    </el-table>

    <!-- 合计行 -->
    <div class="totals">
      <div class="grand-total">
        <span class="subtotal-label">合计</span>
        期初审定 {{ fmtNum(adj.subtotalRow.value.openingAdjusted) }} ·
        期末审定 {{ fmtNum(adj.subtotalRow.value.closingAdjusted) }}
      </div>
    </div>

    <!-- 试算表数 + 差异 -->
    <div class="tb-diff-row">
      <span class="tb-label">试算平衡表数（1132）：</span>
      <el-input-number
        :model-value="adj.trialBalanceAmount.value"
        size="small" :controls="false" :disabled="isReadonly"
        style="width:140px"
        @update:model-value="(v: number) => adj.setTrialBalance(v ?? 0)"
      />
      <span :class="['diff-value', { 'diff-red': adj.hasVarianceHighlight.value }]">
        差异：{{ fmtNum(adj.variance.value) }}
        <template v-if="!adj.hasVarianceHighlight.value"> ✓</template>
        <template v-else> ✗</template>
      </span>
    </div>

    <!-- 审计结论 -->
    <el-card class="conclusion-card" shadow="never">
      <template #header>审计结论</template>
      <el-input v-model="adj.auditConclusion.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly" placeholder="对应收利息审定表的复核结论..." />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, inject } from 'vue'
import { useG2Adjudication } from '../../composables/useG2Adjudication'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const adj = useG2Adjudication({
  wpId: ref(''),
  projectId: ref(''),
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

function fmtNum(v: unknown): string {
  return typeof v === 'number' ? v.toLocaleString() : String(v ?? '')
}
</script>

<style scoped>
.g2-adjudication { padding: 12px; font-size: 13px; }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.row-bold { font-weight: 600; }
.totals { margin-top: 12px; font-size: 12px; color: #606266; }
.subtotal-label { font-weight: 600; margin-right: 8px; }
.grand-total { margin-top: 6px; padding-top: 6px; border-top: 1px solid #dcdfe6; font-weight: 600; color: #303133; }
.tb-diff-row { display: flex; gap: 16px; margin: 16px 0; align-items: center; font-size: 13px; }
.tb-label { font-weight: 500; }
.diff-value { font-weight: 600; }
.diff-red { color: #f56c6c; }
.conclusion-card { margin-top: 12px; }
</style>
