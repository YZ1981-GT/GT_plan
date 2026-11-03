<template>
  <div v-if="projectId" class="chat-project-attachment-picker">
    <el-button
      size="small"
      plain
      :disabled="disabled"
      aria-label="选择本次 AI 对话要引用的项目附件"
      @click="openPicker"
    >
      项目附件<span v-if="selectedIds.length">（{{ selectedIds.length }}）</span>
    </el-button>
    <el-dialog v-model="visible" title="选择项目附件" width="560px" append-to-body>
      <el-alert
        type="info"
        :closable="false"
        title="附件只用于本次对话；平台会在服务端复核权限并钉住确定版本。"
        show-icon
      />
      <el-alert
        v-if="loadError"
        type="error"
        :closable="false"
        title="附件列表加载失败，请重试"
        show-icon
        style="margin-top: 12px"
      />
      <el-select
        v-model="draftIds"
        multiple
        filterable
        collapse-tags
        :loading="loading"
        placeholder="选择项目附件"
        aria-label="本次对话引用的项目附件"
        style="width: 100%; margin-top: 16px"
      >
        <el-option
          v-for="item in items"
          :key="item.id"
          :label="attachmentLabel(item)"
          :value="item.id"
          :disabled="item.state && item.state !== 'available'"
        />
      </el-select>
      <el-empty v-if="!loading && !loadError && items.length === 0" description="暂无可用项目附件" :image-size="48" />
      <template #footer>
        <el-button v-if="loadError" @click="load(true)">重试</el-button>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :disabled="loading || !!loadError" @click="apply">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { api } from '@/services/apiProxy'
import { attachments as P_att } from '@/services/apiPaths'

const props = defineProps<{
  projectId: string | null | undefined
  disabled?: boolean
}>()
const emit = defineEmits<{ change: [ids: string[]] }>()

const visible = ref(false)
const loading = ref(false)
const loadError = ref(false)
const loadedProjectId = ref('')
const items = ref<any[]>([])
const selectedIds = ref<string[]>([])
const draftIds = ref<string[]>([])

watch(() => props.projectId, () => {
  items.value = []
  selectedIds.value = []
  draftIds.value = []
  loadedProjectId.value = ''
  loadError.value = false
  emit('change', [])
})

function attachmentLabel(item: any): string {
  const type = item.attachment_type ? ` · ${item.attachment_type}` : ''
  const unavailable = item.state && item.state !== 'available' ? '（不可用）' : ''
  return `${item.file_name || item.id}${type}${unavailable}`
}

async function load(force = false) {
  const projectId = props.projectId
  if (!projectId || loading.value) return
  if (!force && loadedProjectId.value === projectId && !loadError.value) return
  loading.value = true
  loadError.value = false
  try {
    const data: any = await api.get(P_att.list(projectId), {
      params: { page: 1, page_size: 200 }, _silent: true,
    } as any)
    items.value = Array.isArray(data) ? data : (data?.items ?? [])
    loadedProjectId.value = projectId
  } catch {
    items.value = []
    loadError.value = true
  } finally {
    loading.value = false
  }
}

function openPicker() {
  draftIds.value = [...selectedIds.value]
  visible.value = true
  void load()
}

function apply() {
  selectedIds.value = [...new Set(draftIds.value)]
  emit('change', [...selectedIds.value])
  visible.value = false
}

function clear() {
  selectedIds.value = []
  draftIds.value = []
  emit('change', [])
}

defineExpose({ clear })
</script>

<style scoped>
.chat-project-attachment-picker { display: inline-flex; }
@media (max-width: 390px) {
  .chat-project-attachment-picker { width: 100%; }
  .chat-project-attachment-picker :deep(.el-button) { width: 100%; }
}
</style>
