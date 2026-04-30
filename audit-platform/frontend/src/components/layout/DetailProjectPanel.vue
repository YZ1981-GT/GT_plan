<template>
  <div class="gt-detail-panel">
    <template v-if="project">
      <!-- Tab 页签 -->
      <el-tabs v-model="activeTab" class="gt-detail-tabs">
        <!-- 项目概览 -->
        <el-tab-pane label="概览" name="overview">
          <div class="gt-detail-section">
            <div class="gt-title-row">
              <h3 class="gt-detail-title">{{ project.name }}</h3>
              <el-button size="small" type="primary" @click="editProject">
                <el-icon><Edit /></el-icon> 编辑
              </el-button>
            </div>
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="客户名称">{{ project.client_name || '-' }}</el-descriptions-item>
              <el-descriptions-item label="项目类型">
                <el-tag size="small">{{ typeLabel(project.project_type) }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="当前状态">
                <el-tag :type="statusTagType(project.status)" size="small">
                  {{ statusLabel(project.status) }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="创建时间">{{ formatDate(project.created_at) }}</el-descriptions-item>
            </el-descriptions>
          </div>

          <!-- 快捷入口 -->
          <div class="gt-detail-section">
            <h4 class="gt-section-label">快捷操作</h4>
            <div class="gt-quick-grid">
              <div class="gt-quick-btn" @click="goTo('trial-balance')">
                <el-icon :size="20" color="var(--gt-color-primary)"><DataLine /></el-icon>
                <span>试算表</span>
              </div>
              <div class="gt-quick-btn" @click="goTo('adjustments')">
                <el-icon :size="20" color="var(--gt-color-teal)"><Edit /></el-icon>
                <span>调整分录</span>
              </div>
              <div class="gt-quick-btn" @click="goTo('workpapers')">
                <el-icon :size="20" color="var(--gt-color-primary-light)"><Document /></el-icon>
                <span>底稿</span>
              </div>
              <div class="gt-quick-btn" @click="goTo('reports')">
                <el-icon :size="20" color="var(--gt-color-success)"><TrendCharts /></el-icon>
                <span>报表</span>
              </div>
              <div class="gt-quick-btn" @click="goTo('disclosure-notes')">
                <el-icon :size="20" color="var(--gt-color-wheat)"><Notebook /></el-icon>
                <span>附注</span>
              </div>
              <div class="gt-quick-btn" @click="goTo('materiality')">
                <el-icon :size="20" color="var(--gt-color-coral)"><Aim /></el-icon>
                <span>重要性</span>
              </div>
              <div class="gt-quick-btn" @click="goToLedgerImport()">
                <el-icon :size="20" color="var(--gt-color-primary-dark)"><Upload /></el-icon>
                <span>账套导入</span>
              </div>
              <div class="gt-quick-btn" @click="goTo('ledger')">
                <el-icon :size="20" color="var(--gt-color-primary-dark)"><Search /></el-icon>
                <span>查账</span>
              </div>
              <div class="gt-quick-btn gt-quick-btn--danger" @click="handleResetImport" title="清除卡住的导入任务，释放导入锁">
                <el-icon :size="20" color="#f56c6c"><RefreshRight /></el-icon>
                <span>重置</span>
              </div>
              <div class="gt-quick-btn" @click="onCreateNextYear" title="一键创建当年项目（继承上年配置）">
                <el-icon :size="20" color="var(--gt-color-success)"><CopyDocument /></el-icon>
                <span>创建下年</span>
              </div>
              <div class="gt-quick-btn" @click="showTeamAssign = true" title="为项目分配团队成员">
                <el-icon :size="20" color="var(--gt-color-primary)"><User /></el-icon>
                <span>人员委派</span>
              </div>
              <div
                v-if="project.report_scope === 'consolidated'"
                class="gt-quick-btn"
                @click="goTo('workpaper-summary')"
              >
                <el-icon :size="20" color="var(--gt-color-teal)"><Grid /></el-icon>
                <span>底稿汇总</span>
              </div>
            </div>
          </div>
        </el-tab-pane>

        <!-- 关键指标 -->
        <el-tab-pane label="指标" name="metrics">
          <div class="gt-metrics-grid">
            <div class="gt-metric-card">
              <span class="gt-metric-value">-</span>
              <span class="gt-metric-label">底稿完成率</span>
            </div>
            <div class="gt-metric-card">
              <span class="gt-metric-value">-</span>
              <span class="gt-metric-label">复核完成率</span>
            </div>
            <div class="gt-metric-card">
              <span class="gt-metric-value">-</span>
              <span class="gt-metric-label">AJE数量</span>
            </div>
            <div class="gt-metric-card">
              <span class="gt-metric-value">-</span>
              <span class="gt-metric-label">RJE数量</span>
            </div>
          </div>
          <p class="gt-placeholder-text">指标数据将在选择项目后加载</p>
        </el-tab-pane>

        <!-- 底稿索引 -->
        <el-tab-pane label="底稿" name="workpapers" lazy>
          <div v-if="wpTree.length" class="gt-wp-tree">
            <el-tree :data="wpTree" :props="{ label: 'label', children: 'children' }" default-expand-all>
              <template #default="{ data }">
                <span class="gt-wp-node">
                  <span>{{ data.label }}</span>
                  <el-tag v-if="data.count" size="small" type="info">{{ data.count }}</el-tag>
                </span>
              </template>
            </el-tree>
          </div>
          <el-empty v-else description="暂无底稿索引" :image-size="60">
            <el-button size="small" type="primary" @click="goTo('workpapers')">查看底稿</el-button>
          </el-empty>
        </el-tab-pane>

        <!-- 试算表预览 -->
        <el-tab-pane label="试算表" name="trial-balance" lazy>
          <el-table v-if="trialBalanceRows.length" :data="trialBalanceRows" size="small" stripe max-height="400">
            <el-table-column prop="standard_account_code" label="科目" width="100" />
            <el-table-column prop="account_name" label="名称" min-width="140" />
            <el-table-column label="未审数" width="110" align="right">
              <template #default="{ row }">{{ fmtAmt(row.unadjusted_amount) }}</template>
            </el-table-column>
            <el-table-column label="审定数" width="110" align="right">
              <template #default="{ row }">{{ fmtAmt(row.audited_amount) }}</template>
            </el-table-column>
          </el-table>
          <el-empty v-else description="暂无试算表数据" :image-size="60">
            <el-button size="small" type="primary" @click="goTo('trial-balance')">查看试算表</el-button>
          </el-empty>
        </el-tab-pane>

        <!-- 报表预览 -->
        <el-tab-pane label="报表" name="reports" lazy>
          <div class="gt-report-links">
            <div class="gt-report-card" @click="goTo('reports')">
              <el-icon :size="24" color="var(--gt-color-primary)"><DataLine /></el-icon>
              <span>资产负债表</span>
            </div>
            <div class="gt-report-card" @click="goTo('reports')">
              <el-icon :size="24" color="var(--gt-color-teal)"><TrendCharts /></el-icon>
              <span>利润表</span>
            </div>
            <div class="gt-report-card" @click="goTo('reports')">
              <el-icon :size="24" color="var(--gt-color-success)"><Coin /></el-icon>
              <span>现金流量表</span>
            </div>
            <div class="gt-report-card" @click="goTo('reports')">
              <el-icon :size="24" color="var(--gt-color-wheat)"><PieChart /></el-icon>
              <span>权益变动表</span>
            </div>
          </div>
        </el-tab-pane>

        <!-- 查账（穿透查询） -->
        <el-tab-pane label="查账" name="ledger" lazy>
          <div class="gt-ledger-entry">
            <el-icon :size="40" color="var(--gt-color-primary)"><Search /></el-icon>
            <h4 style="margin: 12px 0 8px; color: var(--gt-color-text)">账证联动查询</h4>
            <p style="color: var(--gt-color-text-secondary); font-size: 13px; margin-bottom: 16px; text-align: center">
              建项后可先独立导入账套数据，再从科目余额表逐级穿透到序时账、凭证、辅助账
            </p>
            <el-button type="primary" @click="goToLedgerImport()">
              <el-icon><Upload /></el-icon> 账套导入
            </el-button>
            <el-button @click="goTo('ledger')">
              <el-icon><Search /></el-icon> 进入查账
            </el-button>
          </div>
        </el-tab-pane>

        <!-- 附件管理 -->
        <el-tab-pane label="附件" name="attachments" lazy>
          <div class="gt-attachment-section">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px">
              <h4 style="margin: 0; color: var(--gt-color-text)">项目附件</h4>
              <el-button type="primary" size="small" @click="goTo('attachments')">
                <el-icon><Paperclip /></el-icon> 管理附件
              </el-button>
            </div>
            <el-table v-if="attachmentList.length" :data="attachmentList" size="small" stripe max-height="300">
              <el-table-column prop="file_name" label="文件名" min-width="180" show-overflow-tooltip />
              <el-table-column prop="file_type" label="类型" width="80" />
              <el-table-column prop="attachment_type" label="分类" width="80">
                <template #default="{ row }">
                  <el-tag size="small">{{ attachTypeLabel(row.attachment_type) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="大小" width="80">
                <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
              </el-table-column>
            </el-table>
            <el-empty v-else description="暂无附件" :image-size="50">
              <el-button size="small" type="primary" @click="goTo('attachments')">上传附件</el-button>
            </el-empty>
          </div>
        </el-tab-pane>
      </el-tabs>
    </template>

    <!-- 未选择项目 -->
    <div v-else class="gt-empty-state">
      <el-empty description="请从左侧选择一个项目" :image-size="100" />
    </div>

    <!-- 人员委派弹窗 -->
    <el-dialog v-model="showTeamAssign" title="人员委派" width="900px" append-to-body destroy-on-close>
      <div style="min-height: 500px;">
        <TeamAssignmentStep v-if="showTeamAssign" :project-id="project.id" />
      </div>
      <template #footer>
        <el-button @click="showTeamAssign = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  DataLine, Edit, Document, TrendCharts, Notebook, Aim, Coin, PieChart, Search, Grid, Paperclip, CopyDocument, Upload, RefreshRight, User,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import TeamAssignmentStep from '@/components/wizard/TeamAssignmentStep.vue'

const props = defineProps<{ project: any | null }>()
const router = useRouter()
const activeTab = ref('overview')
const showTeamAssign = ref(false)
const projectYear = computed(() => Number(props.project?.audit_year) || new Date().getFullYear())

// 底稿索引树
const wpTree = ref<any[]>([])
// 试算表预览
const trialBalanceRows = ref<any[]>([])
// 附件列表
const attachmentList = ref<any[]>([])

// 选中项目变化时加载数据
watch(() => props.project?.id, async (newId) => {
  if (!newId) { wpTree.value = []; trialBalanceRows.value = []; return }
  // 加载底稿索引树（致同编码体系）
  try {
    const data = await api.get('/api/gt-coding/tree')
    const tree = data ?? []
    wpTree.value = tree.map((group: any) => ({
      label: group.label,
      count: group.children?.length || 0,
      children: (group.children || []).map((c: any) => ({
        label: `${c.code_range} ${c.cycle_name}`,
      })),
    }))
  } catch { wpTree.value = [] }
  // 加载试算表预览（前20行）
  try {
    const data = await api.get(`/api/projects/${newId}/trial-balance`, { params: { year: projectYear.value } })
    const rows = data ?? []
    trialBalanceRows.value = rows.slice(0, 20)
  } catch { trialBalanceRows.value = [] }
  // 加载附件列表（前10条，静默失败）
  try {
    const data = await api.get(`/api/projects/${newId}/attachments`, {
      params: { page_size: 10 },
      validateStatus: (s: number) => s < 600,
    })
    if (data) {
      attachmentList.value = Array.isArray(data) ? data.slice(0, 10) : (data?.items ?? []).slice(0, 10)
    } else {
      attachmentList.value = []
    }
  } catch { attachmentList.value = [] }
}, { immediate: true })

function goTo(page: string) {
  if (!props.project) return
  router.push({
    path: `/projects/${props.project.id}/${page}`,
    query: { year: String(projectYear.value) },
  })
}

function goToLedgerImport() {
  if (!props.project) return
  router.push({ path: `/projects/${props.project.id}/ledger`, query: { import: '1' } })
}

async function handleResetImport() {
  if (!props.project) return
  try {
    await ElMessageBox.confirm(
      '将清除当前项目卡住的导入任务，释放导入锁，并刷新页面。\n已入库的数据不受影响。',
      '确认重置',
      { confirmButtonText: '确认', cancelButtonText: '取消', type: 'warning' },
    )
    await api.post(`/api/projects/${props.project.id}/account-chart/import-reset`, null, {
      params: { force: true },
    })
    window.location.reload()
  } catch (e: any) {
    if (e !== 'cancel' && e?.toString() !== 'cancel') {
      const detail = e?.response?.data?.detail
      if (detail?.code === 'IMPORT_RESET_JOB_ID_REQUIRED') {
        ElMessage.warning('请在导入历史中选择具体作业后重置，或由管理员执行项目级强制重置。')
      } else {
        // 即使 API 失败也刷新，防止前端状态残留
        window.location.reload()
      }
    }
  }
}

function editProject() {
  if (!props.project) return
  router.push(`/projects/new?projectId=${props.project.id}`)
}

async function onCreateNextYear() {
  if (!props.project) return
  try {
    await ElMessageBox.confirm(
      `确定要基于「${props.project.name}」创建下年项目吗？将继承科目映射、团队委派、试算表审定数等配置。`,
      '创建下年项目',
      { confirmButtonText: '确定创建', cancelButtonText: '取消', type: 'info' },
    )
    const data = await api.post(`/api/projects/${props.project.id}/create-next-year`)
    const result = data
    ElMessage.success(`已创建下年项目，新项目ID: ${result.new_project_id?.slice(0, 8)}...`)
    router.push(`/projects/new?projectId=${result.new_project_id}`)
  } catch (err: any) {
    if (err !== 'cancel') {
      ElMessage.error(err?.response?.data?.detail || '创建失败')
    }
  }
}

function fmtAmt(v: any): string {
  const n = Number(v)
  if (!n) return '-'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function typeLabel(t: string) {
  const m: Record<string, string> = { annual: '年度审计', special: '专项审计', ipo: 'IPO审计', internal_control: '内控审计' }
  return m[t] || t || '-'
}
function statusTagType(s: string) {
  const m: Record<string, string> = { created: 'info', planning: 'warning', execution: '', completion: 'success', archived: 'info' }
  return m[s] || 'info'
}
function statusLabel(s: string) {
  const m: Record<string, string> = { created: '已创建', planning: '计划中', execution: '执行中', completion: '已完成', archived: '已归档' }
  return m[s] || s || '-'
}
function formatDate(d: string) {
  if (!d) return '-'
  return new Date(d).toLocaleDateString('zh-CN')
}

function attachTypeLabel(t: string) {
  const m: Record<string, string> = {
    general: '通用', workpaper: '底稿', confirmation: '函证',
    contract: '合同', evidence: '证据', report: '报告',
  }
  return m[t] || t || '通用'
}

function formatSize(bytes: number) {
  if (!bytes) return '-'
  if (bytes < 1024) return bytes + 'B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + 'KB'
  return (bytes / 1024 / 1024).toFixed(1) + 'MB'
}
</script>

<style scoped>
.gt-detail-panel { height: 100%; display: flex; flex-direction: column; }
.gt-detail-tabs { flex: 1; display: flex; flex-direction: column; }
.gt-detail-tabs :deep(.el-tabs__header) {
  padding: 0 var(--gt-space-4);
  margin-bottom: 0;
  border-bottom: 1px solid var(--gt-color-border-light);
}
.gt-detail-tabs :deep(.el-tabs__content) {
  flex: 1; overflow-y: auto; padding: var(--gt-space-4);
}

.gt-detail-section { margin-bottom: var(--gt-space-5); }
.gt-detail-title {
  font-size: var(--gt-font-size-xl); font-weight: 700;
  color: var(--gt-color-primary-dark); margin-bottom: var(--gt-space-3);
}
.gt-title-row {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: var(--gt-space-3);
}
.gt-title-row .gt-detail-title { margin-bottom: 0; }
.gt-section-label {
  font-size: var(--gt-font-size-sm); font-weight: 600;
  color: var(--gt-color-text-secondary); margin-bottom: var(--gt-space-2);
}

.gt-quick-grid {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--gt-space-2);
}
.gt-quick-btn {
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  padding: var(--gt-space-3); border-radius: var(--gt-radius-sm);
  cursor: pointer; transition: all var(--gt-transition-fast);
  border: 1px solid transparent; font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-secondary);
}
.gt-quick-btn:hover {
  background: var(--gt-color-primary-bg);
  border-color: var(--gt-color-primary-lighter);
  color: var(--gt-color-primary);
}

.gt-metrics-grid {
  display: grid; grid-template-columns: repeat(2, 1fr); gap: var(--gt-space-3);
}
.gt-metric-card {
  text-align: center; padding: var(--gt-space-4);
  background: var(--gt-color-bg); border-radius: var(--gt-radius-sm);
}
.gt-metric-value {
  display: block; font-size: var(--gt-font-size-2xl); font-weight: 700;
  color: var(--gt-color-primary);
}
.gt-metric-label {
  display: block; font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-secondary); margin-top: 2px;
}

.gt-placeholder-text {
  color: var(--gt-color-text-tertiary); font-size: var(--gt-font-size-sm);
  text-align: center; padding: var(--gt-space-8) 0;
}

.gt-empty-state {
  flex: 1; display: flex; align-items: center; justify-content: center;
}

/* 底稿索引树 */
.gt-wp-tree { padding: var(--gt-space-2) 0; }
.gt-wp-node { display: flex; align-items: center; gap: var(--gt-space-2); }

/* 报表卡片 */
.gt-report-links { display: grid; grid-template-columns: repeat(2, 1fr); gap: var(--gt-space-3); }
.gt-report-card {
  display: flex; flex-direction: column; align-items: center; gap: var(--gt-space-2);
  padding: var(--gt-space-4); border-radius: var(--gt-radius-md);
  border: 1px solid var(--gt-color-border-light); cursor: pointer;
  transition: all var(--gt-transition-fast); font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-secondary);
}
.gt-report-card:hover {
  border-color: var(--gt-color-primary-lighter);
  background: var(--gt-color-primary-bg);
  color: var(--gt-color-primary);
}

/* 查账入口 */
.gt-ledger-entry {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; padding: var(--gt-space-8) var(--gt-space-4);
}
</style>
