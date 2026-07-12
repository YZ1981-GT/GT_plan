<template>
  <div class="i2-adjustment">
    <!-- Section Header -->
    <div class="section-header">
      <span class="section-title">I2-3 调整分录汇总</span>
      <div class="section-actions">
        <el-button size="small" type="primary" text @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI
        </el-button>
        <el-button size="small" type="default" text @click="handleReview">
          复核
        </el-button>
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
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, inject } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'

// ─── Props & Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  sheetName: string
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveResponse: (sheetCode: string, data: Record<string, any>) => Promise<void>
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

watch(() => props.allResponses, () => loadData(), { immediate: true })

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

// ─── AI / Review ─────────────────────────────────────────────────────────────

function handleAiGenerate() {
  console.log('[I2-Adjustment] AI generate')
}

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
</style>
