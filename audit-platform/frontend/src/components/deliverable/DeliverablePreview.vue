<template>
  <el-dialog v-model="visible" :title="title" width="80%" top="5vh" @close="emit('close')">
    <div v-loading="loading" class="deliverable-preview">
      <DraftWatermark :visible="showWatermark" />
      <el-alert
        v-if="officeLoadError && isOfficePreview"
        type="error"
        :closable="false"
        title="预览组件加载失败"
        description="请下载文件查看"
      />
      <VueOfficeDocx
        v-else-if="previewType === 'docx' && url"
        :src="url"
        :request-options="authRequestOptions"
        style="height: 70vh"
        @rendered="loading = false"
        @error="onError"
      />
      <VueOfficePdf
        v-else-if="previewType === 'pdf' && url"
        :src="url"
        :request-options="authRequestOptions"
        style="height: 70vh"
        @rendered="loading = false"
        @error="onError"
      />
      <VueOfficeExcel
        v-else-if="previewType === 'xlsx' && url"
        :src="url"
        :request-options="authRequestOptions"
        style="height: 70vh"
        @rendered="loading = false"
        @error="onError"
      />
      <div v-else-if="previewType === 'html' && htmlContent" class="deliverable-preview__html" v-html="htmlContent" />
      <el-alert
        v-else
        type="info"
        :closable="false"
        title="该格式不支持在线预览"
        description="请使用下载按钮获取文件"
      />
    </div>
    <template #footer>
      <el-button v-if="url" type="primary" :loading="downloading" @click="onDownload">下载</el-button>
      <el-button @click="emit('close')">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, defineAsyncComponent, defineComponent, watch } from 'vue'
import DraftWatermark from './DraftWatermark.vue'
import '@vue-office/docx/lib/index.css'
import '@vue-office/excel/lib/index.css'
import { useAuthStore } from '@/stores/auth'
import { downloadFile } from '@/utils/http'
import { handleApiError } from '@/utils/errorHandler'

// 任一客户端 Office 预览首次命中时加载共享重块；失败重试一次，再显示中文下载降级。
const officeLoadError = ref(false)
const OfficePreviewUnavailable = defineComponent({ name: 'OfficePreviewUnavailable', render: () => null })
function lazyOffice(loader: () => Promise<any>) {
  return defineAsyncComponent(async () => {
    try {
      return await loader()
    } catch {
      try {
        return await loader()
      } catch {
        officeLoadError.value = true
        loading.value = false
        return OfficePreviewUnavailable
      }
    }
  })
}
const VueOfficeDocx = lazyOffice(() => import('@vue-office/docx'))
const VueOfficePdf = lazyOffice(() => import('@vue-office/pdf'))
const VueOfficeExcel = lazyOffice(() => import('@vue-office/excel'))

const props = defineProps<{
  title: string
  previewType: 'docx' | 'pdf' | 'xlsx' | 'html' | 'unsupported'
  url?: string
  htmlContent?: string
  showWatermark?: boolean
}>()

const emit = defineEmits<{ close: [] }>()

const visible = ref(true)
const loading = ref(true)
const authStore = useAuthStore()
const isOfficePreview = computed(() => ['docx', 'pdf', 'xlsx'].includes(props.previewType))

// @vue-office/docx 和 @vue-office/pdf 通过 requestOptions 传递 auth header
const authRequestOptions = computed(() => ({
  headers: {
    Authorization: `Bearer ${authStore.token}`,
  },
}))

watch(() => [props.previewType, props.url] as const, () => {
  officeLoadError.value = false
  // Office 需有 URL 且等 @rendered 才取消 loading；同类型换 URL 也重新显示加载态。
  loading.value = isOfficePreview.value && !!props.url
}, { immediate: true })

function onError() {
  loading.value = false
}

// 原先 <el-button :href target="_blank">：el-button 渲染的是 <button>，href 不生效，点了没反应；
// 即便改成链接，新标签页也带不上 Bearer 头（恒 401）。经 http 取 blob 再保存。
const downloading = ref(false)
async function onDownload() {
  if (!props.url) return
  downloading.value = true
  try {
    await downloadFile(props.url, { silent: true })
  } catch (e) {
    handleApiError(e, '下载')
  } finally {
    downloading.value = false
  }
}
</script>

<style scoped>
.deliverable-preview {
  position: relative;
  min-height: 200px;
}
.deliverable-preview__html {
  max-height: 70vh;
  overflow: auto;
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
}
</style>
