<template>
  <div class="g11-detail">
    <div class="section-head">
      <h3 class="sheet-title">G11-2 投资收益明细分析表</h3>
      <div class="head-actions">
        <G11ImportExportDropdown :wp-id="wpId" sheet="G11-2" @imported="onImported" />
        <GtReviewTrigger section-id="G11-2-detail" />
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="detail.addRow()">+ 新增</el-button>
      </div>
    </div>
    <el-table :data="detail.rows.value" border stripe size="small" style="font-size:13px" max-height="560" data-testid="g11-detail-table">
      <el-table-column prop="seq" label="序号" width="48" align="center" fixed />
      <el-table-column label="项目" min-width="130" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.itemName" size="small"
            @update:model-value="(v: string) => detail.updateRow(row.id, { itemName: v })" />
          <span v-else>{{ row.itemName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="投资类型" width="120">
        <template #default="{ row }">
          <span class="group-tag">{{ row.group }}</span>
        </template>
      </el-table-column>
      <el-table-column label="被投资单位" width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.investeeName" size="small"
            @update:model-value="(v: string) => detail.updateRow(row.id, { investeeName: v })" />
          <span v-else>{{ row.investeeName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期数" align="center">
        <el-table-column label="未审" width="88" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.currentUnadjusted" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.id, { currentUnadjusted: v ?? 0 })" />
            <span v-else>{{ fmt(row.currentUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="调整" width="88" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.currentAdjustment" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.id, { currentAdjustment: v ?? 0 })" />
            <span v-else>{{ fmt(row.currentAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定" width="88" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.currentAudited) }}</span></template>
        </el-table-column>
        <el-table-column label="占比" width="64" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmtPct(row.currentShare) }}</span></template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="上期数" align="center">
        <el-table-column label="未审" width="88" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.priorUnadjusted" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.id, { priorUnadjusted: v ?? 0 })" />
            <span v-else>{{ fmt(row.priorUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="调整" width="88" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.priorAdjustment" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.id, { priorAdjustment: v ?? 0 })" />
            <span v-else>{{ fmt(row.priorAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定" width="88" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.priorAudited) }}</span></template>
        </el-table-column>
        <el-table-column label="占比" width="64" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmtPct(row.priorShare) }}</span></template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="变动额" width="88" align="right">
        <template #default="{ row }">{{ fmt(row.changeAmount) }}</template>
      </el-table-column>
      <el-table-column label="变动率" width="72" align="right">
        <template #default="{ row }">{{ fmtRate(row.changeRate) }}</template>
      </el-table-column>
      <el-table-column label="变动原因/索引" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.reasonIndex" size="small"
            @update:model-value="(v: string) => detail.updateRow(row.id, { reasonIndex: v })" />
          <GtIndexChip v-else-if="row.reasonIndex" :value="row.reasonIndex" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="56" v-if="!isReadonly" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="detail.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div class="group-summary" v-if="detail.groupedRows.value.length">
      <span v-for="g in detail.groupedRows.value" :key="g.groupName" class="group-chip">
        {{ g.groupName }} {{ fmt(g.subtotal.currentAudited) }}
      </span>
    </div>
    <div class="total-bar">
      合计 本期审定 {{ fmt(detail.totalRow.value.currentAudited) }}
      · 上期审定 {{ fmt(detail.totalRow.value.priorAudited) }}
      · 变动 {{ fmt(detail.totalRow.value.changeAmount) }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useG11DetailAnalysis } from '../../composables/useG11DetailAnalysis'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import G11ImportExportDropdown from '../G11ImportExportDropdown.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const detail = useG11DetailAnalysis({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

async function onImported() {
  emit('imported')
  detail.reloadFromStore()
}

function fmt(v: number) { return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
function fmtRate(r: number | null) { return r === null ? 'N/A' : (r * 100).toFixed(1) + '%' }
function fmtPct(v: number | null) { return v === null ? '-' : (v * 100).toFixed(1) + '%' }
</script>

<style scoped>
.g11-detail { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.formula-cell { border-bottom: 1px dashed #999; cursor: help; }
.group-tag { font-size: 11px; color: #606266; }
.group-summary { display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0; }
.group-chip { padding: 2px 8px; background: #ecf5ff; border-radius: 4px; font-size: 12px; }
.total-bar { margin-top: 8px; padding: 8px; background: #f5f7fa; font-size: 12px; }
</style>
