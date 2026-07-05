<template>
  <div class="h10-detail" data-testid="h10-detail-table">
    <div class="section-head">
      <h3 class="sheet-title">H10-2 资产处置明细表</h3>
      <div class="head-actions">
        <H10ImportExportDropdown :wp-id="wpId" sheet="H10-2" @imported="onImported" />
        <GtReviewTrigger section-id="H10-2-detail" />
        <el-button size="small" type="primary" plain :disabled="isReadonly" data-testid="h10-detail-add" @click="detail.addRow()">+ 新增</el-button>
      </div>
    </div>

    <el-segmented v-model="activeTab" :options="detail.tabOptions" size="small" data-testid="h10-detail-tabs" />

    <div class="stats-bar" data-testid="h10-detail-stats">
      <span>行数 {{ detail.statsSummary.value.count }}</span>
      <span>处置收入 {{ fmt(detail.statsSummary.value.totalIncome) }}</span>
      <span>损益合计 {{ fmt(detail.statsSummary.value.totalGainLoss) }}</span>
      <span>盈利 {{ detail.statsSummary.value.profitCount }} / 亏损 {{ detail.statsSummary.value.lossCount }}</span>
    </div>

    <el-table :data="detail.rows.value" border stripe size="small" style="font-size:13px;margin-top:8px" max-height="560"
      :row-class-name="({ row }) => row.isLoss ? 'loss-row' : ''">
      <el-table-column prop="seq" label="序号" width="48" align="center" fixed />
      <el-table-column label="资产名称" min-width="120" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.assetName" size="small"
            @update:model-value="(v: string) => detail.updateRow(row.id, { assetName: v })" />
          <span v-else>{{ row.assetName }}</span>
        </template>
      </el-table-column>

      <template v-if="activeTab === 'basic'">
        <el-table-column label="资产类型" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.assetType" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.id, { assetType: v })" />
            <span v-else>{{ row.assetType }}</span>
          </template>
        </el-table-column>
        <el-table-column label="来源底稿" width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.sourceWp" size="small"
              @change="(v: string) => detail.updateRow(row.id, { sourceWp: v })">
              <el-option v-for="o in detail.sourceWpOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
            <template v-else>
              <GtIndexChip v-if="row.sourceIndex" :value="row.sourceIndex" />
              <el-tag v-else size="small">{{ row.sourceWp }}</el-tag>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="原值" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.originalCost" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.id, { originalCost: v ?? 0 })" />
            <span v-else>{{ fmt(row.originalCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="累计折旧" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.accumulatedDepreciation" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.id, { accumulatedDepreciation: v ?? 0 })" />
            <span v-else>{{ fmt(row.accumulatedDepreciation) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="净值" width="96" align="right">
          <template #default="{ row }"><span class="formula-cell" title="原值-累计折旧">{{ fmt(row.netBookValue) }}</span></template>
        </el-table-column>
      </template>

      <template v-else-if="activeTab === 'disposal'">
        <el-table-column label="处置收入" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.disposalIncome" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.id, { disposalIncome: v ?? 0 })" />
            <span v-else>{{ fmt(row.disposalIncome) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="处置费用" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.disposalExpenses" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.id, { disposalExpenses: v ?? 0 })" />
            <span v-else>{{ fmt(row.disposalExpenses) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="税费" width="88" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.disposalTax" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.id, { disposalTax: v ?? 0 })" />
            <span v-else>{{ fmt(row.disposalTax) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="处置损益" width="96" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :class="{ loss: row.isLoss }" title="收入-净值-费用-税费">{{ fmt(row.disposalGainLoss) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="处置方式" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.disposalMethod" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.id, { disposalMethod: v })" />
            <span v-else>{{ row.disposalMethod }}</span>
          </template>
        </el-table-column>
      </template>

      <template v-else>
        <el-table-column label="审批文件" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.approvalDoc" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.id, { approvalDoc: v })" />
            <span v-else>{{ row.approvalDoc }}</span>
          </template>
        </el-table-column>
        <el-table-column label="评估报告" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.appraisalReport" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.id, { appraisalReport: v })" />
            <span v-else>{{ row.appraisalReport }}</span>
          </template>
        </el-table-column>
        <el-table-column label="合同/发票" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.contractRef" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.id, { contractRef: v })" />
            <span v-else>{{ row.contractRef || row.invoiceRef }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审计结论" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.auditConclusion" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.id, { auditConclusion: v })" />
            <span v-else>{{ row.auditConclusion }}</span>
          </template>
        </el-table-column>
      </template>

      <el-table-column label="操作" width="56" v-if="!isReadonly" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="detail.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useH10Detail } from '../../composables/useH10Detail'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import H10ImportExportDropdown from '../H10ImportExportDropdown.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const detail = useH10Detail({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const activeTab = detail.activeTab

async function onImported() {
  emit('imported')
  detail.reloadFromStore()
}

function fmt(v: number) {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h10-detail { font-size: 13px; }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.formula-cell { border-bottom: 1px dashed #999; }
.formula-cell.loss { color: #f56c6c; }
.stats-bar { display: flex; flex-wrap: wrap; gap: 16px; margin-top: 8px; padding: 10px; background: #f5f7fa; font-size: 12px; }
:deep(.loss-row) { background: #fef0f0 !important; }
</style>
