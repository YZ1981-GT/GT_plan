<template>
  <el-dialog
    v-model="visible"
    title="📋 OCR 识别结果确认"
    width="90%"
    :close-on-click-modal="false"
    class="gt-ocr-confirm-dialog"
    destroy-on-close
    @closed="onClosed"
  >
    <div class="gt-ocr-layout">
      <!-- 左侧：原件预览 -->
      <div class="gt-ocr-left">
        <div class="gt-ocr-section-title">
          <span class="gt-ocr-section-icon">📄</span> 原件预览
        </div>
        <div class="gt-ocr-preview-area">
          <img
            v-if="isImage"
            :src="previewSrc"
            class="gt-ocr-preview-img"
            alt="原件"
          />
          <iframe
            v-else-if="isPdf"
            :src="previewSrc"
            class="gt-ocr-preview-iframe"
            frameborder="0"
          />
          <div v-else class="gt-ocr-preview-fallback">
            <div class="gt-ocr-preview-fallback-icon">{{ fileEmoji }}</div>
            <div class="gt-ocr-preview-fallback-name">{{ fileName }}</div>
            <div class="gt-ocr-preview-fallback-hint">此文件类型暂不支持预览，请参考右侧识别结果</div>
          </div>
        </div>
      </div>

      <!-- 中间分隔线 -->
      <div class="gt-ocr-divider">
        <div class="gt-ocr-divider-line"></div>
        <div class="gt-ocr-divider-icon">⇄</div>
        <div class="gt-ocr-divider-line"></div>
      </div>

      <!-- 右侧：识别结果（可编辑） -->
      <div class="gt-ocr-right">
        <div class="gt-ocr-section-title">
          <span class="gt-ocr-section-icon">✏️</span> 识别结果
          <el-tag size="small" type="warning" effect="plain" style="margin-left: 8px">可编辑</el-tag>
        </div>
        <div class="gt-ocr-edit-area">
          <el-input
            v-model="editedText"
            type="textarea"
            :autosize="{ minRows: 12, maxRows: 30 }"
            placeholder="OCR 识别内容将在此显示..."
            class="gt-ocr-textarea"
          />
        </div>

        <!-- 置信度提示 -->
        <div v-if="confidence != null" class="gt-ocr-confidence">
          <span>识别置信度：</span>
          <el-progress
            :percentage="Math.round(confidence * 100)"
            :stroke-width="8"
            :color="confidence > 0.9 ? '#67C23A' : confidence > 0.7 ? '#E6A23C' : '#F56C6C'"
            style="width: 120px; display: inline-flex"
          />
          <span class="gt-ocr-confidence-val">{{ (confidence * 100).toFixed(1) }}%</span>
        </div>

        <!-- 警告提示 -->
        <el-alert
          v-if="confidence != null && confidence < 0.8"
          title="识别置信度较低，请仔细核对原件内容"
          type="warning"
          :closable="false"
          show-icon
          style="margin-top: 12px"
        />
      </div>
    </div>

    <template #footer>
      <div class="gt-ocr-footer">
        <div class="gt-ocr-footer-left">
          <el-checkbox v-model="skipNextTime">下次自动入库（跳过确认）</el-checkbox>
        </div>
        <div class="gt-ocr-footer-right">
          <el-button @click="onReject">放弃识别</el-button>
          <el-button type="primary" @click="onConfirm" :loading="saving">
            <el-icon><Check /></el-icon> 确认入库
          </el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Check } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { attachments as P_att } from '@/services/apiPaths'

export interface OcrConfirmPayload {
  attachmentId: string
  fileName: string
  fileType: string
  previewUrl: string
  ocrText: string
  confidence?: number
}

const props = defineProps<{
  modelValue: boolean
  payload: OcrConfirmPayload | null
}>()

const emit = defineEmits<{
  'update:modelValue': [val: boolean]
  'confirmed': [payload: { attachmentId: string; text: string }]
  'rejected': [attachmentId: string]
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const editedText = ref('')
const saving = ref(false)
const skipNextTime = ref(false)

// 当 payload 变化时初始化
watch(() => props.payload, (p) => {
  if (p) {
    editedText.value = p.ocrText || ''
  }
}, { immediate: true })

const fileName = computed(() => props.payload?.fileName || '未知文件')
const previewSrc = computed(() => props.payload?.previewUrl || '')
const confidence = computed(() => props.payload?.confidence ?? null)

const isImage = computed(() => {
  const t = (props.payload?.fileType || '').toLowerCase()
  return ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'].some(ext => t.includes(ext))
})

const isPdf = computed(() => {
  const t = (props.payload?.fileType || '').toLowerCase()
  return t.includes('pdf')
})

const fileEmoji = computed(() => {
  const t = (props.payload?.fileType || '').toLowerCase()
  if (t.includes('doc') || t.includes('word')) return '📘'
  if (t.includes('xls') || t.includes('excel')) return '📗'
  return '📄'
})

async function onConfirm() {
  if (!props.payload) return
  saving.value = true
  try {
    await api.put(P_att.ocrStatus(props.payload.attachmentId), {
      status: 'completed',
      ocr_text: editedText.value,
    })
    ElMessage.success('识别结果已确认入库')
    emit('confirmed', { attachmentId: props.payload.attachmentId, text: editedText.value })
    visible.value = false
  } catch (e: any) {
    ElMessage.error('入库失败：' + (e?.message || '未知错误'))
  } finally {
    saving.value = false
  }
}

function onReject() {
  if (props.payload) {
    emit('rejected', props.payload.attachmentId)
  }
  visible.value = false
}

function onClosed() {
  editedText.value = ''
}
</script>

<style scoped>
.gt-ocr-layout {
  display: flex;
  gap: 0;
  min-height: 500px;
  max-height: 70vh;
}

/* 左侧预览 */
.gt-ocr-left {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.gt-ocr-section-title {
  display: flex;
  align-items: center;
  font-size: 14px;
  font-weight: 600;
  color: var(--gt-color-text-primary);
  margin-bottom: 12px;
}

.gt-ocr-section-icon {
  margin-right: 6px;
  font-size: 16px;
}

.gt-ocr-preview-area {
  flex: 1;
  border: 1px solid var(--gt-color-border-light, #eee);
  border-radius: 10px;
  overflow: hidden;
  background: #f8f8fa;
  display: flex;
  align-items: center;
  justify-content: center;
}

.gt-ocr-preview-img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  animation: gt-ocr-fadein 0.4s ease;
}

.gt-ocr-preview-iframe {
  width: 100%;
  height: 100%;
  min-height: 460px;
}

.gt-ocr-preview-fallback {
  text-align: center;
  padding: 40px 20px;
  color: var(--gt-color-text-tertiary);
}

.gt-ocr-preview-fallback-icon {
  font-size: 48px;
  margin-bottom: 12px;
  animation: gt-float 3s ease-in-out infinite;
}

.gt-ocr-preview-fallback-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--gt-color-text-secondary);
  margin-bottom: 6px;
}

.gt-ocr-preview-fallback-hint {
  font-size: 12px;
}

/* 中间分隔线 */
.gt-ocr-divider {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 0 16px;
}

.gt-ocr-divider-line {
  width: 1px;
  flex: 1;
  background: linear-gradient(to bottom, transparent, var(--gt-purple-light, #d8b8ee), transparent);
}

.gt-ocr-divider-icon {
  padding: 8px 0;
  font-size: 18px;
  color: var(--gt-purple, #4b2d77);
  animation: gt-ocr-pulse 2s ease-in-out infinite;
}

/* 右侧编辑 */
.gt-ocr-right {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.gt-ocr-edit-area {
  flex: 1;
}

.gt-ocr-textarea :deep(.el-textarea__inner) {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 13px;
  line-height: 1.7;
  border-radius: 10px;
  padding: 14px 16px;
  background: var(--gt-color-bg-white, #fff);
  border-color: var(--gt-color-border-light, #ddd);
  transition: border-color 0.2s, box-shadow 0.2s;
}

.gt-ocr-textarea :deep(.el-textarea__inner:focus) {
  border-color: var(--gt-purple, #4b2d77);
  box-shadow: 0 0 0 3px rgba(75, 45, 119, 0.08);
}

/* 置信度 */
.gt-ocr-confidence {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  font-size: 12px;
  color: var(--gt-color-text-secondary);
}

.gt-ocr-confidence-val {
  font-weight: 700;
  min-width: 42px;
}

/* Footer */
.gt-ocr-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.gt-ocr-footer-left {
  font-size: 13px;
  color: var(--gt-color-text-secondary);
}

.gt-ocr-footer-right {
  display: flex;
  gap: 8px;
}

/* 动画 */
@keyframes gt-ocr-fadein {
  from { opacity: 0; transform: scale(0.96); }
  to { opacity: 1; transform: scale(1); }
}

@keyframes gt-ocr-pulse {
  0%, 100% { opacity: 1; transform: translateX(0); }
  50% { opacity: 0.6; transform: translateX(2px); }
}

@keyframes gt-float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-6px); }
}

/* 响应式 */
@media (max-width: 768px) {
  .gt-ocr-layout { flex-direction: column; }
  .gt-ocr-divider { flex-direction: row; padding: 12px 0; }
  .gt-ocr-divider-line { height: 1px; width: auto; flex: 1; background: linear-gradient(to right, transparent, var(--gt-purple-light, #d8b8ee), transparent); }
}
</style>
