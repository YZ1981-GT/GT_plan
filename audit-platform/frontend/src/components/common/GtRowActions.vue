<template>
  <div class="gt-row-actions" v-if="visibleActions.length > 0 || dropdownActions.length > 0">
    <!-- 外露按钮 -->
    <el-button
      v-for="action in visibleActions"
      :key="action.key"
      size="small"
      :type="action.danger ? 'danger' : 'primary'"
      link
      :disabled="action.disabled"
      @click.stop="emit('action', action.key)"
    >
      <el-icon v-if="action.icon" style="margin-right: 2px"><component :is="action.icon" /></el-icon>
      {{ action.label }}
    </el-button>

    <!-- 更多下拉 -->
    <el-dropdown
      v-if="dropdownActions.length > 0"
      trigger="click"
      @command="handleCommand"
      @click.stop
    >
      <el-button size="small" type="info" link @click.stop>
        更多
        <el-icon style="margin-left: 2px"><ArrowDown /></el-icon>
      </el-button>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item
            v-for="action in dropdownActions"
            :key="action.key"
            :command="action.key"
            :disabled="action.disabled"
          >
            <el-icon v-if="action.icon"><component :is="action.icon" /></el-icon>
            <span :class="{ 'gt-row-action-danger': action.danger }">{{ action.label }}</span>
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'

export interface RowAction {
  key: string
  label: string
  icon?: string
  priority: number
  disabled?: boolean
  danger?: boolean
  hidden?: boolean
}

const props = withDefaults(defineProps<{
  actions: RowAction[]
  maxVisible?: number
}>(), {
  maxVisible: 2,
})

const emit = defineEmits<{
  action: [key: string]
}>()

/** 过滤 hidden，按 priority 升序排列 */
const sortedActions = computed(() => {
  return props.actions
    .filter(a => !a.hidden)
    .sort((a, b) => a.priority - b.priority)
})

/** 前 maxVisible 个外露 */
const visibleActions = computed(() => {
  return sortedActions.value.slice(0, props.maxVisible)
})

/** 其余收入 dropdown */
const dropdownActions = computed(() => {
  return sortedActions.value.slice(props.maxVisible)
})

function handleCommand(key: string) {
  emit('action', key)
}
</script>

<style scoped>
.gt-row-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.gt-row-action-danger {
  color: var(--el-color-danger);
}
</style>
