<template>
  <el-dialog
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
        v-if="isDocx"
        :src="fileUrl"
        @rendered="onRendered"
        @error="onError"
        class="gt-preview-content"
      />

      <!-- Excel 预览 -->
      <vue-office-excel
        v-else-if="isExcel"
        :src="fileUrl"
        @rendered="onRendered"
        @error="onError"
        class="gt-preview-content"
      />

      <!-- PDF 预览 -->
      <vue-office-pdf
        v-else-if="isPdf"
        :src="fileUrl"
        @rendered="onRendered"
        @error="onError"
        class="gt-preview-content"
      />

      <!-- 图片预览 -->
      <el-image
        v-else-if="isImage"
        :src="fileUrl"
        fit="contain"
        class="gt-preview-image"
        @load="loading = false"
      />

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
import { computed, ref } from 'vue'
// vue-office 组件（需要安装 @vue-office/docx @vue-office/excel @vue-office/pdf）
// 如果未安装，这些 import 会报错，但不影响其他组件
import VueOfficeDocx from '@vue-office/docx'
import VueOfficeExcel from '@vue-office/excel'
import VueOfficePdf from '@vue-office/pdf'
import '@vue-office/docx/lib/index.css'
import '@vue-office/excel/lib/index.css'

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

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const ext = computed(() => {
  if (props.fileType) return props.fileType.toLowerCase()
  const name = props.fileName || ''
  const dot = name.lastIndexOf('.')
  return dot >= 0 ? name.slice(dot + 1).toLowerCase() : ''
})

const isDocx = computed(() => ['docx', 'doc'].includes(ext.value))
const isExcel = computed(() => ['xlsx', 'xls', 'csv'].includes(ext.value))
const isPdf = computed(() => ext.value === 'pdf')
const isImage = computed(() => ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'].includes(ext.value))

function onRendered() { loading.value = false }
function onError() { loading.value = false }

function download() {
  // 使用下载代理端点（preview URL 替换为 download URL）
  const downloadUrl = props.fileUrl.replace('/preview', '/download')
  window.open(downloadUrl, '_blank')
}
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
</style>
