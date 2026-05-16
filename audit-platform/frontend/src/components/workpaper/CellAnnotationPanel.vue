<script setup lang="ts">
/**
 * 复核批注面板 — 批注列表+状态筛选+点击定位
 * Sprint 10 Task 10.3
 */
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { useRoute } from 'vue-router'
import { eventBus } from '@/utils/eventBus'

interface Annotation {
  id: string
  cell_ref: string | null
  content: string
  status: string
  author_id: string
  mentioned_user_ids: Record<string, string> | null
  created_at: string
}

const props = defineProps<{ wpId: string; projectId: string }>()
const route = useRoute()

const annotations = ref<Annotation[]>([])
const statusFilter = ref<string>('')
const loading = ref(false)

const filteredAnnotations = computed(() => {
  if (!statusFilter.value) return annotations.value
  return annotations.value.filter(a => a.status === statusFilter.value)
})

async function loadAnnotations() {
  loading.value = true
  try {
    const params = statusFilter.value ? { status: statusFilter.value } : {}
    const data = await api.get(`/api/workpapers/${props.wpId}/annotations`, { params })
    annotations.value = data as Annotation[]
  } catch {
    ElMessage.error('加载批注失败')
  } finally {
    loading.value = false
  }
}

function locateCell(ann: Annotation) {
  if (!ann.cell_ref) return
  eventBus.emit('workpaper:locate-cell', { wpId: props.wpId, cellRef: ann.cell_ref })
}

function statusTag(status: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  const map: Record<string, '' | 'success' | 'warning' | 'info' | 'danger' | 'primary'> = { open: 'danger', replied: 'warning', resolved: 'success' }
  return map[status] || 'info'
}

function statusLabel(status: string) {
  const map: Record<string, string> = { open: '待处理', replied: '已回复', resolved: '已解决' }
  return map[status] || status
}

onMounted(loadAnnotations)
</script>

<template>
  <div class="cell-annotation-panel">
    <div class="panel-header">
      <span class="title">复核意见</span>
      <el-radio-group v-model="statusFilter" size="small" @change="loadAnnotations">
        <el-radio-button label="">全部</el-radio-button>
        <el-radio-button label="open">待处理</el-radio-button>
        <el-radio-button label="replied">已回复</el-radio-button>
        <el-radio-button label="resolved">已解决</el-radio-button>
      </el-radio-group>
    </div>
    <el-scrollbar max-height="400px">
      <div v-if="loading" class="loading-tip">加载中...</div>
      <div v-else-if="filteredAnnotations.length === 0" class="empty-tip">暂无批注</div>
      <div
        v-for="ann in filteredAnnotations"
        :key="ann.id"
        class="annotation-item"
        @click="locateCell(ann)"
      >
        <div class="item-header">
          <el-tag :type="statusTag(ann.status) || undefined" size="small">{{ statusLabel(ann.status) }}</el-tag>
          <span class="cell-ref">{{ ann.cell_ref || '-' }}</span>
        </div>
        <div class="item-content">{{ ann.content }}</div>
        <div class="item-time">{{ ann.created_at?.slice(0, 16) }}</div>
      </div>
    </el-scrollbar>
  </div>
</template>

<style scoped>
.cell-annotation-panel { padding: 12px; }
.panel-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.title { font-weight: 600; font-size: var(--gt-font-size-sm); }
.annotation-item { padding: 8px; border-bottom: 1px solid #f0f0f0; cursor: pointer; }
.annotation-item:hover { background: var(--gt-color-primary-bg); }
.item-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.cell-ref { font-size: var(--gt-font-size-xs); color: var(--gt-color-info); }
.item-content { font-size: var(--gt-font-size-sm); line-height: 1.4; }
.item-time { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-placeholder); margin-top: 4px; }
.loading-tip, .empty-tip { text-align: center; padding: 24px; color: var(--gt-color-info); }
</style>
