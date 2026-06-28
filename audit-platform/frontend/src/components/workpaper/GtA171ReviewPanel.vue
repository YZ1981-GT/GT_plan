<!--
  GtA171ReviewPanel.vue — A17-1 章节复核批注面板
  独立组件：拖拽resize + 多轮对话 + 角色分发 + 完结确认 + 导入导出 + AI辅助
-->
<template>
  <transition name="gt-slide-right">
    <div v-if="visible" class="gt-review-panel" :style="{ width: panelWidth + 'px' }">
      <!-- Drag handle -->
      <div class="gt-review-panel__resize" @mousedown="startResize" />

      <!-- Header -->
      <div class="gt-review-panel__header">
        <span class="gt-review-panel__title">复核批注</span>
        <el-button text size="small" @click="emit('close')">✕</el-button>
      </div>

      <!-- Sub-header -->
      <div class="gt-review-panel__subheader">
        <span class="gt-review-panel__chapter">{{ chapterTitle }}</span>
        <div class="gt-review-panel__io">
          <el-button text size="small" @click="handleExport">📥 导出</el-button>
          <el-button text size="small" @click="triggerImport">📤 导入</el-button>
        </div>
      </div>
      <input ref="importInput" type="file" accept=".json" style="display:none" @change="handleImport" />

      <!-- Comment List -->
      <div class="gt-review-panel__list">
        <div v-if="!comments.length" class="gt-review-panel__empty">暂无批注</div>
        <div v-for="(c, ci) in comments" :key="ci" class="gt-review-panel__item" :class="{ 'is-resolved': c.resolved }">
          <div class="gt-review-panel__meta">
            <span class="gt-review-panel__author">{{ c.author || '匿名' }}</span>
            <span class="gt-review-panel__arrow">→</span>
            <span class="gt-review-panel__assignee">{{ c.assignee || '全员' }}</span>
            <span class="gt-review-panel__time">{{ fmtTime(c.createdAt) }}</span>
            <el-tag v-if="c.resolved" size="small" type="success" effect="plain">已完结</el-tag>
          </div>
          <div class="gt-review-panel__content">{{ c.content }}</div>

          <!-- Replies -->
          <div v-if="c.replies?.length" class="gt-review-panel__replies">
            <div v-for="(r, ri) in c.replies" :key="ri" class="gt-review-panel__reply">
              <span class="gt-review-panel__reply-author">{{ r.author || '匿名' }}</span>
              <span class="gt-review-panel__reply-time">{{ fmtTime(r.createdAt) }}</span>
              <div class="gt-review-panel__reply-content">{{ r.content }}</div>
            </div>
          </div>

          <!-- Actions -->
          <div v-if="!c.resolved" class="gt-review-panel__actions">
            <el-button text size="small" @click="startReply(ci)">💬 回复</el-button>
            <el-button text size="small" type="success" @click="handleFinish(ci)">✅ 完结</el-button>
          </div>

          <!-- Reply input -->
          <div v-if="replyingTo === ci" class="gt-review-panel__reply-input">
            <el-input v-model="replyText" type="textarea" :rows="2" placeholder="输入回复..." size="small" />
            <div class="gt-review-panel__reply-btns">
              <el-button size="small" @click="replyingTo = -1">取消</el-button>
              <el-button size="small" @click="handleAiReply(ci)">🤖 AI</el-button>
              <el-button size="small" type="primary" @click="submitReply(ci)">回复</el-button>
            </div>
          </div>
        </div>
      </div>

      <!-- New Comment -->
      <div class="gt-review-panel__new">
        <div class="gt-review-panel__new-row">
          <span class="gt-review-panel__new-label">发给：</span>
          <el-select v-model="newAssignee" size="small" placeholder="选择接收人" clearable style="flex:1">
            <el-option label="全员" value="" />
            <el-option label="编制人（审计助理）" value="审计助理" />
            <el-option label="现场经理" value="现场经理" />
            <el-option label="项目合伙人" value="业务合伙人" />
            <el-option label="质量控制复核合伙人" value="质量控制复核合伙人" />
            <el-option label="EQCR技术复核人" value="EQCR技术复核人" />
          </el-select>
        </div>
        <el-input v-model="newText" type="textarea" :rows="3" placeholder="输入复核意见..." size="small" />
        <div class="gt-review-panel__new-btns">
          <el-button size="small" type="primary" :disabled="!newText.trim()" @click="handleAdd">发起批注</el-button>
          <el-button size="small" @click="handleAiComment">🤖 AI 辅助</el-button>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { ref, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'

interface Reply { author?: string; content: string; createdAt?: string }
interface Comment { id?: string; author?: string; assignee?: string; content: string; createdAt?: string; resolved?: boolean; replies?: Reply[] }

const props = defineProps<{
  visible: boolean
  wpId: string
  chapterNum: number
  chapterTitle: string
  currentUser: string
}>()

const emit = defineEmits<{ (e: 'close'): void }>()

// ─── Panel Resize ───
const panelWidth = ref(380)
let _resizing = false
let _startX = 0
let _startW = 0

function startResize(e: MouseEvent) {
  _resizing = true
  _startX = e.clientX
  _startW = panelWidth.value
  document.addEventListener('mousemove', onResize)
  document.addEventListener('mouseup', stopResize)
}
function onResize(e: MouseEvent) {
  if (!_resizing) return
  const diff = _startX - e.clientX
  panelWidth.value = Math.max(280, Math.min(700, _startW + diff))
}
function stopResize() {
  _resizing = false
  document.removeEventListener('mousemove', onResize)
  document.removeEventListener('mouseup', stopResize)
}
onBeforeUnmount(stopResize)

// ─── Comments State ───
const comments = ref<Comment[]>([])
const newText = ref('')
const newAssignee = ref('')
const replyingTo = ref(-1)
const replyText = ref('')
const importInput = ref<HTMLInputElement | null>(null)

// ─── Load ───
async function loadComments() {
  try {
    const objectId = `a171-ch${props.chapterNum}`
    const res = await api.get<any>(`/api/workpapers/${props.wpId}/comments?object_id=${objectId}`, { _silent: true } as any)
    const items = Array.isArray(res) ? res : res?.items || []
    comments.value = items.map((c: any) => ({
      id: c.id, author: c.author_name || c.author || '匿名', assignee: c.assignee || '',
      content: c.content, createdAt: c.created_at, resolved: c.resolved || false,
      replies: (c.replies || []).map((r: any) => ({ author: r.author_name || r.author || '匿名', content: r.content, createdAt: r.created_at })),
    }))
  } catch { comments.value = [] }
}

// ─── Add Comment ───
async function handleAdd() {
  const content = newText.value.trim()
  if (!content) return
  const now = new Date().toISOString()
  comments.value.push({ author: props.currentUser, assignee: newAssignee.value, content, createdAt: now, resolved: false, replies: [] })
  newText.value = ''
  try {
    await api.post(`/api/workpapers/${props.wpId}/comments`, { object_id: `a171-ch${props.chapterNum}`, content, assignee: newAssignee.value })
    loadComments()
  } catch { /* optimistic */ }
}

// ─── Reply ───
function startReply(ci: number) { replyingTo.value = ci; replyText.value = '' }

async function submitReply(ci: number) {
  const content = replyText.value.trim()
  if (!content || !comments.value[ci]) return
  if (!comments.value[ci].replies) comments.value[ci].replies = []
  comments.value[ci].replies!.push({ author: props.currentUser, content, createdAt: new Date().toISOString() })
  replyText.value = ''; replyingTo.value = -1
  try {
    const commentId = comments.value[ci].id
    if (commentId) await api.post(`/api/workpapers/${props.wpId}/comments/${commentId}/replies`, { content })
  } catch { /* optimistic */ }
}

// ─── Finish ───
async function handleFinish(ci: number) {
  try {
    await ElMessageBox.confirm('是否将此批注对话计入正式复核记录？\n计入后将在复核底稿中留痕。', '完结确认', {
      type: 'info', confirmButtonText: '计入记录并完结', cancelButtonText: '仅完结不计入', distinguishCancelAndClose: true,
    })
    comments.value[ci].resolved = true
    // TODO: POST mark as resolved + include_in_record=true
  } catch (action: any) {
    if (action === 'cancel') {
      comments.value[ci].resolved = true
      // TODO: POST mark as resolved + include_in_record=false
    }
  }
}

// ─── AI ───
async function handleAiComment() {
  try {
    const res = await api.post<any>(`/api/workpapers/${props.wpId}/a171/ai-generate`, {
      chapter: props.chapterNum, chapter_title: `复核意见：${props.chapterTitle}`,
      guidance: '请从复核人视角，针对本章节内容提出需要关注的问题或改进建议。语气专业客观。', existing_content: '', knowledge_doc_ids: [],
    }, { _silent: true } as any)
    if (res?.content) { newText.value = res.content; ElMessage.success('AI 已生成复核意见') }
    else ElMessage.info('AI 未生成有效内容')
  } catch { ElMessage.warning('AI 生成失败') }
}

async function handleAiReply(ci: number) {
  const original = comments.value[ci]?.content || ''
  try {
    const res = await api.post<any>(`/api/workpapers/${props.wpId}/a171/ai-generate`, {
      chapter: props.chapterNum, chapter_title: `回复复核意见`,
      guidance: `针对以下复核意见生成回复：\n"${original}"\n\n请从编制人视角回复，说明已采纳/已修改/不同意的理由。`, existing_content: '', knowledge_doc_ids: [],
    }, { _silent: true } as any)
    if (res?.content) { replyText.value = res.content; ElMessage.success('AI 已生成回复') }
  } catch { ElMessage.warning('AI 生成失败') }
}

// ─── Export / Import ───
function handleExport() {
  const data = JSON.stringify({ chapter: props.chapterNum, comments: comments.value }, null, 2)
  const blob = new Blob([data], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = `a171-ch${props.chapterNum}-review.json`; a.click()
  URL.revokeObjectURL(url)
}

function triggerImport() { importInput.value?.click() }

function handleImport(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    try {
      const data = JSON.parse(reader.result as string)
      if (Array.isArray(data.comments)) {
        comments.value.push(...data.comments)
        ElMessage.success(`已导入 ${data.comments.length} 条批注`)
      }
    } catch { ElMessage.error('导入失败：格式无效') }
  }
  reader.readAsText(file)
  ;(e.target as HTMLInputElement).value = ''
}

// ─── Helpers ───
function fmtTime(time?: string): string {
  if (!time) return ''
  try {
    const v = /[zZ]|[+-]\d{2}:?\d{2}$/.test(time) ? time : time + 'Z'
    const d = new Date(v)
    return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
  } catch { return time }
}

// Auto-load on visible
import { watch } from 'vue'
watch(() => props.visible, (v) => { if (v) loadComments() }, { immediate: true })
</script>

<style scoped>
.gt-review-panel { position: fixed; top: 0; right: 0; bottom: 0; z-index: 2000; background: #fff; box-shadow: -4px 0 16px rgba(0,0,0,0.1); display: flex; flex-direction: column; font-size: 13px; }
.gt-review-panel__resize { position: absolute; left: 0; top: 0; bottom: 0; width: 5px; cursor: col-resize; }
.gt-review-panel__resize:hover { background: var(--gt-color-primary, #6b21a8); opacity: 0.3; }
.gt-review-panel__header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid #ebeef5; }
.gt-review-panel__title { font-size: 14px; font-weight: 600; color: var(--gt-color-primary, #6b21a8); }
.gt-review-panel__subheader { display: flex; align-items: center; justify-content: space-between; padding: 8px 16px; background: #fafafa; }
.gt-review-panel__chapter { font-size: 13px; font-weight: 500; color: #303133; }
.gt-review-panel__io { display: flex; gap: 4px; }
.gt-review-panel__list { flex: 1; overflow-y: auto; padding: 12px 16px; }
.gt-review-panel__empty { color: #909399; text-align: center; padding: 24px 0; }
.gt-review-panel__item { border: 1px solid #ebeef5; border-radius: 6px; padding: 10px 12px; margin-bottom: 10px; }
.gt-review-panel__item.is-resolved { opacity: 0.6; background: #f5f7fa; }
.gt-review-panel__meta { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #909399; margin-bottom: 6px; }
.gt-review-panel__author { font-weight: 500; color: #303133; }
.gt-review-panel__arrow { color: #c0c4cc; }
.gt-review-panel__content { line-height: 1.6; color: #303133; }
.gt-review-panel__replies { margin-top: 8px; padding-left: 12px; border-left: 2px solid #e4e7ed; }
.gt-review-panel__reply { margin-bottom: 6px; }
.gt-review-panel__reply-author { font-size: 12px; font-weight: 500; color: #606266; }
.gt-review-panel__reply-time { font-size: 11px; color: #c0c4cc; margin-left: 6px; }
.gt-review-panel__reply-content { font-size: 13px; color: #303133; margin-top: 2px; }
.gt-review-panel__actions { display: flex; gap: 8px; margin-top: 8px; }
.gt-review-panel__reply-input { margin-top: 8px; }
.gt-review-panel__reply-btns { display: flex; gap: 6px; margin-top: 6px; justify-content: flex-end; }
.gt-review-panel__new { padding: 12px 16px; border-top: 1px solid #ebeef5; }
.gt-review-panel__new-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.gt-review-panel__new-label { font-size: 13px; color: #606266; white-space: nowrap; }
.gt-review-panel__new-btns { display: flex; gap: 8px; margin-top: 8px; }
.gt-slide-right-enter-active, .gt-slide-right-leave-active { transition: transform 0.25s ease; }
.gt-slide-right-enter-from, .gt-slide-right-leave-to { transform: translateX(100%); }
</style>
