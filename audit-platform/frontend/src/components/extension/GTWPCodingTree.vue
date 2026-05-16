<template>
  <el-tree
    :data="treeData"
    :props="treeProps"
    node-key="id"
    highlight-current
    default-expand-all
    @node-click="onNodeClick"
  >
    <template #default="{ data: item }">
      <span class="gt-tree-node">
        <el-icon class="gt-tree-icon" :style="{ color: iconColor(item.wp_type) }">
          <Folder v-if="item.children?.length" />
          <Document v-else />
        </el-icon>
        <span class="gt-tree-label">
          <span class="gt-tree-code">{{ item.code_prefix }}</span>
          {{ item.cycle_name || item.label }}
        </span>
      </span>
    </template>
  </el-tree>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Folder, Document } from '@element-plus/icons-vue'

const props = defineProps<{
  data: any[]
}>()

const emit = defineEmits<{
  (e: 'node-click', node: any): void
}>()

const treeProps = { label: 'label', children: 'children' }

// Group flat data by wp_type into tree
const wpTypeOrder = ['preliminary', 'risk_assessment', 'control_test', 'substantive', 'completion', 'specific', 'general', 'permanent']
const wpTypeLabels: Record<string, string> = {
  preliminary: 'B类 - 初步业务活动',
  risk_assessment: 'B类 - 风险评估',
  control_test: 'C类 - 控制测试',
  substantive: 'D-N类 - 实质性程序',
  completion: 'A类 - 完成阶段',
  specific: 'S类 - 特定项目',
  general: 'T类 - 通用',
  permanent: 'Z类 - 永久性档案',
}

const treeData = computed(() => {
  const grouped: Record<string, any[]> = {}
  for (const item of props.data) {
    const type = item.wp_type || 'other'
    if (!grouped[type]) grouped[type] = []
    grouped[type].push({ ...item, label: `${item.code_prefix} ${item.cycle_name || ''}` })
  }
  return wpTypeOrder
    .filter(t => grouped[t]?.length)
    .map(t => ({
      id: `group-${t}`,
      label: wpTypeLabels[t] || t,
      code_prefix: t.charAt(0).toUpperCase(),
      wp_type: t,
      children: (grouped[t] || []).sort((a: any, b: any) => (a.sort_order ?? 0) - (b.sort_order ?? 0)),
    }))
})

function iconColor(type: string) {
  const m: Record<string, string> = {
    preliminary: '#4b2d77',
    risk_assessment: '#4b2d77',
    control_test: '#0094B3',
    substantive: '#28A745',
    completion: '#FFC23D',
    specific: '#FF5149',
    general: '#6e6e73',
    permanent: '#999',
  }
  return m[type] || 'var(--gt-color-text-secondary)'
}

function onNodeClick(item: any) {
  if (!item.id?.startsWith('group-')) {
    emit('node-click', item)
  }
}
</script>

<style scoped>
.gt-tree-node { display: flex; align-items: center; gap: 6px; font-size: var(--gt-font-size-sm); }
.gt-tree-icon { font-size: var(--gt-font-size-md); flex-shrink: 0; }
.gt-tree-code { font-weight: 600; color: var(--gt-color-primary); margin-right: 4px; }
</style>
