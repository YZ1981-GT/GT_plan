<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import AttachmentEyeButton from './AttachmentEyeButton.vue'
import { usePermissionMatrix, type Resource } from '@/composables/usePermissionMatrix'
import { useProjectStore } from '@/stores/project'
import { handleApiError } from '@/utils/errorHandler'

export interface TraceAttachment {
  id: string
  attachment_id: string
  target_type: string
  target_ref: string
  file_name?: string | null
  file_type?: string | null
  created_at?: string | null
}

const props = withDefaults(defineProps<{
  projectId: string
  objectType: 'report_row' | 'note_cell' | 'deliverable_section'
  targetType: 'report_row' | 'note_section' | 'deliverable_section'
  targetRef: string
  resource: Resource
  initialAttachments?: TraceAttachment[]
}>(), { initialAttachments: undefined })

const emit = defineEmits<{ changed: [rows: TraceAttachment[]] }>()
const rows = ref<TraceAttachment[]>([])
const loading = ref(false)
const error = ref('')
const dialogOpen = ref(false)
const candidates = ref<any[]>([])
const candidateLoading = ref(false)
const selectedId = ref('')
const saving = ref(false)
const projectStore = useProjectStore()
const { canDo } = usePermissionMatrix()
const canWrite = computed(() =>
  projectStore.projectStatus !== 'archived' && canDo('edit', props.resource),
)

async function load(): Promise<void> {
  if (!props.projectId || !props.targetRef) return
  loading.value = true
  error.value = ''
  try {
    const data: any = await api.get(`/api/projects/${props.projectId}/lineage`, {
      params: { object_type: props.objectType, object_id: props.targetRef, direction: 'both' },
      _dedupe: false,
      _silent: true,
    } as any)
    rows.value = Array.isArray(data?.attachments) ? data.attachments : []
    emit('changed', rows.value)
  } catch (cause) {
    error.value = '附件溯源加载失败，不能据此判断为无附件'
  } finally {
    loading.value = false
  }
}

async function openLinker(): Promise<void> {
  dialogOpen.value = true
  selectedId.value = ''
  candidateLoading.value = true
  try {
    const data: any = await api.get(`/api/projects/${props.projectId}/attachments`, {
      _silent: true, _dedupe: false,
    } as any)
    const linked = new Set(rows.value.map(row => row.attachment_id))
    candidates.value = (Array.isArray(data) ? data : []).filter(row => row?.id && !linked.has(String(row.id)))
  } catch (cause) {
    candidates.value = []
    handleApiError(cause, '加载项目附件')
  } finally {
    candidateLoading.value = false
  }
}

async function linkSelected(): Promise<void> {
  if (!selectedId.value) return
  saving.value = true
  try {
    await api.post(`/api/attachments/${selectedId.value}/link`, {
      target_type: props.targetType,
      target_ref: props.targetRef,
    }, { _silent: true } as any)
    dialogOpen.value = false
    ElMessage.success('附件已关联到当前溯源位置')
    await load()
  } catch (cause) {
    handleApiError(cause, '关联附件')
  } finally {
    saving.value = false
  }
}

async function unlink(row: TraceAttachment): Promise<void> {
  try {
    await api.delete(`/api/attachments/${row.attachment_id}/link/${row.id}`, { _silent: true } as any)
    ElMessage.success('已解除附件溯源关联，原文件仍保留')
    await load()
  } catch (cause) {
    handleApiError(cause, '解除附件关联')
  }
}

watch(
  () => [props.targetRef, props.initialAttachments] as const,
  ([, initial]) => {
    if (initial !== undefined) rows.value = [...initial]
    else void load()
  },
  { immediate: true, deep: true },
)
</script>

<template>
  <section class="output-attachments" data-testid="output-attachment-links">
    <div class="output-attachments__header">
      <strong>关联附件</strong>
      <el-button
        v-if="canWrite"
        size="small"
        type="primary"
        plain
        :disabled="!targetRef"
        data-testid="output-attachment-add"
        @click="openLinker"
      >关联项目附件</el-button>
    </div>
    <el-alert v-if="error" type="warning" :closable="false" :title="error">
      <el-button link type="primary" @click="load">重试</el-button>
    </el-alert>
    <div v-else-if="loading" class="output-attachments__hint">正在加载附件…</div>
    <ul v-else-if="rows.length" class="output-attachments__list">
      <li v-for="row in rows" :key="row.id">
        <span class="output-attachments__name" :title="row.file_name || ''">{{ row.file_name || '未命名附件' }}</span>
        <AttachmentEyeButton
          :attachment-id="row.attachment_id"
          :file-name="row.file_name || undefined"
          :file-type="row.file_type || undefined"
        />
        <el-button v-if="canWrite" link type="danger" size="small" @click="unlink(row)">解除</el-button>
      </li>
    </ul>
    <div v-else class="output-attachments__hint">当前位置暂无关联附件</div>

    <el-dialog v-model="dialogOpen" title="关联项目附件" width="520px" append-to-body>
      <el-select
        v-model="selectedId"
        filterable
        :loading="candidateLoading"
        placeholder="选择已有附件"
        style="width: 100%"
      >
        <el-option
          v-for="item in candidates"
          :key="item.id"
          :value="item.id"
          :label="item.file_name"
        />
      </el-select>
      <el-empty v-if="!candidateLoading && !candidates.length" description="没有可关联的项目附件" :image-size="60" />
      <template #footer>
        <el-button @click="dialogOpen = false">取消</el-button>
        <el-button type="primary" :loading="saving" :disabled="!selectedId" @click="linkSelected">确认关联</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.output-attachments { margin: 12px 0; padding: 10px 12px; border: 1px solid var(--gt-color-border-light, #e4e7ed); border-radius: 8px; }
.output-attachments__header { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
.output-attachments__hint { color: var(--gt-color-text-secondary, #606266); font-size: var(--gt-font-size-xs, 12px); }
.output-attachments__list { list-style: none; margin: 0; padding: 0; }
.output-attachments__list li { display: flex; align-items: center; gap: 8px; min-width: 0; margin-top: 5px; }
.output-attachments__name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
