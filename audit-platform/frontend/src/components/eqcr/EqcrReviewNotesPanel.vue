<template>
  <div v-loading="loading" class="eqcr-tab">
    <!-- 笔记列表 -->
    <el-card shadow="never" class="eqcr-tab__section">
      <template #header>
        <div class="eqcr-tab__section-header">
          <span class="eqcr-tab__section-title">独立复核笔记</span>
          <div class="eqcr-notes__header-actions">
            <el-tag size="small" type="info" effect="plain">
              共 {{ notes.length }} 条
            </el-tag>
            <el-button
              type="primary"
              size="small"
              @click="openCreateDialog"
            >
              + 新建笔记
            </el-button>
          </div>
        </div>
      </template>

      <el-alert
        :closable="false"
        type="info"
        show-icon
        style="margin-bottom: 12px"
      >
        <template #title>
          独立复核笔记为 EQCR 内部留痕，默认项目组不可见。可单条"分享给项目组"后同步到沟通记录。
        </template>
      </el-alert>

      <el-empty
        v-if="!loading && notes.length === 0"
        description="暂无独立复核笔记"
        :image-size="60"
      />

      <!-- 笔记卡片列表 -->
      <div v-else class="eqcr-notes__list">
        <el-card
          v-for="note in notes"
          :key="note.id"
          shadow="hover"
          class="eqcr-notes__item"
        >
          <div class="eqcr-notes__item-header">
            <div class="eqcr-notes__item-title">
              {{ note.title }}
            </div>
            <el-tag
              :type="note.shared_to_team ? 'success' : 'info'"
              size="small"
              effect="plain"
            >
              {{ note.shared_to_team ? '已分享' : '未分享' }}
            </el-tag>
          </div>

          <div class="eqcr-notes__item-content">
            {{ note.content || '（无内容）' }}
          </div>

          <div class="eqcr-notes__item-footer">
            <span class="eqcr-notes__item-time">
              {{ formatDateTime(note.created_at) }}
              <template v-if="note.shared_at">
                · 分享于 {{ formatDateTime(note.shared_at) }}
              </template>
            </span>
            <div class="eqcr-notes__item-actions">
              <el-button
                v-if="!note.shared_to_team"
                size="small"
                type="success"
                link
                @click="handleShare(note)"
              >
                分享给项目组
              </el-button>
              <el-button
                size="small"
                type="primary"
                link
                @click="openEditDialog(note)"
              >
                编辑
              </el-button>
              <el-button
                size="small"
                type="danger"
                link
                @click="handleDelete(note)"
              >
                删除
              </el-button>
            </div>
          </div>
        </el-card>
      </div>
    </el-card>

    <!-- 新建/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEditing ? '编辑笔记' : '新建笔记'"
      width="560px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <el-form
        ref="formRef"
        :model="formData"
        :rules="formRules"
        label-width="80px"
        label-position="top"
      >
        <el-form-item label="标题" prop="title">
          <el-input
            v-model="formData.title"
            placeholder="请输入笔记标题"
            maxlength="200"
            show-word-limit
          />
        </el-form-item>
        <el-form-item label="内容" prop="content">
          <el-input
            v-model="formData.content"
            type="textarea"
            placeholder="请输入笔记内容（独立思考、推断、待核实事项等）"
            :rows="8"
            maxlength="5000"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="submitting"
          @click="handleSubmit"
        >
          {{ isEditing ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { confirmDelete, confirmShare } from '@/utils/confirm'
import type { FormInstance, FormRules } from 'element-plus'
import {
  eqcrApi,
  type EqcrReviewNote,
} from '@/services/eqcrService'

const props = defineProps<{
  projectId: string
}>()

// ─── 状态 ──────────────────────────────────────────────────────────────────

const loading = ref(false)
const notes = ref<EqcrReviewNote[]>([])

const dialogVisible = ref(false)
const isEditing = ref(false)
const editingNoteId = ref<string | null>(null)
const submitting = ref(false)
const formRef = ref<FormInstance>()

const formData = reactive({
  title: '',
  content: '',
})

const formRules: FormRules = {
  title: [
    { required: true, message: '请输入笔记标题', trigger: 'blur' },
    { max: 200, message: '标题不超过 200 字', trigger: 'blur' },
  ],
}

// ─── 加载笔记列表 ──────────────────────────────────────────────────────────

async function loadNotes() {
  if (!props.projectId) return
  loading.value = true
  try {
    notes.value = await eqcrApi.listNotes(props.projectId)
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '加载笔记列表失败')
    notes.value = []
  } finally {
    loading.value = false
  }
}

// ─── 新建笔记 ──────────────────────────────────────────────────────────────

function openCreateDialog() {
  isEditing.value = false
  editingNoteId.value = null
  formData.title = ''
  formData.content = ''
  dialogVisible.value = true
}

// ─── 编辑笔记 ──────────────────────────────────────────────────────────────

function openEditDialog(note: EqcrReviewNote) {
  isEditing.value = true
  editingNoteId.value = note.id
  formData.title = note.title
  formData.content = note.content || ''
  dialogVisible.value = true
}

// ─── 提交表单 ──────────────────────────────────────────────────────────────

async function handleSubmit() {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    if (isEditing.value && editingNoteId.value) {
      await eqcrApi.updateNote(props.projectId, editingNoteId.value, {
        title: formData.title,
        content: formData.content || null,
      })
      ElMessage.success('笔记已更新')
    } else {
      await eqcrApi.createNote(props.projectId, {
        title: formData.title,
        content: formData.content || null,
      })
      ElMessage.success('笔记已创建')
    }
    dialogVisible.value = false
    await loadNotes()
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '操作失败')
  } finally {
    submitting.value = false
  }
}

// ─── 删除笔记 ──────────────────────────────────────────────────────────────

async function handleDelete(note: EqcrReviewNote) {
  try {
    await confirmDelete('笔记"' + note.title + '"')
  } catch {
    return // 用户取消
  }

  try {
    await eqcrApi.deleteNote(props.projectId, note.id)
    ElMessage.success('笔记已删除')
    await loadNotes()
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '删除失败')
  }
}

// ─── 分享给项目组 ──────────────────────────────────────────────────────────

async function handleShare(note: EqcrReviewNote) {
  try {
    await confirmShare('笔记"' + note.title + '"', '项目组')
  } catch {
    return // 用户取消
  }

  try {
    await eqcrApi.shareNoteToTeam(note.id)
    ElMessage.success('笔记已分享给项目组')
    await loadNotes()
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '分享失败')
  }
}

// ─── 辅助 ──────────────────────────────────────────────────────────────────

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return iso
  }
}

// ─── 初始化 ────────────────────────────────────────────────────────────────

onMounted(loadNotes)
</script>

<style scoped>
.eqcr-tab {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.eqcr-tab__section {
  border-radius: var(--gt-radius-md, 6px);
}
.eqcr-tab__section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}
.eqcr-tab__section-title {
  font-weight: 600;
  color: var(--gt-color-text, #303133);
  margin-right: 10px;
}

.eqcr-notes__header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.eqcr-notes__list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.eqcr-notes__item {
  border-radius: var(--gt-radius-md, 6px);
}

.eqcr-notes__item-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.eqcr-notes__item-title {
  font-weight: 600;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text, #303133);
}

.eqcr-notes__item-content {
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-secondary, #606266);
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.eqcr-notes__item-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid var(--el-border-color-lighter, #ebeef5);
}

.eqcr-notes__item-time {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary, #909399);
}

.eqcr-notes__item-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}
</style>
