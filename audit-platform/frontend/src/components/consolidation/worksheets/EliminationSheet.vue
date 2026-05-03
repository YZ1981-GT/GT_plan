<template>
  <div ref="sheetRef" class="ws-sheet" :class="{ 'ws-sheet--fullscreen': isFullscreen }">
    <div class="ws-sheet-header">
      <h3>合并抵消分录明细表</h3>
      <div class="ws-sheet-actions">
        <el-tooltip :content="isFullscreen ? '退出全屏' : '全屏编辑'" placement="top">
          <el-button size="small" @click="isFullscreen = !isFullscreen">{{ isFullscreen ? '⬜ 退出全屏' : '⛶ 全屏' }}</el-button>
        </el-tooltip>
        <el-button size="small" @click="$emit('open-formula', 'consol_elimination')">ƒx 公式</el-button>
        <el-button size="small" @click="exportTemplate">📥 导出模板</el-button>
        <el-button size="small" @click="fileInputRef?.click()">📤 导入Excel</el-button>
        <el-button size="small" @click="$emit('save', { equity: equityRows, income: incomeRows, cross: crossRows })">💾 保存</el-button>
      </div>
    </div>
    <div class="ws-tip" v-show="!isFullscreen">
      <span>期末权益抵消 + 当期损益抵消 + 交叉持股抵消。合计列自动汇总各子企业金额。底部显示抵销后的少数股东权益和损益。导入时读取<b>"数据填写"</b>工作表。</span>
    </div>

    <!-- 1. 期末权益抵消 -->
    <div class="ws-section">
      <div class="ws-section-title">1. 期末权益抵消</div>
      <el-table :data="equityRows" border size="small" class="ws-table" :max-height="isFullscreen ? '400' : '350'"
        :header-cell-style="headerStyle" :cell-style="cellStyle">
        <el-table-column prop="direction" label="借贷方向" width="60" fixed align="center">
          <template #default="{ row }"><el-tag :type="row.direction === '借' ? 'danger' : 'success'" size="small" effect="plain">{{ row.direction }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="subject" label="项目" width="180" fixed show-overflow-tooltip />
        <el-table-column prop="detail" label="二级明细" width="120" show-overflow-tooltip />
        <el-table-column label="合计" width="120" align="right">
          <template #default="{ row }"><span :class="calcCls(sumValues(row))">{{ fmt(sumValues(row)) }}</span></template>
        </el-table-column>
        <el-table-column v-for="(c, ci) in companies" :key="'eq'+ci" align="right" min-width="120">
          <template #header><div style="text-align:center;line-height:1.3"><div style="font-weight:600">{{ c.name }}</div><div style="color:#4b2d77;font-size:10px">{{ c.ratio }}%</div></div></template>
          <template #default="{ row }"><el-input-number v-if="row.values" v-model="row.values[ci]" size="small" :precision="2" :controls="false" style="width:100%" /></template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 2. 当期损益抵消 -->
    <div class="ws-section">
      <div class="ws-section-title">2. 当期损益抵消</div>
      <el-table :data="incomeRows" border size="small" class="ws-table" :max-height="isFullscreen ? '400' : '350'"
        :header-cell-style="headerStyle" :cell-style="cellStyle">
        <el-table-column prop="direction" label="借贷方向" width="60" fixed align="center">
          <template #default="{ row }"><el-tag :type="row.direction === '借' ? 'danger' : 'success'" size="small" effect="plain">{{ row.direction }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="subject" label="项目" width="220" fixed show-overflow-tooltip />
        <el-table-column prop="detail" label="二级明细" width="160" show-overflow-tooltip />
        <el-table-column label="合计" width="120" align="right">
          <template #default="{ row }"><span :class="calcCls(sumValues(row))">{{ fmt(sumValues(row)) }}</span></template>
        </el-table-column>
        <el-table-column v-for="(c, ci) in companies" :key="'in'+ci" align="right" min-width="120">
          <template #header><div style="text-align:center;line-height:1.3"><div style="font-weight:600">{{ c.name }}</div><div style="color:#4b2d77;font-size:10px">{{ c.ratio }}%</div></div></template>
          <template #default="{ row }"><el-input-number v-if="row.values" v-model="row.values[ci]" size="small" :precision="2" :controls="false" style="width:100%" /></template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 3. 交叉持股 -->
    <div class="ws-section">
      <div class="ws-section-title">3. 交叉持股的权益和损益抵消</div>
      <el-table :data="crossRows" border size="small" class="ws-table" :header-cell-style="headerStyle" :cell-style="cellStyle">
        <el-table-column prop="direction" label="借贷方向" width="60" align="center">
          <template #default="{ row }"><el-tag :type="row.direction === '借' ? 'danger' : 'success'" size="small" effect="plain">{{ row.direction }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="subject" label="项目" width="180" />
        <el-table-column label="金额" width="120" align="right">
          <template #default="{ row }"><el-input-number v-model="row.total" size="small" :precision="2" :controls="false" style="width:100%" /></template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 汇总 -->
    <div class="ws-section">
      <div class="ws-section-title">抵销后汇总</div>
      <el-table :data="summaryRows" border size="small" class="ws-table" :header-cell-style="headerStyle" :cell-style="cellStyle">
        <el-table-column prop="label" label="项目" width="200" fixed />
        <el-table-column label="合计" width="120" align="right">
          <template #default="{ row }"><span class="ws-computed ws-bold">{{ fmt(row.total) }}</span></template>
        </el-table-column>
        <el-table-column v-for="(c, ci) in companies" :key="'sm'+ci" align="right" min-width="120">
          <template #header><div style="text-align:center;font-weight:600">{{ c.name }}</div></template>
          <template #default="{ row }"><span :class="calcCls(row.values?.[ci])">{{ fmt(row.values?.[ci]) }}</span></template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 4. 从内部抵消表自动导入的分录 -->
    <div class="ws-section" v-if="importedEntries.length">
      <div class="ws-section-title">4. 内部抵消分录（自动从往来/交易/现金流表导入）
        <el-tag size="small" type="info" style="margin-left:8px">{{ importedEntries.length }} 条</el-tag>
      </div>
      <el-table :data="importedEntries" border size="small" class="ws-table" max-height="250"
        :header-cell-style="headerStyle" :cell-style="cellStyle">
        <el-table-column prop="direction" label="借贷" width="50" align="center">
          <template #default="{ row }"><el-tag :type="row.direction === '借' ? 'danger' : 'success'" size="small" effect="plain">{{ row.direction }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="subject" label="科目" width="180" show-overflow-tooltip />
        <el-table-column prop="amount" label="金额" width="140" align="right">
          <template #default="{ row }"><span class="ws-computed">{{ fmt(row.amount) }}</span></template>
        </el-table-column>
        <el-table-column prop="source" label="来源" width="120">
          <template #default="{ row }"><el-tag size="small" type="info" effect="plain">{{ row.source }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="desc" label="说明" min-width="200" show-overflow-tooltip />
      </el-table>
    </div>

    <!-- 5. 用户自定义抵消分录 -->
    <div class="ws-section">
      <div class="ws-section-title">
        {{ importedEntries.length ? '5' : '4' }}. 自定义抵消分录
        <el-button size="small" type="primary" style="margin-left:12px" @click="addCustomEntry">+ 新增分录</el-button>
      </div>
      <el-table v-if="customEntries.length" :data="customEntries" border size="small" class="ws-table" max-height="300"
        :header-cell-style="headerStyle" :cell-style="cellStyle">
        <el-table-column label="借贷" width="70" align="center">
          <template #default="{ row }">
            <div @click.stop @mousedown.stop>
              <el-select v-model="row.direction" size="small" style="width:100%">
                <el-option label="借" value="借" /><el-option label="贷" value="贷" />
              </el-select>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="科目" width="160">
          <template #default="{ row }"><el-input v-model="row.subject" size="small" placeholder="科目名称" /></template>
        </el-table-column>
        <el-table-column label="二级明细" width="130">
          <template #default="{ row }"><el-input v-model="row.detail" size="small" placeholder="明细" /></template>
        </el-table-column>
        <el-table-column label="金额" width="140" align="right">
          <template #default="{ row }"><el-input-number v-model="row.amount" size="small" :precision="2" :controls="false" style="width:100%" /></template>
        </el-table-column>
        <el-table-column label="说明" min-width="180">
          <template #default="{ row }"><el-input v-model="row.desc" size="small" placeholder="抵消原因" /></template>
        </el-table-column>
        <el-table-column label="操作" width="60" align="center">
          <template #default="{ $index }"><el-button link type="danger" size="small" @click="customEntries.splice($index, 1)">删</el-button></template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="暂无自定义分录，点击上方按钮新增" :image-size="40" />
    </div>

    <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
    <el-dialog v-model="importVisible" title="导入抵消分录数据" width="600px" append-to-body>
      <el-alert type="warning" :closable="false" style="margin-bottom:12px">
        <template #title><span>按"借贷方向+项目+二级明细"匹配导入，读取<b>"数据填写"</b>工作表。</span></template>
      </el-alert>
      <p v-if="importCount > 0" style="font-size:13px;color:#666">匹配到 <b style="color:#4b2d77">{{ importCount }}</b> 行</p>
      <el-empty v-else description="未解析到有效数据" :image-size="60" />
      <template #footer>
        <el-button @click="importVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!importCount" @click="confirmImport">确认导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'

interface CompanyCol { name: string; code?: string; ratio: number }
interface ElimRow { direction: string; subject: string; detail?: string; total?: number | null; values?: (number | null)[]; isComputed?: boolean }

const props = defineProps<{ companies: CompanyCol[]; equityRows: ElimRow[]; incomeRows: ElimRow[]; crossRows: ElimRow[]; importedEntries?: any[] }>()
defineEmits<{
  (e: 'save', data: { equity: ElimRow[]; income: ElimRow[]; cross: ElimRow[] }): void
  (e: 'open-formula', sheetKey: string): void
}>()

const companies = computed(() => props.companies)
const equityRows = ref([...props.equityRows])
const incomeRows = ref([...props.incomeRows])
const crossRows = ref([...props.crossRows])
const isFullscreen = ref(false)
const sheetRef = ref<HTMLElement | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)
const importVisible = ref(false)
const importCount = ref(0)
const importMap = ref<Map<string, any>>(new Map())

// 从内部抵消表导入的分录（通过 props 传入）
const importedEntries = computed(() => props.importedEntries || [])

// 用户自定义分录
const customEntries = reactive<{ direction: string; subject: string; detail: string; amount: number|null; desc: string }[]>([])

function addCustomEntry() {
  customEntries.push({ direction: '借', subject: '', detail: '', amount: null, desc: '' })
}

watch(() => props.companies, () => {}, { deep: true })
watch(() => props.equityRows, (v) => { equityRows.value = [...v] }, { deep: true })
watch(() => props.incomeRows, (v) => { incomeRows.value = [...v] }, { deep: true })
watch(() => props.crossRows, (v) => { crossRows.value = [...v] }, { deep: true })

const n = (v: any) => Number(v) || 0
function sumValues(row: ElimRow): number {
  if (!row.values) return n(row.total)
  return row.values.reduce((s: number, v) => s + n(v), 0)
}
function fmt(v: any) { if (v == null) return '-'; const num = Number(v); return isNaN(num) ? '-' : num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
function calcCls(v: any) { return n(v) === 0 ? 'ws-computed ws-zero' : 'ws-computed' }

const summaryRows = computed(() => {
  const eq = equityRows.value.find((r: ElimRow) => r.subject === '少数股东权益')
  const inc = incomeRows.value.find((r: ElimRow) => r.subject === '少数股权损益')
  const eqVals = companies.value.map((_: any, ci: number) => eq?.values?.[ci] ?? null)
  const incVals = companies.value.map((_: any, ci: number) => inc?.values?.[ci] ?? null)
  return [
    { label: '抵销后的少数股东权益', total: eqVals.reduce((s: number, v) => s + n(v), 0), values: eqVals },
    { label: '抵销后的少数股东损益', total: incVals.reduce((s: number, v) => s + n(v), 0), values: incVals },
  ]
})

const headerStyle = { background: '#f0edf5', fontSize: '11px', color: '#333', padding: '3px 0' }
const cellStyle = { padding: '2px 4px', fontSize: '11px' }

// ─── 导出模板 ─────────────────────────────────────────────────────────────────
async function exportTemplate() {
  const XLSX = await import('xlsx'); const wb = XLSX.utils.book_new()
  const instr = [['合并抵消分录明细表 — 填写说明'],[],['⚠ 重要提示：'],
    ['1. 在"数据填写"工作表填写，不要修改sheet名称'],
    ['2. 按"借贷方向+项目+二级明细"匹配导入'],
    ['3. 合计列自动汇总，无需填写'],
    ['4. 各子企业列填写对应的抵消金额']]
  const wsI = XLSX.utils.aoa_to_sheet(instr); wsI['!cols']=[{wch:60}]
  XLSX.utils.book_append_sheet(wb, wsI, '填写说明')
  const allRows = [
    { section: '期末权益抵消', rows: equityRows.value },
    { section: '当期损益抵消', rows: incomeRows.value },
  ]
  const headers = ['分类','借贷方向','项目','二级明细',...companies.value.map(c => c.name)]
  const dataRows: any[][] = []
  for (const { section, rows } of allRows) {
    for (const r of rows) {
      dataRows.push([section, r.direction, r.subject, r.detail || '', ...(r.values || []).map(v => v ?? '')])
    }
  }
  const wsD = XLSX.utils.aoa_to_sheet([headers, ...dataRows])
  wsD['!cols'] = [{wch:14},{wch:8},{wch:22},{wch:18},...companies.value.map(()=>({wch:14}))]
  XLSX.utils.book_append_sheet(wb, wsD, '数据填写')
  XLSX.writeFile(wb, '合并抵消分录_模板.xlsx'); ElMessage.success('模板已导出')
}

async function onFileSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]; if (!file) return
  try {
    const XLSX = await import('xlsx'); const wb = XLSX.read(await file.arrayBuffer(), {type:'array'})
    const sn = wb.SheetNames.find(n => n === '数据填写') || wb.SheetNames[wb.SheetNames.length - 1]
    const json: any[][] = XLSX.utils.sheet_to_json(wb.Sheets[sn], {header:1})
    const parsed = new Map<string, any>()
    for (let i = 1; i < json.length; i++) {
      const r = json[i]; if (!r?.[2]) continue
      const key = `${String(r[1]).trim()}|${String(r[2]).trim()}|${String(r[3]||'').trim()}`
      parsed.set(key, r.slice(4))
    }
    importMap.value = parsed; importCount.value = parsed.size; importVisible.value = true
  } catch (err: any) { ElMessage.error('解析失败：' + (err.message || '')) }
  finally { if (fileInputRef.value) fileInputRef.value.value = '' }
}

function confirmImport() {
  let count = 0
  const applyToRows = (rows: ElimRow[]) => {
    for (const row of rows) {
      const key = `${row.direction}|${row.subject}|${row.detail || ''}`
      const vals = importMap.value.get(key)
      if (!vals || !row.values) continue
      for (let k = 0; k < row.values.length; k++) {
        if (vals[k] != null && vals[k] !== '') row.values[k] = Number(vals[k]) || null
      }
      count++
    }
  }
  applyToRows(equityRows.value)
  applyToRows(incomeRows.value)
  importVisible.value = false; ElMessage.success(`已导入 ${count} 行`); importMap.value = new Map()
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
.ws-tip b { color: #4b2d77; }
.ws-section { margin-bottom: 16px; }
.ws-section-title { font-size: 13px; font-weight: 600; color: #4b2d77; margin-bottom: 6px; padding: 6px 10px; background: #f8f6fb; border-radius: 4px; }
.ws-computed { color: #4b2d77; font-weight: 500; }
.ws-zero { color: #c0c4cc !important; font-weight: 400 !important; }
.ws-bold { font-weight: 700; }
.ws-table :deep(.el-input__inner) { text-align: right; font-size: 11px; }
</style>
