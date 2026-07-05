<template>
  <div class="g9-detail" data-testid="g9-detail-table">
    <div class="toolbar">
      <h3>G9-2 明细表</h3>
      <div class="head-actions">
        <G9ImportExportDropdown :wp-id="wpId" sheet="G9-2" @imported="onImported" />
        <el-button v-if="!isReadonly" size="small" @click="detail.addRow()">+ 新增行</el-button>
      </div>
    </div>
    <el-segmented v-model="detail.activeTab.value" :options="tabOptions" size="small" />
    <el-table :data="detail.rows.value" border size="small" style="font-size:13px;margin-top:8px" max-height="520"
      highlight-current-row @current-change="onRowChange">
      <el-table-column prop="seq" label="#" width="44" align="center" fixed />
      <template v-if="detail.activeTab.value === 'basic'">
        <el-table-column label="资产名称" min-width="120" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.assetName" size="small" @update:model-value="(v: string) => detail.updateRow(row.rowId, { assetName: v })" />
            <span v-else>{{ row.assetName }}</span>
          </template>
        </el-table-column>
        <el-table-column label="分类" width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.classification" size="small" @update:model-value="(v: string) => detail.updateRow(row.rowId, { classification: v })">
              <el-option v-for="o in detail.classificationOptions" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.classification }}</span>
          </template>
        </el-table-column>
        <el-table-column label="初始投资日" width="108">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.initialInvestDate" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { initialInvestDate: v })" />
            <span v-else>{{ row.initialInvestDate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="到期日" width="108">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.maturityDate" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { maturityDate: v })" />
            <span v-else>{{ row.maturityDate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="面值/成本" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.faceValueOrCost" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { faceValueOrCost: v ?? 0 })" />
            <span v-else>{{ fmt(row.faceValueOrCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="持有数量" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.holdingQuantity" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { holdingQuantity: v ?? 0 })" />
            <span v-else>{{ row.holdingQuantity }}</span>
          </template>
        </el-table-column>
        <el-table-column label="计量属性" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.measurementAttribute" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { measurementAttribute: v })" />
            <span v-else>{{ row.measurementAttribute }}</span>
          </template>
        </el-table-column>
        <el-table-column label="关联方" width="72" align="center">
          <template #default="{ row }">
            <el-checkbox v-if="!isReadonly" :model-value="row.isRelatedParty"
              @update:model-value="(v: boolean) => detail.updateRow(row.rowId, { isRelatedParty: v })" />
            <span v-else>{{ row.isRelatedParty ? '是' : '否' }}</span>
          </template>
        </el-table-column>
      </template>
      <template v-else-if="detail.activeTab.value === 'movement'">
        <el-table-column label="资产名称" prop="assetName" min-width="100" fixed />
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
        <el-table-column label="本期增加" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.increaseAmount" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { increaseAmount: v ?? 0 })" />
            <span v-else>{{ fmt(row.increaseAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少" width="96" align="right">
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
        <el-table-column label="利息" width="88" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.interestIncome" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { interestIncome: v ?? 0 })" />
            <span v-else>{{ fmt(row.interestIncome) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值" width="88" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.impairmentLoss" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { impairmentLoss: v ?? 0 })" />
            <span v-else>{{ fmt(row.impairmentLoss) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="OCI变动" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.ociChange" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { ociChange: v ?? 0 })" />
            <span v-else>{{ fmt(row.ociChange) }}</span>
          </template>
        </el-table-column>
      </template>
      <template v-else>
        <el-table-column label="资产名称" prop="assetName" min-width="100" fixed />
        <el-table-column label="期末余额" width="100" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.closingBalance) }}</span></template>
        </el-table-column>
        <el-table-column label="调整数" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.closingAdjustment" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { closingAdjustment: v ?? 0 })" />
            <span v-else>{{ fmt(row.closingAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="100" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.closingAdjusted) }}</span></template>
        </el-table-column>
        <el-table-column label="层次" width="96">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.fairValueLevel" size="small" @update:model-value="(v: string) => detail.updateRow(row.rowId, { fairValueLevel: v })">
              <el-option v-for="o in detail.fvLevelOptions" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.fairValueLevel }}</span>
          </template>
        </el-table-column>
        <el-table-column label="估值方法" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.valuationMethod" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { valuationMethod: v })" />
            <span v-else>{{ row.valuationMethod }}</span>
          </template>
        </el-table-column>
        <el-table-column label="OCI累计" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.ociCumulative" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { ociCumulative: v ?? 0 })" />
            <span v-else>{{ fmt(row.ociCumulative) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值准备" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.impairmentProvision" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { impairmentProvision: v ?? 0 })" />
            <span v-else>{{ fmt(row.impairmentProvision) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="发函情况" width="96">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.confirmationStatus" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { confirmationStatus: v })" />
            <span v-else>{{ row.confirmationStatus }}</span>
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
    </el-table>
    <div class="subtotals" data-testid="g9-detail-subtotals">
      <span v-for="(amt, cls) in detail.classificationSubtotals.value" :key="cls"
        :class="{ 'total-line': cls === '总计' }">{{ cls }}: {{ fmt(amt) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import G9ImportExportDropdown from '../G9ImportExportDropdown.vue'
import { useG9Detail } from '../../composables/useG9Detail'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const tabOptions = [
  { label: '基础信息', value: 'basic' },
  { label: '期初+变动', value: 'movement' },
  { label: '期末+公允价值', value: 'closing' },
]

const detail = useG9Detail({
  allResponses: computed(() => props.allResponses),
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly),
})

function onImported() { emit('imported') }

function onRowChange(r: any) {
  if (r) detail.activeRowIndex.value = detail.rows.value.findIndex((x) => x.rowId === r.rowId)
}

function fmt(n: number) {
  return Number(n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.g9-detail { font-size: 13px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.head-actions { display: flex; gap: 8px; }
.subtotals { margin-top: 8px; display: flex; gap: 16px; flex-wrap: wrap; color: #606266; }
.total-line { font-weight: 600; color: #303133; }
.formula-cell { border-bottom: 1px dashed #909399; }
</style>
