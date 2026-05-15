<template>
  <div class="gt-word-editor gt-fade-in">
    <EditorSharedToolbar
      :wp-code="wpDetail?.wp_code"
      :wp-name="wpDetail?.wp_name"
      :status="wpDetail?.status"
      component-type="word"
      :dirty="dirty"
      :saving="saving"
      @back="goBack"
      @save="onSave"
      @export="onExport"
      @versions="$emit('show-versions')"
      @toggle-panel="$emit('toggle-panel')"
    />

    <div class="gt-word-editor-body" v-loading="loading">
      <el-empty v-if="!loading && !fields.length && !content" description="暂无文档内容" />

      <!-- 字段填充模式：模板字段列表 + 预览 -->
      <div v-if="fields.length" class="gt-word-fields-section">
        <h4 style="margin-bottom: 12px; color: var(--gt-color-text)">📝 模板字段填充</h4>
        <el-form label-width="160px" label-position="top">
          <el-form-item v-for="f in fields" :key="f.key" :label="f.label">
            <el-input
              v-model="fieldValues[f.key]"
              :placeholder="f.placeholder || `请输入${f.label}`"
              @change="markDirty"
            />
          </el-form-item>
        </el-form>
        <el-divider />
      </div>

      <!-- 富文本编辑区 -->
      <div class="gt-word-content-section">
        <h4 v-if="fields.length" style="margin-bottom: 12px; color: var(--gt-color-text)">📄 正文内容</h4>
        <el-input
          v-model="content"
          type="textarea"
          :rows="20"
          placeholder="在此编辑文档正文内容..."
          @input="markDirty"
          class="gt-word-textarea"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import EditorSharedToolbar from '@/components/workpaper/EditorSharedToolbar.vue'
import { api as httpApi } from '@/services/apiProxy'
import { workpapers as P_wp } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import type { WorkpaperDetail } from '@/services/workpaperApi'

interface TemplateField {
  key: string
  label: string
  placeholder?: string
}

const props = defineProps<{
  projectId: string
  wpId: string
  wpDetail: WorkpaperDetail | null
}>()

const emit = defineEmits<{
  'show-versions': []
  'toggle-panel': []
  saved: []
}>()

const loading = ref(true)
const saving = ref(false)
const dirty = ref(false)
const content = ref('')
const fields = ref<TemplateField[]>([])
const fieldValues = reactive<Record<string, string>>({})

function markDirty() { dirty.value = true }
function goBack() { window.history.back() }

async function loadData() {
  loading.value = true
  try {
    const detail = await httpApi.get(P_wp.detail(props.projectId, props.wpId))
    const parsed = detail?.parsed_data || {}
    // Template fields from metadata
    fields.value = parsed._fields || []
    content.value = parsed._content || parsed.content || ''
    // Populate field values
    for (const f of fields.value) {
      fieldValues[f.key] = parsed[f.key] ?? ''
    }
  } catch (e: any) {
    handleApiError(e, '加载文档')
  } finally {
    loading.value = false
  }
}

async function onSave() {
  saving.value = true
  try {
    const payload: Record<string, any> = {
      ...fieldValues,
      _fields: fields.value,
      _content: content.value,
    }
    await httpApi.put(P_wp.detail(props.projectId, props.wpId), {
      parsed_data: payload,
    })
    dirty.value = false
    ElMessage.success('保存成功')
    emit('saved')
  } catch (e: any) {
    handleApiError(e, '保存文档')
  } finally {
    saving.value = false
  }
}

function onExport() {
  ElMessage.info('Word 导出功能开发中')
}

watch(() => props.wpId, () => { if (props.wpId) loadData() })
onMounted(() => { if (props.wpId) loadData() })
</script>

<style scoped>
.gt-word-editor { display: flex; flex-direction: column; height: 100%; }
.gt-word-editor-body { flex: 1; overflow-y: auto; padding: 24px 32px; }
.gt-word-fields-section { max-width: 700px; margin: 0 auto; }
.gt-word-content-section { max-width: 800px; margin: 0 auto; }
.gt-word-textarea :deep(textarea) {
  font-family: 'SimSun', serif;
  font-size: 14px;
  line-height: 1.8;
}
</style>
