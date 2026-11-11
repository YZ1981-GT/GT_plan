<!-- 表间审核执行历史面板（从 FormulaManagerDialog 提取；spec formula-settings-wiring-closure T11）。 -->
<template>
  <el-collapse v-model="open" style="margin-top: 12px;">
    <el-collapse-item title="执行历史" name="history">
      <div style="display: flex; justify-content: flex-end; margin-bottom: 6px;">
        <el-button size="small" :loading="loading" @click="load">刷新</el-button>
      </div>
      <el-alert v-if="error" type="warning" :closable="false" :title="error" data-testid="history-error" />
      <el-table v-loading="loading" :data="runs" size="small" border max-height="240" :empty-text="error ? '执行历史读取失败，请重试' : '暂无执行记录'">
        <el-table-column label="时间" width="165">
          <template #default="{ row }">{{ row.created_at ? fmtDateTime(row.created_at) : '—' }}</template>
        </el-table-column>
        <el-table-column label="运行状态" width="100">
          <template #default="{ row }"><el-tag size="small" :type="runType(row.status)">{{ runLabel(row.status) }}</el-tag></template>
        </el-table-column>
        <el-table-column label="执行/问题/提示" width="130">
          <template #default="{ row }">
            {{ row.executed_count ?? row.detail?.executed_count ?? '—' }} /
            {{ row.issue_count ?? row.detail?.issue_count ?? '—' }} /
            {{ row.hint_count ?? row.detail?.hint_count ?? '—' }}
          </template>
        </el-table-column>
        <el-table-column label="已保留的逐条结论" min-width="340">
          <template #default="{ row }">
            <div v-if="row.issues_retained === false" style="font-size: 11px; color: var(--gt-color-text-tertiary);">
              明细未完整保留；以下仅为实际返回项，不代表完整通过清单。
            </div>
            <template v-if="row.issues?.length">
              <div v-for="(issue, i) in row.issues" :key="`${issue.rule_id}-${i}`"
                style="font-size: 12px; border-bottom: 1px solid #f0f0f0; padding: 4px 0;" :style="diffStyle(row, issue)">
                <el-tag :type="itemType(issue)" size="small" effect="plain">{{ checkStatusLabel({ status: itemStatus(issue) }) }}</el-tag>
                <el-tag size="small" effect="plain" :type="severityType(issue)">{{ severityLabel(issue) }}</el-tag>
                <span>{{ issue.rule_id }}</span>
                <span> 左值：{{ fmt(issue.left_value) }}；右值：{{ fmt(issue.right_value) }}；差额：{{ fmt(issue.diff) }}</span>
                <div v-if="itemReason(issue)">原因：{{ itemReason(issue) }}</div>
                <span v-if="prevIssue(row, issue)" style="margin-left: 6px; font-size: 10px;"
                  :style="{ color: itemStatus(prevIssue(row, issue)) !== itemStatus(issue) ? 'var(--gt-color-danger)' : 'var(--gt-color-text-placeholder)' }">
                  （上次：{{ checkStatusLabel({ status: itemStatus(prevIssue(row, issue)) }) }}；差额：{{ fmt(prevIssue(row, issue)?.diff) }}）
                </span>
              </div>
            </template>
            <span v-else style="color: var(--gt-color-text-placeholder);">未返回逐条明细，不能据此判定全部通过</span>
          </template>
        </el-table-column>
      </el-table>
    </el-collapse-item>
  </el-collapse>
</template>

<script setup lang="ts">
import { ref, watch, onScopeDispose } from 'vue'
import api from '@/services/apiProxy'
import { fmtDateTime } from '@/utils/formatters'
import { checkStatusLabel, checkReasonOf } from '@/utils/consistencyCheckStatus'
import { formulaOutcomeStatus, formulaCheckNumber, formulaCheckSeverity } from '../formulaIssueHint'
import { formulaErrorText } from '@/composables/formula/useFormulaSettings'

const props = defineProps<{ projectId?: string; year?: number | null }>()
const open = ref<string[]>([]), runs = ref<any[]>([]), loading = ref(false), error = ref('')
let generation = 0, alive = true

async function load() {
  const pid = props.projectId, year = props.year, token = ++generation
  runs.value = []; error.value = ''
  if (!pid || year == null) { loading.value = false; return }
  const current = () => alive && token === generation && pid === props.projectId && year === props.year
  loading.value = true
  try {
    const data: any = await api.get(`/api/projects/${pid}/formula/cross-check-history`, { params: { year }, _silent: true })
    if (current()) runs.value = Array.isArray(data?.runs) ? data.runs : []
  } catch (e) { if (current()) error.value = formulaErrorText(e, '执行历史读取失败，请重试') }
  finally { if (current()) loading.value = false }
}

watch(() => [props.projectId, props.year], () => {
  ++generation; runs.value = []; error.value = ''; loading.value = false
  if (open.value.includes('history')) void load()
}, { flush: 'sync' })
watch(open, (value, previous) => { if (value.includes('history') && !previous.includes('history')) void load() })
onScopeDispose(() => { alive = false; ++generation })
function runLabel(s: string) { return ({ executed: '已执行', success: '已执行', no_result: '无结果', error: '运行异常', failed: '运行失败' } as Record<string, string>)[s] || '未知运行状态' }
function runType(s: string) { return s === 'error' || s === 'failed' ? 'warning' : 'info' }
const itemStatus = (i: any) => formulaOutcomeStatus({ ...i.details, ...i })
const itemReason = (i: any) => {
  const check = { ...i.details, ...i, reason: i.reason || i.details?.reason }
  return checkReasonOf(check.status === undefined && typeof check.passed === 'boolean'
    ? { ...check, status: itemStatus(i) } : check)
}
const severity = (i: any) => formulaCheckSeverity(i.severity ?? i.details?.severity)
const severityType = (i: any) => severity(i) === 'blocking' ? 'danger' : severity(i) === 'info' ? 'info' : 'warning'
const severityLabel = (i: any) => ({ blocking: '阻断', warning: '警告', info: '提示' })[severity(i)]
function itemType(i: any) { const s = itemStatus(i); return s === 'passed' ? 'success' : s === 'error' ? 'danger' : s === 'not_applicable' ? 'info' : s === 'not_executed' ? 'warning' : severityType(i) }
function fmt(v: unknown) { const n = formulaCheckNumber(v); return n === null ? '—' : n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }

function _prevRun(cur: any): any | null {
  const idx = runs.value.indexOf(cur)
  return (idx >= 0 && idx < runs.value.length - 1) ? runs.value[idx + 1] : null
}
function prevIssue(cur: any, issue: any): any | null {
  const currentMatches = cur.issues?.filter((i: any) => i.rule_id === issue.rule_id) || []
  const previousMatches = _prevRun(cur)?.issues?.filter((i: any) => i.rule_id === issue.rule_id) || []
  return currentMatches.length === 1 && previousMatches.length === 1 ? previousMatches[0] : null
}
function diffStyle(cur: any, issue: any): Record<string, string> {
  const prev = prevIssue(cur, issue)
  if (prev && itemStatus(prev) !== itemStatus(issue)) {
    const status = itemStatus(issue)
    return { background: status === 'passed' ? '#f6ffed' : status === 'failed' || status === 'error' ? '#fff2f0' : '#fffbe6' }
  }
  return {}
}

defineExpose({ load })
</script>
