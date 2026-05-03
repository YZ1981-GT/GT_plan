<template>
  <div class="org-node-wrap">
    <!-- 当前节点卡片 -->
    <div class="org-card" :class="{ 'org-card--root': depth === 0, 'org-card--selected': selectedCode === node.company_code }"
      @click.stop="$emit('select', node)">
      <div class="org-card-header" :style="{ background: depth === 0 ? 'linear-gradient(135deg,#4b2d77,#7c5caa)' : `hsl(${260 - depth * 15}, 45%, ${92 - depth * 2}%)` }">
        <span class="org-card-name" :style="{ color: depth === 0 ? '#fff' : '#333' }">{{ node.company_name || node.name }}</span>
      </div>
      <div class="org-card-body">
        <span v-if="node.company_code" class="org-card-code">{{ node.company_code }}</span>
        <span v-if="node.shareholding" class="org-card-ratio">{{ node.shareholding }}%</span>
        <span v-if="node.children?.length" class="org-card-count">{{ node.children.length }}家</span>
      </div>
    </div>
    <!-- 子节点 -->
    <div v-if="node.children?.length && depth < 14" class="org-children">
      <org-node v-for="(child, ci) in node.children" :key="child.company_code || ci"
        :node="child" :depth="depth + 1" :selected-code="selectedCode"
        @select="$emit('select', $event)" />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ node: any; depth: number; selectedCode?: string }>()
defineEmits<{ (e: 'select', node: any): void }>()
</script>

<style scoped>
.org-node-wrap {
  display: flex; flex-direction: column; align-items: center; position: relative;
}
.org-card {
  min-width: 120px; max-width: 180px; border-radius: 8px; overflow: hidden;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08); cursor: pointer;
  transition: all 0.2s ease; border: 2px solid transparent;
}
.org-card:hover { transform: translateY(-2px); box-shadow: 0 4px 16px rgba(75,45,119,0.15); }
.org-card--selected { border-color: #4b2d77; box-shadow: 0 0 0 3px rgba(75,45,119,0.2); }
.org-card--root { min-width: 160px; }
.org-card-header { padding: 6px 10px; text-align: center; }
.org-card-name { font-size: 12px; font-weight: 600; line-height: 1.3; }
.org-card-body {
  padding: 4px 8px; background: #fff; display: flex; gap: 6px;
  justify-content: center; align-items: center; flex-wrap: wrap;
}
.org-card-code { font-size: 10px; color: #999; }
.org-card-ratio { font-size: 10px; color: #4b2d77; font-weight: 600; background: #f0edf5; padding: 1px 4px; border-radius: 3px; }
.org-card-count { font-size: 10px; color: #67c23a; }

/* 子节点容器 + 连接线 */
.org-children {
  display: flex; gap: 16px; padding-top: 24px; position: relative;
}
/* 垂直连接线（父→子） */
.org-children::before {
  content: ''; position: absolute; top: 0; left: 50%; width: 2px; height: 24px;
  background: #d8d0e8; transform: translateX(-50%);
}
/* 水平连接线（兄弟之间） */
.org-children::after {
  content: ''; position: absolute; top: 24px; height: 2px; background: #d8d0e8;
  left: calc(50% / var(--child-count, 1)); right: calc(50% / var(--child-count, 1));
}
/* 每个子节点的垂直连接线 */
.org-node-wrap::before {
  content: ''; position: absolute; top: -24px; left: 50%; width: 2px; height: 24px;
  background: #d8d0e8; transform: translateX(-50%);
}
/* 根节点不需要上方连接线 */
.org-node-wrap:first-child:last-child::before,
.org-children > .org-node-wrap:only-child::after { display: none; }
</style>
