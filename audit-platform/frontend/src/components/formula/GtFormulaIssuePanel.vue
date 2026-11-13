<template>
  <div class="gt-issue-panel">
    <div class="gt-issue-panel__header">
      <span class="gt-issue-panel__title">
        <el-icon class="gt-issue-panel__title-icon"><Search /></el-icon>
        逻辑判断问题清单
        <el-tag
          v-if="!loading"
          :type="issues.length ? issueSummaryType : (allPassed ? 'success' : 'info')"
          size="small"
          effect="light"
          round
          class="gt-issue-panel__count"
        >{{ summaryText }}</el-tag>
      </span>
      <div class="gt-issue-panel__actions">
        <span v-if="lastComputedAt" class="gt-issue-panel__computed">最近计算：{{ computedAtText }}</span>
        <span v-else class="gt-issue-panel__computed gt-issue-panel__computed--pending">尚未计算</span>
        <el-button
          v-if="showRefresh"
          size="small"
          :loading="loading"
          @click="emit('refresh')"
        >刷新</el-button>
      </div>
    </div>

    <div v-loading="loading" class="gt-issue-panel__body">
      <!-- 问题项（勾稽不通过） -->
      <template v-if="issues.length">
        <div v-for="(issue, i) in issues" :key="issue.formula_id || i" class="gt-issue-item"
          :class="`gt-issue-item--${formulaCheckSeverity(issue.severity)}`">
          <el-icon class="gt-issue-item__icon"><WarningFilled /></el-icon>
          <div class="gt-issue-item__main">
            <div class="gt-issue-item__desc">
              <el-tag v-if="issue.status" :type="issueTagType(issue)" size="small" effect="plain">
                {{ issueStatusLabel(issue.status) }}
              </el-tag>
              <el-tag :type="severityTagType(formulaCheckSeverity(issue.severity))" size="small" effect="plain">
                {{ severityLabel(formulaCheckSeverity(issue.severity)) }}
              </el-tag>
              {{ issue.description }}
            </div>
            <div v-if="hasValues(issue)" class="gt-issue-item__values">
              <span>左值：<b>{{ fmtValue(issue.left_value) }}</b></span>
              <span>右值：<b>{{ fmtValue(issue.right_value) }}</b></span>
              <span v-if="diffOf(issue) !== null" class="gt-issue-item__diff">
                差异：<b>{{ fmtValue(diffOf(issue)) }}</b>
              </span>
            </div>
            <div v-if="issue.reason" class="gt-issue-item__addr">原因：{{ issue.reason }}</div>
            <div v-if="issue.addr_id" class="gt-issue-item__addr">来源：{{ issue.addr_id }}</div>
          </div>
        </div>
      </template>

      <el-empty
        v-else-if="!loading"
        :image-size="64"
        :description="emptyDescription"
      />

      <!-- 全部校验概览（含通过项，折叠） -->
      <el-collapse v-if="outcomes.length" class="gt-issue-panel__all">
        <el-collapse-item :title="`查看全部校验（${outcomes.length} 条）`" name="all">
          <div v-for="(o, i) in outcomes" :key="o.formula_id || i" class="gt-outcome-item">
            <el-tag
              :type="outcomeTagType(o)"
              size="small"
              effect="plain"
              round
            >{{ outcomeLabel(o) }}</el-tag>
            <el-tag :type="severityTagType(formulaCheckSeverity(o.severity))" size="small" effect="plain">{{ severityLabel(formulaCheckSeverity(o.severity)) }}</el-tag>
            <span class="gt-outcome-item__desc">{{ o.description }}<span v-if="o.reason">；原因：{{ o.reason }}</span></span>
            <code class="gt-outcome-item__expr">{{ o.expression }}</code>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * GtFormulaIssuePanel — logic_check 问题清单面板（Req 6.2）
 *
 * 消费后端 logic_check 执行端点返回的 **Issue_List**（勾稽不通过项）与逐条校验结果。
 * logic_check 绝不改值——本面板为只读展示。
 *
 * 数据以 props 注入（展示型组件）：挂在表间审核面板里，取自公式管理中心打开时那一次
 * report-cross-check 响应（formulaIssueHint.ts，spec formula-governance-coverage-closure R4）。
 *
 * Requirements: 6.2
 */
import { computed } from 'vue'
import { Search, WarningFilled } from '@element-plus/icons-vue'
import { fmtDateTime } from '@/utils/formatters'
import { formulaOutcomeStatus, formulaCheckNumber, formulaCheckSeverity, type FormulaIssueItem, type FormulaCheckOutcome } from './formulaIssueHint'
import { checkStatusLabel } from '@/utils/consistencyCheckStatus'

const props = withDefaults(
  defineProps<{
    /** logic_check 不通过项（Issue_List） */
    issues?: FormulaIssueItem[]
    /** 逐条校验结果（含通过项，可选） */
    outcomes?: FormulaCheckOutcome[]
    /** 最近计算时间（后端 naive UTC 或 ISO 串）；空 → "尚未计算" */
    lastComputedAt?: string | null
    loading?: boolean
    /** 是否显示刷新按钮 */
    showRefresh?: boolean
  }>(),
  {
    issues: () => [],
    outcomes: () => [],
    lastComputedAt: null,
    loading: false,
    showRefresh: true,
  },
)

const emit = defineEmits<{ refresh: [] }>()

const issues = computed(() => props.issues ?? [])
const outcomes = computed(() => props.outcomes ?? [])
const issueSummaryType = computed(() => issues.value.some((issue) => formulaCheckSeverity(issue.severity) === 'blocking')
  ? 'danger' : (issues.value.some((issue) => formulaCheckSeverity(issue.severity) === 'warning') ? 'warning' : 'info'))
const allPassed = computed(() => outcomes.value.length > 0 && outcomes.value.every((o) => outcomeStatus(o) === 'passed'))
const incompleteCount = computed(() => outcomes.value.filter((o) => outcomeStatus(o) !== 'passed' && outcomeStatus(o) !== 'not_applicable').length)
const summaryText = computed(() => issues.value.length
  ? `${issues.value.length} 项待处理`
  : (allPassed.value ? '全部通过' : (outcomes.value.length ? (incompleteCount.value ? `${incompleteCount.value} 项需查看结论` : '本次检查不适用') : '无校验结果')))
const emptyDescription = computed(() => allPassed.value
  ? '未发现逻辑判断问题，全部勾稽通过'
  : (outcomes.value.length ? '请查看各项校验状态与原因，非通过不等于失败' : '本次未返回校验结果'))

const computedAtText = computed(() => {
  if (!props.lastComputedAt) return ''
  return fmtDateTime(normalizeTimestamp(props.lastComputedAt))
})

function normalizeTimestamp(v: string): string {
  const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(v)
  return hasTz ? v : `${v}Z`
}

const toNum = formulaCheckNumber

function hasValues(issue: FormulaIssueItem): boolean {
  return toNum(issue.left_value) !== null || toNum(issue.right_value) !== null
}

function diffOf(issue: FormulaIssueItem): number | null {
  const l = toNum(issue.left_value), r = toNum(issue.right_value)
  return l === null || r === null ? null : l - r
}

const outcomeStatus = formulaOutcomeStatus
function outcomeLabel(outcome: FormulaCheckOutcome): string {
  return checkStatusLabel({ status: outcomeStatus(outcome) })
}

function outcomeTagType(outcome: FormulaCheckOutcome): 'success' | 'danger' | 'warning' | 'info' {
  switch (outcomeStatus(outcome)) {
    case 'passed': return 'success'
    case 'failed': return severityTagType(formulaCheckSeverity(outcome.severity))
    case 'error': return 'danger'
    case 'not_executed': return 'warning'
    case 'not_applicable': return 'info'
  }
}

function issueStatusLabel(status: NonNullable<FormulaIssueItem['status']>): string {
  return checkStatusLabel({ status: formulaOutcomeStatus({ status }) })
}

function severityTagType(severity: NonNullable<FormulaIssueItem['severity']>): 'danger' | 'warning' | 'info' {
  return { blocking: 'danger', warning: 'warning', info: 'info' }[severity] as 'danger' | 'warning' | 'info'
}

function severityLabel(severity: NonNullable<FormulaIssueItem['severity']>): string {
  return { blocking: '阻断', warning: '警告', info: '提示' }[severity]
}

function issueTagType(issue: FormulaIssueItem): 'danger' | 'warning' | 'info' {
  if (issue.status === 'error') return 'danger'
  if (issue.status === 'not_executed') return 'warning'
  if (issue.status === 'not_applicable') return 'info'
  return severityTagType(formulaCheckSeverity(issue.severity))
}

function fmtValue(v: string | number | null): string {
  const n = toNum(v)
  if (n === null) return '—'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.gt-issue-panel {
  font-size: 13px;
}
.gt-issue-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.gt-issue-panel__title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  color: var(--gt-color-text-primary, #303133);
}
.gt-issue-panel__title-icon {
  color: #409eff;
}
.gt-issue-panel__count {
  margin-left: 4px;
}
.gt-issue-panel__actions {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}
.gt-issue-panel__computed {
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
}
.gt-issue-panel__computed--pending {
  color: #e6a23c;
  font-style: italic;
}
.gt-issue-panel__body {
  min-height: 48px;
}
.gt-issue-item {
  display: flex;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  background: #fef0f0;
  border-left: 3px solid #f56c6c;
  margin-bottom: 8px;
}
.gt-issue-item__icon {
  color: #f56c6c;
  margin-top: 2px;
}
.gt-issue-item--warning {
  background: #fdf6ec;
  border-left-color: #e6a23c;
}
.gt-issue-item--info {
  background: #f4f4f5;
  border-left-color: #909399;
}
.gt-issue-item--warning .gt-issue-item__icon { color: #e6a23c; }
.gt-issue-item--info .gt-issue-item__icon { color: #909399; }
.gt-issue-item__main {
  flex: 1;
  min-width: 0;
}
.gt-issue-item__desc {
  color: #303133;
  font-weight: 500;
}
.gt-issue-item__values {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-top: 4px;
  font-size: 12px;
  color: #606266;
}
.gt-issue-item__diff b {
  color: #f56c6c;
}
.gt-issue-item__addr {
  margin-top: 3px;
  font-size: 12px;
  color: #909399;
}
.gt-issue-panel__all {
  margin-top: 8px;
}
.gt-outcome-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 12px;
}
.gt-outcome-item__desc {
  color: #606266;
}
.gt-outcome-item__expr {
  color: #909399;
  font-family: 'Consolas', 'Courier New', monospace;
  background: #f5f7fa;
  padding: 1px 6px;
  border-radius: 3px;
  margin-left: auto;
}
</style>
