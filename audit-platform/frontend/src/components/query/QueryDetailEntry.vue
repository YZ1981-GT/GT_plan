<!--
  QueryDetailEntry.vue — 业务页行级「按此查询明细」入口（advanced-query-linkage-closure 任务 47，design §4.3；ADR-AQL-20）

  四个宿主页（试算表右键菜单、报表穿透弹窗、附注右键菜单、底稿编辑器工具栏）只挂这一个组件并传入
  `kind` / `target` / 自己取数用的 `year`；上下文 → 查询参数的映射全在 `queryEntryContext.buildQueryEntry`。
  页面显式 import（不依赖由构建工具重写、且常被并发会话改动的 `components.d.ts`）。

  `ctx` 变体渲染成 `div.gt-ucell-ctx-item`（该样式在 `CellContextMenu.vue` 的非 scoped `<style>` 里，
  插槽内的子组件同样生效）；`button` 变体用 el-button，放工具栏。
-->
<template>
  <div
    v-if="variant === 'ctx'"
    class="gt-ucell-ctx-item"
    :class="{ 'is-disabled': disabledReason }"
    :title="disabledReason || label"
    :aria-disabled="disabledReason ? 'true' : undefined"
    data-testid="query-detail-entry"
    @click="open"
  >
    <span class="gt-ucell-ctx-icon">🔍</span> {{ label }}
  </div>
  <el-button
    v-else
    size="small"
    :disabled="!!disabledReason"
    :title="disabledReason || label"
    :aria-label="label"
    data-testid="query-detail-entry"
    @click="open"
  >
    🔍 {{ label }}
  </el-button>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import {
  buildQueryEntry, isQueryEntryRejected,
  type QueryEntryKind, type QueryEntryTarget,
} from './queryEntryContext'
import { eventBus } from '@/utils/eventBus'

const props = withDefaults(defineProps<{
  kind: QueryEntryKind
  target: QueryEntryTarget | null | undefined
  variant?: 'ctx' | 'button'
  /** 宿主页取数用的年度（ADR-AQL-20）：明细必须与所点的行同一年度；取不到传 null，由弹窗按项目审计年度解析 */
  year?: number | null
  /** 覆盖按钮文案（缺省「按此查询明细」） */
  label?: string
}>(), { variant: 'ctx', year: null, label: '按此查询明细' })

const emit = defineEmits<{ opened: [] }>()

const route = useRoute()
const label = computed(() => props.label)
/** 每次渲染都重算：目标行、年度变了（附注编辑器页内切年）结果随之变 */
const result = computed(() => buildQueryEntry(props.kind, props.target, route, props.year))
const disabledReason = computed(() => (isQueryEntryRejected(result.value) ? result.value.disabledReason : ''))

function open() {
  const built = result.value
  if (isQueryEntryRejected(built)) return // 置灰时不发事件（原因已在 title 上）
  eventBus.emit('open-custom-query', { entry: built })
  emit('opened') // 宿主用它关右键菜单
}
</script>

<style scoped>
.gt-ucell-ctx-item.is-disabled {
  color: var(--el-text-color-disabled);
  cursor: not-allowed;
}
</style>
