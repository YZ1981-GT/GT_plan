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
      <el-empty v-if="!loading && !content && !fields.length && renderMode === 'empty'" description="暂无文档内容" />

      <!-- 字段填充区（如有 metadata 定义字段） -->
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

      <!-- 渲染模式 1：Univer Docs（首选） -->
      <div v-show="renderMode === 'univer'" ref="univerContainer" class="gt-word-univer-container"></div>

      <!-- 渲染模式 2：TipTap 兜底（mammoth → HTML） -->
      <div v-if="renderMode === 'tiptap'" class="gt-word-tiptap-section">
        <el-alert
          type="info"
          show-icon
          :closable="false"
          style="margin-bottom: 12px"
        >
          模板格式较复杂，已切换到富文本兜底编辑器（保留 80%+ 内容，部分高级格式如页眉/嵌套表格/字段域可能损失）
        </el-alert>
        <editor-content :editor="tiptapEditor" class="gt-word-tiptap-editor" />
      </div>

      <!-- 渲染模式 3：纯文本 textarea（最末端兜底） -->
      <div v-if="renderMode === 'textarea'" class="gt-word-textarea-section">
        <el-alert
          type="warning"
          show-icon
          :closable="false"
          style="margin-bottom: 12px"
        >
          无法解析模板内容，已降级为纯文本编辑模式。
        </el-alert>
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
import { ref, reactive, onMounted, onBeforeUnmount, shallowRef, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Editor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
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

// 渲染模式：empty / univer / tiptap / textarea
const renderMode = ref<'empty' | 'univer' | 'tiptap' | 'textarea'>('empty')
const univerContainer = ref<HTMLDivElement>()
const univerInstance = shallowRef<any>(null)
const univerAPI = shallowRef<any>(null)
const tiptapEditor = shallowRef<Editor | null>(null)

function markDirty() { dirty.value = true }
function goBack() { window.history.back() }

/**
 * 三级降级策略加载文档：
 * Tier 1: Univer Docs（后端 docx-to-json，最佳还原 80-90%）
 * Tier 2: mammoth → HTML → TipTap（兜底，保留文字+段落+表格基础格式）
 * Tier 3: 纯文本 textarea（最末端，仅保留文字内容）
 */
async function loadData() {
  loading.value = true
  try {
    const detail = await httpApi.get(P_wp.detail(props.projectId, props.wpId))
    const parsed = detail?.parsed_data || {}
    fields.value = parsed._fields || []
    content.value = parsed._content || parsed.content || ''
    for (const f of fields.value) {
      fieldValues[f.key] = parsed[f.key] ?? ''
    }

    // 已有 parsed_data._content（用户编辑过）→ 用 textarea 显示，避免覆盖用户编辑
    if (content.value) {
      renderMode.value = 'textarea'
      return
    }

    // Tier 1: Univer Docs
    const univerOk = await tryLoadUniver()
    if (univerOk) {
      renderMode.value = 'univer'
      return
    }

    // Tier 2: mammoth → TipTap
    const tiptapOk = await tryLoadTipTapFromDocx()
    if (tiptapOk) {
      renderMode.value = 'tiptap'
      return
    }

    // Tier 3: empty / textarea
    renderMode.value = 'textarea'
  } catch (e: any) {
    handleApiError(e, '加载文档')
    renderMode.value = 'textarea'
  } finally {
    loading.value = false
  }
}

/** Tier 1: 后端 docx-to-json → Univer Docs */
async function tryLoadUniver(): Promise<boolean> {
  try {
    const result = await httpApi.get(
      `/api/projects/${props.projectId}/workpapers/${props.wpId}/template-file/docx-to-json`,
    )
    if (!result?.snapshot) return false

    // 动态导入 Univer Docs preset（避免污染 sheets-only 视图）
    const [{ createUniver, LocaleType }, { UniverDocsCorePreset }] = await Promise.all([
      import('@univerjs/presets'),
      import('@univerjs/preset-docs-core'),
    ])
    // 需要时间让 v-show='univer' 生效后挂载
    await new Promise((r) => setTimeout(r, 50))
    if (!univerContainer.value) return false

    const { univer, univerAPI: api } = createUniver({
      locale: LocaleType.ZH_CN,
      presets: [
        UniverDocsCorePreset({
          container: univerContainer.value,
        }),
      ],
    })
    univerInstance.value = univer
    univerAPI.value = api

    // 加载 docx snapshot
    api.createUnit('UNIVER_DOC', result.snapshot)
    return true
  } catch (e: any) {
    console.warn('[WorkpaperWordEditor] Univer Docs load failed, fallback to TipTap:', e)
    return false
  }
}

/** Tier 2: 前端 mammoth 直接解析 docx → TipTap HTML */
async function tryLoadTipTapFromDocx(): Promise<boolean> {
  try {
    // 拉原始 docx blob
    const token = sessionStorage.getItem('token') || localStorage.getItem('token') || ''
    const resp = await fetch(
      `/api/projects/${props.projectId}/workpapers/${props.wpId}/template-file`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    if (!resp.ok) return false
    const blob = await resp.blob()
    if (blob.size < 100) return false

    const arrayBuffer = await blob.arrayBuffer()
    const mammoth = await import('mammoth')
    const { value: html } = await mammoth.convertToHtml({ arrayBuffer })

    if (!html || html.length < 10) return false

    tiptapEditor.value = new Editor({
      content: html,
      extensions: [StarterKit],
      editable: true,
      onUpdate: () => {
        markDirty()
      },
    })
    return true
  } catch (e: any) {
    console.warn('[WorkpaperWordEditor] mammoth/TipTap fallback failed:', e)
    return false
  }
}

async function onSave() {
  saving.value = true
  try {
    let savedContent = content.value
    if (renderMode.value === 'tiptap' && tiptapEditor.value) {
      // TipTap → HTML 序列化
      savedContent = tiptapEditor.value.getHTML()
    } else if (renderMode.value === 'univer' && univerAPI.value) {
      // Univer 暂不直接序列化为可编辑 docx；保存当前 snapshot 供回放
      const docs = univerAPI.value.getActiveDocument?.() ?? null
      if (docs) {
        const snapshot = docs.getSnapshot?.()
        savedContent = snapshot ? JSON.stringify({ _univer_snapshot: snapshot }) : savedContent
      }
    }

    const payload: Record<string, any> = {
      ...fieldValues,
      _fields: fields.value,
      _content: savedContent,
      _render_mode: renderMode.value,
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
  ElMessage.info('Word 导出功能开发中（当前可下载原模板编辑后再上传）')
}

onBeforeUnmount(() => {
  if (univerInstance.value?.dispose) {
    try { univerInstance.value.dispose() } catch { /* ignore */ }
  }
  if (tiptapEditor.value) {
    tiptapEditor.value.destroy()
  }
})

watch(() => props.wpId, () => { if (props.wpId) loadData() })
onMounted(() => { if (props.wpId) loadData() })
</script>

<style scoped>
.gt-word-editor { display: flex; flex-direction: column; height: 100%; }
.gt-word-editor-body { flex: 1; overflow-y: auto; padding: 24px 32px; }
.gt-word-fields-section { max-width: 700px; margin: 0 auto; }
.gt-word-univer-container { width: 100%; height: 100%; min-height: 600px; background: var(--gt-color-bg-white); border-radius: var(--gt-radius-md); }
.gt-word-tiptap-section { max-width: 800px; margin: 0 auto; }
.gt-word-tiptap-editor :deep(.ProseMirror) {
  background: var(--gt-color-bg-white);
  border: 1px solid var(--gt-color-border);
  border-radius: var(--gt-radius-md);
  padding: 24px 32px;
  min-height: 500px;
  font-family: 'SimSun', serif;
  font-size: var(--gt-font-size-sm);
  line-height: 1.8;
  outline: none;
}
.gt-word-textarea-section { max-width: 800px; margin: 0 auto; }
.gt-word-textarea :deep(textarea) {
  font-family: 'SimSun', serif;
  font-size: var(--gt-font-size-sm);
  line-height: 1.8;
}
</style>
