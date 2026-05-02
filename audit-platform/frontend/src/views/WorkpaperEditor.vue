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
        <el-tag type="success" size="small" style="margin-left: 8px">Univer</el-tag>
      </div>
      <div class="gt-wp-editor-toolbar-right">
        <el-button size="small" @click="onSave" :loading="saving">💾 保存</el-button>
        <el-button size="small" @click="onSyncStructure" :loading="syncLoading">🔄 同步公式</el-button>
        <el-button size="small" @click="onDownload">📥 下载</el-button>
        <el-button size="small" @click="onUpload">📤 上传</el-button>
      </div>
    </div>

    <!-- Univer 编辑区 -->
    <div class="gt-wp-editor-main">
      <div v-if="loading" class="gt-wp-editor-loading">
        <el-icon class="is-loading" :size="32" color="var(--gt-color-primary)"><Loading /></el-icon>
        <p>正在加载底稿...</p>
      </div>
      <div v-show="!loading" ref="univerContainer" class="gt-wp-editor-univer"></div>
    </div>

    <!-- 底部状态栏 -->
    <div class="gt-wp-editor-statusbar" v-if="wpDetail">
      <span>编制人: {{ wpDetail.assigned_to || '未分配' }}</span>
      <span>复核人: {{ wpDetail.reviewer || '未分配' }}</span>
      <span>版本: v{{ wpDetail.file_version || 1 }}</span>
      <span v-if="wpDetail.updated_at">最后修改: {{ wpDetail.updated_at.slice(0, 19) }}</span>
      <span v-if="dirty" style="color: #e6a23c">● 未保存</span>
      <span v-if="smartTip" class="gt-wp-smart-tip" @click="showSmartTipDetail = !showSmartTipDetail">
        💡 {{ smartTip.summary }}
      </span>
    </div>

    <!-- 智能提示详情 -->
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
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { createUniver, LocaleType, mergeLocales } from '@univerjs/presets'
import { UniverSheetsCorePreset } from '@univerjs/preset-sheets-core'
import UniverPresetSheetsCoreZhCN from '@univerjs/preset-sheets-core/lib/locales/zh-CN'
import '@univerjs/preset-sheets-core/lib/index.css'
import {
  downloadWorkpaper,
  getWorkpaper,
  type WorkpaperDetail,
} from '@/services/workpaperApi'
import { rebuildWorkpaperStructure } from '@/services/commonApi'
import http from '@/utils/http'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.projectId as string)
const wpId = computed(() => route.params.wpId as string)

const wpDetail = ref<WorkpaperDetail | null>(null)
const loading = ref(true)
const saving = ref(false)
const syncLoading = ref(false)
const dirty = ref(false)
const univerContainer = ref<HTMLElement | null>(null)

let univerInstance: any = null
let univerAPI: any = null

// 智能提示
const smartTip = ref<any>(null)
const showSmartTipDetail = ref(false)

function statusTagType(s: string) {
  const m: Record<string, string> = {
    not_started: 'info', in_progress: 'warning', draft: 'warning',
    draft_complete: '', edit_complete: '', review_passed: 'success', archived: 'info',
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
  if (dirty.value) {
    if (!confirm('有未保存的修改，确定离开？')) return
  }
  router.push({ name: 'WorkpaperList', params: { projectId: projectId.value } })
}

async function initUniver() {
  if (!univerContainer.value) return

  // 1. 加载底稿详情
  try {
    wpDetail.value = await getWorkpaper(projectId.value, wpId.value)
  } catch {
    ElMessage.error('底稿不存在')
    goBack()
    return
  }

  // 2. 从后端加载完整的 Univer 数据（含所有 Sheet、样式、公式）
  let workbookData: any = null
  try {
    const { data } = await http.get(
      `/api/projects/${projectId.value}/working-papers/${wpId.value}/univer-data`,
      { validateStatus: (s: number) => s < 600 },
    )
    workbookData = data?.data ?? data
  } catch {
    workbookData = null
  }

  if (!workbookData || !workbookData.sheets) {
    // 兜底：创建空白工作簿
    workbookData = {
      id: wpDetail.value.wp_code || 'wp',
      name: `${wpDetail.value.wp_code} ${wpDetail.value.wp_name}`,
      sheetOrder: ['sheet0'],
      sheets: {
        sheet0: {
          id: 'sheet0',
          name: wpDetail.value.wp_name || 'Sheet1',
          rowCount: 100,
          columnCount: 20,
          cellData: {},
        },
      },
    }
  }

  // 3. 初始化 Univer
  const { univerAPI: api, univer } = createUniver({
    locale: LocaleType.ZH_CN,
    locales: {
      [LocaleType.ZH_CN]: mergeLocales(UniverPresetSheetsCoreZhCN),
    },
    presets: [
      UniverSheetsCorePreset({
        container: univerContainer.value,
      }),
    ],
  })

  univerInstance = univer
  univerAPI = api

  // 4. 创建工作簿
  univerAPI.createWorkbook(workbookData)

  // 5. 监听数据变化
  univerAPI.onCommandExecuted((command: any) => {
    if (command.id?.includes('set-range-values') || command.id?.includes('set-cell')) {
      dirty.value = true
    }
  })

  loading.value = false

  // 6. 非阻塞加载智能提示
  loadSmartTips()
}

async function onSave() {
  if (!univerAPI || !wpDetail.value) return
  saving.value = true
  try {
    const workbook = univerAPI.getActiveWorkbook()
    if (!workbook) throw new Error('无法获取工作簿数据')

    const snapshot = workbook.getSnapshot()

    // 调用完整保存 API（xlsx 回写 + structure.json + 审计留痕 + 事件发布）
    const { data } = await http.post(
      `/api/projects/${projectId.value}/working-papers/${wpId.value}/univer-save`,
      { snapshot },
    )
    const result = data?.data ?? data

    dirty.value = false
    ElMessage.success(result?.message || '保存成功')

    // 刷新版本信息
    wpDetail.value = await getWorkpaper(projectId.value, wpId.value)
  } catch (err: any) {
    ElMessage.error('保存失败: ' + (err?.response?.data?.detail || err?.message || ''))
  } finally {
    saving.value = false
  }
}

async function onSyncStructure() {
  syncLoading.value = true
  try {
    // 先保存当前数据
    if (dirty.value) await onSave()
    // 重建 structure
    await rebuildWorkpaperStructure(projectId.value, wpId.value)
    wpDetail.value = await getWorkpaper(projectId.value, wpId.value)
    ElMessage.success('公式坐标已同步')
  } catch {
    ElMessage.error('同步失败')
  } finally {
    syncLoading.value = false
  }
}

async function onDownload() {
  try {
    await downloadWorkpaper(projectId.value, wpId.value)
  } catch {
    ElMessage.error('下载失败')
  }
}

function onUpload() {
  router.push({
    name: 'WorkpaperList',
    params: { projectId: projectId.value },
    query: { upload: wpId.value },
  })
}

async function loadSmartTips() {
  if (!wpDetail.value) return
  try {
    const wpName = wpDetail.value.wp_name || ''
    const accountName = wpName.replace(/审定表|明细表|程序表|汇总表|盘点表|调节表|核对表/g, '').trim()
    if (!accountName) return

    const { data } = await http.get(
      `/api/projects/${projectId.value}/wp-mapping/tsj/${encodeURIComponent(accountName)}`,
      { validateStatus: (s: number) => s < 600 },
    )
    if (data?.tips?.length || data?.risk_areas?.length) {
      smartTip.value = {
        summary: data.risk_areas?.find((a: string) => a.includes('高风险')) || data.tips?.[0]?.slice(0, 30) || '查看审计关注点',
        warnings: (data.risk_areas || []).filter((a: string) => a.includes('高风险')),
        tips: (data.tips || []).slice(0, 3),
      }
    }
  } catch { /* ignore */ }
}

onMounted(initUniver)

onUnmounted(() => {
  if (univerInstance) {
    try { univerInstance.dispose() } catch { /* ignore */ }
    univerInstance = null
    univerAPI = null
  }
})
</script>

<style scoped>
.gt-wp-editor {
  display: flex; flex-direction: column; height: 100vh;
  background: var(--gt-color-bg);
}
.gt-wp-editor-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  padding: var(--gt-space-2) var(--gt-space-4);
  background: var(--gt-color-bg-white); box-shadow: var(--gt-shadow-sm); z-index: 10;
}
.gt-wp-editor-toolbar-left { display: flex; align-items: center; gap: 10px; }
.gt-wp-editor-toolbar-right { display: flex; align-items: center; gap: var(--gt-space-2); }
.gt-wp-editor-code { font-weight: 600; color: var(--gt-color-primary); font-size: var(--gt-font-size-md); }
.gt-wp-editor-name { color: var(--gt-color-text); font-size: var(--gt-font-size-md); }
.gt-wp-editor-main { flex: 1; min-height: 0; position: relative; overflow: hidden; }
.gt-wp-editor-univer { width: 100%; height: 100%; }
.gt-wp-editor-loading {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; height: 100%; gap: 12px; color: #999;
}
.gt-wp-editor-statusbar {
  display: flex; gap: var(--gt-space-5); padding: 6px var(--gt-space-4);
  background: var(--gt-color-primary-dark); color: var(--gt-color-text-tertiary);
  font-size: var(--gt-font-size-xs);
}
.gt-wp-smart-tip {
  margin-left: auto; cursor: pointer; color: #ffd700; font-weight: 500;
}
.gt-wp-smart-tip-detail {
  position: absolute; bottom: 30px; right: 12px; left: 12px;
  background: #fff; border: 1px solid #e8e4f0; border-radius: 8px;
  padding: 12px 16px; box-shadow: 0 -4px 16px rgba(0,0,0,0.08);
  z-index: 20; max-height: 300px; overflow-y: auto;
}
</style>
