<template>
  <div ref="sheetRef" class="ws-sheet" :class="{ 'gt-fullscreen': isFullscreen }">
    <div class="ws-sheet-header">
      <h3>内部交易抵消表</h3>
      <div class="ws-sheet-actions">
        <el-tooltip :content="isFullscreen ? '退出全屏' : '全屏编辑'" placement="top">
          <el-button size="small" @click="toggleFullscreen">{{ isFullscreen ? '⬜ 退出全屏' : '⛶ 全屏' }}</el-button>
        </el-tooltip>
        <el-button size="small" @click="$emit('open-formula', 'consol_internal_trade')">ƒx 公式</el-button>
        <el-button size="small" @click="exportTrade">📥 导出模板</el-button>
        <el-button size="small" @click="exportTradeData">📤 导出数据</el-button>
        <el-button size="small" @click="tradeFileRef?.click()">📤 导入Excel</el-button>
        <el-button size="small" type="primary" @click="_addRow">+ 新增</el-button>
        <el-button size="small" type="danger" :disabled="!selectedRows.length" @click="batchDelete">
          删除{{ selectedRows.length ? `(${selectedRows.length})` : '' }}
        </el-button>
        <el-button size="small" @click="$emit('save', rows)">💾 保存</el-button>
      </div>
    </div>
    <div class="ws-tip" v-show="!isFullscreen">
      <span>📋 <b>内部交易抵消</b>（利润表科目）：卖方收入 = 买方成本，差异需说明。存货中未实现内部利润需单独抵消（应抵消利润=未实现利润×存货留存率）。
        底部自动生成抵消分录（收入成本抵消+未实现利润抵消），汇总到合并抵消分录表。
        支持<b>导出模板→填写→导入</b>，读取"数据填写"工作表。</span>
    </div>

    <el-table :data="rows" border size="small" class="ws-table"
      :style="{ fontSize: displayPrefs.fontConfig.tableFont }"
      :max-height="isFullscreen ? 'calc(100vh - 100px)' : 'calc(100vh - 280px)'"
      :header-cell-style="headerStyle" :cell-style="cellStyle"
      show-summary :summary-method="getSummary"
      @selection-change="onSelectionChange">
      <el-table-column type="selection" width="36" fixed align="center" />
      <el-table-column type="index" label="序号" width="50" fixed align="center" class-name="ws-col-index" />
      <el-table-column prop="sellerCompany" label="卖方" width="130" fixed>
        <template #default="{ row }">
          <div @click.stop @mousedown.stop>
            <el-select v-model="row.sellerCompany" size="small" style="width:100%" placeholder="卖方" filterable>
              <el-option v-for="c in allCompanyOptions" :key="c.code" :label="c.name" :value="c.name" />
            </el-select>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="buyerCompany" label="买方" width="130">
        <template #default="{ row }">
          <div @click.stop @mousedown.stop>
            <el-select v-model="row.buyerCompany" size="small" style="width:100%" placeholder="买方" filterable>
              <el-option v-for="c in allCompanyOptions" :key="c.code" :label="c.name" :value="c.name" />
            </el-select>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="tradeType" label="交易类型" width="110">
        <template #default="{ row }">
          <div @click.stop @mousedown.stop>
            <el-select v-model="row.tradeType" size="small" style="width:100%" placeholder="类型">
              <el-option v-for="t in tradeTypes" :key="t" :label="t" :value="t" />
            </el-select>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="sellerSubject" label="卖方科目" width="120">
        <template #default="{ row }"><el-input v-model="row.sellerSubject" size="small" placeholder="如营业收入" /></template>
      </el-table-column>
      <el-table-column prop="sellerAmount" label="卖方金额" width="130" align="right">
        <template #default="{ row }"><el-input-number v-model="row.sellerAmount" size="small" :precision="2" :controls="false" style="width:100%" /></template>
      </el-table-column>
      <el-table-column prop="buyerSubject" label="买方科目" width="120">
        <template #default="{ row }"><el-input v-model="row.buyerSubject" size="small" placeholder="如营业成本" /></template>
      </el-table-column>
      <el-table-column prop="buyerAmount" label="买方金额" width="130" align="right">
        <template #default="{ row }"><el-input-number v-model="row.buyerAmount" size="small" :precision="2" :controls="false" style="width:100%" /></template>
      </el-table-column>
      <el-table-column label="差异" width="100" align="right">
        <template #default="{ row }">
          <span :class="n(row.sellerAmount) - n(row.buyerAmount) !== 0 ? 'ws-diff-warn' : 'ws-computed'">
            {{ fmt(n(row.sellerAmount) - n(row.buyerAmount)) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="unrealizedProfit" label="未实现利润" width="110" align="right">
        <template #default="{ row }"><el-input-number v-model="row.unrealizedProfit" size="small" :precision="2" :controls="false" style="width:100%" /></template>
      </el-table-column>
      <el-table-column prop="inventoryRatio" label="存货留存率%" width="100" align="right">
        <template #default="{ row }"><el-input-number v-model="row.inventoryRatio" size="small" :precision="2" :controls="false" style="width:100%" /></template>
      </el-table-column>
      <el-table-column label="应抵消利润" width="110" align="right">
        <template #default="{ row }"><span class="ws-computed">{{ fmt(n(row.unrealizedProfit) * n(row.inventoryRatio) / 100) }}</span></template>
      </el-table-column>
    </el-table>

    <input ref="tradeFileRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onTradeFileSelected" />

    <!-- 生成的抵消分录 -->
    <div class="ws-section" style="margin-top:16px">
      <div class="ws-section-title">自动生成的抵消分录</div>
      <el-table :data="generatedEntries" border size="small" class="ws-table" max-height="200"
        :header-cell-style="headerStyle" :cell-style="cellStyle">
        <el-table-column prop="direction" label="借贷" width="50" align="center">
          <template #default="{ row }"><el-tag :type="row.direction === '借' ? 'danger' : 'success'" size="small" effect="plain">{{ row.direction }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="subject" label="科目" width="160" />
        <el-table-column prop="amount" label="金额" width="140" align="right">
          <template #default="{ row }"><span class="ws-computed ws-bold">{{ fmt(row.amount) }}</span></template>
        </el-table-column>
        <el-table-column prop="desc" label="说明" min-width="200" show-overflow-tooltip />
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useFullscreen } from '@/composables/useFullscreen'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { useExcelIO, type ExcelColumn } from '@/composables/useExcelIO'
import { useTableToolbar } from '@/composables/useTableToolbar'

interface CompanyCol { name: string; code?: string; ratio: number }
interface TradeRow {
  sellerCompany: string; buyerCompany: string; tradeType: string
  sellerSubject: string; sellerAmount: number|null; buyerSubject: string; buyerAmount: number|null
  unrealizedProfit: number|null; inventoryRatio: number|null
}

const props = defineProps<{ companies: CompanyCol[] }>()
const emitTrade = defineEmits<{ (e: 'save', data: TradeRow[]): void; (e: 'entries-changed', entries: any[]): void; (e: 'open-formula', key: string): void }>()

const { isFullscreen, toggleFullscreen } = useFullscreen()
const displayPrefs = useDisplayPrefsStore()
const fmt = (v: any) => displayPrefs.fmt(v)
const sheetRef = ref<HTMLElement|null>(null)
const tradeFileRef = ref<HTMLInputElement|null>(null)
const n = (v: any) => Number(v) || 0

const allCompanyOptions = computed(() => [{ name: '母公司', code: 'parent' }, ...props.companies.map(c => ({ name: c.name, code: c.code || '' }))])
const tradeTypes = ['商品销售', '提供劳务', '资产转让', '资金往来', '管理费分摊', '其他']

const rows = ref<TradeRow[]>([mkEmpty(), mkEmpty(), mkEmpty()])

function mkEmpty(): TradeRow {
  return { sellerCompany: '', buyerCompany: '', tradeType: '', sellerSubject: '', sellerAmount: null, buyerSubject: '', buyerAmount: null, unrealizedProfit: null, inventoryRatio: null }
}

const {
  selectedRows,
  onSelectionChange,
  addRow,
  deleteSelectedRows: batchDelete,
} = useTableToolbar(rows)

function _addRow() { addRow(mkEmpty) }

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
    existingData: rows.value.map(r => [r.sellerCompany, r.buyerCompany, r.tradeType, r.sellerSubject, r.sellerAmount ?? '', r.buyerSubject, r.buyerAmount ?? '', r.unrealizedProfit ?? '', r.inventoryRatio ?? '']),
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
const headerStyle = { background: '#f0edf5', fontSize: '11px', color: '#333', padding: '3px 0' }
const cellStyle = { padding: '2px 4px', fontSize: '11px' }
function getSummary({ columns, data }: any) {
  const sums: string[] = []; const sumFields = new Set(['sellerAmount','buyerAmount','unrealizedProfit'])
  columns.forEach((col: any, idx: number) => {
    if (idx <= 1) { sums[idx] = ''; return }; if (idx === 2) { sums[idx] = '合计'; return }
    const prop = col.property
    if (prop && sumFields.has(prop)) { sums[idx] = fmt(data.reduce((s: number, r: any) => s + n(r[prop]), 0)) }
    else if (col.label === '差异') { sums[idx] = fmt(data.reduce((s: number, r: any) => s + (n(r.sellerAmount) - n(r.buyerAmount)), 0)) }
    else if (col.label === '应抵消利润') { sums[idx] = fmt(data.reduce((s: number, r: any) => s + n(r.unrealizedProfit) * n(r.inventoryRatio) / 100, 0)) }
    else { sums[idx] = '' }
  }); return sums
}

</script>

<style scoped>
.ws-sheet { padding: 0; position: relative; }
.ws-sheet-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.ws-sheet-header h3 { margin: 0; font-size: 15px; color: #333; }
.ws-sheet-actions { display: flex; gap: 8px; }
.ws-tip { display: flex; align-items: flex-start; gap: 6px; padding: 6px 10px; margin-bottom: 10px; background: #f4f4f5; border-radius: 6px; font-size: 12px; color: #666; line-height: 1.5; }
.ws-section { margin-bottom: 16px; }
.ws-section-title { font-size: 13px; font-weight: 600; color: #4b2d77; margin-bottom: 6px; padding: 6px 10px; background: #f8f6fb; border-radius: 4px; }
.ws-computed { color: #4b2d77; font-weight: 500; }
.ws-bold { font-weight: 700; }
.ws-diff-warn { color: #e6a23c !important; font-weight: 700 !important; }
.ws-table :deep(.el-input__inner) { text-align: right; font-size: 11px; }
.ws-table :deep(.el-table__body .ws-col-index .cell) { white-space: nowrap; }
.ws-table :deep(.el-table__footer-wrapper td) { background: #f8f6fb !important; font-weight: 700; color: #4b2d77; }
</style>
