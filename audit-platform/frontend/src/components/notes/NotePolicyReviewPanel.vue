<template>
  <div class="policy-review-panel">
    <!-- 顶部操作栏 -->
    <div class="policy-review-panel__toolbar">
      <el-radio-group v-model="filterMode" size="small">
        <el-radio-button value="all">全部</el-radio-button>
        <el-radio-button value="changed">只看有差异</el-radio-button>
        <el-radio-button value="pending">只看未确认</el-radio-button>
      </el-radio-group>
      <el-button
        type="primary"
        size="small"
        :disabled="unchangedPendingCount === 0"
        @click="handleBatchConfirm"
      >
        批量确认未变条款 ({{ unchangedPendingCount }})
      </el-button>
    </div>

    <!-- 条款目录 -->
    <div class="policy-review-panel__body">
      <aside class="policy-review-panel__toc">
        <h4>条款目录</h4>
        <ul>
          <li
            v-for="clause in filteredClauses"
            :key="clause.clause_id"
            :class="[
              'toc-item',
              `toc-item--level-${clause.level || 1}`,
              { 'toc-item--active': activeClauseId === clause.clause_id },
            ]"
            @click="activeClauseId = clause.clause_id"
          >
            <span class="toc-item__title">{{ clause.title }}</span>
            <el-tag
              v-if="clause.diff_status === 'changed'"
              type="warning"
              size="small"
            >变更</el-tag>
            <el-tag
              v-else-if="clause.diff_status === 'added'"
              type="success"
              size="small"
            >新增</el-tag>
            <el-tag
              v-else-if="clause.diff_status === 'removed'"
              type="danger"
              size="small"
            >删除</el-tag>
          </li>
        </ul>
      </aside>

      <!-- 三栏对照 -->
      <main class="policy-review-panel__content">
        <el-empty v-if="filteredClauses.length === 0" description="无匹配条款" />
        <div
          v-else-if="activeClause"
          class="clause-detail"
        >
          <h3>{{ activeClause.title }}</h3>
          <div class="clause-detail__columns">
            <div class="clause-col clause-col--template">
              <h5>模板</h5>
              <div class="clause-text" v-html="highlightVariables(activeClause.template_text)" />
            </div>
            <div class="clause-col clause-col--prior">
              <h5>上年</h5>
              <div class="clause-text" v-html="highlightVariables(activeClause.prior_year_text)" />
            </div>
            <div class="clause-col clause-col--current">
              <h5>本年</h5>
              <div class="clause-text" v-html="highlightVariables(activeClause.current_text)" />
            </div>
          </div>
          <div class="clause-detail__meta">
            <el-tag :type="statusTagType(activeClause.diff_status)" size="small">
              {{ statusLabel(activeClause.diff_status) }}
            </el-tag>
            <el-tag
              :type="confirmTagType(activeClause.confirm_status)"
              size="small"
              style="margin-left: 8px"
            >
              {{ confirmLabel(activeClause.confirm_status) }}
            </el-tag>
            <span v-if="activeClause.variables?.length" class="clause-detail__vars">
              变量：{{ activeClause.variables.join(', ') }}
            </span>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { NotePolicyClause } from '@/types/noteSemantic'

interface Props {
  clauses: NotePolicyClause[]
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'batch-confirm': [clauseIds: string[]]
}>()

const filterMode = ref<'all' | 'changed' | 'pending'>('all')
const activeClauseId = ref<string>('')

const filteredClauses = computed(() => {
  if (filterMode.value === 'all') return props.clauses
  if (filterMode.value === 'changed') {
    return props.clauses.filter(c => c.diff_status === 'changed' || c.diff_status === 'added' || c.diff_status === 'removed')
  }
  if (filterMode.value === 'pending') {
    return props.clauses.filter(c => c.confirm_status === 'pending')
  }
  return props.clauses
})

const activeClause = computed(() => {
  if (!activeClauseId.value && filteredClauses.value.length > 0) {
    return filteredClauses.value[0]
  }
  return filteredClauses.value.find(c => c.clause_id === activeClauseId.value) || null
})

const unchangedPendingCount = computed(() => {
  return props.clauses.filter(
    c => c.diff_status === 'unchanged' && c.confirm_status === 'pending'
  ).length
})

function handleBatchConfirm() {
  const ids = props.clauses
    .filter(c => c.diff_status === 'unchanged' && c.confirm_status === 'pending')
    .map(c => c.clause_id)
  emit('batch-confirm', ids)
}

function highlightVariables(text: string | null | undefined): string {
  if (!text) return '<span class="no-content">暂无内容</span>'
  return text.replace(
    /\{\{(\w+)\}\}/g,
    '<mark class="var-highlight">{{$1}}</mark>'
  )
}

function statusTagType(status: string | undefined): string {
  const map: Record<string, string> = {
    unchanged: 'success',
    changed: 'warning',
    added: '',
    removed: 'danger',
    unknown: 'info',
  }
  return map[status || 'unknown'] || 'info'
}

function statusLabel(status: string | undefined): string {
  const map: Record<string, string> = {
    unchanged: '未变',
    changed: '有变更',
    added: '新增',
    removed: '已删除',
    unknown: '未知',
  }
  return map[status || 'unknown'] || '未知'
}

function confirmTagType(status: string | undefined): string {
  const map: Record<string, string> = {
    pending: 'warning',
    confirmed: 'success',
    rejected: 'danger',
  }
  return map[status || 'pending'] || 'info'
}

function confirmLabel(status: string | undefined): string {
  const map: Record<string, string> = {
    pending: '待确认',
    confirmed: '已确认',
    rejected: '已拒绝',
  }
  return map[status || 'pending'] || '待确认'
}
</script>

<style scoped>
.policy-review-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.policy-review-panel__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter, #ebeef5);
}

.policy-review-panel__body {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.policy-review-panel__toc {
  width: 240px;
  border-right: 1px solid var(--el-border-color-lighter, #ebeef5);
  overflow-y: auto;
  padding: 12px;
}

.policy-review-panel__toc h4 {
  margin: 0 0 8px;
  font-size: 14px;
  color: #303133;
}

.policy-review-panel__toc ul {
  list-style: none;
  padding: 0;
  margin: 0;
}

.toc-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  cursor: pointer;
  border-radius: 4px;
  font-size: 13px;
}

.toc-item:hover {
  background: var(--gt-color-primary-bg, #f4f0fa);
}

.toc-item--active {
  background: var(--gt-color-primary-bg, #f4f0fa);
  font-weight: 500;
}

.toc-item--level-2 {
  padding-left: 20px;
}

.toc-item--level-3 {
  padding-left: 36px;
}

.toc-item__title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.policy-review-panel__content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.clause-detail h3 {
  margin: 0 0 12px;
  font-size: 16px;
}

.clause-detail__columns {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
  margin-bottom: 12px;
}

.clause-col {
  border: 1px solid var(--el-border-color-lighter, #ebeef5);
  border-radius: 4px;
  padding: 12px;
}

.clause-col h5 {
  margin: 0 0 8px;
  font-size: 13px;
  color: #909399;
}

.clause-text {
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}

.clause-detail__meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

.clause-detail__vars {
  margin-left: 12px;
  font-size: 12px;
  color: #909399;
}

:deep(.var-highlight) {
  background: #fef0c7;
  padding: 0 2px;
  border-radius: 2px;
  font-weight: 500;
}

:deep(.no-content) {
  color: #c0c4cc;
  font-style: italic;
}
</style>
