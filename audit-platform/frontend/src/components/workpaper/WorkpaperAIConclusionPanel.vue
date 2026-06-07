<template>
  <div class="ai-conclusion-panel">
    <!-- 结论区域标题 -->
    <div class="ai-conclusion-header">
      <h4 class="ai-conclusion-title">{{ sheetLabel }} 科目结论</h4>
      <el-tag v-if="draftStatus === 'pending'" type="warning" size="small">
        🤖 AI 草稿待确认
      </el-tag>
      <el-tag v-else-if="draftStatus === 'confirmed'" type="success" size="small">
        ✅ 已确认
      </el-tag>
      <el-tag v-else-if="draftStatus === 'revised'" type="success" size="small">
        ✏️ 已修订确认
      </el-tag>
      <el-tag v-else-if="draftStatus === 'rejected'" type="info" size="small">
        ❌ 已拒绝
      </el-tag>
    </div>

    <!-- 不可生成提示：目标绑定不完整或上下文 missing -->
    <div v-if="cannotGenerate" class="ai-conclusion-blocked">
      <el-alert
        type="warning"
        :closable="false"
        show-icon
      >
        <template #title>无法生成 AI 草稿</template>
        <template #default>
          <p>{{ cannotGenerateReason }}</p>
          <ul v-if="missingItems.length > 0" class="missing-list">
            <li v-for="(item, idx) in missingItems" :key="idx">
              <strong>[{{ item.source }}]</strong> {{ item.impact }}
            </li>
          </ul>
        </template>
      </el-alert>
    </div>

    <!-- 生成按钮 -->
    <div v-if="!cannotGenerate && draftStatus !== 'pending'" class="ai-conclusion-actions">
      <el-button
        type="primary"
        :loading="generating"
        @click="onGenerate"
      >
        🤖 生成 AI 草稿
      </el-button>
    </div>

    <!-- AI 草稿展示区 -->
    <div v-if="draft" class="ai-conclusion-draft">
      <!-- 来源摘要 -->
      <div v-if="sourceSummary" class="ai-conclusion-sources">
        <span class="sources-label">引用来源：</span>
        <el-tag
          v-for="src in sourceSummary.sources"
          :key="src.type"
          size="small"
          type="info"
          class="source-tag"
        >
          {{ src.label }}
        </el-tag>
      </div>

      <!-- Missing 项展示 -->
      <div v-if="missingItems.length > 0" class="ai-conclusion-missing">
        <el-alert type="info" :closable="false" show-icon>
          <template #title>缺失资料提示</template>
          <template #default>
            <ul class="missing-list">
              <li v-for="(item, idx) in missingItems" :key="idx">
                <strong>[{{ item.source }}]</strong> {{ item.reason }}：{{ item.impact }}
              </li>
            </ul>
          </template>
        </el-alert>
      </div>

      <!-- 草稿内容 -->
      <div class="ai-conclusion-content">
        <div class="draft-content-text">{{ draft.generated_content }}</div>
      </div>

      <!-- 确认/修订/拒绝 按钮 -->
      <div v-if="draftStatus === 'pending'" class="ai-conclusion-confirm-actions">
        <el-button type="success" @click="onConfirm">✅ 确认采纳</el-button>
        <el-button type="warning" @click="showReviseDialog = true">✏️ 修订确认</el-button>
        <el-button type="danger" @click="showRejectDialog = true">❌ 拒绝</el-button>
      </div>
    </div>

    <!-- 修订对话框 -->
    <el-dialog
      v-model="showReviseDialog"
      title="修订 AI 草稿"
      width="520px"
      :close-on-click-modal="false"
    >
      <el-input
        v-model="revisedContent"
        type="textarea"
        :rows="6"
        placeholder="请输入修订后的内容..."
      />
      <template #footer>
        <el-button @click="showReviseDialog = false">取消</el-button>
        <el-button type="primary" @click="onReviseConfirm">确认修订</el-button>
      </template>
    </el-dialog>

    <!-- 拒绝对话框 -->
    <el-dialog
      v-model="showRejectDialog"
      title="拒绝 AI 草稿"
      width="420px"
      :close-on-click-modal="false"
    >
      <el-input
        v-model="rejectReason"
        type="textarea"
        :rows="3"
        placeholder="请填写拒绝原因..."
      />
      <template #footer>
        <el-button @click="showRejectDialog = false">取消</el-button>
        <el-button type="danger" :disabled="!rejectReason.trim()" @click="onReject">
          确认拒绝
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'

export interface AIDraft {
  log_id: string
  generated_content: string
  confirm_action: string
  target_binding: {
    account_package_id: string
    wp_id: string
    sheet_type: string
    field_id: string
  }
  source_summary: {
    wp_code: string
    conclusion_sheet: string
    sources: Array<{ type: string; label: string; available: boolean }>
    source_count: number
  }
  missing: Array<{ source: string; reason: string; impact: string }>
}

const props = defineProps<{
  sheetLabel: string
  accountPackageId: string
  wpId: string
  fieldId: string
  projectId: string
  draft?: AIDraft | null
  generating?: boolean
  cannotGenerate?: boolean
  cannotGenerateReason?: string
}>()

const emit = defineEmits<{
  (e: 'generate'): void
  (e: 'confirm', logId: string): void
  (e: 'revise', logId: string, revisedContent: string): void
  (e: 'reject', logId: string, reason: string): void
}>()

const showReviseDialog = ref(false)
const showRejectDialog = ref(false)
const revisedContent = ref('')
const rejectReason = ref('')

const draftStatus = computed(() => props.draft?.confirm_action || null)

const sourceSummary = computed(() => props.draft?.source_summary || null)

const missingItems = computed(() => props.draft?.missing || [])

function onGenerate() {
  emit('generate')
}

function onConfirm() {
  if (!props.draft) return
  emit('confirm', props.draft.log_id)
}

function onReviseConfirm() {
  if (!props.draft || !revisedContent.value.trim()) {
    ElMessage.warning('请输入修订内容')
    return
  }
  emit('revise', props.draft.log_id, revisedContent.value.trim())
  showReviseDialog.value = false
  revisedContent.value = ''
}

function onReject() {
  if (!props.draft || !rejectReason.value.trim()) {
    ElMessage.warning('请填写拒绝原因')
    return
  }
  emit('reject', props.draft.log_id, rejectReason.value.trim())
  showRejectDialog.value = false
  rejectReason.value = ''
}
</script>

<style scoped>
.ai-conclusion-panel {
  border: 1px solid var(--gt-color-border-purple-light, #d8b8ee);
  border-radius: 8px;
  padding: 16px;
  background: var(--gt-color-primary-bg, #f4f0fa);
}

.ai-conclusion-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.ai-conclusion-title {
  margin: 0;
  font-size: 15px;
  color: var(--gt-color-text-primary, #303133);
}

.ai-conclusion-blocked {
  margin-bottom: 12px;
}

.ai-conclusion-actions {
  margin-bottom: 12px;
}

.ai-conclusion-sources {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.sources-label {
  font-size: 13px;
  color: var(--gt-color-text-secondary, #909399);
}

.source-tag {
  cursor: pointer;
}

.ai-conclusion-missing {
  margin-bottom: 10px;
}

.missing-list {
  margin: 4px 0 0;
  padding-left: 18px;
  font-size: 13px;
}

.ai-conclusion-content {
  margin-bottom: 12px;
}

.draft-content-text {
  background: #fff;
  border: 1px dashed var(--gt-color-primary, #4b2d77);
  border-radius: 6px;
  padding: 12px;
  font-size: 14px;
  color: var(--gt-color-text-regular, #606266);
  white-space: pre-wrap;
  max-height: 300px;
  overflow-y: auto;
}

.ai-conclusion-confirm-actions {
  display: flex;
  gap: 8px;
}
</style>
