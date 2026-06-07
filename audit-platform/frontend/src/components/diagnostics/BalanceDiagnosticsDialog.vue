<template>
  <el-dialog
    v-model="visible"
    title="借贷不平衡诊断"
    width="780px"
    :close-on-click-modal="false"
    @close="onClose"
  >
    <!-- 口径概要 -->
    <div class="bd-caliber-bar">
      <span class="bd-caliber-label">平衡口径：</span>
      <el-tag type="primary" effect="plain" size="small">{{ caliberLabel }}</el-tag>
      <span v-if="result.status !== 'passed'" class="bd-difference">
        差额：<strong>{{ formatAmount(result.difference) }}</strong>
      </span>
      <el-tag
        :type="statusTagType"
        size="small"
        effect="dark"
        class="bd-status-tag"
      >
        {{ statusLabel }}
      </el-tag>
    </div>

    <!-- 原因清单（按 severity 降序） -->
    <div class="bd-causes" v-if="sortedCauses.length">
      <h4 class="bd-section-title">可能原因</h4>
      <div
        v-for="(cause, idx) in sortedCauses"
        :key="idx"
        class="bd-cause-item"
        :class="`bd-cause-item--severity-${cause.severity}`"
      >
        <span class="bd-cause-icon">{{ getSeverityIcon(cause.severity) }}</span>
        <span class="bd-cause-desc">{{ cause.description }}</span>
        <el-tag size="small" effect="plain" :type="getSeverityTagType(cause.severity)">
          置信度 {{ (cause.confidence * 100).toFixed(0) }}%
        </el-tag>
      </div>
    </div>

    <!-- 未匹配科目清单 -->
    <div class="bd-unmatched" v-if="result.unmatched_accounts.length">
      <h4 class="bd-section-title">未匹配报表行次科目</h4>
      <el-table :data="result.unmatched_accounts" size="small" max-height="200" stripe>
        <el-table-column prop="account_code" label="科目编码" width="100" />
        <el-table-column prop="account_name" label="科目名称" width="140" />
        <el-table-column prop="amount" label="金额" width="120" align="right">
          <template #default="{ row }">{{ formatAmount(row.amount) }}</template>
        </el-table-column>
        <el-table-column prop="mapping_status" label="映射状态" width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="getMappingStatusType(row.mapping_status)">
              {{ getMappingStatusLabel(row.mapping_status) }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 跳转修复入口 -->
    <div class="bd-jump-targets" v-if="result.jump_targets.length">
      <h4 class="bd-section-title">修复入口</h4>
      <div class="bd-jump-buttons">
        <el-button
          v-for="(target, idx) in result.jump_targets"
          :key="idx"
          type="primary"
          size="small"
          @click="onJump(target)"
        >
          {{ target.label }}
        </el-button>
      </div>
    </div>

    <template #footer>
      <el-button @click="onClose">关闭</el-button>
      <el-button type="primary" @click="$emit('rerun')">重新诊断</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type {
  BalanceDiagnosticsResult,
  DiagnosticCause,
  DiagnosticJumpTarget,
} from '@/types/balance-diagnostics'
import { CALIBER_LABELS } from '@/types/balance-diagnostics'

const props = defineProps<{
  modelValue: boolean
  result: BalanceDiagnosticsResult
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'jump': [target: DiagnosticJumpTarget]
  'rerun': []
}>()

const visible = ref(props.modelValue)

watch(() => props.modelValue, (val) => { visible.value = val })
watch(visible, (val) => { emit('update:modelValue', val) })

const caliberLabel = computed(() => CALIBER_LABELS[props.result.caliber] || props.result.caliber)

const statusLabel = computed(() => {
  if (props.result.status === 'passed') return '通过'
  if (props.result.status === 'warning') return '警告'
  return '阻断'
})

const statusTagType = computed(() => {
  if (props.result.status === 'passed') return 'success'
  if (props.result.status === 'warning') return 'warning'
  return 'danger'
})

/** 原因按 severity 降序排列 */
const sortedCauses = computed(() => {
  return [...props.result.likely_causes].sort((a, b) => b.severity - a.severity)
})

function getSeverityIcon(severity: number): string {
  if (severity >= 4) return '🔴'
  if (severity >= 3) return '🟡'
  return '🟢'
}

function getSeverityTagType(severity: number): 'danger' | 'warning' | 'info' {
  if (severity >= 4) return 'danger'
  if (severity >= 3) return 'warning'
  return 'info'
}

function getMappingStatusLabel(status: string): string {
  if (status === 'seed_missing') return 'Seed 缺失'
  if (status === 'unconfirmed') return '未确认'
  return '未映射'
}

function getMappingStatusType(status: string): 'danger' | 'warning' | 'info' {
  if (status === 'seed_missing') return 'danger'
  if (status === 'unconfirmed') return 'warning'
  return 'info'
}

function formatAmount(val: number): string {
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function onJump(target: DiagnosticJumpTarget) {
  emit('jump', target)
}

function onClose() {
  visible.value = false
}
</script>

<style scoped>
.bd-caliber-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--gt-color-primary-bg, #f4f0fa);
  border-radius: 8px;
  margin-bottom: 16px;
  border: 1px solid var(--gt-color-border-purple-light, #d8b8ee);
}

.bd-caliber-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--gt-color-primary, #4b2d77);
}

.bd-difference {
  margin-left: auto;
  font-size: 13px;
  color: var(--gt-color-coral, #f56c6c);
}

.bd-status-tag {
  margin-left: 8px;
}

.bd-section-title {
  font-size: 14px;
  font-weight: 600;
  margin: 16px 0 8px;
  color: var(--gt-color-primary, #4b2d77);
}

.bd-causes {
  margin-bottom: 12px;
}

.bd-cause-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  margin-bottom: 6px;
  border: 1px solid var(--gt-color-border-lighter, #ebeef5);
}

.bd-cause-item--severity-5,
.bd-cause-item--severity-4 {
  background: var(--gt-bg-danger, #fef0f0);
  border-left: 3px solid var(--gt-color-coral, #f56c6c);
}

.bd-cause-item--severity-3 {
  background: var(--gt-bg-warning, #fdf6ec);
  border-left: 3px solid var(--gt-color-wheat, #e6a23c);
}

.bd-cause-item--severity-2,
.bd-cause-item--severity-1 {
  border-left: 3px solid var(--gt-color-success, #67c23a);
}

.bd-cause-icon {
  font-size: 16px;
}

.bd-cause-desc {
  flex: 1;
  font-size: 13px;
}

.bd-unmatched {
  margin-bottom: 12px;
}

.bd-jump-targets {
  margin-bottom: 8px;
}

.bd-jump-buttons {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
