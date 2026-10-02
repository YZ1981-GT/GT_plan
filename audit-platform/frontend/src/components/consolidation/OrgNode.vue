<template>
  <div class="org-node-wrap">
    <!-- 当前节点卡片：键与选中态都用 node_key（同一企业可有合并户与母公司户两个节点） -->
    <div
      class="org-card"
      :class="[`org-card--${node.kind || 'data'}`, {
        'org-card--root': depth === 0,
        'org-card--selected': !!selectedKey && selectedKey === node.node_key,
        'org-card--warn': hasWarningFlag(node),
      }]"
      :data-node-key="node.node_key"
      :data-role="node.role"
      @click.stop="$emit('select', node)"
    >
      <div class="org-card-header">
        <span class="org-card-name">{{ nodeLabel(node) }}</span>
      </div>
      <div class="org-card-body">
        <el-tag v-if="roleLabel(node.role)" size="small" effect="plain" :type="node.kind === 'elim' ? 'warning' : 'info'">
          {{ roleLabel(node.role) }}
        </el-tag>
        <el-tag v-if="relationTagLabel(node)" size="small" effect="light" data-testid="org-relation-tag">
          {{ relationTagLabel(node) }}
        </el-tag>
        <el-tooltip v-for="tag in flagTags(node)" :key="tag.code" :content="tag.hint || tag.label" placement="top">
          <el-tag size="small" effect="plain" :type="tag.type">{{ tag.label }}</el-tag>
        </el-tooltip>
        <span v-if="node.company_code" class="org-card-code">{{ node.company_code }}</span>
        <!-- 双向导航：只对有项目的节点显示（差额节点、有分公司的汇总节点没有自己的项目） -->
        <el-link
          v-if="canEnterProject(node)"
          type="primary"
          class="org-card-enter"
          @click.stop="$emit('enter-project', node)"
        >进入项目</el-link>
      </div>
    </div>
    <!-- 子节点 -->
    <div v-if="node.children?.length && depth < 14" class="org-children">
      <org-node
        v-for="child in node.children"
        :key="child.node_key"
        :node="child"
        :depth="depth + 1"
        :selected-key="selectedKey"
        @select="$emit('select', $event)"
        @enter-project="$emit('enter-project', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ConsolTreeNode } from '@/services/consolidationApi'
import {
  canEnterProject,
  flagTags,
  hasWarningFlag,
  nodeLabel,
  relationTagLabel,
  roleLabel,
} from '@/components/consolidation/composables/consolTreeView'

defineOptions({ name: 'OrgNode' })
defineProps<{ node: ConsolTreeNode; depth: number; selectedKey?: string | null }>()
defineEmits<{
  (e: 'select', node: ConsolTreeNode): void
  (e: 'enter-project', node: ConsolTreeNode): void
}>()
</script>

<style scoped>
.org-node-wrap {
  display: flex; flex-direction: column; align-items: center; position: relative;
}
.org-card {
  min-width: 132px; max-width: 200px; border-radius: 8px; overflow: hidden;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08); cursor: pointer;
  transition: all 0.2s ease; border: 2px solid transparent;
}
.org-card:hover { transform: translateY(-2px); box-shadow: 0 4px 16px rgba(75,45,119,0.15); }
.org-card--selected { border-color: var(--gt-color-primary); box-shadow: 0 0 0 3px rgba(75,45,119,0.2); }
.org-card--root { min-width: 168px; }
.org-card-header { padding: 6px 10px; text-align: center; background: var(--gt-color-primary-bg); }
/* 按节点类型区分色块：汇总（合并/母公司汇总）深色、差额浅黄虚线、数据白底 */
.org-card--aggregate .org-card-header { background: linear-gradient(135deg, #4b2d77, #7c5caa); }
.org-card--aggregate .org-card-name { color: #fff; }
.org-card--elim { border-style: dashed; border-color: var(--gt-color-wheat, #d9b56b); }
.org-card--elim .org-card-header { background: #fbf4e4; }
.org-card--elim.org-card--selected { border-style: solid; border-color: var(--gt-color-primary); }
.org-card--data .org-card-header { background: var(--gt-color-primary-bg); }
.org-card--warn .org-card-header { box-shadow: inset 0 -2px 0 var(--gt-color-wheat, #d9b56b); }
.org-card-name { font-size: var(--gt-font-size-xs); font-weight: 600; line-height: 1.3; color: var(--gt-color-text-primary); }
.org-card-body {
  padding: 4px 8px; background: var(--gt-color-bg-white); display: flex; gap: 4px;
  justify-content: center; align-items: center; flex-wrap: wrap;
}
.org-card-code { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.org-card-enter { font-size: var(--gt-font-size-xs); }
.org-card-enter :deep(.el-link__inner) { font-size: var(--gt-font-size-xs); }

/*
 * 子节点容器 + 连接线（上 12px 为父节点竖线，下 12px 为各子节点竖线，中间一条横线连住首末子节点）。
 * 横线由每个子节点各画一段拼成：两侧各伸出半个 gap 补上兄弟间距，首个从中点起、末个到中点止。
 */
.org-children {
  display: flex; gap: 16px; padding-top: 24px; position: relative;
}
.org-children::before {
  content: ''; position: absolute; top: 0; left: 50%; width: 2px; height: 12px;
  background: var(--gt-color-primary-lighter); transform: translateX(-50%);
}
.org-children > .org-node-wrap::before {
  content: ''; position: absolute; top: -12px; left: 50%; width: 2px; height: 12px;
  background: var(--gt-color-primary-lighter); transform: translateX(-50%);
}
.org-children > .org-node-wrap::after {
  content: ''; position: absolute; top: -12px; left: -8px; right: -8px; height: 2px;
  background: var(--gt-color-primary-lighter);
}
.org-children > .org-node-wrap:first-child::after { left: 50%; }
.org-children > .org-node-wrap:last-child::after { right: 50%; }
.org-children > .org-node-wrap:only-child::after { display: none; }
</style>
