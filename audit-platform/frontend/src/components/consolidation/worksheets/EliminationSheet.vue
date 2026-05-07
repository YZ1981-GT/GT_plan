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
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { confirmBatch } from '@/utils/confirm'
import { useFullscreen } from '@/composables/useFullscreen'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { useExcelIO, type ExcelColumn } from '@/composables/useExcelIO'

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

// 科目树形选项（父节点 disabled 禁止选中，只能选叶子科目）
const subjectTree = [
  { label: '资产', value: '_asset', disabled: true, children: [
    { label: '流动资产', value: '_current_asset', disabled: true, children: [
      { label: '货币资金', value: '货币资金' },
      { label: '应收票据', value: '应收票据' },
      { label: '应收账款', value: '应收账款' },
      { label: '预付账款', value: '预付账款' },
      { label: '其他应收款', value: '其他应收款' },
      { label: '存货', value: '存货' },
      { label: '合同资产', value: '合同资产' },
    ]},
    { label: '非流动资产', value: '_noncurrent_asset', disabled: true, children: [
      { label: '长期股权投资', value: '长期股权投资' },
      { label: '固定资产', value: '固定资产' },
      { label: '在建工程', value: '在建工程' },
      { label: '无形资产', value: '无形资产' },
      { label: '商誉', value: '商誉' },
      { label: '长期待摊费用', value: '长期待摊费用' },
      { label: '递延所得税资产', value: '递延所得税资产' },
    ]},
    { label: '减值准备', value: '_impairment', disabled: true, children: [
      { label: '坏账准备', value: '坏账准备' },
      { label: '存货跌价准备', value: '存货跌价准备' },
      { label: '固定资产减值准备', value: '固定资产减值准备' },
      { label: '长期股权投资减值准备', value: '长期股权投资减值准备' },
    ]},
  ]},
  { label: '负债', value: '_liability', disabled: true, children: [
    { label: '流动负债', value: '_current_liability', disabled: true, children: [
      { label: '应付票据', value: '应付票据' },
      { label: '应付账款', value: '应付账款' },
      { label: '预收账款', value: '预收账款' },
      { label: '合同负债', value: '合同负债' },
      { label: '其他应付款', value: '其他应付款' },
      { label: '应付职工薪酬', value: '应付职工薪酬' },
      { label: '应交税费', value: '应交税费' },
    ]},
    { label: '非流动负债', value: '_noncurrent_liability', disabled: true, children: [
      { label: '长期借款', value: '长期借款' },
      { label: '递延所得税负债', value: '递延所得税负债' },
      { label: '递延收益', value: '递延收益' },
    ]},
  ]},
  { label: '权益', value: '_equity', disabled: true, children: [
    { label: '实收资本（或股本）', value: '实收资本（或股本）' },
    { label: '其他权益工具', value: '其他权益工具' },
    { label: '资本公积', value: '资本公积' },
    { label: '减：库存股', value: '减：库存股' },
    { label: '其他综合收益', value: '其他综合收益' },
    { label: '专项储备', value: '专项储备' },
    { label: '盈余公积', value: '盈余公积' },
    { label: '△一般风险准备', value: '△一般风险准备' },
    { label: '未分配利润', value: '未分配利润' },
    { label: '少数股东权益', value: '少数股东权益' },
  ]},
  { label: '损益', value: '_income', disabled: true, children: [
    { label: '收入', value: '_revenue', disabled: true, children: [
      { label: '营业收入', value: '营业收入' },
      { label: '投资收益', value: '投资收益' },
      { label: '公允价值变动收益', value: '公允价值变动收益' },
      { label: '资产处置收益', value: '资产处置收益' },
      { label: '其他收益', value: '其他收益' },
    ]},
    { label: '成本费用', value: '_expense', disabled: true, children: [
      { label: '营业成本', value: '营业成本' },
      { label: '管理费用', value: '管理费用' },
      { label: '销售费用', value: '销售费用' },
      { label: '财务费用', value: '财务费用' },
      { label: '研发费用', value: '研发费用' },
      { label: '信用减值损失', value: '信用减值损失' },
      { label: '资产减值损失', value: '资产减值损失' },
    ]},
    { label: '利润分配', value: '_profit_dist', disabled: true, children: [
      { label: '年初未分配利润', value: '年初未分配利润' },
      { label: '少数股权损益', value: '少数股权损益' },
      { label: '提取盈余公积', value: '提取盈余公积' },
      { label: '对所有者的分配', value: '对所有者的分配' },
    ]},
  ]},
  { label: '现金流', value: '_cashflow', disabled: true, children: [
    { label: '销售商品收到的现金', value: '销售商品收到的现金' },
    { label: '购买商品支付的现金', value: '购买商品支付的现金' },
    { label: '收回投资收到的现金', value: '收回投资收到的现金' },
    { label: '投资支付的现金', value: '投资支付的现金' },
    { label: '分配股利支付的现金', value: '分配股利支付的现金' },
  ]},
]

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

const totalDebit = computed(() => allEntries.value.filter(r => r.direction === '借').reduce((s, r) => s + n(r.amount), 0))
const totalCredit = computed(() => allEntries.value.filter(r => r.direction === '贷').reduce((s, r) => s + n(r.amount), 0))

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

<style>
/* 科目树形下拉面板样式 */
.ws-subject-popper {
  min-width: 240px !important;
}
.ws-subject-popper .el-tree-node__content {
  height: 26px;
  font-size: 12px;
}
.ws-subject-popper .el-tree-node__label {
  font-size: 12px;
}
.ws-subject-popper .el-tree-node__expand-icon {
  font-size: 11px;
}
/* 父节点（disabled）灰色斜体，仅作分类标题 */
.ws-subject-popper .el-tree-node.is-disabled > .el-tree-node__content {
  cursor: default;
  opacity: 1;
}
.ws-subject-popper .el-tree-node.is-disabled > .el-tree-node__content .el-tree-node__label {
  color: #999;
  font-weight: 600;
  font-size: 11px;
}
/* 叶子节点正常可选 */
.ws-subject-popper .el-tree-node:not(.is-disabled) > .el-tree-node__content:hover {
  background: #f0edf5;
}
.ws-subject-popper .el-tree-node:not(.is-disabled) > .el-tree-node__content .el-tree-node__label {
  color: #333;
}
</style>
