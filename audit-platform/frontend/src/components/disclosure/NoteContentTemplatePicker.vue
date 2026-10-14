<script setup lang="ts">
/**
 * NoteContentTemplatePicker — 附注内容模板列表与版本选择
 *
 * spec: disclosure-note-doc-upload-and-batch-fill Phase 8 Task 46/48
 */
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useNoteContentTemplate, type ContentTemplateItem } from '@/composables/useNoteContentTemplate'

const props = defineProps<{
  visible: boolean
  projectId: string
}>()

const emit = defineEmits<{
  'update:visible': [val: boolean]
  'select': [template: ContentTemplateItem, versionId: string]
}>()

const dialogVisible = computed({
  get: () => props.visible,
  set: (v) => emit('update:visible', v),
})

const tmpl = useNoteContentTemplate({ projectId: computed(() => props.projectId) })

onMounted(() => { if (props.visible) tmpl.fetchTemplates() })
watch(() => props.visible, (v) => { if (v) tmpl.fetchTemplates() })

function onSelect(item: ContentTemplateItem) {
  if (!item.current_version_id) {
    ElMessage.warning('该模板暂无版本')
    return
  }
  emit('select', item, item.current_version_id)
  dialogVisible.value = false
}
</script>

<template>
  <el-dialog v-model="dialogVisible" title="📋 选择附注内容模板" width="700px" append-to-body destroy-on-close>
    <div v-if="tmpl.loading.value" style="text-align: center; padding: 40px;">加载中...</div>
    <div v-else-if="!tmpl.templates.value.length" style="text-align: center; padding: 40px; color: var(--el-text-color-placeholder);">
      暂无可用的附注内容模板
    </div>
    <div v-else>
      <div v-for="item in tmpl.templates.value" :key="item.id"
        style="padding: 12px; margin-bottom: 8px; border: 1px solid var(--el-border-color-lighter); border-radius: 6px; cursor: pointer;"
        @click="onSelect(item)"
      >
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <strong>{{ item.name }}</strong>
          <el-tag size="small" :type="item.owner_scope === 'group' ? 'warning' : 'info'">
            {{ item.owner_scope === 'group' ? '集团' : '个人' }}
          </el-tag>
        </div>
        <div v-if="item.description" style="font-size: 13px; color: var(--el-text-color-secondary); margin-top: 4px;">
          {{ item.description }}
        </div>
        <div style="font-size: 12px; color: var(--el-text-color-placeholder); margin-top: 4px;">
          更新于 {{ item.updated_at?.slice(0, 10) }}
        </div>
      </div>
    </div>
  </el-dialog>
</template>
