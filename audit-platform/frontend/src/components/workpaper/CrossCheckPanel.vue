<script setup lang="ts">
/**
 * CrossCheckPanel — 跨科目校验结果展示 + 差异明细
 *
 * Sprint 4 Task 4.6
 */
import { ref, onMounted, watch } from 'vue'
import { useCrossCheck } from '@/composables/useCrossCheck'
import type { CrossCheckResult } from '@/composables/useCrossCheck'

const props = defineProps<{
  projectId: string
  year: number
}>()

const { results, rules, loading, executing, summary, passRate, hasBlockingFailures, execute, fetchResults, fetchRules } = useCrossCheck(props.projectId)

const expandedRow = ref<string | null>(null)

onMounted(async () => {
  await Promise.all([fetchResults(props.year), fetchRules()])
})

watch(() => props.year, async (newYear) => {
  if (newYear) await fetchResults(newYear)
})

async function handleExecute() {
  await execute(props.year)
}

function toggleExpand(id: string) {
  expandedRow.value = expandedRow.value === id ? null : id
}

function getStatusType(status: string) {
  switch (status) {
    case 'pass': return 'success'
    case 'fail': return 'danger'
    case 'skip': return 'info'
    case 'error': return 'warning'
    default: return 'info'
  }
}

function getStatusLabel(status: string) {
  switch (status) {
    case 'pass': return '通过'
    case 'fail': return '差异'
    case 'skip': return '跳过'
    case 'error': return '错误'
    default: return status
  }
}

function getSeverityType(ruleId: string) {
  const rule = rules.value.find(r => r.rule_id === ruleId)
  if (!rule) return 'info'
  switch (rule.severity) {
    case 'blocking': return 'danger'
    case 'warning': return 'warning'
    default: return 'info'
  }
}

function formatAmount(val: number | null): string {
  if (val === null || val === undefined) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function getRuleDescription(ruleId: string): string {
  const rule = rules.value.find(r => r.rule_id === ruleId)
  return rule?.description || ruleId
}
</script>

<template>
  <div class="cross-check-panel">
    <!-- 顶部操作栏 -->
    <div class="panel-header">
      <div class="header-left">
        <span class="panel-title">跨科目校验</span>
        <el-tag v-if="summary.total > 0" :type="hasBlockingFailures ? 'danger' : 'success'" size="small">
          {{ passRate }}% 通过
        </el-tag>
      </div>
      <el-button type="primary" size="small" :loading="executing" @click="handleExecute">
        执行校验
      </el-button>
    </div>

    <!-- 摘要卡片 -->
    <div v-if="summary.total > 0" class="summary-bar">
      <div class="summary-item">
        <span class="summary-num success">{{ summary.passed }}</span>
        <span class="summary-label">通过</span>
      </div>
      <div class="summary-item">
        <span class="summary-num danger">{{ summary.failed }}</span>
        <span class="summary-label">差异</span>
      </div>
      <div class="summary-item">
        <span class="summary-num info">{{ summary.skipped }}</span>
        <span class="summary-label">跳过</span>
      </div>
    </div>

    <!-- 结果列表 -->
    <div v-loading="loading" class="results-list">
      <div v-if="results.length === 0 && !loading" class="empty-state">
        <el-empty description="暂无校验结果，点击执行校验开始" :image-size="60" />
      </div>

      <div
        v-for="item in results"
        :key="item.id || item.rule_id"
        class="result-item"
        :class="{ expanded: expandedRow === (item.id || item.rule_id) }"
        @click="toggleExpand(item.id || item.rule_id)"
      >
        <div class="result-row">
          <div class="result-left">
            <el-tag :type="getStatusType(item.status)" size="small" effect="dark">
              {{ getStatusLabel(item.status) }}
            </el-tag>
            <el-tag :type="getSeverityType(item.rule_id)" size="small" effect="plain" class="severity-tag">
              {{ item.rule_id }}
            </el-tag>
            <span class="result-desc">{{ item.description || getRuleDescription(item.rule_id) }}</span>
          </div>
          <div class="result-right">
            <span v-if="item.difference !== null && item.status === 'fail'" class="diff-amount">
              差异: {{ formatAmount(item.difference) }}
            </span>
            <el-icon class="expand-icon"><i class="el-icon-arrow-down" /></el-icon>
          </div>
        </div>

        <!-- 展开明细 -->
        <div v-if="expandedRow === (item.id || item.rule_id)" class="result-detail">
          <div class="detail-grid">
            <div class="detail-item">
              <span class="detail-label">左侧金额</span>
              <span class="detail-value">{{ formatAmount(item.left_amount) }}</span>
            </div>
            <div class="detail-item">
              <span class="detail-label">右侧金额</span>
              <span class="detail-value">{{ formatAmount(item.right_amount) }}</span>
            </div>
            <div class="detail-item">
              <span class="detail-label">差异</span>
              <span class="detail-value" :class="{ 'text-danger': item.status === 'fail' }">
                {{ formatAmount(item.difference) }}
              </span>
            </div>
            <div class="detail-item">
              <span class="detail-label">检查时间</span>
              <span class="detail-value">{{ item.checked_at ? new Date(item.checked_at).toLocaleString('zh-CN') : '-' }}</span>
            </div>
          </div>
          <div v-if="item.details?.formula" class="detail-formula">
            <span class="detail-label">公式：</span>
            <code>{{ item.details.formula }}</code>
          </div>
          <div v-if="item.details?.failures && (item.details.failures as unknown[]).length > 0" class="detail-failures">
            <span class="detail-label">失败明细（前 {{ (item.details.failures as unknown[]).length }} 条）：</span>
            <el-table :data="(item.details.failures as Record<string, unknown>[])" size="small" max-height="200">
              <el-table-column prop="account_code" label="科目" width="120" />
              <el-table-column prop="audited" label="审定数" width="120" align="right" />
              <el-table-column prop="expected" label="预期值" width="120" align="right" />
              <el-table-column prop="difference" label="差异" width="100" align="right" />
            </el-table>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cross-check-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 12px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.summary-bar {
  display: flex;
  gap: 16px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 6px;
  margin-bottom: 12px;
}

.summary-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.summary-num {
  font-size: 16px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.summary-num.success { color: #67c23a; }
.summary-num.danger { color: #f56c6c; }
.summary-num.info { color: #909399; }

.summary-label {
  font-size: 12px;
  color: #909399;
}

.results-list {
  flex: 1;
  overflow-y: auto;
}

.empty-state {
  padding: 40px 0;
}

.result-item {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: border-color 0.2s;
}

.result-item:hover {
  border-color: #c0c4cc;
}

.result-item.expanded {
  border-color: #409eff;
}

.result-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
}

.result-left {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  min-width: 0;
}

.result-desc {
  font-size: 13px;
  color: #606266;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.severity-tag {
  font-size: 11px;
}

.result-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.diff-amount {
  font-size: 12px;
  color: #f56c6c;
  font-variant-numeric: tabular-nums;
}

.expand-icon {
  color: #c0c4cc;
  transition: transform 0.2s;
}

.result-item.expanded .expand-icon {
  transform: rotate(180deg);
}

.result-detail {
  padding: 12px;
  border-top: 1px solid #ebeef5;
  background: #fafafa;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  margin-bottom: 8px;
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.detail-label {
  font-size: 11px;
  color: #909399;
}

.detail-value {
  font-size: 13px;
  color: #303133;
  font-variant-numeric: tabular-nums;
}

.text-danger {
  color: #f56c6c;
  font-weight: 600;
}

.detail-formula {
  margin-top: 8px;
  padding: 6px 8px;
  background: #fff;
  border-radius: 4px;
  border: 1px solid #ebeef5;
}

.detail-formula code {
  font-size: 12px;
  color: #606266;
  word-break: break-all;
}

.detail-failures {
  margin-top: 8px;
}
</style>
