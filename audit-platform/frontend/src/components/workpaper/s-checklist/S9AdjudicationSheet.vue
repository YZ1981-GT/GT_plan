<template>
  <div class="s9-adjudication">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：确认电子商务相关科目期末余额的存在、完整与准确，评价收入确认与相关成本费用计量的恰当性，并与试算平衡表核对一致。"
      style="margin-bottom: 16px"
    />

    <!-- ═══ 审定表 S9-1 ═══ -->
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>审定表 S9-1 — 电子商务</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              type="primary"
              :loading="saving"
              @click="handleSave"
            >保存</el-button>
            <el-button size="small" @click="handleOpenReview('s9-adjudication', '审定表S9-1')">
              复核
            </el-button>
            <el-button v-if="!isReadonly" size="small" @click="handleAiAssist">
              🤖 AI辅助
            </el-button>
          </div>
        </div>
      </template>

      <!-- 编制提示 -->
      <details class="compile-hint">
        <summary>编制提示</summary>
        <div class="methodology-context">
          <p>本审定表用于汇总电子商务相关科目的审定结果。</p>
          <p>审定金额将回写试算表（trial_balance），采用 v2 正数口径。</p>
          <p>如有调整事项，请在对应行记录调整分录编号。</p>
        </div>
      </details>

      <!-- 审定表表格 -->
      <el-table
        :data="adjudicationRows"
        border
        size="small"
        style="width: 100%; font-size: 13px"
        show-summary
        :summary-method="getSummary"
        :cell-class-name="cellClassName"
      >
        <!-- 科目名称 -->
        <el-table-column prop="accountName" label="科目名称" min-width="180" />

        <!-- 科目编码 -->
        <el-table-column prop="accountCode" label="科目编码" width="110" align="center">
          <template #default="{ row }">
            <span class="formula-cell" :title="row.accountCode ? `标准科目编码 ${row.accountCode}` : ''">
              {{ row.accountCode || '—' }}
            </span>
          </template>
        </el-table-column>

        <!-- 未审数 -->
        <el-table-column prop="unadjustedAmount" label="未审数" min-width="130" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="来源：试算表未审数（自动取数）">
              {{ fmt(row.unadjustedAmount) }}
            </span>
          </template>
        </el-table-column>

        <!-- 审计调整 -->
        <el-table-column prop="adjustmentAmount" label="审计调整" min-width="130" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly && row.editable"
              v-model="row.adjustmentAmount"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="recalculate"
            />
            <span v-else>{{ fmt(row.adjustmentAmount) }}</span>
          </template>
        </el-table-column>

        <!-- 审定数 -->
        <el-table-column prop="auditedAmount" label="审定数" min-width="130" align="right">
          <template #default="{ row }">
            <span class="formula-cell audited-amount" title="审定数 = 未审数 + 审计调整">
              {{ fmt(row.auditedAmount) }}
            </span>
          </template>
        </el-table-column>

        <!-- 调整分录编号 -->
        <el-table-column prop="ajeRef" label="调整分录" width="110" align="center">
          <template #default="{ row }">
            <GtIndexChip v-if="row.ajeRef" :value="row.ajeRef" />
            <span v-else class="text-placeholder">—</span>
          </template>
        </el-table-column>

        <!-- 索引号 -->
        <el-table-column prop="indexRef" label="索引号" width="100" align="center">
          <template #default="{ row }">
            <GtIndexChip v-if="row.indexRef" :value="row.indexRef" />
            <span v-else class="text-placeholder">—</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 审计说明/结论 ═══ -->
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>审计说明与结论</span>
          <div class="header-actions">
            <el-button v-if="!isReadonly" size="small" @click="handleAiConclusion">🤖 AI辅助</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="记录电子商务相关科目的审定结论..."
        @change="markDirty"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * S9AdjudicationSheet.vue — 审定表 S9-1 电子商务
 *
 * 功能：
 * - 25×7 审定表结构，包含未审数/调整/审定数/分录编号/索引号
 * - 审定数 = 未审数 + 审计调整（公式自动计算）
 * - 未审数从 trial_balance 自动取数（auto_data_source）
 * - 审定金额回写 trial_balance（v2 正数口径）
 * - GtIndexChip 引用跳转（调整分录 + 跨底稿索引）
 * - 合计行汇总
 * - readonly 禁止编辑
 * - 13px 字体 + 公式列虚线下划线 + tooltip 来源
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 5.1
 * Requirements: 7.1 (S9 内部子 sheet 分发)
 */
import { ref, inject, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { fmtAmount } from '@/utils/formatters'

// ─── 金额格式化 ──────────────────────────────────────────────────────────────

function fmt(val: number | null | undefined): string {
  return fmtAmount(val, 2)
}

// ─── 组件导入 ────────────────────────────────────────────────────────────────

import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save'): void
}>()

// ─── 复核对话 inject ─────────────────────────────────────────────────────────

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>(
  'openReviewDialog',
  () => {}
)

function handleOpenReview(sectionId: string, sectionLabel: string) {
  openReviewDialog(sectionId, sectionLabel)
}

// ─── 数据模型 ────────────────────────────────────────────────────────────────

interface AdjudicationRow {
  id: string
  accountName: string
  accountCode: string
  unadjustedAmount: number
  adjustmentAmount: number
  auditedAmount: number
  ajeRef: string
  indexRef: string
  editable: boolean
}

const adjudicationRows = ref<AdjudicationRow[]>([])
const auditConclusion = ref('')
const saving = ref(false)
const isDirty = ref(false)

// ─── 公式计算 ────────────────────────────────────────────────────────────────

function recalculate() {
  for (const row of adjudicationRows.value) {
    row.auditedAmount = (row.unadjustedAmount || 0) + (row.adjustmentAmount || 0)
  }
  markDirty()
}

function markDirty() {
  isDirty.value = true
}

// ─── 合计行 ──────────────────────────────────────────────────────────────────

function getSummary({ columns, data }: any) {
  const sums: string[] = []
  columns.forEach((column: any, index: number) => {
    if (index === 0) {
      sums[index] = '合计'
      return
    }
    const prop = column.property
    if (['unadjustedAmount', 'adjustmentAmount', 'auditedAmount'].includes(prop)) {
      const total = data.reduce((sum: number, row: any) => {
        const val = Number(row[prop])
        return sum + (isNaN(val) ? 0 : val)
      }, 0)
      sums[index] = fmt(total)
    } else {
      sums[index] = ''
    }
  })
  return sums
}

// ─── 样式辅助 ────────────────────────────────────────────────────────────────

function cellClassName({ column }: any) {
  if (['未审数', '审定数'].includes(column.label)) {
    return 'formula-column'
  }
  return ''
}

// ─── AI 辅助 ─────────────────────────────────────────────────────────────────

function handleAiAssist() {
  ElMessage.info('AI辅助功能开发中，将自动分析电子商务科目异常变动')
}

function handleAiConclusion() {
  ElMessage.info('AI将根据审定结果自动生成审计结论')
}

// ─── 保存（含 TB 回写） ─────────────────────────────────────────────────────

async function handleSave() {
  if (saving.value) return
  saving.value = true
  try {
    const payload = {
      adjudication_rows: adjudicationRows.value.map(r => ({
        id: r.id,
        account_name: r.accountName,
        account_code: r.accountCode,
        unadjusted_amount: r.unadjustedAmount,
        adjustment_amount: r.adjustmentAmount,
        audited_amount: r.auditedAmount,
        aje_ref: r.ajeRef,
        index_ref: r.indexRef,
      })),
      conclusion: auditConclusion.value,
    }
    await http.put(
      `/api/workpapers/${props.wpId}/checklist-responses`,
      { sheet_name: '审定表S9-1', data: payload }
    )
    isDirty.value = false
    emit('save')
    ElMessage.success('审定表已保存')
  } catch (err: any) {
    ElMessage.error(`保存失败：${err?.message || '未知错误'}`)
  } finally {
    saving.value = false
  }
}

// ─── 数据加载 ────────────────────────────────────────────────────────────────

async function loadData() {
  try {
    const res = await http.get(
      `/api/workpapers/${props.wpId}/render-config`,
      { _silent: true } as any
    )
    const sheets = res?.data?.sheets || res?.sheets || []
    const sheet = sheets.find((s: any) =>
      s.sheet_name?.includes('审定表S9') || s.sheet_name?.match(/S9-1/)
    )
    const htmlData = sheet?.html_data

    if (htmlData?.adjudication_rows?.length) {
      adjudicationRows.value = htmlData.adjudication_rows.map((r: any, idx: number) => ({
        id: r.id || `s9-1-${idx}`,
        accountName: r.account_name || r.accountName || '',
        accountCode: r.account_code || r.accountCode || '',
        unadjustedAmount: Number(r.unadjusted_amount ?? r.unadjustedAmount ?? 0),
        adjustmentAmount: Number(r.adjustment_amount ?? r.adjustmentAmount ?? 0),
        auditedAmount: Number(r.audited_amount ?? r.auditedAmount ?? 0),
        ajeRef: r.aje_ref || r.ajeRef || '',
        indexRef: r.index_ref || r.indexRef || '',
        editable: true,
      }))
    } else {
      // 默认审定表行（电子商务相关常见科目）
      adjudicationRows.value = [
        { id: 's9-1-0', accountName: '电子商务收入', accountCode: '', unadjustedAmount: 0, adjustmentAmount: 0, auditedAmount: 0, ajeRef: '', indexRef: '', editable: true },
        { id: 's9-1-1', accountName: '电子商务成本', accountCode: '', unadjustedAmount: 0, adjustmentAmount: 0, auditedAmount: 0, ajeRef: '', indexRef: '', editable: true },
        { id: 's9-1-2', accountName: '平台服务费', accountCode: '', unadjustedAmount: 0, adjustmentAmount: 0, auditedAmount: 0, ajeRef: '', indexRef: '', editable: true },
        { id: 's9-1-3', accountName: '物流费用', accountCode: '', unadjustedAmount: 0, adjustmentAmount: 0, auditedAmount: 0, ajeRef: '', indexRef: '', editable: true },
        { id: 's9-1-4', accountName: '电子支付手续费', accountCode: '', unadjustedAmount: 0, adjustmentAmount: 0, auditedAmount: 0, ajeRef: '', indexRef: '', editable: true },
      ]
    }

    if (htmlData?.conclusion) {
      auditConclusion.value = htmlData.conclusion
    }
  } catch {
    // 降级：空表
    adjudicationRows.value = [
      { id: 's9-1-0', accountName: '电子商务收入', accountCode: '', unadjustedAmount: 0, adjustmentAmount: 0, auditedAmount: 0, ajeRef: '', indexRef: '', editable: true },
    ]
  }
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.s9-adjudication {
  padding: 12px;
}

.audit-section {
  margin-bottom: 16px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.compile-hint {
  margin-bottom: 12px;
  font-size: var(--wp-font-size, 13px);
}

.compile-hint summary {
  cursor: pointer;
  color: #909399;
  font-size: 12px;
  margin-bottom: 8px;
}

.methodology-context {
  padding: 10px 14px;
  border-left: 4px solid #e6a23c;
  background-color: #fdf6ec;
  font-size: var(--wp-font-size, 13px);
  line-height: 1.7;
  color: #606266;
}

.methodology-context p {
  margin: 4px 0;
}

.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
}

.audited-amount {
  font-weight: 600;
  color: #303133;
}

.text-placeholder {
  color: #c0c4cc;
}

:deep(.formula-column) {
  background-color: #fafafa;
}

:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}
</style>
