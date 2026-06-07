<!--
  FieldSourcePanel.vue — 字段来源面板（MVP 最小接入）

  Task 7：前端来源面板最小接入
  - 7.1 在审定表关键字段提供来源入口
  - 7.2 展示来源、编辑权限、人工确认、stale 策略
  - 7.3 缺失来源时显示结构化 unknown，不报错
  - 7.4 历史 schema 缺少 sheet_type 时，导航回退启发式且不破坏现有渲染

  Validates: Requirements 2.2, 2.4, 5.2
-->
<template>
  <div class="gt-field-source-panel">
    <template v-if="fieldSource">
      <div class="gt-field-source-panel__header">
        <span class="gt-field-source-panel__label">{{ fieldSource.label }}</span>
        <el-tag size="small" :type="sourceTagType" effect="light">
          {{ sourceLabel }}
        </el-tag>
      </div>
      <div class="gt-field-source-panel__detail">
        <div class="gt-field-source-panel__row">
          <span class="gt-field-source-panel__key">来源模块</span>
          <span class="gt-field-source-panel__value">{{ sourceModule }}</span>
        </div>
        <div class="gt-field-source-panel__row">
          <span class="gt-field-source-panel__key">可编辑</span>
          <span class="gt-field-source-panel__value">{{ fieldSource.editable ? '是' : '否' }}</span>
        </div>
        <div class="gt-field-source-panel__row">
          <span class="gt-field-source-panel__key">允许覆盖</span>
          <span class="gt-field-source-panel__value">{{ fieldSource.override_allowed ? '是' : '否' }}</span>
        </div>
        <div class="gt-field-source-panel__row">
          <span class="gt-field-source-panel__key">需人工确认</span>
          <span class="gt-field-source-panel__value">{{ fieldSource.requires_confirmation ? '是' : '否' }}</span>
        </div>
        <div class="gt-field-source-panel__row">
          <span class="gt-field-source-panel__key">刷新策略</span>
          <span class="gt-field-source-panel__value">{{ stalePolicyLabel }}</span>
        </div>
      </div>
    </template>
    <template v-else>
      <div class="gt-field-source-panel__unknown">
        <span class="gt-field-source-panel__unknown-icon">ℹ️</span>
        <span class="gt-field-source-panel__unknown-text">来源未知（该字段暂未配置来源契约）</span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { FieldSourceContract, FieldSourceType, StalePolicy } from '@/types/workpaperSemanticContract'

const props = defineProps<{
  fieldSource: FieldSourceContract | null
  fieldId: string
}>()

/** source_type → 中文标签 */
const SOURCE_TYPE_LABELS: Record<FieldSourceType, string> = {
  trial_balance: '试算表',
  formula: '公式计算',
  manual: '手工录入',
  linked: '关联引用',
  ai_generated: 'AI 生成',
}

/** stale_policy → 中文标签 */
const STALE_POLICY_LABELS: Record<StalePolicy, string> = {
  refresh_on_tb_updated: '试算表更新时刷新',
  refresh_on_report_regen: '报表重生成时刷新',
  manual_refresh: '手动刷新',
  none: '无',
}

/** source_type → el-tag type 映射 */
const SOURCE_TAG_TYPES: Record<FieldSourceType, string> = {
  trial_balance: '',       // default(purple via scoped override)
  formula: 'success',
  manual: 'warning',
  linked: 'info',
  ai_generated: 'danger',
}

const sourceLabel = computed(() => {
  if (!props.fieldSource) return ''
  return SOURCE_TYPE_LABELS[props.fieldSource.source_type] ?? props.fieldSource.source_type
})

const sourceTagType = computed(() => {
  if (!props.fieldSource) return ''
  return SOURCE_TAG_TYPES[props.fieldSource.source_type] ?? ''
})

const sourceModule = computed(() => {
  if (!props.fieldSource?.source_ref) return '未知'
  return (props.fieldSource.source_ref as Record<string, unknown>).module as string ?? '未知'
})

const stalePolicyLabel = computed(() => {
  if (!props.fieldSource) return ''
  return STALE_POLICY_LABELS[props.fieldSource.stale_policy] ?? props.fieldSource.stale_policy
})
</script>

<style scoped>
.gt-field-source-panel {
  padding: 12px;
  border: 1px solid var(--gt-color-border-purple, #e8e4f0);
  border-radius: 6px;
  background: var(--gt-color-primary-bg, #f4f0fa);
  font-size: 13px;
  line-height: 1.6;
}

.gt-field-source-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--gt-color-border-purple, #e8e4f0);
}

.gt-field-source-panel__label {
  font-weight: 600;
  color: var(--gt-color-primary, #4b2d77);
}

.gt-field-source-panel__detail {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.gt-field-source-panel__row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.gt-field-source-panel__key {
  flex: 0 0 80px;
  color: var(--gt-color-text-secondary, #6e6e73);
}

.gt-field-source-panel__value {
  color: var(--gt-color-text-primary, #1d1d1f);
}

.gt-field-source-panel__unknown {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 0;
  color: var(--gt-color-text-secondary, #6e6e73);
}

.gt-field-source-panel__unknown-icon {
  flex: 0 0 auto;
}

.gt-field-source-panel__unknown-text {
  font-size: 13px;
}

/* el-tag default type scoped purple override (GT brand) */
.gt-field-source-panel :deep(.el-tag:not(.el-tag--success):not(.el-tag--warning):not(.el-tag--info):not(.el-tag--danger)) {
  --el-tag-bg-color: var(--gt-color-primary-bg, #f4f0fa);
  --el-tag-border-color: var(--gt-color-border-purple-light, #d8b8ee);
  --el-tag-text-color: var(--gt-color-primary, #4b2d77);
}
</style>
