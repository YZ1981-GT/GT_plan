<template>
  <div ref="sheetRef" class="ws-sheet" :class="{ 'gt-fullscreen': isFullscreen }">
    <div class="ws-sheet-header">
      <h3>内部现金流抵消表</h3>
      <div class="ws-sheet-actions">
        <el-tooltip :content="isFullscreen ? '退出全屏' : '全屏编辑'" placement="top">
          <el-button size="small" @click="toggleFullscreen">{{ isFullscreen ? '⬜ 退出全屏' : '⛶ 全屏' }}</el-button>
        </el-tooltip>
        <el-button size="small" @click="$emit('open-formula', 'consol_internal_cashflow')">ƒx 公式</el-button>
        <el-button size="small" @click="exportCf">📥 导出模板</el-button>
        <el-button size="small" @click="exportCfData">📤 导出数据</el-button>
        <el-button size="small" @click="cfFileRef?.click()">📤 导入Excel</el-button>
        <el-button size="small" type="primary" @click="_addRow">+ 新增</el-button>
        <el-button size="small" type="danger" :disabled="!selectedRows.length" @click="batchDelete">
          删除{{ selectedRows.length ? `(${selectedRows.length})` : '' }}
        </el-button>
        <el-button size="small" @click="$emit('save', rows)">💾 保存</el-button>
      </div>
    </div>
    <div class="ws-tip" v-show="!isFullscreen">
      <span>📋 <b>内部现金流抵消</b>（现金流量表项目）：A的"购买商品支付的现金"中对B的部分 = B的"销售商品收到的现金"中对A的部分。
        付款方和收款方的现金流项目需配对填写，差异需核查。底部自动生成抵消分录，汇总到合并抵消分录表。
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
      <el-table-column prop="payerCompany" label="付款方" width="130" fixed>
        <template #default="{ row }">
          <div @click.stop @mousedown.stop>
            <el-select v-model="row.payerCompany" size="small" style="width:100%" placeholder="付款方" filterable>
              <el-option v-for="c in allCompanyOptions" :key="c.code" :label="c.name" :value="c.name" />
            </el-select>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="receiverCompany" label="收款方" width="130">
        <template #default="{ row }">
          <div @click.stop @mousedown.stop>
            <el-select v-model="row.receiverCompany" size="small" style="width:100%" placeholder="收款方" filterable>
              <el-option v-for="c in allCompanyOptions" :key="c.code" :label="c.name" :value="c.name" />
            </el-select>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="payerItem" label="付款方现金流项目" width="180">
        <template #default="{ row }">
          <div @click.stop @mousedown.stop>
            <el-select v-model="row.payerItem" size="small" style="width:100%" placeholder="选择项目" filterable allow-create>
              <el-option v-for="i in cashFlowItems" :key="i" :label="i" :value="i" />
            </el-select>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="payerAmount" label="付款方金额" width="130" align="right">
        <template #default="{ row }"><el-input-number v-model="row.payerAmount" size="small" :precision="2" :controls="false" style="width:100%" /></template>
      </el-table-column>
      <el-table-column prop="receiverItem" label="收款方现金流项目" width="180">
        <template #default="{ row }">
          <div @click.stop @mousedown.stop>
            <el-select v-model="row.receiverItem" size="small" style="width:100%" placeholder="选择项目" filterable allow-create>
              <el-option v-for="i in cashFlowItems" :key="i" :label="i" :value="i" />
            </el-select>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="receiverAmount" label="收款方金额" width="130" align="right">
        <template #default="{ row }"><el-input-number v-model="row.receiverAmount" size="small" :precision="2" :controls="false" style="width:100%" /></template>
      </el-table-column>
      <el-table-column label="差异" width="100" align="right">
        <template #default="{ row }">
          <span :class="n(row.payerAmount) - n(row.receiverAmount) !== 0 ? 'ws-diff-warn' : 'ws-computed'">
            {{ fmt(n(row.payerAmount) - n(row.receiverAmount)) }}
          </span>
        </template>
      </el-table-column>
    </el-table>

    <input ref="cfFileRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onCfFileSelected" />

    <div class="ws-section" style="margin-top:16px">
      <div class="ws-section-title">自动生成的现金流抵消分录</div>
      <el-table :data="generatedEntries" border size="small" class="ws-table" max-height="200"
        :header-cell-style="headerStyle" :cell-style="cellStyle">
        <el-table-column prop="direction" label="借贷" width="50" align="center">
          <template #default="{ row }"><el-tag :type="row.direction === '借' ? 'danger' : 'success'" size="small" effect="plain">{{ row.direction }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="subject" label="现金流项目" width="200" />
        <el-table-column prop="amount" label="金额" width="140" align="right">
          <template #default="{ row }"><span class="ws-computed ws-bold">{{ fmt(row.amount) }}</span></template>
        </el-table-column>
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
interface CashFlowRow { payerCompany: string; receiverCompany: string; payerItem: string; payerAmount: number|null; receiverItem: string; receiverAmount: number|null }

const props = defineProps<{ companies: CompanyCol[] }>()
const emitCf = defineEmits<{ (e: 'save', data: CashFlowRow[]): void; (e: 'entries-changed', entries: any[]): void; (e: 'open-formula', key: string): void }>()

const { isFullscreen, toggleFullscreen } = useFullscreen()
const displayPrefs = useDisplayPrefsStore()
const fmt = (v: any) => displayPrefs.fmt(v)
const sheetRef = ref<HTMLElement|null>(null)
const cfFileRef = ref<HTMLInputElement|null>(null)
const n = (v: any) => Number(v) || 0

const allCompanyOptions = computed(() => [{ name: '母公司', code: 'parent' }, ...props.companies.map(c => ({ name: c.name, code: c.code || '' }))])
const cashFlowItems = [
  '销售商品、提供劳务收到的现金', '购买商品、接受劳务支付的现金',
  '收到的其他与经营活动有关的现金', '支付的其他与经营活动有关的现金',
  '收回投资收到的现金', '投资支付的现金',
  '取得借款收到的现金', '偿还债务支付的现金',
  '分配股利、利润或偿付利息支付的现金', '收到的其他与筹资活动有关的现金',
]

const rows = ref<CashFlowRow[]>([mkEmpty(), mkEmpty()])
function mkEmpty(): CashFlowRow { return { payerCompany: '', receiverCompany: '', payerItem: '', payerAmount: null, receiverItem: '', receiverAmount: null } }

const {
  selectedRows,
  onSelectionChange,
  addRow,
  deleteSelectedRows: batchDelete,
} = useTableToolbar(rows)

function _addRow() { addRow(mkEmpty) }

const generatedEntries = computed(() => {
  const map = new Map<string, number>()
  for (const row of rows.value) {
    if (!row.payerItem || !row.receiverItem) continue
    const amount = Math.min(n(row.payerAmount), n(row.receiverAmount))
    if (amount <= 0) continue
    map.set(row.payerItem, (map.get(row.payerItem) || 0) + amount)
    map.set(row.receiverItem, (map.get(row.receiverItem) || 0) + amount)
  }
  const entries: any[] = []
  const processed = new Set<string>()
  for (const row of rows.value) {
    if (!row.payerItem || !row.receiverItem) continue
    const key = `${row.payerItem}|${row.receiverItem}`
    if (processed.has(key)) continue; processed.add(key)
    const amount = Math.min(n(row.payerAmount), n(row.receiverAmount))
    if (amount > 0) {
      entries.push({ direction: '借', subject: row.receiverItem, amount })
      entries.push({ direction: '贷', subject: row.payerItem, amount })
    }
  }
  return entries
})

watch(generatedEntries, (entries) => {
  emitCf('entries-changed', entries.map(e => ({ ...e, source: '内部现金流' })))
}, { immediate: true })


const { exportTemplate: _exportTemplate, exportData: _exportData, onFileSelected: _onFileSelected } = useExcelIO()

const CF_COLS: ExcelColumn[] = [
  { key: 'payerCompany', header: '付款方', width: 22 },
  { key: 'receiverCompany', header: '收款方', width: 22 },
  { key: 'payerItem', header: '付款方现金流项目', width: 22 },
  { key: 'payerAmount', header: '付款方金额', width: 22 },
  { key: 'receiverItem', header: '收款方现金流项目', width: 22 },
  { key: 'receiverAmount', header: '收款方金额', width: 22 },
]

async function exportCf() {
  await _exportTemplate({
    columns: CF_COLS,
    fileName: '内部现金流抵消_模板.xlsx',
    includeNoteRow: false,
    existingData: rows.value.map(r => [r.payerCompany, r.receiverCompany, r.payerItem, r.payerAmount ?? '', r.receiverItem, r.receiverAmount ?? '']),
  })
}
async function exportCfData() {
  await _exportData({
    data: rows.value.filter(r => r.payerCompany || r.receiverCompany),
    columns: CF_COLS,
    sheetName: '内部现金流抵消',
    fileName: '内部现金流抵消_数据.xlsx',
    extraHeaders: ['差异'],
    extraDataFn: (r) => [n(r.payerAmount) - n(r.receiverAmount)],
  })
}
async function onCfFileSelected(e: Event) {
  await _onFileSelected(e, (result) => {
    let cnt = 0
    for (const r of result.rows) {
      if (!r['付款方']) continue
      rows.value.push({
        payerCompany: String(r['付款方'] || ''), receiverCompany: String(r['收款方'] || ''),
        payerItem: String(r['付款方现金流项目'] || ''), payerAmount: r['付款方金额'] != null ? Number(r['付款方金额']) : null,
        receiverItem: String(r['收款方现金流项目'] || ''), receiverAmount: r['收款方金额'] != null ? Number(r['收款方金额']) : null,
      })
      cnt++
    }
    ElMessage.success(`已导入 ${cnt} 条`)
  }, { skipRows: 1 })
}
const headerStyle = { background: '#f0edf5', fontSize: '11px', color: '#333', padding: '3px 0' }
const cellStyle = { padding: '2px 4px', fontSize: '11px' }
function getSummary({ columns, data }: any) {
  const sums: string[] = []; const sumFields = new Set(['payerAmount','receiverAmount'])
  columns.forEach((col: any, idx: number) => {
    if (idx <= 1) { sums[idx] = ''; return }; if (idx === 2) { sums[idx] = '合计'; return }
    const prop = col.property
    if (prop && sumFields.has(prop)) { sums[idx] = fmt(data.reduce((s: number, r: any) => s + n(r[prop]), 0)) }
    else if (col.label === '差异') { sums[idx] = fmt(data.reduce((s: number, r: any) => s + (n(r.payerAmount) - n(r.receiverAmount)), 0)) }
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
