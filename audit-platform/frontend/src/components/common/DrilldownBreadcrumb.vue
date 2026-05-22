<template>
  <div v-if="stack.length > 0" class="gt-breadcrumb">
    <!-- 折叠模式：超过 5 层时折叠中间层 -->
    <template v-if="stack.length <= 5">
      <span
        v-for="(item, idx) in stack"
        :key="idx"
        class="gt-breadcrumb-item"
        :class="{ 'gt-breadcrumb-item--current': idx === stack.length - 1 }"
        @click="idx < stack.length - 1 && $emit('jump', idx)"
      >
        <span v-if="item.direction" class="gt-breadcrumb-direction" :class="`gt-breadcrumb-direction--${item.direction}`">{{ item.direction === 'down' ? '↓' : '↑' }}</span>
        {{ labelFor(item) }}
        <span v-if="idx < stack.length - 1" class="gt-breadcrumb-sep">&gt;</span>
      </span>
    </template>
    <template v-else>
      <!-- 首项 -->
      <span class="gt-breadcrumb-item" @click="$emit('jump', 0)">
        <span v-if="stack[0].direction" class="gt-breadcrumb-direction" :class="`gt-breadcrumb-direction--${stack[0].direction}`">{{ stack[0].direction === 'down' ? '↓' : '↑' }}</span>
        {{ labelFor(stack[0]) }}
        <span class="gt-breadcrumb-sep">&gt;</span>
      </span>
      <!-- 折叠省略号 -->
      <el-popover trigger="hover" :width="200" placement="bottom">
        <template #reference>
          <span class="gt-breadcrumb-item gt-breadcrumb-ellipsis">...</span>
        </template>
        <div class="gt-breadcrumb-popover">
          <div
            v-for="(item, idx) in stack.slice(1, stack.length - 2)"
            :key="idx + 1"
            class="gt-breadcrumb-popover-item"
            @click="$emit('jump', idx + 1)"
          >
            <span v-if="item.direction" class="gt-breadcrumb-direction" :class="`gt-breadcrumb-direction--${item.direction}`">{{ item.direction === 'down' ? '↓' : '↑' }}</span>
            {{ labelFor(item) }}
          </div>
        </div>
      </el-popover>
      <span class="gt-breadcrumb-sep">&gt;</span>
      <!-- 倒数第二项 -->
      <span class="gt-breadcrumb-item" @click="$emit('jump', stack.length - 2)">
        <span v-if="stack[stack.length - 2].direction" class="gt-breadcrumb-direction" :class="`gt-breadcrumb-direction--${stack[stack.length - 2].direction}`">{{ stack[stack.length - 2].direction === 'down' ? '↓' : '↑' }}</span>
        {{ labelFor(stack[stack.length - 2]) }}
        <span class="gt-breadcrumb-sep">&gt;</span>
      </span>
      <!-- 当前项 -->
      <span class="gt-breadcrumb-item gt-breadcrumb-item--current">
        <span v-if="stack[stack.length - 1].direction" class="gt-breadcrumb-direction" :class="`gt-breadcrumb-direction--${stack[stack.length - 1].direction}`">{{ stack[stack.length - 1].direction === 'down' ? '↓' : '↑' }}</span>
        {{ labelFor(stack[stack.length - 1]) }}
      </span>
    </template>
  </div>
</template>

<script setup lang="ts">
import type { NavigationEntry } from '@/composables/useNavigationStack'

defineProps<{ stack: NavigationEntry[] }>()
defineEmits<{ jump: [index: number] }>()

/** 路由路径 → 中文标签映射 */
const ROUTE_LABEL_MAP: Record<string, string> = {
  '/trial-balance': '试算表',
  '/drilldown': '穿透查询',
  '/ledger': '明细账',
  '/aux-summary': '辅助余额',
  '/workpapers': '底稿列表',
  '/adjustments': '调整分录',
  '/reports': '报表',
  '/disclosure-notes': '附注',
  '/materiality': '重要性',
  '/misstatements': '错报',
}

function labelFor(entry: NavigationEntry): string {
  if (entry.label) return entry.label
  // 从 source_view 路径推断标签
  const path = entry.source_view || ''
  for (const [pattern, label] of Object.entries(ROUTE_LABEL_MAP)) {
    if (path.includes(pattern)) return label
  }
  // fallback: 取路径最后一段
  const segments = path.split('/').filter(Boolean)
  return segments[segments.length - 1] || '未知'
}
</script>

<style scoped>
.gt-breadcrumb {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 16px;
  background: #f8f9fa;
  border-bottom: 1px solid #e4e7ed;
  font-size: 13px;
  min-height: 32px;
}

.gt-breadcrumb-item {
  color: #4b2d77;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 3px;
  transition: background 0.15s;
}

.gt-breadcrumb-item:hover:not(.gt-breadcrumb-item--current) {
  background: rgba(75, 45, 119, 0.08);
}

.gt-breadcrumb-item--current {
  font-weight: 600;
  color: #333;
  cursor: default;
}

.gt-breadcrumb-sep {
  color: #ccc;
  margin: 0 2px;
  font-weight: normal;
}

.gt-breadcrumb-ellipsis {
  letter-spacing: 2px;
}

.gt-breadcrumb-popover-item {
  padding: 4px 8px;
  cursor: pointer;
  border-radius: 3px;
}

.gt-breadcrumb-popover-item:hover {
  background: #f0edf5;
}

.gt-breadcrumb-direction {
  font-size: 11px;
  margin-right: 2px;
  font-weight: 600;
}

.gt-breadcrumb-direction--down {
  color: #e6a23c;
}

.gt-breadcrumb-direction--up {
  color: #409eff;
}
</style>
