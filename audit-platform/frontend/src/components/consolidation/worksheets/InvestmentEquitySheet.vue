<template>
  <div ref="sheetRef" class="ws-sheet" :class="{ 'ws-sheet--fullscreen': isFullscreen }">
    <div class="ws-sheet-header">
      <h3>投资明细-权益法</h3>
      <div class="ws-sheet-actions">
        <el-tooltip :content="isFullscreen ? '退出全屏' : '全屏编辑'" placement="top">
          <el-button size="small" @click="isFullscreen = !isFullscreen">{{ isFullscreen ? '⬜ 退出全屏' : '⛶ 全屏' }}</el-button>
        </el-tooltip>
        <el-button size="small" @click="$emit('open-formula', 'consol_equity_inv')">ƒx 公式</el-button>
        <el-button size="small" @click="exportTemplate">📥 导出模板</el-button>
        <el-button size="small" @click="fileInputRef?.click()">📤 导入Excel</el-button>
        <el-button size="small" type="primary" @click="addRow">+ 新增</el-button>
        <el-button size="small" type="danger" :disabled="!selectedRows.length" @click="batchDelete">
          删除{{ selectedRows.length ? `(${selectedRows.length})` : '' }}
        </el-button>
        <el-button size="small" @click="$emit('save', rows)">💾 保存</el-button>
      </div>
    </div>
    <div class="ws-tip" v-show="!isFullscreen">
      <span>按权益法核算的长期股权投资。权益增加小计、期末投资比例和长投金额自动计算。导入时自动读取<b>"数据填写"</b>工作表，请勿修改sheet名称。</span>
    </div>

    <el-table :data="tableData" border size="small" class="ws-table"
      :max-height="isFullscreen ? 'calc(100vh - 80px)' : 'calc(100vh - 300px)'"
      :header-cell-style="headerStyle" :cell-style="rowCellStyle"
      :row-class-name="rowClassName" @selection-change="onSelChange">
      <el-table-column type="selection" width="36" fixed align="center" :selectable="(row: any) => !row._isSummary" />
      <el-table-column label="序号" width="50" fixed align="center" class-name="ws-col-index">
        <template #default="{ row, $index }">{{ row._isSummary ? '' : $index + 1 }}</template>
      </el-table-column>
      <el-table-column prop="company_name" label="被投资单位名称" min-width="140" fixed>
        <template #default="{ row }">
          <span v-if="row._isSummary" class="ws-summary-label">小计</span>
          <el-input v-else v-model="row.company_name" size="small" />
        </template>
      </el-table-column>
      <el-table-column prop="company_code" label="企业代码" width="90">
        <template #default="{ row }">
          <template v-if="!row._isSummary"><el-input v-model="row.company_code" size="small" /></template>
        </template>
      </el-table-column>
      <!-- 期初余额 -->
      <el-table-column label="期初余额" align="center">
        <el-table-column prop="open_ratio" label="投资比例" width="80" align="right">
          <template #default="{ row }"><el-input-number v-model="row.open_ratio" size="small" :precision="2" :controls="false" style="width:100%" /></template>
        </el-table-column>
        <el-table-column prop="open_amount" label="长投金额" width="110" align="right">
          <template #default="{ row }"><el-input-number v-model="row.open_amount" size="small" :precision="2" :controls="false" style="width:100%" /></template>
        </el-table-column>
        <el-table-column prop="open_impairment" label="减值准备" width="100" align="right">
          <template #default="{ row }"><el-input-number v-model="row.open_impairment" size="small" :precision="2" :controls="false" style="width:100%" /></template>
        </el-table-column>
      </el-table-column>
      <!-- 本期增加 -->
      <el-table-column label="本期增加" align="center">
        <el-table-column prop="add_ratio" label="投资比例" width="80" align="right">
          <template #default="{ row }"><el-input-number v-model="row.add_ratio" size="small" :precision="2" :controls="false" style="width:100%" /></template>
        </el-table-column>
        <el-table-column prop="add_cost" label="投资成本增加" width="110" align="right">
          <template #default="{ row }"><el-input-number v-model="row.add_cost" size="small" :precision="2" :controls="false" style="width:100%" /></template>
        </el-table-column>
        <el-table-column label="权益增加" align="center">
          <el-table-column prop="add_income_adj" label="损益调整" width="100" align="right">
            <template #default="{ row }"><el-input-number v-model="row.add_income_adj" size="small" :precision="2" :controls="false" style="width:100%" /></template>
          </el-table-column>
          <el-table-column prop="add_oci" label="其他综合收益" width="100" align="right">
            <template #default="{ row }"><el-input-number v-model="row.add_oci" size="small" :precision="2" :controls="false" style="width:100%" /></template>
          </el-table-column>
          <el-table-column prop="add_other_equity" label="其他权益变动" width="100" align="right">
            <template #default="{ row }"><el-input-number v-model="row.add_other_equity" size="small" :precision="2" :controls="false" style="width:100%" /></template>
          </el-table-column>
          <el-table-column label="权益增加小计" width="100" align="right">
            <template #default="{ row }"><span :class="calcCls(n(row.add_income_adj)+n(row.add_oci)+n(row.add_other_equity))">{{ fmt(n(row.add_income_adj)+n(row.add_oci)+n(row.add_other_equity)) }}</span></template>
          </el-table-column>
        </el-table-column>
        <el-table-column prop="add_other" label="其他" width="90" align="right">
          <template #default="{ row }"><el-input-number v-model="row.add_other" size="small" :precision="2" :controls="false" style="width:100%" /></template>
        </el-table-column>
        <el-table-column prop="add_impairment" label="减值准备" width="100" align="right">
          <template #default="{ row }"><el-input-number v-model="row.add_impairment" size="small" :precision="2" :controls="false" style="width:100%" /></template>
        </el-table-column>
      </el-table-column>
      <!-- 本期减少 -->
      <el-table-column label="本期减少" align="center">
        <el-table-column prop="reduce_ratio" label="投资比例" width="80" align="right">
          <template #default="{ row }"><el-input-number v-model="row.reduce_ratio" size="small" :precision="2" :controls="false" style="width:100%" /></template>
        </el-table-column>
        <el-table-column prop="reduce_cost" label="投资成本减少" width="110" align="right">
          <template #default="{ row }"><el-input-number v-model="row.reduce_cost" size="small" :precision="2" :controls="false" style="width:100%" /></template>
        </el-table-column>
        <el-table-column prop="reduce_dividend" label="本期分回利润" width="110" align="right">
          <template #default="{ row }"><el-input-number v-model="row.reduce_dividend" size="small" :precision="2" :controls="false" style="width:100%" /></template>
        </el-table-column>
        <el-table-column prop="reduce_other" label="其他" width="90" align="right">
          <template #default="{ row }"><el-input-number v-model="row.reduce_other" size="small" :precision="2" :controls="false" style="width:100%" /></template>
        </el-table-column>
        <el-table-column prop="reduce_impairment" label="减值准备" width="100" align="right">
          <template #default="{ row }"><el-input-number v-model="row.reduce_impairment" size="small" :precision="2" :controls="false" style="width:100%" /></template>
        </el-table-column>
      </el-table-column>
      <!-- 期末余额（自动计算） -->
      <el-table-column label="期末余额" align="center">
        <el-table-column label="投资比例" width="80" align="right">
          <template #default="{ row }"><span :class="calcCls(n(row.open_ratio)+n(row.add_ratio)-n(row.reduce_ratio))">{{ fmtR(n(row.open_ratio)+n(row.add_ratio)-n(row.reduce_ratio)) }}</span></template>
        </el-table-column>
        <el-table-column label="长投金额" width="110" align="right">
          <template #default="{ row }"><span :class="[calcCls(calcEnd(row)), 'ws-bold']">{{ fmt(calcEnd(row)) }}</span></template>
        </el-table-column>
        <el-table-column label="减值准备" width="100" align="right">
          <template #default="{ row }"><span :class="calcCls(n(row.open_impairment)+n(row.add_impairment)-n(row.reduce_impairment))">{{ fmt(n(row.open_impairment)+n(row.add_impairment)-n(row.reduce_impairment)) }}</span></template>
        </el-table-column>
      </el-table-column>
    </el-table>

    <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
    <el-dialog v-model="importVisible" title="导入Excel数据" width="600px" append-to-body>
      <el-alert type="warning" :closable="false" style="margin-bottom:12px">
        <template #title><span>请使用"导出模板"填写。系统自动读取<b>"数据填写"</b>工作表，请勿修改sheet名称。导入将<b>追加</b>到现有数据。</span></template>
      </el-alert>
      <el-table v-if="importPreview.length" :data="importPreview.slice(0,5)" border size="small" max-height="250">
        <el-table-column prop="company_name" label="被投资单位" min-width="140" />
        <el-table-column prop="open_amount" label="期初长投金额" width="120" />
        <el-table-column prop="add_cost" label="增加投资成本" width="120" />
      </el-table>
      <p v-if="importPreview.length" style="font-size:12px;color:#999;margin-top:8px">共 {{ importPreview.length }} 条</p>
      <el-empty v-else description="未解析到有效数据" :image-size="60" />
      <template #footer>
        <el-button @click="importVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!importPreview.length" @click="confirmImport">确认导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'

interface Row {
  company_name: string; company_code: string
  open_ratio: number|null; open_amount: number|null; open_impairment: number|null
  add_ratio: number|null; add_cost: number|null; add_income_adj: number|null; add_oci: number|null; add_other_equity: number|null; add_other: number|null; add_impairment: number|null
  reduce_ratio: number|null; reduce_cost: number|null; reduce_dividend: number|null; reduce_other: number|null; reduce_impairment: number|null
}

const props = defineProps<{ modelValue: Row[] }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: Row[]): void; (e: 'save', v: Row[]): void; (e: 'open-formula', sheetKey: string): void }>()

const rows = ref<Row[]>([...props.modelValue])
let internalUpdate = false
watch(() => props.modelValue, (v) => { if (!internalUpdate) rows.value = v }, { deep: true })
watch(rows, (v) => { internalUpdate = true; emit('update:modelValue', v); nextTick(() => { internalUpdate = false }) }, { deep: true })

const selectedRows = ref<Row[]>([])
const isFullscreen = ref(false)
const sheetRef = ref<HTMLElement|null>(null)
const fileInputRef = ref<HTMLInputElement|null>(null)
const importVisible = ref(false)
const importPreview = ref<Row[]>([])

function mkEmpty(): Row {
  return { company_name:'',company_code:'',open_ratio:null,open_amount:null,open_impairment:null,
    add_ratio:null,add_cost:null,add_income_adj:null,add_oci:null,add_other_equity:null,add_other:null,add_impairment:null,
    reduce_ratio:null,reduce_cost:null,reduce_dividend:null,reduce_other:null,reduce_impairment:null }
}
function addRow() { rows.value.push(mkEmpty()) }

async function batchDelete() {
  if (!selectedRows.value.length) return
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selectedRows.value.length} 条？`, '删除确认', { type: 'warning' })
    const del = new Set(selectedRows.value); rows.value = rows.value.filter(r => !del.has(r)); selectedRows.value = []
  } catch {}
}

const n = (v: any) => Number(v) || 0
const calcEnd = (r: Row) => n(r.open_amount)+n(r.add_cost)+n(r.add_income_adj)+n(r.add_oci)+n(r.add_other_equity)+n(r.add_other)-n(r.reduce_cost)-n(r.reduce_dividend)-n(r.reduce_other)
function fmt(v: number) { if (v == null) return '-'; return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
function fmtR(v: number) { return v ? `${v.toFixed(2)}%` : '--' }
function calcCls(v: number) { return v === 0 ? 'ws-computed ws-zero' : 'ws-computed' }

const headerStyle = { background: '#f0edf5', fontSize: '12px', color: '#333', padding: '2px 0' }

// ─── 小计行 ───────────────────────────────────────────────────────────────────
const NUM_FIELDS: (keyof Row)[] = ['open_ratio','open_amount','open_impairment',
  'add_ratio','add_cost','add_income_adj','add_oci','add_other_equity','add_other','add_impairment',
  'reduce_ratio','reduce_cost','reduce_dividend','reduce_other','reduce_impairment']

const summaryRow = reactive<any>({
  _isSummary: true, company_name: '小计', company_code: '',
  open_ratio: 0, open_amount: 0, open_impairment: 0,
  add_ratio: 0, add_cost: 0, add_income_adj: 0, add_oci: 0, add_other_equity: 0, add_other: 0, add_impairment: 0,
  reduce_ratio: 0, reduce_cost: 0, reduce_dividend: 0, reduce_other: 0, reduce_impairment: 0,
})
const overriddenFields = reactive<Set<string>>(new Set())

watch(rows, () => {
  for (const f of NUM_FIELDS) {
    if (!overriddenFields.has(f)) {
      summaryRow[f] = rows.value.reduce((s: number, r: any) => s + n(r[f]), 0)
    }
  }
}, { deep: true, immediate: true })

const tableData = computed(() => [...rows.value, summaryRow])

function onSelChange(sel: any[]) { selectedRows.value = sel.filter((r: any) => !r._isSummary) }
function rowClassName({ row }: any) { return row._isSummary ? 'ws-row-summary' : '' }
function rowCellStyle({ row }: any) {
  const base: any = { padding: '2px 4px', fontSize: '12px' }
  if (row._isSummary) { base.background = '#f8f6fb'; base.fontWeight = '700'; base.color = '#4b2d77' }
  return base
}

// ─── 导出模板 ─────────────────────────────────────────────────────────────────
const COLS = [
  {key:'company_name',header:'被投资单位名称',note:'必填'},{key:'company_code',header:'企业代码',note:'必填'},
  {key:'open_ratio',header:'期初-投资比例',note:'%'},{key:'open_amount',header:'期初-长投金额',note:'金额'},{key:'open_impairment',header:'期初-减值准备',note:'金额'},
  {key:'add_ratio',header:'增加-投资比例',note:'%'},{key:'add_cost',header:'增加-投资成本',note:'金额'},
  {key:'add_income_adj',header:'增加-损益调整',note:'金额'},{key:'add_oci',header:'增加-其他综合收益',note:'金额'},{key:'add_other_equity',header:'增加-其他权益变动',note:'金额'},
  {key:'add_other',header:'增加-其他',note:'金额'},{key:'add_impairment',header:'增加-减值准备',note:'金额'},
  {key:'reduce_ratio',header:'减少-投资比例',note:'%'},{key:'reduce_cost',header:'减少-投资成本',note:'金额'},
  {key:'reduce_dividend',header:'减少-分回利润',note:'金额'},{key:'reduce_other',header:'减少-其他',note:'金额'},{key:'reduce_impairment',header:'减少-减值准备',note:'金额'},
]

async function exportTemplate() {
  const XLSX = await import('xlsx'); const wb = XLSX.utils.book_new()
  const instrRows = [['投资明细-权益法 — 填写说明'],[],['⚠ 重要提示：'],
    ['1. 在"数据填写"工作表填写，不要修改sheet名称和表头'],['2. 第1行分类，第2行说明，第3行表头，第4行起为数据'],
    ['3. 金额填数字，比例填数字（51表示51%）'],['4. 权益增加小计和期末金额由系统自动计算，无需填写'],
    ['5. 示例行导入时自动跳过'],[],['字段说明：'],['列号','字段名','说明']]
  COLS.forEach((c,i) => instrRows.push([String(i+1),c.header,c.note]))
  const wsI = XLSX.utils.aoa_to_sheet(instrRows); wsI['!cols']=[{wch:6},{wch:22},{wch:40}]; wsI['!merges']=[{s:{r:0,c:0},e:{r:0,c:2}}]
  XLSX.utils.book_append_sheet(wb, wsI, '填写说明')
  const catRow = ['基本信息','','期初余额','','','本期增加','','','','','','','本期减少','','','','']
  const noteRow = COLS.map(c=>c.note); const hdrRow = COLS.map(c=>c.header)
  const existing = rows.value.filter(r=>r.company_name).map(r=>COLS.map(c=>(r as any)[c.key]??''))
  const dataRows = existing.length ? [catRow,noteRow,hdrRow,...existing] : [catRow,noteRow,hdrRow,
    ['示例公司A','A001',51,5000000,100000,'','','','','','','','','','','',''],
    ['示例公司B','B002',30,3000000,'','',500000,200000,50000,30000,'','','','','','','']]
  const wsD = XLSX.utils.aoa_to_sheet(dataRows); wsD['!cols']=COLS.map(c=>({wch:Math.max(c.header.length*2.5,12)}))
  wsD['!merges']=[{s:{r:0,c:0},e:{r:0,c:1}},{s:{r:0,c:2},e:{r:0,c:4}},{s:{r:0,c:5},e:{r:0,c:11}},{s:{r:0,c:12},e:{r:0,c:16}}]
  XLSX.utils.book_append_sheet(wb, wsD, '数据填写')
  XLSX.writeFile(wb, '投资明细_权益法_模板.xlsx'); ElMessage.success('模板已导出')
}

async function onFileSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]; if (!file) return
  try {
    const XLSX = await import('xlsx'); const wb = XLSX.read(await file.arrayBuffer(), {type:'array'})
    const sn = wb.SheetNames.find(n=>n==='数据填写')||wb.SheetNames[wb.SheetNames.length-1]
    const json: any[][] = XLSX.utils.sheet_to_json(wb.Sheets[sn], {header:1})
    const parsed: Row[] = []
    for (let i=3;i<json.length;i++) {
      const r=json[i]; if(!r?.[0]||String(r[0]).startsWith('示例')) continue
      const p = (idx: number) => r[idx]!=null&&r[idx]!=='' ? Number(r[idx]) : null
      parsed.push({ company_name:String(r[0]||''),company_code:String(r[1]||''),
        open_ratio:p(2),open_amount:p(3),open_impairment:p(4),
        add_ratio:p(5),add_cost:p(6),add_income_adj:p(7),add_oci:p(8),add_other_equity:p(9),add_other:p(10),add_impairment:p(11),
        reduce_ratio:p(12),reduce_cost:p(13),reduce_dividend:p(14),reduce_other:p(15),reduce_impairment:p(16) })
    }
    importPreview.value = parsed; importVisible.value = true
  } catch(err:any) { ElMessage.error('解析失败：'+(err.message||'格式错误')) }
  finally { if(fileInputRef.value) fileInputRef.value.value='' }
}

function confirmImport() {
  const nonEmpty = rows.value.filter(r=>r.company_name)
  rows.value = [...nonEmpty,...importPreview.value]; importVisible.value = false
  ElMessage.success(`已导入 ${importPreview.value.length} 条`); importPreview.value = []
}

function onEsc(e: KeyboardEvent) { if(e.key==='Escape'&&isFullscreen.value) isFullscreen.value=false }
onMounted(()=>document.addEventListener('keydown',onEsc))
onUnmounted(()=>document.removeEventListener('keydown',onEsc))
</script>

<style scoped>
.ws-sheet { padding: 0; position: relative; }
.ws-sheet--fullscreen { position: fixed !important; top: 0; left: 0; right: 0; bottom: 0; z-index: 2000; background: #fff; padding: 16px; overflow: auto; }
.ws-sheet-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.ws-sheet-header h3 { margin: 0; font-size: 15px; color: #333; }
.ws-sheet-actions { display: flex; gap: 8px; }
.ws-tip { display: flex; align-items: flex-start; gap: 6px; padding: 6px 10px; margin-bottom: 10px; background: #f4f4f5; border-radius: 6px; font-size: 12px; color: #666; line-height: 1.5; }
.ws-tip b { color: #4b2d77; }
.ws-computed { color: #4b2d77; font-weight: 500; }
.ws-zero { color: #c0c4cc !important; font-weight: 400 !important; }
.ws-bold { font-weight: 700; }
.ws-table :deep(.el-input__inner) { text-align: right; }
.ws-table :deep(.el-table__body .ws-col-index .cell) { white-space: nowrap; }
.ws-table :deep(.ws-row-summary td) { background: #f8f6fb !important; font-weight: 700; color: #4b2d77; }
.ws-summary-label { font-weight: 700; color: #4b2d77; font-size: 13px; }
</style>
