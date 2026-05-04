<template>
  <el-dialog append-to-body
    v-model="visible"
    :title="fileName"
    width="80%"
    top="5vh"
    destroy-on-close
    @close="$emit('close')"
  >
    <div class="gt-preview-body" v-loading="loading">
      <!-- Word 预览 -->
      <vue-office-docx
        v-if="isDocx && previewSrc"
        :src="previewSrc"
        @rendered="onRendered"
        @error="onError"
        class="gt-preview-content"
      />

      <!-- Excel 预览 -->
      <vue-office-excel
        v-else-if="isExcel && previewSrc"
        :src="previewSrc"
        @rendered="onRendered"
        @error="onError"
        class="gt-preview-content"
      />

      <!-- PDF 预览 -->
      <vue-office-pdf
        v-else-if="isPdf && previewSrc"
        :src="previewSrc"
        @rendered="onRendered"
        @error="onError"
        class="gt-preview-content"
      />

      <!-- 图片预览 -->
      <el-image
        v-else-if="isImage && previewSrc"
        :src="previewSrc"
        fit="contain"
        class="gt-preview-image"
        @load="loading = false"
      />

      <div v-else-if="loading" class="gt-preview-loading-placeholder" />

      <!-- 不支持的格式 -->
      <el-empty v-else description="暂不支持预览此格式，请下载后查看" :image-size="80">
        <el-button type="primary" @click="download">下载文件</el-button>
      </el-empty>
    </div>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button @click="download">下载</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
// vue-office 组件（需要安装 @vue-office/docx @vue-office/excel @vue-office/pdf）
// 如果未安装，这些 import 会报错，但不影响其他组件
import VueOfficeDocx from '@vue-office/docx'
import VueOfficeExcel from '@vue-office/excel'
import VueOfficePdf from '@vue-office/pdf'
import '@vue-office/docx/lib/index.css'
import '@vue-office/excel/lib/index.css'
import { api } from '@/services/apiProxy'
import { downloadFile } from '@/utils/http'

const props = defineProps<{
  modelValue: boolean
  fileUrl: string
  fileName: string
  fileType?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'close'): void
}>()

const loading = ref(true)
const previewSrc = ref('')

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const normalizedFileType = computed(() => (props.fileType || '').toLowerCase())

const ext = computed(() => {
  if (normalizedFileType.value && !['word', 'excel', 'image'].includes(normalizedFileType.value)) {
    return normalizedFileType.value
  }
  const name = props.fileName || ''
  const dot = name.lastIndexOf('.')
  return dot >= 0 ? name.slice(dot + 1).toLowerCase() : ''
})

const isDocx = computed(() => normalizedFileType.value === 'word' || ['docx', 'doc'].includes(ext.value))
const isExcel = computed(() => normalizedFileType.value === 'excel' || ['xlsx', 'xls', 'csv'].includes(ext.value))
const isPdf = computed(() => normalizedFileType.value === 'pdf' || ext.value === 'pdf')
const isImage = computed(() => normalizedFileType.value === 'image' || ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'].includes(ext.value))
const isPreviewable = computed(() => isDocx.value || isExcel.value || isPdf.value || isImage.value)

function revokePreviewSrc() {
  if (previewSrc.value) {
    window.URL.revokeObjectURL(previewSrc.value)
    previewSrc.value = ''
  }
}

async function loadPreview() {
  if (!visible.value || !props.fileUrl || !isPreviewable.value) {
    loading.value = false
    revokePreviewSrc()
    return
  }

  loading.value = true
  revokePreviewSrc()
  try {
    const blob = await api.get(props.fileUrl, { responseType: 'blob' })
    previewSrc.value = window.URL.createObjectURL(blob as Blob)
  } catch {
    loading.value = false
  }
}

function onRendered() { loading.value = false }
function onError() { loading.value = false }

async function download() {
  const downloadUrl = props.fileUrl.replace('/preview', '/download')
  await downloadFile(downloadUrl)
}

watch(
  () => [props.modelValue, props.fileUrl, props.fileName, props.fileType],
  async () => {
    if (props.modelValue) {
      await loadPreview()
    } else {
      loading.value = true
      revokePreviewSrc()
    }
  },
  { immediate: true },
)

onUnmounted(() => {
  revokePreviewSrc()
})
</script>

<style scoped>
.gt-preview-body {
  min-height: 400px;
  max-height: 70vh;
  overflow: auto;
}
.gt-preview-content {
  width: 100%;
  min-height: 400px;
}
.gt-preview-image {
  max-width: 100%;
  max-height: 60vh;
  display: block;
  margin: 0 auto;
}
.gt-preview-loading-placeholder {
  min-height: 400px;
}
</style>
