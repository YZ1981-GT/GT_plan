<template>
  <div class="f2-purchase-price">
    <h3 class="title">原材料采购价格分析 F2-61</h3>

    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="pp.addRow()">+ 新增材料</el-button>
      <F2SheetToolbar
        :wp-id="wpId"
        api-prefix="f2-spe"
        sheet="F2-61"
        :disabled="isReadonly"
        ai-section="price-analysis"
        :existing-content="pp.auditNote.value"
        review-section="F2-61-price"
        @ai-filled="(t: string) => { pp.auditNote.value = t }"
      />
      <el-input v-model="pp.searchQuery.value" size="small" placeholder="搜索材料名称/规格" clearable class="search" />
      <el-tag v-if="pp.abnormalCount.value > 0" type="warning" size="small">
        {{ pp.abnormalCount.value }} 行价格异常
      </el-tag>
      <span class="hint">共 {{ pp.filteredRows.value.length }} 行</span>
      <template v-if="useVirtualScroll">
        <el-button size="small" link @click="browseMode = !browseMode">
          {{ browseMode ? '切换表格编辑' : '切换虚拟速览' }}
        </el-button>
      </template>
    </div>

    <el-segmented v-model="pp.activeSegment.value" :options="segments" size="small" class="segment-bar" />

    <el-table-v2
      v-if="useVirtualScroll && browseMode && pp.activeSegment.value === 'summary'"
      :columns="virtualColumns"
      :data="virtualRows"
      :width="920"
      :height="480"
      :row-height="36"
      :header-height="40"
      fixed
      class="virtual-table"
    />

    <el-table
      v-else
      :data="pp.filteredRows.value"
      border
      size="small"
      height="480"
      :row-class-name="({ row }) => row.isAbnormal ? 'warn-row' : ''"
    >
      <el-table-column prop="materialName" label="材料名称" width="130" fixed />

      <template v-if="pp.activeSegment.value === 'basic'">
        <el-table-column label="规格" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.spec" size="small"
              @change="(v: string) => pp.updateRow(row.id, { spec: v })" />
            <span v-else>{{ row.spec }}</span>
          </template>
        </el-table-column>
        <el-table-column label="单位" width="80">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.unit" size="small"
              @change="(v: string) => pp.updateRow(row.id, { unit: v })" />
            <span v-else>{{ row.unit }}</span>
          </template>
        </el-table-column>
      </template>

      <template v-else-if="pp.activeSegment.value === 'h1' || pp.activeSegment.value === 'h2'">
        <el-table-column
          v-for="mi in halfMonths"
          :key="mi"
          :label="MONTH_LABELS[mi]"
          align="center"
        >
          <el-table-column label="金额" width="88">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.months[mi].amount"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number) => pp.updateMonth(row.id, mi, { amount: v ?? 0 })"
              />
            </template>
          </el-table-column>
          <el-table-column label="数量" width="80">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.months[mi].qty"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number) => pp.updateMonth(row.id, mi, { qty: v ?? 0 })"
              />
            </template>
          </el-table-column>
          <el-table-column label="单价" width="80" align="right">
            <template #default="{ row }">
              <span
                :class="{
                  formula: true,
                  'price-warn': row.enrichedMonths[mi].priceAbnormal,
                }"
              >
                {{ fmtPrice(row.enrichedMonths[mi].unitPrice) }}
              </span>
            </template>
          </el-table-column>
        </el-table-column>
      </template>

      <template v-else>
        <el-table-column label="年度总金额" width="110" align="right">
          <template #default="{ row }">{{ row.annualTotalAmount.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="年度总数量" width="110" align="right">
          <template #default="{ row }">{{ row.annualTotalQty.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="年度均价" width="100" align="right">
          <template #default="{ row }"><span class="formula">{{ row.annualAvgPrice.toFixed(4) }}</span></template>
        </el-table-column>
        <el-table-column label="上年均价" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.priorAvgPrice" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => pp.updateRow(row.id, { priorAvgPrice: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="变动率%" width="90" align="right">
          <template #default="{ row }">
            <span :class="{ 'price-warn': row.isAbnormal }">{{ row.changeRate.toFixed(1) }}%</span>
          </template>
        </el-table-column>
      </template>

      <el-table-column label="操作" width="55" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="pp.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <h4>审计说明</h4>
    <el-input v-model="pp.auditNote.value" type="textarea" :rows="3" :disabled="isReadonly" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, toRef, h } from 'vue'
import { ElTag } from 'element-plus'
import type { Column } from 'element-plus'
import { useF2PurchasePrice, MONTH_LABELS } from '../../composables/useF2PurchasePrice'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const segments = [
  { label: '材料基础', value: 'basic' },
  { label: '上半年1~6月', value: 'h1' },
  { label: '下半年7~12月', value: 'h2' },
  { label: '年度汇总', value: 'summary' },
]

const pp = useF2PurchasePrice({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const halfMonths = computed(() => {
  if (pp.activeSegment.value === 'h1') return [0, 1, 2, 3, 4, 5]
  if (pp.activeSegment.value === 'h2') return [6, 7, 8, 9, 10, 11]
  return []
})

const browseMode = ref(false)
const useVirtualScroll = computed(() => pp.filteredRows.value.length >= 50)

const virtualRows = computed(() =>
  pp.filteredRows.value.map((row) => ({
    id: row.id,
    materialName: row.materialName,
    annualAvgPrice: row.annualAvgPrice.toFixed(4),
    changeRate: `${row.changeRate.toFixed(1)}%`,
    isAbnormal: row.isAbnormal,
  })),
)

const virtualColumns = computed<Column[]>(() => [
  { key: 'materialName', dataKey: 'materialName', title: '材料名称', width: 160 },
  { key: 'annualAvgPrice', dataKey: 'annualAvgPrice', title: '年度均价', width: 120, align: 'right' },
  { key: 'changeRate', dataKey: 'changeRate', title: '变动率', width: 100, align: 'right',
    cellRenderer: ({ rowData }: { rowData: { changeRate: string; isAbnormal: boolean } }) =>
      h(ElTag, { type: rowData.isAbnormal ? 'warning' : 'info', size: 'small' }, () => rowData.changeRate),
  },
])

function fmtPrice(v: number | ''): string {
  if (v === '') return '—'
  return Number(v).toFixed(4)
}
</script>

<style scoped>
.f2-purchase-price { padding: 12px; font-size: 13px; }
.title { margin: 0 0 8px; }
.toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.search { width: 180px; }
.hint { font-size: 12px; color: #909399; }
.segment-bar { margin-bottom: 8px; }
.formula { text-decoration: underline dotted #909399; }
.price-warn { color: #e6a23c; font-weight: 600; background: #fdf6ec; padding: 0 4px; border-radius: 2px; }
:deep(.warn-row) { background: #fdf6ec; }
.virtual-table { margin-bottom: 8px; }
h4 { margin: 16px 0 8px; font-size: 13px; }
</style>
