<template>
  <div class="g10-detail" data-testid="g10-detail-table">
    <div class="section-head">
      <h3 class="sheet-title">G10-2 交易性金融负债明细表</h3>
      <div class="head-actions">
        <G10ImportExportDropdown :wp-id="wpId" sheet="G10-2" @imported="onImported" />
        <GtReviewTrigger section-id="G10-2-detail" />
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="detail.addRow()">+ 新增</el-button>
      </div>
    </div>

    <el-segmented v-model="detail.activeTab.value" :options="tabOptions" size="small" />

    <el-table
      :data="detail.rows.value"
      border stripe size="small"
      style="font-size:13px;margin-top:8px"
      max-height="520"
      highlight-current-row
      @current-change="onRowChange"
    >
      <el-table-column prop="seq" label="#" width="44" align="center" fixed />

      <template v-if="detail.activeTab.value === 'basic'">
        <el-table-column label="负债名称" min-width="120" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.liabilityName" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { liabilityName: v })" />
            <span v-else>{{ row.liabilityName }}</span>
          </template>
        </el-table-column>
        <el-table-column label="负债类型" width="120">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.liabilityType" size="small"
              @change="(v: string) => detail.updateRow(row.rowId, { liabilityType: v })">
              <el-option v-for="t in detail.G10_LIABILITY_TYPE_OPTIONS" :key="t" :label="t" :value="t" />
            </el-select>
            <span v-else>{{ row.liabilityType }}</span>
          </template>
        </el-table-column>
        <el-table-column label="对手方" width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.counterparty" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { counterparty: v })" />
            <span v-else>{{ row.counterparty }}</span>
          </template>
        </el-table-column>
        <el-table-column label="合同日" width="108">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.contractDate" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { contractDate: v })" />
            <span v-else>{{ row.contractDate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="到期日" width="108">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.maturityDate" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { maturityDate: v })" />
            <span v-else>{{ row.maturityDate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="初始金额" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.initialAmount" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { initialAmount: v ?? 0 })" />
            <span v-else>{{ fmt(row.initialAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.openingBalance" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { openingBalance: v ?? 0, openingAdjusted: v ?? 0 })" />
            <span v-else>{{ fmt(row.openingBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期增加" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.currentIncrease" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { currentIncrease: v ?? 0 })" />
            <span v-else>{{ fmt(row.currentIncrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.currentDecrease" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { currentDecrease: v ?? 0 })" />
            <span v-else>{{ fmt(row.currentDecrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="100" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.closingBalance) }}</span></template>
        </el-table-column>
        <el-table-column label="审定数" width="100" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.closingAdjusted) }}</span></template>
        </el-table-column>
      </template>

      <template v-else>
        <el-table-column label="负债名称" min-width="120" fixed>
          <template #default="{ row }">{{ row.liabilityName }}</template>
        </el-table-column>
        <el-table-column label="FV层次" width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.fairValueLevel" size="small"
              @change="(v: string) => detail.updateRow(row.rowId, { fairValueLevel: v })">
              <el-option v-for="lv in detail.G10_FV_LEVEL_OPTIONS" :key="lv" :label="lv" :value="lv" />
            </el-select>
            <span v-else>{{ row.fairValueLevel }}</span>
          </template>
        </el-table-column>
        <el-table-column label="估值方法" width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.valuationMethod" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { valuationMethod: v })" />
            <span v-else>{{ row.valuationMethod }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初FV" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.openingFairValue" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { openingFairValue: v ?? 0 })" />
            <span v-else>{{ fmt(row.openingFairValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末FV" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.closingFairValue" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { closingFairValue: v ?? 0 })" />
            <span v-else>{{ fmt(row.closingFairValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="FV变动" width="100" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.fairValueChange) }}</span></template>
        </el-table-column>
        <el-table-column label="计入损益" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.profitLossAmount" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { profitLossAmount: v ?? 0 })" />
            <span v-else>{{ fmt(row.profitLossAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="衍生" width="64" align="center">
          <template #default="{ row }">
            <el-checkbox v-if="!isReadonly" :model-value="row.isDerivative"
              @change="(v: boolean) => detail.updateRow(row.rowId, { isDerivative: v })" />
            <span v-else>{{ row.isDerivative ? '是' : '否' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="主合同" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.hostContractDesc" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { hostContractDesc: v })" />
            <span v-else>{{ row.hostContractDesc }}</span>
          </template>
        </el-table-column>
        <el-table-column label="嵌入衍生" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.embeddedDerivativeJudgment" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { embeddedDerivativeJudgment: v })" />
            <span v-else>{{ row.embeddedDerivativeJudgment }}</span>
          </template>
        </el-table-column>
        <el-table-column label="发函" width="88">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.confirmationStatus" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { confirmationStatus: v })" />
            <span v-else>{{ row.confirmationStatus }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="90">
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

    <div class="total-bar">
      合计 期末审定 {{ fmt(detail.totalRow.value.closingAdjusted) }}
      · 期初审定 {{ fmt(detail.totalRow.value.openingAdjusted) }}
      · FV变动合计 {{ fmt(detail.rows.value.reduce((s, r) => s + r.fairValueChange, 0)) }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useG10Detail, type G10DetailRow } from '../../composables/useG10Detail'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import G10ImportExportDropdown from '../G10ImportExportDropdown.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const detail = useG10Detail({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const tabOptions = [
  { label: '基础信息', value: 'basic' },
  { label: '公允价值+分类', value: 'fv' },
]

function onImported() {
  emit('imported')
  detail.reloadFromStore()
}

function onRowChange(row: G10DetailRow | undefined) {
  if (!row) return
  const idx = detail.rows.value.findIndex((r) => r.rowId === row.rowId)
  if (idx >= 0) detail.setActiveRowIndex(idx)
}

function fmt(v: number) {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.g10-detail { font-size: 13px; }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.formula-cell { border-bottom: 1px dashed #999; }
.total-bar { margin-top: 8px; padding: 8px; background: #f5f7fa; font-size: 12px; }
</style>
