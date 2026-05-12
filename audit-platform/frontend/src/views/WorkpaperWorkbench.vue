<template>
  <div class="gt-wp-bench gt-fade-in">
    <!-- 页面横幅 -->
    <div class="gt-wpb-banner">
      <div class="gt-wpb-banner-text">
        <el-button text style="color: #fff; font-size: 13px; padding: 0; margin-right: 8px" @click="router.push('/projects')">← 返回</el-button>
        <div>
          <h2>底稿工作台</h2>
          <p>{{ mappings.length }} 个底稿映射，覆盖试算表与附注</p>
        </div>
      </div>
      <div class="gt-wpb-banner-actions">
        <el-button size="small" @click="refreshAll" :loading="loading" round>刷新</el-button>
        <el-button size="small" @click="onBatchPrefill" :loading="prefillLoading" round>批量预填充</el-button>
        <el-button size="small" @click="onSmartRecommend" :loading="recommendLoading" round>
          智能推荐底稿
        </el-button>
      </div>
    </div>
    <!-- 推荐面板 -->
    <div v-if="recommendations.length > 0" class="gt-wpb-recommend-panel gt-fade-in">
      <div class="gt-wpb-recommend-header">
        <h4 class="gt-wpb-section-title">
          智能推荐
          <el-badge :value="recommendations.length" :max="99" type="primary" style="margin-left: 6px" />
        </h4>
        <el-button size="small" text @click="recommendations = []">收起</el-button>
        <el-button size="small" type="primary" @click="onGenerateRecommended" :loading="generatingWps">
          一键生成推荐底稿
        </el-button>
      </div>
      <div class="gt-wpb-recommend-list">
        <div v-for="rec in recommendations" :key="rec.wp_code" class="gt-wpb-recommend-item">
          <div class="gt-wpb-rec-left">
            <span class="gt-wpb-rec-code">{{ rec.wp_code }}</span>
            <span class="gt-wpb-rec-name">{{ rec.wp_name || rec.account_name }}</span>
          </div>
          <div class="gt-wpb-rec-right">
            <el-tag size="small" :type="rec.priority === 'required' ? 'danger' : 'info'" round>
              {{ rec.priority === 'required' ? '必编' : '建议' }}
            </el-tag>
            <span class="gt-wpb-rec-reason">{{ rec.reason }}</span>
          </div>
        </div>
      </div>
    </div>
    <div class="gt-wpb-body">
      <!-- 左栏：按循环分组底稿树 -->
      <div class="gt-wpb-tree">
        <div class="gt-wpb-tree-header">
          <el-input v-model="searchText" placeholder="搜索底稿..." size="small" clearable />
          <div class="gt-wpb-tree-filters">
            <el-checkbox v-model="onlyMine" size="small">仅我的</el-checkbox>
            <el-select v-model="filterStatus" size="small" placeholder="状态" clearable style="width: 80px">
              <el-option label="待编" value="pending" />
              <el-option label="编制中" value="in_progress" />
              <el-option label="复核中" value="review" />
              <el-option label="已通过" value="passed" />
            </el-select>
          </div>
          <!-- 进度概览 -->
          <div class="gt-wpb-tree-progress">
            <span class="gt-wpb-prog-item gt-wpb-prog--done">{{ doneCount }}</span>
            <span class="gt-wpb-prog-sep">/</span>
            <span class="gt-wpb-prog-item">{{ totalCount }}</span>
            <el-progress :percentage="progressPct" :stroke-width="4" :show-text="false" style="flex:1; margin-left: 8px" />
          </div>
        </div>
        <el-tree
          :data="treeData"
          :props="{ label: 'label', children: 'children' }"
          node-key="id"
          highlight-current
          default-expand-all
          :filter-node-method="filterNode"
          ref="treeRef"
          @node-click="onNodeClick"
        >
          <template #default="{ data }">
            <div class="gt-wpb-node">
              <span class="gt-wpb-node-icon" v-if="data.statusIcon">{{ data.statusIcon }}</span>
              <span class="gt-wpb-node-label">{{ data.label }}</span>
              <span v-if="data.assignee" class="gt-wpb-node-assignee">{{ data.assignee }}</span>
            </div>
          </template>
        </el-tree>
      </div>
      <!-- 中栏：底稿详情预览 -->
      <div class="gt-wpb-detail">
        <template v-if="selectedMapping">
          <div class="gt-wpb-detail-header">
            <div class="gt-wpb-detail-title-row">
              <h3>{{ selectedMapping.wp_code }} {{ selectedMapping.wp_name }}</h3>
              <el-tag :type="selectedMapping.note_section ? 'success' : 'info'" size="small" effect="plain" round>
                {{ selectedMapping.account_name }}
              </el-tag>
            </div>
            <div class="gt-wpb-detail-tags">
              <el-tag size="small" round>{{ selectedMapping.cycle }}循环</el-tag>
              <el-tag v-if="selectedMapping.report_row" size="small" type="info" round>报表行 {{ selectedMapping.report_row }}</el-tag>
              <el-tag v-if="selectedMapping.note_section" size="small" type="warning" round>附注 {{ selectedMapping.note_section }}</el-tag>
            </div>
          </div>
          <!-- 流程步骤指示 -->
          <div class="gt-wpb-workflow">
            <div class="gt-wpb-step" :class="{ 'gt-wpb-step--done': true }">
              <div class="gt-wpb-step-dot"></div>
              <span>创建</span>
            </div>
            <div class="gt-wpb-step-line"></div>
            <div class="gt-wpb-step" :class="{ 'gt-wpb-step--done': !!prefillData }">
              <div class="gt-wpb-step-dot"></div>
              <span>预填充</span>
            </div>
            <div class="gt-wpb-step-line"></div>
            <div class="gt-wpb-step" :class="{ 'gt-wpb-step--active': !!prefillData }">
              <div class="gt-wpb-step-dot"></div>
              <span>编制底稿</span>
            </div>
            <div class="gt-wpb-step-line"></div>
            <div class="gt-wpb-step">
              <div class="gt-wpb-step-dot"></div>
              <span>复核</span>
            </div>
            <div class="gt-wpb-step-line"></div>
            <div class="gt-wpb-step">
              <div class="gt-wpb-step-dot"></div>
              <span>归档</span>
            </div>
          </div>
          <!-- 科目指标卡片 -->
          <div class="gt-wpb-data-section">
            <h4 class="gt-wpb-section-title">试算表数据</h4>
            <div v-if="prefillData" class="gt-wpb-prefill-cards gt-stagger">
              <div class="gt-wpb-prefill-card gt-wpb-prefill-card--muted">
                <span class="gt-wpb-pf-label">期初余额</span>
                <span class="gt-wpb-pf-value">{{ fmtAmt(totalOpening) }}</span>
              </div>
              <div class="gt-wpb-prefill-card gt-wpb-prefill-card--primary">
                <span class="gt-wpb-pf-label">未审数</span>
                <span class="gt-wpb-pf-value">{{ fmtAmt(prefillData.total_unadjusted) }}</span>
              </div>
              <div class="gt-wpb-prefill-card gt-wpb-prefill-card--teal">
                <span class="gt-wpb-pf-label">调整影响</span>
                <span class="gt-wpb-pf-value" :class="{ 'gt-wpb-pf-value--diff': totalAdj !== '0' }">{{ fmtAmt(totalAdj) }}</span>
              </div>
              <div class="gt-wpb-prefill-card gt-wpb-prefill-card--success">
                <span class="gt-wpb-pf-label">审定数</span>
                <span class="gt-wpb-pf-value">{{ fmtAmt(prefillData.total_audited) }}</span>
              </div>
            </div>
            <el-skeleton v-else-if="prefillLoading" :rows="2" animated />
            <!-- 科目明细表 -->
            <el-table v-if="prefillData?.accounts?.length" :data="prefillData.accounts" size="small" border stripe style="margin-top: 12px" class="gt-wpb-acct-table">
              <el-table-column prop="code" label="科目编码" width="90" />
              <el-table-column prop="name" label="科目名称" min-width="120" show-overflow-tooltip />
              <el-table-column label="期初余额" width="110" align="right">
                <template #default="{ row }">{{ fmtAmt(row.opening) }}</template>
              </el-table-column>
              <el-table-column label="未审数" width="110" align="right">
                <template #default="{ row }">{{ fmtAmt(row.unadjusted) }}</template>
              </el-table-column>
              <el-table-column label="调整额" width="90" align="right">
                <template #default="{ row }">
                  <span :style="{ color: adjVal(row) !== 0 ? '#FF5149' : '#999' }">{{ fmtAmt(adjVal(row)) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="审定数" width="110" align="right">
                <template #default="{ row }">
                  <span style="font-weight: 700; color: var(--gt-color-primary); cursor: pointer; text-decoration: underline dotted"
                    @dblclick="onDrillToAdjustment(row)"
                    title="双击查看调整分录">{{ fmtAmt(row.audited) }}</span>
                </template>
              </el-table-column>
            </el-table>
          </div>
          <!-- 附件区域 -->
          <div class="gt-wpb-data-section">
            <h4 class="gt-wpb-section-title">关联附件</h4>
            <div class="gt-wpb-attach-list" v-if="attachments.length">
              <div v-for="att in attachments" :key="att.id" class="gt-wpb-attach-item">
                <div class="gt-wpb-attach-icon">{{ getFileIcon(att.file_type) }}</div>
                <div class="gt-wpb-attach-info">
                  <span class="gt-wpb-attach-name">{{ att.file_name }}</span>
                  <span class="gt-wpb-attach-meta">
                    {{ att.attachment_type || '通用' }}  {{ formatSize(att.file_size) }}
                    <OcrStatusBadge v-if="att.ocr_status" :status="getOcrStatus(att)" />
                  </span>
                </div>
                <el-button size="small" text type="primary" @click="onPreviewAttachment(att.id)">预览</el-button>
              </div>
            </div>
            <div v-else class="gt-wpb-attach-empty">
              <span>暂无关联附件</span>
            </div>
            <div class="gt-wpb-attach-actions">
              <el-upload
                :show-file-list="false"
                :auto-upload="false"
                :on-change="onAttachFileSelect"
                accept=".pdf,.jpg,.jpeg,.png,.doc,.docx,.xls,.xlsx"
                style="display: inline-block"
              >
                <el-button size="small" round>
                  <el-icon style="margin-right: 4px"><Paperclip /></el-icon>上传并关联
                </el-button>
              </el-upload>
              <el-button size="small" @click="onManageAttachments" round>管理全部附件</el-button>
            </div>
          </div>
          <!-- 操作按钮 -->
          <div class="gt-wpb-actions">
            <el-button type="primary" @click="onOpenWorkpaper" round>
              <el-icon style="margin-right: 4px"><EditPen /></el-icon>编辑底稿
            </el-button>
            <el-button @click="showAssignDialog = true" round>分配委派</el-button>
            <el-button @click="onGoTrialBalance" round>查看试算表</el-button>
            <el-button v-if="selectedMapping.note_section" @click="onGoNote" round>查看附注</el-button>
            <el-button @click="onGoLedger" round>查看序时账</el-button>
          </div>
          <!-- 底稿委派弹窗 -->
          <el-dialog v-model="showAssignDialog" title="底稿委派" width="420" append-to-body>
            <el-form label-width="70px">
              <el-form-item label="编制人">
                <el-select v-model="assignForm.assigned_to" filterable clearable placeholder="选择编制人" style="width: 100%">
                  <el-option v-for="s in staffList" :key="s.id" :label="s.name" :value="s.user_id || s.id" />
                </el-select>
              </el-form-item>
              <el-form-item label="复核人">
                <el-select v-model="assignForm.reviewer" filterable clearable placeholder="选择复核人" style="width: 100%">
                  <el-option v-for="s in staffList" :key="s.id" :label="s.name" :value="s.user_id || s.id" />
                </el-select>
              </el-form-item>
            </el-form>
            <template #footer>
              <el-button @click="showAssignDialog = false">取消</el-button>
              <el-button type="primary" @click="onConfirmAssign" :loading="assignLoading">确认分配</el-button>
            </template>
          </el-dialog>
          <!-- 上年数据参照 -->
          <div class="gt-wpb-data-section" v-if="priorYearData">
            <h4 class="gt-wpb-section-title">上年数据参照</h4>
            <div class="gt-wpb-prior-cards">
              <div class="gt-wpb-prior-card">
                <span class="gt-wpb-prior-label">{{ year - 1 }}年审定数</span>
                <span class="gt-wpb-prior-value">{{ fmtAmt(priorYearData.total_audited) }}</span>
              </div>
              <div class="gt-wpb-prior-card">
                <span class="gt-wpb-prior-label">同比变动</span>
                <span class="gt-wpb-prior-value" :class="{ 'gt-wpb-prior-diff': yoyChange !== 0 }">
                  {{ yoyChange > 0 ? '+' : '' }}{{ fmtAmt(yoyChange) }}
                </span>
              </div>
            </div>
          </div>
        </template>
        <div v-else class="gt-wpb-empty-state">
          <div class="gt-wpb-empty-icon">📋</div>
          <h4>请选择底稿查看详情</h4>
          <p>点击左侧底稿树，查看科目数据与审计要点</p>
        </div>
      </div>
      <!-- 右栏：AI 审计助手 -->
      <div class="gt-wpb-ai">
        <h4 class="gt-wpb-section-title">AI 审计助手</h4>
        <div v-if="selectedMapping" class="gt-wpb-ai-content">
          <div class="gt-wpb-ai-hint">
            <el-icon style="color: var(--gt-color-primary); margin-right: 6px"><MagicStick /></el-icon>
            按 {{ selectedMapping.account_name }} 审计要点
          </div>
          <!-- AI 变动分析不可用提示 -->
          <div v-if="aiAnalysis?.unavailable" class="gt-wpb-ai-unavailable">
            <el-icon><WarningFilled /></el-icon>
            <span>{{ aiAnalysis.message }}</span>
          </div>
          <!-- AI 变动分析 -->
          <div v-else-if="aiAnalysis" class="gt-wpb-ai-analysis gt-fade-in">
            <div class="gt-wpb-ai-analysis-header">
              <span class="gt-wpb-ai-analysis-badge">AI 变动分析</span>
              <span v-if="aiAnalysis.change_rate !== null" :class="Math.abs(aiAnalysis.change_rate) > 20 ? 'gt-wpb-ai-sig' : 'gt-wpb-ai-normal'">
                {{ aiAnalysis.change_rate > 0 ? '+' : '' }}{{ aiAnalysis.change_rate }}%
              </span>
            </div>
            <p class="gt-wpb-ai-analysis-text">{{ aiAnalysis.ai_analysis }}</p>
          </div>
          <el-skeleton v-else-if="aiLoading" :rows="2" animated style="margin-bottom: 12px" />
          <div class="gt-wpb-ai-tips">
            <div class="gt-wpb-ai-tip" v-for="(tip, i) in auditTips" :key="i">
              <span class="gt-wpb-ai-tip-num">{{ i + 1 }}</span>
              <span>{{ tip }}</span>
            </div>
          </div>
          <!-- [R9 F8 Task 29] AI 对话已移至 WorkpaperSidePanel AI Tab，此处仅保留入口提示 -->
          <div class="gt-wpb-ai-hint" style="margin-top: 12px; padding: 12px; background: #f9f7fb; border-radius: 8px; text-align: center; color: #666; font-size: 13px;">
            💡 AI 助手已整合到底稿编辑器侧面板，请在编辑器中使用 AI Tab 获取智能辅助
          </div>
          <!-- 审计程序检查清单 -->
          <div class="gt-wpb-checklist" v-if="auditChecklist.length">
            <h4 class="gt-wpb-section-title" style="margin-top: 20px">审计程序检查清单</h4>
            <div v-for="(item, i) in auditChecklist" :key="i" class="gt-wpb-check-item" @click="item.done = !item.done">
              <el-checkbox v-model="item.done" size="small" />
              <span :class="{ 'gt-wpb-check-done': item.done }">{{ item.label }}</span>
            </div>
            <div class="gt-wpb-check-progress">
              {{ auditChecklist.filter(c => c.done).length }} / {{ auditChecklist.length }} 已完成
            </div>
          </div>
        </div>
        <el-empty v-else description="选择底稿后显示审计要点" :image-size="60" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { MagicStick, EditPen, Paperclip, WarningFilled } from '@element-plus/icons-vue'
import { getAllWpMappings, getWpPrefillData, getWpRecommendations, type WpAccountMapping, type WpPrefillData, type WpRecommendation } from '@/services/workpaperApi'
import { getProjectAuditYear } from '@/services/auditPlatformApi'
import { api } from '@/services/apiProxy'
import { workpapers as P_wp, attachments as P_att, wpAI as P_wpai, staff as P_staff } from '@/services/apiPaths'
import { fmtAmount } from '@/utils/formatters'
import OcrStatusBadge from '@/components/common/OcrStatusBadge.vue'
import { handleApiError } from '@/utils/errorHandler'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.projectId as string)
const year = ref(new Date().getFullYear())

const loading = ref(false)
const prefillLoading = ref(false)
const mappings = ref<WpAccountMapping[]>([])
const selectedMapping = ref<WpAccountMapping | null>(null)
const prefillData = ref<WpPrefillData | null>(null)
const searchText = ref('')
const treeRef = ref<any>(null)
const aiQuestion = ref('')
const onlyMine = ref(false)
const filterStatus = ref('')
const attachments = ref<any[]>([])
const aiLoading = ref(false)
const aiAnalysis = ref<any>(null)
const aiAsking = ref(false)
const aiAnswer = ref('')
const priorYearData = ref<WpPrefillData | null>(null)
const recommendations = ref<WpRecommendation[]>([])
const recommendLoading = ref(false)
const generatingWps = ref(false)

// 底稿委派
const showAssignDialog = ref(false)
const assignLoading = ref(false)
const staffList = ref<Array<{ id: string; name: string; user_id?: string }>>([])
const assignForm = reactive({ assigned_to: '', reviewer: '' })

const yoyChange = computed(() => {
  if (!prefillData.value || !priorYearData.value) return 0
  return (parseFloat(prefillData.value.total_audited) || 0) - (parseFloat(priorYearData.value.total_audited) || 0)
})

// 从底稿列表获取实际状态
const wpStatusMap = ref<Record<string, { status: string; review_status: string; assigned_to?: string }>>({})
const totalCount = computed(() => mappings.value.length)
const doneCount = computed(() => {
  return Object.values(wpStatusMap.value).filter(
    w => w.status === 'review_passed' || w.status === 'archived' ||
         w.review_status === 'level1_passed' || w.review_status === 'level2_passed'
  ).length
})
const progressPct = computed(() => totalCount.value > 0 ? Math.round(doneCount.value / totalCount.value * 100) : 0)

// 计算属性
const totalOpening = computed(() => {
  if (!prefillData.value?.accounts) return '0'
  return String(prefillData.value.accounts.reduce((s, a) => s + (parseFloat(a.opening) || 0), 0))
})
const totalAdj = computed(() => {
  if (!prefillData.value?.accounts) return '0'
  const total = prefillData.value.accounts.reduce((s, a) => s + (parseFloat(a.rje) || 0) + (parseFloat(a.aje) || 0), 0)
  return String(total)
})
function adjVal(row: any): number {
  return (parseFloat(row.rje) || 0) + (parseFloat(row.aje) || 0)
}

// 审计要点回退数据（TSJ 提示词库不可用时）
const AUDIT_TIPS_FALLBACK: Record<string, string[]> = {
  '货币资金': ['核实银行存款余额', '检查银行对账单', '验证现金盘点', '检查受限资金'],
  '应收账款': ['检查账龄分析', '评估坏账准备', '验证应收函证', '检查期后回款'],
  '存货': ['参与存货盘点', '评估跌价准备', '检查结转成本', '关注滞销品'],
  '固定资产': ['核实资产清单', '检查折旧计算', '关注减值迹象', '核查处置情况'],
  '营业收入': ['执行截止测试', '检查收入确认', '分析毛利率', '关注确认时点'],
}

const tsjData = ref<{ tips: string[]; checklist: string[]; risk_areas: any[] } | null>(null)

const auditTips = computed(() => {
  if (tsjData.value?.tips?.length) return tsjData.value.tips
  if (!selectedMapping.value) return []
  const name = selectedMapping.value.account_name
  return AUDIT_TIPS_FALLBACK[name] || ['检查期末余额', '核实变动分析', '抽查凭证穿透', '评估披露恰当性']
})

// 审计程序检查清单
const AUDIT_CHECKLISTS_FALLBACK: Record<string, string[]> = {
  '货币资金': ['获取银行存款余额', '验证现金盘点', '检查银行对账单', '检查银行函证', '检查受限资金', '编制审定表'],
  '应收账款': ['获取账龄分析', '验证应收函证', '检查期后回款', '评估坏账准备', '检查关联方', '编制审定表'],
  '存货': ['参与存货盘点', '评估跌价准备', '检查成本结转', '截止测试', '检查周转率', '编制审定表'],
  '固定资产': ['核实资产清单', '检查折旧计算', '核查处置', '评估减值', '核实产权证书', '编制审定表'],
  '营业收入': ['执行截止测试', '检查收入确认', '分析回款', '抽查合同', '检查确认时点', '编制审定表'],
}

const auditChecklist = ref<Array<{ label: string; done: boolean }>>([])

watch(selectedMapping, async (m) => {
  if (!m) { auditChecklist.value = []; tsjData.value = null; return }
  // 加载 TSJ 提示词
  tsjData.value = null
  try {
    const data = await api.get(
      P_wp.wpMappingTsj(projectId.value, m.account_name),
      { validateStatus: () => true }
    )
    const result = data
    if (result?.tips?.length || result?.checklist?.length) {
      tsjData.value = result
    }
  } catch { /* TSJ 不可用时 fallback */ }
  // 构建检查清单
  const tsjChecklist = tsjData.value?.checklist
  const items = tsjChecklist?.length
    ? tsjChecklist
    : (AUDIT_CHECKLISTS_FALLBACK[m.account_name] || ['获取明细表', '抽查凭证', '变动分析', '编制底稿', '编制审定表'])
  auditChecklist.value = items.map(label => ({ label, done: false }))
})

interface TreeNode {
  id: string; label: string; children?: TreeNode[]
  wpCode?: string; stale?: boolean; consistent?: boolean | null
  statusIcon?: string; assignee?: string
}

function _wpStatusIcon(wp?: { status: string; review_status: string }): string {
  if (!wp) return '⬜'
  if (wp.status === 'review_passed' || wp.status === 'archived') return '✅'
  if (wp.review_status?.startsWith('pending_')) return '🔍'
  if (wp.review_status?.includes('rejected')) return '↩️'
  if (wp.status === 'draft' || wp.status === 'edit_complete') return '📝'
  if (wp.status === 'under_review') return '🔍'
  return '⬜'
}

const treeData = computed<TreeNode[]>(() => {
  const groups: Record<string, TreeNode> = {}
  const CYCLE_NAMES: Record<string, string> = {
    D: 'D 销售循环', E: 'E 货币资金', F: 'F 存货', G: 'G 投资',
    H: 'H 固定资产', I: 'I 无形资产', J: 'J 薪酬', K: 'K 费用',
    L: 'L 负债', M: 'M 权益', N: 'N 税项',
  }
  for (const m of mappings.value) {
    const key = m.cycle
    if (!groups[key]) {
      groups[key] = { id: `g-${key}`, label: CYCLE_NAMES[key] || `${key}循环`, children: [] }
    }
    groups[key].children!.push({
      id: m.wp_code, label: `${m.wp_code} ${m.wp_name}`, wpCode: m.wp_code,
      statusIcon: _wpStatusIcon(wpStatusMap.value[m.wp_code]),
      assignee: wpStatusMap.value[m.wp_code]?.assigned_to || undefined,
    })
  }
  // 统计每组数量
  for (const g of Object.values(groups)) {
    const total = g.children?.length || 0
    g.label = `${g.label}（${total}）`
  }
  return Object.values(groups).sort((a, b) => a.label.localeCompare(b.label))
})

function filterNode(value: string, data: any, node: any) {
  if (!value) return true
  const v = value.toLowerCase()
  return (data.label || '').toLowerCase().includes(v)
}

watch(searchText, (val) => {
  treeRef.value?.filter(val)
})

function onNodeClick(data: TreeNode) {
  if (!data.wpCode) return
  const m = mappings.value.find(x => x.wp_code === data.wpCode)
  if (m) {
    selectedMapping.value = m
    loadPrefillData(m)
    loadAttachments(m.wp_code)
    loadAiAnalysis(m)
    loadPriorYear(m)
  }
}

const fmtAmt = fmtAmount

function getFileIcon(type?: string): string {
  if (!type) return '📄'
  if (type.includes('pdf')) return '📕'
  if (type.includes('image') || type.includes('jpg') || type.includes('png')) return '🖼️'
  if (type.includes('xls')) return '📊'
  if (type.includes('doc')) return '📝'
  return '📄'
}

function formatSize(bytes?: number): string {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`
}

function getOcrStatus(att: any): 'ok' | 'processing' | 'failed' | 'pending' {
  if (att.ocr_status === 'completed' || att.ocr_status === 'success' || att.ocr_status === 'ok') return 'ok'
  if (att.ocr_status === 'processing') return 'processing'
  if (att.ocr_status === 'failed') return 'failed'
  return 'pending'
}

// ── 数据加载 ──
async function refreshAll() {
  loading.value = true
  try {
    mappings.value = await getAllWpMappings(projectId.value)
  } catch {
    // 映射数据不存在时静默（新项目无映射）
    mappings.value = []
  }
  // 加载底稿状态（非关键，静默）
  try {
    const wps = await api.get(P_wp.list(projectId.value), { validateStatus: (s: number) => s < 500 })
    const list = Array.isArray(wps) ? wps : (wps?.items || [])
    const map: Record<string, any> = {}
    for (const w of list) {
      map[w.wp_code] = { id: w.id, status: w.status, review_status: w.review_status || '', assigned_to: w.assigned_to }
    }
    wpStatusMap.value = map
  } catch { /* 静默 */ }
  // 加载年度（非关键，静默）
  try {
    const y = await getProjectAuditYear(projectId.value)
    if (y) year.value = y
  } catch { /* 静默 */ }
  loading.value = false
}

async function loadPrefillData(m: WpAccountMapping) {
  prefillLoading.value = true
  prefillData.value = null
  try {
    prefillData.value = await getWpPrefillData(projectId.value, m.wp_code, year.value)
  } catch { /* 静默 */ }
  prefillLoading.value = false
}

async function loadAttachments(wpCode: string) {
  try {
    const data = await api.get(P_att.search, {
      params: { wp_code: wpCode, project_id: projectId.value },
      validateStatus: (s: number) => s < 500,
    })
    attachments.value = Array.isArray(data) ? data : (data?.items || [])
  } catch { attachments.value = [] }
}

// 任务 12.6.1：AI 分析结果会话级缓存（切换底稿时命中缓存，避免重复请求 vLLM）
const aiAnalysisCache = ref<Map<string, any>>(new Map())

async function loadAiAnalysis(m: WpAccountMapping) {
  const cacheKey = `${m.wp_code}|${m.account_name}|${year.value}`
  const cached = aiAnalysisCache.value.get(cacheKey)
  if (cached) {
    aiAnalysis.value = cached
    aiLoading.value = false
    return
  }

  aiLoading.value = true
  aiAnalysis.value = null
  try {
    const data = await api.get(P_wpai.generateExplanation(projectId.value, ''), {
      params: { account_name: m.account_name, year: year.value },
      validateStatus: (s: number) => s < 500,
    })
    if (data && !data.error) {
      aiAnalysis.value = data
      aiAnalysisCache.value.set(cacheKey, data)
    } else {
      aiAnalysis.value = { unavailable: true, message: 'AI 分析服务未启动，请检查 vLLM 是否运行' }
      // 不缓存 unavailable，下次重试
    }
  } catch {
    aiAnalysis.value = { unavailable: true, message: 'AI 分析服务未启动，请检查 vLLM 是否运行' }
  }
  aiLoading.value = false
}

async function loadPriorYear(m: WpAccountMapping) {
  priorYearData.value = null
  try {
    priorYearData.value = await getWpPrefillData(projectId.value, m.wp_code, year.value - 1)
  } catch { /* 无上年数据 */ }
}

async function onBatchPrefill() {
  prefillLoading.value = true
  try {
    await api.post(P_wp.batchPrefill(projectId.value))
    ElMessage.success('批量预填充已提交')
  } catch (e: any) {
    ElMessage.warning(e?.message || '预填充失败')
  }
  prefillLoading.value = false
}

async function onSmartRecommend() {
  recommendLoading.value = true
  try {
    recommendations.value = await getWpRecommendations(projectId.value, year.value)
  } catch (e: any) {
    ElMessage.warning(e?.message || '获取推荐失败')
  }
  recommendLoading.value = false
}

async function onGenerateRecommended() {
  generatingWps.value = true
  try {
    const codes = recommendations.value.map(r => r.wp_code)
    await api.post(P_wp.generateFromCodes(projectId.value), { wp_codes: codes, year: year.value })
    ElMessage.success('底稿生成完成')
    recommendations.value = []
    await refreshAll()
  } catch (e: any) {
    handleApiError(e, '生成')
  }
  generatingWps.value = false
}

// [R9 F8 Task 29] AI 对话已移至 WorkpaperSidePanel AI Tab
// onAskAI 函数已移除，AI 功能通过 WorkpaperEditor 的 AiAssistantSidebar 提供

function onOpenWorkpaper() {
  if (!selectedMapping.value) return
  const wpCode = selectedMapping.value.wp_code
  const wpStatus = wpStatusMap.value[wpCode]
  if (wpStatus && (wpStatus as any).id) {
    router.push({ name: 'WorkpaperEditor', params: { projectId: projectId.value, wpId: (wpStatus as any).id } })
  } else {
    // 底稿尚未生成，直接触发生成
    ElMessage.info(`底稿 ${wpCode} 尚未生成，正在为您创建...`)
    generateSingleWorkpaper(wpCode)
  }
}

async function generateSingleWorkpaper(wpCode: string) {
  try {
    await api.post(P_wp.generateFromCodes(projectId.value), {
      wp_codes: [wpCode],
      year: year.value,
    })
    ElMessage.success(`底稿 ${wpCode} 已生成`)
    await refreshAll()
    // 生成后重新尝试打开
    const wpStatus = wpStatusMap.value[wpCode]
    if (wpStatus && (wpStatus as any).id) {
      router.push({ name: 'WorkpaperEditor', params: { projectId: projectId.value, wpId: (wpStatus as any).id } })
    }
  } catch (e: any) {
    const msg = typeof e?.message === 'string' ? e.message : '生成失败'
    ElMessage.warning(`底稿 ${wpCode} 生成失败：${msg}`)
  }
}

function onGoTrialBalance() {
  router.push(`/projects/${projectId.value}/trial-balance`)
}

function onGoNote() {
  if (!selectedMapping.value?.note_section) return
  router.push(`/projects/${projectId.value}/disclosure-notes`)
}

function onGoLedger() {
  if (!selectedMapping.value) return
  router.push(`/projects/${projectId.value}/ledger`)
}

function onDrillToAdjustment(row: any) {
  router.push(`/projects/${projectId.value}/adjustments?account_code=${row.code}`)
}

async function onAttachFileSelect(file: any) {
  if (!selectedMapping.value) return
  const formData = new FormData()
  formData.append('file', file.raw)
  formData.append('wp_code', selectedMapping.value.wp_code)
  formData.append('attachment_type', 'workpaper')
  try {
    await api.post(P_att.upload(projectId.value), formData)
    ElMessage.success('附件上传成功')
    loadAttachments(selectedMapping.value.wp_code)
  } catch (e: any) {
    handleApiError(e, '上传')
  }
}

function onPreviewAttachment(id: string) {
  // TODO: replace window.open with AttachmentPreviewDrawer
  window.open(`${P_att.search}/${id}/preview`, '_blank')
}

function onManageAttachments() {
  router.push(`/projects/${projectId.value}/attachments`)
}

async function onConfirmAssign() {
  if (!selectedMapping.value) return
  assignLoading.value = true
  try {
    await api.put(`${P_wp.list(projectId.value)}/${selectedMapping.value.wp_code}/assign`, assignForm)
    ElMessage.success('委派成功')
    showAssignDialog.value = false
    await refreshAll()
  } catch (e: any) {
    handleApiError(e, '委派')
  }
  assignLoading.value = false
}

// ── 初始化 ──
onMounted(async () => {
  await refreshAll()
  // 加载人员列表
  try {
    const data = await api.get(P_staff.list)
    staffList.value = Array.isArray(data) ? data : (data?.items || [])
  } catch { /* 静默 */ }
})
</script>

<style scoped>
.gt-wp-bench { padding: var(--gt-space-4); height: 100%; display: flex; flex-direction: column; overflow: hidden; }
/* 横幅 */
.gt-wpb-banner {
  display: flex; justify-content: space-between; align-items: center;
  padding: var(--gt-space-5) var(--gt-space-6); margin-bottom: var(--gt-space-4);
  background: var(--gt-gradient-primary); border-radius: var(--gt-radius-lg); color: #fff;
  position: relative; overflow: hidden;
  background-image: var(--gt-gradient-primary),
    linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px);
  background-size: 100% 100%, 20px 20px, 20px 20px;
}
.gt-wpb-banner::before {
  content: ''; position: absolute; top: -40%; right: -10%; width: 45%; height: 180%;
  background: radial-gradient(ellipse, rgba(255,255,255,0.07) 0%, transparent 65%); pointer-events: none;
}
.gt-wpb-banner-text { position: relative; z-index: 1; }
.gt-wpb-banner-text h2 { margin: 0; font-size: var(--gt-font-size-xl); font-weight: 700; }
.gt-wpb-banner-text p { margin: 4px 0 0; font-size: var(--gt-font-size-sm); opacity: 0.85; }
.gt-wpb-banner-actions { display: flex; gap: var(--gt-space-2); position: relative; z-index: 1; }
.gt-wpb-banner-actions .el-button {
  background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.25); color: #fff;
}
.gt-wpb-banner-actions .el-button:hover { background: rgba(255,255,255,0.25); }
/* 推荐面板 */
.gt-wpb-recommend-panel {
  background: var(--gt-color-bg-white); border-radius: var(--gt-radius-md);
  padding: var(--gt-space-4); margin-bottom: var(--gt-space-4); box-shadow: var(--gt-shadow-sm);
  border: 1px solid rgba(75, 45, 119, 0.06);
}
.gt-wpb-recommend-header { display: flex; align-items: center; gap: var(--gt-space-3); margin-bottom: var(--gt-space-3); }
.gt-wpb-recommend-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: var(--gt-space-2); }
.gt-wpb-recommend-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: var(--gt-space-2) var(--gt-space-3); background: var(--gt-color-bg);
  border-radius: var(--gt-radius-sm); transition: background var(--gt-transition-fast);
}
.gt-wpb-recommend-item:hover { background: var(--gt-color-primary-bg); }
.gt-wpb-rec-left { display: flex; align-items: center; gap: var(--gt-space-2); }
.gt-wpb-rec-code { font-family: monospace; font-size: 12px; color: var(--gt-color-text-tertiary); }
.gt-wpb-rec-name { font-size: 13px; }
.gt-wpb-rec-right { display: flex; align-items: center; gap: var(--gt-space-2); }
.gt-wpb-rec-reason { font-size: 11px; color: var(--gt-color-text-tertiary); }
/* 三栏主体 */
.gt-wpb-body { flex: 1; display: flex; gap: var(--gt-space-3); min-height: 0; overflow: hidden; }
/* 左栏：底稿树 */
.gt-wpb-tree {
  width: 260px; flex-shrink: 0; background: var(--gt-color-bg-white);
  border-radius: var(--gt-radius-md); box-shadow: var(--gt-shadow-sm);
  display: flex; flex-direction: column; overflow: hidden;
}
.gt-wpb-tree-header { padding: var(--gt-space-3); border-bottom: 1px solid var(--gt-color-border-light); display: flex; flex-direction: column; gap: var(--gt-space-2); }
.gt-wpb-tree-filters { display: flex; align-items: center; gap: var(--gt-space-2); }
.gt-wpb-tree-progress { display: flex; align-items: center; gap: 4px; font-size: 12px; color: var(--gt-color-text-secondary); }
.gt-wpb-prog-item { font-weight: 600; }
.gt-wpb-prog--done { color: var(--gt-color-success); }
.gt-wpb-prog-sep { color: var(--gt-color-text-tertiary); }
.gt-wpb-tree :deep(.el-tree) { flex: 1; overflow-y: auto; padding: var(--gt-space-1); }
.gt-wpb-node { display: flex; align-items: center; gap: 4px; font-size: 13px; width: 100%; }
.gt-wpb-node-icon { font-size: 14px; flex-shrink: 0; }
.gt-wpb-node-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gt-wpb-node-assignee { font-size: 10px; color: var(--gt-color-text-tertiary); background: var(--gt-color-bg); padding: 1px 4px; border-radius: 3px; }
/* 中栏：详情 */
.gt-wpb-detail {
  flex: 1; min-width: 0; background: var(--gt-color-bg-white);
  border-radius: var(--gt-radius-md); box-shadow: var(--gt-shadow-sm);
  padding: var(--gt-space-4); overflow-y: auto;
}
.gt-wpb-detail-header { margin-bottom: var(--gt-space-4); }
.gt-wpb-detail-title-row { display: flex; align-items: center; gap: var(--gt-space-3); margin-bottom: var(--gt-space-2); }
.gt-wpb-detail-title-row h3 { margin: 0; font-size: var(--gt-font-size-lg); font-weight: 700; color: var(--gt-color-primary-dark); }
.gt-wpb-detail-tags { display: flex; gap: var(--gt-space-2); }
.gt-wpb-section-title { font-size: var(--gt-font-size-base); font-weight: 600; color: var(--gt-color-text); margin: 0 0 var(--gt-space-3); }
/* 流程步骤 */
.gt-wpb-workflow { display: flex; align-items: center; gap: 0; margin-bottom: var(--gt-space-5); padding: var(--gt-space-3) 0; }
.gt-wpb-step { display: flex; flex-direction: column; align-items: center; gap: 4px; min-width: 60px; }
.gt-wpb-step-dot { width: 12px; height: 12px; border-radius: 50%; background: var(--gt-color-border); transition: all var(--gt-transition-fast); }
.gt-wpb-step--done .gt-wpb-step-dot { background: var(--gt-color-success); box-shadow: 0 0 0 3px rgba(40, 167, 69, 0.15); }
.gt-wpb-step--active .gt-wpb-step-dot { background: var(--gt-color-primary); box-shadow: 0 0 0 3px rgba(75, 45, 119, 0.15); }
.gt-wpb-step span { font-size: 11px; color: var(--gt-color-text-secondary); }
.gt-wpb-step--done span { color: var(--gt-color-success); font-weight: 600; }
.gt-wpb-step--active span { color: var(--gt-color-primary); font-weight: 600; }
.gt-wpb-step-line { flex: 1; height: 2px; background: var(--gt-color-border-light); min-width: 16px; margin-top: -10px; }
/* 数据区块 */
.gt-wpb-data-section { margin-bottom: var(--gt-space-5); }
/* 预填充卡片 */
.gt-wpb-prefill-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--gt-space-3); }
.gt-wpb-prefill-card {
  padding: var(--gt-space-3) var(--gt-space-4); border-radius: var(--gt-radius-md);
  display: flex; flex-direction: column; gap: 2px; border-left: 3px solid var(--gt-color-border);
}
.gt-wpb-prefill-card--muted { border-left-color: var(--gt-color-text-tertiary); background: #f9f9fb; }
.gt-wpb-prefill-card--primary { border-left-color: var(--gt-color-primary); background: var(--gt-color-primary-bg); }
.gt-wpb-prefill-card--teal { border-left-color: var(--gt-color-teal); background: var(--gt-color-teal-light); }
.gt-wpb-prefill-card--success { border-left-color: var(--gt-color-success); background: var(--gt-color-success-light); }
.gt-wpb-pf-label { font-size: 11px; color: var(--gt-color-text-secondary); }
.gt-wpb-pf-value { font-size: var(--gt-font-size-lg); font-weight: 700; color: var(--gt-color-text); font-variant-numeric: tabular-nums; }
.gt-wpb-pf-value--diff { color: var(--gt-color-coral); }
.gt-wpb-acct-table :deep(th) { font-size: 11px !important; }
/* 附件 */
.gt-wpb-attach-list { display: flex; flex-direction: column; gap: var(--gt-space-2); margin-bottom: var(--gt-space-3); }
.gt-wpb-attach-item {
  display: flex; align-items: center; gap: var(--gt-space-3);
  padding: var(--gt-space-2) var(--gt-space-3); background: var(--gt-color-bg);
  border-radius: var(--gt-radius-sm); transition: background var(--gt-transition-fast);
}
.gt-wpb-attach-item:hover { background: var(--gt-color-primary-bg); }
.gt-wpb-attach-icon { font-size: 20px; }
.gt-wpb-attach-info { flex: 1; display: flex; flex-direction: column; }
.gt-wpb-attach-name { font-size: 13px; font-weight: 500; }
.gt-wpb-attach-meta { font-size: 11px; color: var(--gt-color-text-tertiary); display: flex; align-items: center; gap: 6px; }
.gt-wpb-attach-empty { text-align: center; padding: var(--gt-space-4); color: var(--gt-color-text-tertiary); font-size: 13px; }
.gt-wpb-attach-actions { display: flex; gap: var(--gt-space-2); }
/* 操作按钮 */
.gt-wpb-actions { display: flex; flex-wrap: wrap; gap: var(--gt-space-2); margin-top: var(--gt-space-4); padding-top: var(--gt-space-4); border-top: 1px solid var(--gt-color-border-light); }
/* 上年数据 */
.gt-wpb-prior-cards { display: flex; gap: var(--gt-space-3); }
.gt-wpb-prior-card {
  flex: 1; padding: var(--gt-space-3) var(--gt-space-4);
  background: var(--gt-color-bg); border-radius: var(--gt-radius-sm);
  border: 1px dashed var(--gt-color-border); display: flex; flex-direction: column; gap: 2px;
}
.gt-wpb-prior-label { font-size: 11px; color: var(--gt-color-text-tertiary); }
.gt-wpb-prior-value { font-size: var(--gt-font-size-md); font-weight: 600; font-variant-numeric: tabular-nums; }
.gt-wpb-prior-diff { color: var(--gt-color-coral); }
/* 空状态 */
.gt-wpb-empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; color: var(--gt-color-text-tertiary); }
.gt-wpb-empty-icon { font-size: 48px; margin-bottom: var(--gt-space-3); }
.gt-wpb-empty-state h4 { margin: 0 0 var(--gt-space-2); color: var(--gt-color-text-secondary); }
.gt-wpb-empty-state p { font-size: 13px; }
/* 右栏：AI 助手 */
.gt-wpb-ai {
  width: 300px; flex-shrink: 0; background: var(--gt-color-bg-white);
  border-radius: var(--gt-radius-md); box-shadow: var(--gt-shadow-sm);
  padding: var(--gt-space-4); overflow-y: auto;
}
.gt-wpb-ai-content { display: flex; flex-direction: column; }
.gt-wpb-ai-hint {
  display: flex; align-items: center; font-size: 13px; color: var(--gt-color-text-secondary);
  padding: var(--gt-space-2) var(--gt-space-3); background: var(--gt-color-primary-bg);
  border-radius: var(--gt-radius-sm); margin-bottom: var(--gt-space-3);
}
.gt-wpb-ai-unavailable {
  display: flex; align-items: center; gap: 8px;
  padding: 12px 16px; background: var(--gt-color-warning-light, #fdf6ec);
  border: 1px solid var(--gt-color-warning, #e6a23c);
  border-radius: var(--gt-radius-md, 8px); color: var(--gt-color-warning, #e6a23c);
  font-size: 13px; margin-bottom: var(--gt-space-3);
}
.gt-wpb-ai-analysis {
  padding: var(--gt-space-3); background: var(--gt-color-teal-light);
  border-radius: var(--gt-radius-sm); border-left: 3px solid var(--gt-color-teal); margin-bottom: var(--gt-space-3);
}
.gt-wpb-ai-analysis-header { display: flex; align-items: center; gap: var(--gt-space-2); margin-bottom: var(--gt-space-2); }
.gt-wpb-ai-analysis-badge { font-size: 11px; font-weight: 600; color: var(--gt-color-teal); background: rgba(0,148,179,0.1); padding: 2px 6px; border-radius: 3px; }
.gt-wpb-ai-sig { font-weight: 700; color: var(--gt-color-coral); }
.gt-wpb-ai-normal { font-weight: 600; color: var(--gt-color-text-secondary); }
.gt-wpb-ai-analysis-text { font-size: 13px; color: var(--gt-color-text); line-height: 1.6; margin: 0; }
.gt-wpb-ai-tips { display: flex; flex-direction: column; gap: var(--gt-space-2); }
.gt-wpb-ai-tip {
  display: flex; align-items: flex-start; gap: var(--gt-space-2);
  font-size: 13px; color: var(--gt-color-text); padding: var(--gt-space-1) 0;
}
.gt-wpb-ai-tip-num {
  width: 20px; height: 20px; border-radius: 50%; background: var(--gt-color-primary-bg);
  color: var(--gt-color-primary); font-size: 11px; font-weight: 700;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.gt-wpb-ai-answer {
  margin-top: var(--gt-space-3); padding: var(--gt-space-3);
  background: var(--gt-color-teal-light); border-radius: var(--gt-radius-sm);
  border-left: 3px solid var(--gt-color-teal);
}
.gt-wpb-ai-answer p { margin: 0; font-size: 13px; line-height: 1.6; color: var(--gt-color-text); }
/* 检查清单 */
.gt-wpb-checklist { margin-top: var(--gt-space-4); }
.gt-wpb-check-item {
  display: flex; align-items: center; gap: var(--gt-space-2);
  padding: var(--gt-space-1) var(--gt-space-2); border-radius: var(--gt-radius-sm);
  cursor: pointer; transition: background var(--gt-transition-fast);
  font-size: 13px; color: var(--gt-color-text);
}
.gt-wpb-check-item:hover { background: var(--gt-color-primary-bg); }
.gt-wpb-check-done { text-decoration: line-through; color: var(--gt-color-text-tertiary); }
.gt-wpb-check-progress {
  font-size: 11px; color: var(--gt-color-text-secondary); margin-top: 8px;
  padding: 4px 8px; background: var(--gt-color-bg); border-radius: var(--gt-radius-sm);
  text-align: center; font-weight: 500;
}
</style>