<template>
  <div class="gt-wp-list gt-fade-in">
    <!-- 顶部筛选栏 -->
    <div class="gt-wp-filter-bar">
      <h2 class="gt-page-title">底稿管理</h2>
      <div class="gt-wp-filters">
        <el-select v-model="filterCycle" placeholder="审计循环" clearable size="default" style="width: 160px">
          <el-option v-for="c in cycleOptions" :key="c.value" :label="c.label" :value="c.value" />
        </el-select>
        <el-select v-model="filterStatus" placeholder="状态" clearable size="default" style="width: 130px">
          <el-option v-for="s in statusOptions" :key="s.value" :label="s.label" :value="s.value" />
        </el-select>
        <el-select v-model="filterAssignee" placeholder="编制人" clearable size="default" style="width: 130px">
          <el-option label="全部" value="" />
        </el-select>
        <el-button @click="fetchData" :loading="loading">刷新</el-button>
        <el-button type="primary" :disabled="selectedWpIds.length === 0" @click="onBatchDownload" :loading="downloadLoading">
          批量下载 ({{ selectedWpIds.length }})
        </el-button>
      </div>
    </div>

    <!-- 主体：左树 + 右详情 -->
    <div class="gt-wp-body">
      <!-- 左侧索引树 -->
      <div class="gt-wp-tree-panel">
        <el-tree
          :data="treeData"
          :props="{ label: 'label', children: 'children' }"
          node-key="id"
          highlight-current
          default-expand-all
          show-checkbox
          @check-change="onCheckChange"
          @node-click="onNodeClick"
          ref="treeRef"
        >
          <template #default="{ data }">
            <div class="gt-wp-tree-node">
              <span class="gt-wp-tree-node-label">{{ data.label }}</span>
              <el-tag v-if="data.status" :type="statusTagType(data.status)" size="small" class="gt-wp-tree-node-tag">
                {{ statusLabel(data.status) }}
              </el-tag>
            </div>
          </template>
        </el-tree>
        <el-empty v-if="!loading && treeData.length === 0" description="暂无底稿" :image-size="80" />
      </div>

      <!-- 右侧详情面板 -->
      <div class="gt-wp-detail-panel">
        <template v-if="selectedWp">
          <div class="gt-wp-detail-card">
            <h3 class="gt-wp-detail-title">{{ selectedWp.wp_code }} {{ selectedWp.wp_name }}</h3>
            <el-descriptions :column="2" border size="default">
              <el-descriptions-item label="底稿编号">{{ selectedWp.wp_code }}</el-descriptions-item>
              <el-descriptions-item label="底稿名称">{{ selectedWp.wp_name }}</el-descriptions-item>
              <el-descriptions-item label="审计循环">{{ selectedWp.audit_cycle || '-' }}</el-descriptions-item>
              <el-descriptions-item label="状态">
                <el-tag :type="statusTagType(selectedWp.status)" size="small">
                  {{ statusLabel(selectedWp.status) }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="编制人">{{ selectedWp.assigned_to || '未分配' }}</el-descriptions-item>
              <el-descriptions-item label="复核人">{{ selectedWp.reviewer || '未分配' }}</el-descriptions-item>
              <el-descriptions-item label="文件版本">v{{ selectedWp.file_version || 1 }}</el-descriptions-item>
              <el-descriptions-item label="最后解析">{{ selectedWp.last_parsed_at?.slice(0, 19) || '-' }}</el-descriptions-item>
            </el-descriptions>

            <!-- 操作按钮 -->
            <div class="gt-wp-detail-actions">
              <el-button type="primary" @click="onOnlineEdit">在线编辑</el-button>
              <el-button @click="onDownload">下载</el-button>
              <el-button @click="onUpload">上传</el-button>
              <el-button type="warning" @click="onQCCheck" :loading="qcLoading">自检</el-button>
              <el-tooltip :disabled="!hasBlocking" :content="blockingReasons.join('；')" placement="top">
                <el-button type="success" @click="onSubmitReview" :disabled="hasBlocking">提交复核</el-button>
              </el-tooltip>
            </div>

            <!-- QC 结果摘要 -->
            <div v-if="qcResult" class="gt-wp-qc-summary-inline">
              <el-tag :type="qcResult.passed ? 'success' : 'danger'" size="small">
                {{ qcResult.passed ? '自检通过' : '存在问题' }}
              </el-tag>
              <span class="gt-wp-qc-counts">
                阻断 {{ qcResult.blocking_count }} / 警告 {{ qcResult.warning_count }} / 提示 {{ qcResult.info_count }}
              </span>
            </div>

            <!-- 复核批注面板 -->
            <div class="gt-wp-review-section" style="margin-top: 16px">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px">
                <h4 style="margin: 0; font-size: 14px; color: var(--gt-color-text)">
                  复核意见
                  <el-badge v-if="unresolvedCount > 0" :value="unresolvedCount" type="danger" style="margin-left: 8px" />
                </h4>
                <el-button size="small" type="primary" @click="showAddAnnotation = true">新增意见</el-button>
              </div>
              <el-table v-if="annotations.length" :data="annotations" size="small" stripe max-height="200">
                <el-table-column prop="content" label="内容" min-width="200" show-overflow-tooltip />
                <el-table-column prop="priority" label="优先级" width="80">
                  <template #default="{ row }">
                    <el-tag :type="row.priority === 'high' ? 'danger' : row.priority === 'medium' ? 'warning' : 'info'" size="small">
                      {{ row.priority === 'high' ? '高' : row.priority === 'medium' ? '中' : '低' }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="status" label="状态" width="80">
                  <template #default="{ row }">
                    <el-tag :type="row.status === 'resolved' ? 'success' : row.status === 'replied' ? 'warning' : 'danger'" size="small">
                      {{ row.status === 'resolved' ? '已解决' : row.status === 'replied' ? '已回复' : '待处理' }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="100">
                  <template #default="{ row }">
                    <el-button v-if="row.status !== 'resolved'" size="small" text type="success" @click="resolveAnnotation(row.id)">解决</el-button>
                  </template>
                </el-table-column>
              </el-table>
              <el-empty v-else description="暂无复核意见" :image-size="40" />
            </div>

            <!-- 新增意见弹窗 -->
            <el-dialog v-model="showAddAnnotation" title="新增复核意见" width="400px">
              <el-form label-width="60px">
                <el-form-item label="内容">
                  <el-input v-model="newAnnotation.content" type="textarea" :rows="3" placeholder="输入复核意见" />
                </el-form-item>
                <el-form-item label="优先级">
                  <el-radio-group v-model="newAnnotation.priority">
                    <el-radio value="high">高</el-radio>
                    <el-radio value="medium">中</el-radio>
                    <el-radio value="low">低</el-radio>
                  </el-radio-group>
                </el-form-item>
              </el-form>
              <template #footer>
                <el-button @click="showAddAnnotation = false">取消</el-button>
                <el-button type="primary" @click="submitAnnotation" :disabled="!newAnnotation.content">提交</el-button>
              </template>
            </el-dialog>
          </div>
        </template>
        <el-empty v-else description="请从左侧选择底稿" :image-size="120" />
      </div>
    </div>

    <!-- 上传弹窗 -->
    <el-dialog v-model="uploadDialogVisible" title="上传底稿" width="500px">
      <el-alert v-if="uploadConflict" type="warning" :closable="false" show-icon style="margin-bottom: 16px">
        版本冲突：服务器版本 v{{ uploadConflict.server_version }}，您的版本 v{{ uploadConflict.uploaded_version }}
      </el-alert>
      <el-upload
        ref="uploadRef"
        drag
        :auto-upload="false"
        :limit="1"
        accept=".xlsx,.xls"
        :on-change="onUploadFileChange"
      >
        <el-icon style="font-size: 40px; color: var(--gt-color-primary)"><Upload /></el-icon>
        <div>拖拽文件到此处，或点击选择</div>
      </el-upload>
      <template #footer>
        <el-button @click="uploadDialogVisible = false">取消</el-button>
        <el-button v-if="uploadConflict" type="warning" @click="doUpload(true)" :loading="uploadLoading">
          强制覆盖
        </el-button>
        <el-button type="primary" @click="doUpload(false)" :loading="uploadLoading" :disabled="!uploadFile">
          上传
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Upload } from '@element-plus/icons-vue'
import http from '@/utils/http'
import {
  listWorkpapers, runQCCheck, getQCResults,
  updateWorkpaperStatus, getWpIndex,
  type WorkpaperDetail, type WpIndexItem, type QCResult,
} from '@/services/workpaperApi'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.projectId as string)

const loading = ref(false)
const qcLoading = ref(false)
const downloadLoading = ref(false)
const uploadLoading = ref(false)
const wpList = ref<WorkpaperDetail[]>([])
const wpIndex = ref<WpIndexItem[]>([])
const selectedWp = ref<WorkpaperDetail | null>(null)
const selectedWpIds = ref<string[]>([])
const qcResult = ref<QCResult | null>(null)
const treeRef = ref<any>(null)

// Upload dialog
const uploadDialogVisible = ref(false)
const uploadFile = ref<File | null>(null)
const uploadConflict = ref<{ server_version: number; uploaded_version: number } | null>(null)
const uploadRef = ref<any>(null)

// Review annotations
const annotations = ref<any[]>([])
const unresolvedCount = computed(() => annotations.value.filter(a => a.status !== 'resolved').length)
const showAddAnnotation = ref(false)
const newAnnotation = ref({ content: '', priority: 'medium' })

// Filters
const filterCycle = ref('')
const filterStatus = ref('')
const filterAssignee = ref('')

const cycleOptions = [
  { value: 'B', label: 'B类 穿行测试' },
  { value: 'C', label: 'C类 控制测试' },
  { value: 'D', label: 'D类 货币资金' },
  { value: 'E', label: 'E类 应收账款' },
  { value: 'F', label: 'F类 存货' },
  { value: 'G', label: 'G类 固定资产' },
  { value: 'H', label: 'H类 无形资产' },
  { value: 'I', label: 'I类 投资' },
  { value: 'J', label: 'J类 负债' },
  { value: 'K', label: 'K类 收入' },
  { value: 'L', label: 'L类 成本费用' },
  { value: 'M', label: 'M类 权益' },
  { value: 'N', label: 'N类 其他' },
]

const statusOptions = [
  { value: 'not_started', label: '未开始' },
  { value: 'in_progress', label: '编制中' },
  { value: 'draft_complete', label: '初稿完成' },
  { value: 'review_passed', label: '复核通过' },
  { value: 'archived', label: '已归档' },
]

const hasBlocking = computed(() => {
  // 4 项硬门槛：任一不满足则禁止提交复核
  if (!selectedWp.value) return true
  // 1. reviewer 未分配
  if (!selectedWp.value.reviewer) return true
  // 2. 阻断级 QC 未通过
  if (qcResult.value && (qcResult.value.blocking_count ?? 0) > 0) return true
  // 3. 存在未解决复核意见
  if (unresolvedCount.value > 0) return true
  return false
})

const blockingReasons = computed(() => {
  const reasons: string[] = []
  if (!selectedWp.value) return reasons
  if (!selectedWp.value.reviewer) reasons.push('复核人未分配')
  if (qcResult.value && (qcResult.value.blocking_count ?? 0) > 0) reasons.push('存在阻断级 QC 问题')
  if (unresolvedCount.value > 0) reasons.push(`${unresolvedCount.value} 条未解决复核意见`)
  return reasons
})

interface TreeNode {
  id: string
  label: string
  status?: string
  assigned_to?: string | null
  wpId?: string
  children?: TreeNode[]
}

const treeData = computed<TreeNode[]>(() => {
  const groups: Record<string, TreeNode> = {}
  const CYCLE_GROUPS: Record<string, string> = {
    B: 'B类 穿行测试', C: 'C类 控制测试',
  }

  const items = wpIndex.value.filter(w => {
    if (filterCycle.value && !w.wp_code?.startsWith(filterCycle.value)) return false
    if (filterStatus.value && w.status !== filterStatus.value) return false
    if (filterAssignee.value && w.assigned_to !== filterAssignee.value) return false
    return true
  })

  for (const wp of items) {
    const prefix = wp.wp_code?.charAt(0) || '?'
    const groupKey = prefix
    const groupLabel = CYCLE_GROUPS[prefix] || `${prefix}类 实质性程序`

    if (!groups[groupKey]) {
      groups[groupKey] = { id: `group-${groupKey}`, label: groupLabel, children: [] }
    }
    groups[groupKey].children!.push({
      id: wp.id,
      label: `${wp.wp_code} ${wp.wp_name}`,
      status: wp.status || undefined,
      assigned_to: wp.assigned_to,
      wpId: wp.id,
    })
  }

  return Object.values(groups).sort((a, b) => a.label.localeCompare(b.label))
})

function statusTagType(s: string) {
  const m: Record<string, string> = {
    not_started: 'info', in_progress: 'warning', draft: 'warning',
    draft_complete: '', edit_complete: '', review_passed: 'success',
    review_level1_passed: 'success', review_level2_passed: 'success',
    archived: 'info',
  }
  return m[s] || 'info'
}

function statusLabel(s: string) {
  const m: Record<string, string> = {
    not_started: '未开始', in_progress: '编制中', draft: '草稿',
    draft_complete: '初稿完成', edit_complete: '编辑完成',
    review_passed: '复核通过', review_level1_passed: '一级复核通过',
    review_level2_passed: '二级复核通过', archived: '已归档',
  }
  return m[s] || s
}

async function fetchData() {
  loading.value = true
  try {
    const [wps, idx] = await Promise.all([
      listWorkpapers(projectId.value, {
        audit_cycle: filterCycle.value || undefined,
        status: filterStatus.value || undefined,
        assigned_to: filterAssignee.value || undefined,
      }),
      getWpIndex(projectId.value),
    ])
    wpList.value = wps
    wpIndex.value = idx
  } finally {
    loading.value = false
  }
}

async function onNodeClick(data: TreeNode) {
  if (!data.wpId) return
  // Find matching working paper detail
  const wp = wpList.value.find(w => w.wp_index_id === data.wpId || w.id === data.wpId)
  if (wp) {
    selectedWp.value = wp
  } else {
    // Fetch from index info
    const idx = wpIndex.value.find(i => i.id === data.wpId)
    if (idx) {
      selectedWp.value = {
        id: idx.id, project_id: projectId.value, wp_index_id: idx.id,
        file_path: null, source_type: 'template', status: idx.status || 'not_started',
        assigned_to: idx.assigned_to, reviewer: idx.reviewer,
        file_version: 1, last_parsed_at: null, created_at: null, updated_at: null,
        wp_code: idx.wp_code, wp_name: idx.wp_name, audit_cycle: idx.audit_cycle || undefined,
      }
    }
  }
  qcResult.value = null
  annotations.value = []
  // Try to load QC results and annotations
  if (selectedWp.value) {
    try { qcResult.value = await getQCResults(projectId.value, selectedWp.value.id) } catch { /* no QC yet */ }
    await loadAnnotations()
  }
}

function onOnlineEdit() {
  if (!selectedWp.value) return
  router.push({
    name: 'WorkpaperEditor',
    params: { projectId: projectId.value, wpId: selectedWp.value.id },
  })
}

function onDownload() {
  if (!selectedWp.value) return
  window.open(`/api/projects/${projectId.value}/workpapers/${selectedWp.value.id}/download-file`, '_blank')
}

function onUpload() {
  if (!selectedWp.value) return
  uploadFile.value = null
  uploadConflict.value = null
  uploadDialogVisible.value = true
}

function onUploadFileChange(file: any) {
  uploadFile.value = file.raw
}

async function doUpload(forceOverwrite: boolean) {
  if (!selectedWp.value || !uploadFile.value) return
  uploadLoading.value = true
  try {
    const formData = new FormData()
    formData.append('file', uploadFile.value)
    const version = selectedWp.value.file_version || 1
    const resp = await http.post(
      `/api/projects/${projectId.value}/workpapers/${selectedWp.value.id}/upload-file?uploaded_version=${version}&force_overwrite=${forceOverwrite}`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    )
    ElMessage.success(`上传成功，新版本 v${resp.data?.new_version || version + 1}`)
    uploadDialogVisible.value = false
    await fetchData()
  } catch (err: any) {
    if (err.response?.status === 409) {
      uploadConflict.value = err.response.data?.detail || err.response.data
      ElMessage.warning('版本冲突，请选择操作')
    } else {
      ElMessage.error('上传失败')
    }
  } finally {
    uploadLoading.value = false
  }
}

async function onBatchDownload() {
  if (selectedWpIds.value.length === 0) return
  downloadLoading.value = true
  try {
    const resp = await http.post(
      `/api/projects/${projectId.value}/workpapers/download-pack`,
      { wp_ids: selectedWpIds.value, include_prefill: true },
      { responseType: 'blob' }
    )
    const url = window.URL.createObjectURL(new Blob([resp.data]))
    const a = document.createElement('a')
    a.href = url
    a.download = 'workpapers.zip'
    a.click()
    window.URL.revokeObjectURL(url)
    ElMessage.success(`已下载 ${selectedWpIds.value.length} 个底稿`)
  } catch {
    ElMessage.error('批量下载失败')
  } finally {
    downloadLoading.value = false
  }
}

function onCheckChange() {
  if (!treeRef.value) return
  const checked = treeRef.value.getCheckedNodes(true) // leaf only
  selectedWpIds.value = checked.filter((n: any) => n.wpId).map((n: any) => n.wpId)
}

async function onQCCheck() {
  if (!selectedWp.value) return
  qcLoading.value = true
  try {
    qcResult.value = await runQCCheck(projectId.value, selectedWp.value.id)
    ElMessage.success('自检完成')
  } catch {
    ElMessage.error('自检失败')
  } finally {
    qcLoading.value = false
  }
}

async function onSubmitReview() {
  if (!selectedWp.value || hasBlocking.value) return
  try {
    await updateWorkpaperStatus(projectId.value, selectedWp.value.id, 'review_level1_passed')
    ElMessage.success('已提交复核')
    await fetchData()
  } catch {
    ElMessage.error('提交失败')
  }
}

async function loadAnnotations() {
  if (!selectedWp.value) { annotations.value = []; return }
  try {
    const { data } = await http.get(`/api/projects/${projectId.value}/annotations`, {
      params: { object_type: 'workpaper', object_id: selectedWp.value.id },
    })
    annotations.value = Array.isArray(data) ? data : data?.items ?? []
  } catch { annotations.value = [] }
}

async function submitAnnotation() {
  if (!selectedWp.value || !newAnnotation.value.content) return
  try {
    await http.post(`/api/projects/${projectId.value}/annotations`, {
      object_type: 'workpaper',
      object_id: selectedWp.value.id,
      content: newAnnotation.value.content,
      priority: newAnnotation.value.priority,
    })
    ElMessage.success('复核意见已提交')
    showAddAnnotation.value = false
    newAnnotation.value = { content: '', priority: 'medium' }
    await loadAnnotations()
  } catch { ElMessage.error('提交失败') }
}

async function resolveAnnotation(id: string) {
  try {
    await http.put(`/api/annotations/${id}`, { status: 'resolved' })
    ElMessage.success('已标记为解决')
    await loadAnnotations()
  } catch { ElMessage.error('操作失败') }
}

watch([filterCycle, filterStatus, filterAssignee], () => fetchData())
onMounted(fetchData)
</script>

<style scoped>
.gt-wp-list { padding: var(--gt-space-4); height: 100%; display: flex; flex-direction: column; }
.gt-wp-filter-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-3); }
.gt-wp-filters { display: flex; gap: var(--gt-space-2); align-items: center; }
.gt-wp-body { display: flex; gap: var(--gt-space-4); flex: 1; min-height: 0; }
.gt-wp-tree-panel {
  width: 320px; min-width: 320px; background: var(--gt-color-bg-white); border-radius: var(--gt-radius-md);
  box-shadow: var(--gt-shadow-sm); padding: var(--gt-space-3); overflow-y: auto;
}
.gt-wp-detail-panel {
  flex: 1; background: var(--gt-color-bg-white); border-radius: var(--gt-radius-md);
  box-shadow: var(--gt-shadow-sm); padding: var(--gt-space-5); overflow-y: auto;
}
.gt-wp-tree-node { display: flex; align-items: center; gap: 6px; width: 100%; }
.gt-wp-tree-node-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gt-wp-tree-node-tag { flex-shrink: 0; }
.gt-wp-detail-card { }
.gt-wp-detail-title { margin: 0 0 var(--gt-space-4); color: var(--gt-color-primary); font-size: var(--gt-font-size-xl); }
.gt-wp-detail-actions { display: flex; gap: var(--gt-space-2); margin-top: var(--gt-space-4); flex-wrap: wrap; }
.gt-wp-qc-summary-inline { margin-top: var(--gt-space-3); display: flex; align-items: center; gap: var(--gt-space-2); }
.gt-wp-qc-counts { font-size: var(--gt-font-size-sm); color: var(--gt-color-text-secondary); }
</style>
