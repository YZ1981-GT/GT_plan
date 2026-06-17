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
import OnlyOfficeEditor from '@/components/deliverable/OnlyOfficeEditor.vue'
import { DOCX_POPUP_CONFIGS, type DocxPopupConfig } from './wpPopupDocxConfigs'

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
const loading = ref(false)
const editorVisible = ref(false)
const onlyofficeAvailable = ref(false)
const documentUrl = ref('')
const documentKey = ref('')

const config = computed((): DocxPopupConfig | null => DOCX_POPUP_CONFIGS[props.wpCode] || null)

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
  // 提取 wp_code（从 templatePath 中推导，如 "wp_templates/A/A10-1 xxx.docx" → "A10-1"）
  const wpCode = props.wpCode
  // 调用预填充下载端点（自动替换公司名/年度等占位符）
  const url = `/api/projects/${pid}/wp-templates/${wpCode}/prefilled-download`
  const a = document.createElement('a')
  a.href = url
  a.download = config.value.templatePath.split('/').pop() || 'template.docx'
  a.click()
}

function onSaved() {
  ElMessage.success('文档已保存')
  emit('save')
  emit('completed')
}

function navigateToLink(_link: { label: string; routeName?: string; wpCode?: string }) {
  emit('save')
}

onMounted(() => {
  checkOnlyoffice()
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
      <el-divider direction="vertical" />
      <template v-for="link in config.relatedLinks" :key="link.label">
        <el-button text size="small" type="primary" @click="navigateToLink(link)">
          🔗 {{ link.label }}
        </el-button>
      </template>
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
</style>
