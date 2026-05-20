<script setup lang="ts">
/**
 * ViewSwitcher.vue — 角色视图切换下拉组件
 *
 * 在 WorkpaperList 筛选栏左侧显示 el-select，提供 4 种角色视图预设。
 *
 * Requirements: 1.1, 1.4
 */
import type { ViewPresetId } from '@/composables/viewPresetConfig'
import { VIEW_PRESET_CONFIG, VALID_PRESET_IDS } from '@/composables/viewPresetConfig'

interface Props {
  modelValue: ViewPresetId
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: ViewPresetId]
}>()

/** 下拉选项列表 */
const options = VALID_PRESET_IDS.map(id => ({
  value: id,
  label: `${VIEW_PRESET_CONFIG[id].icon} ${VIEW_PRESET_CONFIG[id].label}`,
}))

function handleChange(value: ViewPresetId) {
  emit('update:modelValue', value)
}
</script>

<template>
  <el-select
    :model-value="props.modelValue"
    :disabled="props.disabled"
    class="gt-view-switcher"
    size="default"
    placeholder="选择视图"
    @change="handleChange"
  >
    <el-option
      v-for="opt in options"
      :key="opt.value"
      :value="opt.value"
      :label="opt.label"
    />
  </el-select>
</template>

<style scoped>
.gt-view-switcher {
  width: 160px;
}
</style>
