<template>
  <div class="g1-adjudication">
    <h3 class="sheet-title">G1-1 交易性金融资产审定表</h3>
    <el-table :data="adj.rows" border size="small" :span-method="spanInvest">
      <el-table-column prop="investLabel" label="投资品种" width="100" fixed />
      <el-table-column prop="measureLabel" label="项目" width="120" fixed />
      <el-table-column label="上期未审" width="110">
        <template #default="{ row }">
          <el-input-number
            v-if="row.rowKey !== 'subtotal'"
            :model-value="row.priorUnadjusted"
            size="small" :controls="false" :disabled="isReadonly"
            @update:model-value="(v: number) => adj.updateField(row.investKey, row.measureKey, 'prior', 'unadj', v ?? 0)"
          />
        </template>
      </el-table-column>
      <el-table-column label="上期AJE" width="100">
        <template #default="{ row }">
          <el-input-number
            v-if="row.rowKey !== 'subtotal'"
            :model-value="row.priorAje"
            size="small" :controls="false" :disabled="isReadonly"
            @update:model-value="(v: number) => adj.updateField(row.investKey, row.measureKey, 'prior', 'aje', v ?? 0)"
          />
        </template>
      </el-table-column>
      <el-table-column label="上期RJE" width="100">
        <template #default="{ row }">
          <el-input-number
            v-if="row.rowKey !== 'subtotal'"
            :model-value="row.priorRje"
            size="small" :controls="false" :disabled="isReadonly"
            @update:model-value="(v: number) => adj.updateField(row.investKey, row.measureKey, 'prior', 'rje', v ?? 0)"
          />
        </template>
      </el-table-column>
      <el-table-column label="上期审定" width="110">
        <template #default="{ row }">{{ row.priorAudited.toLocaleString() }}</template>
      </el-table-column>
      <el-table-column label="本期未审" width="110">
        <template #default="{ row }">
          <el-input-number
            v-if="row.rowKey !== 'subtotal'"
            :model-value="row.currentUnadjusted"
            size="small" :controls="false" :disabled="isReadonly"
            @update:model-value="(v: number) => adj.updateField(row.investKey, row.measureKey, 'cur', 'unadj', v ?? 0)"
          />
        </template>
      </el-table-column>
      <el-table-column label="本期AJE" width="100">
        <template #default="{ row }">
          <el-input-number
            v-if="row.rowKey !== 'subtotal'"
            :model-value="row.currentAje"
            size="small" :controls="false" :disabled="isReadonly"
            @update:model-value="(v: number) => adj.updateField(row.investKey, row.measureKey, 'cur', 'aje', v ?? 0)"
          />
        </template>
      </el-table-column>
      <el-table-column label="本期RJE" width="100">
        <template #default="{ row }">
          <el-input-number
            v-if="row.rowKey !== 'subtotal'"
            :model-value="row.currentRje"
            size="small" :controls="false" :disabled="isReadonly"
            @update:model-value="(v: number) => adj.updateField(row.investKey, row.measureKey, 'cur', 'rje', v ?? 0)"
          />
        </template>
      </el-table-column>
      <el-table-column label="本期审定" width="110">
        <template #default="{ row }">{{ row.currentAudited.toLocaleString() }}</template>
      </el-table-column>
      <el-table-column label="变动额" width="100">
        <template #default="{ row }">{{ row.changeAmount.toLocaleString() }}</template>
      </el-table-column>
      <el-table-column label="变动率" width="80">
        <template #default="{ row }">
          <span v-if="row.changeRate === 'N/A'">N/A</span>
          <span v-else-if="row.changeRate === ''">—</span>
          <span v-else>{{ (Number(row.changeRate) * 100).toFixed(1) }}%</span>
        </template>
      </el-table-column>
    </el-table>

    <el-table :data="[adj.totalRow]" border size="small" class="subtotal-table" :show-header="false">
      <el-table-column width="100"><template #default="{ row }"><b>{{ row.investLabel }}</b></template></el-table-column>
      <el-table-column width="120" />
      <el-table-column width="110"><template #default="{ row }">{{ row.priorUnadjusted.toLocaleString() }}</template></el-table-column>
      <el-table-column width="100"><template #default="{ row }">{{ row.priorAje.toLocaleString() }}</template></el-table-column>
      <el-table-column width="100"><template #default="{ row }">{{ row.priorRje.toLocaleString() }}</template></el-table-column>
      <el-table-column width="110"><template #default="{ row }">{{ row.priorAudited.toLocaleString() }}</template></el-table-column>
      <el-table-column width="110"><template #default="{ row }">{{ row.currentUnadjusted.toLocaleString() }}</template></el-table-column>
      <el-table-column width="100"><template #default="{ row }">{{ row.currentAje.toLocaleString() }}</template></el-table-column>
      <el-table-column width="100"><template #default="{ row }">{{ row.currentRje.toLocaleString() }}</template></el-table-column>
      <el-table-column width="110"><template #default="{ row }">{{ row.currentAudited.toLocaleString() }}</template></el-table-column>
      <el-table-column width="100"><template #default="{ row }">{{ row.changeAmount.toLocaleString() }}</template></el-table-column>
      <el-table-column width="80" />
    </el-table>

    <div class="tb-diff-row">
      <span>试算平衡表数（1501）：
        <el-input-number v-model="adj.trialBalanceAmount" size="small" :controls="false" :disabled="isReadonly" />
      </span>
      <span :class="{ 'diff-red': adj.trialBalanceDiff !== 0 }">
        差异：{{ adj.trialBalanceDiff.toLocaleString() }}
        <template v-if="adj.trialBalanceDiff === 0"> ✓</template>
        <template v-else> ✗</template>
      </span>
    </div>

    <div class="audit-notes">
      <h4>审计说明</h4>
      <el-input v-model="adj.auditNote" type="textarea" :rows="2" :disabled="isReadonly" />
      <h4>审计结论</h4>
      <el-input v-model="adj.conclusion" type="textarea" :rows="2" :disabled="isReadonly" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useG1Adjudication } from '../../composables/useG1Adjudication'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const adj = useG1Adjudication({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

function spanInvest({ row, rowIndex, columnIndex }: { row: { investKey: string; rowKey: string }; rowIndex: number; columnIndex: number }) {
  if (columnIndex !== 0) return { rowspan: 1, colspan: 1 }
  const data = adj.rows
  if (row.rowKey === 'subtotal') return { rowspan: 1, colspan: 1 }
  const firstIdx = data.findIndex((r) => r.investKey === row.investKey)
  if (firstIdx !== rowIndex) return { rowspan: 0, colspan: 0 }
  const same = data.filter((r) => r.investKey === row.investKey && r.rowKey !== 'subtotal').length
  return { rowspan: same, colspan: 1 }
}
</script>

<style scoped>
.g1-adjudication { padding: 12px; font-size: 13px; }
.sheet-title { margin: 0 0 12px; font-size: 15px; }
.subtotal-table { margin-top: -1px; }
.tb-diff-row { display: flex; gap: 24px; margin: 16px 0; align-items: center; }
.diff-red { color: #f56c6c; font-weight: 600; }
.audit-notes h4 { margin: 12px 0 6px; font-size: 13px; }
</style>
