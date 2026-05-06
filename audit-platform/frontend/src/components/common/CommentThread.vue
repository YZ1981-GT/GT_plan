<template>
  <div class="gt-comment-thread">
    <!-- 批注列表 -->
    <div class="gt-ct-list" v-if="comments.length">
      <div
        v-for="(comment, idx) in comments"
        :key="comment.id || idx"
        class="gt-ct-item"
        :class="{ 'gt-ct-item--resolved': comment.resolved }"
      >
        <div class="gt-ct-header">
          <span class="gt-ct-author">{{ comment.author || '匿名' }}</span>
          <span class="gt-ct-time">{{ formatTime(comment.createdAt) }}</span>
          <el-tag v-if="comment.resolved" size="small" type="success" effect="plain">已解决</el-tag>
        </div>
        <div class="gt-ct-content">{{ comment.content }}</div>

        <!-- 回复链 -->
        <div v-if="comment.replies?.length" class="gt-ct-replies">
          <div v-for="(reply, ri) in comment.replies" :key="ri" class="gt-ct-reply">
            <span class="gt-ct-reply-author">{{ reply.author || '匿名' }}</span>
            <span class="gt-ct-reply-time">{{ formatTime(reply.createdAt) }}</span>
            <div class="gt-ct-reply-content">{{ reply.content }}</div>
          </div>
        </div>

        <!-- 回复输入 -->
        <div v-if="replyingTo === idx" class="gt-ct-reply-input">
          <el-input
            v-model="replyText"
            type="textarea"
            :rows="2"
            placeholder="输入回复..."
            size="small"
          />
          <div class="gt-ct-reply-actions">
            <el-button size="small" @click="replyingTo = -1">取消</el-button>
            <el-button size="small" type="primary" @click="submitReply(idx)">回复</el-button>
          </div>
        </div>

        <!-- 操作按钮 -->
        <div class="gt-ct-actions" v-if="replyingTo !== idx">
          <el-button text size="small" @click="replyingTo = idx; replyText = ''">💬 回复</el-button>
          <el-button
            v-if="!comment.resolved"
            text size="small"
            @click="$emit('resolve', idx)"
          >✅ 标记解决</el-button>
          <el-button text size="small" type="danger" @click="$emit('delete', idx)">🗑️ 删除</el-button>
        </div>
      </div>
    </div>

    <el-empty v-else description="暂无批注" :image-size="40" />

    <!-- 新增批注 -->
    <div class="gt-ct-new">
      <el-input
        v-model="newComment"
        type="textarea"
        :rows="2"
        placeholder="添加批注..."
        size="small"
      />
      <el-button
        size="small"
        type="primary"
        :disabled="!newComment.trim()"
        @click="submitNew"
        style="margin-top: 6px"
      >添加批注</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * CommentThread — 批注线程组件（回复链）[R10.7]
 *
 * 支持：
 * - 批注列表展示
 * - 回复链（嵌套回复）
 * - 标记已解决
 * - 新增批注
 */
import { ref } from 'vue'

export interface CommentReply {
  author?: string
  content: string
  createdAt?: string
}

export interface CommentItem {
  id?: string
  author?: string
  content: string
  createdAt?: string
  resolved?: boolean
  replies?: CommentReply[]
}

defineProps<{
  comments: CommentItem[]
  currentUser?: string
}>()

const emit = defineEmits<{
  (e: 'add', content: string): void
  (e: 'reply', commentIndex: number, content: string): void
  (e: 'resolve', commentIndex: number): void
  (e: 'delete', commentIndex: number): void
}>()

const newComment = ref('')
const replyingTo = ref(-1)
const replyText = ref('')

function submitNew() {
  if (!newComment.value.trim()) return
  emit('add', newComment.value.trim())
  newComment.value = ''
}

function submitReply(commentIndex: number) {
  if (!replyText.value.trim()) return
  emit('reply', commentIndex, replyText.value.trim())
  replyText.value = ''
  replyingTo.value = -1
}

function formatTime(time?: string): string {
  if (!time) return ''
  try {
    const d = new Date(time)
    return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
  } catch {
    return time
  }
}
</script>

<style scoped>
.gt-comment-thread {
  padding: 8px;
  max-height: 400px;
  overflow-y: auto;
}

.gt-ct-item {
  padding: 8px;
  border-bottom: 1px solid #f0f0f0;
}

.gt-ct-item--resolved {
  opacity: 0.6;
}

.gt-ct-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.gt-ct-author {
  font-weight: 600;
  font-size: 12px;
  color: #4b2d77;
}

.gt-ct-time {
  font-size: 11px;
  color: #999;
}

.gt-ct-content {
  font-size: 13px;
  line-height: 1.5;
  color: #333;
}

.gt-ct-replies {
  margin-left: 16px;
  margin-top: 6px;
  border-left: 2px solid #e8e0f0;
  padding-left: 8px;
}

.gt-ct-reply {
  margin-bottom: 6px;
}

.gt-ct-reply-author {
  font-weight: 600;
  font-size: 11px;
  color: #666;
}

.gt-ct-reply-time {
  font-size: 10px;
  color: #bbb;
  margin-left: 6px;
}

.gt-ct-reply-content {
  font-size: 12px;
  color: #555;
  margin-top: 2px;
}

.gt-ct-reply-input {
  margin-top: 6px;
}

.gt-ct-reply-actions {
  display: flex;
  gap: 6px;
  margin-top: 4px;
  justify-content: flex-end;
}

.gt-ct-actions {
  display: flex;
  gap: 4px;
  margin-top: 4px;
}

.gt-ct-new {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #f0f0f0;
}
</style>
