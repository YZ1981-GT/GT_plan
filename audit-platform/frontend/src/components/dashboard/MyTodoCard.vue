<template>
  <div class="my-todo-card">
    <div class="my-todo-header">
      <span class="my-todo-title">我的待办</span>
      <el-button size="small" link @click="fetchTodos" :loading="loading">
        刷新
      </el-button>
    </div>

    <div v-if="loading" class="my-todo-loading" v-loading="true" style="min-height: 120px" />

    <template v-else>
      <!-- 空状态 -->
      <div v-if="!todos.length" class="my-todo-empty">
        <span>暂无待办，保持好状态 ✓</span>
      </div>

      <!-- 待办列表 -->
      <div v-else class="my-todo-list">
        <div
          v-for="item in todos"
          :key="item.wp_id"
          class="my-todo-item"
          @click="navigateToWorkpaper(item)"
        >
          <div class="my-todo-item-left">
            <el-tag
              size="small"
              :style="{ backgroundColor: urgencyColor(item.urgency), color: '#fff', border: 'none' }"
              effect="dark"
            >
              {{ urgencyLabel(item.urgency) }}
            </el-tag>
            <span class="my-todo-wp-code">{{ item.wp_code }}</span>
            <span class="my-todo-wp-name">{{ item.wp_name }}</span>
          </div>
          <div class="my-todo-item-right">
            <span class="my-todo-cycle">{{ item.cycle }}</span>
            <span class="my-todo-time">{{ formatTime(item.updated_at) }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/services/apiProxy'

interface TodoItem {
  wp_id: string
  wp_code: string
  wp_name: string
  cycle: string
  urgency: 'critical' | 'high' | 'medium' | 'normal'
  urgency_reason: string
  updated_at: string
}

interface MyTodoResponse {
  items: TodoItem[]
  total: number
}

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.projectId as string)

const loading = ref(false)
const todos = ref<TodoItem[]>([])

function urgencyColor(urgency: string): string {
  switch (urgency) {
    case 'critical': return '#D32F2F'
    case 'high': return '#EF6C00'
    case 'medium': return '#F57C00'
    case 'normal': return '#9E9E9E'
    default: return '#9E9E9E'
  }
}

function urgencyLabel(urgency: string): string {
  switch (urgency) {
    case 'critical': return '紧急'
    case 'high': return '高'
    case 'medium': return '中'
    case 'normal': return '普通'
    default: return '普通'
  }
}

function formatTime(dateStr: string): string {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function navigateToWorkpaper(item: TodoItem) {
  router.push({
    name: 'WorkpaperEditor',
    params: { projectId: projectId.value, wpId: item.wp_id },
  })
}

async function fetchTodos() {
  loading.value = true
  try {
    const data = await api.get<MyTodoResponse>(
      `/api/projects/${projectId.value}/my-todo`
    )
    todos.value = data.items || []
  } catch {
    todos.value = []
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchTodos()
})
</script>

<style scoped>
.my-todo-card {
  background: var(--el-bg-color, #fff);
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter, #ebeef5);
  padding: 16px;
}

.my-todo-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.my-todo-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary, #303133);
}

.my-todo-empty {
  text-align: center;
  padding: 32px 16px;
  color: var(--el-text-color-secondary, #909399);
  font-size: 14px;
}

.my-todo-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 360px;
  overflow-y: auto;
}

.my-todo-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
  border: 1px solid transparent;
}

.my-todo-item:hover {
  background: var(--el-fill-color-light, #f5f7fa);
  border-color: var(--el-border-color-lighter, #ebeef5);
}

.my-todo-item-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}

.my-todo-wp-code {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-primary, #303133);
  white-space: nowrap;
}

.my-todo-wp-name {
  font-size: 13px;
  color: var(--el-text-color-regular, #606266);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.my-todo-item-right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
  margin-left: 12px;
}

.my-todo-cycle {
  font-size: 12px;
  color: var(--el-text-color-secondary, #909399);
}

.my-todo-time {
  font-size: 12px;
  color: var(--el-text-color-placeholder, #a8abb2);
  white-space: nowrap;
}
</style>
