<template>
  <div class="gt-review-conv gt-fade-in">
    <div class="gt-page-header">
      <h2 class="gt-page-title">复核对话</h2>
      <div class="gt-header-actions">
        <el-radio-group v-model="statusFilter" size="default" @change="fetchConversations">
          <el-radio-button label="">全部</el-radio-button>
          <el-radio-button label="open">进行中</el-radio-button>
          <el-radio-button label="closed">已关闭</el-radio-button>
        </el-radio-group>
        <el-button type="primary" @click="showCreateDialog = true">发起对话</el-button>
      </div>
    </div>

    <div class="gt-conv-layout">
      <!-- 左侧对话列表 -->
      <div class="gt-conv-list">
        <el-card v-for="conv in conversations" :key="conv.id"
          :class="['gt-conv-card', { active: selectedId === conv.id }]"
          shadow="hover" @click="selectConversation(conv)">
          <div class="gt-conv-title">{{ conv.title }}</div>
          <div class="gt-conv-meta">
            <el-tag :type="conv.status === 'open' ? 'success' : 'info'" size="small">
              {{ conv.status === 'open' ? '进行中' : '已关闭' }}
            </el-tag>
            <span class="gt-conv-count">{{ conv.message_count || 0 }} 条消息</span>
            <span class="gt-conv-time">{{ conv.created_at?.slice(0, 16) }}</span>
          </div>
        </el-card>
        <el-empty v-if="conversations.length === 0" description="暂无复核对话" />
      </div>

      <!-- 右侧消息区 -->
      <div class="gt-conv-messages" v-if="selectedId">
        <div class="gt-msg-header">
          <span>{{ selectedConv?.title }}</span>
          <div>
            <el-button size="small" @click="onExport">导出</el-button>
            <el-button size="small" type="danger" @click="onClose"
              v-if="selectedConv?.status === 'open'">结束对话</el-button>
          </div>
        </div>
        <div class="gt-msg-list" ref="msgListRef">
          <div v-for="msg in messages" :key="msg.id" class="gt-msg-item">
            <div class="gt-msg-sender">{{ msg.sender_id?.slice(0, 8) }}</div>
            <div class="gt-msg-content">{{ msg.content }}</div>
            <div class="gt-msg-time">{{ msg.created_at?.slice(11, 16) }}</div>
          </div>
        </div>
        <div class="gt-msg-input" v-if="selectedConv?.status === 'open'">
          <el-input v-model="newMessage" placeholder="输入消息..." @keyup.enter="onSend" />
          <el-button type="primary" @click="onSend" :disabled="!newMessage.trim()">发送</el-button>
        </div>
      </div>
      <div class="gt-conv-empty" v-else>
        <el-empty description="选择一个对话查看消息" />
      </div>
    </div>

    <!-- 创建对话弹窗 -->
    <el-dialog v-model="showCreateDialog" title="发起复核对话" width="480px">
      <el-form label-width="80px">
        <el-form-item label="标题"><el-input v-model="createForm.title" /></el-form-item>
        <el-form-item label="对象类型">
          <el-select v-model="createForm.related_object_type">
            <el-option label="底稿" value="workpaper" />
            <el-option label="附注" value="disclosure_note" />
            <el-option label="审计报告" value="audit_report" />
          </el-select>
        </el-form-item>
        <el-form-item label="单元格"><el-input v-model="createForm.cell_ref" placeholder="如 E9-1!B15" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="onCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  listConversations, getMessages, sendMessage, closeConversation,
  exportConversation, createConversation, type ConversationItem,
} from '@/services/phase10Api'

const route = useRoute()
const projectId = ref(route.params.projectId as string || '')

const statusFilter = ref('')
const conversations = ref<ConversationItem[]>([])
const selectedId = ref('')
const selectedConv = ref<ConversationItem | null>(null)
const messages = ref<any[]>([])
const newMessage = ref('')
const showCreateDialog = ref(false)
const msgListRef = ref<HTMLElement>()
const createForm = ref({ title: '', related_object_type: 'workpaper', cell_ref: '' })

async function fetchConversations() {
  if (!projectId.value) return
  conversations.value = await listConversations(projectId.value, statusFilter.value || undefined)
}

async function selectConversation(conv: ConversationItem) {
  selectedId.value = conv.id
  selectedConv.value = conv
  messages.value = await getMessages(conv.id)
  await nextTick()
  if (msgListRef.value) msgListRef.value.scrollTop = msgListRef.value.scrollHeight
}

async function onSend() {
  if (!newMessage.value.trim() || !selectedId.value) return
  await sendMessage(selectedId.value, { content: newMessage.value })
  newMessage.value = ''
  messages.value = await getMessages(selectedId.value)
  await nextTick()
  if (msgListRef.value) msgListRef.value.scrollTop = msgListRef.value.scrollHeight
}

async function onClose() {
  try {
    await closeConversation(selectedId.value)
    ElMessage.success('对话已关闭')
    await fetchConversations()
  } catch (e: any) { ElMessage.error(e?.response?.data?.detail || '关闭失败') }
}

async function onExport() {
  const data = await exportConversation(selectedId.value)
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = `conversation_${selectedId.value}.json`; a.click()
}

async function onCreate() {
  if (!createForm.value.title) return ElMessage.warning('请输入标题')
  await createConversation(projectId.value, {
    target_id: '00000000-0000-0000-0000-000000000000',
    ...createForm.value,
  })
  showCreateDialog.value = false
  ElMessage.success('对话已创建')
  await fetchConversations()
}

onMounted(fetchConversations)
</script>

<style scoped>
.gt-review-conv { padding: var(--gt-space-4); height: 100%; }
.gt-page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-3); }
.gt-header-actions { display: flex; gap: var(--gt-space-2); }
.gt-conv-layout { display: flex; gap: var(--gt-space-3); height: calc(100vh - 180px); }
.gt-conv-list { width: 340px; overflow-y: auto; display: flex; flex-direction: column; gap: var(--gt-space-2); }
.gt-conv-card { cursor: pointer; }
.gt-conv-card.active { border-color: var(--gt-color-primary); }
.gt-conv-title { font-weight: 600; margin-bottom: 4px; }
.gt-conv-meta { display: flex; align-items: center; gap: var(--gt-space-2); font-size: var(--gt-font-size-sm); color: var(--gt-color-text-secondary); }
.gt-conv-messages { flex: 1; display: flex; flex-direction: column; border: 1px solid var(--el-border-color); border-radius: var(--gt-radius-md); }
.gt-conv-empty { flex: 1; display: flex; align-items: center; justify-content: center; }
.gt-msg-header { padding: var(--gt-space-2) var(--gt-space-3); border-bottom: 1px solid var(--el-border-color); display: flex; justify-content: space-between; align-items: center; font-weight: 600; }
.gt-msg-list { flex: 1; overflow-y: auto; padding: var(--gt-space-3); display: flex; flex-direction: column; gap: var(--gt-space-2); }
.gt-msg-item { padding: var(--gt-space-2); background: var(--el-fill-color-light); border-radius: var(--gt-radius-sm); }
.gt-msg-sender { font-size: var(--gt-font-size-sm); color: var(--gt-color-primary); font-weight: 600; }
.gt-msg-content { margin: 4px 0; }
.gt-msg-time { font-size: 11px; color: var(--gt-color-text-secondary); text-align: right; }
.gt-msg-input { padding: var(--gt-space-2) var(--gt-space-3); border-top: 1px solid var(--el-border-color); display: flex; gap: var(--gt-space-2); }
</style>
