<template>
  <div class="f2-detail-sheet">
    <h3 class="sheet-title">{{ config.categoryLabel }}明细表 {{ config.sheetCode }}</h3>
    <details class="guidance-details"><summary>📋 编制提示</summary><p>区段Tab切换查看期初/增减/期末/库龄；期末=期初+增加-减少(自动计算)；库龄合计需=期末金额；3年以上有值行标记长期积压。</p></details>
    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="detail.addRow()">新增品名</el-button>
      <el-input
        v-model="detail.searchText.value"
        size="small"
        placeholder="搜索品名..."
        clearable
        style="width: 180px"
      />
      <CycleImportExportDropdown
        :wp-id="wpId"
        api-prefix="f2"
        :sheet="sheetCode"
        :disabled="isReadonly"
        @imported="onImported"
      />
      <span class="account-tag">科目 {{ config.accountCode }}</span>
    </div>

    <el-segmented v-model="detail.activeSegment" :options="segmentOptions" size="small" class="segment-bar" />

    <div v-if="detail.useVirtualScroll" class="virtual-toolbar">
      <el-alert type="info" :closable="false" class="virtual-hint">
        行数较多（{{ detail.filteredRows.value.length }} / {{ detail.rows.value.length }} 行）· {{ browseMode ? '虚拟滚动速览' : '表格编辑' }}模式
      </el-alert>
      <el-button size="small" @click="browseMode = !browseMode">
        {{ browseMode ? '切换表格编辑' : '切换虚拟速览' }}
      </el-button>
    </div>

    <el-table-v2
      v-if="detail.useVirtualScroll && browseMode"
      :columns="virtualColumns"
      :data="detail.filteredRows.value"
      :width="tableWidth"
      :height="560"
      :row-height="36"
      :header-height="40"
      :row-event-handlers="rowEventHandlers"
      fixed
      class="virtual-table"
    />

    <el-table
      v-else
      :data="detail.filteredRows.value"
      border
      size="small"
      :row-class-name="({ row }) => detail.isLongTermRow(row) ? 'long-term-row' : ''"
    >
      <el-table-column prop="itemName" label="品名" width="140" fixed />

      <template v-if="detail.activeSegment === 'opening'">
        <el-table-column v-if="config.hasQuantity" label="期初数量" min-width="110">
          <template #default="{ row }">
            <el-input-number v-model="row.openingQty" size="small" :controls="false" :disabled="isReadonly"
              @change="detail.updateRow(row.id, { openingQty: row.openingQty })" />
          </template>
        </el-table-column>
        <el-table-column label="期初金额" min-width="120">
          <template #default="{ row }">
            <el-input-number v-model="row.openingAmt" size="small" :controls="false" :disabled="isReadonly"
              @change="detail.updateRow(row.id, { openingAmt: row.openingAmt })" />
          </template>
        </el-table-column>
      </template>

      <template v-else-if="detail.activeSegment === 'movement'">
        <el-table-column v-if="config.hasQuantity" label="增加数量" min-width="110">
          <template #default="{ row }">
            <el-input-number v-model="row.increaseQty" size="small" :controls="false" :disabled="isReadonly"
              @change="detail.updateRow(row.id, { increaseQty: row.increaseQty })" />
          </template>
        </el-table-column>
        <el-table-column label="增加金额" min-width="120">
          <template #default="{ row }">
            <el-input-number v-model="row.increaseAmt" size="small" :controls="false" :disabled="isReadonly"
              @change="detail.updateRow(row.id, { increaseAmt: row.increaseAmt })" />
          </template>
        </el-table-column>
        <el-table-column v-if="config.hasQuantity" label="减少数量" min-width="110">
          <template #default="{ row }">
            <el-input-number v-model="row.decreaseQty" size="small" :controls="false" :disabled="isReadonly"
              @change="detail.updateRow(row.id, { decreaseQty: row.decreaseQty })" />
          </template>
        </el-table-column>
        <el-table-column label="减少金额" min-width="120">
          <template #default="{ row }">
            <el-input-number v-model="row.decreaseAmt" size="small" :controls="false" :disabled="isReadonly"
              @change="detail.updateRow(row.id, { decreaseAmt: row.decreaseAmt })" />
          </template>
        </el-table-column>
        <el-table-column v-if="config.extraColumnLabel" :label="config.extraColumnLabel" min-width="120">
          <template #default="{ row }">
            <el-input v-model="row.extra" size="small" :disabled="isReadonly"
              @change="detail.updateRow(row.id, { extra: row.extra })" />
          </template>
        </el-table-column>
      </template>

      <template v-else-if="detail.activeSegment === 'closing'">
        <el-table-column v-if="config.hasQuantity" label="期末数量" min-width="110">
          <template #default="{ row }">
            <el-tooltip content="公式：期初数量 + 增加 - 减少" placement="top">
              <span class="formula-cell">{{ row.closingQty.toLocaleString() }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="期末金额" min-width="120">
          <template #default="{ row }">
            <el-tooltip content="公式：期初金额 + 增加 - 减少" placement="top">
              <span class="formula-cell">{{ row.closingAmt.toLocaleString() }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="单价" min-width="100">
          <template #default="{ row }">
            <el-tooltip content="公式：金额 ÷ 数量" placement="top">
              <span v-if="row.unitPrice === ''" class="formula-cell">—</span>
              <span v-else class="formula-cell">{{ Number(row.unitPrice).toFixed(4) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </template>

      <template v-else>
        <el-table-column label="1年以内" min-width="110">
          <template #default="{ row }">
            <el-input-number v-model="row.agingLt1" size="small" :controls="false" :disabled="isReadonly"
              @change="detail.updateRow(row.id, { agingLt1: row.agingLt1 })" />
          </template>
        </el-table-column>
        <el-table-column label="1-2年" min-width="100">
          <template #default="{ row }">
            <el-input-number v-model="row.aging1to2" size="small" :controls="false" :disabled="isReadonly"
              @change="detail.updateRow(row.id, { aging1to2: row.aging1to2 })" />
          </template>
        </el-table-column>
        <el-table-column label="2-3年" min-width="100">
          <template #default="{ row }">
            <el-input-number v-model="row.aging2to3" size="small" :controls="false" :disabled="isReadonly"
              @change="detail.updateRow(row.id, { aging2to3: row.aging2to3 })" />
          </template>
        </el-table-column>
        <el-table-column label="3年以上" min-width="100">
          <template #default="{ row }">
            <el-input-number v-model="row.agingGt3" size="small" :controls="false" :disabled="isReadonly"
              @change="detail.updateRow(row.id, { agingGt3: row.agingGt3 })" />
          </template>
        </el-table-column>
        <el-table-column label="库龄合计" min-width="110">
          <template #default="{ row }">
            <el-tooltip content="公式：Σ(1年以内 + 1-2年 + 2-3年 + 3年以上)" placement="top">
              <span :class="['formula-cell', { 'aging-warn': Math.abs(row.agingTotal - row.closingAmt) > 0.01 }]">
                {{ row.agingTotal.toLocaleString() }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="期末金额" min-width="110">
          <template #default="{ row }">{{ row.closingAmt.toLocaleString() }}</template>
        </el-table-column>
      </template>

      <el-table-column label="操作" width="70" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" size="small" type="danger" link @click="detail.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="totals-row">
      <span>合计 — 期初: {{ detail.totals.openingAmt.toLocaleString() }}</span>
      <span>增加: {{ detail.totals.increaseAmt.toLocaleString() }}</span>
      <span>减少: {{ detail.totals.decreaseAmt.toLocaleString() }}</span>
      <span>期末: {{ detail.totals.closingAmt.toLocaleString() }}</span>
      <span v-if="detail.agingMismatch.length" class="aging-warn">
        {{ detail.agingMismatch.length }} 行库龄合计≠期末金额
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, toRef, ref, h, onMounted, onBeforeUnmount } from 'vue'
import { useF2DetailSheet } from '../../composables/useF2DetailSheet'
import { useVirtualTable, type VirtualColumn } from '@/composables/useVirtualTable'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'
import type { ChecklistResponse } from '../../composables/useF2FormData'
import type { F2DetailSheetConfig } from './f2DetailSheetConfigs'
import type { F2DetailRow } from '../../composables/useF2DetailSheet'

const props = defineProps<{
  config: F2DetailSheetConfig
  wpId: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const configRef = computed(() => props.config)
const sheetCode = computed(() => props.config.sheetCode)

const detail = useF2DetailSheet({
  config: configRef,
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)

async function onImported() {
  await reloadWorkpaperData?.()
}

const segmentOptions = [
  { label: '期初', value: 'opening' },
  { label: '增减', value: 'movement' },
  { label: '期末', value: 'closing' },
  { label: '库龄', value: 'aging' },
]

const browseMode = ref(true)
const tableWidth = ref(900)

function updateTableWidth() {
  tableWidth.value = Math.max(640, (document.querySelector('.f2-detail-sheet')?.clientWidth ?? 900) - 24)
}

onMounted(() => {
  updateTableWidth()
  window.addEventListener('resize', updateTableWidth)
})
onBeforeUnmount(() => window.removeEventListener('resize', updateTableWidth))

function fmtNum(v: unknown): string {
  const n = Number(v)
  return Number.isFinite(n) ? n.toLocaleString() : '—'
}

const virtualColumns = computed((): VirtualColumn[] => {
  const seg = detail.activeSegment.value
  const hq = props.config.hasQuantity
  const cols: VirtualColumn[] = [
    { key: 'itemName', dataKey: 'itemName', title: '品名', width: 140 },
  ]
  const numCol = (key: keyof F2DetailRow, title: string, w = 110): VirtualColumn => ({
    key: String(key),
    dataKey: String(key),
    title,
    width: w,
    align: 'right',
    cellRenderer: ({ cellData }) => h('span', {}, fmtNum(cellData)),
  })

  if (seg === 'opening') {
    if (hq) cols.push(numCol('openingQty', '期初数量'))
    cols.push(numCol('openingAmt', '期初金额', 120))
  } else if (seg === 'movement') {
    if (hq) cols.push(numCol('increaseQty', '增加数量'), numCol('decreaseQty', '减少数量'))
    cols.push(numCol('increaseAmt', '增加金额', 120), numCol('decreaseAmt', '减少金额', 120))
    if (props.config.extraColumnLabel) {
      cols.push({ key: 'extra', dataKey: 'extra', title: props.config.extraColumnLabel, width: 120 })
    }
  } else if (seg === 'closing') {
    if (hq) cols.push(numCol('closingQty', '期末数量'))
    cols.push(numCol('closingAmt', '期末金额', 120))
    cols.push({
      key: 'unitPrice',
      dataKey: 'unitPrice',
      title: '单价',
      width: 100,
      align: 'right',
      cellRenderer: ({ cellData }) => h('span', {}, cellData === '' ? '—' : Number(cellData).toFixed(4)),
    })
  } else {
    cols.push(
      numCol('agingLt1', '1年以内'),
      numCol('aging1to2', '1-2年', 100),
      numCol('aging2to3', '2-3年', 100),
      numCol('agingGt3', '3年以上', 100),
      numCol('agingTotal', '库龄合计', 110),
      numCol('closingAmt', '期末金额', 110),
    )
  }
  return cols
})

const { rowEventHandlers } = useVirtualTable({
  rows: computed(() => detail.filteredRows.value),
  columns: virtualColumns,
  width: tableWidth,
  height: 560,
  onRowDblclick: () => { browseMode.value = false },
})
</script>

<style scoped>
.f2-detail-sheet { padding: 12px; font-size: 13px; }
.sheet-title { margin: 0 0 12px; font-size: 15px; }
.toolbar { display: flex; gap: 12px; align-items: center; margin-bottom: 8px; }
.account-tag { font-size: 12px; color: #909399; }
.segment-bar { margin-bottom: 12px; }
.totals-row { display: flex; gap: 16px; margin-top: 12px; flex-wrap: wrap; font-size: 12px; }
.aging-warn { color: #e6a23c; font-weight: 600; }
.formula-cell { border-bottom: 1px dashed #c0c4cc; cursor: help; }
.virtual-hint { margin-bottom: 8px; flex: 1; }
.virtual-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.virtual-table { margin-bottom: 8px; }
.guidance-details { margin-bottom: 8px; font-size: 12px; color: #606266; }
:deep(.long-term-row) { background: #fdf6ec; }
</style>
