<template>
  <div class="i3-tab-adjustment">
    <!-- 方法论上下文（琥珀色左边线） -->
    <div class="methodology-block">
      <p><strong>商誉调整分录编制规则：</strong></p>
      <ul>
        <li>AJE（审计调整分录）：影响报表金额，改变审定数</li>
        <li>RJE（重分类调整分录）：仅重分类列报，不改变损益总额</li>
        <li>每笔分录借贷方合计必须相等（借贷平衡原则）</li>
        <li>科目代码应与试算平衡表科目编码一致（1711商誉）</li>
        <li>商誉减值不可转回！减值分录一经确认不可冲销</li>
        <li>保存后自动同步至审定表I3-1，推送A13错报汇总</li>
      </ul>
    </div>

    <!-- 操作栏 -->
    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>I3-3 调整分录汇总（AJE / RJE）</span>
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
            <el-button size="small" @click="handleSave" :disabled="isReadonly" type="success">
              保存
            </el-button>
            <el-button size="small" link @click="handlePushA13" :disabled="isReadonly || rows.length === 0">
              推送A13错报汇总
            </el-button>
          </div>
        </div>
      </template>

      <!-- 调整分录表格 -->
      <el-table :data="rows" border stripe size="small" class="adj-table" show-summary :summary-method="getSummary">
        <!-- 1. 序号 -->
        <el-table-column type="index" label="序号" width="50" align="center" />

        <!-- 2. 类别(AJE/RJE) -->
        <el-table-column prop="entryType" label="类型" width="90" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.entryType" size="small" style="width:72px">
              <el-option label="AJE" value="AJE" />
              <el-option label="RJE" value="RJE" />
            </el-select>
            <el-tag v-else :type="row.entryType === 'AJE' ? 'danger' : 'warning'" size="small">
              {{ row.entryType }}
            </el-tag>
          </template>
        </el-table-column>

        <!-- 3. 科目代码 -->
        <el-table-column prop="accountCode" label="科目代码" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.accountCode" size="small" placeholder="如1711" />
            <span v-else>{{ row.accountCode }}</span>
          </template>
        </el-table-column>

        <!-- 4. 科目名称 -->
        <el-table-column prop="accountName" label="科目名称" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.accountName" size="small" placeholder="科目名称" />
            <span v-else>{{ row.accountName }}</span>
          </template>
        </el-table-column>

        <!-- 5. 摘要 -->
        <el-table-column prop="summary" label="摘要" min-width="150">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.summary" size="small" placeholder="分录摘要" />
            <span v-else>{{ row.summary }}</span>
          </template>
        </el-table-column>

        <!-- 6. 借方 -->
        <el-table-column prop="debit" label="借方" width="120" align="right" header-align="center">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.debit"
              :controls="false"
              :min="0"
              :precision="2"
              size="small"
              style="width:100%"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.debit) }}</span>
          </template>
        </el-table-column>

        <!-- 7. 贷方 -->
        <el-table-column prop="credit" label="贷方" width="120" align="right" header-align="center">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.credit"
              :controls="false"
              :min="0"
              :precision="2"
              size="small"
              style="width:100%"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.credit) }}</span>
          </template>
        </el-table-column>

        <!-- 8. 索引 -->
        <el-table-column prop="indexRef" label="索引" width="90">
          <template #default="{ row }">
            <GtIndexChip v-if="row.indexRef" :value="row.indexRef" @click="$emit('navigate-sheet', row.indexRef)" />
            <el-input v-if="!isReadonly && !row.indexRef" v-model="row.indexRef" size="small" placeholder="A13" />
          </template>
        </el-table-column>

        <!-- 9. 备注 -->
        <el-table-column prop="remark" label="备注" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" placeholder="备注" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>

        <!-- 操作列 -->
        <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="handleRemove(row.rowId)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 借贷平衡校验栏 -->
      <div class="balance-bar" :class="{ 'balance-ok': isBalanced, 'balance-err': !isBalanced }">
        <span>借方合计：<strong>{{ fmtAmt(debitTotal) }}</strong></span>
        <span>贷方合计：<strong>{{ fmtAmt(creditTotal) }}</strong></span>
        <span v-if="!isBalanced" class="diff-warn">
          差额：{{ fmtAmt(Math.abs(debitTotal - creditTotal)) }}
        </span>
        <el-tag :type="isBalanced ? 'success' : 'danger'" size="small">
          {{ isBalanced ? '✓ 借贷平衡' : '✗ 借贷不平' }}
        </el-tag>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header><span>审计说明</span></template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="记录调整事项的审计判断、与管理层沟通情况（如商誉减值调整原因、CGU划分依据等）..."
      />
    </el-card>

    <!-- 跨底稿跳转 -->
    <div class="cross-ref-bar">
      <span class="cross-ref-label">跨底稿联动：</span>
      <GtIndexChip value="I3-1" @click="navigateTo('I3-1')" />
      <span class="cross-ref-desc">商誉审定表</span>
      <GtIndexChip value="A13" @click="navigateTo('A13')" />
      <span class="cross-ref-desc">错报汇总表</span>
    </div>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>AJE=审计调整分录，影响报表审定数；RJE=重分类调整，仅影响列报位置</li>
        <li>科目代码：1711商誉（借方/资产类）</li>
        <li>商誉减值准备科目需按被投资单位/CGU明细设置</li>
        <li>商誉减值不可转回！一经计提不可冲销（CAS8相关规定）</li>
        <li>每笔分录借贷合计必须平衡，整表借贷合计也须平衡</li>
        <li>保存后自动发布 adjustment:created 事件同步至审定表I3-1</li>
        <li>"推送A13"将分录同步到调整分录汇总表（错报汇总）</li>
        <li>索引列可输入底稿编号，自动生成跳转链接</li>
      </ul>
    </details>

    <!-- 隐藏的文件输入（导入用） -->
    <input
      ref="fileInputRef"
      type="file"
      accept=".xlsx,.xls"
      style="display:none"
      @change="handleFileSelected"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

// ─── Props & Emits ─────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
  (e: 'save'): void
}>()

// ─── Types ─────────────────────────────────────────────────────────────────

interface AdjustmentRow {
  rowId: string
  entryType: 'AJE' | 'RJE'
  accountCode: string
  accountName: string
  summary: string
  debit: number
  credit: number
  indexRef: string
  remark: string
}

// ─── State ─────────────────────────────────────────────────────────────────

const ITEM_ID = 'I3-3-rows'
const rows = ref<AdjustmentRow[]>([])
const auditNote = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)

// ─── Load from allResponses ────────────────────────────────────────────────

function loadRows(): void {
  const item = props.allResponses.get(ITEM_ID)
  const raw = item?.remark ?? item?.value
  if (!raw) { rows.value = []; return }
  try {
    const parsed = JSON.parse(typeof raw === 'string' ? raw : JSON.stringify(raw))
    rows.value = Array.isArray(parsed) ? parsed.map(normalizeRow) : []
  } catch { rows.value = [] }

  // Load audit note
  const noteItem = props.allResponses.get('I3-3-audit-note')
  auditNote.value = noteItem?.remark ?? noteItem?.value ?? ''
}

function normalizeRow(raw: any): AdjustmentRow {
  return {
    rowId: raw.rowId ?? `adj-${Math.random().toString(36).slice(2, 10)}`,
    entryType: raw.entryType === 'RJE' ? 'RJE' : 'AJE',
    accountCode: raw.accountCode ?? '',
    accountName: raw.accountName ?? '',
    summary: raw.summary ?? '',
    debit: Number(raw.debit) || 0,
    credit: Number(raw.credit) || 0,
    indexRef: raw.indexRef ?? '',
    remark: raw.remark ?? '',
  }
}

watch(() => props.allResponses, () => loadRows(), { immediate: true })

// ─── Computed: 借贷平衡 ────────────────────────────────────────────────────

const debitTotal = computed(() => rows.value.reduce((sum, r) => sum + (r.debit || 0), 0))
const creditTotal = computed(() => rows.value.reduce((sum, r) => sum + (r.credit || 0), 0))
const isBalanced = computed(() => Math.abs(debitTotal.value - creditTotal.value) < 0.005)

// ─── 合计行 ────────────────────────────────────────────────────────────────

function getSummary({ columns }: { columns: any[] }): string[] {
  return columns.map((col, idx) => {
    if (idx === 0) return ''
    if (idx === 1) return '合计'
    if (col.property === 'debit') return fmtAmt(debitTotal.value)
    if (col.property === 'credit') return fmtAmt(creditTotal.value)
    return ''
  })
}

// ─── CRUD ──────────────────────────────────────────────────────────────────

function handleAddRow(): void {
  const newRow: AdjustmentRow = {
    rowId: `adj-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    entryType: 'AJE',
    accountCode: '',
    accountName: '',
    summary: '',
    debit: 0,
    credit: 0,
    indexRef: '',
    remark: '',
  }
  rows.value.push(newRow)
}

function handleRemove(rowId: string): void {
  const idx = rows.value.findIndex((r) => r.rowId === rowId)
  if (idx >= 0) rows.value.splice(idx, 1)
}

// ─── Save → EventBus publish ───────────────────────────────────────────────

async function handleSave(): Promise<void> {
  try {
    // 保存行数据到 checklist_responses
    await http.post(`/api/workpapers/${props.wpId}/checklist-responses`, {
      items: [
        { item_id: ITEM_ID, remark: JSON.stringify(rows.value) },
        { item_id: 'I3-3-audit-note', remark: auditNote.value },
      ],
    })

    // Client-side EventBus: adjustment:created → I3审定表/A13同步
    publishAdjustmentCreated()

    // Server-side EventBus publish（降级：失败不阻塞保存）
    await http.post(`/api/projects/${props.projectId}/events/publish`, {
      event_type: 'adjustment:created',
      payload: {
        wp_code: 'I3',
        source: 'I3-3',
        rows: rows.value,
        debitTotal: debitTotal.value,
        creditTotal: creditTotal.value,
        isBalanced: isBalanced.value,
      },
    }).catch(() => { /* EventBus发布失败不阻塞保存 */ })

    ElMessage.success('调整分录已保存')
    emit('save')
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.message || '保存失败')
  }
}

// ─── publishAdjustmentCreated（CustomEvent on window → A13同步）──────────────

/**
 * 发布 'adjustment:created' CustomEvent 至 window。
 * Payload:
 *   - wpCode: 'I3'
 *   - entries: 调整分录行数组（含借贷/科目/摘要等）
 *   - adjustmentType: 'AJE' | 'RJE' | 'MIXED'
 *   - debitTotal / creditTotal / isBalanced
 *
 * 消费方：I3审定表（同步AJE/RJE累计）、A13错报汇总
 */
function publishAdjustmentCreated(): void {
  if (rows.value.length === 0) return

  // 判定 adjustmentType：全AJE/全RJE/混合
  const types = new Set(rows.value.map((r) => r.entryType))
  const adjustmentType: 'AJE' | 'RJE' | 'MIXED' =
    types.size === 1 ? (types.has('RJE') ? 'RJE' : 'AJE') : 'MIXED'

  const event = new CustomEvent('adjustment:created', {
    detail: {
      wpCode: 'I3',
      adjustmentType,
      entries: rows.value.map((r) => ({
        rowId: r.rowId,
        entryType: r.entryType,
        accountCode: r.accountCode,
        accountName: r.accountName,
        summary: r.summary,
        debit: r.debit,
        credit: r.credit,
      })),
      debitTotal: debitTotal.value,
      creditTotal: creditTotal.value,
      isBalanced: isBalanced.value,
    },
  })
  window.dispatchEvent(event)
}

// ─── Push to A13 错报汇总 ──────────────────────────────────────────────────

async function handlePushA13(): Promise<void> {
  if (rows.value.length === 0) {
    ElMessage.warning('暂无分录可推送')
    return
  }
  try {
    await ElMessageBox.confirm(
      `将 ${rows.value.length} 笔调整分录推送至A13错报汇总，确认？`,
      '推送确认',
      { confirmButtonText: '确认推送', cancelButtonText: '取消', type: 'info' },
    )

    // Client-side EventBus: a13:push-misstatement
    window.dispatchEvent(new CustomEvent('a13:push-misstatement', {
      detail: {
        wpCode: 'I3',
        source: 'I3-3',
        entries: rows.value.map((r) => ({
          entryType: r.entryType,
          accountCode: r.accountCode,
          accountName: r.accountName,
          summary: r.summary,
          debit: r.debit,
          credit: r.credit,
        })),
      },
    }))

    // Server-side EventBus（降级：失败不阻塞）
    await http.post(`/api/projects/${props.projectId}/events/publish`, {
      event_type: 'adjustment:push-to-a13',
      payload: {
        wp_code: 'I3',
        source: 'I3-3',
        entries: rows.value.map((r) => ({
          entryType: r.entryType,
          accountCode: r.accountCode,
          accountName: r.accountName,
          summary: r.summary,
          debit: r.debit,
          credit: r.credit,
        })),
      },
    }).catch(() => { /* silent */ })

    ElMessage.success('已推送至A13错报汇总')
  } catch (err: any) {
    if (err === 'cancel' || err?.toString?.().includes('cancel')) return
    ElMessage.error('推送失败')
  }
}

// ─── Navigation ───────────────────────────────────────────────────────────

function navigateTo(wpCode: string): void {
  emit('navigate-sheet', wpCode)
}

// ─── Import/Export ─────────────────────────────────────────────────────────

function handleImportExport(command: string): void {
  switch (command) {
    case 'export-template':
      doExport('template')
      break
    case 'export-data':
      doExport('data')
      break
    case 'import-data':
      fileInputRef.value?.click()
      break
  }
}

async function doExport(type: 'template' | 'data'): Promise<void> {
  try {
    const endpoint = type === 'template' ? 'export-template' : 'export-data'
    const response = await http.post(
      `/api/workpapers/${props.wpId}/i3/${endpoint}`,
      null,
      { params: { sheet: 'I3-3' }, responseType: 'blob' },
    )
    const timestamp = new Date().toISOString().slice(0, 10)
    const filename = type === 'template'
      ? 'I3-3_调整分录_模板.xlsx'
      : `I3-3_调整分录_数据_${timestamp}.xlsx`
    const url = URL.createObjectURL(new Blob([response.data]))
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success(`${type === 'template' ? '模板' : '数据'}导出成功`)
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.message || '导出失败')
  }
}

async function handleFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  input.value = '' // reset for re-select

  try {
    await ElMessageBox.confirm(
      `即将导入文件「${file.name}」到 I3-3 调整分录，已有数据将被覆盖。确认？`,
      '导入确认',
      { confirmButtonText: '确认导入', cancelButtonText: '取消', type: 'warning' },
    )
    const formData = new FormData()
    formData.append('file', file)
    const response = await http.post(
      `/api/workpapers/${props.wpId}/i3/import-data`,
      formData,
      { params: { sheet: 'I3-3' }, headers: { 'Content-Type': 'multipart/form-data' } },
    )
    const data = response.data?.data ?? response.data
    ElMessage.success(`成功导入 ${data?.imported_count ?? 0} 行`)
    loadRows()
  } catch (err: any) {
    if (err === 'cancel' || err?.toString?.().includes('cancel')) return
    ElMessage.error(err?.response?.data?.message || '导入失败')
  }
}

// ─── 格式化金额 ───────────────────────────────────────────────────────────

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i3-tab-adjustment {
  padding: 16px;
  font-size: 13px;
}

/* 方法论上下文 - 琥珀色左边线 */
.methodology-block {
  border-left: 4px solid #f59e0b;
  background: #fffbeb;
  padding: 12px 16px;
  margin-bottom: 16px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
}
.methodology-block p { margin: 0 0 6px; }
.methodology-block ul {
  margin: 0;
  padding-left: 18px;
  line-height: 1.8;
}

/* section标题栏 */
.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
}
.title-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 表格 */
.adj-table {
  font-size: 13px;
}
.adj-table :deep(.el-table__footer) {
  font-weight: 600;
}
.amount-cell {
  font-variant-numeric: tabular-nums;
}

/* 借贷平衡栏 */
.balance-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 14px;
  margin-top: 12px;
  border-radius: 4px;
  font-size: 13px;
}
.balance-ok {
  background: var(--el-color-success-light-9, #f0f9eb);
}
.balance-err {
  background: var(--el-color-danger-light-9, #fef0f0);
}
.diff-warn {
  color: var(--el-color-danger);
  font-weight: 600;
}

/* 审计说明卡片 */
.note-card {
  margin-top: 12px;
}

/* 编制提示 */
.compile-hint {
  margin-top: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.compile-hint summary {
  cursor: pointer;
  font-weight: 500;
}
.compile-hint ul {
  padding-left: 20px;
  margin-top: 8px;
  line-height: 1.8;
}

/* 跨底稿联动栏 */
.cross-ref-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  margin-top: 12px;
  margin-bottom: 4px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  border: 1px dashed var(--el-border-color);
  font-size: 12px;
}
.cross-ref-label {
  color: var(--el-text-color-secondary);
  font-weight: 500;
}
.cross-ref-desc {
  color: var(--el-text-color-regular);
  margin-right: 12px;
}
</style>
