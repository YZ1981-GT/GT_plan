<template>
  <div class="gt-smart-tip-list" v-if="findings.length > 0">
    <!-- 聚合 badge -->
    <el-popover
      :visible="dropdownVisible"
      placement="top-end"
      :width="420"
      trigger="click"
      popper-class="gt-smart-tip-popover"
      @update:visible="(v: boolean) => dropdownVisible = v"
    >
      <template #reference>
        <span
          class="gt-smart-tip-badge"
          @click="dropdownVisible = !dropdownVisible"
        >
          ⚠ {{ findings.length }}
        </span>
      </template>

      <!-- 下拉列表 -->
      <div class="gt-smart-tip-dropdown">
        <div class="gt-smart-tip-dropdown-header">
          <span class="gt-smart-tip-dropdown-title">审计发现 ({{ findings.length }})</span>
          <el-button size="small" text @click="dropdownVisible = false">收起</el-button>
        </div>
        <div class="gt-smart-tip-dropdown-body">
          <div
            v-for="(item, idx) in findings"
            :key="idx"
            class="gt-smart-tip-item"
            :class="severityClass(item.severity)"
            @click="onFindingClick(item)"
          >
            <span class="gt-smart-tip-item-severity">{{ severityIcon(item.severity) }}</span>
            <span class="gt-smart-tip-item-cell" v-if="item.cell_reference">
              {{ item.cell_reference }}
            </span>
            <span class="gt-smart-tip-item-message">{{ item.message }}</span>
          </div>
        </div>
      </div>
    </el-popover>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

/**
 * SmartTipList — 替代现有单行 smartTip
 *
 * 聚合 badge "⚠ N"，点击展开下拉列表。
 * 每条 finding 点击 emit navigate-to-cell 事件，
 * 由 WorkpaperEditor 调用 Univer API 滚动到 cell_reference + 闪烁 3 次。
 * 按 severity 染色：blocking=红 / warning=黄 / info=蓝。
 *
 * Validates: Requirements 3
 */

export interface SmartTipFinding {
  /** 单元格引用，如 "D5" 或跨 sheet "利润表!B5" */
  cell_reference?: string | null
  /** 提示消息 */
  message: string
  /** 严重级别 */
  severity: 'blocking' | 'warning' | 'info'
  /** 规则 ID（可选） */
  rule_id?: string
  /** 所在 sheet 名称（可选，跨 sheet 时使用） */
  sheet_name?: string
}

const props = defineProps<{
  findings: SmartTipFinding[]
}>()

const emit = defineEmits<{
  /** 点击某条 finding，请求导航到对应单元格 */
  (e: 'navigate-to-cell', finding: SmartTipFinding): void
}>()

const dropdownVisible = ref(false)

function severityClass(severity: string): string {
  switch (severity) {
    case 'blocking': return 'gt-severity-blocking'
    case 'warning': return 'gt-severity-warning'
    case 'info': return 'gt-severity-info'
    default: return 'gt-severity-info'
  }
}

function severityIcon(severity: string): string {
  switch (severity) {
    case 'blocking': return '🔴'
    case 'warning': return '🟡'
    case 'info': return '🔵'
    default: return '🔵'
  }
}

function onFindingClick(item: SmartTipFinding) {
  emit('navigate-to-cell', item)
  dropdownVisible.value = false
}
</script>

<style scoped>
.gt-smart-tip-list {
  display: inline-flex;
  align-items: center;
  margin-left: auto;
}

.gt-smart-tip-badge {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 2px 8px;
  border-radius: 10px;
  background: rgba(230, 162, 60, 0.15);
  color: var(--gt-color-wheat);
  font-size: var(--gt-font-size-xs);
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s ease;
  user-select: none;
}

.gt-smart-tip-badge:hover {
  background: rgba(230, 162, 60, 0.3);
}

.gt-smart-tip-dropdown {
  max-height: 320px;
  display: flex;
  flex-direction: column;
}

.gt-smart-tip-dropdown-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--gt-color-border-lighter);
  margin-bottom: 8px;
}

.gt-smart-tip-dropdown-title {
  font-weight: 600;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-primary);
}

.gt-smart-tip-dropdown-body {
  overflow-y: auto;
  max-height: 260px;
}

.gt-smart-tip-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s ease;
  margin-bottom: 4px;
}

.gt-smart-tip-item:hover {
  filter: brightness(0.95);
}

.gt-smart-tip-item:last-child {
  margin-bottom: 0;
}

/* Severity 染色 */
.gt-severity-blocking {
  background: rgba(245, 108, 108, 0.1);
  border-left: 3px solid var(--gt-color-coral);
}

.gt-severity-blocking:hover {
  background: rgba(245, 108, 108, 0.18);
}

.gt-severity-warning {
  background: rgba(230, 162, 60, 0.1);
  border-left: 3px solid var(--gt-color-wheat);
}

.gt-severity-warning:hover {
  background: rgba(230, 162, 60, 0.18);
}

.gt-severity-info {
  background: rgba(64, 158, 255, 0.08);
  border-left: 3px solid var(--gt-color-teal);
}

.gt-severity-info:hover {
  background: rgba(64, 158, 255, 0.15);
}

.gt-smart-tip-item-severity {
  flex-shrink: 0;
  font-size: var(--gt-font-size-xs);
  line-height: 1.4;
}

.gt-smart-tip-item-cell {
  flex-shrink: 0;
  font-family: 'Courier New', monospace;
  font-size: var(--gt-font-size-xs);
  font-weight: 600;
  color: var(--gt-color-text-regular);
  background: rgba(0, 0, 0, 0.04);
  padding: 1px 5px;
  border-radius: 3px;
}

.gt-smart-tip-item-message {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-primary);
  line-height: 1.4;
  word-break: break-word;
}
</style>
