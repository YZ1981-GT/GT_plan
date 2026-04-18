<template>
  <div class="gt-forum gt-fade-in">
    <div class="gt-page-header">
      <h2 class="gt-page-title">吐槽与求助</h2>
      <el-button type="primary" @click="showCreate = true">发帖</el-button>
    </div>

    <el-radio-group v-model="category" @change="fetchPosts" style="margin-bottom: var(--gt-space-3)">
      <el-radio-button label="">全部</el-radio-button>
      <el-radio-button label="vent">吐槽</el-radio-button>
      <el-radio-button label="help">求助</el-radio-button>
      <el-radio-button label="share">分享</el-radio-button>
    </el-radio-group>

    <div class="gt-post-list">
      <el-card v-for="post in posts" :key="post.id" shadow="hover" class="gt-post-card">
        <div class="gt-post-header">
          <el-tag :type="categoryTag(post.category)" size="small">{{ categoryLabel(post.category) }}</el-tag>
          <span class="gt-post-author">{{ post.is_anonymous ? '匿名' : (post.author_id?.slice(0, 8) || '未知') }}</span>
          <span class="gt-post-time">{{ post.created_at?.slice(0, 16) }}</span>
        </div>
        <h3 class="gt-post-title">{{ post.title }}</h3>
        <p class="gt-post-content">{{ post.content }}</p>
        <div class="gt-post-actions">
          <el-button text size="small" @click="onLike(post.id)">👍 {{ post.like_count }}</el-button>
          <el-button text size="small" @click="toggleComments(post)">💬 {{ post.comment_count || 0 }}</el-button>
        </div>
        <!-- 评论区 -->
        <div v-if="expandedPost === post.id" class="gt-comments">
          <div v-for="c in comments" :key="c.id" class="gt-comment">
            <span class="gt-comment-author">{{ c.author_id?.slice(0, 8) }}</span>
            <span class="gt-comment-text">{{ c.content }}</span>
          </div>
          <div class="gt-comment-input">
            <el-input v-model="commentText" size="small" placeholder="写评论..." />
            <el-button size="small" type="primary" @click="onComment(post.id)">发送</el-button>
          </div>
        </div>
      </el-card>
    </div>

    <el-dialog v-model="showCreate" title="发帖" width="500px">
      <el-form label-width="60px">
        <el-form-item label="分类">
          <el-select v-model="form.category">
            <el-option label="吐槽" value="vent" />
            <el-option label="求助" value="help" />
            <el-option label="分享" value="share" />
          </el-select>
        </el-form-item>
        <el-form-item label="标题"><el-input v-model="form.title" /></el-form-item>
        <el-form-item label="内容"><el-input v-model="form.content" type="textarea" :rows="4" /></el-form-item>
        <el-form-item><el-checkbox v-model="form.is_anonymous">匿名发布</el-checkbox></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" @click="onCreatePost">发布</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { listPosts, createPost, getComments, createComment, likePost, type ForumPostItem } from '@/services/phase10Api'

const category = ref('')
const posts = ref<ForumPostItem[]>([])
const showCreate = ref(false)
const form = ref({ title: '', content: '', category: 'share', is_anonymous: false })
const expandedPost = ref('')
const comments = ref<any[]>([])
const commentText = ref('')

function categoryTag(c: string) { return c === 'vent' ? 'danger' : c === 'help' ? 'warning' : 'success' }
function categoryLabel(c: string) { return c === 'vent' ? '吐槽' : c === 'help' ? '求助' : '分享' }

async function fetchPosts() { posts.value = await listPosts(category.value || undefined) }

async function onCreatePost() {
  if (!form.value.title || !form.value.content) return ElMessage.warning('请填写标题和内容')
  await createPost(form.value)
  showCreate.value = false
  form.value = { title: '', content: '', category: 'share', is_anonymous: false }
  ElMessage.success('发布成功')
  await fetchPosts()
}

async function onLike(postId: string) {
  await likePost(postId)
  await fetchPosts()
}

async function toggleComments(post: ForumPostItem) {
  if (expandedPost.value === post.id) { expandedPost.value = ''; return }
  expandedPost.value = post.id
  comments.value = await getComments(post.id)
}

async function onComment(postId: string) {
  if (!commentText.value.trim()) return
  await createComment(postId, commentText.value)
  commentText.value = ''
  comments.value = await getComments(postId)
  await fetchPosts()
}

onMounted(fetchPosts)
</script>

<style scoped>
.gt-forum { padding: var(--gt-space-4); }
.gt-page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-3); }
.gt-post-list { display: flex; flex-direction: column; gap: var(--gt-space-2); }
.gt-post-card { cursor: default; }
.gt-post-header { display: flex; align-items: center; gap: var(--gt-space-2); margin-bottom: var(--gt-space-1); }
.gt-post-author, .gt-post-time { font-size: var(--gt-font-size-sm); color: var(--gt-color-text-secondary); }
.gt-post-title { margin: var(--gt-space-1) 0; font-size: 16px; }
.gt-post-content { color: var(--gt-color-text-secondary); margin-bottom: var(--gt-space-2); }
.gt-post-actions { display: flex; gap: var(--gt-space-2); }
.gt-comments { margin-top: var(--gt-space-2); padding-top: var(--gt-space-2); border-top: 1px solid var(--el-border-color); }
.gt-comment { padding: 4px 0; font-size: var(--gt-font-size-sm); }
.gt-comment-author { color: var(--gt-color-primary); font-weight: 600; margin-right: 8px; }
.gt-comment-input { display: flex; gap: var(--gt-space-1); margin-top: var(--gt-space-1); }
</style>
