<template>
  <template v-if="result">
    <div class="gt-rv-balance-bar" :class="'gt-rv-balance-bar--' + result.status" data-testid="report-balance-banner">
      <span class="gt-rv-balance-bar__icon">{{ result.status === 'passed' ? '✓' : result.status === 'error' ? '✗' : 'ℹ' }}</span>
      <span class="gt-rv-balance-bar__text">{{ result.message }}</span>
      <el-button v-if="result.checks.length" text size="small" type="primary" @click="expanded = !expanded">
        {{ expanded ? '收起' : '展开明细' }}
      </el-button>
      <el-button text size="small" style="margin-left: auto; padding: 0" aria-label="关闭报表审核提示" @click="$emit('close')">✕</el-button>
    </div>
    <div v-if="result.failed_count != null || result.hint_count != null" class="gt-rv-balance-counts">
      后端汇总：失败 {{ result.failed_count ?? '—' }} 项，提示 {{ result.hint_count ?? '—' }} 项（提示不计入失败）
    </div>
    <transition name="el-zoom-in-top">
      <div v-if="expanded && result.checks.length" class="gt-rv-balance-detail">
        <div v-for="(check, index) in details" :key="index" class="gt-rv-balance-detail__row" :data-check-status="check.presentation.status">
          <span :style="{ color: checkColor(check.presentation.status, check.presentation.isHint) }">{{ check.presentation.label }}</span>
          <span style="flex: 1">{{ check.name }}</span>
          <span>严重度：{{ check.presentation.severityLabel }}</span>
          <span>期望 {{ reportCheckValueText(check.expected) }}，实际 {{ reportCheckValueText(check.actual) }}，差 {{ reportCheckValueText(check.diff) }}</span>
          <span v-if="check.presentation.reason">原因：{{ check.presentation.reason }}</span>
          <el-button text size="small" type="primary" style="padding: 0" @click="$emit('locate', check.name)">定位 →</el-button>
        </div>
      </div>
    </transition>
  </template>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { getReportBalanceDetails, reportCheckValueText, type ReportBalanceResult, type ReportCheckStatus } from '@/services/reportCheckPresentation'
const props = defineProps<{ result: ReportBalanceResult | null }>()
defineEmits<{ (event: 'close'): void; (event: 'locate', name: string): void }>()
const expanded = ref(false)
const details = computed(() => getReportBalanceDetails(props.result?.checks))
watch(() => props.result, () => { expanded.value = false })
function checkColor(status: ReportCheckStatus, hint: boolean) {
  if (status === 'passed') return 'var(--el-color-success)'
  if (status === 'error' || (status === 'failed' && !hint)) return 'var(--el-color-danger)'
  return status === 'failed' ? 'var(--el-color-warning)' : 'var(--el-text-color-secondary)'
}
</script>

<style scoped>
.gt-rv-balance-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 16px;
  margin-bottom: 6px;
  border-radius: 6px;
  font-size: 13px;
  background: var(--el-fill-color-light, #f5f7fa);
  border: 1px solid var(--el-border-color-light, #e4e7ed);
}
.gt-rv-balance-bar--warning,
.gt-rv-balance-bar--hint { background: #fdf6ec; border-color: #faecd8; }
.gt-rv-balance-bar--error { background: #fef0f0; border-color: #fde2e2; }
.gt-rv-balance-bar--passed { background: #f0f9eb; border-color: #e1f3d8; }
.gt-rv-balance-bar__icon { font-size: 14px; }
.gt-rv-balance-bar__text { font-weight: 500; color: var(--el-text-color-primary, #303133); }
.gt-rv-balance-detail {
  margin-bottom: 8px;
  padding: 8px 16px;
  background: #fffbf0;
  border: 1px solid #faecd8;
  border-radius: 6px;
  font-size: 12px;
}
.gt-rv-balance-detail__row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 4px 0;
  border-bottom: 1px solid rgba(0, 0, 0, 0.04);
}
.gt-rv-balance-detail__row:last-child { border-bottom: none; }
.gt-rv-balance-detail__row:hover { background: rgba(75, 45, 119, 0.04); border-radius: 4px; }
.gt-rv-balance-counts { font-size: 12px; color: var(--gt-color-text-secondary); margin: 4px 0 8px; }
</style>
