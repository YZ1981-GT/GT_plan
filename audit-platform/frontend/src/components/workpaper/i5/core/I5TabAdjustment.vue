<template>
  <div class="i5-tab-adjustment">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：确认其他非流动资产调整分录的准确性、完整性及借贷平衡，确保审定数正确反映经调整后余额。" />

    <!-- 方法论上下文（琥珀色左边线） -->
    <div class="methodology-block">
      <p><strong>其他非流动资产调整分录编制规则：</strong></p>
      <ul>
        <li>AJE（审计调整分录）：影响报表金额，改变审定数</li>
        <li>RJE（重分类调整分录）：仅重分类列报，不改变损益总额</li>
        <li>每笔分录借贷方合计必须相等（借贷平衡原则）</li>
        <li>科目代码应与试算平衡表科目编码一致（1911其他非流动资产）</li>
        <li>保存后自动同步至审定表I5-1，推送A13错报汇总</li>
      </ul>
    </div>

    <!-- 操作栏 -->
    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>I5-3 调整分录汇总（AJE / RJE）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" @click="handleAddRow" :disabled="isReadonly">
              + 新增分录
            </el-button>
            <el-dropdown size="small" :disabled="isReadonly" @command="handleImportExport">
              <el-button size="small">
                导入导出 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
                  <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
                  <el-dropdown-item command="import-data" divided>导入数据</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button size="small" type="primary" text @click="handleAiGenerate">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
            <el-button size="small" type="default" text @click="handleReview">
              复核
            </el-button>
          </div>
        </div>
      </template>

      <!-- 借贷平衡警告 -->
      <el-alert
        v-if="!isBalanced && rows.length > 0"
        type="error"
        :title="`借贷不平衡！借方合计 ${fmtAmount(totalDebit)} ≠ 贷方合计 ${fmtAmount(totalCredit)}，差额 ${fmtAmount(totalDebit - totalCredit)}`"
        show-icon
        :closable="false"
        class="balance-warning"
      />

      <!-- 调整分录表格 -->
      <el-table :data="rows" border stripe size="small" class="adj-table" show-summary :summary-method="getSummary">
        <!-- 1. 序号 -->
        <el-table-column type="index" label="序号" width="50" align="center" />

        <!-- 2. 调整事项 -->
        <el-table-column prop="description" label="调整事项" min-width="150">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.description" size="small" placeholder="调整事项描述" @change="onFieldChange" />
            <span v-else>{{ row.description }}</span>
          </template>
        </el-table-column>

        <!-- 3. 分录类型(AJE/RJE) -->
        <el-table-column prop="entryType" label="分录类型" width="100" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.entryType" size="small" style="width:80px" @change="onFieldChange">
              <el-option label="AJE" value="AJE" />
              <el-option label="RJE" value="RJE" />
            </el-select>
            <el-tag v-else :type="row.entryType === 'AJE' ? 'danger' : 'warning'" size="small">
              {{ row.entryType }}
            </el-tag>
          </template>
        </el-table-column>

        <!-- 4. 科目代码 -->
        <el-table-column prop="accountCode" label="科目代码" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.accountCode" size="small" placeholder="如1911" @change="onFieldChange" />
            <span v-else>{{ row.accountCode }}</span>
          </template>
        </el-table-column>

        <!-- 5. 科目名称 -->
        <el-table-column prop="accountName" label="科目名称" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.accountName" size="small" placeholder="科目名称" @change="onFieldChange" />
            <span v-else>{{ row.accountName }}</span>
          </template>
        </el-table-column>

        <!-- 6. 摘要 -->
        <el-table-column prop="summary" label="摘要" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.summary" size="small" placeholder="摘要" @change="onFieldChange" />
            <span v-else>{{ row.summary }}</span>
          </template>
        </el-table-column>

        <!-- 7. 借方 -->
        <el-table-column prop="debit" label="借方" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.debit"
              size="small"
              :controls="false"
              :min="0"
              @change="onFieldChange"
            />
            <span v-else>{{ fmtAmount(row.debit) }}</span>
          </template>
        </el-table-column>

        <!-- 8. 贷方 -->
        <el-table-column prop="credit" label="贷方" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.credit"
              size="small"
              :controls="false"
              :min="0"
              @change="onFieldChange"
            />
            <span v-else>{{ fmtAmount(row.credit) }}</span>
          </template>
        </el-table-column>

        <!-- 9. 索引 -->
        <el-table-column prop="indexRef" label="索引" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.indexRef" size="small" placeholder="索引" @change="onFieldChange" />
            <GtIndexChip v-else-if="row.indexRef" :value="row.indexRef" @click="navigateTo(row.indexRef)" />
            <span v-else>-</span>
          </template>
        </el-table-column>

        <!-- 10. 备注 -->
        <el-table-column prop="remark" label="备注" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" placeholder="备注" @change="onFieldChange" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>

        <!-- 操作列 -->
        <el-table-column label="操作" width="60" align="center" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="handleRemoveRow(row.rowId)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 联动操作 -->
    <div class="action-bar">
      <el-button type="success" size="small" @click="handleSave" :disabled="isReadonly">
        保存
      </el-button>
      <el-button size="small" @click="handlePushA13" :disabled="isReadonly || rows.length === 0">
        推送A13错报汇总
      </el-button>
      <div class="cross-ref-bar">
        <span class="cross-ref-label">联动：</span>
        <GtIndexChip value="I5-1" @click="navigateTo('I5-1')" />
        <GtIndexChip value="A13" @click="navigateTo('A13')" />
      </div>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header"><span>审计说明</span></div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="请填写审计说明..."
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header"><span>审计结论</span></div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="请填写审计结论..."
        @change="saveAuditConclusion"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>调整分录借贷方必须平衡（借方合计=贷方合计）</li>
        <li>保存后自动同步AJE/RJE金额到审定表I5-1</li>
        <li>推送A13按钮将错报信息发送至A13汇总底稿</li>
        <li>常用科目：1911其他非流动资产（借方/资产类）</li>
        <li>索引列填写关联底稿编号，自动生成可点击芯片跳转</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I5TabAdjustment.vue — I5-3 调整分录汇总
 *
 * 列结构：序号 | 调整事项 | 分录类型(AJE/RJE) | 科目代码 | 科目名称 | 摘要 | 借方 | 贷方 | 索引 | 备注
 * - 借贷平衡校验（Σdebit === Σcredit，红色警告）
 * - EventBus: 'adjustment:created' → A13
 * - 动态行: add/delete entries
 * - 导入导出(el-dropdown)
 * - 合计行 at bottom showing total debit/credit
 * - GtIndexChip linking to A13
 *
 * Spec: .kiro/specs/i5-other-noncurrent-assets/
 * Task: 4.4
 * Requirements: 6.1
 */
import { ref, computed, watch, inject } from 'vue'
import { ArrowDown, MagicStick } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

// ─── Emits ───────────────────────────────────────────────────────────────────

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
  'save': [itemId: string, value: any]
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(section?: string) => void>('openReviewDialog', () => {})

// ─── Types ───────────────────────────────────────────────────────────────────

interface AdjustmentRow {
  rowId: string
  description: string
  entryType: 'AJE' | 'RJE'
  accountCode: string
  accountName: string
  summary: string
  debit: number
  credit: number
  indexRef: string
  remark: string
}

// ─── State ───────────────────────────────────────────────────────────────────

const ITEM_ID = 'I5-3-rows'
const rows = ref<AdjustmentRow[]>([])

// ─── Load ────────────────────────────────────────────────────────────────────

function _load(): void {
  const item = props.allResponses.get(ITEM_ID)
  const raw = item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : null)
  if (!raw) { rows.value = []; return }
  try {
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) {
      rows.value = parsed.map(_normalizeRow)
    }
  } catch { rows.value = [] }
}

function _normalizeRow(raw: any): AdjustmentRow {
  return {
    rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
    description: raw.description ?? '',
    entryType: raw.entryType === 'RJE' ? 'RJE' : 'AJE',
    accountCode: raw.accountCode ?? '1911',
    accountName: raw.accountName ?? '其他非流动资产',
    summary: raw.summary ?? '',
    debit: Number(raw.debit) || 0,
    credit: Number(raw.credit) || 0,
    indexRef: raw.indexRef ?? '',
    remark: raw.remark ?? '',
  }
}

watch(() => props.allResponses, () => _load(), { immediate: true })

// ─── Computed: 借贷平衡 ──────────────────────────────────────────────────────

const totalDebit = computed(() => rows.value.reduce((sum, r) => sum + (r.debit || 0), 0))
const totalCredit = computed(() => rows.value.reduce((sum, r) => sum + (r.credit || 0), 0))
const isBalanced = computed(() => Math.abs(totalDebit.value - totalCredit.value) < 0.01)

// ─── Summary ─────────────────────────────────────────────────────────────────

function getSummary({ columns }: { columns: any[] }): string[] {
  const sums: string[] = []
  columns.forEach((col, idx) => {
    if (idx === 0) { sums[idx] = '合计'; return }
    if (col.property === 'debit') { sums[idx] = fmtAmount(totalDebit.value); return }
    if (col.property === 'credit') { sums[idx] = fmtAmount(totalCredit.value); return }
    sums[idx] = ''
  })
  return sums
}

// ─── Actions ─────────────────────────────────────────────────────────────────

async function handleAddRow(): Promise<void> {
  try {
    const { value: desc } = await ElMessageBox.prompt(
      '请输入调整事项描述',
      '新增调整分录',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '描述不能为空',
      },
    )
    if (!desc) return

    rows.value.push({
      rowId: `row-${Date.now().toString(36)}`,
      description: desc.trim(),
      entryType: 'AJE',
      accountCode: '1911',
      accountName: '其他非流动资产',
      summary: '',
      debit: 0,
      credit: 0,
      indexRef: '',
      remark: '',
    })
    _persist()
  } catch { /* cancelled */ }
}

function handleRemoveRow(rowId: string): void {
  const idx = rows.value.findIndex((r) => r.rowId === rowId)
  if (idx >= 0) {
    rows.value.splice(idx, 1)
    _persist()
  }
}

function onFieldChange(): void {
  _persist()
}

function handleSave(): void {
  _persist()
  // EventBus: adjustment:created → A13联动
  window.dispatchEvent(new CustomEvent('adjustment:created', {
    detail: {
      wpCode: 'I5-3',
      target: 'A13',
      accountCodes: ['1911'],
      entries: rows.value,
      totalDebit: totalDebit.value,
      totalCredit: totalCredit.value,
    },
  }))
  ElMessage.success('调整分录已保存')
}

function handlePushA13(): void {
  if (!isBalanced.value) {
    ElMessage.warning('借贷不平衡，请先修正')
    return
  }
  window.dispatchEvent(new CustomEvent('adjustment:created', {
    detail: {
      wpCode: 'I5-3',
      target: 'A13',
      entries: rows.value,
    },
  }))
  ElMessage.success('已推送至A13错报汇总')
}

function _persist(): void {
  emit('save', ITEM_ID, JSON.stringify(rows.value))
}

// ─── Audit Note / Conclusion (AN+AC) persistence ─────────────────────────────

const NOTE_KEY = 'I5-adjustment-audit-note'
const CONCLUSION_KEY_AC = 'I5-adjustment-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  const item = { item_id: NOTE_KEY, conclusion: null, remark: val }
  props.allResponses.set(NOTE_KEY, item)
  emit('save', NOTE_KEY, val)
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  const item = { item_id: CONCLUSION_KEY_AC, conclusion: null, remark: val }
  props.allResponses.set(CONCLUSION_KEY_AC, item)
  emit('save', CONCLUSION_KEY_AC, val)
}

// Load AN+AC from allResponses
function _loadNoteConclusion(): void {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY_AC)
  if (c?.remark) auditConclusion.value = c.remark
}

watch(() => props.allResponses, () => _loadNoteConclusion(), { immediate: true })

// ─── Import / Export ─────────────────────────────────────────────────────────

async function handleImportExport(command: string): Promise<void> {
  if (command === 'export-template') {
    try {
      const res = await http.get(`/api/workpapers/${props.wpId}/i5/export-template`, {
        params: { sheet: 'I5-3' }, responseType: 'blob',
      })
      _downloadBlob(res, 'I5-3_调整分录模板.xlsx')
    } catch { ElMessage.error('导出模板失败') }
  } else if (command === 'export-data') {
    try {
      const res = await http.get(`/api/workpapers/${props.wpId}/i5/export-data`, {
        params: { sheet: 'I5-3' }, responseType: 'blob',
      })
      _downloadBlob(res, 'I5-3_调整分录数据.xlsx')
    } catch { ElMessage.error('导出数据失败') }
  } else if (command === 'import-data') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.xlsx,.xls,.csv'
    input.onchange = async (e: Event) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (!file) return
      try {
        await ElMessageBox.confirm(`导入「${file.name}」将覆盖现有数据。确认？`, '导入确认', { type: 'warning' })
        const formData = new FormData()
        formData.append('file', file)
        const res = await http.post(`/api/workpapers/${props.wpId}/i5/import-data`, formData, {
          params: { sheet: 'I5-3' }, headers: { 'Content-Type': 'multipart/form-data' },
        })
        const data = res.data?.data ?? res.data
        if (Array.isArray(data?.rows)) {
          rows.value = data.rows.map(_normalizeRow)
          _persist()
        }
        ElMessage.success(`导入成功 ${data?.imported_count ?? rows.value.length} 行`)
      } catch { /* cancelled or error */ }
    }
    input.click()
  }
}

function _downloadBlob(response: any, fallbackName: string): void {
  const blob = response.data instanceof Blob ? response.data : new Blob([response.data])
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fallbackName
  a.click()
  URL.revokeObjectURL(url)
}

// ─── AI / Review ─────────────────────────────────────────────────────────────

async function handleAiGenerate(): Promise<void> {
  try {
    await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'adjustment',
      prompt: 'I5其他非流动资产调整分录建议',
      context: { wpCode: 'I5-3', rowCount: rows.value.length },
    })
  } catch { /* ignore */ }
}

function handleReview(): void {
  openReviewDialog('I5-3 调整分录')
}

// ─── Navigation ──────────────────────────────────────────────────────────────

function navigateTo(wpCode: string): void {
  emit('navigate-sheet', wpCode)
}

// ─── Formatter ───────────────────────────────────────────────────────────────

function fmtAmount(value: number | null | undefined): string {
  if (value == null) return '-'
  if (Math.abs(value) < 0.005) return '-'
  return value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i5-tab-adjustment { padding: 16px; font-size: var(--wp-font-size, 13px); }

/* 审计目标 */
.objective-alert { margin-bottom: 14px; }

/* 审计说明/结论 el-card */
.audit-note-card { margin-bottom: 16px; }
.audit-note-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; }
.card-header { display: flex; align-items: center; justify-content: space-between; font-size: 14px; font-weight: 500; }

/* 方法论（琥珀色） */
.methodology-block {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 12px 16px;
  margin-bottom: 16px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.6;
}
.methodology-block p { margin: 0 0 4px; }
.methodology-block ul { margin: 0; padding-left: 16px; }
.methodology-block li { margin-bottom: 2px; }
.methodology-block strong { color: #78350f; }

/* 标题行 */
.section-title {
  display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: 8px;
}
.title-actions { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }

/* 平衡警告 */
.balance-warning { margin-bottom: 12px; }

/* 表格 */
.adj-table { font-size: var(--wp-font-size, 13px); }
.adj-table :deep(.el-table__footer td) { font-weight: 600; background: #f0f9ff; }

/* 操作栏 */
.action-bar {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 0; margin-top: 12px; flex-wrap: wrap;
}
.cross-ref-bar { display: flex; align-items: center; gap: 6px; margin-left: auto; }
.cross-ref-label { color: #606266; font-size: 12px; }

/* 编制提示 */
.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
