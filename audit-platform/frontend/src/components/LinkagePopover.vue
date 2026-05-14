<script setup lang="ts">
/**
 * LinkagePopover — 联动详情弹出面板 [enterprise-linkage 3.6]
 *
 * 弹出面板显示分录摘要/底稿列表，点击跳转。
 */
import { useRouter } from 'vue-router'

export interface LinkageItem {
  id: string
  label: string
  sublabel?: string
  amount?: number
}

const props = defineProps<{
  items: LinkageItem[]
  type: 'adjustment' | 'workpaper'
  projectId: string
}>()

const router = useRouter()

function onItemClick(item: LinkageItem) {
  if (props.type === 'adjustment') {
    router.push({ path: `/projects/${props.projectId}/adjustments`, query: { highlight: item.id } })
  } else {
    router.push({ path: `/projects/${props.projectId}/workpapers`, query: { wpId: item.id } })
  }
}
</script>

<template>
  <div class="linkage-popover-content">
    <div class="linkage-popover-title">
      {{ type === 'adjustment' ? '关联调整分录' : '关联底稿' }}（{{ items.length }}）
    </div>
    <div v-if="items.length === 0" class="linkage-empty">暂无关联</div>
    <div
      v-for="item in items"
      :key="item.id"
      class="linkage-item"
      @click="onItemClick(item)"
    >
      <span class="linkage-item-label">{{ item.label }}</span>
      <span v-if="item.sublabel" class="linkage-item-sub">{{ item.sublabel }}</span>
      <span v-if="item.amount != null" class="linkage-item-amount">
        {{ item.amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 }) }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.linkage-popover-content {
  max-height: 240px;
  overflow-y: auto;
  min-width: 200px;
}
.linkage-popover-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid #ebeef5;
}
.linkage-empty {
  font-size: 12px;
  color: #909399;
  text-align: center;
  padding: 12px 0;
}
.linkage-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 4px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  transition: background 0.15s;
}
.linkage-item:hover {
  background: #f5f7fa;
}
.linkage-item-label {
  color: #409eff;
  font-weight: 500;
}
.linkage-item-sub {
  color: #606266;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.linkage-item-amount {
  color: #303133;
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
</style>
