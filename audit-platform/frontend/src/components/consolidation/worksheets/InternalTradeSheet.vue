<template>
  <div class="ws-sheet">
    <GtEditableTable
      ref="editableTableRef"
      v-model="rows"
      :columns="columns"
      :editable="true"
      :show-selection="true"
      :lazy-edit="false"
      :show-toolbar="true"
      :show-selection-bar="false"
      :show-summary="true"
      :summary-method="getSummary"
      :max-height="'calc(100vh - 280px)'"
      :default-row="mkEmpty"
    >
      <!-- 工具栏左侧：标题 -->
      <template #toolbar-left>
        <h3 class="ws-sheet-title">内部交易抵消表</h3>
      </template>

      <!-- 工具栏右侧：导入导出+公式+保存 -->
      <template #toolbar-right>
        <el-button size="small" @click="$emit('open-formula', 'consol_internal_trade')">ƒx 公式</el-button>
        <el-button size="small" @click="exportTrade">📥 导出模板</el-button>
        <el-button size="small" @click="exportTradeData">📤 导出数据</el-button>
        <el-button size="small" @click="tradeFileRef?.click()">📤 导入Excel</el-button>
        <el-button size="small" @click="$emit('save', rows)">💾 保存</el-button>
      </template>

      <!-- 自定义列：卖方（下拉选择） -->
      <template #col-sellerCompany="{ row, editing }">
        <template v-if="editing">
          <div @click.stop @mousedown.stop>
            <el-select v-model="row.sellerCompany" size="small" style="width:100%" placeholder="卖方" filterable>
              <el-option v-for="c in allCompanyOptions" :key="c.code" :label="c.name" :value="c.name" />
            </el-select>
          </div>
        </template>
        <span v-else>{{ row.sellerCompany || '-' }}</span>
      </template>

      <!-- 自定义列：买方（下拉选择） -->
      <template #col-buyerCompany="{ row, editing }">
        <template v-if="editing">
          <div @click.stop @mousedown.stop>
            <el-select v-model="row.buyerCompany" size="small" style="width:100%" placeholder="买方" filterable>
              <el-option v-for="c in allCompanyOptions" :key="c.code" :label="c.name" :value="c.name" />
            </el-select>
          </div>
        </template>
        <span v-else>{{ row.buyerCompany || '-' }}</span>
      </template>

      <!-- 自定义列：交易类型（下拉选择） -->
      <template #col-tradeType="{ row, editing }">
        <template v-if="editing">
          <div @click.stop @mousedown.stop>
            <el-select v-model="row.tradeType" size="small" style="width:100%" placeholder="类型">
              <el-option v-for="t in tradeTypes" :key="t" :label="t" :value="t" />
            </el-select>
          </div>
        </template>
        <span v-else>{{ row.tradeType || '-' }}</span>
      </template>

      <!-- 自定义列：差异（计算列） -->
      <template #col-_diff="{ row }">
        <span :class="n(row.sellerAmount) - n(row.buyerAmount) !== 0 ? 'ws-diff-warn' : 'ws-computed'">
          {{ fmt(n(row.sellerAmount) - n(row.buyerAmount)) }}
        </span>
      </template>

      <!-- 自定义列：应抵消利润（计算列） -->
      <template #col-_eliminateProfit="{ row }">
        <span class="ws-computed">{{ fmt(n(row.unrealizedProfit) * n(row.inventoryRatio) / 100) }}</span>
      </template>

      <!-- 底部左侧 -->
      <template #footer-left>
        <div class="ws-tip">
          <span>📋 <b>内部交易抵消</b>（利润表科目）：卖方收入 = 买方成本，差异需说明。</span>
        </div>
      </template>
    </GtEditableTable>

    <input ref="tradeFileRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onTradeFileSelected" />

    <!-- 生成的抵消分录 -->
    <div class="ws-section" style="margin-top:16px">
      <div class="ws-section-title">自动生成的抵消分录</div>
      <el-table :data="generatedEntries" border size="small" class="ws-table" max-height="200"
        :header-cell-style="headerStyle" :cell-style="cellStyle">
        <el-table-column prop="direction" label="借贷" width="50" align="center">
          <template #default="{ row }">
            <el-tag :type="row.direction === '借' ? 'danger' : 'success'" size="small" effect="plain">{{ row.direction }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="subject" label="科目" width="160" />
        <el-table-column prop="amount" label="金额" width="140" align="right">
          <template #default="{ row }">
            <span class="ws-computed ws-bold">{{ fmt(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="desc" label="说明" min-width="200" show-overflow-tooltip />
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { useExcelIO, type ExcelColumn } from '@/composables/useExcelIO'
import GtEditableTable, { type GtColumn } from '@/components/common/GtEditableTable.vue'

interface CompanyCol { name: string; code?: string; ratio: number }
interface TradeRow {
  sellerCompany: string; buyerCompany: string; tradeType: string
  sellerSubject: string; sellerAmount: number|null; buyerSubject: string; buyerAmount: number|null
  unrealizedProfit: number|null; inventoryRatio: number|null
}

const props = defineProps<{ companies: CompanyCol[] }>()
const emitTrade = defineEmits<{
  (e: 'save', data: TradeRow[]): void
  (e: 'entries-changed', entries: any[]): void
  (e: 'open-formula', key: string): void
}>()

const displayPrefs = useDisplayPrefsStore()
const fmt = (v: any) => displayPrefs.fmt(v)
const n = (v: any) => Number(v) || 0
const tradeFileRef = ref<HTMLInputElement|null>(null)
const editableTableRef = ref<InstanceType<typeof GtEditableTable> | null>(null)

const allCompanyOptions = computed(() => [
  { name: '母公司', code: 'parent' },
  ...props.companies.map(c => ({ name: c.name, code: c.code || '' })),
])
const tradeTypes = ['商品销售', '提供劳务', '资产转让', '资金往来', '管理费分摊', '其他']

const rows = ref<TradeRow[]>([mkEmpty(), mkEmpty(), mkEmpty()])

function mkEmpty(): TradeRow {
  return {
    sellerCompany: '', buyerCompany: '', tradeType: '',
    sellerSubject: '', sellerAmount: null, buyerSubject: '', buyerAmount: null,
    unrealizedProfit: null, inventoryRatio: null,
  }
}

// ── 列配置（声明式） ──────────────────────────────────────────────────────────
const columns: GtColumn[] = [
  { prop: 'sellerCompany', label: '卖方', width: 130, fixed: 'left' },
  { prop: 'buyerCompany', label: '买方', width: 130 },
  { prop: 'tradeType', label: '交易类型', width: 110 },
  { prop: 'sellerSubject', label: '卖方科目', width: 120, editType: 'input' },
  { prop: 'sellerAmount', label: '卖方金额', width: 130, align: 'right', editType: 'number' },
  { prop: 'buyerSubject', label: '买方科目', width: 120, editType: 'input' },
  { prop: 'buyerAmount', label: '买方金额', width: 130, align: 'right', editType: 'number' },
  { prop: '_diff', label: '差异', width: 100, align: 'right', editable: false },
  { prop: 'unrealizedProfit', label: '未实现利润', width: 110, align: 'right', editType: 'number' },
  { prop: 'inventoryRatio', label: '存货留存率%', width: 100, align: 'right', editType: 'number' },
  { prop: '_eliminateProfit', label: '应抵消利润', width: 110, align: 'right', editable: false },
]

// ── 抵消分录自动生成 ──────────────────────────────────────────────────────────
const generatedEntries = computed(() => {
  const entries: any[] = []
  let totalRevenue = 0, totalCost = 0, totalUnrealized = 0
  for (const row of rows.value) {
    if (!row.sellerCompany || !row.buyerCompany) continue
    totalRevenue += n(row.sellerAmount); totalCost += n(row.buyerAmount)
    totalUnrealized += n(row.unrealizedProfit) * n(row.inventoryRatio) / 100
  }
  if (totalRevenue > 0 || totalCost > 0) {
    const amount = Math.min(totalRevenue, totalCost)
    entries.push({ direction: '借', subject: '营业收入', amount, desc: '内部交易收入抵消' })
    entries.push({ direction: '贷', subject: '营业成本', amount, desc: '内部交易成本抵消' })
  }
  if (totalUnrealized > 0) {
    entries.push({ direction: '借', subject: '营业成本', amount: totalUnrealized, desc: '未实现内部利润抵消' })
    entries.push({ direction: '贷', subject: '存货', amount: totalUnrealized, desc: '存货中未实现利润' })
  }
  return entries
})

watch(generatedEntries, (entries) => {
  emitTrade('entries-changed', entries.map(e => ({ ...e, source: '内部交易' })))
}, { immediate: true })

// ── Excel 导入导出 ────────────────────────────────────────────────────────────
const { exportTemplate: _exportTemplate, exportData: _exportData, onFileSelected: _onFileSelected } = useExcelIO()

const TRADE_COLS: ExcelColumn[] = [
  { key: 'sellerCompany', header: '卖方' }, { key: 'buyerCompany', header: '买方' },
  { key: 'tradeType', header: '交易类型' }, { key: 'sellerSubject', header: '卖方科目' },
  { key: 'sellerAmount', header: '卖方金额' }, { key: 'buyerSubject', header: '买方科目' },
  { key: 'buyerAmount', header: '买方金额' }, { key: 'unrealizedProfit', header: '未实现利润' },
  { key: 'inventoryRatio', header: '存货留存率%' },
]

async function exportTrade() {
  await _exportTemplate({
    columns: TRADE_COLS,
    fileName: '内部交易抵消_模板.xlsx',
    includeNoteRow: false,
    existingData: rows.value.map(r => [
      r.sellerCompany, r.buyerCompany, r.tradeType, r.sellerSubject,
      r.sellerAmount ?? '', r.buyerSubject, r.buyerAmount ?? '',
      r.unrealizedProfit ?? '', r.inventoryRatio ?? '',
    ]),
  })
}

async function exportTradeData() {
  await _exportData({
    data: rows.value.filter(r => r.sellerCompany || r.buyerCompany),
    columns: TRADE_COLS,
    sheetName: '内部交易抵消',
    fileName: '内部交易抵消_数据.xlsx',
    extraHeaders: ['差异', '应抵消利润'],
    extraDataFn: (r) => [
      n(r.sellerAmount) - n(r.buyerAmount),
      n(r.unrealizedProfit) * n(r.inventoryRatio) / 100,
    ],
  })
}

async function onTradeFileSelected(e: Event) {
  await _onFileSelected(e, (result) => {
    let cnt = 0
    for (const r of result.rows) {
      if (!r['卖方']) continue
      rows.value.push({
        sellerCompany: String(r['卖方'] || ''), buyerCompany: String(r['买方'] || ''),
        tradeType: String(r['交易类型'] || ''), sellerSubject: String(r['卖方科目'] || ''),
        sellerAmount: r['卖方金额'] != null ? Number(r['卖方金额']) : null,
        buyerSubject: String(r['买方科目'] || ''), buyerAmount: r['买方金额'] != null ? Number(r['买方金额']) : null,
        unrealizedProfit: r['未实现利润'] != null ? Number(r['未实现利润']) : null,
        inventoryRatio: r['存货留存率%'] != null ? Number(r['存货留存率%']) : null,
      })
      cnt++
    }
    ElMessage.success(`已导入 ${cnt} 条`)
  }, { skipRows: 1 })
}

// ── 合计行 ────────────────────────────────────────────────────────────────────
const headerStyle = { background: '#f0edf5', fontSize: '11px', color: '#333', padding: '3px 0' }
const cellStyle = { padding: '2px 4px', fontSize: '11px' }

function getSummary({ columns: cols, data }: any) {
  const sums: string[] = []
  const sumFields = new Set(['sellerAmount', 'buyerAmount', 'unrealizedProfit'])
  cols.forEach((col: any, idx: number) => {
    if (idx === 0) { sums[idx] = '合计'; return }
    const prop = col.property
    if (prop && sumFields.has(prop)) {
      sums[idx] = fmt(data.reduce((s: number, r: any) => s + n(r[prop]), 0))
    } else if (col.label === '差异') {
      sums[idx] = fmt(data.reduce((s: number, r: any) => s + (n(r.sellerAmount) - n(r.buyerAmount)), 0))
    } else if (col.label === '应抵消利润') {
      sums[idx] = fmt(data.reduce((s: number, r: any) => s + n(r.unrealizedProfit) * n(r.inventoryRatio) / 100, 0))
    } else {
      sums[idx] = ''
    }
  })
  return sums
}
</script>

<style scoped>
.ws-sheet { padding: 0; position: relative; }
.ws-sheet-title { margin: 0; font-size: 15px; color: #333; }
.ws-tip { font-size: 12px; color: #666; line-height: 1.5; }
.ws-section { margin-bottom: 16px; }
.ws-section-title { font-size: 13px; font-weight: 600; color: #4b2d77; margin-bottom: 6px; padding: 6px 10px; background: #f8f6fb; border-radius: 4px; }
.ws-computed { color: #4b2d77; font-weight: 500; }
.ws-bold { font-weight: 700; }
.ws-diff-warn { color: #e6a23c !important; font-weight: 700 !important; }
.ws-table :deep(.el-input__inner) { text-align: right; font-size: 11px; }
.ws-table :deep(.el-table__footer-wrapper td) { background: #f8f6fb !important; font-weight: 700; color: #4b2d77; }
</style>
