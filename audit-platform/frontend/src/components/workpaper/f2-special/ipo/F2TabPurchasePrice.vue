<template>
  <div class="f2-purchase-price">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表按月分析原材料采购单价，识别 IPO 期间采购价格异常波动及可能的成本操纵。</p>
        <p>2. 灰底列为自动计算列（月度单价、年度总额/总量/均价、变动率），不可手动编辑。</p>
        <p>3. 单价异常（标黄）或年度均价变动率超阈值（标黄行）须结合市场行情与供应商访谈说明原因。</p>
        <p>4. 分"材料基础 / 上半年 / 下半年 / 年度汇总"四段查看，减少横向滚动。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>审计目标：分析原材料采购价格的合理性与波动趋势，识别异常定价，验证采购成本的真实性。</template>
    </el-alert>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="pp.addRow()">+ 新增材料</el-button>
        <el-input v-model="pp.searchQuery.value" size="small" placeholder="搜索材料名称/规格" clearable class="search" />
        <el-tag v-if="pp.abnormalCount.value > 0" type="warning" size="small">
          {{ pp.abnormalCount.value }} 行价格异常
        </el-tag>
        <template v-if="useVirtualScroll">
          <el-button size="small" link @click="browseMode = !browseMode">
            {{ browseMode ? '切换表格编辑' : '切换虚拟速览' }}
          </el-button>
        </template>
      </div>
      <div class="toolbar-right">
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
        <GtIndexChip value="wp:F2-61" />
        <el-tag size="small" type="info">共 {{ pp.filteredRows.value.length }} 行</el-tag>
      </div>
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
          <el-table-column label="单价" width="80" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <el-tooltip content="月度单价 = 当月金额 / 当月数量" placement="top">
                <span
                  :class="{
                    formula: true,
                    'price-warn': row.enrichedMonths[mi].priceAbnormal,
                  }"
                >
                  {{ fmtPrice(row.enrichedMonths[mi].unitPrice) }}
                </span>
              </el-tooltip>
            </template>
          </el-table-column>
        </el-table-column>
      </template>

      <template v-else>
        <el-table-column label="年度总金额" width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <el-tooltip content="年度总金额 = 各月采购金额合计" placement="top">
              <span class="formula">{{ row.annualTotalAmount.toLocaleString() }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="年度总数量" width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <el-tooltip content="年度总数量 = 各月采购数量合计" placement="top">
              <span class="formula">{{ row.annualTotalQty.toLocaleString() }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="年度均价" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <el-tooltip content="年度均价 = 年度总金额 / 年度总数量" placement="top">
              <span class="formula">{{ row.annualAvgPrice.toFixed(4) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="上年均价" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.priorAvgPrice" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => pp.updateRow(row.id, { priorAvgPrice: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="变动率%" width="90" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <el-tooltip content="变动率 =（年度均价 − 上年均价）/ 上年均价" placement="top">
              <span class="formula" :class="{ 'price-warn': row.isAbnormal }">{{ row.changeRate.toFixed(1) }}%</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </template>

      <el-table-column label="操作" width="55" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="pp.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计说明 -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明</span>
        </div>
      </template>
      <el-input v-model="pp.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请说明采购价格波动分析结果、异常定价原因及与市场行情/供应商访谈的印证情况……" :disabled="isReadonly" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="audit-card-header"><span>审计结论</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditConclusionText"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在以下重大未调整事项（或审计范围受到限制），不可确认。"
        @change="saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, toRef, h } from 'vue'
import { ElTag } from 'element-plus'
import type { Column } from 'element-plus'
import { useF2PurchasePrice, MONTH_LABELS } from '../../composables/useF2PurchasePrice'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'
import GtIndexChip from '../../GtIndexChip.vue'

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

// ─── 审计结论（逐 sheet 打磨补齐，持久化走 f2-spe:save-items）──────────────────
const CONCLUSION_KEY = 'F2-61-audit-conclusion'
const auditConclusionText = ref('')
function persistSpeAudit(key: string, val: string): void {
  const item = { item_id: key, conclusion: null, remark: val }
  props.allResponses.set(key, item)
  window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items: [item] } }))
}
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusionText.value = val
  persistSpeAudit(CONCLUSION_KEY, val)
}
onMounted(() => {
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusionText.value = c.remark
})
</script>

<style scoped>
.f2-purchase-price { padding: 12px; font-size: var(--wp-font-size, 13px); }
.f2-purchase-price :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f2-purchase-price :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.search { width: 180px; }
.segment-bar { margin-bottom: 8px; }
.formula { text-decoration: underline dotted #909399; cursor: help; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.price-warn { color: #e6a23c; font-weight: 600; background: #fdf6ec; padding: 0 4px; border-radius: 2px; }
:deep(.warn-row) { background: #fdf6ec; }
.virtual-table { margin-bottom: 8px; }
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.audit-note-card { margin-top: 16px; border-radius: 8px; }
.audit-note-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.audit-card-header { font-weight: 600; font-size: 14px; color: #303133; }
</style>
