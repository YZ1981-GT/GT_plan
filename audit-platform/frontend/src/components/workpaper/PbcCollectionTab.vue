<!--
  PbcCollectionTab.vue — 底稿侧栏"证据收集"tab
  
  显示关联 PBC 项 + 收集状态，缺失证据高亮提示
  Spec: wp-evidence-collection Task 2.1 / 2.2
-->
<template>
  <div class="gt-pbc-collection">
    <div v-if="loading" v-loading="true" style="min-height: 120px" />
    <template v-else>
      <!-- 缺失证据高亮提示 -->
      <el-alert
        v-if="missingCount > 0"
        type="warning"
        :closable="false"
        class="gt-pbc-alert"
      >
        <template #title>
          <span>⚠️ {{ missingCount }} 项证据待收集</span>
        </template>
      </el-alert>

      <!-- PBC 项列表 -->
      <div v-if="items.length === 0" class="gt-pbc-empty">
        本底稿暂无关联 PBC 项
      </div>
      <div v-else class="gt-pbc-list">
        <div
          v-for="item in items"
          :key="item.id"
          class="gt-pbc-item"
          :class="{ 'gt-pbc-item--missing': item.status === 'pending' }"
        >
          <div class="gt-pbc-item__header">
            <span class="gt-pbc-item__name">{{ item.item_name }}</span>
            <el-tag
              :type="statusTagType(item.status)"
              size="small"
            >
              {{ statusLabel(item.status) }}
            </el-tag>
          </div>
          <div v-if="item.category" class="gt-pbc-item__meta">
            分类: {{ item.category }}
          </div>
          <div v-if="item.due_date" class="gt-pbc-item__meta">
            截止: {{ item.due_date }}
            <el-tag v-if="isOverdue(item)" type="danger" size="small">逾期</el-tag>
          </div>
          <div v-if="item.notes" class="gt-pbc-item__notes">
            {{ item.notes }}
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { apiProxy } from '@/services/apiProxy'

const props = defineProps<{
  projectId: string
  wpId: string
}>()

const loading = ref(true)
const items = ref<any[]>([])

const missingCount = computed(() =>
  items.value.filter(i => i.status === 'pending').length
)

function statusTagType(status: string) {
  switch (status) {
    case 'received': return 'success'
    case 'reviewed': return 'primary'
    case 'rejected': return 'danger'
    default: return 'warning'
  }
}

function statusLabel(status: string) {
  switch (status) {
    case 'pending': return '待收集'
    case 'received': return '已收到'
    case 'reviewed': return '已审阅'
    case 'rejected': return '已退回'
    default: return status
  }
}

function isOverdue(item: any) {
  if (!item.due_date || item.status !== 'pending') return false
  return new Date(item.due_date) < new Date()
}

async function fetchItems() {
  loading.value = true
  try {
    const data = await apiProxy.get(
      `/projects/${props.projectId}/pbc/by-workpaper/${props.wpId}`
    )
    items.value = Array.isArray(data) ? data : []
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}

onMounted(fetchItems)
</script>

<style scoped>
.gt-pbc-collection {
  padding: 4px;
}
.gt-pbc-alert {
  margin-bottom: 12px;
}
.gt-pbc-empty {
  text-align: center;
  color: var(--el-text-color-secondary);
  padding: 24px 0;
}
.gt-pbc-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.gt-pbc-item {
  padding: 8px 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  background: var(--el-fill-color-blank);
}
.gt-pbc-item--missing {
  border-left: 3px solid var(--el-color-warning);
  background: var(--el-color-warning-light-9);
}
.gt-pbc-item__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.gt-pbc-item__name {
  font-weight: 500;
  font-size: 13px;
}
.gt-pbc-item__meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 2px;
}
.gt-pbc-item__notes {
  font-size: 12px;
  color: var(--el-text-color-regular);
  margin-top: 4px;
  white-space: pre-wrap;
}
</style>
