<template>
  <Teleport to="body">
    <div
      v-if="visible"
      ref="menuRef"
      class="confirmation-context-menu"
      :style="{ left: x + 'px', top: y + 'px' }"
    >
      <ul class="confirmation-context-menu__list">
        <li class="confirmation-context-menu__item" @click="handleAction('copy-row')">
          复制行
        </li>
        <template v-if="!readonly">
          <li class="confirmation-context-menu__item" @click="handleAction('insert-above')">
            上方插入行
          </li>
          <li class="confirmation-context-menu__item" @click="handleAction('insert-below')">
            下方插入行
          </li>
          <li class="confirmation-context-menu__item confirmation-context-menu__item--danger" @click="handleAction('delete-row')">
            删除行
          </li>
        </template>
        <li class="confirmation-context-menu__item" @click="handleAction('copy-index')">
          复制索引号
        </li>
      </ul>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue'

defineProps<{
  visible: boolean
  x: number
  y: number
  readonly: boolean
}>()

const emit = defineEmits<{
  (e: 'action', type: string): void
  (e: 'update:visible', value: boolean): void
}>()

const menuRef = ref<HTMLDivElement>()

function handleAction(type: string) {
  emit('action', type)
  emit('update:visible', false)
}

function handleClickOutside(event: MouseEvent) {
  if (menuRef.value && !menuRef.value.contains(event.target as Node)) {
    emit('update:visible', false)
  }
}

watch(
  () => menuRef.value,
  () => {
    // Use nextTick-style delayed binding to avoid the triggering click
    setTimeout(() => {
      document.addEventListener('click', handleClickOutside)
    }, 0)
  },
)

onBeforeUnmount(() => {
  document.removeEventListener('click', handleClickOutside)
})
</script>

<style scoped>
.confirmation-context-menu {
  position: fixed;
  z-index: 9999;
  min-width: 140px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.12);
  padding: 4px 0;
}

.confirmation-context-menu__list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.confirmation-context-menu__item {
  padding: 8px 16px;
  font-size: 13px;
  cursor: pointer;
  color: var(--el-text-color-regular);
  transition: background-color 0.15s;
}

.confirmation-context-menu__item:hover {
  background-color: var(--el-fill-color-light);
}

.confirmation-context-menu__item--danger {
  color: var(--el-color-danger);
}

.confirmation-context-menu__item--danger:hover {
  background-color: var(--el-color-danger-light-9);
}
</style>
