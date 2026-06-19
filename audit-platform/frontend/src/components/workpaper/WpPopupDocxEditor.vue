<script setup lang="ts">
/**
 * WpPopupDocxEditor — 通用 Word 底稿弹窗编辑器
 *
 * 适用于程序表关联的 docx 子底稿（A8-1 声明/A8-2 比对记录等），提供：
 * - 使用说明提示区（引导用户何时使用、注意事项）
 * - OnlyOffice 在线编辑（可用时）
 * - 降级预览（vue-office-docx）
 * - 下载模板到本地编辑
 * - 关联模块跳转链接
 */
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute } from 'vue-router'
import { api } from '@/services/apiProxy'
import { downloadFile } from '@/utils/http'
import OnlyOfficeEditor from '@/components/deliverable/OnlyOfficeEditor.vue'
import { ALL_DOCX_POPUP_CONFIGS, type DocxPopupConfig } from './wpPopupDocxConfigs'
import { useWorkpaperNavigation } from '@/composables/useWorkpaperNavigation'

const props = defineProps<{
  wpCode: string
  wpId?: string
  projectId?: string
}>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
}>()

const route = useRoute()
const { navigateToWorkpaper } = useWorkpaperNavigation()
const loading = ref(false)
const editorVisible = ref(false)
const onlyofficeAvailable = ref(false)
const documentUrl = ref('')
const documentKey = ref('')

const config = computed((): DocxPopupConfig | null => ALL_DOCX_POPUP_CONFIGS[props.wpCode] || null)

async function checkOnlyoffice() {
  try {
    const pid = props.projectId || (route.params.projectId as string)
    const res = await api.get(`/api/projects/${pid}/deliverables/onlyoffice/health`)
    onlyofficeAvailable.value = res?.available === true
  } catch {
    onlyofficeAvailable.value = false
  }
}

async function openEditor() {
  if (!config.value) return
  loading.value = true
  try {
    const pid = props.projectId || (route.params.projectId as string)
    // 查找该 wpCode 对应的独立底稿实例（非父底稿）
    // A8-1/A8-2 当前无独立实例，走模板下载
    // 未来若有独立实例，可通过 wp-index-resolve 接口查找
    if (props.wpId && config.value.templatePath.endsWith('.docx')) {
      try {
        const res = await api.get(`/api/projects/${pid}/working-papers/${props.wpId}/onlyoffice-config`)
        if (res?.document_url) {
          documentUrl.value = res.document_url
          documentKey.value = res.document_key
          editorVisible.value = true
          return
        }
      } catch {
        // 端点失败（底稿可能是 xlsx 非 docx），降级到模板下载
      }
    }
    downloadTemplate()
  } catch {
    ElMessage.warning('打开编辑器失败，请下载到本地编辑')
    downloadTemplate()
  } finally {
    loading.value = false
  }
}

function downloadTemplate() {
  if (!config.value) return
  const pid = props.projectId || (route.params.projectId as string)
  const wpCode = props.wpCode
  const url = `/api/projects/${pid}/wp-templates/${wpCode}/prefilled-download`
  const fileName = config.value.templatePath.split('/').pop() || 'template.docx'
  downloadFile(url, { fileName })
}

function onSaved() {
  ElMessage.success('文档已保存')
  emit('save')
  emit('completed')
}

function navigateToLink(_link: { label: string; routeName?: string; wpCode?: string }) {
  emit('save')
}

const signStatus = ref<'pending' | 'sent' | 'signed'>('pending')
const isA16Popup = computed(() => /^A16-\d/.test(props.wpCode))
const isA18_1Popup = computed(() => props.wpCode === 'A18-1')
const isB5Popup = computed(() => /^B5(-\d+)?$/.test(props.wpCode))
const b5Recommendation = ref<{ code: string; label: string; reason: string; confidence: string } | null>(null)
const summaryLoading = ref(false)
const summaryPreview = ref('')
const summaryCompleteness = ref(0)

/** 「完整编辑」→ 跳转页 + ?version=A16-x */
function goToFullEditor() {
  const pid = props.projectId || (route.params.projectId as string)
  navigateToWorkpaper(props.wpCode, pid)
}

async function generateA18Summary() {
  summaryLoading.value = true
  try {
    const pid = props.projectId || (route.params.projectId as string)
    const res = await api.get(`/api/projects/${pid}/a18/generate-summary`)
    const data = (res as any)?.data ?? res
    summaryPreview.value = data?.formatted_text || ''
    summaryCompleteness.value = Math.round((data?.completeness || 0) * 100)
    if (summaryPreview.value) {
      ElMessage.success(`已生成审计小结框架（完整度 ${summaryCompleteness.value}%）`)
    } else {
      ElMessage.info(data?.message || '暂无可用章节，请先填写 A17-1 关键章节')
    }
  } catch (err: any) {
    ElMessage.error('生成失败：' + (err?.message || '未知错误'))
  } finally {
    summaryLoading.value = false
  }
}

async function copySummaryPreview() {
  if (!summaryPreview.value) return
  try {
    await navigator.clipboard.writeText(summaryPreview.value)
    ElMessage.success('已复制到剪贴板，可粘贴至 A18-1 文档')
  } catch {
    ElMessage.warning('复制失败，请手动选择文本')
  }
}

async function loadSignStatus() {
  if (!isA16Popup.value || !props.wpId) return
  try {
    const res = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const list = Array.isArray(res) ? res : res?.data ?? []
    const row = list.find((r: any) => r.item_id === `${props.wpCode}-sign-status`)
    const st = row?.conclusion
    if (st === 'signed' || st === 'sent' || st === 'pending') signStatus.value = st
  } catch { /* ignore */ }
}

async function updateSignStatus(status: 'pending' | 'sent' | 'signed') {
  if (!props.wpId) return
  signStatus.value = status
  await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
    project_id: props.projectId || (route.params.projectId as string),
    items: [{ item_id: `${props.wpCode}-sign-status`, conclusion: status, remark: null }],
  })
  emit('save')
  if (status === 'signed') emit('completed')
}

async function loadB5Recommendation() {
  if (!isB5Popup.value) return
  try {
    const pid = props.projectId || (route.params.projectId as string)
    const res = await api.get(`/api/projects/${pid}/b5/recommended-version`)
    const data = (res as any)?.data ?? res
    if (data?.code) {
      b5Recommendation.value = data
    }
  } catch { /* ignore — endpoint may not exist yet */ }
}

onMounted(() => {
  checkOnlyoffice()
  loadSignStatus()
  loadB5Recommendation()
})
</script>

<template>
  <div class="wp-popup-docx-editor" v-if="config">
    <el-alert type="info" :closable="false" show-icon class="wp-popup-docx-editor__guidance">
      <template #title>
        <span class="guidance-title">📋 使用说明</span>
      </template>
      <div class="guidance-content">
        <ol>
          <li v-for="(item, idx) in config.guidance" :key="idx">{{ item }}</li>
        </ol>
        <el-tag type="warning" size="small" effect="plain" style="margin-top: 8px">
          适用条件：{{ config.applicableNote }}
        </el-tag>
      </div>
    </el-alert>
    <div class="wp-popup-docx-editor__toolbar">
      <el-button type="primary" size="small" @click="openEditor" :loading="loading">
        {{ onlyofficeAvailable ? '📝 在线编辑' : '📄 预览文档' }}
      </el-button>
      <el-button size="small" @click="downloadTemplate">⬇️ 下载模板</el-button>
      <el-tag v-if="isB5Popup && b5Recommendation" type="success" size="small" effect="light">
        推荐: {{ b5Recommendation.label }}（{{ b5Recommendation.code }}）
      </el-tag>
      <el-tag v-if="isA18_1Popup" size="small" type="info" effect="plain">
        下载含 A17 小结（如有）
      </el-tag>
      <el-button v-if="isA16Popup" size="small" type="success" @click="goToFullEditor">
        📖 完整编辑
      </el-button>
      <el-button
        v-if="isA18_1Popup"
        size="small"
        type="success"
        :loading="summaryLoading"
        @click="generateA18Summary"
      >
        📋 从 A17 生成小结框架
      </el-button>
      <el-button
        v-if="isA18_1Popup && summaryPreview"
        size="small"
        @click="copySummaryPreview"
      >
        📎 复制框架
      </el-button>
      <el-divider direction="vertical" />
      <template v-for="link in config.relatedLinks" :key="link.label">
        <el-button text size="small" type="primary" @click="navigateToLink(link)">
          🔗 {{ link.label }}
        </el-button>
      </template>
    </div>
    <el-alert
      v-if="isA18_1Popup && summaryPreview"
      type="success"
      :closable="false"
      class="wp-popup-docx-editor__summary-preview"
      :title="`A17 小结框架（完整度 ${summaryCompleteness}%）`"
    >
      <pre class="summary-preview-text">{{ summaryPreview }}</pre>
    </el-alert>
    <div v-if="isA16Popup" class="sign-row">
      <span class="sign-label">签回状态：</span>
      <el-radio-group v-model="signStatus" size="small" @change="updateSignStatus(signStatus)">
        <el-radio-button value="pending">待编辑</el-radio-button>
        <el-radio-button value="sent">已发送</el-radio-button>
        <el-radio-button value="signed">已签回</el-radio-button>
      </el-radio-group>
    </div>
    <OnlyOfficeEditor
      v-if="editorVisible"
      v-model:visible="editorVisible"
      :document-url="documentUrl"
      :document-key="documentKey"
      :title="config.title"
      mode="edit"
      @saved="onSaved"
      @close="editorVisible = false"
    />
  </div>
  <div v-else class="popup-empty">
    <p>未配置该文档类型（{{ wpCode }}）</p>
  </div>
</template>

<style scoped>
.wp-popup-docx-editor {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.wp-popup-docx-editor__guidance {
  margin-bottom: 8px;
}
.guidance-title {
  font-weight: 600;
  font-size: 14px;
}
.guidance-content ol {
  margin: 8px 0 0;
  padding-left: 20px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
}
.guidance-content ol li {
  margin-bottom: 4px;
}
.wp-popup-docx-editor__toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.popup-empty {
  padding: 24px;
  text-align: center;
  color: var(--el-text-color-secondary);
}
.sign-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.sign-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.wp-popup-docx-editor__summary-preview {
  margin-top: 4px;
}
.summary-preview-text {
  margin: 0;
  white-space: pre-wrap;
  font-size: 12px;
  line-height: 1.6;
  max-height: 240px;
  overflow-y: auto;
  font-family: inherit;
}
</style>
