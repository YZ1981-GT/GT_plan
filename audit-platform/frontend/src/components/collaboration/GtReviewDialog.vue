<template>
  <!-- 4.1 面板布局: el-drawer 400px 右侧滑入 -->
  <el-drawer
    v-model="isOpen"
    :size="400"
    direction="rtl"
    :before-close="handleClose"
    :show-close="false"
    class="review-dialog-drawer"
  >
    <!-- 顶部标题栏 -->
    <template #header>
      <div class="drawer-header">
        <template v-if="isMultiSelectMode">
          <span class="header-title">选择消息</span>
          <div class="header-actions">
            <el-button link @click="selectAll">全选</el-button>
            <el-button link @click="exitSelectMode">取消</el-button>
          </div>
        </template>
        <template v-else>
          <span class="header-title">{{ dialogTitle }}</span>
          <el-button :icon="Close" circle size="small" @click="handleClose" />
        </template>
      </div>
    </template>

    <!-- 上下文摘要卡片 -->
    <div v-if="props.relatedData && !isMultiSelectMode" class="context-card">
      <div v-if="props.relatedData.cellLabel" class="context-item">
        <span class="context-label">{{ props.relatedData.cellLabel }}：</span>
        <span class="context-value">{{ props.relatedData.cellValue }}</span>
        <span v-if="props.relatedData.priorValue" class="context-prior">
          （上期：{{ props.relatedData.priorValue }}）
        </span>
      </div>
      <div v-else-if="props.relatedData.wpTitle" class="context-item">
        <span class="context-label">{{ props.relatedData.wpTitle }}</span>
      </div>
      <div v-if="props.relatedData.selectedText" class="context-item context-quote">
        "{{ props.relatedData.selectedText }}"
      </div>
    </div>

    <!-- 消息列表（可滚动） -->
    <div ref="messageListRef" class="message-list">
      <div v-if="isLoading" class="message-loading">加载中...</div>
      <div v-else-if="messages.length === 0" class="message-empty">暂无消息，发送第一条吧</div>
      <div
        v-for="msg in messages"
        :key="msg.id || msg._tempId"
        class="message-row"
        :class="{ 'is-self': msg.sender_id === props.currentUser.id }"
      >
        <!-- 4.3 多选模式：左侧圆形选择框 -->
        <div
          v-if="isMultiSelectMode"
          class="select-checkbox"
          :class="{ selected: selectedIds.has(msg.id) }"
          @click="toggleSelect(msg.id)"
        >
          <span v-if="selectedIds.has(msg.id)">✓</span>
        </div>

        <!-- 4.2 消息气泡渲染 -->
        <div class="bubble-wrapper" @click="isMultiSelectMode && toggleSelect(msg.id)">
          <!-- 头像 -->
          <div
            v-if="msg.sender_id !== props.currentUser.id"
            class="avatar"
            :class="getRoleColorClass(msg.sender_role)"
          >
            {{ msg.sender_name?.charAt(0) || '?' }}
          </div>

          <div class="bubble-content">
            <!-- 发送者名称+角色 -->
            <div v-if="msg.sender_id !== props.currentUser.id" class="sender-info">
              <span class="sender-name">{{ msg.sender_name }}</span>
              <span class="role-badge">{{ msg.sender_role }}</span>
            </div>
            <!-- 气泡 -->
            <div
              class="bubble"
              :class="msg.sender_id === props.currentUser.id ? 'bubble-self' : 'bubble-other'"
            >
              {{ msg.content }}
            </div>
            <!-- 时间 + 失败状态 -->
            <div class="bubble-meta">
              <span class="msg-time">{{ formatTime(msg.created_at) }}</span>
              <!-- 4.2 失败状态：红色❗+ 重发 -->
              <span v-if="msg._status === 'failed'" class="msg-failed">
                <span class="failed-icon">❗</span>
                <el-button link size="small" class="retry-btn" @click.stop="retryMessage(msg._tempId!)">
                  重发
                </el-button>
              </span>
              <span v-else-if="msg._status === 'sending'" class="msg-sending">发送中...</span>
            </div>
          </div>

          <!-- 自己的头像在右侧 -->
          <div
            v-if="msg.sender_id === props.currentUser.id"
            class="avatar"
            :class="getRoleColorClass(msg.sender_role)"
          >
            {{ msg.sender_name?.charAt(0) || '?' }}
          </div>
        </div>
      </div>
      <!-- 用于自动滚动的锚点 -->
      <div ref="scrollAnchorRef" />
    </div>

    <!-- 4.3 多选模式底部栏 -->
    <div v-if="isMultiSelectMode" class="multiselect-footer">
      <span class="selected-count">已选 {{ selectedCount }} 条</span>
      <el-button type="primary" :disabled="!canExport" @click="exportSelected">导出</el-button>
    </div>

    <!-- 底部输入区（非多选 + 有写权限） -->
    <div v-if="canWrite && !isMultiSelectMode" class="input-area">
      <el-input
        v-model="inputText"
        type="textarea"
        :rows="3"
        placeholder="输入消息..."
        resize="none"
        @keydown="handleKeydown"
      />
      <el-button type="primary" :disabled="!inputText.trim()" @click="handleSend">发送</el-button>
    </div>
  </el-drawer>

  <!-- 4.4 关闭确认弹窗 -->
  <el-dialog v-model="isCloseConfirmOpen" width="400" title="关闭对话" :close-on-click-modal="false">
    <p>当前对话有消息记录，确定要关闭吗？</p>
    <template #footer>
      <el-button @click="confirmClose">关闭对话</el-button>
      <el-button type="primary" @click="confirmContinue">继续对话</el-button>
      <el-button type="success" @click="confirmExport">导出到复核记录</el-button>
    </template>
  </el-dialog>

  <!-- 4.5 导出编辑弹窗 -->
  <el-dialog v-model="isExportDialogOpen" width="600" title="编辑导出内容" :close-on-click-modal="false">
    <el-input v-model="exportText" type="textarea" :rows="10" placeholder="编辑导出内容..." />
    <template #footer>
      <el-button @click="aiPolish" :loading="isAiPolishing">🤖 AI润色</el-button>
      <el-button @click="isExportDialogOpen = false">取消</el-button>
      <el-button type="primary" @click="saveToReviewRecord" :disabled="!exportText.trim()">
        保存到复核记录
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, onMounted } from 'vue'
import { Close } from '@element-plus/icons-vue'
import { useReviewDialog, type GtReviewDialogProps } from '@/composables/useReviewDialog'

const props = defineProps<GtReviewDialogProps>()

// ── Composable ──────────────────────────────────────────────────────────────
const {
  isOpen,
  isLoading,
  dialogTitle,
  messages,
  isMultiSelectMode,
  selectedIds,
  selectedCount,
  canExport,
  isExportDialogOpen,
  exportText,
  isAiPolishing,
  canWrite,
  isCloseConfirmOpen,
  openDialog,
  sendMessage,
  retryMessage,
  enterSelectMode,
  exitSelectMode,
  toggleSelect,
  selectAll,
  exportSelected,
  aiPolish,
  saveToReviewRecord,
  handleClose,
  confirmClose,
  confirmContinue,
  confirmExport,
} = useReviewDialog(props)

// ── Local state ─────────────────────────────────────────────────────────────
const inputText = ref('')
const messageListRef = ref<HTMLElement | null>(null)
const scrollAnchorRef = ref<HTMLElement | null>(null)

// ── 4.6 键盘交互: Enter 发送 / Shift+Enter 换行 ────────────────────────────
function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
  // Shift+Enter 默认行为即换行，无需处理
}

async function handleSend() {
  const text = inputText.value.trim()
  if (!text) return
  inputText.value = ''
  await sendMessage(text)
}

// ── 4.6 新消息自动滚动底部 ──────────────────────────────────────────────────
watch(
  () => messages.value.length,
  () => {
    nextTick(() => {
      scrollAnchorRef.value?.scrollIntoView({ behavior: 'smooth' })
    })
  },
)

// ── Helpers ─────────────────────────────────────────────────────────────────
function formatTime(isoStr: string): string {
  const d = new Date(isoStr)
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${hh}:${mm}`
}

function getRoleColorClass(role: string): string {
  const map: Record<string, string> = {
    '审计助理': 'avatar-assistant',
    '现场经理': 'avatar-manager',
    '业务合伙人': 'avatar-partner',
    '质量控制复核合伙人': 'avatar-qc',
    'EQCR技术复核人': 'avatar-eqcr',
  }
  return map[role] || 'avatar-default'
}

// ── Mount: auto open ────────────────────────────────────────────────────────
onMounted(() => {
  openDialog()
})
</script>

<style scoped>
.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}
.header-title {
  font-size: 16px;
  font-weight: 600;
}
.header-actions {
  display: flex;
  gap: 8px;
}

/* 上下文摘要卡片 */
.context-card {
  background: #e8f4fd;
  border-radius: 8px;
  padding: 10px 12px;
  margin: 0 0 12px;
  font-size: 13px;
  color: #333;
}
.context-item {
  margin-bottom: 4px;
}
.context-item:last-child {
  margin-bottom: 0;
}
.context-label {
  font-weight: 500;
}
.context-value {
  color: #1a73e8;
}
.context-prior {
  color: #888;
  font-size: 12px;
}
.context-quote {
  font-style: italic;
  color: #555;
  border-left: 3px solid #90caf9;
  padding-left: 8px;
  margin-top: 6px;
}

/* 消息列表 */
.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 12px 0;
}
.message-loading,
.message-empty {
  text-align: center;
  color: #999;
  padding: 40px 0;
  font-size: 14px;
}

/* 消息行 */
.message-row {
  display: flex;
  align-items: flex-start;
  margin-bottom: 16px;
  padding: 0 4px;
}
.message-row.is-self .bubble-wrapper {
  flex-direction: row-reverse;
}

.bubble-wrapper {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  flex: 1;
}

/* 头像 */
.avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  flex-shrink: 0;
}
.avatar-assistant { background: #409eff; }
.avatar-manager { background: #67c23a; }
.avatar-partner { background: #e6a23c; }
.avatar-qc { background: #909399; }
.avatar-eqcr { background: #f56c6c; }
.avatar-default { background: #c0c4cc; }

/* 气泡内容区 */
.bubble-content {
  max-width: 260px;
  display: flex;
  flex-direction: column;
}
.message-row.is-self .bubble-content {
  align-items: flex-end;
}

.sender-info {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}
.sender-name {
  font-size: 12px;
  color: #666;
  font-weight: 500;
}
.role-badge {
  font-size: 10px;
  color: #999;
  background: #f0f0f0;
  padding: 1px 6px;
  border-radius: 4px;
}

/* 气泡 */
.bubble {
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.5;
  word-break: break-word;
  white-space: pre-wrap;
}
.bubble-self {
  background: #d9fdd3;
  border-top-right-radius: 4px;
}
.bubble-other {
  background: #fff;
  border: 1px solid #e8e8e8;
  border-top-left-radius: 4px;
}

/* 时间+状态 */
.bubble-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
}
.msg-time {
  font-size: 11px;
  color: #aaa;
}
.msg-sending {
  font-size: 11px;
  color: #999;
}
.msg-failed {
  display: flex;
  align-items: center;
  gap: 2px;
}
.failed-icon {
  color: #f56c6c;
  font-size: 14px;
}
.retry-btn {
  font-size: 11px;
  color: #f56c6c !important;
}

/* 多选复选框 */
.select-checkbox {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: 2px solid #dcdfe6;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
  margin-top: 8px;
  margin-right: 8px;
  transition: all 0.2s;
}
.select-checkbox.selected {
  background: #409eff;
  border-color: #409eff;
  color: #fff;
  font-size: 12px;
  font-weight: bold;
}

/* 多选底部栏 */
.multiselect-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-top: 1px solid #ebeef5;
  background: #fafafa;
}
.selected-count {
  font-size: 14px;
  color: #606266;
}

/* 输入区 */
.input-area {
  padding: 12px;
  border-top: 1px solid #ebeef5;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.input-area .el-button {
  align-self: flex-end;
}
</style>
