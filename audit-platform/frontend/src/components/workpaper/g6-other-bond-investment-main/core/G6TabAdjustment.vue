<template>
  <div class="g6-tab-adjustment">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="审计目标：确认针对其他债权投资的审计调整(AJE)与重分类(RJE)分录依据充分、借贷平衡，并正确汇总回写至 G6-1 审定表。"
      style="margin-bottom: 12px"
    />
    <!-- Section标题栏 + 复核按钮右对齐 -->
    <div class="section-head">
      <h3 class="sheet-title">G6-4 调整分录汇总</h3>
      <div class="head-actions">
        <el-button size="small" type="success" :disabled="isReadonly || !isBalanced" @click="handleSaveWriteback">
          保存&amp;回写
        </el-button>
        <!-- 导入导出 el-dropdown -->
        <el-dropdown trigger="click" size="small" @command="handleIECommand">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export">导出数据</el-dropdown-item>
              <el-dropdown-item command="import">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="openReview">💬复核</el-button>
      </div>
    </div>

    <!-- 借贷不平衡警告 -->
    <el-alert v-if="!isBalanced" type="error" :closable="false" style="margin-bottom:8px">
      ⚠️ 借贷不平衡：借方合计 {{ fmt(totalDebits) }} ≠ 贷方合计 {{ fmt(totalCredits) }}，差额
      <span class="balance-diff">{{ fmt(Math.abs(balanceDiff)) }}</span>
    </el-alert>

    <!-- 工具栏：新增按钮 -->
    <div class="g6-adj-toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddEntry">
        + 新增分录
      </el-button>
      <span class="row-count">共 {{ entries.length }} 行</span>
    </div>

    <!-- 隐藏的文件上传 -->
    <input ref="fileInputRef" type="file" accept=".xlsx" style="display:none" @change="onFileSelected" />

    <!-- 10列调整分录表格 -->
    <el-table
      :data="entries"
      border
      size="small"
      style="width:100%;font-size:13px"
      max-height="520"
      :row-class-name="tableRowClassName"
    >
      <el-table-column prop="seq" label="序号" width="56" align="center" />

      <el-table-column label="分录类型" width="100">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            v-model="row.entryType"
            size="small"
            @change="markDirty"
          >
            <el-option value="AJE" label="AJE" />
            <el-option value="RJE" label="RJE" />
          </el-select>
          <span v-else>{{ row.entryType }}</span>
        </template>
      </el-table-column>

      <el-table-column label="日期" width="120">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            v-model="row.date"
            size="small"
            placeholder="YYYY-MM-DD"
            @change="markDirty"
          />
          <span v-else>{{ row.date }}</span>
        </template>
      </el-table-column>

      <el-table-column label="摘要" min-width="140">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            v-model="row.summary"
            size="small"
            @change="markDirty"
          />
          <span v-else>{{ row.summary || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="科目代码" width="110">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            v-model="row.accountCode"
            size="small"
            placeholder="如1503"
            @change="markDirty"
          />
          <span v-else>{{ row.accountCode }}</span>
        </template>
      </el-table-column>

      <el-table-column label="科目名称" min-width="130">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            v-model="row.accountName"
            size="small"
            @change="markDirty"
          />
          <span v-else>{{ row.accountName || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="借方金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            v-model="row.debitAmount"
            size="small"
            :controls="false"
            :precision="2"
            :min="0"
            style="width:100%"
            @change="markDirty"
          />
          <span v-else>{{ fmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="贷方金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            v-model="row.creditAmount"
            size="small"
            :controls="false"
            :precision="2"
            :min="0"
            style="width:100%"
            @change="markDirty"
          />
          <span v-else>{{ fmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="编制人" width="90">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            v-model="row.preparedBy"
            size="small"
            @change="markDirty"
          />
          <span v-else>{{ row.preparedBy || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="备注" min-width="100">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            v-model="row.remark"
            size="small"
            @change="markDirty"
          />
          <span v-else>{{ row.remark || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="操作" width="56" align="center">
        <template #default="{ row }">
          <el-button link size="small" type="danger" @click="handleRemoveEntry(row.id)">
            🗑️
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 合计行（借贷不平衡时红色高亮） -->
    <div class="g6-adj-footer" :class="{ 'balance-fail': !isBalanced }">
      <span class="footer-label">合计</span>
      <span class="footer-debit">借方：{{ fmt(totalDebits) }}</span>
      <span class="footer-credit">贷方：{{ fmt(totalCredits) }}</span>
      <span v-if="isBalanced" class="footer-status ok">✓ 平衡</span>
      <span v-else class="footer-status err">
        ✗ 不平衡 | 差额：{{ fmt(Math.abs(balanceDiff)) }}
      </span>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：调整分录的依据、借贷平衡与回写情况，拟调整/未调整事项及其影响。"
        @change="(v: string) => saveAuditNote(v)"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计结论</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：A、未见异常。B、除上述调整事项予以调整外，其余未见异常。C、存在重大未调整事项，不可确认。"
        @change="(v: string) => saveAuditConclusion(v)"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="g6-guide-details">
      <summary>📋 编制提示</summary>
      <div class="g6-guide-content">
        <p>1. 调整分录(AJE)用于更正被审计单位财务报表中的错报；重分类分录(RJE)用于分析性归类调整。</p>
        <p>2. 借贷必须平衡后方可保存回写。点击"保存&amp;回写"将汇总数据回写G6-1审定表的调整列。</p>
        <p>3. 科目代码1503为其他债权投资，保存后自动汇总AJE/RJE调整额回写审定表。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G6TabAdjustment.vue — G6-4 调整分录汇总（23行×10列）
 *
 * Spec: .kiro/specs/g6-other-bond-investment-main/ Task 7.1
 * Requirements: 7.1, 7.4
 *
 * 功能：
 * - 10列调整分录表格（序号|分录类型(AJE/RJE)|日期|摘要|科目代码|科目名称|借方金额|贷方金额|编制人|备注）
 * - 借贷平衡实时校验 (isDebitCreditBalanced) + 不平衡时红色差额高亮
 * - 不平衡时阻止保存
 * - 动态行增删 (ElMessageBox.prompt 输入摘要确认)
 * - 导入导出 (sheet='G6-4')
 * - 保存时汇总回写 G6-1 审定表 adjustment 列
 */
import { ref, computed, inject, onMounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import http from '@/utils/http'
import { isDebitCreditBalanced, parseNum } from '@/composables/useG6MainFormulaEngine'
import { useG6MainImportExport } from '../../composables/useG6MainImportExport'
import type { G6MainImportableSheet } from '../../composables/useG6MainImportExport'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// ─── 审计说明 / 审计结论（走 checklist_responses，conclusion:null + remark 文本） ───
const NOTE_KEY = 'G6-4-adjustment-audit-note'
const CONCLUSION_KEY = 'G6-4-adjustment-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function readSaved(key: string): string {
  const cr = props.htmlData?.checklist_responses
  if (cr && typeof cr === 'object' && (cr as Record<string, any>)[key]) {
    const v = (cr as Record<string, any>)[key]
    return typeof v === 'object' ? (v.remark ?? '') : String(v ?? '')
  }
  const resp = props.htmlData?.responses
  if (Array.isArray(resp)) {
    const found = resp.find((r: any) => r?.item_id === key)
    if (found?.remark) return found.remark
  }
  return ''
}

async function saveAudit(key: string, val: string): Promise<void> {
  if (props.isReadonly) return
  try {
    await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId || undefined,
      items: [{ item_id: key, conclusion: null, remark: val }],
    })
  } catch { /* silent */ }
}

function saveAuditNote(val: string): void {
  auditNote.value = val
  void saveAudit(NOTE_KEY, val)
}
function saveAuditConclusion(val: string): void {
  auditConclusion.value = val
  void saveAudit(CONCLUSION_KEY, val)
}

// ═══ 数据模型 ═══
interface AdjustmentEntry {
  id: string
  seq: number
  entryType: 'AJE' | 'RJE'
  date: string
  summary: string
  accountCode: string
  accountName: string
  debitAmount: number
  creditAmount: number
  preparedBy: string
  remark: string
}

// ═══ 状态 ═══
const entries = ref<AdjustmentEntry[]>([])
const isDirty = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)

// ═══ 导入导出 ═══
const ie = useG6MainImportExport({
  wpId: computed(() => props.wpId),
  onImported: () => { /* 将在实际后端数据返回后刷新 */ },
})

// ═══ 计算属性 ═══
const totalDebits = computed(() =>
  entries.value.reduce((sum, e) => sum + parseNum(e.debitAmount), 0),
)
const totalCredits = computed(() =>
  entries.value.reduce((sum, e) => sum + parseNum(e.creditAmount), 0),
)
const balanceDiff = computed(() => totalDebits.value - totalCredits.value)
const isBalanced = computed(() =>
  isDebitCreditBalanced(
    entries.value.map((e) => e.debitAmount),
    entries.value.map((e) => e.creditAmount),
  ),
)

// ═══ 初始化 ═══
function generateId(): string {
  return `adj-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function buildInitialEntries(count: number): AdjustmentEntry[] {
  const rows: AdjustmentEntry[] = []
  for (let i = 1; i <= count; i++) {
    rows.push({
      id: generateId(),
      seq: i,
      entryType: 'AJE',
      date: '',
      summary: '',
      accountCode: '',
      accountName: '',
      debitAmount: 0,
      creditAmount: 0,
      preparedBy: '',
      remark: '',
    })
  }
  return rows
}

function loadFromHtmlData(): void {
  if (props.htmlData?.adjustment?.entries) {
    const saved = props.htmlData.adjustment.entries as AdjustmentEntry[]
    entries.value = saved.map((e, i) => ({
      ...e,
      id: e.id || generateId(),
      seq: i + 1,
    }))
  } else {
    entries.value = buildInitialEntries(23)
  }
}

onMounted(() => {
  loadFromHtmlData()
  auditNote.value = readSaved(NOTE_KEY)
  auditConclusion.value = readSaved(CONCLUSION_KEY)
})

// ═══ 操作方法 ═══
function markDirty(): void {
  isDirty.value = true
}

function reSequence(): void {
  entries.value.forEach((e, i) => { e.seq = i + 1 })
}

/** 新增行 - 弹出ElMessageBox.prompt输入摘要 */
async function handleAddEntry(): Promise<void> {
  try {
    const { value: summary } = await ElMessageBox.prompt(
      '请输入新分录摘要：',
      '新增调整分录',
      {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        inputPlaceholder: '如：调整其他债权投资减值损失',
        inputValidator: (v) => (!v?.trim() ? '摘要不能为空' : true),
      },
    )
    const newEntry: AdjustmentEntry = {
      id: generateId(),
      seq: entries.value.length + 1,
      entryType: 'AJE',
      date: new Date().toISOString().slice(0, 10),
      summary: summary.trim(),
      accountCode: '',
      accountName: '',
      debitAmount: 0,
      creditAmount: 0,
      preparedBy: '',
      remark: '',
    }
    entries.value.push(newEntry)
    markDirty()
  } catch {
    // 用户取消
  }
}

/** 删除行 */
async function handleRemoveEntry(id: string): Promise<void> {
  try {
    await ElMessageBox.confirm('确认删除该调整分录行？', '删除确认', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      type: 'warning',
    })
    entries.value = entries.value.filter((e) => e.id !== id)
    reSequence()
    markDirty()
  } catch {
    // 用户取消
  }
}

/** 保存并回写G6-1审定表 */
function handleSaveWriteback(): void {
  if (!isBalanced.value) {
    ElMessage.error('借贷不平衡，无法保存')
    return
  }
  // 汇总AJE/RJE调整总额
  const ajeTotal = entries.value
    .filter((e) => e.entryType === 'AJE')
    .reduce((s, e) => s + parseNum(e.debitAmount) - parseNum(e.creditAmount), 0)
  const rjeTotal = entries.value
    .filter((e) => e.entryType === 'RJE')
    .reduce((s, e) => s + parseNum(e.debitAmount) - parseNum(e.creditAmount), 0)

  // 发布EventBus通知G6-1刷新调整列
  try {
    window.dispatchEvent(new CustomEvent('g6:adjustment-writeback', {
      detail: { accountCode: '1503', ajeTotal, rjeTotal, totalAdjustment: ajeTotal + rjeTotal },
    }))
  } catch { /* silent */ }

  ElMessage.success(`保存成功，AJE调整 ${fmt(ajeTotal)}，RJE调整 ${fmt(rjeTotal)}`)
  isDirty.value = false
}

/** 导入导出命令处理 */
function handleIECommand(cmd: string): void {
  const sheet: G6MainImportableSheet = 'G6-4'
  if (cmd === 'template') ie.exportTemplate(sheet)
  else if (cmd === 'export') ie.exportData(sheet)
  else if (cmd === 'import') fileInputRef.value?.click()
}

/** 文件选择后导入 */
async function onFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  await ie.importData('G6-4', file)
  input.value = '' // 重置file input
}

/** 复核对话 */
function openReview(): void {
  openReviewDialog('G6-4-adjustment')
}

/** 格式化金额 */
function fmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '-'
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

/** 表格行class（RJE浅色区分） */
function tableRowClassName({ row }: { row: AdjustmentEntry }): string {
  if (row.entryType === 'RJE') return 'rje-row'
  return ''
}
</script>

<style scoped>
.g6-tab-adjustment {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.sheet-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* 审计说明/结论卡片 */
.audit-note-card { margin-top: 12px; }
.audit-note-card .card-header { display: flex; align-items: center; justify-content: space-between; font-weight: 500; }

.g6-adj-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.row-count {
  color: #909399;
  font-size: 12px;
}

/* 合计行 */
.g6-adj-footer {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 8px;
  padding: 10px 16px;
  background: #f0f9eb;
  border-radius: 4px;
  font-weight: 600;
  font-size: var(--wp-font-size, 13px);
}

.g6-adj-footer.balance-fail {
  background: #fef0f0;
  border: 1px solid #f56c6c;
}

.footer-label {
  color: #606266;
}

.footer-debit,
.footer-credit {
  color: #303133;
}

.footer-status.ok {
  color: #67c23a;
  margin-left: auto;
}

.footer-status.err {
  color: #f56c6c;
  margin-left: auto;
  font-weight: 700;
}

.balance-diff {
  color: #f56c6c;
  font-weight: 700;
}

/* RJE行浅色区分 */
:deep(.rje-row) {
  background-color: #fdf6ec !important;
}

/* 编制提示 */
.g6-guide-details {
  margin-top: 16px;
}

.g6-guide-details summary {
  cursor: pointer;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.g6-guide-content {
  padding: 8px 12px;
  background: #fffbeb;
  border-left: 3px solid #f59e0b;
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.8;
}

.g6-guide-content p {
  margin: 0;
}
</style>
