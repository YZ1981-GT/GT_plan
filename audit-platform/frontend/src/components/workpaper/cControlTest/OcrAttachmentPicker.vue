<!--
  OcrAttachmentPicker.vue — C 循环控制测试 AI 生成前的附件 OCR 上下文选择器

  职责：
  - AI 生成前弹出 el-dialog，列出当前底稿关联附件
  - 用户勾选可 OCR 识别的附件（PDF/图片），确认后：
    1. 逐个下载附件 blob（GET /api/attachments/{id}/download，responseType=blob）
    2. 命中 ocrCache（prop，父组件维护）则跳过 HTTP，否则调用 OCR 端点识别
    3. 拼接所有成功文本并截断到 3000 字符，emit confirm({ ocrText, failedIds })
  - 不可识别格式的附件 checkbox 禁用 + tooltip "仅支持 PDF/图片"
  - 无附件时显示"暂无附件"空状态

  数据来源（复用真实端点，走 http/axios 携带 Authorization）：
  - 附件列表：useOcrAttachmentCache.loadAttachments → GET /api/working-papers/{wpId}/attachments
  - 附件下载：GET /api/attachments/{id}/download（responseType=blob）
  - OCR 识别：useOcrAttachmentCache.runOcr → POST /api/workpapers/{wpId}/d4/contract-ocr

  Spec: .kiro/specs/c-control-test-popup-enhance/
  Task: 8.1
  Requirements: 4.1, 4.2, 4.3, 4.4, 4.6, 5.1, 5.4
-->
<template>
  <el-dialog
    v-model="dialogVisible"
    title="选择参考附件（OCR 识别）"
    width="520px"
    append-to-body
    :close-on-click-modal="false"
    class="ocr-attachment-picker"
    @open="handleOpen"
  >
    <!-- 空状态：无附件 -->
    <div v-if="attachmentListLoaded && attachmentList.length === 0" class="ocr-picker__empty">
      <el-empty description="暂无附件" :image-size="80" />
    </div>

    <!-- 附件勾选列表 -->
    <div v-else class="ocr-picker__list">
      <p class="ocr-picker__hint">
        勾选需纳入 AI 上下文的附件，系统将对其执行 OCR 识别（仅支持 PDF / 图片）。
      </p>
      <el-checkbox-group v-model="selectedIds">
        <div v-for="att in attachmentList" :key="att.id" class="ocr-picker__row">
          <el-tooltip
            v-if="!att.ocrEligible"
            content="仅支持 PDF/图片"
            placement="top"
            :show-after="200"
          >
            <span class="ocr-picker__row-wrap">
              <el-checkbox :value="att.id" disabled>
                <span class="ocr-picker__filename">{{ att.file_name }}</span>
              </el-checkbox>
            </span>
          </el-tooltip>
          <el-checkbox v-else :value="att.id">
            <span class="ocr-picker__filename">{{ att.file_name }}</span>
            <el-tag size="small" type="success" effect="light" class="ocr-picker__tag">可OCR</el-tag>
          </el-checkbox>
        </div>
      </el-checkbox-group>
    </div>

    <template #footer>
      <el-button @click="handleCancel">取消</el-button>
      <el-button
        type="primary"
        :loading="confirming"
        :disabled="attachmentList.length === 0"
        @click="handleConfirm"
      >
        {{ confirming ? 'OCR 识别中…' : '确认' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { useOcrAttachmentCache, truncateOcrText } from '@/composables/useOcrAttachmentCache'

// ─── Props / Emits ────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  /** v-model:visible 控制显隐 */
  visible: boolean
  /** 已缓存的 OCR 结果（attachment_id → text），由父组件维护并作为共享缓存 */
  ocrCache: Map<string, string>
}>()

const emit = defineEmits<{
  (e: 'update:visible', val: boolean): void
  (e: 'confirm', payload: { ocrText: string; failedIds: string[] }): void
  (e: 'cancel'): void
}>()

// OCR 文本拼接/截断规则见 useOcrAttachmentCache.truncateOcrText（design §7）

// ─── Composable（内部实例，负责列表加载 + OCR 识别） ──────────────────────────────

const { attachmentList, attachmentListLoaded, loadAttachments, runOcr, resetListCache } =
  useOcrAttachmentCache()

// ─── 本地状态 ──────────────────────────────────────────────────────────────────

const selectedIds = ref<string[]>([])
const confirming = ref(false)

const dialogVisible = computed<boolean>({
  get: () => props.visible,
  set: (val) => emit('update:visible', val),
})

// ─── 行为 ──────────────────────────────────────────────────────────────────────

/**
 * dialog 打开时加载附件列表并重置勾选。
 * 每次打开为新的选择会话：先清列表缓存再重新拉取，确保上传的新附件即时可见（Req 6.4）。
 */
async function handleOpen(): Promise<void> {
  selectedIds.value = []
  resetListCache()
  await loadAttachments(props.wpId)
}

/**
 * 下载附件二进制 blob（供 OCR 端点识别）。
 * responseType=blob 时 http 拦截器不解包，直接返回 AxiosResponse，data 即 Blob。
 */
async function downloadAttachmentBlob(attachmentId: string): Promise<Blob> {
  const res = await http.get(`/api/attachments/${attachmentId}/download`, {
    responseType: 'blob',
    _silent: true,
  } as any)
  return res.data as Blob
}

/**
 * 确认：对选中且可 OCR 的附件执行识别，命中缓存跳过 HTTP。
 * 拼接成功文本并截断，收集失败 ID，emit confirm 后关闭。
 */
async function handleConfirm(): Promise<void> {
  confirming.value = true
  const texts: string[] = []
  const failedIds: string[] = []
  try {
    // 仅处理选中且可识别的附件
    const targets = attachmentList.value.filter(
      (a) => selectedIds.value.includes(a.id) && a.ocrEligible,
    )
    for (const att of targets) {
      try {
        // 优先命中父组件共享缓存（prop ocrCache），避免重复 OCR
        if (props.ocrCache.has(att.id)) {
          const cached = props.ocrCache.get(att.id) ?? ''
          if (cached) texts.push(cached)
          continue
        }
        // 未缓存：下载 blob → OCR 识别 → 写回共享缓存
        const blob = await downloadAttachmentBlob(att.id)
        const text = await runOcr(props.wpId, att.id, blob)
        props.ocrCache.set(att.id, text)
        if (text) texts.push(text)
      } catch {
        // 单个附件失败：跳过并收集 ID，不阻塞其余附件
        failedIds.push(att.id)
      }
    }

    if (failedIds.length > 0) {
      const names = attachmentList.value
        .filter((a) => failedIds.includes(a.id))
        .map((a) => a.file_name)
        .join('、')
      ElMessage.warning(`以下附件 OCR 识别失败，已跳过：${names}`)
    }

    const ocrText = truncateOcrText(texts)
    emit('confirm', { ocrText, failedIds })
    dialogVisible.value = false
  } finally {
    confirming.value = false
  }
}

/** 取消：emit cancel 并关闭 */
function handleCancel(): void {
  emit('cancel')
  dialogVisible.value = false
}
</script>

<style scoped>
.ocr-picker__hint {
  margin: 0 0 12px;
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
}
.ocr-picker__list {
  max-height: 360px;
  overflow-y: auto;
}
.ocr-picker__row {
  padding: 6px 0;
  border-bottom: 1px solid #f0f0f0;
}
.ocr-picker__row:last-child {
  border-bottom: none;
}
.ocr-picker__row-wrap {
  display: inline-flex;
  align-items: center;
}
.ocr-picker__filename {
  font-size: 13px;
  vertical-align: middle;
}
.ocr-picker__tag {
  margin-left: 8px;
}
.ocr-picker__empty {
  padding: 12px 0;
}
</style>
