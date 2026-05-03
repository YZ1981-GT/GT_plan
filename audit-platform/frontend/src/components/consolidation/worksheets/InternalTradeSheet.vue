<template>
  <div ref="sheetRef" class="ws-sheet" :class="{ 'ws-sheet--fullscreen': isFullscreen }">
    <div class="ws-sheet-header">
      <h3>内部交易抵消表</h3>
      <div class="ws-sheet-actions">
        <el-tooltip :content="isFullscreen ? '退出全屏' : '全屏编辑'" placement="top">
          <el-button size="small" @click="isFullscreen = !isFullscreen">{{ isFullscreen ? '⬜ 退出全屏' : '⛶ 全屏' }}</el-button>
        </el-tooltip>
        <el-button size="small" @click="exportTrade">📥 导出模板</el-button>
        <el-button size="small" @click="tradeFileRef?.click()">📤 导入Excel</el-button>
        <el-button size="small" type="primary" @click="addRow">+ 新增</el-button>
        <el-button size="small" type="danger" :disabled="!selectedRows.length" @click="batchDelete">
          删除{{ selectedRows.length ? `(${selectedRows.length})` : '' }}
        </el-button>
        <el-button size="small" @click="$emit('save', rows)">💾 保存</el-button>
      </div>
    </div>
    <div class="ws-tip" v-show="!isFullscreen">
      <span>内部交易抵消（利润表科目）。卖方收入 = 买方成本，差异需说明。存货中未实现内部利润需单独抵消。<b>导出模板后按格式填写，导入时追加到现有数据</b>，读取"数据填写"工作表。</span>
    </div>

    <el-table :data="rows" border size="small" class="ws-table"
      :max-height="isFullscreen ? 'calc(100vh - 100px)' : 'calc(100vh - 280px)'"
      :header-cell-style="headerStyle" :cell-style="cellStyle"
      show-summary :summary-method="getSummary"
      @selection-change="sel => selectedRows = sel">
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
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'

interface CompanyCol { name: string; code?: string; ratio: number }
interface TradeRow {
  sellerCompany: string; buyerCompany: string; tradeType: string
  sellerSubject: string; sellerAmount: number|null; buyerSubject: string; buyerAmount: number|null
  unrealizedProfit: number|null; inventoryRatio: number|null
}

const props = defineProps<{ companies: CompanyCol[] }>()
const emitTrade = defineEmits<{ (e: 'save', data: TradeRow[]): void; (e: 'entries-changed', entries: any[]): void }>()

const isFullscreen = ref(false)
const sheetRef = ref<HTMLElement|null>(null)
const selectedRows = ref<TradeRow[]>([])
const tradeFileRef = ref<HTMLInputElement|null>(null)
const n = (v: any) => Number(v) || 0

const allCompanyOptions = computed(() => [{ name: '母公司', code: 'parent' }, ...props.companies.map(c => ({ name: c.name, code: c.code || '' }))])
const tradeTypes = ['商品销售', '提供劳务', '资产转让', '资金往来', '管理费分摊', '其他']

const rows = reactive<TradeRow[]>([mkEmpty(), mkEmpty(), mkEmpty()])

function mkEmpty(): TradeRow {
  return { sellerCompany: '', buyerCompany: '', tradeType: '', sellerSubject: '', sellerAmount: null, buyerSubject: '', buyerAmount: null, unrealizedProfit: null, inventoryRatio: null }
}
function addRow() { rows.push(mkEmpty()) }
async function batchDelete() {
  if (!selectedRows.value.length) return
  try { await ElMessageBox.confirm(`确定删除 ${selectedRows.value.length} 条？`, '删除确认', { type: 'warning' })
    const del = new Set(selectedRows.value); const remaining = rows.filter(r => !del.has(r)); rows.length = 0; rows.push(...remaining); selectedRows.value = []
  } catch {}
}

const generatedEntries = computed(() => {
  const entries: any[] = []
  let totalRevenue = 0, totalCost = 0, totalUnrealized = 0
  for (const row of rows) {
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

function fmt(v: any) { if (v == null) return '-'; const num = Number(v); return isNaN(num) ? '-' : num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }

async function exportTrade() {
  const XLSX = await import('xlsx'); const wb = XLSX.utils.book_new()
  const headers = ['卖方','买方','交易类型','卖方科目','卖方金额','买方科目','买方金额','未实现利润','存货留存率%']
  const dataRows = rows.map(r => [r.sellerCompany,r.buyerCompany,r.tradeType,r.sellerSubject,r.sellerAmount??'',r.buyerSubject,r.buyerAmount??'',r.unrealizedProfit??'',r.inventoryRatio??''])
  const ws = XLSX.utils.aoa_to_sheet([headers,...dataRows]); ws['!cols']=headers.map(()=>({wch:14}))
  XLSX.utils.book_append_sheet(wb,ws,'数据填写'); XLSX.writeFile(wb,'内部交易抵消_模板.xlsx'); ElMessage.success('模板已导出')
}
async function onTradeFileSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]; if (!file) return
  try {
    const XLSX = await import('xlsx'); const wb = XLSX.read(await file.arrayBuffer(),{type:'array'})
    const sn = wb.SheetNames.find(n=>n==='数据填写')||wb.SheetNames[wb.SheetNames.length-1]
    const json: any[][] = XLSX.utils.sheet_to_json(wb.Sheets[sn],{header:1})
    let cnt=0; for(let i=1;i<json.length;i++){const r=json[i];if(!r?.[0])continue
      rows.push({sellerCompany:String(r[0]||''),buyerCompany:String(r[1]||''),tradeType:String(r[2]||''),
        sellerSubject:String(r[3]||''),sellerAmount:r[4]!=null?Number(r[4]):null,
        buyerSubject:String(r[5]||''),buyerAmount:r[6]!=null?Number(r[6]):null,
        unrealizedProfit:r[7]!=null?Number(r[7]):null,inventoryRatio:r[8]!=null?Number(r[8]):null}); cnt++}
    ElMessage.success(`已导入 ${cnt} 条`)
  } catch(err:any){ElMessage.error('解析失败：'+(err.message||''))}
  finally{if(tradeFileRef.value)tradeFileRef.value.value=''}
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
function onEsc(e: KeyboardEvent) { if (e.key === 'Escape' && isFullscreen.value) isFullscreen.value = false }
onMounted(() => document.addEventListener('keydown', onEsc))
onUnmounted(() => document.removeEventListener('keydown', onEsc))
</script>

<style scoped>
.ws-sheet { padding: 0; position: relative; }
.ws-sheet--fullscreen { position: fixed !important; top: 0; left: 0; right: 0; bottom: 0; z-index: 2000; background: #fff; padding: 16px; overflow: auto; }
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
