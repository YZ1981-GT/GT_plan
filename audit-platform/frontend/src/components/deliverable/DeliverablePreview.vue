<template>
  <el-dialog v-model="visible" :title="title" width="80%" top="5vh" @close="emit('close')">
    <div v-loading="loading" class="deliverable-preview">
      <DraftWatermark :visible="showWatermark" />
      <VueOfficeDocx
        v-if="previewType === 'docx' && url"
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
      <el-button v-if="url" type="primary" :href="url" target="_blank">下载</el-button>
      <el-button @click="emit('close')">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import DraftWatermark from './DraftWatermark.vue'
import VueOfficeDocx from '@vue-office/docx'
import VueOfficePdf from '@vue-office/pdf'
import '@vue-office/docx/lib/index.css'
import { useAuthStore } from '@/stores/auth'

const props = defineProps<{
  title: string
  previewType: 'docx' | 'pdf' | 'html' | 'unsupported'
  url?: string
  htmlContent?: string
  showWatermark?: boolean
}>()

const emit = defineEmits<{ close: [] }>()

const visible = ref(true)
const loading = ref(true)
const authStore = useAuthStore()

// @vue-office/docx 和 @vue-office/pdf 通过 requestOptions 传递 auth header
const authRequestOptions = computed(() => ({
  headers: {
    Authorization: `Bearer ${authStore.token}`,
  },
}))

watch(() => props.previewType, () => {
  // docx/pdf 需等 @rendered 事件才取消 loading；html 和 unsupported 立即取消
  loading.value = (props.previewType === 'docx' || props.previewType === 'pdf')
}, { immediate: true })

function onError() {
  loading.value = false
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
