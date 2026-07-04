<template>
  <div class="g1-detail">
    <h3 class="sheet-title">G1-2 交易性金融资产明细表</h3>
    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="detail.addRow()">新增证券</el-button>
    </div>
    <el-segmented v-model="detail.segment" :options="segments" size="small" class="segment-bar" />

    <el-table :data="detail.rows" border size="small" max-height="500">
      <el-table-column prop="securityName" label="证券名称" width="120" fixed />

      <template v-if="detail.segment === 'basic'">
        <el-table-column label="代码" width="90">
          <template #default="{ row }">
            <el-input v-model="row.securityCode" size="small" :disabled="isReadonly" @change="detail.updateRow(row.id, { securityCode: row.securityCode })" />
          </template>
        </el-table-column>
        <el-table-column label="类型" width="100">
          <template #default="{ row }">
            <el-select v-model="row.investType" size="small" :disabled="isReadonly" @change="detail.updateRow(row.id, { investType: row.investType })">
              <el-option value="stock" label="股票" /><el-option value="fund" label="基金" />
              <el-option value="bond" label="债券" /><el-option value="derivative" label="衍生" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="市场" width="90">
          <template #default="{ row }">
            <el-input v-model="row.market" size="small" :disabled="isReadonly" @change="detail.updateRow(row.id, { market: row.market })" />
          </template>
        </el-table-column>
        <el-table-column label="初始成本" width="110">
          <template #default="{ row }">
            <el-input-number v-model="row.initialCost" size="small" :controls="false" :disabled="isReadonly" @change="detail.updateRow(row.id, { initialCost: row.initialCost })" />
          </template>
        </el-table-column>
      </template>

      <template v-else-if="detail.segment === 'holding'">
        <el-table-column label="期初数量" width="100"><template #default="{ row }"><el-input-number v-model="row.openingQty" size="small" :controls="false" :disabled="isReadonly" @change="detail.updateRow(row.id, { openingQty: row.openingQty })" /></template></el-table-column>
        <el-table-column label="买入" width="90"><template #default="{ row }"><el-input-number v-model="row.boughtQty" size="small" :controls="false" :disabled="isReadonly" @change="detail.updateRow(row.id, { boughtQty: row.boughtQty })" /></template></el-table-column>
        <el-table-column label="卖出" width="90"><template #default="{ row }"><el-input-number v-model="row.soldQty" size="small" :controls="false" :disabled="isReadonly" @change="detail.updateRow(row.id, { soldQty: row.soldQty })" /></template></el-table-column>
        <el-table-column label="期末数量" width="100"><template #default="{ row }">{{ row.closingQty }}</template></el-table-column>
        <el-table-column label="期末成本" width="110"><template #default="{ row }">{{ row.closingCost.toLocaleString() }}</template></el-table-column>
      </template>

      <template v-else-if="detail.segment === 'fv'">
        <el-table-column label="单位公允" width="100"><template #default="{ row }"><el-input-number v-model="row.unitFv" size="small" :controls="false" :disabled="isReadonly" @change="detail.updateRow(row.id, { unitFv: row.unitFv })" /></template></el-table-column>
        <el-table-column label="期末公允" width="110"><template #default="{ row }">{{ row.closingFv.toLocaleString() }}</template></el-table-column>
        <el-table-column label="Level" width="80"><template #default="{ row }"><el-select v-model="row.fvLevel" size="small" :disabled="isReadonly" @change="detail.updateRow(row.id, { fvLevel: row.fvLevel })"><el-option value="1" label="L1" /><el-option value="2" label="L2" /><el-option value="3" label="L3" /></el-select></template></el-table-column>
        <el-table-column label="公允变动" width="100"><template #default="{ row }">{{ row.fvChange.toLocaleString() }}</template></el-table-column>
      </template>

      <template v-else-if="detail.segment === 'pl'">
        <el-table-column label="处置收入" width="100"><template #default="{ row }"><el-input-number v-model="row.disposalProceeds" size="small" :controls="false" :disabled="isReadonly" @change="detail.updateRow(row.id, { disposalProceeds: row.disposalProceeds })" /></template></el-table-column>
        <el-table-column label="处置成本" width="100"><template #default="{ row }"><el-input-number v-model="row.disposalCost" size="small" :controls="false" :disabled="isReadonly" @change="detail.updateRow(row.id, { disposalCost: row.disposalCost })" /></template></el-table-column>
        <el-table-column label="已实现损益" width="110"><template #default="{ row }">{{ row.realizedGain.toLocaleString() }}</template></el-table-column>
      </template>

      <template v-else>
        <el-table-column label="未审" width="100"><template #default="{ row }"><el-input-number v-model="row.unadjusted" size="small" :controls="false" :disabled="isReadonly" @change="detail.updateRow(row.id, { unadjusted: row.unadjusted })" /></template></el-table-column>
        <el-table-column label="AJE" width="90"><template #default="{ row }"><el-input-number v-model="row.aje" size="small" :controls="false" :disabled="isReadonly" @change="detail.updateRow(row.id, { aje: row.aje })" /></template></el-table-column>
        <el-table-column label="RJE" width="90"><template #default="{ row }"><el-input-number v-model="row.rje" size="small" :controls="false" :disabled="isReadonly" @change="detail.updateRow(row.id, { rje: row.rje })" /></template></el-table-column>
        <el-table-column label="审定" width="110"><template #default="{ row }">{{ row.adjusted.toLocaleString() }}</template></el-table-column>
      </template>

      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" size="small" type="danger" link @click="detail.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="totals">期末成本合计: {{ detail.totals.closingCost.toLocaleString() }} | 公允价值: {{ detail.totals.closingFv.toLocaleString() }} | 审定: {{ detail.totals.adjusted.toLocaleString() }}</div>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useG1Detail } from '../../composables/useG1Detail'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const detail = useG1Detail({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const segments = [
  { label: '基础信息', value: 'basic' },
  { label: '持有明细', value: 'holding' },
  { label: '公允价值', value: 'fv' },
  { label: '损益', value: 'pl' },
  { label: '审定调整', value: 'adj' },
]
</script>

<style scoped>
.g1-detail { padding: 12px; font-size: 13px; }
.sheet-title { margin: 0 0 12px; }
.toolbar { margin-bottom: 8px; }
.segment-bar { margin-bottom: 12px; }
.totals { margin-top: 12px; font-size: 12px; color: #606266; }
</style>
