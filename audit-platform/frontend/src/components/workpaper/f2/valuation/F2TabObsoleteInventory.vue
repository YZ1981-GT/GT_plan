<template>
  <div class="f2-obsolete">
    <h3 class="title">长库龄呆滞超保质期存货 F2-48</h3>
    <div class="summary">
      <el-tag size="small">长库龄 ≥365天: {{ obs.summary.value.longAgeCount }}</el-tag>
      <el-tag size="small" type="warning">呆滞: {{ obs.summary.value.obsoleteCount }}</el-tag>
      <el-tag size="small" type="danger">超保质期: {{ obs.summary.value.expiredCount }}</el-tag>
      <el-tag size="small" type="info">建议跌价合计: {{ obs.summary.value.impairmentTotal.toLocaleString() }}</el-tag>
    </div>
    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="obs.addRow()">+ 新增行</el-button>
      <F2SheetToolbar
        :wp-id="wpId"
        api-prefix="f2-val"
        sheet="F2-48"
        :disabled="isReadonly"
        ai-section="impairment-evaluation"
        :existing-content="obs.auditNote.value"
        review-section="F2-48-conclusion"
        @ai-filled="(t: string) => { obs.auditNote.value = t }"
      />
    </div>
    <el-table :data="obs.enrichedRows.value" border size="small" max-height="480"
      :row-class-name="({ row }) => row.highlight ? 'warn-row' : ''">
      <el-table-column label="品名" width="120" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.itemName" size="small"
            @change="(v: string) => obs.updateRow(row.rowId, { itemName: v })" />
          <span v-else>{{ row.itemName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="数量" width="80">
        <template #default="{ row }">
          <el-input-number :model-value="row.qty" size="small" :controls="false" :disabled="isReadonly"
            @change="(v: number) => obs.updateRow(row.rowId, { qty: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="账面成本" width="100">
        <template #default="{ row }">
          <el-input-number :model-value="row.bookCost" size="small" :controls="false" :disabled="isReadonly"
            @change="(v: number) => obs.updateRow(row.rowId, { bookCost: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="库龄(天)" width="90">
        <template #default="{ row }">
          <el-input-number :model-value="row.ageDays" size="small" :controls="false" :disabled="isReadonly"
            @change="(v: number) => obs.updateRow(row.rowId, { ageDays: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="保质期(天)" width="100">
        <template #default="{ row }">
          <el-input-number :model-value="row.shelfDays" size="small" :controls="false" :disabled="isReadonly"
            @change="(v: number) => obs.updateRow(row.rowId, { shelfDays: v ?? 365 })" />
        </template>
      </el-table-column>
      <el-table-column label="剩余天数" width="80" align="right">
        <template #default="{ row }">
          <span :class="{ expired: row.expired }">{{ row.remainingDays }}</span>
        </template>
      </el-table-column>
      <el-table-column label="呆滞" width="60">
        <template #default="{ row }">
          <el-checkbox :model-value="row.isObsolete" :disabled="isReadonly"
            @change="(v: boolean) => obs.updateRow(row.rowId, { isObsolete: !!v })" />
        </template>
      </el-table-column>
      <el-table-column label="处置方案" width="110">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.disposalPlan" size="small"
            @change="(v: string) => obs.updateRow(row.rowId, { disposalPlan: v })">
            <el-option v-for="opt in DISPOSAL_OPTIONS" :key="opt" :label="opt" :value="opt" />
          </el-select>
          <span v-else>{{ row.disposalPlan }}</span>
        </template>
      </el-table-column>
      <el-table-column label="建议跌价" width="100" align="right">
        <template #default="{ row }"><span class="formula">{{ row.suggestedImpairment.toLocaleString() }}</span></template>
      </el-table-column>
      <el-table-column label="操作" width="55">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="obs.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
    <h4>审计说明</h4>
    <el-input v-model="obs.auditNote.value" type="textarea" :rows="3" :disabled="isReadonly" />
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useF2ObsoleteInventory, DISPOSAL_OPTIONS } from '../../composables/useF2ObsoleteInventory'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const obs = useF2ObsoleteInventory({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})
</script>

<style scoped>
.f2-obsolete { padding: 12px; font-size: 13px; }
.title { margin: 0 0 8px; }
.summary { margin-bottom: 8px; display: flex; gap: 8px; flex-wrap: wrap; }
.toolbar { margin-bottom: 8px; }
.formula { text-decoration: underline dotted #909399; }
.expired { color: #f56c6c; font-weight: 600; }
:deep(.warn-row) { background: #fdf6ec; }
h4 { margin: 16px 0 8px; font-size: 13px; }
</style>
