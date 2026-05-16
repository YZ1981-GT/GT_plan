<!--
  GtInfoBar — 信息栏组件 [R5.5]
  在 GtPageHeader 内显示单位/年度/模板选择器 + 徽章信息。
  通过 props 控制显示哪些选择器，通过 events 通知父组件变更。

  用法：
    <GtInfoBar
      :show-unit="true"
      :show-year="true"
      :show-template="true"
      :badges="[{ label: '科目', value: '128 个' }]"
      @unit-change="onProjectChange"
      @year-change="onYearChange"
      @template-change="onTemplateChange"
    />
-->
<template>
  <div class="gt-info-bar">
    <!-- 单位选择器 -->
    <template v-if="showUnit">
      <div class="gt-info-bar__item">
        <span class="gt-info-bar__label">单位</span>
        <el-select
          :model-value="unitValue"
          size="small"
          class="gt-info-bar__select gt-info-bar__select--unit"
          filterable
          @change="$emit('unit-change', $event)"
        >
          <el-option
            v-for="p in unitOptions"
            :key="p.id"
            :label="p.name"
            :value="p.id"
          />
        </el-select>
      </div>
      <div class="gt-info-bar__sep" />
    </template>

    <!-- 年度选择器 -->
    <template v-if="showYear">
      <div class="gt-info-bar__item">
        <span class="gt-info-bar__label">年度</span>
        <el-select
          :model-value="yearValue"
          size="small"
          class="gt-info-bar__select gt-info-bar__select--year"
          @change="$emit('year-change', $event)"
        >
          <el-option
            v-for="y in yearOptionsList"
            :key="y"
            :label="y + '年'"
            :value="y"
          />
        </el-select>
      </div>
      <div class="gt-info-bar__sep" />
    </template>

    <!-- 模板选择器 -->
    <template v-if="showTemplate">
      <div class="gt-info-bar__item">
        <span class="gt-info-bar__label">模板</span>
        <el-select
          :model-value="templateValue"
          size="small"
          class="gt-info-bar__select gt-info-bar__select--tpl"
          @change="$emit('template-change', $event)"
        >
          <el-option
            v-for="opt in templateOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </div>
      <div class="gt-info-bar__sep" />
    </template>

    <!-- 口径选择器 -->
    <template v-if="showScope">
      <div class="gt-info-bar__item">
        <span class="gt-info-bar__label">口径</span>
        <span class="gt-info-bar__badge">{{ scopeLabel }}</span>
      </div>
      <div class="gt-info-bar__sep" />
    </template>

    <!-- 徽章列表 -->
    <template v-for="(badge, idx) in badges" :key="idx">
      <div class="gt-info-bar__item">
        <span v-if="badge.label" class="gt-info-bar__label">{{ badge.label }}</span>
        <span class="gt-info-bar__badge">{{ badge.value }}</span>
      </div>
      <div v-if="idx < badges.length - 1" class="gt-info-bar__sep" />
    </template>

    <!-- 额外插槽（模式切换等自定义内容） -->
    <slot />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useProjectStore } from '@/stores/project'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { useDictStore } from '@/stores/dict'

export interface InfoBadge {
  label?: string
  value: string
  type?: 'default' | 'success' | 'warning' | 'danger'
}

export interface TemplateOption {
  label: string
  value: string
}

const props = withDefaults(defineProps<{
  /** 显示单位选择器 */
  showUnit?: boolean
  /** 显示年度选择器 */
  showYear?: boolean
  /** 显示模板选择器 */
  showTemplate?: boolean
  /** 显示口径标签 */
  showScope?: boolean
  /** 口径文本 */
  scopeLabel?: string
  /** 当前选中的单位 ID */
  unitValue?: string
  /** 当前选中的年度 */
  yearValue?: number
  /** 当前选中的模板 */
  templateValue?: string
  /** 模板选项列表（覆盖 dictStore 默认值） */
  templateOptions?: TemplateOption[]
  /** 单位选项列表（覆盖 projectStore 默认值） */
  unitOptions?: Array<{ id: string; name: string }>
  /** 年度选项列表（覆盖 projectStore 默认值） */
  yearOptionsList?: number[]
  /** 徽章列表 */
  badges?: InfoBadge[]
}>(), {
  showUnit: false,
  showYear: false,
  showTemplate: false,
  showScope: false,
  scopeLabel: '',
  unitValue: '',
  yearValue: undefined,
  templateValue: '',
  templateOptions: undefined,
  unitOptions: undefined,
  yearOptionsList: undefined,
  badges: () => [],
})

defineEmits<{
  (e: 'unit-change', value: string): void
  (e: 'year-change', value: number): void
  (e: 'template-change', value: string): void
  (e: 'scope-change', value: string): void
}>()

const projectStore = useProjectStore()
const displayPrefs = useDisplayPrefsStore()
const dictStore = useDictStore()

// 如果没有传入 unitOptions，使用 projectStore 的
const unitOptions = computed(() => props.unitOptions ?? projectStore.projectOptions)
const yearOptionsList = computed(() => props.yearOptionsList ?? projectStore.yearOptions)

/** 模板选项：优先 props 传入 → 其次 dictStore（applicable_standard 字典）→ 最后硬编码默认值 */
const templateOptions = computed((): TemplateOption[] => {
  if (props.templateOptions) return props.templateOptions
  const dictOpts = dictStore.options('applicable_standard')
  if (dictOpts.length > 0) {
    return dictOpts.map(e => ({ label: e.label, value: e.value }))
  }
  // 硬编码兜底（dictStore 未加载时）
  return [
    { label: '国企版', value: 'soe' },
    { label: '上市版', value: 'listed' },
  ]
})
</script>

<style scoped>
.gt-info-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.gt-info-bar__item {
  display: flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.gt-info-bar__label {
  font-size: var(--gt-font-size-xs);
  color: rgba(255, 255, 255, 0.55);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.gt-info-bar__badge {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: var(--gt-font-size-xs);
  font-weight: 600;
  background: rgba(255, 255, 255, 0.15);
  color: var(--gt-color-text-inverse);
}

.gt-info-bar__sep {
  width: 1px;
  height: 16px;
  background: rgba(255, 255, 255, 0.18);
  flex-shrink: 0;
}

/* 下拉框白色风格 */
.gt-info-bar__select--unit { width: 200px; }
.gt-info-bar__select--year { width: 85px; }
.gt-info-bar__select--tpl { width: 100px; }

.gt-info-bar__select :deep(.el-input__wrapper) {
  background: rgba(255, 255, 255, 0.12) !important;
  border: 1px solid rgba(255, 255, 255, 0.2) !important;
  box-shadow: none !important;
  border-radius: 12px !important;
  padding: 0 8px !important;
  height: 24px !important;
}

.gt-info-bar__select :deep(.el-input__inner) {
  color: var(--gt-color-text-inverse) !important;
  font-size: var(--gt-font-size-xs) !important;
  font-weight: 600 !important;
}

.gt-info-bar__select :deep(.el-select__caret) {
  color: rgba(255, 255, 255, 0.5) !important;
}
</style>
