<!--
  合并页内容区顶部的当前节点上下文条（spec consol-autotree-linkage-closure R7.3）：
  当前节点、角色与口径（合并口径 / 本级调整与抵销 / 单体项目）；
  差额户给「📝 差额分录」（点击差额户不再自动弹出分录抽屉，R7.2）；有单体项目的数据节点给「进入该企业项目」；
  非根节点给「回到合并户」。
-->
<template>
  <div v-if="node" class="gt-cnb" :class="`gt-cnb--${node.kind}`" data-testid="consol-node-bar">
    <span class="gt-cnb-label">当前节点</span>
    <strong class="gt-cnb-name" data-testid="consol-node-bar-name">{{ nodeLabel(node) }}</strong>
    <el-tag v-if="role" size="small" effect="plain">{{ role }}</el-tag>
    <span class="gt-cnb-basis" data-testid="consol-node-bar-basis">口径：{{ basis }}</span>
    <span v-if="hint" class="gt-cnb-hint">{{ hint }}</span>
    <span class="gt-cnb-spacer" />
    <el-button v-if="node.kind === 'elim'" size="small" type="warning" plain data-testid="consol-node-bar-elim"
      @click="emit('open-elim', node)">📝 差额分录</el-button>
    <el-button v-if="node.kind === 'data' && node.project_id" size="small" data-testid="consol-node-bar-enter"
      @click="emit('enter-project', node)">进入该企业项目</el-button>
    <el-button v-if="!isRoot" size="small" link type="primary" data-testid="consol-node-bar-root"
      @click="emit('go-root')">回到合并户</el-button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ConsolTreeNode } from '@/services/consolidationApi'
import { nodeBasisLabel, nodeLabel, roleLabel } from '@/components/consolidation/composables/consolTreeView'

defineOptions({ name: 'ConsolNodeContextBar' })

const props = defineProps<{ node: ConsolTreeNode | null; isRoot: boolean }>()
const emit = defineEmits<{
  (e: 'open-elim', node: ConsolTreeNode): void
  (e: 'enter-project', node: ConsolTreeNode): void
  (e: 'go-root'): void
}>()

const role = computed(() => (props.node ? roleLabel(props.node.role, props.node.kind) : ''))
const basis = computed(() => nodeBasisLabel(props.node))
const hint = computed(() => {
  const n = props.node
  if (!n) return ''
  if (n.kind === 'elim') return '只列归属本差额户的已审批调整与抵销分录的影响'
  if (n.kind === 'data') return n.project_id ? '显示该企业单体项目的报表与附注（只读）' : '该企业本年度没有单体项目'
  return ''
})
</script>

<style scoped>
.gt-cnb {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 6px 12px; margin-bottom: 4px; border-radius: var(--gt-radius-sm, 4px);
  background: var(--gt-color-primary-bg, #f4f0fa); font-size: var(--gt-font-size-xs);
}
.gt-cnb--elim { background: var(--gt-color-wheat-light); }
.gt-cnb-label { color: var(--gt-color-text-tertiary); }
.gt-cnb-name { color: var(--gt-color-primary); }
.gt-cnb-basis { color: var(--gt-color-text-secondary); }
.gt-cnb-hint { color: var(--gt-color-text-tertiary); }
.gt-cnb-spacer { flex: 1; }
</style>
