<template>
  <Teleport to="body">
    <Transition name="gt-ucell-ctx-fade">
      <div v-if="visible" class="gt-ucell-context-menu"
        :style="{ left: x + 'px', top: y + 'px' }" @contextmenu.prevent>
        <div class="gt-ucell-ctx-header">
          <span>{{ itemName }}</span>
          <span v-if="value != null" style="color:#4b2d77;font-weight:600">{{ formattedValue }}</span>
        </div>
        <div class="gt-ucell-ctx-divider" />
        <!-- 通用项 -->
        <div class="gt-ucell-ctx-item" @click="$emit('copy')"><span class="gt-ucell-ctx-icon">📋</span> 复制值</div>
        <div class="gt-ucell-ctx-item" @click="$emit('formula')"><span class="gt-ucell-ctx-icon">ƒx</span> 查看公式</div>
        <!-- 自定义插槽：模块特有的菜单项 -->
        <slot />
        <!-- 多选项 -->
        <template v-if="multiCount > 1">
          <div class="gt-ucell-ctx-divider" />
          <div class="gt-ucell-ctx-item" @click="$emit('sum')">
            <span class="gt-ucell-ctx-icon">Σ</span> 求和 <b style="color:#4b2d77;margin-left:4px">{{ multiCount }} 格</b>
          </div>
          <div class="gt-ucell-ctx-item" @click="$emit('compare')">
            <span class="gt-ucell-ctx-icon">⇄</span> 对比差异
          </div>
        </template>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  visible: boolean
  x: number
  y: number
  itemName: string
  value?: any
  multiCount: number
}>()

defineEmits<{
  (e: 'copy'): void
  (e: 'formula'): void
  (e: 'sum'): void
  (e: 'compare'): void
}>()

const formattedValue = computed(() => {
  const v = props.value
  if (v == null) return ''
  const n = Number(v)
  if (isNaN(n)) return String(v)
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
})
</script>

<style>
/* 通用单元格选中高亮 */
.gt-ucell--selected {
  background: linear-gradient(135deg, rgba(75,45,119,0.05), rgba(124,92,170,0.08)) !important;
  box-shadow: inset 0 0 0 1.5px rgba(75,45,119,0.35), 0 0 8px rgba(75,45,119,0.1);
  border-radius: 3px;
  animation: gt-ucell-pulse 1.5s ease-in-out infinite alternate;
}
@keyframes gt-ucell-pulse {
  0% { box-shadow: inset 0 0 0 1.5px rgba(75,45,119,0.35), 0 0 6px rgba(75,45,119,0.08); }
  100% { box-shadow: inset 0 0 0 1.5px rgba(75,45,119,0.5), 0 0 12px rgba(75,45,119,0.15); }
}

/* 右键菜单 */
.gt-ucell-context-menu {
  position: fixed; z-index: 10001; background: #fff;
  border-radius: 8px; box-shadow: 0 6px 24px rgba(0,0,0,0.15); padding: 6px 0; min-width: 200px;
  border: 1px solid #e8e4f0;
}
.gt-ucell-ctx-header {
  padding: 6px 14px; font-size: 11px; color: #999;
  display: flex; justify-content: space-between; gap: 8px;
}
.gt-ucell-ctx-divider { height: 1px; background: #f0edf5; margin: 2px 0; }
.gt-ucell-ctx-item {
  padding: 8px 14px; font-size: 13px; cursor: pointer; color: #333;
  display: flex; align-items: center; gap: 6px; transition: background 0.1s;
}
.gt-ucell-ctx-item:hover { background: #f0edf5; color: #4b2d77; }
.gt-ucell-ctx-icon { width: 18px; text-align: center; font-size: 13px; }
.gt-ucell-ctx-fade-enter-active { transition: opacity 0.1s, transform 0.1s; }
.gt-ucell-ctx-fade-leave-active { transition: opacity 0.08s; }
.gt-ucell-ctx-fade-enter-from { opacity: 0; transform: scale(0.95); }
.gt-ucell-ctx-fade-leave-to { opacity: 0; }
</style>
