<template>
  <div class="gt-formula-bar" v-if="visible">
    <!-- 地址显示 -->
    <div class="addr-box">
      <span class="addr-label">{{ currentAddr || '--' }}</span>
    </div>

    <!-- 公式/值编辑 -->
    <div class="formula-box">
      <span class="fx-icon" :class="{ 'fx-has-formula': hasFormula }" :title="hasFormula ? '含公式' : '值'">fx</span>
      <input
        ref="formulaInput"
        class="formula-input"
        :value="displayFormula"
        :placeholder="hasFormula ? '公式（以=开头）' : '输入值或公式（=开头）'"
        @focus="editing = true"
        @blur="onBlur"
        @keydown.enter="onConfirm"
        @keydown.escape="onCancel"
      />
      <!-- 确认/取消 -->
      <el-button size="small" type="primary" text @click="onConfirm" title="确认 (Enter)">✓</el-button>
      <el-button size="small" text @click="onCancel" title="取消 (Esc)">✗</el-button>
      <!-- 选择按钮 → 弹出取数辅助面板 -->
      <el-popover placement="bottom-end" :width="400" trigger="click" :teleported="true">
        <template #reference>
          <el-button size="small" text title="公式辅助选择">📋 选择</el-button>
        </template>
        <div class="qp-panel">
          <div class="qp-title">公式辅助输入</div>
          <div class="qp-section">
            <div class="qp-label">取数（点击弹窗选择数据源）</div>
            <div class="qp-btns">
              <el-button size="small" @click="pickSource('TB')" title="从试算表选择科目">TB</el-button>
              <el-button size="small" @click="pickSource('ROW')" title="从报表选择行次">ROW</el-button>
              <el-button size="small" @click="pickSource('SUM_ROW')" title="连续行范围求和">SUM_ROW</el-button>
              <el-button size="small" @click="pickSource('NOTE')" title="从附注选择章节">NOTE</el-button>
              <el-button size="small" @click="pickSource('WP')" title="从底稿选择">WP</el-button>
              <el-button size="small" @click="pickSource('REPORT')" title="跨表引用报表行">REPORT</el-button>
            </div>
          </div>
          <div class="qp-section">
            <div class="qp-label">运算符（自动插入到公式栏）</div>
            <div class="qp-btns">
              <el-button size="small" @click="insertOp(' + ')">+</el-button>
              <el-button size="small" @click="insertOp(' - ')">−</el-button>
              <el-button size="small" @click="insertOp(' * ')">×</el-button>
              <el-button size="small" @click="insertOp(' / ')">÷</el-button>
              <el-button size="small" @click="insertOp(' = ')">=</el-button>
              <el-button size="small" @click="insertOp(' > ')">></el-button>
              <el-button size="small" @click="insertOp(' < ')"><</el-button>
              <el-button size="small" @click="insertOp(' >= ')">≥</el-button>
              <el-button size="small" @click="insertOp(' <= ')">≤</el-button>
            </div>
          </div>
          <div class="qp-section">
            <div class="qp-label">函数</div>
            <div class="qp-btns">
              <el-button size="small" @click="quickInsert('IF')" title="IF(条件, 真值, 假值)">IF</el-button>
              <el-button size="small" @click="quickInsert('ABS')" title="取绝对值">ABS</el-button>
              <el-button size="small" @click="quickInsert('ROUND')" title="四舍五入">ROUND</el-button>
              <el-button size="small" @click="quickInsert('MAX')" title="最大值">MAX</el-button>
              <el-button size="small" @click="quickInsert('MIN')" title="最小值">MIN</el-button>
            </div>
          </div>
          <div class="qp-hint">💡 取数按钮会弹出数据源选择弹窗，运算符直接插入公式栏</div>
        </div>
      </el-popover>
    </div>

    <!-- 状态标签 -->
    <div class="formula-meta" v-if="hasFormula || isMerged || hasFetchRule">
      <el-tag v-if="hasFormula" size="small" :type="(formulaTypeColor) || undefined" effect="plain" title="公式类型">{{ formulaTypeLabel || '公式' }}</el-tag>
      <el-tag v-if="isMerged" size="small" type="warning" effect="plain">合并{{ mergeRange }}</el-tag>
      <el-tag v-if="hasFetchRule" size="small" type="info" effect="plain">🔗取数</el-tag>
    </div>
  </div>

  <!-- 数据源选择弹窗（TB/ROW/NOTE/WP/REPORT） -->
  <el-dialog v-model="showSourceDialog" :title="sourceDialogTitle" width="65%" top="8vh" append-to-body destroy-on-close>
    <el-input v-model="sourceSearch" size="small" placeholder="搜索..." clearable style="width: 240px; margin-bottom: 8px;" />
    <el-table :data="filteredSourceRows" v-loading="sourceLoading" max-height="50vh" border highlight-current-row
      size="small" @row-click="onSourceRowClick">
      <el-table-column prop="code" label="编码" width="120" />
      <el-table-column prop="name" label="名称" min-width="200" show-overflow-tooltip />
      <el-table-column label="将插入" width="240">
        <template #default="{ row }">
          <code style="font-size: var(--gt-font-size-xs); color: var(--gt-color-primary); background: var(--gt-color-primary-bg); padding: 1px 6px; border-radius: 4px;">{{ row._ref }}</code>
        </template>
      </el-table-column>
    </el-table>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { api } from '@/services/apiProxy'
import * as P from '@/services/apiPaths'

interface CellInfo {
  cell: string
  address: string
  value: any
  formula: string | null
  formula_type: string | null
  formula_desc: string | null
  fetch_rule_id: string | null
  merge: { range: string; rowspan: number; colspan: number } | null
  is_merged: boolean
}

const props = defineProps<{
  visible?: boolean
  cellInfo: CellInfo | null
  projectId?: string
}>()

const emit = defineEmits<{
  'update-formula': [cell: string, formula: string]
  'update-value': [cell: string, value: string]
  'open-selector': []
}>()

const editing = ref(false)
const formulaInput = ref<HTMLInputElement>()
const _showQuickPicker = ref(false)

const currentAddr = computed(() => props.cellInfo?.address || '')
const isMerged = computed(() => props.cellInfo?.is_merged || false)
const mergeRange = computed(() => props.cellInfo?.merge?.range || '')
const hasFormula = computed(() => !!props.cellInfo?.formula)
const hasFetchRule = computed(() => !!props.cellInfo?.fetch_rule_id)
const formulaType = computed(() => props.cellInfo?.formula_type || '')
const _formulaDesc = computed(() => props.cellInfo?.formula_desc || '')

const displayFormula = computed(() => {
  if (props.cellInfo?.formula) return props.cellInfo.formula
  const val = props.cellInfo?.value
  if (val === null || val === undefined) return ''
  return String(val)
})

const formulaTypeLabel = computed(() => {
  const map: Record<string, string> = {
    vertical_sum: '纵向合计',
    horizontal_balance: '横向平衡',
    book_value: '账面价值',
    cross_table: '跨表引用',
  }
  return map[formulaType.value] || formulaType.value
})

const formulaTypeColor = computed((): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' => {
  if (formulaType.value === 'cross_table') return 'warning'
  if (formulaType.value === 'vertical_sum') return ''
  return 'info'
})

function onConfirm() {
  const input = formulaInput.value
  if (!input || !props.cellInfo) return

  const val = input.value.trim()
  if (val.startsWith('=')) {
    emit('update-formula', props.cellInfo.cell, val)
  } else {
    emit('update-value', props.cellInfo.cell, val)
  }
  editing.value = false
}

function onCancel() {
  editing.value = false
  // 恢复原值
  if (formulaInput.value) {
    formulaInput.value.value = displayFormula.value
  }
}

function onBlur() {
  setTimeout(() => { editing.value = false }, 200)
}

// ── 运算符直接插入 ──
function insertOp(op: string) {
  const input = formulaInput.value
  if (!input) return
  const start = input.selectionStart || input.value.length
  const before = input.value.substring(0, start)
  const after = input.value.substring(input.selectionEnd || start)
  input.value = before + op + after
  input.focus()
  const pos = before.length + op.length
  input.setSelectionRange(pos, pos)
}

// ── 函数模板插入 ──
function quickInsert(fn: string) {
  const templates: Record<string, string> = {
    'IF': 'IF(,,)', 'ABS': 'ABS()', 'ROUND': 'ROUND(,2)', 'MAX': 'MAX(,)', 'MIN': 'MIN(,)',
  }
  const tpl = templates[fn] || fn + '()'
  const input = formulaInput.value
  if (!input) return
  const start = input.selectionStart || input.value.length
  const before = input.value.substring(0, start)
  const after = input.value.substring(input.selectionEnd || start)
  input.value = before + tpl + after
  input.focus()
  const cursorPos = before.length + tpl.indexOf('(') + 1
  input.setSelectionRange(cursorPos, cursorPos)
}

// ── 数据源选择弹窗 ──
const showSourceDialog = ref(false)
const sourceDialogTitle = ref('')
const sourceRows = ref<any[]>([])
const sourceLoading = ref(false)
const sourceSearch = ref('')
const currentPickFn = ref('')

const filteredSourceRows = computed(() => {
  const kw = sourceSearch.value.toLowerCase()
  if (!kw) return sourceRows.value
  return sourceRows.value.filter((r: any) =>
    (r.code || '').toLowerCase().includes(kw) || (r.name || '').toLowerCase().includes(kw)
  )
})

async function pickSource(fn: string) {
  currentPickFn.value = fn
  sourceSearch.value = ''
  sourceLoading.value = true
  showSourceDialog.value = true

  const titleMap: Record<string, string> = {
    TB: '选择试算表科目', ROW: '选择报表行次', SUM_ROW: '选择报表行次（范围）',
    NOTE: '选择附注章节', WP: '选择底稿', REPORT: '选择报表行次',
  }
  sourceDialogTitle.value = titleMap[fn] || '选择数据源'

  try {
    if (fn === 'TB') {
      const data = await api.get('/api/trial-balance', {
        params: { project_id: props.projectId },
        validateStatus: (s: number) => s < 600,
      })
      const rows = data ?? []
      sourceRows.value = rows.map((r: any) => ({
        code: r.standard_account_code || r.account_code || '',
        name: r.account_name || r.standard_account_name || '',
        _ref: `TB('${r.standard_account_code || r.account_code || ''}','期末余额')`,
      }))
    } else if (fn === 'ROW' || fn === 'SUM_ROW' || fn === 'REPORT') {
      const data = await api.get(P.reportConfig.list, {
        params: { report_type: 'balance_sheet', project_id: props.projectId },
        validateStatus: (s: number) => s < 600,
      })
      const rows = data ?? []
      sourceRows.value = rows.map((r: any) => ({
        code: r.row_code || '',
        name: r.row_name || '',
        _ref: fn === 'REPORT' ? `REPORT('${r.row_code}','期末')` : `ROW('${r.row_code}')`,
      }))
    } else if (fn === 'NOTE') {
      const data = await api.get('/api/disclosure-notes/tree', { validateStatus: (s: number) => s < 600 })
      const items = data ?? []
      sourceRows.value = items.map((r: any) => ({
        code: r.note_number || r.section_number || r.note_section || '',
        name: r.title || r.section_title || '',
        _ref: `NOTE('${r.title || r.section_title || ''}','合计','期末')`,
      }))
    } else if (fn === 'WP') {
      const data = await api.get('/api/working-papers', { validateStatus: (s: number) => s < 600 })
      const items = data ?? []
      sourceRows.value = items.map((r: any) => ({
        code: r.wp_code || '',
        name: r.wp_name || r.name || '',
        _ref: `WP('${r.wp_code || ''}','审定数')`,
      }))
    } else {
      sourceRows.value = []
    }
  } catch {
    sourceRows.value = []
  } finally {
    sourceLoading.value = false
  }
}

function onSourceRowClick(row: any) {
  const input = formulaInput.value
  if (!input) return
  const ref = row._ref || ''
  const start = input.selectionStart || input.value.length
  const before = input.value.substring(0, start)
  const after = input.value.substring(input.selectionEnd || start)
  input.value = before + ref + after
  input.focus()
  const pos = before.length + ref.length
  input.setSelectionRange(pos, pos)
  showSourceDialog.value = false
}
</script>

<style scoped>
.gt-formula-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  background: linear-gradient(180deg, #faf8fd 0%, #f5f3f8 100%);
  border-bottom: 1px solid #e8e4f0;
  min-height: 36px;
  font-size: var(--gt-font-size-sm);
  box-shadow: 0 1px 2px rgba(75, 45, 119, 0.04);
}
.addr-box {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 80px;
  padding: 4px 10px;
  background: var(--gt-color-bg-white);
  border: 1px solid #e0dae8;
  border-radius: 6px;
  font-family: 'Cascadia Code', 'Fira Code', monospace;
  font-size: var(--gt-font-size-xs);
  font-weight: 700;
  color: var(--gt-color-primary);
  box-shadow: inset 0 1px 2px rgba(75, 45, 119, 0.06);
}
.formula-box {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;
  background: var(--gt-color-bg-white);
  border: 1px solid #e0dae8;
  border-radius: 6px;
  padding: 4px 10px;
  box-shadow: inset 0 1px 2px rgba(75, 45, 119, 0.04);
  transition: border-color 0.15s;
}
.formula-box:focus-within {
  border-color: #4b2d77;
  box-shadow: 0 0 0 2px rgba(75, 45, 119, 0.08);
}
.fx-icon {
  font-style: italic;
  font-weight: bold;
  color: var(--gt-color-primary);
  font-size: var(--gt-font-size-sm);
  user-select: none;
  opacity: 0.6;
}
.formula-input {
  flex: 1;
  border: none;
  outline: none;
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  font-size: var(--gt-font-size-xs);
  background: transparent;
  color: var(--gt-color-text-primary);
}
.formula-input:focus {
  color: var(--gt-color-text-primary);
}
.formula-actions {
  display: flex;
  gap: 2px;
}
.formula-meta {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}
.fx-has-formula { color: var(--gt-color-primary); opacity: 1; }

/* 快捷选择面板 */
.qp-panel { padding: 4px 0; }
.qp-title { font-size: var(--gt-font-size-xs); font-weight: 600; color: var(--gt-color-text-primary); margin-bottom: 8px; }
.qp-section { margin-bottom: 8px; }
.qp-label { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-bottom: 4px; }
.qp-btns { display: flex; gap: 4px; flex-wrap: wrap; }
.qp-btns .el-button { font-size: var(--gt-font-size-xs); padding: 2px 8px; font-family: monospace; }
.qp-hint { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-placeholder); margin-top: 4px; }
</style>
