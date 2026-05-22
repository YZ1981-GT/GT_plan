<template>
  <!--
    TraceSourcePopover — 来源追溯弹窗
    附注 auto cell / 报表行点击后显示来源报表行 + 构成科目列表
    ADR-F1: 使用 el-popover（轻量弹出层），追溯信息量小（1 报表行 + 2-5 科目）
    Validates: Requirements F1.1, F1.2
  -->
  <el-popover
    :visible="visible"
    trigger="click"
    placement="bottom-start"
    :width="380"
    popper-class="gt-trace-popover"
    @update:visible="$emit('update:visible', $event)"
  >
    <template #reference>
      <slot />
    </template>

    <div class="gt-trace-content">
      <!-- Loading state -->
      <div v-if="loading" class="gt-trace-loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>加载来源数据...</span>
      </div>

      <!-- Empty state -->
      <div v-else-if="!traceData || !traceData.report_line" class="gt-trace-empty">
        <el-icon><InfoFilled /></el-icon>
        <span>暂无来源数据</span>
      </div>

      <!-- Trace content -->
      <template v-else>
        <!-- 来源报表行 -->
        <div class="gt-trace-header">
          <span class="gt-trace-label">来源报表行</span>
          <div class="gt-trace-report-line">
            <span class="gt-trace-item-name">{{ traceData.report_line.item_name }}</span>
            <span class="gt-amt">{{ formatAmount(traceData.report_line.amount) }}</span>
          </div>
        </div>

        <!-- 构成科目列表 -->
        <div v-if="traceData.tb_accounts && traceData.tb_accounts.length > 0" class="gt-trace-accounts">
          <span class="gt-trace-label">构成科目</span>
          <div class="gt-trace-account-list">
            <div
              v-for="account in traceData.tb_accounts"
              :key="account.code"
              class="gt-trace-account-row"
            >
              <span class="gt-trace-account-code gt-amt">{{ account.code }}</span>
              <span class="gt-trace-account-name">{{ account.name }}</span>
              <span class="gt-trace-account-amount gt-amt">{{ formatAmount(account.closing_balance) }}</span>
              <span class="gt-trace-account-pct">({{ formatPct(account.pct) }})</span>
            </div>
          </div>
        </div>

        <!-- 底部跳转按钮 -->
        <div class="gt-trace-footer">
          <el-button
            type="primary"
            text
            size="small"
            @click="handleJumpToTB"
          >
            跳转到试算表 →
          </el-button>
        </div>
      </template>
    </div>
  </el-popover>
</template>

<script setup lang="ts">
import { Loading, InfoFilled } from '@element-plus/icons-vue'

export interface TraceReportLine {
  line_code: string
  item_name: string
  amount: number
}

export interface TraceTBAccount {
  code: string
  name: string
  closing_balance: number
  pct: number
}

export interface TraceSourceData {
  source_type: string
  report_line: TraceReportLine | null
  tb_accounts: TraceTBAccount[]
}

const props = withDefaults(
  defineProps<{
    /** 追溯数据 */
    traceData: TraceSourceData | null
    /** 是否显示 */
    visible?: boolean
    /** 是否加载中 */
    loading?: boolean
  }>(),
  {
    visible: false,
    loading: false,
  },
)

const emit = defineEmits<{
  'update:visible': [value: boolean]
  'jump-to-tb': [accountCode?: string]
}>()

/** 格式化金额 */
function formatAmount(value: number | null | undefined): string {
  if (value == null) return '—'
  return `¥${value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

/** 格式化占比 */
function formatPct(value: number | null | undefined): string {
  if (value == null) return '—'
  return `${value.toFixed(1)}%`
}

/** 跳转到试算表 */
function handleJumpToTB() {
  const firstAccount = props.traceData?.tb_accounts?.[0]
  emit('jump-to-tb', firstAccount?.code)
}
</script>

<style scoped>
.gt-trace-content {
  padding: 4px 0;
}

.gt-trace-loading,
.gt-trace-empty {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 0;
  color: var(--gt-text-secondary, #999);
  font-size: 13px;
}

.gt-trace-loading .is-loading {
  animation: rotating 1.5s linear infinite;
}

.gt-trace-header {
  margin-bottom: 12px;
}

.gt-trace-label {
  display: block;
  font-size: 12px;
  color: var(--gt-text-secondary, #999);
  margin-bottom: 4px;
}

.gt-trace-report-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 8px;
  background: var(--gt-bg-secondary, #f8f9fa);
  border-radius: 4px;
}

.gt-trace-item-name {
  font-weight: 500;
  color: var(--gt-text-primary, #1a1a1a);
  font-size: 14px;
}

.gt-trace-accounts {
  margin-bottom: 12px;
}

.gt-trace-account-list {
  border: 1px solid var(--gt-border-color, #e4e7ed);
  border-radius: 4px;
  overflow: hidden;
}

.gt-trace-account-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  font-size: 13px;
  border-bottom: 1px solid var(--gt-border-color, #e4e7ed);
}

.gt-trace-account-row:last-child {
  border-bottom: none;
}

.gt-trace-account-row:hover {
  background: var(--gt-table-row-hover, #f5f8fc);
}

.gt-trace-account-code {
  flex-shrink: 0;
  width: 48px;
  color: var(--gt-text-secondary, #666);
}

.gt-trace-account-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--gt-text-primary, #1a1a1a);
}

.gt-trace-account-amount {
  flex-shrink: 0;
  text-align: right;
  color: var(--gt-text-primary, #1a1a1a);
  font-weight: 500;
}

.gt-trace-account-pct {
  flex-shrink: 0;
  width: 48px;
  text-align: right;
  color: var(--gt-text-secondary, #999);
  font-size: 12px;
}

.gt-trace-footer {
  padding-top: 8px;
  border-top: 1px solid var(--gt-border-color, #e4e7ed);
  text-align: right;
}

@keyframes rotating {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>

<style>
/* 非 scoped：popover 容器样式 */
.gt-trace-popover {
  padding: 12px 16px !important;
}
</style>
