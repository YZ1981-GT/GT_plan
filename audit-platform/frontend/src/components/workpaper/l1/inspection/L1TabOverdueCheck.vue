<template>
  <div class="l1-tab-overdue-check">
    <!-- ═══ 返回目录 + 标题 + 操作栏 ═══ -->
    <div class="overdue-header">
      <div class="overdue-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">
          ← 返回目录
        </el-button>
        <h3 class="overdue-title">L1-7 逾期贷款检查表</h3>
      </div>
      <div class="overdue-header-right">
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          @click="handleAddRow"
        >
          + 新增检查行
        </el-button>
      </div>
    </div>

    <!-- ═══ 蓝色引导区 ═══ -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step">
          <span class="guide-num">①</span>
          <span>录入每笔借款的合同号、到期日、逾期金额</span>
        </div>
        <div class="guide-step">
          <span class="guide-num">②</span>
          <span>系统自动计算逾期天数并按等级高亮（黄/橙/红）</span>
        </div>
        <div class="guide-step">
          <span class="guide-num">③</span>
          <span>评价展期情况与风险等级</span>
        </div>
        <div class="guide-step">
          <span class="guide-num">④</span>
          <span>查看统计汇总：逾期笔数/金额/等级分布</span>
        </div>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>逾期天数计算：</strong>
        逾期天数 = 报告日（资产负债表日）− 合同到期日。
        正值表示逾期，负值表示未到期。
        <strong>风险分级：</strong>&lt;30天黄色（关注类）/ 30-90天橙色（次级类）/ &gt;90天红色（可疑+损失类）。
      </div>
    </div>

    <!-- ═══ 逾期检查表主体 ═══ -->
    <el-table
      :data="computedRows"
      border
      size="small"
      style="width: 100%"
      :row-class-name="getRowClassName"
      max-height="480"
    >
      <!-- 序号 -->
      <el-table-column type="index" label="#" width="42" align="center" />

      <!-- 借款合同号 -->
      <el-table-column prop="contractNo" label="借款合同号" min-width="140">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-input
              :model-value="row.contractNo"
              size="small"
              placeholder="合同号"
              @input="(val: string) => handleFieldChange($index, 'contractNo', val)"
            />
          </template>
          <span v-else>{{ row.contractNo || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 到期日 -->
      <el-table-column prop="dueDate" label="到期日" width="130">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-date-picker
              :model-value="row.dueDate"
              type="date"
              size="small"
              value-format="YYYY-MM-DD"
              placeholder="到期日"
              style="width: 100%"
              @update:model-value="(val: string) => handleFieldChange($index, 'dueDate', val || '')"
            />
          </template>
          <span v-else>{{ row.dueDate || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 报告日 -->
      <el-table-column prop="reportDate" label="报告日" width="110">
        <template #default="{ row }">
          <span>{{ row.reportDate || reportDateStr }}</span>
        </template>
      </el-table-column>

      <!-- 逾期天数（公式列） -->
      <el-table-column label="逾期天数" width="100" align="center">
        <template #header>
          <el-tooltip content="逾期天数 = 报告日 − 到期日（正值=逾期）" placement="top">
            <span class="formula-col-header">逾期天数</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-tooltip content="报告日 − 到期日" placement="top">
            <span :class="['formula-cell', getOverdueDaysClass(row)]">
              {{ row.computedOverdueDays || '-' }}
            </span>
          </el-tooltip>
        </template>
      </el-table-column>

      <!-- 逾期金额 -->
      <el-table-column prop="overdueAmount" label="逾期金额" min-width="120" align="right">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-input-number
              :model-value="row.overdueAmount"
              :controls="false"
              :precision="2"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => handleFieldChange($index, 'overdueAmount', val ?? 0)"
            />
          </template>
          <span v-else>{{ fmtAmount(row.overdueAmount) }}</span>
        </template>
      </el-table-column>

      <!-- 是否展期 -->
      <el-table-column prop="isExtended" label="是否展期" width="100" align="center">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-select
              :model-value="row.isExtended"
              size="small"
              placeholder="选择"
              style="width: 100%"
              @change="(val: string) => handleFieldChange($index, 'isExtended', val)"
            >
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="待确认" value="待确认" />
            </el-select>
          </template>
          <span v-else>{{ row.isExtended || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 风险评价 -->
      <el-table-column prop="riskEvaluation" label="风险评价" min-width="130">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly">
            <el-select
              :model-value="row.riskEvaluation"
              size="small"
              placeholder="风险等级"
              style="width: 100%"
              @change="(val: string) => handleFieldChange($index, 'riskEvaluation', val)"
            >
              <el-option label="正常" value="正常" />
              <el-option label="关注" value="关注" />
              <el-option label="次级" value="次级" />
              <el-option label="可疑" value="可疑" />
              <el-option label="损失" value="损失" />
            </el-select>
          </template>
          <span v-else>{{ row.riskEvaluation || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
        <template #default="{ $index }">
          <el-button
            text
            type="danger"
            size="small"
            @click="handleRemoveRow($index)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 统计区：逾期笔数/金额/按等级分布 ═══ -->
    <div class="summary-section">
      <div class="summary-grid">
        <div class="summary-item">
          <span class="summary-label">逾期笔数</span>
          <span :class="['summary-value', { 'diff-warning': overdueCount > 0 }]">
            {{ overdueCount }} 笔
          </span>
        </div>
        <div class="summary-item">
          <span class="summary-label">逾期金额合计</span>
          <span :class="['summary-value', { 'diff-warning': totalOverdueAmount > 0 }]">
            {{ fmtAmount(totalOverdueAmount) }}
          </span>
        </div>
        <div class="summary-item">
          <span class="summary-label">等级分布</span>
          <span class="summary-value summary-dist">
            <span class="level-low">{{ overdueSummary.low }} 低</span>
            <span class="level-medium">{{ overdueSummary.medium }} 中</span>
            <span class="level-high">{{ overdueSummary.high }} 高</span>
          </span>
        </div>
        <div class="summary-item">
          <span class="summary-label">未逾期笔数</span>
          <span class="summary-value">{{ overdueSummary.none }} 笔</span>
        </div>
      </div>
    </div>

    <!-- ═══ 审计说明 ═══ -->
    <el-card class="conclusion-card" shadow="never">
      <template #header>
        <div class="conclusion-header">
          <span>审计说明</span>
          <el-button
            v-if="!isReadonly"
            size="small"
            type="primary"
            plain
            :loading="aiNoteLoading"
            @click="handleAiNote"
          >🤖 AI 辅助</el-button>
        </div>
      </template>
      <el-input
        :model-value="note"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="关注未办理转期手续是否引发诉讼（取得诉状）；分析逾期借款占全部借款比例及对持续经营的影响；说明未按期偿还原因与预计还款期。"
        @input="onNoteInput"
      />
    </el-card>

    <!-- ═══ 审计结论区 ═══ -->
    <el-card class="conclusion-card" shadow="never">
      <template #header>
        <div class="conclusion-header">
          <span>逾期检查结论</span>
          <el-button
            v-if="!isReadonly"
            size="small"
            type="primary"
            plain
            :loading="aiConclusionLoading"
            @click="handleAiConclusion"
          >🤖 AI 辅助</el-button>
        </div>
      </template>
      <el-input
        :model-value="conclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="根据逾期检查结果，填写审计结论..."
        @input="onConclusionInput"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l1-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>逾期天数</strong>：报告日 − 合同到期日，正值表示已逾期</li>
        <li><strong>风险分级</strong>：&lt;30天黄色(关注) / 30-90天橙色(次级) / &gt;90天红色(可疑+损失)</li>
        <li><strong>展期关注</strong>：展期借款需关注是否为掩盖实质逾期的风险信号</li>
        <li><strong>分类标准</strong>：参照《贷款风险分类指引》五级分类（正常/关注/次级/可疑/损失）</li>
        <li><strong>联动审定</strong>：逾期借款影响短期借款的减值评估和风险披露</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L1TabOverdueCheck — L1-7 逾期贷款检查表
 *
 * 逾期天数 = 报告日 − 到期日（>0为逾期）
 * 逾期天数分级高亮：<30天黄 / 30-90天橙 / >90天红
 * 统计区：逾期笔数/金额/按等级分布
 *
 * Spec: .kiro/specs/l1-short-term-loans/
 * Task: 4.5
 * Requirements: 6.1-6.3
 */
import { computed, inject, onMounted, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import type { useL1FormData } from '@/composables/useL1FormData'
import type { OverdueCheckRow } from '@/composables/useL1FormData'
import { useL1OverdueCheck, type OverdueLevel } from '@/composables/useL1OverdueCheck'
import { useL1AiNote } from '@/composables/useL1AiNote'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  year?: number
  isReadonly: boolean
}>()

defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

// ─── Inject formData ─────────────────────────────────────────────────────────

const formData = inject<ReturnType<typeof useL1FormData>>('l1FormData')!

// ─── 报告期截止日（优先取项目审计年度，回退当前年） ──────────────────────────
const auditYear = computed(() => props.year || new Date().getFullYear())
const reportDate = computed<Date>(() => new Date(auditYear.value, 11, 31))
const reportDateStr = computed(() => `${auditYear.value}-12-31`)

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  computedRows,
  overdueCount,
  totalOverdueAmount,
  overdueSummary,
  addRow,
  removeRow,
  updateRow,
} = useL1OverdueCheck(formData, reportDate)

// ─── 审计说明 + 审计结论（AI 辅助，统一 useL1AiNote：修复刷新丢失+真实AI） ───

const {
  note, conclusion, aiNoteLoading, aiConclusionLoading,
  load: loadNote, onNoteInput, onConclusionInput, generateNote, generateConclusion,
} = useL1AiNote(formData, toRef(props, 'wpId'), 'ovd', toRef(props, 'isReadonly'))

function _aiContext() {
  return {
    逾期笔数: overdueCount.value,
    逾期金额合计: totalOverdueAmount.value,
    等级分布: `低${overdueSummary.value.low}/中${overdueSummary.value.medium}/高${overdueSummary.value.high}`,
  }
}
function handleAiNote() {
  generateNote('请基于逾期贷款检查情况撰写审计说明，覆盖逾期比例、诉讼风险、对持续经营的影响。', _aiContext())
}
function handleAiConclusion() {
  generateConclusion('请基于逾期贷款检查结果生成审计结论。', _aiContext())
}

onMounted(() => {
  loadNote()
})

// ─── 字段编辑处理 ────────────────────────────────────────────────────────────

function handleFieldChange(index: number, field: keyof OverdueCheckRow, value: string | number): void {
  updateRow(index, field, value)
}

// ─── 新增行 ──────────────────────────────────────────────────────────────────

async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入借款合同号',
      '新增逾期检查行',
      {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        inputPlaceholder: '如：LOAN-2024-001',
        inputValidator: (val: string) => {
          if (!val?.trim()) return '合同号不能为空'
          return true
        },
      },
    )
    if (value?.trim()) {
      addRow(value.trim())
    }
  } catch {
    // 用户取消
  }
}

// ─── 删除行 ──────────────────────────────────────────────────────────────────

function handleRemoveRow(index: number): void {
  removeRow(index)
}

// ─── 行样式（逾期天数分级高亮） ─────────────────────────────────────────────

function getRowClassName({ row }: { row: any }): string {
  if (row.overdueLevel === 'high') return 'overdue-high-row'
  if (row.overdueLevel === 'medium') return 'overdue-medium-row'
  if (row.overdueLevel === 'low') return 'overdue-low-row'
  return ''
}

function getOverdueDaysClass(row: any): string {
  if (row.overdueLevel === 'high') return 'overdue-high'
  if (row.overdueLevel === 'medium') return 'overdue-medium'
  if (row.overdueLevel === 'low') return 'overdue-low'
  return ''
}

// ─── 工具函数 ────────────────────────────────────────────────────────────────

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) {
    return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  }
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.l1-tab-overdue-check {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 头部 ─── */
.overdue-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.overdue-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.overdue-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.overdue-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

/* ─── 蓝色引导区 ─── */
.guide-area {
  background: linear-gradient(135deg, #ecf5ff 0%, #f0f7ff 100%);
  border: 1px solid #d9ecff;
  border-radius: 8px;
  padding: 14px 18px;
  margin-bottom: 14px;
}

.guide-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 24px;
}

.guide-step {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #409eff;
  line-height: 1.5;
}

.guide-num {
  font-weight: 700;
  font-size: 14px;
  min-width: 18px;
}

/* ─── 方法论上下文（琥珀色） ─── */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 14px;
  font-size: var(--wp-font-size, 13px);
  color: #5a4e3a;
  line-height: 1.6;
}

.methodology-text strong {
  color: #b88230;
}

/* ─── 公式列表头 ─── */
.formula-col-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 1px;
}

/* ─── 公式列单元格 ─── */
.formula-cell {
  border-bottom: 1px dashed #c0c4cc;
  cursor: help;
  padding-bottom: 1px;
  display: inline-block;
}

/* ─── 逾期天数分级高亮 ─── */
.overdue-low {
  color: #e6a23c !important;
  font-weight: 700;
  border-bottom-color: #e6a23c;
}

.overdue-medium {
  color: #f56c6c !important;
  font-weight: 700;
  border-bottom-color: #f56c6c;
}

.overdue-high {
  color: #c00 !important;
  font-weight: 700;
  border-bottom-color: #c00;
}

/* ─── 逾期行背景分级 ─── */
:deep(.overdue-low-row) {
  background-color: #fdf6ec !important;
}

:deep(.overdue-medium-row) {
  background-color: #fef0f0 !important;
}

:deep(.overdue-high-row) {
  background-color: #fde2e2 !important;
}

/* ─── 差异高亮 ─── */
.diff-warning {
  color: #f56c6c !important;
  font-weight: 700;
}

/* ─── 表格统一13px字体 ─── */
:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}

:deep(.el-table th .cell) {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}

/* ─── 统计区 ─── */
.summary-section {
  margin-top: 16px;
  padding: 14px 18px;
  background: #f0f9eb;
  border: 1px solid #e1f3d8;
  border-radius: 8px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.summary-label {
  font-size: 12px;
  color: #909399;
}

.summary-value {
  font-size: 15px;
  font-weight: 700;
  color: #303133;
}

.summary-dist {
  display: flex;
  gap: 8px;
  font-size: var(--wp-font-size, 13px);
}

.level-low {
  color: #e6a23c;
  font-weight: 600;
}

.level-medium {
  color: #f56c6c;
  font-weight: 600;
}

.level-high {
  color: #c00;
  font-weight: 600;
}

/* ─── 结论卡片 ─── */
.conclusion-card {
  margin-top: 16px;
}

.conclusion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
}

/* ─── 编制提示折叠 ─── */
.l1-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.l1-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.l1-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
