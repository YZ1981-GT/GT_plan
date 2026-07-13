<template>
  <div class="i6-tab-adjustment">
    <div class="methodology-block">
      <p><strong>研发费用调整分录编制规则：</strong></p>
      <ul>
        <li>AJE（审计调整分录）：影响报表金额，改变审定数</li>
        <li>RJE（重分类调整分录）：仅重分类列报</li>
        <li>每笔分录借贷方合计必须相等（借贷平衡原则）</li>
        <li>科目6602研发费用（损益类/借方科目），取发生额</li>
        <li>保存后自动同步至审定表I6-1，推送A13错报汇总</li>
      </ul>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实研发费用相关审计调整分录（AJE/RJE）编制正确、借贷平衡，恰当调整研发费用（6602）发生额，并准确推送至审定表 I6-1 及 A13 错报汇总。"
      class="objective-alert"
    />

    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>I6-3 调整分录汇总（AJE / RJE）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" @click="handleAddRow" :disabled="isReadonly">+ 新增分录</el-button>
            <el-dropdown size="small" :disabled="isReadonly" @command="handleImportExport">
              <el-button size="small">导入导出 <el-icon class="el-icon--right"><ArrowDown /></el-icon></el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
                  <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
                  <el-dropdown-item command="import-data" divided>导入数据</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button size="small" type="default" text @click="handleReview">复核</el-button>
          </div>
        </div>
      </template>

      <el-alert v-if="!isBalanced && rows.length > 0" type="error"
        :title="`借贷不平衡！借方合计 ${fmtAmount(totalDebit)} ≠ 贷方合计 ${fmtAmount(totalCredit)}，差额 ${fmtAmount(totalDebit - totalCredit)}`"
        show-icon :closable="false" class="balance-warning" />

      <el-table :data="rows" border stripe size="small" class="adj-table" show-summary :summary-method="getSummary">
        <el-table-column type="index" label="序号" width="50" align="center" />
        <el-table-column prop="description" label="调整事项说明" min-width="150">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.description" size="small" placeholder="调整事项" @change="onFieldChange" /><span v-else>{{ row.description }}</span></template>
        </el-table-column>
        <el-table-column prop="category" label="类别" width="90" align="center">
          <template #default="{ row }"><el-select v-if="!isReadonly" v-model="row.category" size="small" style="width:80px" @change="onFieldChange"><el-option label="AJE" value="AJE" /><el-option label="RJE" value="RJE" /></el-select><el-tag v-else :type="row.category === 'AJE' ? 'danger' : 'warning'" size="small">{{ row.category }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="reportItem" label="报表项目" min-width="110">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.reportItem" size="small" @change="onFieldChange" /><span v-else>{{ row.reportItem }}</span></template>
        </el-table-column>
        <el-table-column prop="accountName" label="科目名称" min-width="120">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.accountName" size="small" placeholder="如 研发费用" @change="onFieldChange" /><span v-else>{{ row.accountName }}</span></template>
        </el-table-column>
        <el-table-column prop="noteItem" label="附注项目" min-width="100">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.noteItem" size="small" @change="onFieldChange" /><span v-else>{{ row.noteItem || '-' }}</span></template>
        </el-table-column>
        <el-table-column prop="debit" label="借方调整" width="120" align="right">
          <template #default="{ row }"><el-input-number v-if="!isReadonly" v-model="row.debit" size="small" :controls="false" :min="0" @change="onFieldChange" /><span v-else>{{ fmtAmount(row.debit) }}</span></template>
        </el-table-column>
        <el-table-column prop="credit" label="贷方调整" width="120" align="right">
          <template #default="{ row }"><el-input-number v-if="!isReadonly" v-model="row.credit" size="small" :controls="false" :min="0" @change="onFieldChange" /><span v-else>{{ fmtAmount(row.credit) }}</span></template>
        </el-table-column>
        <el-table-column prop="indexRef" label="索引" width="90">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.indexRef" size="small" @change="onFieldChange" /><GtIndexChip v-else-if="row.indexRef" :value="row.indexRef" @click="navigateTo(row.indexRef)" /><span v-else>-</span></template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="100">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="onFieldChange" /><span v-else>{{ row.remark || '-' }}</span></template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="55" align="center">
          <template #default="{ row }"><el-button type="danger" link size="small" @click="handleRemoveRow(row.rowId)">删</el-button></template>
        </el-table-column>
      </el-table>
    </el-card>

    <div class="action-bar">
      <el-button type="success" size="small" @click="handleSave" :disabled="isReadonly">保存</el-button>
      <el-button size="small" @click="handlePushA13" :disabled="isReadonly || rows.length === 0">推送A13错报汇总</el-button>
      <div class="cross-ref-bar">
        <span class="cross-ref-label">联动：</span>
        <GtIndexChip value="I6-1" @click="navigateTo('I6-1')" />
        <GtIndexChip value="A13" @click="navigateTo('A13')" />
      </div>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><span>审计说明</span></template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly" placeholder="请填写审计说明（调整分录依据、AJE/RJE性质、对研发费用发生额的影响等）..." @blur="onAuditNoteBlur" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><span>审计结论</span></template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly" placeholder="请填写审计结论（调整分录编制正确、借贷平衡、已同步审定表与A13）..." @blur="onAuditConclusionBlur" />
    </el-card>

    <details class="guidance-details compile-hint"><summary>编制提示</summary><ul>
      <li>借贷方合计必须相等（借贷平衡原则）</li>
      <li>保存后EventBus推送'i6:adjustment-writeback'更新I6-1</li>
      <li>推送A13将错报信息发送至错报汇总底稿</li>
      <li>科目6602研发费用（损益类/借方）</li>
    </ul></details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, inject } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const emit = defineEmits<{ 'navigate-sheet': [sheetName: string]; 'save': [itemId: string, value: any] }>()
const openReviewDialog = inject<(section?: string) => void>('openReviewDialog', () => {})

interface AdjRow { rowId: string; description: string; category: 'AJE' | 'RJE'; reportItem: string; accountName: string; noteItem: string; debit: number; credit: number; indexRef: string; remark: string }

const ITEM_ID = 'I6-3-rows'
const NOTE_KEY = 'I6-3-audit-note'
const CONCLUSION_KEY = 'I6-3-audit-conclusion'
const rows = ref<AdjRow[]>([])
const auditNote = ref('')
const auditConclusion = ref('')

const totalDebit = computed(() => rows.value.reduce((s, r) => s + (r.debit || 0), 0))
const totalCredit = computed(() => rows.value.reduce((s, r) => s + (r.credit || 0), 0))
const isBalanced = computed(() => Math.abs(totalDebit.value - totalCredit.value) < 0.01)

function _str(id: string): string { const it = props.allResponses.get(id); return (it?.remark ?? (typeof it === 'string' ? it : '')) as string }

function _load(): void {
  auditNote.value = _str(NOTE_KEY)
  auditConclusion.value = _str(CONCLUSION_KEY)
  const item = props.allResponses.get(ITEM_ID)
  const raw = item?.remark ?? (typeof item === 'string' ? item : null)
  if (raw) { try { const p = JSON.parse(raw); if (Array.isArray(p)) { rows.value = p; return } } catch { /* */ } }
  rows.value = []
}
watch(() => props.allResponses, () => _load(), { immediate: true })

function onAuditNoteBlur(): void { if (props.isReadonly) return; emit('save', NOTE_KEY, auditNote.value) }
function onAuditConclusionBlur(): void { if (props.isReadonly) return; emit('save', CONCLUSION_KEY, auditConclusion.value) }

function _persist(): void { emit('save', ITEM_ID, JSON.stringify(rows.value)) }
function onFieldChange(): void { _persist() }

async function handleAddRow(): Promise<void> {
  try {
    const { value: desc } = await ElMessageBox.prompt('请输入调整事项描述', '新增调整分录', { confirmButtonText: '确定', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '描述不能为空' })
    if (!desc) return
    rows.value.push({ rowId: `row-${Date.now().toString(36)}`, description: desc.trim(), category: 'AJE', reportItem: '研发费用', accountName: '研发费用', noteItem: '', debit: 0, credit: 0, indexRef: '', remark: '' })
    _persist()
  } catch { /* cancelled */ }
}

function handleRemoveRow(rowId: string): void { const idx = rows.value.findIndex((r) => r.rowId === rowId); if (idx >= 0) { rows.value.splice(idx, 1); _persist() } }

function handleSave(): void {
  _persist()
  window.dispatchEvent(new CustomEvent('i6:adjustment-writeback', { detail: { wpCode: 'I6-3', entries: rows.value, totalDebit: totalDebit.value, totalCredit: totalCredit.value } }))
  ElMessage.success('调整分录已保存')
}

function handlePushA13(): void {
  if (!isBalanced.value) { ElMessage.warning('借贷不平衡，请先修正'); return }
  window.dispatchEvent(new CustomEvent('adjustment:created', { detail: { wpCode: 'I6-3', target: 'A13', entries: rows.value } }))
  ElMessage.success('已推送至A13错报汇总')
}

function getSummary({ columns }: { columns: any[] }): string[] {
  return columns.map((col, idx) => { if (idx === 0) return '合计'; if (col.property === 'debit') return fmtAmount(totalDebit.value); if (col.property === 'credit') return fmtAmount(totalCredit.value); return '' })
}

async function handleImportExport(cmd: string): Promise<void> {
  if (cmd === 'export-template' || cmd === 'export-data') {
    try { const ep = cmd === 'export-template' ? 'export-template' : 'export-data'; const res = await http.get(`/api/workpapers/${props.wpId}/i6/${ep}`, { params: { sheet: 'I6-3' }, responseType: 'blob' }); const blob = res.data instanceof Blob ? res.data : new Blob([res.data]); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = `I6-3_调整分录${cmd === 'export-template' ? '模板' : '数据'}.xlsx`; a.click(); URL.revokeObjectURL(url) } catch { ElMessage.error('导出失败') }
  } else if (cmd === 'import-data') {
    const input = document.createElement('input'); input.type = 'file'; input.accept = '.xlsx,.xls,.csv'
    input.onchange = async (e: Event) => { const file = (e.target as HTMLInputElement).files?.[0]; if (!file) return; const fd = new FormData(); fd.append('file', file); try { const res = await http.post(`/api/workpapers/${props.wpId}/i6/import-data`, fd, { params: { sheet: 'I6-3' }, headers: { 'Content-Type': 'multipart/form-data' } }); const data = res.data?.data ?? res.data; if (Array.isArray(data?.rows)) { rows.value = data.rows; _persist() }; ElMessage.success('导入成功') } catch { ElMessage.error('导入失败') } }
    input.click()
  }
}

function handleReview(): void { openReviewDialog('I6-3 调整分录') }
function navigateTo(code: string): void { emit('navigate-sheet', code) }
function fmtAmount(v: number | null | undefined): string { if (v == null || Math.abs(v) < 0.005) return '-'; return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.i6-tab-adjustment { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.audit-note-card { margin-top: 16px; }
.audit-note-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; }
.methodology-block { border-left: 4px solid #d97706; background: #fffbeb; padding: 12px 16px; margin-bottom: 16px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.6; }
.methodology-block p { margin: 0 0 4px; }
.methodology-block ul { margin: 0; padding-left: 16px; }
.methodology-block li { margin-bottom: 2px; }
.methodology-block strong { color: #78350f; }
.section-title { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
.title-actions { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.balance-warning { margin-bottom: 12px; }
.adj-table { font-size: var(--wp-font-size, 13px); }
.adj-table :deep(.el-table__footer td) { font-weight: 600; background: #f0f9ff; }
.action-bar { display: flex; align-items: center; gap: 12px; padding: 12px 0; margin-top: 12px; flex-wrap: wrap; }
.cross-ref-bar { display: flex; align-items: center; gap: 6px; margin-left: auto; }
.cross-ref-label { color: #606266; font-size: 12px; }
.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
