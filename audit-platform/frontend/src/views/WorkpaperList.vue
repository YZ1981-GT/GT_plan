<template>
  <div class="wp-list-page">
    <!-- 顶部筛选栏 -->
    <div class="wp-filter-bar">
      <h2 class="wp-title">底稿管理</h2>
      <div class="wp-filters">
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
      </div>
    </div>

    <!-- 主体：左树 + 右详情 -->
    <div class="wp-body">
      <!-- 左侧索引树 -->
      <div class="wp-tree-panel">
        <el-tree
          :data="treeData"
          :props="{ label: 'label', children: 'children' }"
          node-key="id"
          highlight-current
          default-expand-all
          @node-click="onNodeClick"
        >
          <template #default="{ data }">
            <div class="tree-node">
              <span class="tree-node-label">{{ data.label }}</span>
              <el-tag v-if="data.status" :type="statusTagType(data.status)" size="small" class="tree-node-tag">
                {{ statusLabel(data.status) }}
              </el-tag>
            </div>
          </template>
        </el-tree>
        <el-empty v-if="!loading && treeData.length === 0" description="暂无底稿" :image-size="80" />
      </div>

      <!-- 右侧详情面板 -->
      <div class="wp-detail-panel">
        <template v-if="selectedWp">
          <div class="detail-card">
            <h3 class="detail-title">{{ selectedWp.wp_code }} {{ selectedWp.wp_name }}</h3>
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
            <div class="detail-actions">
              <el-button type="primary" @click="onOnlineEdit">在线编辑</el-button>
              <el-button @click="onDownload">下载</el-button>
              <el-button @click="onUpload">上传</el-button>
              <el-button type="warning" @click="onQCCheck" :loading="qcLoading">自检</el-button>
              <el-button type="success" @click="onSubmitReview" :disabled="hasBlocking">提交复核</el-button>
            </div>

            <!-- QC 结果摘要 -->
            <div v-if="qcResult" class="qc-summary-inline">
              <el-tag :type="qcResult.passed ? 'success' : 'danger'" size="small">
                {{ qcResult.passed ? '自检通过' : '存在问题' }}
              </el-tag>
              <span class="qc-counts">
                阻断 {{ qcResult.blocking_count }} / 警告 {{ qcResult.warning_count }} / 提示 {{ qcResult.info_count }}
              </span>
            </div>
          </div>
        </template>
        <el-empty v-else description="请从左侧选择底稿" :image-size="120" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
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
const wpList = ref<WorkpaperDetail[]>([])
const wpIndex = ref<WpIndexItem[]>([])
const selectedWp = ref<WorkpaperDetail | null>(null)
const qcResult = ref<QCResult | null>(null)

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

const hasBlocking = computed(() => (qcResult.value?.blocking_count ?? 0) > 0)

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
  // Try to load QC results
  if (selectedWp.value) {
    try {
      qcResult.value = await getQCResults(projectId.value, selectedWp.value.id)
    } catch { /* no QC yet */ }
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
  window.open(`/api/projects/${projectId.value}/working-papers/${selectedWp.value.id}/download`, '_blank')
}

function onUpload() {
  ElMessage.info('上传功能开发中')
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

watch([filterCycle, filterStatus, filterAssignee], () => fetchData())
onMounted(fetchData)
</script>

<style scoped>
.wp-list-page { padding: 16px; height: 100%; display: flex; flex-direction: column; }
.wp-filter-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.wp-title { margin: 0; color: var(--gt-color-primary); font-size: 20px; }
.wp-filters { display: flex; gap: 8px; align-items: center; }
.wp-body { display: flex; gap: 16px; flex: 1; min-height: 0; }
.wp-tree-panel {
  width: 320px; min-width: 320px; background: #fff; border-radius: var(--gt-radius-md);
  box-shadow: var(--gt-shadow-sm); padding: 12px; overflow-y: auto;
}
.wp-detail-panel {
  flex: 1; background: #fff; border-radius: var(--gt-radius-md);
  box-shadow: var(--gt-shadow-sm); padding: 20px; overflow-y: auto;
}
.tree-node { display: flex; align-items: center; gap: 6px; width: 100%; }
.tree-node-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tree-node-tag { flex-shrink: 0; }
.detail-card { }
.detail-title { margin: 0 0 16px; color: var(--gt-color-primary); font-size: 18px; }
.detail-actions { display: flex; gap: 8px; margin-top: 16px; flex-wrap: wrap; }
.qc-summary-inline { margin-top: 12px; display: flex; align-items: center; gap: 8px; }
.qc-counts { font-size: 13px; color: #666; }
</style>
