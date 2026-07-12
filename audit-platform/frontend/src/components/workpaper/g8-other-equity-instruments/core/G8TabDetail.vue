<template>
  <div class="g8-detail" data-testid="g8-detail-table">
    <div class="toolbar">
      <h3>G8-2 明细表</h3>
      <div class="head-actions">
        <G8ImportExportDropdown :wp-id="wpId" sheet="G8-2" @imported="onImported" />
        <GtReviewTrigger section-id="G8-2-detail" />
        <el-button v-if="!isReadonly" size="small" data-testid="g8-detail-add" @click="detail.addRow()">+ 新增行</el-button>
      </div>
    </div>
    <el-segmented v-model="detail.activeTab.value" :options="tabOptions" size="small" data-testid="g8-detail-tabs" />
    <el-table :data="detail.rows.value" border size="small" style="font-size:13px;margin-top:8px" max-height="520"
      highlight-current-row @current-change="onRowChange">
      <el-table-column prop="seq" label="#" width="44" align="center" fixed />
      <template v-if="detail.activeTab.value === 'basic'">
        <el-table-column label="被投资单位" min-width="120" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.investeeName" size="small" @update:model-value="(v: string) => detail.updateRow(row.rowId, { investeeName: v })" />
            <span v-else>{{ row.investeeName }}</span>
          </template>
        </el-table-column>
        <el-table-column label="投资比例" width="88" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.investmentRatio" size="small" :controls="false" :step="0.01" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { investmentRatio: v ?? 0 })" />
            <span v-else>{{ (row.investmentRatio * 100).toFixed(2) }}%</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.openingBalance" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { openingBalance: v ?? 0 })" />
            <span v-else>{{ fmt(row.openingBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初调整" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.openingAdjustment" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { openingAdjustment: v ?? 0 })" />
            <span v-else>{{ fmt(row.openingAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初审定" width="96" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.openingAdjusted) }}</span></template>
        </el-table-column>
        <el-table-column label="增加" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.increaseAmount" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { increaseAmount: v ?? 0 })" />
            <span v-else>{{ fmt(row.increaseAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减少" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.decreaseAmount" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { decreaseAmount: v ?? 0 })" />
            <span v-else>{{ fmt(row.decreaseAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="FV变动" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.fvChangeAmount" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { fvChangeAmount: v ?? 0 })" />
            <span v-else>{{ fmt(row.fvChangeAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="96" align="right">
          <template #default="{ row }"><span class="formula-cell" title="期初审定+增加-减少+FV变动">{{ fmt(row.closingBalance) }}</span></template>
        </el-table-column>
        <el-table-column label="调整数" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.closingAdjustment" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { closingAdjustment: v ?? 0 })" />
            <span v-else>{{ fmt(row.closingAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="96" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.closingAdjusted) }}</span></template>
        </el-table-column>
        <el-table-column label="指定OCI原因" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.designationReason" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { designationReason: v })" />
            <span v-else>{{ row.designationReason }}</span>
          </template>
        </el-table-column>
      </template>
      <template v-else>
        <el-table-column label="被投资单位" prop="investeeName" min-width="120" fixed />
        <el-table-column label="OCI累计" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.ociCumulativeChange" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { ociCumulativeChange: v ?? 0 })" />
            <span v-else>{{ fmt(row.ociCumulativeChange) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期OCI" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.ociCurrentChange" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { ociCurrentChange: v ?? 0 })" />
            <span v-else>{{ fmt(row.ociCurrentChange) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="OCI转留存" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.ociToRetainedEarnings" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { ociToRetainedEarnings: v ?? 0 })" />
            <span v-else>{{ fmt(row.ociToRetainedEarnings) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="转入原因" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.transferReason" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { transferReason: v })" />
            <span v-else>{{ row.transferReason }}</span>
          </template>
        </el-table-column>
        <el-table-column label="发函情况" width="96">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.confirmationStatus" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { confirmationStatus: v })" />
            <span v-else>{{ row.confirmationStatus }}</span>
          </template>
        </el-table-column>
        <el-table-column label="层次" width="96">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.fairValueLevel" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { fairValueLevel: v })">
              <el-option v-for="o in detail.fvLevelOptions" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.fairValueLevel }}</span>
          </template>
        </el-table-column>
        <el-table-column label="估值方法" width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.valuationMethod" size="small" allow-create filterable
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { valuationMethod: v })">
              <el-option v-for="o in detail.valuationMethodOptions" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.valuationMethod }}</span>
          </template>
        </el-table-column>
        <el-table-column label="持股数" width="88" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.shareCount" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { shareCount: v ?? 0 })" />
            <span v-else>{{ row.shareCount }}</span>
          </template>
        </el-table-column>
        <el-table-column label="每股公允价值" width="108" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.pricePerShare" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { pricePerShare: v ?? 0 })" />
            <span v-else>{{ fmt(row.pricePerShare) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="公允价值合计" width="108" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.fairValueTotal" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { fairValueTotal: v ?? 0 })" />
            <span v-else>{{ fmt(row.fairValueTotal) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { remark: v })" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
      </template>
      <el-table-column v-if="!isReadonly" label="操作" width="56" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="detail.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-table v-if="detail.rows.value.length" :data="[detail.totals.value]" border size="small" class="totals-table" style="font-size:13px;margin-top:8px">
      <el-table-column label="合计" width="120" />
      <el-table-column label="期初审定" width="100" align="right">
        <template #default="{ row }">{{ fmt(row.openingAdjusted) }}</template>
      </el-table-column>
      <el-table-column label="增加" width="96" align="right">
        <template #default="{ row }">{{ fmt(row.increaseAmount) }}</template>
      </el-table-column>
      <el-table-column label="减少" width="96" align="right">
        <template #default="{ row }">{{ fmt(row.decreaseAmount) }}</template>
      </el-table-column>
      <el-table-column label="FV变动" width="96" align="right">
        <template #default="{ row }">{{ fmt(row.fvChangeAmount) }}</template>
      </el-table-column>
      <el-table-column label="期末余额" width="96" align="right">
        <template #default="{ row }">{{ fmt(row.closingBalance) }}</template>
      </el-table-column>
      <el-table-column label="审定数" width="96" align="right">
        <template #default="{ row }"><strong>{{ fmt(row.closingAdjusted) }}</strong></template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import G8ImportExportDropdown from '../G8ImportExportDropdown.vue'
import { useG8Detail } from '../../composables/useG8Detail'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const detail = useG8Detail({
  allResponses: computed(() => props.allResponses),
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly),
})

const tabOptions = [
  { label: '基础信息', value: 'basic' },
  { label: '公允价值+OCI', value: 'fv_oci' },
]

function onRowChange(row: { seq?: number } | undefined) {
  if (row?.seq) detail.activeRowIndex.value = row.seq - 1
}

function onImported() { emit('imported') }

function fmt(n: number) {
  return Number(n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.g8-detail { font-size: var(--wp-font-size, 13px); }
.toolbar { display: flex; justify-content: space-between; margin-bottom: 8px; align-items: center; }
.head-actions { display: flex; gap: 8px; }
.formula-cell { border-bottom: 1px dashed #c0c4cc; cursor: help; }
</style>
