<template>
  <div ref="sheetRef" class="ws-sheet" :class="{ 'ws-sheet--fullscreen': isFullscreen }">
    <div class="ws-sheet-header">
      <h3>净资产表</h3>
      <div class="ws-sheet-actions">
        <el-tooltip :content="isFullscreen ? '退出全屏' : '全屏编辑'" placement="top">
          <el-button size="small" @click="isFullscreen = !isFullscreen">{{ isFullscreen ? '⬜ 退出全屏' : '⛶ 全屏' }}</el-button>
        </el-tooltip>
        <el-button size="small" @click="$emit('open-formula', 'consol_net_asset')">ƒx 公式</el-button>
        <el-button size="small" @click="exportTemplate">📥 导出模板</el-button>
        <el-button size="small" @click="fileInputRef?.click()">📤 导入Excel</el-button>
        <el-button size="small" type="primary" @click="addRow">+ 新增行</el-button>
        <el-button size="small" type="danger" :disabled="!selectedRows.length" @click="batchDelete">
          删除{{ selectedRows.length ? `(${selectedRows.length})` : '' }}
        </el-button>
        <el-button size="small" @click="$emit('save', tableData)">💾 保存</el-button>
      </div>
    </div>
    <div class="ws-tip" v-show="!isFullscreen">
      <span>子企业列根据合并范围树形结构动态生成（当前层级的直接下级）。包含三部分：所有者权益变动 → 利润及利润分配 → 资本公积变动。紫色数值为自动计算，合计列自动汇总。</span>
    </div>

    <el-table :data="tableData" border size="small" class="ws-table"
      :max-height="isFullscreen ? 'calc(100vh - 80px)' : 'calc(100vh - 280px)'"
      :header-cell-style="headerStyle" :cell-style="rowCellStyle"
      :row-class-name="rowClassName" :span-method="spanMethod"
      @selection-change="sel => selectedRows = sel">
      <el-table-column type="selection" width="36" fixed align="center" />
      <!-- 序号 -->
      <el-table-column prop="seq" label="序号" width="50" fixed align="center" class-name="ws-col-index" />
      <!-- 项目 -->
      <el-table-column prop="item" label="项目" width="220" fixed show-overflow-tooltip>
        <template #default="{ row }">
          <span :style="{ paddingLeft: (row.indent || 0) * 12 + 'px', fontWeight: row.bold ? 700 : 400 }">
            {{ row.item }}
          </span>
        </template>
      </el-table-column>
      <!-- 合计 -->
      <el-table-column prop="total" label="合计" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!row.isHeader" v-model="row.total" size="small" :precision="2" :controls="false"
            style="width:100%" :class="{ 'ws-auto-cell': row.isComputed }" />
        </template>
      </el-table-column>
      <!-- 母公司 -->
      <el-table-column prop="parent" label="母公司" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!row.isHeader" v-model="row.parent" size="small" :precision="2" :controls="false"
            style="width:100%" :class="{ 'ws-auto-cell': row.isComputed }" />
        </template>
      </el-table-column>
      <!-- 动态子企业列（合并范围直接下级） -->
      <el-table-column v-for="(comp, ci) in companies" :key="comp.code || ci" align="center" min-width="120">
        <template #header>
          <div style="text-align:center;line-height:1.3">
            <div style="font-weight:600">{{ comp.name }}</div>
            <div style="color:#4b2d77;font-size:11px">持股比例 {{ comp.ratio }}%</div>
          </div>
        </template>
        <template #default="{ row }">
          <el-input-number v-if="!row.isHeader && row.values"
            v-model="row.values[ci]" size="small" :precision="2" :controls="false"
            style="width:100%" :class="{ 'ws-auto-cell': row.isComputed }" />
        </template>
      </el-table-column>
    </el-table>

    <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
    <el-dialog v-model="importVisible" title="导入净资产表数据" width="700px" append-to-body>
      <el-alert type="warning" :closable="false" style="margin-bottom:12px">
        <template #title><span>请使用"导出模板"填写。系统自动读取<b>"数据填写"</b>工作表，按行名匹配填入对应单元格。请勿修改sheet名称和项目列。</span></template>
      </el-alert>
      <div v-if="importStats">
        <p style="font-size:13px;color:#666">解析结果：匹配 <b style="color:#4b2d77">{{ importStats.matched }}</b> 行，跳过 {{ importStats.skipped }} 行</p>
        <el-table :data="importPreviewRows" border size="small" max-height="300">
          <el-table-column prop="item" label="项目" width="200" />
          <el-table-column prop="total" label="合计" width="100" align="right" />
          <el-table-column prop="parent" label="母公司" width="100" align="right" />
          <el-table-column v-for="(c, i) in companies" :key="i" :label="c.name" width="100" align="right">
            <template #default="{ row }">{{ row.values?.[i] ?? '-' }}</template>
          </el-table-column>
        </el-table>
      </div>
      <el-empty v-else description="未解析到有效数据" :image-size="60" />
      <template #footer>
        <el-button @click="importVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!importStats?.matched" @click="confirmImport">确认导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

interface CompanyCol {
  name: string    // 子企业名称
  code: string    // 企业代码
  ratio: number   // 期末持股比例（%）
}

interface NetAssetRow {
  seq: string; item: string; total: number | null; parent: number | null
  values: (number | null)[]; indent?: number; bold?: boolean
  isHeader?: boolean; isComputed?: boolean; section?: string
}

const props = defineProps<{
  companies: CompanyCol[]
  modelValue: NetAssetRow[]
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: NetAssetRow[]): void
  (e: 'save', v: NetAssetRow[]): void
  (e: 'open-formula', sheetKey: string): void
}>()

const companies = computed(() => props.companies)
const tableData = ref<NetAssetRow[]>([...props.modelValue])
const isFullscreen = ref(false)
const sheetRef = ref<HTMLElement | null>(null)
const selectedRows = ref<NetAssetRow[]>([])

function addRow() {
  // 在最后一个明细行后插入自定义行
  const newRow: NetAssetRow = { seq: '', item: '自定义行', total: null, parent: null, values: [], indent: 1 }
  tableData.value.push(newRow)
}

async function batchDelete() {
  if (!selectedRows.value.length) return
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selectedRows.value.length} 行？`, '删除确认', { type: 'warning' })
    const del = new Set(selectedRows.value)
    tableData.value = tableData.value.filter(r => !del.has(r))
    selectedRows.value = []
  } catch {}
}

let internalUpdate = false
watch(() => props.modelValue, (v) => { if (!internalUpdate) tableData.value = v }, { deep: true })
watch(tableData, (v) => {
  recalcSummaryRows()
  internalUpdate = true; emit('update:modelValue', v); nextTick(() => { internalUpdate = false })
}, { deep: true, immediate: true })

// 自动计算汇总行（期初合计、本期增加、本期减少、期末金额等）
// 规则：isComputed + bold 的行 = 其后连续 indent>0 且非 bold/header 行的合计
function recalcSummaryRows() {
  const rows = tableData.value
  const n = (v: any) => Number(v) || 0
  for (let i = 0; i < rows.length; i++) {
    const row = rows[i]
    if (!row.isComputed || !row.bold || row.isHeader) continue
    // 找到这个汇总行后面的明细行
    let totalSum = 0, parentSum = 0
    const valSums: number[] = new Array(companies.value.length).fill(0)
    for (let j = i + 1; j < rows.length; j++) {
      const child = rows[j]
      if (child.bold || child.isHeader || (child.indent || 0) === 0) break
      if (child.isComputed) continue // 跳过子级的计算行
      totalSum += n(child.total)
      parentSum += n(child.parent)
      if (child.values) {
        for (let k = 0; k < valSums.length; k++) {
          valSums[k] += n(child.values[k])
        }
      }
    }
    row.total = totalSum
    row.parent = parentSum
    if (!row.values) row.values = []
    for (let k = 0; k < valSums.length; k++) {
      row.values[k] = valSums[k]
    }
  }
}

function fmt(v: any) {
  if (v == null) return '-'
  const num = Number(v)
  return isNaN(num) ? '-' : num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function calcCls(v: any) { return Number(v) === 0 ? 'ws-computed ws-zero' : 'ws-computed' }

const headerStyle = { background: '#f0edf5', fontSize: '12px', color: '#333', padding: '2px 0' }

function rowCellStyle({ row }: any) {
  const base: any = { padding: '2px 4px', fontSize: '12px' }
  if (row.isHeader) { base.background = '#f8f6fb'; base.fontWeight = '600' }
  if (row.bold) { base.fontWeight = '600' }
  return base
}

function rowClassName({ row }: { row: NetAssetRow }) {
  if (row.isHeader) return 'ws-row-header'
  if (row.bold) return 'ws-row-bold'
  return ''
}

function spanMethod({ row, columnIndex }: any) {
  // columnIndex: 0=selection, 1=seq, 2=item, 3=total, 4=parent, 5+=companies
  if (row.isHeader && columnIndex === 2) {
    return { rowspan: 1, colspan: 3 + companies.value.length }
  }
  if (row.isHeader && columnIndex > 2) return { rowspan: 0, colspan: 0 }
  return { rowspan: 1, colspan: 1 }
}

function onEsc(e: KeyboardEvent) { if (e.key === 'Escape' && isFullscreen.value) isFullscreen.value = false }

// ─── 导出模板 / 导入 Excel ────────────────────────────────────────────────────
const fileInputRef = ref<HTMLInputElement | null>(null)
const importVisible = ref(false)
const importStats = ref<{ matched: number; skipped: number } | null>(null)
const importPreviewRows = ref<any[]>([])
const importParsedMap = ref<Map<string, any>>(new Map())

async function exportTemplate() {
  const XLSX = await import('xlsx')
  const wb = XLSX.utils.book_new()

  // 说明 sheet
  const instrRows = [['净资产表 — 填写说明'], [],
    ['⚠ 重要提示：'],
    ['1. 在"数据填写"工作表填写，不要修改sheet名称'],
    ['2. 第1行为表头（序号/项目/合计/母公司/各子企业名称），不要修改'],
    ['3. "项目"列的文字不要修改，系统按项目名匹配导入'],
    ['4. 紫色背景行（期初合计/本期增加/本期减少/期末金额等）为自动计算行，无需填写'],
    ['5. 只需填写明细行的数值（如实收资本、资本公积等）'],
    ['6. 金额填数字，不要带逗号或货币符号'],
  ]
  const wsI = XLSX.utils.aoa_to_sheet(instrRows)
  wsI['!cols'] = [{ wch: 80 }]
  wsI['!merges'] = [{ s: { r: 0, c: 0 }, e: { r: 0, c: 0 } }]
  XLSX.utils.book_append_sheet(wb, wsI, '填写说明')

  // 数据 sheet
  const headers = ['序号', '项目', '合计', '母公司', ...companies.value.map(c => `${c.name}\n(${c.ratio}%)`)]
  const dataRows = tableData.value.map(row => {
    const vals = [row.seq, row.item, row.total ?? '', row.parent ?? '']
    if (row.values) {
      for (let i = 0; i < companies.value.length; i++) {
        vals.push(row.values[i] ?? '')
      }
    } else {
      for (let i = 0; i < companies.value.length; i++) vals.push('')
    }
    return vals
  })
  const wsD = XLSX.utils.aoa_to_sheet([headers, ...dataRows])
  wsD['!cols'] = [{ wch: 6 }, { wch: 28 }, { wch: 14 }, { wch: 14 },
    ...companies.value.map(() => ({ wch: 14 }))]
  XLSX.utils.book_append_sheet(wb, wsD, '数据填写')
  XLSX.writeFile(wb, '净资产表_模板.xlsx')
  ElMessage.success('模板已导出')
}

async function onFileSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    const XLSX = await import('xlsx')
    const wb = XLSX.read(await file.arrayBuffer(), { type: 'array' })
    const sn = wb.SheetNames.find(n => n === '数据填写') || wb.SheetNames[wb.SheetNames.length - 1]
    const json: any[][] = XLSX.utils.sheet_to_json(wb.Sheets[sn], { header: 1 })
    if (json.length < 2) { ElMessage.warning('文件中没有数据'); return }

    // 按项目名匹配
    const parsed = new Map<string, any>()
    let matched = 0, skipped = 0
    for (let i = 1; i < json.length; i++) {
      const r = json[i]
      const itemName = String(r?.[1] || '').trim()
      if (!itemName) { skipped++; continue }
      // 在 tableData 中找到匹配的行
      const target = tableData.value.find(row => row.item === itemName)
      if (!target || target.isHeader || target.isComputed) { skipped++; continue }
      const entry: any = { item: itemName, total: r[2], parent: r[3], values: [] }
      for (let k = 0; k < companies.value.length; k++) {
        entry.values.push(r[4 + k] ?? null)
      }
      parsed.set(itemName, entry)
      matched++
    }
    importParsedMap.value = parsed
    importStats.value = { matched, skipped }
    importPreviewRows.value = Array.from(parsed.values()).slice(0, 10)
    importVisible.value = true
  } catch (err: any) { ElMessage.error('解析失败：' + (err.message || '格式错误')) }
  finally { if (fileInputRef.value) fileInputRef.value.value = '' }
}

function confirmImport() {
  const n = (v: any) => (v != null && v !== '') ? Number(v) : null
  let count = 0
  for (const row of tableData.value) {
    if (row.isHeader || row.isComputed) continue
    const entry = importParsedMap.value.get(row.item)
    if (!entry) continue
    row.total = n(entry.total)
    row.parent = n(entry.parent)
    if (entry.values) {
      if (!row.values) row.values = []
      for (let k = 0; k < companies.value.length; k++) {
        row.values[k] = n(entry.values[k])
      }
    }
    count++
  }
  importVisible.value = false
  importStats.value = null
  importParsedMap.value = new Map()
  ElMessage.success(`已导入 ${count} 行数据`)
}
onMounted(() => document.addEventListener('keydown', onEsc))
onUnmounted(() => document.removeEventListener('keydown', onEsc))
</script>

<style scoped>
.ws-sheet { padding: 0; position: relative; }
.ws-sheet--fullscreen { position: fixed !important; top: 0; left: 0; right: 0; bottom: 0; z-index: 2000; background: #fff; padding: 16px; overflow: auto; }
.ws-sheet-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.ws-sheet-header h3 { margin: 0; font-size: 15px; color: #333; }
.ws-sheet-actions { display: flex; gap: 8px; }
.ws-tip { display: flex; align-items: flex-start; gap: 6px; padding: 6px 10px; margin-bottom: 10px; background: #f4f4f5; border-radius: 6px; font-size: 12px; color: #666; line-height: 1.5; }
.ws-computed { color: #4b2d77; font-weight: 500; }
.ws-zero { color: #c0c4cc !important; font-weight: 400 !important; }
.ws-table :deep(.el-input__inner) { text-align: right; }
.ws-table :deep(.ws-auto-cell .el-input__inner) { color: #4b2d77; font-weight: 500; background: #faf8fd; }
.ws-table :deep(.el-table__body .ws-col-index .cell) { white-space: nowrap; }
.ws-table :deep(.ws-row-header td) { background: #f8f6fb !important; font-weight: 600; }
.ws-table :deep(.ws-row-bold td) { font-weight: 600; }
</style>
