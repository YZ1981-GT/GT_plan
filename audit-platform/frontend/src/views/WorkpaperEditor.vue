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
        <template v-if="editorAvailable">
          <el-button size="small" @click="onSyncStructure" :loading="convertLoading" title="同步最新编辑到公式系统（通常自动完成，手动点击可强制刷新）">🔄 同步公式</el-button>
          <el-button size="small" @click="onDownloadEdit">下载副本</el-button>
        </template>
        <template v-else>
          <el-button size="small" type="primary" @click="retryOnline" :loading="retrying">重试在线</el-button>
        </template>
        <el-button size="small" @click="onUploadEdit">上传回传</el-button>
        <el-button size="small" @click="onDownloadEdit">下载</el-button>
      </div>
    </div>

    <!-- 主编辑区 -->
    <div class="gt-wp-editor-main">
      <!-- ONLYOFFICE 可用：在线编辑 -->
      <template v-if="editorAvailable">
        <div ref="editorContainer" id="onlyoffice-editor" class="gt-wp-editor-iframe"></div>
      </template>

      <!-- ONLYOFFICE 不可用：直接提供下载编辑入口 -->
      <template v-else>
        <div class="gt-wp-editor-fallback-panel">
          <div style="font-size: 40px; margin-bottom: 16px; opacity: 0.6">📥</div>
          <div style="font-size: 16px; font-weight: 600; color: #444; margin-bottom: 8px">在线编辑器暂不可用</div>
          <div style="font-size: 13px; color: #999; margin-bottom: 24px; max-width: 400px; text-align: center; line-height: 1.6">
            ONLYOFFICE 服务未启动，请下载底稿到本地 Excel 编辑，完成后上传回传
          </div>
          <div class="gt-wp-editor-fallback-actions">
            <el-button type="primary" size="large" @click="onDownloadEdit">
              <el-icon style="margin-right: 6px"><Download /></el-icon>下载底稿
            </el-button>
            <el-button size="large" @click="onUploadEdit">上传编辑后的底稿</el-button>
            <el-button size="large" @click="goBack">返回</el-button>
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
      <!-- 智能提示 -->
      <span v-if="smartTip" class="gt-wp-smart-tip" @click="showSmartTipDetail = !showSmartTipDetail" title="点击展开/收起">
        💡 {{ smartTip.summary }}
      </span>
    </div>
    <!-- 智能提示详情（展开时显示在状态栏上方） -->
    <div v-if="showSmartTipDetail && smartTip" class="gt-wp-smart-tip-detail">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <span style="font-weight:600;font-size:13px">💡 审计关注点</span>
        <el-button size="small" text @click="showSmartTipDetail = false">收起</el-button>
      </div>
      <div v-if="smartTip.warnings?.length" style="margin-bottom:6px">
        <div v-for="(w, i) in smartTip.warnings" :key="i" style="font-size:12px;color:#e6a23c;padding:2px 0">⚠️ {{ w }}</div>
      </div>
      <div v-if="smartTip.tips?.length">
        <div v-for="(t, i) in smartTip.tips" :key="i" style="font-size:12px;color:#666;padding:1px 0">• {{ t }}</div>
      </div>
      <div v-if="smartTip.dependency_warnings?.length" style="margin-top:6px;border-top:1px solid #eee;padding-top:6px">
        <div v-for="(d, i) in smartTip.dependency_warnings" :key="i" style="font-size:11px;color:#909399;padding:1px 0">📋 {{ d }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import {
  checkOnlineEditingAvailability,
  downloadWorkpaper,
  getOnlineEditSession,
  getWorkpaper,
  getWopiEditorUrl,
  type WorkpaperDetail,
} from '@/services/workpaperApi'
import { getWorkpaperStructure, rebuildWorkpaperStructure } from '@/services/commonApi'
import StructureEditor from '@/components/formula/StructureEditor.vue'
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

// ── 三式联动（StructureEditor 降级模式） ──
const structureLoading = ref(false)
const structureData = ref<any>(null)
const structureFileStem = computed(() => wpDetail.value?.wp_code || '')

async function loadStructure() {
  if (editorAvailable.value) return
  structureLoading.value = true
  try {
    const result = await getWorkpaperStructure(projectId.value, wpId.value)
    structureData.value = result?.structure || null
  } catch {
    // structure.json 不存在，自动触发生成
    try {
      await rebuildWorkpaperStructure(projectId.value, wpId.value)
      const result = await getWorkpaperStructure(projectId.value, wpId.value)
      structureData.value = result?.structure || null
    } catch {
      structureData.value = null
    }
  } finally {
    structureLoading.value = false
  }
}

async function onStructureSave() {
  ElMessage.success('底稿已保存')
  // 重新加载详情（版本号可能更新）
  try {
    wpDetail.value = await getWorkpaper(projectId.value, wpId.value)
  } catch { /* ignore */ }
}

async function onStructureRebuild() {
  structureLoading.value = true
  try {
    await rebuildWorkpaperStructure(projectId.value, wpId.value)
    const result = await getWorkpaperStructure(projectId.value, wpId.value, true)
    structureData.value = result.structure
    ElMessage.success('底稿结构已重新解析')
  } catch {
    ElMessage.error('重新解析失败')
  } finally {
    structureLoading.value = false
  }
}

function onExportWord() {
  ElMessage.info('Word 导出功能开发中')
}

// ── 智能提示 ──
const smartTip = ref<{ summary: string; warnings: string[]; tips: string[]; dependency_warnings: string[] } | null>(null)
const showSmartTipDetail = ref(false)

async function loadSmartTips() {
  if (!wpDetail.value) return
  try {
    const wpName = wpDetail.value.wp_name || ''
    const accountName = wpName.replace(/审定表|明细表|程序表|汇总表|盘点表|调节表|核对表/g, '').trim()
    const tips: string[] = []
    const warnings: string[] = []
    const depWarnings: string[] = []

    // 1. 从TSJ加载审计要点
    if (accountName) {
      try {
        const { data } = await import('@/utils/http').then(m =>
          m.default.get(`/api/projects/${projectId.value}/wp-mapping/tsj/${encodeURIComponent(accountName)}`, {
            validateStatus: (s: number) => s < 600,
          })
        )
        if (data?.tips?.length) {
          tips.push(...data.tips.slice(0, 3))
        }
        if (data?.risk_areas?.length) {
          for (const area of data.risk_areas.slice(0, 2)) {
            if (area.includes('高风险')) warnings.push(area)
          }
        }
      } catch { /* ignore */ }
    }

    // 2. 检查B/C/D依赖状态
    try {
      const { getWpDependencies } = await import('@/services/commonApi')
      const deps = await getWpDependencies(projectId.value, wpId.value)
      if (deps?.warnings?.length) {
        depWarnings.push(...deps.warnings)
      }
      if (deps?.impact?.label) {
        tips.push(`控制测试结论：${deps.impact.label} — ${deps.impact.suggested_procedures}`)
      }
    } catch { /* ignore */ }

    if (tips.length || warnings.length || depWarnings.length) {
      const summary = warnings.length > 0
        ? `${warnings.length}项高风险关注点`
        : tips.length > 0
          ? tips[0].slice(0, 30) + (tips[0].length > 30 ? '...' : '')
          : '查看审计关注点'
      smartTip.value = { summary, warnings, tips, dependency_warnings: depWarnings }
    }
  } catch { /* ignore */ }
}

// ── 确认转换（ONLYOFFICE编辑完成后生成structure.json） ──
const convertLoading = ref(false)

async function onSyncStructure() {
  convertLoading.value = true
  try {
    await rebuildWorkpaperStructure(projectId.value, wpId.value)
    wpDetail.value = await getWorkpaper(projectId.value, wpId.value)
    ElMessage.success('公式坐标已同步（ONLYOFFICE保存时通常自动完成）')
  } catch {
    ElMessage.error('同步失败，请稍后重试')
  } finally {
    convertLoading.value = false
  }
}

function stopLockRefresh() {
  if (lockRefreshTimer) {
    clearInterval(lockRefreshTimer)
    lockRefreshTimer = null
  }
}

const editorContainer = ref<HTMLElement | null>(null)
let docEditor: any = null

async function applyOnlineMode(notify: boolean = false) {
  stopLockRefresh()
  editorAvailable.value = false
  editorUrl.value = ''
  onlineAccessToken.value = ''

  try {
    const session = await getOnlineEditSession(projectId.value, wpId.value)
    onlineEditEnabled.value = session.enabled
    if (!session.enabled || !session.wopi_src) {
      if (notify) ElMessage.warning('在线编辑当前未启用，继续使用离线模式')
      return
    }

    const available = await checkOnlineEditingAvailability()
    if (!available) {
      if (notify) ElMessage.warning('在线编辑服务仍不可用，继续使用离线模式')
      return
    }

    onlineAccessToken.value = session.access_token || ''
    editorAvailable.value = true

    // 等待 DOM 渲染
    await nextTick()

    // 加载 ONLYOFFICE Document Server API 脚本
    const ooUrl = (session.onlyoffice_url || import.meta.env.VITE_ONLYOFFICE_URL || 'http://localhost:8080').replace(/\/$/, '')
    await loadOOScript(ooUrl)

    // 用 Document Server API 初始化编辑器
    const fileUrl = `${session.editor_base_url || 'http://localhost:9980'}/api/projects/${projectId.value}/working-papers/${wpId.value}/download`
    const callbackUrl = `${ooUrl.replace('localhost', 'host.docker.internal')}/api/projects/${projectId.value}/working-papers/${wpId.value}/callback`

    const config = {
      document: {
        fileType: 'xlsx',
        key: `${wpId.value}_v${wpDetail.value?.file_version || 1}_${Date.now()}`,
        title: wpDetail.value?.wp_name ? `${wpDetail.value.wp_code} ${wpDetail.value.wp_name}.xlsx` : 'workpaper.xlsx',
        url: `http://host.docker.internal:9980/wopi/files/${wpId.value}/contents?access_token=${onlineAccessToken.value}`,
      },
      editorConfig: {
        mode: 'edit',
        lang: 'zh-CN',
        callbackUrl: `http://host.docker.internal:9980/wopi/ds-callback/${wpId.value}`,
        user: {
          id: 'admin',
          name: 'Admin',
        },
      },
      type: 'desktop',
      width: '100%',
      height: '100%',
    }

    if (docEditor) {
      try { docEditor.destroyEditor() } catch { /* ignore */ }
    }

    docEditor = new (window as any).DocsAPI.DocEditor('onlyoffice-editor', config)
    startLockRefresh()
    if (notify) ElMessage.success('在线编辑已恢复')
  } catch (e: any) {
    editorAvailable.value = false
    if (notify) {
      ElMessage.warning('在线编辑初始化失败：' + (e?.message || '未知错误'))
    }
  }
}

function loadOOScript(baseUrl: string): Promise<void> {
  return new Promise((resolve, reject) => {
    if ((window as any).DocsAPI) { resolve(); return }
    const script = document.createElement('script')
    script.src = `${baseUrl}/web-apps/apps/api/documents/api.js`
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Failed to load ONLYOFFICE API script'))
    document.head.appendChild(script)
  })
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

  // 在线模式不可用时，不再加载 structure（底稿直接下载编辑）

  // 非阻塞加载智能提示
  loadSmartTips()
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
.gt-wp-smart-tip {
  margin-left: auto; cursor: pointer; color: #ffd700; font-weight: 500;
  transition: opacity 0.2s;
}
.gt-wp-smart-tip:hover { opacity: 0.8; }
.gt-wp-smart-tip-detail {
  position: absolute; bottom: 30px; right: 12px; left: 12px;
  background: #fff; border: 1px solid #e8e4f0; border-radius: 8px;
  padding: 12px 16px; box-shadow: 0 -4px 16px rgba(0,0,0,0.08);
  z-index: 20; max-height: 300px; overflow-y: auto;
}
</style>
