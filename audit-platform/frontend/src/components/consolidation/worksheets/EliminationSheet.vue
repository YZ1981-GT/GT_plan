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
        <el-button size="small" type="warning" @click="refreshAutoEntries">🔄 刷新</el-button>
        <el-button size="small" type="primary" @click="addCustomRow">+ 新增行</el-button>
        <el-button size="small" type="danger" :disabled="!selectedCustomRows.length" @click="batchDeleteCustom">
          删除{{ selectedCustomRows.length ? `(${selectedCustomRows.length})` : '' }}
        </el-button>
        <el-button size="small" @click="$emit('save', allEntries)">💾 保存</el-button>
      </div>
    </div>
    <div class="ws-tip" v-show="!isFullscreen">
      <span>统一汇总表：自动拉取的分录（灰色背景）来自
        <a class="ws-link" @click="$emit('goto-sheet', 'equity_sim')">模拟权益法</a>、
        <a class="ws-link" @click="$emit('goto-sheet', 'internal_arap')">内部往来</a>、
        <a class="ws-link" @click="$emit('goto-sheet', 'internal_trade')">内部交易</a>、
        <a class="ws-link" @click="$emit('goto-sheet', 'internal_cashflow')">内部现金流</a>，
        <b>不可直接编辑，需到源表修改后点"🔄 刷新"</b>。白色行为自定义分录，可自由编辑增删。
      </span>
    </div>

    <el-table :data="allEntries" border size="small" class="ws-table"
      :max-height="isFullscreen ? 'calc(100vh - 100px)' : 'calc(100vh - 280px)'"
      :header-cell-style="headerStyle" :cell-style="entryCellStyle"
      :row-class-name="entryRowClass"
      @selection-change="onSelChange">
      <el-table-column type="selection" width="36" fixed align="center" :selectable="(row: any) => row._custom" />
      <el-table-column type="index" label="序号" width="50" fixed align="center" class-name="ws-col-index" />
      <el-table-column prop="source" label="来源" width="90" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.source" :type="sourceTagType(row.source)" size="small" effect="plain">{{ row.source }}</el-tag>
          <el-tag v-else type="info" size="small" effect="light">自定义</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="direction" label="借贷方向" width="70" align="center">
        <template #default="{ row }">
          <div v-if="row._custom" @click.stop @mousedown.stop>
            <el-select v-model="row.direction" size="small" style="width:100%">
              <el-option label="借" value="借" /><el-option label="贷" value="贷" />
            </el-select>
          </div>
          <el-tag v-else :type="row.direction === '借' ? 'danger' : 'success'" size="small" effect="plain">{{ row.direction }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="subject" label="科目" width="180">
        <template #default="{ row }">
          <el-input v-if="row._custom" v-model="row.subject" size="small" placeholder="科目" />
          <span v-else>{{ row.subject }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="detail" label="二级明细" width="140">
        <template #default="{ row }">
          <el-input v-if="row._custom" v-model="row.detail" size="small" placeholder="明细" />
          <span v-else>{{ row.detail || '' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="amount" label="金额" width="140" align="right">
        <template #default="{ row }">
          <el-input-number v-if="row._custom" v-model="row.amount" size="small" :precision="2" :controls="false" style="width:100%" />
          <span v-else class="ws-computed">{{ fmt(row.amount) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="desc" label="说明" min-width="180">
        <template #default="{ row }">
          <el-input v-if="row._custom" v-model="row.desc" size="small" placeholder="说明" />
          <span v-else style="font-size:11px;color:#999">{{ row.desc || '' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 借贷平衡校验 -->
    <div class="ws-balance-check">
      <span>借方合计: <b class="ws-computed">{{ fmt(totalDebit) }}</b></span>
      <span style="margin:0 12px">贷方合计: <b class="ws-computed">{{ fmt(totalCredit) }}</b></span>
      <span :class="totalDebit - totalCredit !== 0 ? 'ws-diff-warn' : ''" style="font-weight:600">
        差额: {{ fmt(totalDebit - totalCredit) }}
        <span v-if="totalDebit - totalCredit === 0" style="color:#67c23a;margin-left:4px">✓ 平衡</span>
        <span v-else style="color:#e6a23c;margin-left:4px">⚠ 不平衡</span>
      </span>
    </div>

    <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

interface CompanyCol { name: string; code?: string; ratio: number }
interface EntryRow {
  source: string; direction: string; subject: string; detail: string
  amount: number | null; desc: string; _custom?: boolean
}

const props = defineProps<{
  companies: CompanyCol[]
  equityRows: any[]; incomeRows: any[]; crossRows: any[]
  importedEntries?: any[]
}>()

defineEmits<{
  (e: 'save', data: EntryRow[]): void
  (e: 'open-formula', key: string): void
  (e: 'goto-sheet', key: string): void
}>()

const isFullscreen = ref(false)
const sheetRef = ref<HTMLElement | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)
const selectedCustomRows = ref<EntryRow[]>([])
const n = (v: any) => Number(v) || 0

// ─── 自动拉取的分录（只读） ──────────────────────────────────────────────────
function buildAutoEntries(): EntryRow[] {
  const entries: EntryRow[] = []
  // 权益抵消
  for (const r of (props.equityRows || [])) {
    const amt = r.values ? r.values.reduce((s: number, v: any) => s + n(v), 0) : n(r.total)
    if (amt) entries.push({ source: '权益抵消', direction: r.direction, subject: r.subject, detail: r.detail || '', amount: amt, desc: '' })
  }
  // 损益抵消
  for (const r of (props.incomeRows || [])) {
    const amt = r.values ? r.values.reduce((s: number, v: any) => s + n(v), 0) : n(r.total)
    if (amt) entries.push({ source: '损益抵消', direction: r.direction, subject: r.subject, detail: r.detail || '', amount: amt, desc: '' })
  }
  // 交叉持股
  for (const r of (props.crossRows || [])) {
    if (n(r.total)) entries.push({ source: '交叉持股', direction: r.direction, subject: r.subject, detail: '', amount: n(r.total), desc: '' })
  }
  // 内部抵消（从 importedEntries）
  for (const r of (props.importedEntries || [])) {
    if (n(r.amount)) entries.push({ source: r.source || '内部抵消', direction: r.direction, subject: r.subject, detail: '', amount: n(r.amount), desc: r.desc || '' })
  }
  return entries
}

const autoEntries = ref<EntryRow[]>(buildAutoEntries())

function refreshAutoEntries() {
  autoEntries.value = buildAutoEntries()
  ElMessage.success(`已刷新，共 ${autoEntries.value.length} 条自动分录`)
}

// 监听 props 变化自动刷新
watch([() => props.equityRows, () => props.incomeRows, () => props.crossRows, () => props.importedEntries], () => {
  autoEntries.value = buildAutoEntries()
}, { deep: true })

// ─── 自定义分录（可编辑） ────────────────────────────────────────────────────
const customEntries = reactive<EntryRow[]>([])

function addCustomRow() {
  const nr: EntryRow = { source: '', direction: '借', subject: '', detail: '', amount: null, desc: '', _custom: true }
  if (selectedCustomRows.value.length > 0) {
    const last = selectedCustomRows.value[selectedCustomRows.value.length - 1]
    const idx = customEntries.indexOf(last)
    if (idx >= 0) { customEntries.splice(idx + 1, 0, nr); return }
  }
  customEntries.push(nr)
}

async function batchDeleteCustom() {
  if (!selectedCustomRows.value.length) return
  try {
    await ElMessageBox.confirm(`确定删除 ${selectedCustomRows.value.length} 条自定义分录？`, '删除确认', { type: 'warning' })
    const del = new Set(selectedCustomRows.value)
    const remaining = customEntries.filter(r => !del.has(r))
    customEntries.length = 0; customEntries.push(...remaining)
    selectedCustomRows.value = []
  } catch {}
}

function onSelChange(sel: any[]) {
  selectedCustomRows.value = sel.filter((r: EntryRow) => r._custom)
}

// ─── 合并所有分录 ────────────────────────────────────────────────────────────
const allEntries = computed(() => [...autoEntries.value, ...customEntries])

const totalDebit = computed(() => allEntries.value.filter(r => r.direction === '借').reduce((s, r) => s + n(r.amount), 0))
const totalCredit = computed(() => allEntries.value.filter(r => r.direction === '贷').reduce((s, r) => s + n(r.amount), 0))

// ─── 导出/导入 ───────────────────────────────────────────────────────────────
async function exportTemplate() {
  const XLSX = await import('xlsx'); const wb = XLSX.utils.book_new()
  const headers = ['来源','借贷方向','科目','二级明细','金额','说明']
  const dataRows = allEntries.value.map(r => [r.source || '自定义', r.direction, r.subject, r.detail, r.amount ?? '', r.desc])
  const ws = XLSX.utils.aoa_to_sheet([headers, ...dataRows])
  ws['!cols'] = [{ wch: 10 }, { wch: 8 }, { wch: 20 }, { wch: 16 }, { wch: 16 }, { wch: 24 }]
  XLSX.utils.book_append_sheet(wb, ws, '数据填写')
  XLSX.writeFile(wb, '合并抵消分录_模板.xlsx'); ElMessage.success('模板已导出')
}

async function onFileSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]; if (!file) return
  try {
    const XLSX = await import('xlsx'); const wb = XLSX.read(await file.arrayBuffer(), { type: 'array' })
    const sn = wb.SheetNames.find(n => n === '数据填写') || wb.SheetNames[wb.SheetNames.length - 1]
    const json: any[][] = XLSX.utils.sheet_to_json(wb.Sheets[sn], { header: 1 })
    let cnt = 0
    for (let i = 1; i < json.length; i++) {
      const r = json[i]; if (!r?.[2]) continue
      customEntries.push({
        source: '', direction: String(r[1] || '借'), subject: String(r[2] || ''),
        detail: String(r[3] || ''), amount: r[4] != null ? Number(r[4]) : null,
        desc: String(r[5] || ''), _custom: true,
      })
      cnt++
    }
    ElMessage.success(`已导入 ${cnt} 条自定义分录`)
  } catch (err: any) { ElMessage.error('解析失败：' + (err.message || '')) }
  finally { if (fileInputRef.value) fileInputRef.value.value = '' }
}

function fmt(v: any) { if (v == null) return '-'; const num = Number(v); return isNaN(num) ? '-' : num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }

function sourceTagType(source: string) {
  const map: Record<string, string> = { '权益抵消': '', '损益抵消': 'warning', '交叉持股': 'info', '内部往来': 'success', '内部交易': 'success', '内部现金流': 'success' }
  return map[source] || 'info'
}

const headerStyle = { background: '#f0edf5', fontSize: '11px', color: '#333', padding: '3px 0' }
function entryCellStyle({ row }: any) {
  const base: any = { padding: '3px 6px', fontSize: '12px' }
  if (!row._custom) { base.background = '#f9f9f9'; base.color = '#666' }
  return base
}
function entryRowClass({ row }: any) { return row._custom ? '' : 'ws-row-auto' }

function onEsc(e: KeyboardEvent) { if (e.key === 'Escape' && isFullscreen.value) isFullscreen.value = false }
onMounted(() => document.addEventListener('keydown', onEsc))
onUnmounted(() => document.removeEventListener('keydown', onEsc))
</script>

<style scoped>
.ws-sheet { padding: 0; position: relative; }
.ws-sheet--fullscreen { position: fixed !important; top: 0; left: 0; right: 0; bottom: 0; z-index: 2000; background: #fff; padding: 16px; overflow: auto; }
.ws-sheet-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 6px; }
.ws-sheet-header h3 { margin: 0; font-size: 15px; color: #333; }
.ws-sheet-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.ws-tip { display: flex; align-items: flex-start; gap: 6px; padding: 6px 10px; margin-bottom: 10px; background: #f4f4f5; border-radius: 6px; font-size: 12px; color: #666; line-height: 1.5; }
.ws-tip b { color: #4b2d77; }
.ws-link { color: #4b2d77; cursor: pointer; text-decoration: underline; font-weight: 500; }
.ws-link:hover { color: #7c5caa; }
.ws-computed { color: #4b2d77; font-weight: 500; }
.ws-bold { font-weight: 700; }
.ws-diff-warn { color: #e6a23c !important; font-weight: 700 !important; }
.ws-balance-check {
  margin-top: 10px; padding: 8px 14px; background: #fafafa; border-radius: 6px;
  border: 1px solid #eee; font-size: 13px; display: flex; align-items: center;
}
.ws-table :deep(.el-input__inner) { text-align: right; font-size: 11px; }
.ws-table :deep(.el-table__body .ws-col-index .cell) { white-space: nowrap; }
.ws-table :deep(.ws-row-auto td) { background: #f9f9f9 !important; }
</style>
