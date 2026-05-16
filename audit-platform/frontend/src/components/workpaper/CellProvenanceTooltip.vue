<template>
  <div class="gt-cell-provenance-tooltip" v-if="provenance">
    <el-popover
      :visible="visible"
      placement="bottom-start"
      :width="320"
      trigger="hover"
      popper-class="gt-provenance-popover"
      :show-after="300"
      :hide-after="100"
    >
      <template #reference>
        <slot />
      </template>

      <!-- Tooltip 内容 -->
      <div class="gt-provenance-content">
        <div class="gt-provenance-header">
          <span class="gt-provenance-icon">{{ sourceIcon }}</span>
          <span class="gt-provenance-title">数据来源</span>
        </div>

        <div class="gt-provenance-body">
          <!-- 来源类型 -->
          <div class="gt-provenance-row">
            <span class="gt-provenance-label">来源类型：</span>
            <el-tag :type="sourceTagType" size="small">{{ sourceLabel }}</el-tag>
          </div>

          <!-- 来源引用 -->
          <div class="gt-provenance-row" v-if="provenance.source_ref">
            <span class="gt-provenance-label">来源引用：</span>
            <span class="gt-provenance-value">{{ provenance.source_ref }}</span>
          </div>

          <!-- 填充时间 -->
          <div class="gt-provenance-row" v-if="provenance.filled_at">
            <span class="gt-provenance-label">填充时间：</span>
            <span class="gt-provenance-value">{{ formatTime(provenance.filled_at) }}</span>
          </div>

          <!-- 服务版本 -->
          <div class="gt-provenance-row" v-if="provenance.filled_by_service_version">
            <span class="gt-provenance-label">服务版本：</span>
            <span class="gt-provenance-value gt-provenance-version">
              {{ provenance.filled_by_service_version }}
            </span>
          </div>
        </div>

        <!-- 跳转链接（manual 无跳转） -->
        <div class="gt-provenance-footer" v-if="hasJumpLink">
          <el-button
            type="primary"
            size="small"
            link
            @click="onJump"
          >
            {{ jumpLabel }} →
          </el-button>
        </div>
      </div>
    </el-popover>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

/**
 * CellProvenanceTooltip — 单元格来源 tooltip
 *
 * 单元格 hover 显示来源信息（source 类型、source_ref、filled_at）。
 * 来源点击跳转：
 *   - trial_balance → TrialBalance 页高亮该行
 *   - prior_year → 打开对比上年抽屉
 *   - ledger → 打开序时账穿透抽屉
 *   - formula → 无跳转（公式计算）
 *   - manual → 无跳转（手动填写）
 *   - ocr → 跳转附件预览
 *
 * Validates: Requirements 7
 */

export interface CellProvenanceData {
  source: 'trial_balance' | 'prior_year' | 'formula' | 'ledger' | 'manual' | 'ocr'
  source_ref: string | null
  filled_at: string | null
  filled_by_service_version: string | null
}

const props = defineProps<{
  /** 当前单元格的 provenance 数据 */
  provenance: CellProvenanceData | null
  /** 当前单元格引用（如 "D5"） */
  cellRef?: string
  /** 控制 popover 可见性 */
  visible?: boolean
}>()

const emit = defineEmits<{
  /** 跳转到试算表页面 */
  (e: 'navigate-trial-balance', sourceRef: string): void
  /** 打开上年对比抽屉 */
  (e: 'navigate-prior-year'): void
  /** 打开序时账穿透抽屉 */
  (e: 'navigate-ledger', sourceRef: string): void
  /** 跳转到 OCR 附件预览 */
  (e: 'navigate-ocr', sourceRef: string): void
}>()

/** 来源类型中文标签 */
const SOURCE_LABELS: Record<string, string> = {
  trial_balance: '试算平衡表',
  prior_year: '上年底稿',
  formula: '公式计算',
  ledger: '序时账',
  manual: '手动填写',
  ocr: 'OCR 提取',
}

/** 来源类型图标 */
const SOURCE_ICONS: Record<string, string> = {
  trial_balance: '📊',
  prior_year: '📜',
  formula: '🔢',
  ledger: '📒',
  manual: '✏️',
  ocr: '📄',
}

/** 来源类型 tag 颜色 */
const SOURCE_TAG_TYPES: Record<string, 'primary' | 'success' | 'info' | 'warning' | 'danger' | undefined> = {
  trial_balance: 'primary',
  prior_year: 'success',
  formula: 'info',
  ledger: 'warning',
  manual: undefined,
  ocr: 'danger',
}

/** 跳转链接文案 */
const JUMP_LABELS: Record<string, string> = {
  trial_balance: '查看试算表',
  prior_year: '对比上年',
  ledger: '查看序时账',
  ocr: '查看附件',
}

const sourceLabel = computed(() => {
  if (!props.provenance) return ''
  return SOURCE_LABELS[props.provenance.source] || props.provenance.source
})

const sourceIcon = computed(() => {
  if (!props.provenance) return ''
  return SOURCE_ICONS[props.provenance.source] || '📋'
})

const sourceTagType = computed((): 'primary' | 'success' | 'info' | 'warning' | 'danger' | undefined => {
  if (!props.provenance) return undefined
  return SOURCE_TAG_TYPES[props.provenance.source] || 'info'
})

/** 是否有跳转链接（manual 和 formula 无跳转） */
const hasJumpLink = computed(() => {
  if (!props.provenance) return false
  return ['trial_balance', 'prior_year', 'ledger', 'ocr'].includes(props.provenance.source)
})

const jumpLabel = computed(() => {
  if (!props.provenance) return ''
  return JUMP_LABELS[props.provenance.source] || '查看来源'
})

/** 格式化时间戳 */
function formatTime(ts: string): string {
  if (!ts) return ''
  try {
    return ts.slice(0, 19).replace('T', ' ')
  } catch {
    return ts
  }
}

/** 点击跳转 */
function onJump() {
  if (!props.provenance) return

  switch (props.provenance.source) {
    case 'trial_balance':
      emit('navigate-trial-balance', props.provenance.source_ref || '')
      break
    case 'prior_year':
      emit('navigate-prior-year')
      break
    case 'ledger':
      emit('navigate-ledger', props.provenance.source_ref || '')
      break
    case 'ocr':
      emit('navigate-ocr', props.provenance.source_ref || '')
      break
  }
}
</script>

<style scoped>
.gt-cell-provenance-tooltip {
  display: inline-block;
}

.gt-provenance-content {
  padding: 4px 0;
}

.gt-provenance-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--el-border-color-lighter, #ebeef5);
}

.gt-provenance-icon {
  font-size: var(--gt-font-size-md);
}

.gt-provenance-title {
  font-weight: 600;
  font-size: var(--gt-font-size-sm);
  color: var(--el-text-color-primary, #303133);
}

.gt-provenance-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.gt-provenance-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--gt-font-size-xs);
}

.gt-provenance-label {
  color: var(--el-text-color-secondary, #909399);
  white-space: nowrap;
  min-width: 70px;
}

.gt-provenance-value {
  color: var(--el-text-color-primary, #303133);
  word-break: break-all;
}

.gt-provenance-version {
  font-family: monospace;
  font-size: var(--gt-font-size-xs);
  color: var(--el-text-color-secondary, #909399);
}

.gt-provenance-footer {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid var(--el-border-color-lighter, #ebeef5);
}
</style>
