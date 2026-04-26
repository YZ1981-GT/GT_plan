<template>
  <div class="gt-wp-editor gt-fade-in">
    <!-- 顶部工具栏 -->
    <div class="gt-wp-editor-toolbar">
      <div class="gt-wp-editor-toolbar-left">
        <el-button text @click="goBack">← 返回</el-button>
        <span class="gt-wp-editor-code" v-if="wpDetail">{{ wpDetail.wp_code }}</span>
        <span class="gt-wp-editor-name" v-if="wpDetail">{{ wpDetail.wp_name }}</span>
        <el-tag v-if="wpDetail" :type="statusTagType(wpDetail.status)" size="small">
          {{ statusLabel(wpDetail.status) }}
        </el-tag>
        <el-tag v-if="editorAvailable" type="success" size="small" style="margin-left: 8px">在线模式</el-tag>
        <el-tag v-else type="info" size="small" style="margin-left: 8px">离线模式</el-tag>
      </div>
      <div class="gt-wp-editor-toolbar-right">
        <!-- 双模式切换：在线时也能下载，离线时也能重试在线 -->
        <el-button v-if="editorAvailable" size="small" @click="onDownloadEdit">下载副本</el-button>
        <el-button v-else size="small" type="primary" @click="retryOnline" :loading="retrying">重试在线</el-button>
        <el-button size="small" @click="onUploadEdit">上传回传</el-button>
      </div>
    </div>

    <!-- 主编辑区 -->
    <div class="gt-wp-editor-main">
      <!-- ONLYOFFICE 可用：在线编辑 -->
      <template v-if="editorAvailable">
        <iframe
          :src="editorUrl"
          class="gt-wp-editor-iframe"
          allow="fullscreen"
        />
      </template>

      <!-- ONLYOFFICE 不可用：自动降级到离线模式 -->
      <template v-else>
        <div class="gt-wp-editor-fallback-panel">
          <el-alert
            title="在线编辑暂不可用，已自动切换到离线模式"
            description="您可以下载底稿到本地 Excel 编辑，完成后点击「上传回传」。在线服务恢复后可点击「重试在线」切换回来。"
            type="info"
            show-icon
            :closable="false"
            style="margin-bottom: 20px"
          />
          <div class="gt-wp-editor-fallback-actions">
            <el-button type="primary" size="large" @click="onDownloadEdit">
              下载底稿到本地编辑
            </el-button>
            <el-button size="large" @click="onUploadEdit">上传编辑后的底稿</el-button>
            <el-button size="large" @click="goBack">返回底稿列表</el-button>
          </div>
        </div>
      </template>
    </div>

    <!-- 底部状态栏 -->
    <div class="gt-wp-editor-statusbar" v-if="wpDetail">
      <span>编制人: {{ wpDetail.assigned_to || '未分配' }}</span>
      <span>复核人: {{ wpDetail.reviewer || '未分配' }}</span>
      <span>版本: v{{ wpDetail.file_version || 1 }}</span>
      <span v-if="wpDetail.updated_at">最后修改: {{ wpDetail.updated_at.slice(0, 19) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  checkOnlineEditingAvailability,
  downloadWorkpaper,
  getOnlineEditSession,
  getWorkpaper,
  getWopiEditorUrl,
  type WorkpaperDetail,
} from '@/services/workpaperApi'
import http from '@/utils/http' // Needed for WOPI lock refresh with custom headers

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.projectId as string)
const wpId = computed(() => route.params.wpId as string)

const wpDetail = ref<WorkpaperDetail | null>(null)
const editorAvailable = ref(false)
const editorUrl = ref('')
const onlineEditEnabled = ref(true)
const onlineAccessToken = ref('')

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

async function onDownloadEdit() {
  try {
    await downloadWorkpaper(projectId.value, wpId.value)
  } catch {
    ElMessage.error('底稿下载失败')
  }
}

function onUploadEdit() {
  // 跳转到底稿列表页的上传弹窗
  router.push({
    name: 'WorkpaperList',
    params: { projectId: projectId.value },
    query: { upload: wpId.value },
  })
}

const retrying = ref(false)
let lockRefreshTimer: ReturnType<typeof setInterval> | null = null

function stopLockRefresh() {
  if (lockRefreshTimer) {
    clearInterval(lockRefreshTimer)
    lockRefreshTimer = null
  }
}

async function applyOnlineMode(notify: boolean = false) {
  stopLockRefresh()
  editorAvailable.value = false
  editorUrl.value = ''
  onlineAccessToken.value = ''

  try {
    const session = await getOnlineEditSession(projectId.value, wpId.value)
    onlineEditEnabled.value = session.enabled
    if (!session.enabled || !session.wopi_src) {
      if (notify) {
        ElMessage.warning('在线编辑当前未启用，继续使用离线模式')
      }
      return
    }

    const available = await checkOnlineEditingAvailability()
    if (!available) {
      if (notify) {
        ElMessage.warning('在线编辑服务仍不可用，继续使用离线模式')
      }
      return
    }

    onlineAccessToken.value = session.access_token || ''
    editorUrl.value = getWopiEditorUrl(session.wopi_src)
    editorAvailable.value = true
    startLockRefresh()
    if (notify) {
      ElMessage.success('在线编辑已恢复')
    }
  } catch {
    if (notify) {
      ElMessage.warning(onlineEditEnabled.value ? '在线编辑暂不可用，继续使用离线模式' : '在线编辑当前未启用，继续使用离线模式')
    }
  }
}

async function retryOnline() {
  retrying.value = true
  try {
    await applyOnlineMode(true)
  } finally {
    retrying.value = false
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

  await applyOnlineMode()
}

function startLockRefresh() {
  stopLockRefresh()
  lockRefreshTimer = setInterval(async () => {
    if (!editorAvailable.value || !wpDetail.value || !onlineAccessToken.value) return
    try {
      await http.post(`/wopi/files/${wpId.value}?access_token=${encodeURIComponent(onlineAccessToken.value)}`, null, {
        headers: { 'X-WOPI-Override': 'REFRESH_LOCK', 'X-WOPI-Lock': `lock-${wpId.value}` },
        timeout: 5000,
      })
    } catch (err: any) {
      if (err?.response?.status === 409) {
        ElMessage.error('编辑锁已被其他用户获取，请保存后刷新页面')
        editorAvailable.value = false
        editorUrl.value = ''
        stopLockRefresh()
      }
    }
  }, 10 * 60 * 1000) // 10 分钟
}

onUnmounted(() => {
  stopLockRefresh()
})

onMounted(loadEditor)
</script>

<style scoped>
.gt-wp-editor {
  display: flex; flex-direction: column; height: 100vh;
  background: var(--gt-color-bg);
}
.gt-wp-editor-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  padding: var(--gt-space-2) var(--gt-space-4); background: var(--gt-color-bg-white); box-shadow: var(--gt-shadow-sm);
  z-index: 10;
}
.gt-wp-editor-toolbar-left { display: flex; align-items: center; gap: 10px; }
.gt-wp-editor-toolbar-right { display: flex; align-items: center; gap: var(--gt-space-2); }
.gt-wp-editor-code { font-weight: 600; color: var(--gt-color-primary); font-size: var(--gt-font-size-md); }
.gt-wp-editor-name { color: var(--gt-color-text); font-size: var(--gt-font-size-md); }
.gt-wp-editor-save-indicator { font-size: var(--gt-font-size-sm); color: var(--gt-color-success); }
.gt-wp-editor-main { flex: 1; min-height: 0; }
.gt-wp-editor-iframe { width: 100%; height: 100%; border: none; }
.gt-wp-editor-fallback-panel {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; height: 100%; padding: var(--gt-space-10);
}
.gt-wp-editor-fallback-actions { display: flex; gap: var(--gt-space-3); }
.gt-wp-editor-statusbar {
  display: flex; gap: var(--gt-space-5); padding: 6px var(--gt-space-4);
  background: var(--gt-color-primary-dark); color: var(--gt-color-text-tertiary); font-size: var(--gt-font-size-xs);
}
</style>
