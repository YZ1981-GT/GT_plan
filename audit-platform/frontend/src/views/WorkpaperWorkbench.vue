<template>
  <div class="gt-wp-bench gt-fade-in">
    <!-- 页面横幅 -->
    <div class="gt-wpb-banner">
      <div class="gt-wpb-banner-text">
        <div style="display: flex; align-items: center; gap: 8px">
          <el-button text style="color: #fff; font-size: 13px; padding: 0" @click="router.push('/projects')">← 返回</el-button>
          <h2>底稿工作台</h2>
        </div>
        <p>{{ projectName || '' }} · {{ templates.length }} 个主编码模板</p>
      </div>
      <div class="gt-wpb-banner-actions">
        <el-button size="small" @click="refreshAll" :loading="loading" round>刷新</el-button>
        <el-button size="small" @click="onBatchPrefill" :loading="prefillLoading" round>批量预填充</el-button>
        <el-button size="small" @click="onSmartRecommend" :loading="recommendLoading" round>智能推荐底稿</el-button>
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
            <el-tooltip
              :content="!balanceLoaded ? '需先导入账套' : '隐藏所有 linked_accounts 在试算表中余额为零的模板（B/C/A/S 类无 linked_accounts 始终显示）'"
              placement="bottom"
            >
              <el-checkbox v-model="onlyWithData" size="small">仅有数据</el-checkbox>
            </el-tooltip>
            <el-checkbox v-model="onlyMine" size="small">仅我的</el-checkbox>
            <el-select v-model="filterStatus" size="small" placeholder="状态" clearable style="width: 80px">
              <el-option label="待编" value="pending" />
              <el-option label="编制中" value="in_progress" />
              <el-option label="复核中" value="review" />
              <el-option label="已通过" value="passed" />
            </el-select>
          </div>
          <!-- 进度概览 (template-library-coordination Sprint 2.1)：已生成主编码数 / 主编码总数 -->
          <div class="gt-wpb-tree-progress">
            <span class="gt-wpb-prog-item gt-wpb-prog--done">{{ generatedCount }}</span>
            <span class="gt-wpb-prog-sep">/</span>
            <span class="gt-wpb-prog-item">{{ totalPrimaryCount }}</span>
            <el-progress :percentage="generatedPct" :stroke-width="4" :show-text="false" style="flex:1; margin-left: 8px" />
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
            <div class="gt-wpb-node" :class="{
              'gt-tree-cycle': data.isCycle,
              [data.cycleProgressClass]: data.isCycle && data.cycleProgressClass,
              'gt-tree-ungenerated': !data.isCycle && data.generated === false,
            }">
              <span class="gt-wpb-node-icon" v-if="data.statusIcon">{{ data.statusIcon }}</span>
              <span class="gt-wpb-node-label">{{ data.label }}</span>
              <span v-if="data.sheetCount && data.sheetCount > 1" class="gt-wpb-node-sheets">
                ({{ data.sheetCount }} sheets)
              </span>
              <span v-if="data.hasFormula" class="gt-wpb-node-formula" title="含预填充公式">ƒ</span>
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
              <!-- Spec A R1：stale 标志 -->
              <el-tooltip
                v-if="isCurrentWpStale"
                content="底稿已过期，建议重新生成"
                placement="top"
              >
                <el-tag type="warning" size="small" round style="cursor: help">🟡 stale</el-tag>
              </el-tooltip>
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
          <!-- 操作按钮（紧跟标题） -->
          <div class="gt-wpb-actions">
            <el-button type="primary" @click="onOpenWorkpaper" round>
              <el-icon style="margin-right: 4px"><EditPen /></el-icon>编辑底稿
            </el-button>
            <el-button @click="showAssignDialog = true" round>分配委派</el-button>
            <el-button @click="onGoTrialBalance" round>查看试算表</el-button>
            <el-button v-if="selectedMapping.note_section" @click="onGoNote" round>查看附注</el-button>
            <el-button @click="onGoLedger" round>查看序时账</el-button>
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
              <el-table-column prop="code" label="科目编码" width="100" />
              <el-table-column prop="name" label="科目名称" min-width="130" show-overflow-tooltip />
              <el-table-column label="期初余额" width="130" align="right">
                <template #default="{ row }">{{ fmtAmt(row.opening) }}</template>
              </el-table-column>
              <el-table-column label="未审数" width="130" align="right">
                <template #default="{ row }">{{ fmtAmt(row.unadjusted) }}</template>
              </el-table-column>
              <el-table-column label="调整额" width="110" align="right">
                <template #default="{ row }">
                  <span
                    class="gt-wpb-adj-cell"
                    :class="{ 'gt-wpb-adj-cell--active': adjVal(row) !== 0 }"
                    @dblclick="adjVal(row) !== 0 && onDrillToAdjustment(row)"
                    :title="adjVal(row) !== 0 ? '双击查看调整分录' : ''">{{ fmtAmt(adjVal(row)) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="审定数" width="130" align="right">
                <template #default="{ row }">
                  <span style="font-weight: 700; color: var(--gt-color-primary)">{{ fmtAmt(row.audited) }}</span>
                </template>
              </el-table-column>
            </el-table>
          </div>
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
import { ref, computed, watch, onMounted, onBeforeUnmount, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { MagicStick, EditPen, Paperclip, WarningFilled } from '@element-plus/icons-vue'
import { getAllWpMappings, getWpPrefillData, getWpRecommendations, type WpAccountMapping, type WpPrefillData, type WpRecommendation } from '@/services/workpaperApi'
import { getProjectAuditYear } from '@/services/auditPlatformApi'
import { api } from '@/services/apiProxy'
import { workpapers as P_wp, attachments as P_att, wpAI as P_wpai, staff as P_staff, trialBalance as P_tb } from '@/services/apiPaths'
import { fmtAmount } from '@/utils/formatters'
import OcrStatusBadge from '@/components/common/OcrStatusBadge.vue'
import { handleApiError } from '@/utils/errorHandler'
import { useNavigationStack } from '@/composables/useNavigationStack'
// Spec A R1：跨视图 stale 摘要
import { useStaleSummaryFull } from '@/composables/useStaleSummaryFull'
import { eventBus } from '@/utils/eventBus'

const route = useRoute()
const router = useRouter()
const { push: navPush } = useNavigationStack()
const projectId = computed(() => route.params.projectId as string)
const year = ref(new Date().getFullYear())
const projectName = ref('')

// Spec A: 跨视图 stale 摘要
const yearRef = computed(() => year.value)
const { workpapers: wpStaleSummary } = useStaleSummaryFull(projectId, yearRef)
const staleWpCodeSet = computed(() => {
  // wpStaleSummary.items 是 [{id, wp_code, wp_name}, ...]
  return new Set(wpStaleSummary.value.items.map((it: any) => it.wp_code).filter(Boolean))
})
// 当前选中的 mapping 是否 stale（按 wp_code 匹配）
const isCurrentWpStale = computed(() => {
  const code = selectedMapping.value?.wp_code
  return code ? staleWpCodeSet.value.has(code) : false
})

const loading = ref(false)
const prefillLoading = ref(false)
const mappings = ref<WpAccountMapping[]>([])
const selectedMapping = ref<WpAccountMapping | null>(null)
const prefillData = ref<WpPrefillData | null>(null)
const searchText = ref('')
const treeRef = ref<any>(null)
const aiQuestion = ref('')
const onlyWithData = ref(true)  // 默认只显示有数据的科目
const accountsWithData = ref<Set<string>>(new Set())
const balanceLoaded = ref(false)  // 试算表是否已加载（用于"仅有数据"筛选器）
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

// [template-library-coordination Sprint 2.1] 模板列表（来自 /api/projects/{pid}/wp-templates/list）
// 替代旧的 mappings 作为树形数据源 — 包含全部主编码模板（B/C/D-N/A/S 全 6 模块）
interface TemplateListItem {
  wp_code: string
  wp_name: string
  cycle: string
  cycle_name: string
  filename: string
  format: string
  component_type: string | null
  audit_stage: string | null
  linked_accounts: string[]
  procedure_steps: any[]
  has_formula: boolean
  source_file_count: number
  sheet_count: number
  generated: boolean
  sort_order: number | null
}
const templates = ref<TemplateListItem[]>([])

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

// [template-library-coordination Sprint 2.1] 进度统计基于 templates 而非 mappings
const totalPrimaryCount = computed(() => templates.value.length)
const generatedCount = computed(() => templates.value.filter(t => t.generated).length)
const generatedPct = computed(() => totalPrimaryCount.value > 0
  ? Math.round((generatedCount.value / totalPrimaryCount.value) * 100)
  : 0
)

// 旧字段保留兼容（暂未删除引用处）
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
  // [Sprint 2.1+2.2] 树形扩展字段
  isCycle?: boolean
  cycleProgressClass?: string  // 进度颜色：done(green) / partial(blue) / empty(grey)
  generated?: boolean          // 模板是否已生成（未生成显示灰色）
  sheetCount?: number
  hasFormula?: boolean
  componentType?: string | null
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

// [template-library-coordination Sprint 2.1+2.2+2.3]
// treeData 数据源从 mappings 改为 templates（来自 /api/projects/{pid}/wp-templates/list）
// - 按 cycle 分组（用 cycle_name 作为分组节点名）
// - 循环节点旁显示模板数量（动态从 API 计算）+ 进度（已完成/总数）
// - 未生成底稿（generated=false）的节点 class="gt-tree-ungenerated" 灰色
// - "仅有数据"筛选：linked_accounts 中所有科目余额为零时隐藏；无 linked_accounts（B/C/A/S）始终显示
const treeData = computed<TreeNode[]>(() => {
  const groups = new Map<string, {
    cycle: string
    cycleName: string
    sortOrder: number
    items: TemplateListItem[]
  }>()

  for (const t of templates.value) {
    // 仅有数据筛选（D11 ADR：树节点维度按主编码）
    // 必须满足：(a) 试算表已加载 + (b) 模板有 linked_accounts + (c) 所有 linked_accounts 余额为零 → 才隐藏
    // 无 linked_accounts（B/C/A/S 类）始终显示
    if (onlyWithData.value && balanceLoaded.value) {
      const linked = (t.linked_accounts || []) as string[]
      if (linked.length > 0) {
        const hasData = linked.some(c => {
          if (!c) return false
          if (accountsWithData.value.has(c)) return true
          // 前缀匹配：模板编码 1122 匹配余额表中的 112201
          for (const existing of accountsWithData.value) {
            if (existing.startsWith(c) || c.startsWith(existing)) return true
          }
          return false
        })
        if (!hasData) continue
      }
    }

    const key = t.cycle || '?'
    if (!groups.has(key)) {
      groups.set(key, {
        cycle: key,
        cycleName: t.cycle_name || `${key} 循环`,
        sortOrder: t.sort_order ?? 999999,
        items: [],
      })
    }
    groups.get(key)!.items.push(t)
  }

  // 按 sort_order 升序（gt_wp_coding 真源），后端已传该字段
  const sortedKeys = Array.from(groups.keys()).sort((a, b) => {
    const ga = groups.get(a)!
    const gb = groups.get(b)!
    if (ga.sortOrder !== gb.sortOrder) return ga.sortOrder - gb.sortOrder
    return a.localeCompare(b)
  })

  const result: TreeNode[] = []
  for (const key of sortedKeys) {
    const g = groups.get(key)!
    const total = g.items.length
    if (total === 0) continue

    // [Sprint 2.2] 循环进度统计（基于 generated 字段）
    const done = g.items.filter(it => it.generated).length
    const pct = total > 0 ? Math.round((done / total) * 100) : 0
    let progressClass = 'gt-cycle-progress--empty'  // grey <50%
    if (pct === 100) progressClass = 'gt-cycle-progress--done'
    else if (pct >= 50) progressClass = 'gt-cycle-progress--partial'

    const children: TreeNode[] = g.items
      .sort((a, b) => (a.wp_code || '').localeCompare(b.wp_code || ''))
      .map(t => ({
        id: t.wp_code,
        label: `${t.wp_code} ${t.wp_name}`,
        wpCode: t.wp_code,
        statusIcon: _wpStatusIcon(wpStatusMap.value[t.wp_code]),
        assignee: wpStatusMap.value[t.wp_code]?.assigned_to || undefined,
        generated: t.generated,
        sheetCount: t.sheet_count || 1,
        hasFormula: t.has_formula,
        componentType: t.component_type,
      }))

    result.push({
      id: `cycle-${key}`,
      label: `${g.cycleName}（${done}/${total}）`,
      isCycle: true,
      cycleProgressClass: progressClass,
      children,
    })
  }
  return result
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
  // 优先从 mappings 找（含 account_codes/account_name），找不到则降级用 templates 构造最小 mapping 占位
  let m = mappings.value.find(x => x.wp_code === data.wpCode)
  if (!m) {
    const t = templates.value.find(x => x.wp_code === data.wpCode)
    if (t) {
      m = {
        wp_code: t.wp_code,
        cycle: t.cycle,
        wp_name: t.wp_name,
        account_codes: t.linked_accounts || [],
        account_name: (t.linked_accounts || [])[0] || t.wp_name,
        report_row: null,
        note_section: null,
      } as WpAccountMapping
    }
  }
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

  // [Sprint 2.1] 加载模板列表（来自 /list 端点 — 全部主编码模板含 generated 字段）
  try {
    const data = await api.get(P_wp.templateList(projectId.value))
    const list = Array.isArray(data) ? data : (data?.items || [])
    templates.value = list as TemplateListItem[]
  } catch {
    templates.value = []
  }

  // 加载科目映射（保留兼容，详情面板仍依赖）
  try {
    mappings.value = await getAllWpMappings(projectId.value)
  } catch {
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
  // 加载项目名称
  try {
    const proj = await api.get(`/api/projects/${projectId.value}`)
    projectName.value = proj?.name || proj?.project_name || ''
  } catch { /* 静默 */ }
  // 加载有数据的科目编码集合（用于树形过滤）
  try {
    const balanceData = await api.get(`/api/projects/${projectId.value}/ledger/balance`, { params: { year: year.value } })
    const rows = Array.isArray(balanceData) ? balanceData : (balanceData?.items || balanceData?.rows || [])
    const codes = new Set<string>()
    for (const r of rows) {
      const code = r.account_code || r.standard_account_code || ''
      if (code) {
        codes.add(code)
        // 加入所有前缀层级
        for (let i = 1; i <= code.length; i++) {
          codes.add(code.substring(0, i))
        }
      }
    }
    accountsWithData.value = codes
    balanceLoaded.value = codes.size > 0
  } catch {
    balanceLoaded.value = false
  }
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
  navPush({
    source_view: route.fullPath,
    query: { wp_code: selectedMapping.value?.wp_code || '' },
  })
  router.push(`/projects/${projectId.value}/trial-balance`)
}

function onGoNote() {
  if (!selectedMapping.value?.note_section) return
  navPush({
    source_view: route.fullPath,
    query: { wp_code: selectedMapping.value?.wp_code || '' },
  })
  router.push(`/projects/${projectId.value}/disclosure-notes`)
}

function onGoLedger() {
  if (!selectedMapping.value) return
  navPush({
    source_view: route.fullPath,
    query: { wp_code: selectedMapping.value?.wp_code || '' },
  })
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
// [Sprint 2.2] 监听底稿保存事件，实时刷新进度统计
let _unsubscribers: Array<() => void> = []

function _setupEventListeners() {
  // 底稿保存后刷新进度（generated 字段会变化）
  const off1 = eventBus.on('workpaper:saved', (payload) => {
    if (payload?.projectId === projectId.value) {
      // 仅重新拉取 templates 列表（最轻量）
      api.get(P_wp.templateList(projectId.value))
        .then((data: any) => {
          const list = Array.isArray(data) ? data : (data?.items || [])
          templates.value = list as TemplateListItem[]
        })
        .catch(() => { /* 静默 */ })
    }
  })
  _unsubscribers.push(off1 as any)
}

onMounted(async () => {
  _setupEventListeners()
  await refreshAll()
  // 加载人员列表
  try {
    const data = await api.get(P_staff.list)
    staffList.value = Array.isArray(data) ? data : (data?.items || [])
  } catch { /* 静默 */ }
  // Backspace 返回时自动选中之前的科目
  const qWpCode = route.query.wp_code as string
  if (qWpCode && mappings.value.length) {
    const target = mappings.value.find(m => m.wp_code === qWpCode)
    if (target) {
      selectedMapping.value = target
      loadPrefillData(target)
      loadAttachments(target.wp_code)
      loadAiAnalysis(target)
    }
  }
})

onBeforeUnmount(() => {
  for (const off of _unsubscribers) {
    try { off() } catch { /* ignore */ }
  }
  _unsubscribers = []
})
</script>

<style scoped>
.gt-wp-bench { padding: var(--gt-space-4); height: 100%; display: flex; flex-direction: column; overflow: hidden; }
/* 横幅 */
.gt-wpb-banner {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 24px; margin-bottom: 12px;
  background: var(--gt-gradient-primary); border-radius: var(--gt-radius-md); color: #fff;
  position: relative; overflow: hidden;
}
.gt-wpb-banner::before {
  content: ''; position: absolute; top: -40%; right: -10%; width: 45%; height: 180%;
  background: radial-gradient(ellipse, rgba(255,255,255,0.07) 0%, transparent 65%); pointer-events: none;
}
.gt-wpb-banner-text { position: relative; z-index: 1; }
.gt-wpb-banner-text h2 { margin: 0; font-size: 16px; font-weight: 700; }
.gt-wpb-banner-text p { margin: 2px 0 0; font-size: 12px; opacity: 0.85; }
.gt-wpb-banner-actions { display: flex; gap: var(--gt-space-2); position: relative; z-index: 1; }
.gt-wpb-banner-actions .el-button {
  background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.25); color: #fff;
}
.gt-wpb-banner-actions .el-button:hover { background: rgba(255,255,255,0.25); }
/* 推荐面板 — 全屏覆盖 */
.gt-wpb-recommend-panel {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0; z-index: 100;
  background: var(--gt-color-bg-white);
  padding: 20px 32px; overflow-y: auto;
  box-shadow: 0 0 40px rgba(0,0,0,0.15);
}
.gt-wpb-recommend-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; position: sticky; top: 0; background: var(--gt-color-bg-white); padding-bottom: 12px; border-bottom: 1px solid var(--gt-color-border-light); z-index: 1; }
.gt-wpb-recommend-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 8px; }
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
/* [template-library-coordination Sprint 2.1+2.2+2.3] 树形扩展样式 */
.gt-tree-ungenerated { color: #c0c4cc; }
.gt-tree-ungenerated .gt-wpb-node-label { color: #c0c4cc; }
.gt-tree-cycle { font-weight: 600; }
.gt-cycle-progress--done .gt-wpb-node-label { color: #67c23a; }
.gt-cycle-progress--partial .gt-wpb-node-label { color: #409eff; }
.gt-cycle-progress--empty .gt-wpb-node-label { color: #909399; }
.gt-wpb-node-sheets {
  font-size: 11px;
  color: #909399;
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  margin-left: 4px;
}
.gt-wpb-node-formula {
  font-family: 'Times New Roman', serif;
  font-style: italic;
  color: #67c23a;
  font-size: 12px;
  margin-left: 2px;
}
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
.gt-wpb-pf-value { font-size: var(--gt-font-size-lg); font-weight: 700; color: var(--gt-color-text); font-family: 'Arial Narrow', Arial, sans-serif; font-variant-numeric: tabular-nums; white-space: nowrap; }
.gt-wpb-pf-value--diff { color: var(--gt-color-coral); }
.gt-wpb-acct-table :deep(th) { font-size: 11px !important; white-space: nowrap; background: #f0edf5 !important; color: #4b2d77 !important; }
.gt-wpb-acct-table :deep(td .cell) { font-family: 'Arial Narrow', Arial, sans-serif; font-variant-numeric: tabular-nums; white-space: nowrap; }
.gt-wpb-adj-cell { color: #999; }
.gt-wpb-adj-cell--active { color: #FF5149; cursor: pointer; }
.gt-wpb-adj-cell--active:hover { text-decoration: underline; }
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
.gt-wpb-actions { display: flex; flex-wrap: nowrap; gap: 8px; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid var(--gt-color-border-light); white-space: nowrap; }
.gt-wpb-actions :deep(.el-button) { height: 28px; font-size: 12px; padding: 0 14px; }
/* 上年数据 */
.gt-wpb-prior-cards { display: flex; gap: var(--gt-space-3); }
.gt-wpb-prior-card {
  flex: 1; padding: var(--gt-space-3) var(--gt-space-4);
  background: var(--gt-color-bg); border-radius: var(--gt-radius-sm);
  border: 1px dashed var(--gt-color-border); display: flex; flex-direction: column; gap: 2px;
}
.gt-wpb-prior-label { font-size: 11px; color: var(--gt-color-text-tertiary); }
.gt-wpb-prior-value { font-size: var(--gt-font-size-md); font-weight: 600; font-family: 'Arial Narrow', Arial, sans-serif; font-variant-numeric: tabular-nums; white-space: nowrap; }
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