<template>
  <div ref="sheetRef" class="ws-sheet" :class="{ 'gt-fullscreen': isFullscreen }">
    <div class="ws-sheet-header">
      <h3>合并抵消分录明细表</h3>
      <div class="ws-sheet-actions">
        <el-tooltip :content="isFullscreen ? '退出全屏' : '全屏编辑'" placement="top">
          <el-button size="small" @click="toggleFullscreen">{{ isFullscreen ? '⬜ 退出全屏' : '⛶ 全屏' }}</el-button>
        </el-tooltip>
        <el-button size="small" @click="$emit('open-formula', 'consol_elimination')">ƒx 公式</el-button>
        <el-button size="small" @click="exportTemplate">📥 导出模板</el-button>
        <el-button size="small" @click="exportData">📤 导出数据</el-button>
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
      :style="{ fontSize: displayPrefs.fontConfig.tableFont }"
      :max-height="isFullscreen ? 'calc(100vh - 100px)' : 'calc(100vh - 280px)'"
      :header-cell-style="headerStyle" :cell-style="entryCellStyle"
      :row-class-name="entryRowClass"
      @selection-change="onSelChange">
      <el-table-column type="selection" width="36" fixed align="center" :selectable="(row: any) => row._custom" />
      <el-table-column type="index" label="序号" width="50" fixed align="center" class-name="ws-col-index" />
      <el-table-column prop="source" label="来源" width="90" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.source" :type="(sourceTagType(row.source)) || undefined" size="small" effect="plain">{{ row.source }}</el-tag>
          <el-tag v-else type="info" size="small" effect="light">自定义</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="direction" label="借贷" width="70" align="center">
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
          <div v-if="row._custom" @click.stop @mousedown.stop>
            <el-tree-select v-model="row.subject" :data="subjectTree" size="small" style="width:100%"
              placeholder="选择科目" filterable check-strictly :render-after-expand="false"
              popper-class="ws-subject-popper"
              :props="{ label: 'label', children: 'children', disabled: 'disabled' }" />
          </div>
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
          <span v-else style="font-size: var(--gt-font-size-xs);color: var(--gt-color-text-tertiary)">{{ row.desc || '' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 借贷平衡校验 -->
    <div class="ws-balance-check">
      <span>借方合计: <b class="ws-computed">{{ fmt(totalDebit) }}</b></span>
      <span style="margin:0 12px">贷方合计: <b class="ws-computed">{{ fmt(totalCredit) }}</b></span>
      <span :class="elimBalanceDiff !== 0 ? 'ws-diff-warn' : ''" style="font-weight:600">
        差额: {{ fmt(elimBalanceDiff) }}
        <span v-if="elimBalanceDiff === 0" style="color: var(--gt-color-success);margin-left:4px">✓ 平衡</span>
        <span v-else style="color: var(--gt-color-wheat);margin-left:4px">⚠ 不平衡</span>
      </span>
    </div>
    <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { confirmBatch } from '@/utils/confirm'
import { useFullscreen } from '@/composables/useFullscreen'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { useExcelIO, type ExcelColumn } from '@/composables/useExcelIO'
import { useDecimalCalc } from '@/composables/useDecimalCalc'
import { useConsolSubjectSource } from '../composables/useConsolSubjectSource'

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

const { isFullscreen, toggleFullscreen } = useFullscreen()
const displayPrefs = useDisplayPrefsStore()
const fmt = (v: any) => displayPrefs.fmt(v)
const sheetRef = ref<HTMLElement | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)
const selectedCustomRows = ref<EntryRow[]>([])
const n = (v: any) => Number(v) || 0
const { sum: decSum, sub: decSub } = useDecimalCalc()

// 科目树形选项（Req 19.1）：名称真源来自 ACNR-backed TB 域（useConsolSubjectSource）。
// 保留 disabled 父节点分组骨架 + 叶子科目名；registry 空/不可用时自动回退硬编码（Req 19.5）。
// 叶子 value === 科目名字符串，subject 值契约不变，buildAutoEntries / Excel 逻辑无需改动（Req 19.7）。
const { subjectTree } = useConsolSubjectSource()

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
    await confirmBatch('删除', selectedCustomRows.value.length)
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

const totalDebit = computed(() => Number(decSum(...allEntries.value.filter(r => r.direction === '借').map(r => String(n(r.amount))))))
const totalCredit = computed(() => Number(decSum(...allEntries.value.filter(r => r.direction === '贷').map(r => String(n(r.amount))))))
const elimBalanceDiff = computed(() => Number(decSub(String(totalDebit.value), String(totalCredit.value))))

// ─── 导出/导入 ───────────────────────────────────────────────────────────────
const { exportTemplate: _exportTemplate, exportData: _exportData, onFileSelected: _onFileSelected } = useExcelIO()

const ELIM_COLS: ExcelColumn[] = [
  { key: 'source', header: '来源', width: 10 },
  { key: 'direction', header: '借贷', width: 8 },
  { key: 'subject', header: '科目', width: 20 },
  { key: 'detail', header: '二级明细', width: 16 },
  { key: 'amount', header: '金额', width: 16 },
  { key: 'desc', header: '说明', width: 24 },
]

async function exportTemplate() {
  await _exportTemplate({
    columns: ELIM_COLS,
    fileName: '合并抵消分录_模板.xlsx',
    includeNoteRow: false,
    existingData: allEntries.value.map(r => [r.source || '自定义', r.direction, r.subject, r.detail, r.amount ?? '', r.desc]),
  })
}

async function exportData() {
  await _exportData({
    data: allEntries.value.map(r => ({ ...r, source: r.source || '自定义' })),
    columns: ELIM_COLS,
    sheetName: '合并抵消分录',
    fileName: '合并抵消分录_数据.xlsx',
  })
}

async function onFileSelected(e: Event) {
  await _onFileSelected(e, (result) => {
    let cnt = 0
    for (const r of result.rows) {
      if (!r['科目']) continue
      customEntries.push({
        source: '', direction: String(r['借贷'] || '借'), subject: String(r['科目'] || ''),
        detail: String(r['二级明细'] || ''), amount: r['金额'] != null ? Number(r['金额']) : null,
        desc: String(r['说明'] || ''), _custom: true,
      })
      cnt++
    }
    ElMessage.success(`已导入 ${cnt} 条自定义分录`)
  }, { skipRows: 1 })
}


function sourceTagType(source: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  const map: Record<string, '' | 'success' | 'warning' | 'info' | 'danger' | 'primary'> = { '权益抵消': '', '损益抵消': 'warning', '交叉持股': 'info', '内部往来': 'success', '内部交易': 'success', '内部现金流': 'success' }
  return map[source] || 'info'
}

const headerStyle = { background: '#f0edf5', fontSize: '11px', color: '#333', padding: '3px 0' }
function entryCellStyle({ row }: any) {
  const base: any = { padding: '3px 6px', fontSize: '12px' }
  if (!row._custom) { base.background = '#f9f9f9'; base.color = '#666' }
  return base
}
function entryRowClass({ row }: any) { return row._custom ? '' : 'ws-row-auto' }


</script>

<style scoped>
.ws-sheet { padding: 0; position: relative; }
.ws-sheet-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 6px; }
.ws-sheet-header h3 { margin: 0; font-size: var(--gt-font-size-base); color: var(--gt-color-text-primary); }
.ws-sheet-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.ws-tip { display: flex; align-items: flex-start; gap: 6px; padding: 6px 10px; margin-bottom: 10px; background: var(--gt-color-bg); border-radius: 6px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); line-height: 1.5; }
.ws-tip b { color: var(--gt-color-primary); }
.ws-link { color: var(--gt-color-primary); cursor: pointer; text-decoration: underline; font-weight: 500; }
.ws-link:hover { color: var(--gt-color-primary); }
.ws-computed { color: var(--gt-color-primary); font-weight: 500; }
.ws-bold { font-weight: 700; }
.ws-diff-warn { color: var(--gt-color-wheat) !important; font-weight: 700 !important; }
.ws-balance-check {
  margin-top: 10px; padding: 8px 14px; background: var(--gt-color-bg); border-radius: 6px;
  border: 1px solid var(--gt-color-border-light); font-size: var(--gt-font-size-sm); display: flex; align-items: center;
}
.ws-table :deep(.el-input__inner) { text-align: right; font-size: var(--gt-font-size-xs); }
.ws-table :deep(.el-table__body .ws-col-index .cell) { white-space: nowrap; }
.ws-table :deep(.ws-row-auto td) { background: var(--gt-color-bg) !important; }
</style>

<style>
/* 科目树形下拉面板样式 */
.ws-subject-popper {
  min-width: 240px !important;
}
.ws-subject-popper .el-tree-node__content {
  height: 26px;
  font-size: var(--gt-font-size-xs);
}
.ws-subject-popper .el-tree-node__label {
  font-size: var(--gt-font-size-xs);
}
.ws-subject-popper .el-tree-node__expand-icon {
  font-size: var(--gt-font-size-xs);
}
/* 父节点（disabled）灰色斜体，仅作分类标题 */
.ws-subject-popper .el-tree-node.is-disabled > .el-tree-node__content {
  cursor: default;
  opacity: 1;
}
.ws-subject-popper .el-tree-node.is-disabled > .el-tree-node__content .el-tree-node__label {
  color: var(--gt-color-text-tertiary);
  font-weight: 600;
  font-size: var(--gt-font-size-xs);
}
/* 叶子节点正常可选 */
.ws-subject-popper .el-tree-node:not(.is-disabled) > .el-tree-node__content:hover {
  background: var(--gt-color-primary-bg);
}
.ws-subject-popper .el-tree-node:not(.is-disabled) > .el-tree-node__content .el-tree-node__label {
  color: var(--gt-color-text-primary);
}
</style>
