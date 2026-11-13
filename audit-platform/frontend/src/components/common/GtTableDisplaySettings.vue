<template>
  <el-popover placement="bottom-end" :width="300" trigger="click" :disabled="disabled || invalidPageKey">
    <template #reference>
      <el-button
        size="small"
        :disabled="disabled || invalidPageKey"
        data-testid="table-display-settings"
        :title="invalidPageKey ? '当前表缺少稳定身份，不能保存固定列' : '设置固定列'"
      >
        固定列
      </el-button>
    </template>
    <div class="gt-fixed-settings">
      <div class="gt-fixed-settings__title">固定在表格左侧</div>
      <el-checkbox-group :model-value="selection" @change="saveSelection">
        <el-checkbox
          v-for="column in normalizedColumns"
          :key="column.key"
          :value="column.key"
          :disabled="mandatoryKeySet.has(column.key)"
          :data-mandatory="String(mandatoryKeySet.has(column.key))"
        >
          {{ column.label }}
          <span v-if="mandatoryKeySet.has(column.key)" class="gt-fixed-settings__required">（必选）</span>
        </el-checkbox>
      </el-checkbox-group>
      <el-alert
        v-if="staleKeys.length"
        type="warning"
        :closable="false"
        show-icon
        title="部分已固定列在当前表中不存在，已忽略"
      />
    </div>
  </el-popover>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { usePreferredFixedColumns } from '@/composables/usePreferredFixedColumns'

export interface TableDisplayColumn {
  key: string
  label: string
}

const props = withDefaults(defineProps<{
  pageKey: string
  columns: TableDisplayColumn[]
  mandatoryKeys?: string[]
  disabled?: boolean
}>(), { mandatoryKeys: () => [], disabled: false })

const emit = defineEmits<{
  change: [payload: { pageKey: string; savedKeys: string[]; effectiveKeys: string[]; staleKeys: string[] }]
}>()

const normalizedColumns = computed(() => {
  const seen = new Set<string>()
  return props.columns.filter((column) => {
    if (!column.key || column.key.length > 100 || seen.has(column.key)) return false
    seen.add(column.key)
    return true
  })
})
const invalidPageKey = computed(() => !props.pageKey || props.pageKey.length > 100)
const preferred = usePreferredFixedColumns({
  pageKey: () => props.pageKey,
  allowedColumns: () => normalizedColumns.value.map((column) => column.key),
  mandatoryColumns: () => props.mandatoryKeys,
})
const selection = computed(() => preferred.effectiveKeys.value)
const mandatoryKeySet = computed(() => new Set(preferred.mandatoryKeys.value))
const staleKeys = computed(() => preferred.staleKeys.value)

function saveSelection(value: unknown): void {
  const keys = Array.isArray(value) ? value.map(String) : []
  if (!preferred.save(keys)) return
  emit('change', {
    pageKey: props.pageKey,
    savedKeys: preferred.savedKeys.value,
    effectiveKeys: preferred.effectiveKeys.value,
    staleKeys: preferred.staleKeys.value,
  })
}
</script>

<style scoped>
.gt-fixed-settings { display: flex; flex-direction: column; gap: 10px; }
.gt-fixed-settings__title { color: var(--gt-color-text-primary, #303133); font-weight: 600; }
.gt-fixed-settings :deep(.el-checkbox-group) { display: flex; flex-direction: column; max-height: 320px; overflow: auto; }
.gt-fixed-settings__required { color: var(--gt-color-text-tertiary, #909399); font-size: var(--gt-font-size-xs, 11px); }
</style>
