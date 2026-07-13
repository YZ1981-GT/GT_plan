<template>
  <div class="i2-adjustment">
    <!-- Section Header -->
    <div class="section-header">
      <span class="section-title">I2-3 调整分录汇总</span>
      <div class="section-actions">
        <el-button size="small" type="default" text @click="handleReview">
          复核
        </el-button>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：汇总开发支出相关审计调整与重分类分录，确认每笔分录借贷平衡、依据充分且过账至审定表准确。" />

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 逐笔录入调整分录科目、借贷金额与摘要，区分 AJE(会计差错更正)与 RJE(列报重分类)；</p>
        <p>2. 校验每笔分录借方合计=贷方合计，确保借贷平衡并附充分调整依据；</p>
        <p>3. 依据 CAS6《无形资产》确认资本化/费用化调整对开发支出归集的影响。</p>
      </div>
    </details>

    <!-- 索引工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-right">
        <GtIndexChip value="wp:I2" :context-project-id="props.projectId" />
        <el-tag size="small" type="info">共 {{ entries.length }} 行</el-tag>
      </div>
    </div>

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p><strong>调整分录汇总：</strong>记录审计过程中发现的需要调整或重分类的分录。</p>
      <p>AJE（审计调整分录）：修正被审计单位的会计差错。RJE（重分类分录）：报表列报调整。</p>
      <p>借贷平衡校验：每笔分录的借方合计必须等于贷方合计。</p>
    </div>

    <!-- 调整分录表 -->
    <el-table
      :data="entries"
      border
      size="small"
      class="adjustment-table"
    >
      <el-table-column label="序号" width="60" align="center">
        <template #default="{ $index }">
          {{ $index + 1 }}
        </template>
      </el-table-column>

      <el-table-column label="日期" min-width="130">
        <template #default="{ row, $index }">
          <el-date-picker
            v-model="row.date"
            type="date"
            size="small"
            value-format="YYYY-MM-DD"
            placeholder="选择日期"
            style="width: 100%"
            @change="markDirty"
          />
        </template>
      </el-table-column>

      <el-table-column label="科目" min-width="160">
        <template #default="{ row }">
          <el-input v-model="row.account" size="small" placeholder="科目名称" @change="markDirty" />
        </template>
      </el-table-column>

      <el-table-column label="借方" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-model="row.debit"
            size="small"
            :controls="false"
            :min="0"
            @change="markDirty"
          />
        </template>
      </el-table-column>

      <el-table-column label="贷方" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-model="row.credit"
            size="small"
            :controls="false"
            :min="0"
            @change="markDirty"
          />
        </template>
      </el-table-column>

      <el-table-column label="摘要" min-width="180">
        <template #default="{ row }">
          <el-input v-model="row.summary" size="small" placeholder="摘要说明" @change="markDirty" />
        </template>
      </el-table-column>

      <el-table-column label="分录类型" width="110" align="center">
        <template #default="{ row }">
          <el-select v-model="row.entryType" size="small" style="width: 90px" @change="markDirty">
            <el-option label="AJE" value="AJE" />
            <el-option label="RJE" value="RJE" />
          </el-select>
        </template>
      </el-table-column>

      <el-table-column label="附件" width="70" align="center">
        <template #default="{ row }">
          <el-button size="small" type="primary" text @click="handleAttachment(row)">
            📎
          </el-button>
        </template>
      </el-table-column>

      <el-table-column label="操作" width="70" align="center">
        <template #default="{ $index }">
          <el-button size="small" type="danger" text @click="removeEntry($index)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 操作按钮 -->
    <div class="table-actions">
      <el-button size="small" type="primary" plain @click="addEntry">
        + 新增分录
      </el-button>
      <el-button size="small" type="success" @click="handleSave">
        保存
      </el-button>
    </div>

    <!-- 借贷平衡校验 -->
    <el-card class="balance-card" shadow="never">
      <div class="balance-row">
        <span class="balance-label">借方合计：</span>
        <span class="balance-value">{{ fmtAmount(totalDebit) }}</span>
        <span class="balance-label" style="margin-left: 32px">贷方合计：</span>
        <span class="balance-value">{{ fmtAmount(totalCredit) }}</span>
        <span class="balance-label" style="margin-left: 32px">差额：</span>
        <span :class="['balance-value', { 'balance-error': !isBalanced }]">
          {{ fmtAmount(balanceDiff) }}
        </span>
        <el-tag v-if="isBalanced" type="success" size="small" style="margin-left: 12px">借贷平衡 ✓</el-tag>
        <el-tag v-else type="danger" size="small" style="margin-left: 12px">借贷不平衡 ✗</el-tag>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><span>审计说明</span></template>
      <el-input type="textarea" :model-value="auditNote" :disabled="isReadonly" :autosize="{ minRows: 5 }" placeholder="记录审计过程、发现的问题及处理..." @change="saveAuditNote" />
    </el-card>
    <el-card shadow="never" class="audit-conclusion-card">
      <template #header><span>审计结论</span></template>
      <el-input type="textarea" :model-value="auditConclusion" :disabled="isReadonly" :autosize="{ minRows: 3 }" placeholder="填写审计结论..." @change="saveAuditConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, inject, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'

// ─── Props & Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  sheetName: string
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveResponse: (sheetCode: string, data: Record<string, any>) => Promise<void>
  isReadonly?: boolean
}>()

const emit = defineEmits<{
  'save': []
  'navigate-sheet': [sheetName: string]
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

// ─── Types ───────────────────────────────────────────────────────────────────

interface AdjustmentEntry {
  date: string
  account: string
  debit: number
  credit: number
  summary: string
  entryType: 'AJE' | 'RJE'
  attachment: string
}

// ─── State ───────────────────────────────────────────────────────────────────

const entries = ref<AdjustmentEntry[]>([])
const isDirty = ref(false)

// ─── Init: Load from allResponses ────────────────────────────────────────────

function loadData() {
  const raw = props.allResponses.get('I2-3-entries')
  if (raw) {
    try {
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : (raw.remark ? JSON.parse(raw.remark) : raw)
      if (Array.isArray(parsed)) {
        entries.value = parsed.map((e: any) => ({
          date: e.date ?? '',
          account: e.account ?? '',
          debit: Number(e.debit) || 0,
          credit: Number(e.credit) || 0,
          summary: e.summary ?? '',
          entryType: e.entryType === 'RJE' ? 'RJE' : 'AJE',
          attachment: e.attachment ?? '',
        }))
        return
      }
    } catch { /* ignore */ }
  }
  entries.value = []
}

// ─── 审计说明 / 审计结论 ───
const AUDIT_NOTE_KEY = 'I2-3-audit-note'
const AUDIT_CONCLUSION_KEY = 'I2-3-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
function readRemark(key: string): string { const raw = props.allResponses.get(key); if (raw == null) return ''; return typeof raw === 'string' ? raw : (raw.remark ?? '') }
function hydrateAudit() { auditNote.value = readRemark(AUDIT_NOTE_KEY); auditConclusion.value = readRemark(AUDIT_CONCLUSION_KEY) }
function saveAuditNote(val: string) { auditNote.value = val; void props.saveResponse('I2-3', { [AUDIT_NOTE_KEY]: val }) }
function saveAuditConclusion(val: string) { auditConclusion.value = val; void props.saveResponse('I2-3', { [AUDIT_CONCLUSION_KEY]: val }) }

watch(() => props.allResponses, () => { loadData(); hydrateAudit() }, { immediate: true })
onMounted(hydrateAudit)

// ─── Computed ────────────────────────────────────────────────────────────────

const totalDebit = computed(() => entries.value.reduce((s, e) => s + (e.debit || 0), 0))
const totalCredit = computed(() => entries.value.reduce((s, e) => s + (e.credit || 0), 0))
const balanceDiff = computed(() => totalDebit.value - totalCredit.value)
const isBalanced = computed(() => Math.abs(balanceDiff.value) < 0.01)

// ─── Actions ─────────────────────────────────────────────────────────────────

function addEntry() {
  entries.value.push({
    date: '',
    account: '',
    debit: 0,
    credit: 0,
    summary: '',
    entryType: 'AJE',
    attachment: '',
  })
  isDirty.value = true
}

function removeEntry(index: number) {
  entries.value.splice(index, 1)
  isDirty.value = true
}

function markDirty() {
  isDirty.value = true
}

async function handleSave() {
  await props.saveResponse('I2-3', { 'I2-3-entries': JSON.stringify(entries.value) })
  isDirty.value = false
  emit('save')
  ElMessage.success('调整分录已保存')
}

function handleAttachment(row: AdjustmentEntry) {
  ElMessage.info('附件上传功能开发中')
}

// ─── Review ──────────────────────────────────────────────────────────────────

function handleReview() {
  openReviewDialog('I2-3-调整分录')
}

// ─── Formatter ───────────────────────────────────────────────────────────────

function fmtAmount(value: number | null | undefined): string {
  if (value == null) return '-'
  if (Math.abs(value) < 0.005) return '-'
  return value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i2-adjustment {
  font-size: var(--wp-font-size, 13px);
  padding: 16px;
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
}
.section-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}
.methodology-context {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 14px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.7;
}
.methodology-context p { margin: 0; }
.methodology-context strong { color: #78350f; }
.adjustment-table {
  font-size: var(--wp-font-size, 13px);
  margin-bottom: 12px;
}
.table-actions {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}
.balance-card {
  margin-top: 8px;
}
.balance-row {
  display: flex;
  align-items: center;
  font-size: var(--wp-font-size, 13px);
}
.balance-label {
  color: #606266;
}
.balance-value {
  font-weight: 600;
  color: #303133;
}
.balance-error {
  color: #f56c6c;
}
.objective-alert { margin-bottom: 12px; }
.guidance-details { margin-bottom: 12px; font-size: 12px; color: var(--el-text-color-secondary); background: #f9fafb; border: 1px solid #ebeef5; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 600; color: #374151; }
.guidance-details .guidance-content { margin-top: 8px; line-height: 1.7; }
.guidance-details .guidance-content p { margin: 0 0 4px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; margin-bottom: 10px; }
.tab-toolbar .toolbar-right { display: flex; align-items: center; gap: 8px; }
.audit-note-card, .audit-conclusion-card { margin-top: 16px; }
</style>
