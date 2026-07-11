<template>
  <div class="g1-inventory">
    <div class="section-head">
      <h3 class="sheet-title">G1-4 证券结存表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="inv.addRow()">新增证券</el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-2" /></span>
        <el-tag size="small" type="info">共 {{ inv.rows.value.length }} 行</el-tag>
        <el-button size="small" @click="openReviewDialog('G1-4-conclusion')">💬复核</el-button>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实交易性金融资产各证券期末数量、成本与公允价值结存的准确与完整，确认未实现损益计算恰当，为明细表及审定表提供支撑。"
      class="objective-alert"
    />

    <el-segmented v-model="segment" :options="segmentOptions" size="small" class="segment-bar" />

    <el-table :data="inv.rows.value" border size="small" max-height="500">
      <el-table-column
        v-for="col in currentColumns"
        :key="String(col.prop)"
        :label="col.label"
        :width="col.width"
        :align="col.type === 'number' ? 'right' : 'left'"
        :class-name="col.formula ? 'auto-calc-col' : ''"
        :fixed="col.prop === 'securityName' ? 'left' : undefined"
      >
        <template #default="{ row, $index }">
          <span v-if="col.prop === 'seq'">{{ $index + 1 }}</span>
          <span v-else-if="col.formula" class="formula-cell" :title="formulaHint(col.prop)">
            {{ fmtNum(row[col.prop]) }}
          </span>
          <el-input-number
            v-else-if="col.type === 'number'"
            v-model="row[col.prop]"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width: 100%"
            @change="inv.updateRow(row.id, { [col.prop]: row[col.prop] })"
          />
          <el-input
            v-else
            v-model="row[col.prop]"
            size="small"
            :disabled="isReadonly"
            @change="inv.updateRow(row.id, { [col.prop]: row[col.prop] })"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" size="small" type="danger" link @click="inv.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 品种分组小计 + 总计 -->
    <div class="totals">
      <div v-for="g in inv.groups.value" :key="g.securityType" class="subtotal-line">
        <span class="subtotal-label">{{ g.securityType }}小计({{ g.rows.length }})</span>
        期末数量 {{ fmtNum(g.subtotal.closingQuantity) }} · 期末成本 {{ fmtNum(g.subtotal.closingCost) }} ·
        期末公允 {{ fmtNum(g.subtotal.closingFairValue) }} · 未实现损益 {{ fmtNum(g.subtotal.unrealizedGain) }}
      </div>
      <div class="grand-total">
        <span class="subtotal-label">总计</span>
        期末数量 {{ fmtNum(inv.grandTotal.value.closingQuantity) }} · 期末成本 {{ fmtNum(inv.grandTotal.value.closingCost) }} ·
        期末公允 {{ fmtNum(inv.grandTotal.value.closingFairValue) }} · 未实现损益 {{ fmtNum(inv.grandTotal.value.unrealizedGain) }}
      </div>
    </div>

    <el-card class="conclusion-card" shadow="never">
      <template #header>审计结论</template>
      <el-input v-model="inv.auditConclusion.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly" placeholder="对证券结存的复核结论..." />
    </el-card>

    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>期末数量 = 期初数量 + 增加数量 - 减少数量；期末成本 = 期初成本 + 增加成本 - 减少成本。</li>
        <li>未实现损益 = 期末公允 - 期末成本，系统自动计算。</li>
        <li>21列拆为2区段：基础+期初增减 / 期末+损益，切换 Tab 时行保持同步。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, computed, inject } from 'vue'
import { useG1Inventory, type G1InventoryRow } from '../../composables/useG1Inventory'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const inv = useG1Inventory({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const segment = ref<'basic' | 'closing'>('basic')
const segmentOptions = [
  { label: '基础+期初增减', value: 'basic' },
  { label: '期末+损益', value: 'closing' },
]

const currentColumns = computed(() =>
  segment.value === 'basic' ? inv.basicColumns : inv.closingColumns,
)

const FORMULA_HINTS: Partial<Record<keyof G1InventoryRow, string>> = {
  closingQuantity: '期末数量 = 期初数量 + 增加数量 - 减少数量',
  closingCost: '期末成本 = 期初成本 + 增加成本 - 减少成本',
  unrealizedGain: '未实现损益 = 期末公允 - 期末成本',
}

function formulaHint(prop: keyof G1InventoryRow): string {
  return FORMULA_HINTS[prop] ?? ''
}

function fmtNum(v: unknown): string {
  return typeof v === 'number' ? v.toLocaleString() : String(v ?? '')
}
</script>

<style scoped>
.g1-inventory { padding: 12px; font-size: 13px; }
.g1-inventory :deep(.el-table) { --el-table-font-size: 13px; font-size: 13px; }
.g1-inventory :deep(.el-table .cell) { font-size: 13px; }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.objective-alert { margin-bottom: 12px; }
.segment-bar { margin-bottom: 12px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
:deep(.auto-calc-col) { background-color: #f5f7fa; }
.totals { margin-top: 12px; font-size: 12px; color: #606266; }
.subtotal-line { padding: 2px 0; }
.subtotal-label { font-weight: 600; margin-right: 8px; }
.grand-total { margin-top: 6px; padding-top: 6px; border-top: 1px solid #dcdfe6; font-weight: 600; color: #303133; }
.conclusion-card { margin-top: 12px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
</style>
