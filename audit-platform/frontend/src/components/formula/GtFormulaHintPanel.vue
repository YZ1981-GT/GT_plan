<template>
  <div class="gt-hint-panel">
    <!-- 智能公式建议（优化建议 #9：当前底稿有匹配的系统预设但尚未配置时展示推荐） -->
    <div v-if="suggestions.length" class="gt-hint-suggest">
      <div class="gt-hint-suggest__header">
        <el-icon><MagicStick /></el-icon>
        <span>💡 公式建议</span>
        <el-tag size="small" type="success" effect="light" round>{{ suggestions.length }} 条可用</el-tag>
        <span style="flex: 1;" />
        <el-button size="small" link @click="showSuggestions = !showSuggestions">
          {{ showSuggestions ? '收起' : '展开' }}
        </el-button>
      </div>
      <div v-if="showSuggestions" class="gt-hint-suggest__body">
        <div class="gt-hint-suggest__desc">以下公式来自系统预设，适用于当前底稿，可一键应用：</div>
        <div v-for="s in suggestions" :key="s.target_cell" class="gt-hint-suggest__item">
          <div class="gt-hint-suggest__item-main">
            <span class="gt-hint-suggest__cell">{{ s.target_cell }}</span>
            <code class="gt-hint-suggest__expr">{{ s.expression }}</code>
            <el-tag size="small" effect="plain" :type="suggestTypeTag(s.formula_type)">{{ suggestTypeLabel(s.formula_type) }}</el-tag>
          </div>
          <el-button size="small" type="primary" plain @click="emit('apply-suggestion', s)">应用</el-button>
        </div>
      </div>
    </div>

    <div class="gt-hint-panel__header">
      <span class="gt-hint-panel__title">
        <el-icon class="gt-hint-panel__title-icon"><MagicStick /></el-icon>
        合理性提醒清单
        <el-tag
          v-if="!loading"
          :type="hints.length ? 'warning' : 'info'"
          size="small"
          effect="light"
          round
          class="gt-hint-panel__count"
        >{{ hints.length ? `${hints.length} 条提醒` : '暂无提醒' }}</el-tag>
      </span>
      <div class="gt-hint-panel__actions">
        <span v-if="lastComputedAt" class="gt-hint-panel__computed">最近计算：{{ computedAtText }}</span>
        <span v-else class="gt-hint-panel__computed gt-hint-panel__computed--pending">尚未计算</span>
        <el-button
          v-if="showRefresh"
          size="small"
          :loading="loading"
          @click="emit('refresh')"
        >刷新</el-button>
      </div>
    </div>

    <div v-loading="loading" class="gt-hint-panel__body">
      <template v-if="hints.length">
        <div v-for="(hint, i) in hints" :key="hint.formula_id || i" class="gt-hint-item">
          <el-icon class="gt-hint-item__icon"><InfoFilled /></el-icon>
          <div class="gt-hint-item__main">
            <div class="gt-hint-item__text">{{ hint.hint_text }}</div>
            <div v-if="hint.addr_id" class="gt-hint-item__addr">来源：{{ hint.addr_id }}</div>
          </div>
        </div>
      </template>

      <el-empty
        v-else-if="!loading"
        :image-size="64"
        description="暂无合理性提醒"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * GtFormulaHintPanel — reasonability 提醒清单面板（Req 7.2）
 *
 * 消费 reasonability 类公式产出的 **Hint_List**（提醒项）。
 * reasonability 绝不改值——本面板为只读展示。
 *
 * 数据由父级经 useFormulaIssueHint.setHints / loadHints 提供后以 props 注入（展示型组件）。
 *
 * Requirements: 7.2
 */
import { computed, ref } from 'vue'
import { MagicStick, InfoFilled } from '@element-plus/icons-vue'
import { fmtDateTime } from '@/utils/formatters'
import type { FormulaHintItem } from './useFormulaIssueHint'

const props = withDefaults(
  defineProps<{
    /** reasonability 提醒项（Hint_List） */
    hints?: FormulaHintItem[]
    /** 最近计算时间（后端 naive UTC 或 ISO 串）；空 → "尚未计算" */
    lastComputedAt?: string | null
    loading?: boolean
    /** 是否显示刷新按钮 */
    showRefresh?: boolean
    /** 智能公式建议（系统预设中匹配当前底稿但尚未配置的公式） */
    suggestions?: Array<{ target_cell: string; expression: string; formula_type: string; [k: string]: any }>
  }>(),
  {
    hints: () => [],
    lastComputedAt: null,
    loading: false,
    showRefresh: true,
    suggestions: () => [],
  },
)

const emit = defineEmits<{
  refresh: []
  /** 用户点击"应用"某条建议公式 */
  'apply-suggestion': [suggestion: { target_cell: string; expression: string; formula_type: string }]
}>()

const hints = computed(() => props.hints ?? [])
const suggestions = computed(() => props.suggestions ?? [])
const showSuggestions = ref(true)

function suggestTypeLabel(t: string): string {
  const m: Record<string, string> = { auto_calc: '自动运算', logic_check: '逻辑审核', reasonability: '合理性' }
  return m[t] || t
}
function suggestTypeTag(t: string): 'primary' | 'warning' | 'success' {
  if (t === 'logic_check') return 'warning'
  if (t === 'reasonability') return 'success'
  return 'primary'
}

const computedAtText = computed(() => {
  if (!props.lastComputedAt) return ''
  return fmtDateTime(normalizeTimestamp(props.lastComputedAt))
})

function normalizeTimestamp(v: string): string {
  const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(v)
  return hasTz ? v : `${v}Z`
}
</script>

<style scoped>
.gt-hint-panel {
  font-size: 13px;
}
.gt-hint-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.gt-hint-panel__title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  color: var(--gt-color-text-primary, #303133);
}
.gt-hint-panel__title-icon {
  color: #e6a23c;
}
.gt-hint-panel__count {
  margin-left: 4px;
}
.gt-hint-panel__actions {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}
.gt-hint-panel__computed {
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
}
.gt-hint-panel__computed--pending {
  color: #e6a23c;
  font-style: italic;
}
.gt-hint-panel__body {
  min-height: 48px;
}
.gt-hint-item {
  display: flex;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  background: #fdf6ec;
  border-left: 3px solid #e6a23c;
  margin-bottom: 8px;
}
.gt-hint-item__icon {
  color: #e6a23c;
  margin-top: 2px;
}
.gt-hint-item__main {
  flex: 1;
  min-width: 0;
}
.gt-hint-item__text {
  color: #303133;
}
.gt-hint-item__addr {
  margin-top: 3px;
  font-size: 12px;
  color: #909399;
}
/* 公式建议区 */
.gt-hint-suggest {
  margin-bottom: 12px;
  border: 1px solid #d9ecff;
  border-radius: 6px;
  background: #ecf5ff;
  padding: 8px 10px;
}
.gt-hint-suggest__header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--gt-color-primary, #409eff);
}
.gt-hint-suggest__body {
  margin-top: 8px;
}
.gt-hint-suggest__desc {
  font-size: 12px;
  color: var(--gt-color-text-secondary);
  margin-bottom: 6px;
}
.gt-hint-suggest__item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  margin-bottom: 4px;
  background: #fff;
  border-radius: 4px;
  border: 1px solid #e4e7ed;
}
.gt-hint-suggest__item-main {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  overflow: hidden;
}
.gt-hint-suggest__cell {
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  color: var(--gt-color-text-primary);
}
.gt-hint-suggest__expr {
  font-size: 11px;
  color: var(--gt-color-text-regular);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: 'Consolas', monospace;
}
</style>
