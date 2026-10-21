<!-- 表间审核执行历史面板（从 FormulaManagerDialog 提取；spec formula-settings-wiring-closure T11）。 -->
<template>
  <el-collapse v-model="open" style="margin-top: 12px;">
    <el-collapse-item title="执行历史" name="history">
      <div style="display: flex; justify-content: flex-end; margin-bottom: 6px;">
        <el-button size="small" :loading="loading" @click="load">刷新</el-button>
      </div>
      <div v-if="runs.length && !runs[0].issues_retained" style="font-size: 11px; color: var(--gt-color-text-tertiary); margin-bottom: 4px;">
        仅最近一次运行保留逐条明细，更早的运行只显示计数。
      </div>
      <el-table v-loading="loading" :data="runs" size="small" border max-height="240" empty-text="暂无执行记录">
        <el-table-column label="时间" width="165">
          <template #default="{ row }">{{ row.created_at || '—' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="执行/问题/提示" width="130">
          <template #default="{ row }">
            <span>{{ row.executed_count ?? row.detail?.executed_count ?? '—' }}</span> /
            <span :style="{ color: (row.issue_count || row.detail?.issue_count) ? 'var(--gt-color-danger)' : undefined }">
              {{ row.issue_count ?? row.detail?.issue_count ?? 0 }}
            </span> /
            <span style="color: var(--gt-color-text-tertiary);">{{ row.hint_count ?? row.detail?.hint_count ?? 0 }}</span>
          </template>
        </el-table-column>
        <el-table-column label="逐条结论" min-width="340">
          <template #default="{ row }">
            <template v-if="row.issues_retained !== false && row.issues?.length">
              <div v-for="issue in row.issues" :key="issue.rule_id"
                style="font-size: 11px; border-bottom: 1px solid #f0f0f0; padding: 2px 0;"
                :style="diffStyle(row, issue)">
                <el-tag :type="issue.status === 'passed' ? 'success' : 'danger'" size="small" effect="plain" style="margin-right: 4px;">
                  {{ issue.status === 'passed' ? '✅' : '❌' }}
                </el-tag>
                <span>{{ issue.rule_id }}</span>
                <span v-if="issue.diff != null" style="margin-left: 8px; color: var(--gt-color-text-tertiary);">
                  差额: {{ typeof issue.diff === 'number' ? issue.diff.toFixed(2) : issue.diff }}
                </span>
                <span v-if="prevIssue(row, issue)" style="margin-left: 6px; font-size: 10px;"
                  :style="{ color: prevIssue(row, issue)?.status !== issue.status ? 'var(--gt-color-danger)' : 'var(--gt-color-text-placeholder)' }">
                  （上次: {{ prevIssue(row, issue)?.status === 'passed' ? '✅' : '❌' }}
                  <template v-if="prevIssue(row, issue)?.diff != null">
                    差额 {{ typeof prevIssue(row, issue)?.diff === 'number' ? prevIssue(row, issue)!.diff.toFixed(2) : prevIssue(row, issue)?.diff }}
                  </template>）
                </span>
              </div>
            </template>
            <span v-else-if="row.issues_retained === false" style="color: var(--gt-color-text-placeholder); font-size: 11px;">仅最近一次保留明细</span>
            <span v-else style="color: var(--gt-color-text-placeholder);">无明细</span>
          </template>
        </el-table-column>
      </el-table>
    </el-collapse-item>
  </el-collapse>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import api from '@/services/apiProxy'

const props = defineProps<{ projectId?: string; year?: number }>()

const open = ref<string[]>([])
const runs = ref<any[]>([])
const loading = ref(false)

async function load() {
  if (!props.projectId || !props.year) return
  loading.value = true
  try {
    const data: any = await api.get(`/api/projects/${props.projectId}/formula/cross-check-history`, { params: { year: props.year } })
    runs.value = data?.runs || []
  } catch { runs.value = [] }
  finally { loading.value = false }
}

function statusType(s: string) { return s === 'executed' || s === 'success' ? 'success' : s === 'no_result' ? 'info' : 'warning' }
function statusLabel(s: string) { return s === 'executed' || s === 'success' ? '已执行' : s === 'no_result' ? '无结果' : s }

function _prevRun(cur: any): any | null {
  const idx = runs.value.indexOf(cur)
  return (idx >= 0 && idx < runs.value.length - 1) ? runs.value[idx + 1] : null
}
function prevIssue(cur: any, issue: any): any | null {
  return _prevRun(cur)?.issues?.find((i: any) => i.rule_id === issue.rule_id) || null
}
function diffStyle(cur: any, issue: any): Record<string, string> {
  const prev = prevIssue(cur, issue)
  if (prev && prev.status !== issue.status) return { background: issue.status === 'passed' ? '#f6ffed' : '#fff2f0' }
  return {}
}

defineExpose({ load })
</script>
