<template>
  <div class="gt-virtual-table">
    <!-- 表头 -->
    <div class="gt-vt-header">
      <div
        v-for="col in columns"
        :key="col.key"
        class="gt-vt-cell gt-vt-th"
        :style="{ width: col.width || 'auto', flex: col.width ? 'none' : '1', textAlign: col.align || 'left' }"
      >
        {{ col.label }}
      </div>
    </div>

    <!-- 虚拟滚动区域 -->
    <div
      ref="scrollContainer"
      class="gt-vt-body"
      :style="{ height: height + 'px' }"
      @scroll="onScroll"
    >
      <!-- 撑开总高度的占位 -->
      <div :style="{ height: totalHeight + 'px', position: 'relative' }">
        <!-- 只渲染可见行 -->
        <div
          v-for="(item, idx) in visibleItems"
          :key="item._key || idx"
          class="gt-vt-row"
          :class="{ 'gt-vt-row--active': activeIndex === item._index, 'gt-vt-row--stripe': item._index % 2 === 1 }"
          :style="{ position: 'absolute', top: item._top + 'px', width: '100%' }"
          @click="$emit('row-click', item, item._index)"
        >
          <div
            v-for="col in columns"
            :key="col.key"
            class="gt-vt-cell"
            :style="{ width: col.width || 'auto', flex: col.width ? 'none' : '1', textAlign: col.align || 'left' }"
          >
            <slot :name="col.key" :row="item" :value="item[col.key]">
              {{ formatCell(item[col.key], col) }}
            </slot>
          </div>
        </div>
      </div>
    </div>

    <!-- 底部信息栏 -->
    <div class="gt-vt-footer">
      <span>共 {{ data.length.toLocaleString() }} 条</span>
      <span v-if="data.length > 1000" class="gt-vt-hint">虚拟滚动已启用</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { fmtAmount } from '@/utils/formatters'

export interface VTColumn {
  key: string
  label: string
  width?: string
  align?: 'left' | 'center' | 'right'
  formatter?: (val: any) => string
}

const props = withDefaults(defineProps<{
  data: any[]
  columns: VTColumn[]
  rowHeight?: number
  height?: number
  bufferSize?: number
  activeIndex?: number | null
}>(), {
  rowHeight: 36,
  height: 500,
  bufferSize: 10,
  activeIndex: null,
})

defineEmits<{ (e: 'row-click', row: any, index: number): void }>()

const scrollContainer = ref<HTMLElement | null>(null)
const scrollTop = ref(0)

const totalHeight = computed(() => props.data.length * props.rowHeight)

const visibleItems = computed(() => {
  const startIdx = Math.max(0, Math.floor(scrollTop.value / props.rowHeight) - props.bufferSize)
  const visibleCount = Math.ceil(props.height / props.rowHeight)
  const endIdx = Math.min(props.data.length, startIdx + visibleCount + props.bufferSize * 2)

  return props.data.slice(startIdx, endIdx).map((item, i) => ({
    ...item,
    _index: startIdx + i,
    _top: (startIdx + i) * props.rowHeight,
    _key: item.id || item.voucher_no || `row-${startIdx + i}`,
  }))
})

function onScroll(e: Event) {
  scrollTop.value = (e.target as HTMLElement).scrollTop
}

function formatCell(val: any, col: VTColumn): string {
  if (val == null) return '-'
  if (col.formatter) return col.formatter(val)
  if (typeof val === 'number') {
    if (val === 0) return '-'
    return fmtAmount(val)
  }
  return String(val)
}

// 数据变化时重置滚动位置
watch(() => props.data.length, () => {
  if (scrollContainer.value) scrollContainer.value.scrollTop = 0
  scrollTop.value = 0
})
</script>

<style scoped>
.gt-virtual-table {
  border: 1px solid var(--gt-color-border-light);
  border-radius: var(--gt-radius-md);
  overflow: hidden;
  background: var(--gt-color-bg-white);
}

.gt-vt-header {
  display: flex;
  background: var(--gt-color-primary-bg);
  border-bottom: 2px solid var(--gt-color-primary-lighter, #c4a8e8);
  position: sticky;
  top: 0;
  z-index: 2;
}

.gt-vt-th {
  font-weight: 600;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-primary-dark);
  padding: 8px 12px;
}

.gt-vt-body {
  overflow-y: auto;
  overflow-x: hidden;
}

.gt-vt-row {
  display: flex;
  border-bottom: 1px solid var(--gt-color-border-light);
  cursor: pointer;
  transition: background var(--gt-transition-fast);
  height: v-bind("props.rowHeight + 'px'");
  align-items: center;
}

.gt-vt-row:hover { background: var(--gt-color-primary-bg); }
.gt-vt-row--active { background: var(--gt-color-primary-bg) !important; }
.gt-vt-row--stripe { background: var(--gt-color-primary-bg); }

.gt-vt-cell {
  padding: 0 12px;
  font-size: var(--gt-font-size-sm);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gt-vt-footer {
  display: flex;
  justify-content: space-between;
  padding: 6px 12px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-secondary);
  border-top: 1px solid var(--gt-color-border-light);
  background: var(--gt-color-bg);
}

.gt-vt-hint { color: var(--gt-color-teal); }
</style>
