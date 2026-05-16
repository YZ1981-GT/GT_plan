<!--
  ShortcutHelpDialog — 快捷键帮助面板 [R7-S2-12]
  F1 或 ? 触发，按 scope 分组展示所有注册快捷键。

  用法：由 ThreeColumnLayout 监听 shortcut:help 事件打开。
-->
<template>
  <el-dialog v-model="visible" title="⌨️ 键盘快捷键" width="480" append-to-body>
    <el-input
      v-model="search"
      placeholder="搜索快捷键..."
      clearable
      style="margin-bottom: 16px"
      prefix-icon="Search"
    />
    <div v-for="(group, scope) in filteredGroups" :key="scope" class="gt-shortcut-group">
      <h4 class="gt-shortcut-scope">{{ scope }}</h4>
      <div v-for="s in group" :key="s.key" class="gt-shortcut-row">
        <kbd class="gt-shortcut-key">{{ s.key }}</kbd>
        <span class="gt-shortcut-desc">{{ s.description }}</span>
      </div>
    </div>
    <div v-if="Object.keys(filteredGroups).length === 0" class="gt-shortcut-empty">
      无匹配的快捷键
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { shortcutManager } from '@/utils/shortcuts'

const visible = defineModel<boolean>({ default: false })
const search = ref('')

const allShortcuts = computed(() => shortcutManager.getAll())

const filteredGroups = computed(() => {
  const q = search.value.toLowerCase()
  const groups: Record<string, typeof allShortcuts.value> = {}
  for (const s of allShortcuts.value) {
    if (q && !s.key.toLowerCase().includes(q) && !s.description.toLowerCase().includes(q)) continue
    const scope = s.scope || '全局'
    if (!groups[scope]) groups[scope] = []
    groups[scope].push(s)
  }
  return groups
})
</script>

<style scoped>
.gt-shortcut-group { margin-bottom: 16px; }
.gt-shortcut-scope {
  margin: 0 0 8px;
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  color: var(--gt-color-primary);
}
.gt-shortcut-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 4px 0;
}
.gt-shortcut-key {
  display: inline-block;
  min-width: 80px;
  padding: 2px 8px;
  background: var(--gt-color-bg);
  border: 1px solid var(--gt-color-border);
  border-radius: var(--gt-radius-sm);
  font-family: monospace;
  font-size: var(--gt-font-size-xs);
  text-align: center;
}
.gt-shortcut-desc {
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-secondary);
}
.gt-shortcut-empty {
  text-align: center;
  padding: 24px;
  color: var(--gt-color-text-tertiary);
}
</style>
