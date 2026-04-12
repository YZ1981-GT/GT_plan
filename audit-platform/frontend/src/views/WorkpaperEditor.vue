<template>
  <div class="wp-editor-page">
    <!-- 顶部工具栏 -->
    <div class="editor-toolbar">
      <div class="toolbar-left">
        <el-button text @click="goBack">← 返回</el-button>
        <span class="wp-code" v-if="wpDetail">{{ wpDetail.wp_code }}</span>
        <span class="wp-name" v-if="wpDetail">{{ wpDetail.wp_name }}</span>
        <el-tag v-if="wpDetail" :type="statusTagType(wpDetail.status)" size="small">
          {{ statusLabel(wpDetail.status) }}
        </el-tag>
      </div>
      <div class="toolbar-right">
        <span class="save-indicator" v-if="wpDetail">
          <el-icon color="var(--gt-color-success)"><i class="el-icon-check" /></el-icon>
          已保存
        </span>
      </div>
    </div>

    <!-- 主编辑区 -->
    <div class="editor-main">
      <!-- ONLYOFFICE 可用 -->
      <template v-if="editorAvailable">
        <iframe
          ref="editorFrame"
          :src="editorUrl"
          class="editor-iframe"
          allow="fullscreen"
        />
      </template>

      <!-- ONLYOFFICE 不可用：降级模式 -->
      <template v-else>
        <div class="fallback-panel">
          <el-alert
            title="ONLYOFFICE 编辑器不可用"
            description="在线编辑服务暂时无法连接，请使用离线编辑模式：下载底稿到本地编辑后再上传。"
            type="warning"
            show-icon
            :closable="false"
            style="margin-bottom: 20px"
          />
          <div class="fallback-actions">
            <el-button type="primary" size="large" @click="onDownloadEdit">
              下载编辑
            </el-button>
            <el-button size="large" @click="goBack">返回底稿列表</el-button>
          </div>
        </div>
      </template>
    </div>

    <!-- 底部状态栏 -->
    <div class="editor-statusbar" v-if="wpDetail">
      <span>编制人: {{ wpDetail.assigned_to || '未分配' }}</span>
      <span>复核人: {{ wpDetail.reviewer || '未分配' }}</span>
      <span>版本: v{{ wpDetail.file_version || 1 }}</span>
      <span v-if="wpDetail.updated_at">最后修改: {{ wpDetail.updated_at.slice(0, 19) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getWorkpaper, getWopiEditorUrl, type WorkpaperDetail } from '@/services/workpaperApi'
import http from '@/utils/http'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.projectId as string)
const wpId = computed(() => route.params.wpId as string)

const wpDetail = ref<WorkpaperDetail | null>(null)
const editorAvailable = ref(false)
const editorUrl = ref('')
const editorFrame = ref<HTMLIFrameElement | null>(null)

function statusTagType(s: string) {
  const m: Record<string, string> = {
    not_started: 'info', in_progress: 'warning', draft: 'warning',
    draft_complete: '', edit_complete: '', review_passed: 'success',
    archived: 'info',
  }
  return m[s] || 'info'
}

function statusLabel(s: string) {
  const m: Record<string, string> = {
    not_started: '未开始', in_progress: '编制中', draft: '草稿',
    draft_complete: '初稿完成', edit_complete: '编辑完成',
    review_passed: '复核通过', archived: '已归档',
  }
  return m[s] || s
}

function goBack() {
  router.push({ name: 'WorkpaperList', params: { projectId: projectId.value } })
}

function onDownloadEdit() {
  window.open(`/api/projects/${projectId.value}/working-papers/${wpId.value}/download`, '_blank')
}

async function checkOnlyoffice(): Promise<boolean> {
  try {
    const resp = await http.get('/api/health', { timeout: 5000 })
    // Check if ONLYOFFICE is configured and reachable
    return resp.status === 200
  } catch {
    return false
  }
}

async function loadEditor() {
  try {
    wpDetail.value = await getWorkpaper(projectId.value, wpId.value)
  } catch {
    ElMessage.error('底稿不存在')
    goBack()
    return
  }

  // Check ONLYOFFICE availability
  const available = await checkOnlyoffice()
  editorAvailable.value = available

  if (available) {
    // Build WOPI editor URL with access token
    const token = localStorage.getItem('access_token') || ''
    editorUrl.value = getWopiEditorUrl(wpId.value, token)
  }
}

onMounted(loadEditor)
</script>

<style scoped>
.wp-editor-page {
  display: flex; flex-direction: column; height: 100vh;
  background: #f5f5f5;
}
.editor-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 16px; background: #fff; box-shadow: var(--gt-shadow-sm);
  z-index: 10;
}
.toolbar-left { display: flex; align-items: center; gap: 10px; }
.toolbar-right { display: flex; align-items: center; gap: 8px; }
.wp-code { font-weight: 600; color: var(--gt-color-primary); font-size: 15px; }
.wp-name { color: #333; font-size: 15px; }
.save-indicator { font-size: 13px; color: var(--gt-color-success); }
.editor-main { flex: 1; min-height: 0; }
.editor-iframe { width: 100%; height: 100%; border: none; }
.fallback-panel {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; height: 100%; padding: 40px;
}
.fallback-actions { display: flex; gap: 12px; }
.editor-statusbar {
  display: flex; gap: 20px; padding: 6px 16px;
  background: var(--gt-color-primary-dark); color: #ccc; font-size: 12px;
}
</style>
