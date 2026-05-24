<!--
  MyTemplatesDialog.vue — 「我的模板」对话框（3 入口共用）
  Validates: Requirements 15.2, 15.4, 15.5
  Feature: advanced-query-enhancements-p1p2, Task 8.2

  3 个查询入口共用：CustomQueryTab / CustomQueryDialog / SheetCellRangePicker
  sessionStorage 缓存模板列表（5 分钟 TTL）
-->
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Loading } from '@element-plus/icons-vue'
import api from '@/services/api'
import type { CustomQueryTemplateConfig } from '@/types/custom-query-template'

const props = defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
  (e: 'load-template', config: CustomQueryTemplateConfig, templateName: string): void
}>()

interface TemplateItem {
  id: string
  name: string
  description: string | null
  data_source: string
  config: CustomQueryTemplateConfig
  scope: string
  is_owner: boolean
  created_at: string
  updated_at: string
}

const templates = ref<TemplateItem[]>([])
const loading = ref(false)
const CACHE_KEY = 'gt:cqd:my-templates-cache'
const CACHE_TTL = 5 * 60 * 1000 // 5 minutes

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

async function loadTemplates() {
  // Check sessionStorage cache first
  const cached = sessionStorage.getItem(CACHE_KEY)
  if (cached) {
    try {
      const { data, ts } = JSON.parse(cached)
      if (Date.now() - ts < CACHE_TTL) {
        templates.value = data
        return
      }
    } catch { /* cache corrupt, reload */ }
  }

  loading.value = true
  try {
    const resp = await api.get('/api/custom-query/templates')
    const data = resp.data?.templates ?? resp.data ?? []
    templates.value = data
    // Cache to sessionStorage
    sessionStorage.setItem(CACHE_KEY, JSON.stringify({ data, ts: Date.now() }))
  } catch (err: any) {
    ElMessage.error('加载模板列表失败')
  } finally {
    loading.value = false
  }
}

/** Invalidate cache (called after save/delete) */
export function invalidateTemplateCache() {
  sessionStorage.removeItem(CACHE_KEY)
}

async function onLoadTemplate(tpl: TemplateItem) {
  const config = tpl.config
  if (!config || !config.source) {
    ElMessage.warning('模板配置不完整，无法加载')
    return
  }

  // Stale sheet detection (Req 15 AC5 / Task 8.6)
  // Emit to parent which handles the actual state restoration
  emit('load-template', config, tpl.name)
  visible.value = false
  ElMessage.success(`已加载模板「${tpl.name}」`)
}

async function onDeleteTemplate(tpl: TemplateItem) {
  try {
    await ElMessageBox.confirm(
      `确定删除模板「${tpl.name}」？此操作不可恢复。`,
      '删除确认',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch { return }

  try {
    await api.delete(`/api/custom-query/templates/${tpl.id}`)
    templates.value = templates.value.filter(t => t.id !== tpl.id)
    invalidateTemplateCache()
    ElMessage.success('已删除')
  } catch (err: any) {
    ElMessage.error('删除失败')
  }
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleDateString('zh-CN') + ' ' + d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

onMounted(() => {
  if (props.modelValue) loadTemplates()
})

// Reload when dialog opens
function onOpen() {
  loadTemplates()
}
</script>

<template>
  <el-dialog
    v-model="visible"
    title="📚 我的查询模板"
    width="640px"
    append-to-body
    destroy-on-close
    @open="onOpen"
  >
    <div v-if="loading" style="text-align: center; padding: 32px;">
      <el-icon :size="24" class="is-loading"><Loading /></el-icon>
      <p style="margin-top: 8px; color: #909399;">加载中...</p>
    </div>

    <div v-else-if="templates.length === 0" style="text-align: center; padding: 32px; color: #909399;">
      暂无保存的模板，可在查询界面点击「💾 保存为模板」创建
    </div>

    <div v-else class="gt-template-list">
      <div
        v-for="tpl in templates"
        :key="tpl.id"
        class="gt-template-item"
      >
        <div class="gt-template-info">
          <div class="gt-template-name">{{ tpl.name }}</div>
          <div class="gt-template-meta">
            <span v-if="tpl.config?.source" class="gt-template-source">{{ tpl.config.source }}</span>
            <span v-if="tpl.config?.cell_range" class="gt-template-range">{{ tpl.config.cell_range }}</span>
            <span class="gt-template-date">{{ formatDate(tpl.updated_at) }}</span>
          </div>
          <div v-if="tpl.description" class="gt-template-desc">{{ tpl.description }}</div>
        </div>
        <div class="gt-template-actions">
          <el-button size="small" type="primary" @click="onLoadTemplate(tpl)">加载</el-button>
          <el-button
            v-if="tpl.is_owner"
            size="small"
            type="danger"
            plain
            :icon="Delete"
            @click="onDeleteTemplate(tpl)"
          />
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<style scoped>
.gt-template-list {
  max-height: 400px;
  overflow-y: auto;
}
.gt-template-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.gt-template-item:last-child {
  border-bottom: none;
}
.gt-template-item:hover {
  background: var(--el-fill-color-light);
}
.gt-template-info {
  flex: 1;
  min-width: 0;
}
.gt-template-name {
  font-weight: 500;
  font-size: 14px;
  color: var(--el-text-color-primary);
}
.gt-template-meta {
  display: flex;
  gap: 8px;
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.gt-template-source {
  background: var(--el-color-primary-light-9);
  padding: 0 6px;
  border-radius: 3px;
}
.gt-template-range {
  background: var(--el-color-success-light-9);
  padding: 0 6px;
  border-radius: 3px;
}
.gt-template-desc {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.gt-template-actions {
  display: flex;
  gap: 4px;
  margin-left: 12px;
}
</style>
