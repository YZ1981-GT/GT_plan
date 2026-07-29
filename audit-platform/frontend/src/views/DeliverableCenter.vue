<template>
  <div class="deliverable-center">
    <div class="deliverable-center__header">
      <el-icon class="deliverable-center__header-icon"><FolderOpened /></el-icon>
      <div>
        <h2>交付件管理中心</h2>
        <p class="deliverable-center__subtitle">选择性导出 · 版本管理 · 在线预览 · 报告正文生成</p>
      </div>
      <el-button class="deliverable-center__handbook-btn" text @click="handbookVisible = true">
        <el-icon><Reading /></el-icon>
        使用手册
      </el-button>
    </div>

    <CompletenessBanner :project-id="projectId" :year="year" />

    <DeliverableToolbar
      v-model:doc-type="filterDocType"
      v-model:status="filterStatus"
      v-model:keyword="filterKeyword"
      :generating="generating"
      :packaging="packaging"
      :full-generating="fullGenerating"
      @refresh="loadList"
      @generate-report="openGenerateReport"
      @generate-reports="goGenerateReports"
      @generate-notes="goGenerateNotes"
      @generate-full="runGenerateFull"
      @package-download="runPackageDownload"
      @archive="runArchive"
    />

    <ApprovalPanel
      v-if="selectedItem"
      :task-id="selectedItem.task_id"
      :status="selectedItem.status"
      :file-name="selectedItem.file_name"
      :can-submit="selectedItem.status === 'editing'"
      :can-approve="selectedItem.status === 'pending_approval'"
      :loading="approvalLoading"
      @submit="onSubmitApproval"
      @approve="onApprove"
      @reject="onReject"
    />

    <el-skeleton v-if="loading" :rows="6" animated />

    <template v-else>
      <DeliverableGroupList
        :grouped="grouped"
        :expanded-task-id="expandedTaskId"
        :selected-task-id="selectedItem?.task_id || null"
        @toggle-versions="toggleVersions"
        @preview="openPreview"
        @download="downloadItem"
        @download-guidance="downloadGuidanceVersion"
        @edit="openEditor"
        @select="selectItem"
        @delete="confirmDeleteItem"
      />

      <DeliverableVersionList
        v-if="expandedTaskId && versionChain.length"
        :versions="versionChain"
        :project-id="projectId"
        class="deliverable-center__versions"
      />
    </template>

    <DeliverableExportDialog
      v-if="showExportDialog"
      :project-id="projectId"
      :year="year"
      doc-type="audit_report"
      @close="showExportDialog = false"
      @confirm="onExportConfirm"
    />

    <DisclosureNotesSelectionDialog
      v-model:visible="notesDialogVisible"
      :project-id="projectId"
      :year="year"
      :submitting="generating"
      @confirm="onNotesSelectionConfirm"
    />

    <DeliverablePreview
      v-if="previewVisible"
      :title="previewTitle"
      :preview-type="previewType"
      :url="previewUrl"
      :html-content="previewHtml"
      :show-watermark="previewWatermark"
      @close="previewVisible = false"
    />

    <OnlyOfficeEditor
      v-if="editorVisible && editorItem"
      :project-id="projectId"
      :task-id="editorItem.task_id"
      :version-no="editorItem.version_no"
      :year="year"
      :title="editorItem.file_name || '在线编辑'"
      :preview-type="editorPreviewType"
      :preview-url="editorUrl"
      :deliverable-status="editorItem.status"
      :show-watermark="['draft', 'editing'].includes(editorItem.status)"
      @close="editorVisible = false"
    />

    <!-- 生成财务报表选择弹窗 -->
    <el-dialog v-model="showGenerateReports" title="生成财务报表" width="440px">
      <p style="margin: 0 0 12px; color: var(--el-text-color-secondary); font-size: 13px">
        请选择要导出的报表类型：
      </p>
      <el-form-item label="取数口径" style="margin-bottom: 12px">
        <el-radio-group v-model="financialReportDataMode">
          <el-radio value="audited">审定数</el-radio>
          <el-radio value="unadjusted">未审数</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-checkbox-group v-model="selectedReportTypes">
        <el-checkbox label="balance_sheet">资产负债表</el-checkbox>
        <el-checkbox label="income_statement">利润表</el-checkbox>
        <el-checkbox label="cash_flow_statement">现金流量表</el-checkbox>
        <el-checkbox label="equity_statement">所有者权益变动表</el-checkbox>
        <el-checkbox label="impairment_provision">减值准备明细表</el-checkbox>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="showGenerateReports = false">取消</el-button>
        <el-button type="primary" :loading="generating" :disabled="!selectedReportTypes.length" @click="confirmGenerateReports">
          生成（{{ selectedReportTypes.length }}张）
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showGenerateReport" title="生成审计报告正文" width="520px">
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 16px"
      >
        <template #title>请先选择审计意见类型</template>
        <div style="font-size: 12px; line-height: 1.6">
          意见类型决定报告正文采用的模板（无保留 / 带强调事项段 / 保留 / 否定 / 无法表示意见），请根据审计结论审慎选择。
        </div>
      </el-alert>
      <el-form label-width="120px">
        <el-form-item label="审计意见类型" required>
          <el-select v-model="genForm.opinion_type" style="width: 100%" placeholder="请选择审计意见类型">
            <el-option label="标准无保留意见" value="unqualified" />
            <el-option label="带强调事项段的无保留意见" value="unqualified_with_emphasis" />
            <el-option label="保留意见" value="qualified" />
            <el-option label="否定意见" value="adverse" />
            <el-option label="无法表示意见" value="disclaimer" />
          </el-select>
        </el-form-item>
        <el-form-item label="公司类型">
          <el-select v-model="genForm.company_type" style="width: 100%">
            <el-option label="非上市（含国企）" value="non_listed" />
            <el-option label="上市" value="listed" />
          </el-select>
        </el-form-item>
        <el-form-item label="公共利益实体">
          <el-switch v-model="genForm.is_pie" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showGenerateReport = false">取消</el-button>
        <el-button type="primary" :loading="generating" @click="runGenerateReport">下一步</el-button>
      </template>
    </el-dialog>

    <!-- 可选段落确认弹窗（报告正文两阶段生成 §13.1，走真实 Word 模板） -->
    <OptionalSectionDialog
      v-model:visible="optDialogVisible"
      :optional-sections="optSections"
      :missing-fields="optMissingFields"
      :template-version="optTemplateVersion"
      :company-subtype-resolved="optCompanySubtype"
      :confirm-loading="confirmReportLoading"
      @confirm="onReportOptConfirm"
    />

    <DeliverableHandbookDialog v-model:visible="handbookVisible" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { FolderOpened, Reading } from '@element-plus/icons-vue'
import { downloadFile } from '@/utils/http'
import ApprovalPanel from '@/components/deliverable/ApprovalPanel.vue'
import CompletenessBanner from '@/components/deliverable/CompletenessBanner.vue'
import OnlyOfficeEditor from '@/components/deliverable/OnlyOfficeEditor.vue'
import DeliverableToolbar from '@/components/deliverable/DeliverableToolbar.vue'
import DeliverableGroupList from '@/components/deliverable/DeliverableGroupList.vue'
import DeliverableVersionList from '@/components/deliverable/DeliverableVersionList.vue'
import DeliverableExportDialog from '@/components/deliverable/DeliverableExportDialog.vue'
import DisclosureNotesSelectionDialog from '@/components/deliverable/DisclosureNotesSelectionDialog.vue'
import DeliverablePreview from '@/components/deliverable/DeliverablePreview.vue'
import OptionalSectionDialog from '@/components/deliverable/OptionalSectionDialog.vue'
import DeliverableHandbookDialog from '@/components/deliverable/DeliverableHandbookDialog.vue'
import {
  deliverableDownloadUrl,
  deliverableGuidanceDownloadUrl,
  fetchDeliverables,
  fetchVersionChain,
  fetchCompleteness,
  approveDeliverable,
  archiveDeliverables,
  createPackage,
  packageFileUrl,
  createFullDeliverables,
  fetchExportJob,
  renderDisclosureNotes,
  renderFinancialReports,
  previewReportBody,
  confirmReportBody,
  rejectDeliverable,
  submitApproval,
  deleteDeliverable,
  type DeliverableItem,
  type DeliverableVersion,
  type OptionalSection,
} from '@/services/deliverableApi'
import {
  checkGenerateReady,
  type DataReadiness,
  type GenerateEntryKey,
} from '@/components/deliverable/generateGuard'
import { useProjectStore } from '@/stores/project'
import { getDisclosureReadiness } from '@/services/commonApi'

const route = useRoute()
const projectStore = useProjectStore()

const projectId = computed(() => route.params.projectId as string)
const year = computed(() => projectStore.year || new Date().getFullYear() - 1)

const loading = ref(false)
const generating = ref(false)
const packaging = ref(false)
const fullGenerating = ref(false)
const approvalLoading = ref(false)
const handbookVisible = ref(false)
const selectedItem = ref<DeliverableItem | null>(null)
const editorVisible = ref(false)
const editorItem = ref<DeliverableItem | null>(null)
const editorUrl = ref('')
const previewWatermark = ref(false)

// OnlyOffice 降级时传给 DeliverablePreview 的 previewType
// docx → VueOfficeDocx；pdf → VueOfficePdf；xlsx/xls → VueOfficeExcel（只读预览）
const editorPreviewType = computed<'docx' | 'pdf' | 'xlsx' | 'html' | 'unsupported'>(() => {
  let suffix = editorItem.value?.file_name?.split('.').pop()?.toLowerCase()
  if (!suffix) {
    const dt = editorItem.value?.doc_type || ''
    if (dt.startsWith('financial_report')) suffix = 'xlsx'
    else if (dt === 'disclosure_notes' || dt === 'audit_report') suffix = 'docx'
  }
  if (suffix === 'docx') return 'docx'
  if (suffix === 'pdf') return 'pdf'
  if (suffix === 'xlsx' || suffix === 'xls') return 'xlsx'
  return 'unsupported'
})
const items = ref<DeliverableItem[]>([])
const grouped = ref<Record<string, DeliverableItem[]>>({})
const filterDocType = ref('')
const filterStatus = ref('')
const filterKeyword = ref('')
const expandedTaskId = ref<string | null>(null)
const versionChain = ref<DeliverableVersion[]>([])
const showExportDialog = ref(false)
const notesDialogVisible = ref(false)
const showGenerateReport = ref(false)
const showGenerateReports = ref(false)
const financialReportDataMode = ref<'audited' | 'unadjusted'>('audited')
const selectedReportTypes = ref<string[]>(['balance_sheet', 'income_statement', 'cash_flow_statement', 'equity_statement', 'impairment_provision'])
const previewVisible = ref(false)
const previewTitle = ref('')
const previewType = ref<'docx' | 'pdf' | 'xlsx' | 'html' | 'unsupported'>('html')
const previewUrl = ref('')
const previewHtml = ref('')

const genForm = ref({
  opinion_type: 'unqualified',
  company_type: 'non_listed',
  is_pie: false,
})

// ── 报告正文两阶段生成（preview → OPT 弹窗 → confirm，走真实 Word 模板）──
const optDialogVisible = ref(false)
const optSections = ref<OptionalSection[]>([])
const optMissingFields = ref<string[]>([])
const optTemplateVersion = ref('')
const optCompanySubtype = ref('')
const optPreviewSessionId = ref('')
const confirmReportLoading = ref(false)

// 生成入口前置数据就绪状态（需求 21.4 / Property 37）
const readiness = ref<DataReadiness>({ trialBalanceReady: false, reportsReady: false })

/**
 * 三类生成入口统一前置检查（需求 21.4/21.7）。
 * 未就绪时阻止生成并给出前置检查提示，返回是否放行。
 */
function guardGenerate(entry: GenerateEntryKey): boolean {
  const result = checkGenerateReady(entry, readiness.value)
  if (!result.allowed) {
    ElMessage.warning(result.message)
  }
  return result.allowed
}

const DOC_TYPE_LABEL: Record<string, string> = {
  audit_report: '审计报告正文',
  financial_report: '财务报表（审定）',
  financial_report_unadjusted: '财务报表（未审）',
  disclosure_notes: '附注',
  full_package: '全套包',
}

async function loadList() {
  loading.value = true
  try {
    const res = await fetchDeliverables(projectId.value, {
      doc_type: filterDocType.value || undefined,
      status: filterStatus.value || undefined,
      keyword: filterKeyword.value || undefined,
    })
    items.value = res.items
    grouped.value = res.grouped
    await refreshReadiness()
  } catch (e) {
    ElMessage.error('加载交付物列表失败')
  } finally {
    loading.value = false
  }
}

// 拉取完整性状态，推导生成入口前置就绪标志（需求 21.4）
async function refreshReadiness() {
  try {
    const c = await fetchCompleteness(projectId.value, year.value)
    readiness.value = {
      // 财务报表已生成：未列入缺失件清单
      reportsReady: !c.missing_doc_types.includes('financial_report'),
      // 试算表就绪：报表能生成则视为底层数据已就绪
      trialBalanceReady: c.missing_financial_reports.length === 0 || !c.missing_doc_types.includes('financial_report'),
    }
  } catch {
    /* 完整性接口不可用时不阻断列表展示 */
  }
}

async function toggleVersions(taskId: string) {
  if (expandedTaskId.value === taskId) {
    expandedTaskId.value = null
    versionChain.value = []
    return
  }
  expandedTaskId.value = taskId
  versionChain.value = await fetchVersionChain(projectId.value, taskId)
}

function downloadItem(item: DeliverableItem) {
  const url = deliverableDownloadUrl(projectId.value, item.task_id, item.version_no)
  downloadFile(url, { fileName: item.file_name || `deliverable_v${item.version_no}` })
}

/**
 * 下载「编制参考版」（含内部 ##NOTE## 提示的 with_notes 副本，§13.2）。
 * 仅供项目组编制参考，不可对外出具。走 axios blob 认证下载（downloadFile 内部
 * 带 Bearer，404 时提示重新生成）。
 */
async function downloadGuidanceVersion(item: DeliverableItem) {
  const url = deliverableGuidanceDownloadUrl(projectId.value, item.task_id, item.version_no)
  try {
    await downloadFile(url, {
      fileName: `审计报告正文（编制参考版）_v${item.version_no}.docx`,
      silent: true,
    })
    ElMessage.info('编制参考版仅供项目组编制参考，不可对外出具')
  } catch {
    ElMessage.warning('编制参考版不存在，该版本可能由旧流程生成，请重新生成报告正文')
  }
}

async function confirmDeleteItem(item: DeliverableItem) {
  try {
    await ElMessageBox.confirm(
      `确认删除「${item.file_name || item.doc_type}」？此操作不可恢复。`,
      '删除交付物',
      { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' },
    )
    await deleteDeliverable(projectId.value, item.task_id)
    ElMessage.success('交付物已删除')
    await loadList()
    if (selectedItem.value?.task_id === item.task_id) selectedItem.value = null
  } catch { /* 用户取消 */ }
}

function selectItem(item: DeliverableItem) {
  selectedItem.value = item
}

function openEditor(item: DeliverableItem) {
  editorItem.value = item
  editorUrl.value = deliverableDownloadUrl(projectId.value, item.task_id, item.version_no)
  editorVisible.value = true
}

async function openPreview(item: DeliverableItem) {
  selectedItem.value = item
  previewTitle.value = item.file_name || DOC_TYPE_LABEL[item.doc_type] || '预览'
  previewHtml.value = ''
  previewUrl.value = deliverableDownloadUrl(projectId.value, item.task_id, item.version_no)
  previewWatermark.value = ['draft', 'editing'].includes(item.status)
  // 从 file_name 推导后缀；file_name 为空时从 doc_type 推导默认格式
  let suffix = item.file_name?.split('.').pop()?.toLowerCase()
  if (!suffix) {
    // doc_type → 默认格式：financial_report* → xlsx，disclosure_notes/audit_report → docx
    const dt = item.doc_type || ''
    if (dt.startsWith('financial_report')) suffix = 'xlsx'
    else if (dt === 'disclosure_notes' || dt === 'audit_report') suffix = 'docx'
  }

  // xlsx 走 OnlyOffice 编辑器（只读预览），不可用时自动降级
  if (suffix === 'xlsx' || suffix === 'xls') {
    editorItem.value = item
    editorUrl.value = previewUrl.value
    editorVisible.value = true
    return
  }

  // docx 也走 OnlyOffice（高保真），不可用时 OnlyOfficeEditor 内部降级到 @vue-office/docx
  if (suffix === 'docx') {
    editorItem.value = item
    editorUrl.value = previewUrl.value
    editorVisible.value = true
    return
  }

  if (suffix === 'pdf') previewType.value = 'pdf'
  else previewType.value = 'unsupported'
  previewVisible.value = true
}

function openGenerateReport() {
  if (!guardGenerate('report_body')) return
  showGenerateReport.value = true
}

async function goGenerateReports() {
  if (!guardGenerate('reports')) return
  selectedReportTypes.value = ['balance_sheet', 'income_statement', 'cash_flow_statement', 'equity_statement', 'impairment_provision']
  showGenerateReports.value = true
}

async function confirmGenerateReports() {
  generating.value = true
  showGenerateReports.value = false
  try {
    const isUnadjusted = financialReportDataMode.value === 'unadjusted'
    const res = await renderFinancialReports(projectId.value, {
      year: year.value,
      report_types: selectedReportTypes.value,
      data_mode: financialReportDataMode.value,
    })
    if (res.platform_persist_failed) {
      ElMessage.warning('平台留存失败，请从版本链重新下载')
    } else {
      ElMessage.success(isUnadjusted ? '未审财务报表已生成并保存到交付中心' : '财务报表已生成并保存到交付中心')
    }
    const dlName = isUnadjusted
      ? `financial_reports_unadjusted_${year.value}.xlsx`
      : `financial_reports_${year.value}.xlsx`
    downloadFile(deliverableDownloadUrl(projectId.value, res.task_id, res.version_no), { fileName: dlName })
    await loadList()
  } catch {
    ElMessage.error('生成财务报表失败')
  } finally {
    generating.value = false
  }
}

function goGenerateNotes() {
  // 权限门控保留在打开前；不再直接调渲染接口，改为弹出章节选择对话框
  if (!guardGenerate('notes')) return
  notesDialogVisible.value = true
}

/**
 * 附注选择对话框「确认生成」回调：以用户勾选的 selected_sections 生成交付 docx。
 * 不传 template_type（后端从 Project.template_type 权威解析变体）。
 * P2-10: 生成前附注质量预检（校验未通过/stale/未同步），不硬阻断但明确提示。
 */
async function onNotesSelectionConfirm({ selectedSections }: { selectedSections: string[] }) {
  // P2-10: 质量预检——调 readiness 获取统计，有问题时提示确认
  try {
    const readiness = await getDisclosureReadiness(projectId.value, year.value)
    const s = readiness?.summary
    if (s) {
      const issues: string[] = []
      if (s.error_sections > 0) issues.push(`校验错误 ${s.error_sections} 章`)
      if (s.never_synced > 0) issues.push(`未从底稿同步 ${s.never_synced} 章`)
      if (s.stale > 0) issues.push(`上游已变更(stale) ${s.stale} 章`)
      if (s.empty > 0) issues.push(`无数据 ${s.empty} 章`)
      if (issues.length > 0) {
        const msg = `<p style="margin-bottom:8px;font-weight:600;">📋 附注质量检查发现以下问题：</p>` +
          issues.map(i => `<p style="color:#e74c3c;margin:2px 0;">• ${i}</p>`).join('') +
          `<p style="margin-top:10px;color:#666;font-size:12px;">仍可继续生成，但导出文档可能存在缺失或过时数据。</p>`
        await ElMessageBox.confirm(msg, '附注质量检查', {
          confirmButtonText: '仍然生成',
          cancelButtonText: '返回检查',
          type: 'warning',
          dangerouslyUseHTMLString: true,
        })
      }
    }
  } catch (qualityErr: any) {
    // 质量预检失败不阻断生成（fail-open）
    if (qualityErr === 'cancel' || qualityErr?.toString?.()?.includes?.('cancel')) return
  }

  generating.value = true
  try {
    const res = await renderDisclosureNotes(projectId.value, {
      year: year.value,
      selected_sections: selectedSections,
    })
    if (res.platform_persist_failed) {
      ElMessage.warning('平台留存失败，请从版本链重新下载')
    } else {
      ElMessage.success('附注已生成并保存到交付中心')
    }
    // 附注联动复盘 P1-3：出具前软闸门提示（后端返回，不阻断导出）
    const warnings = (res as any)?.warnings as string[] | undefined
    if (warnings?.length) {
      const esc = (s: string) =>
        s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      ElMessageBox.alert(
        warnings.map(w => `• ${esc(w)}`).join('<br/>'),
        '附注出具提醒（不影响本次导出）',
        { confirmButtonText: '我知道了', type: 'warning', dangerouslyUseHTMLString: true },
      ).catch(() => {})
    }
    downloadFile(deliverableDownloadUrl(projectId.value, res.task_id, res.version_no), { fileName: `disclosure_notes_${year.value}.docx` })
    await loadList()
    notesDialogVisible.value = false
  } catch {
    ElMessage.error('生成附注失败')
  } finally {
    generating.value = false
  }
}

async function runGenerateReport() {
  // 两阶段第一步：preview（不落库），走真实 Word 模板，返回可选段落
  generating.value = true
  try {
    const result = await previewReportBody(projectId.value, {
      year: year.value,
      opinion_type: genForm.value.opinion_type,
      company_subtype: null,
      template_variant: 'simple',
    })
    optPreviewSessionId.value = result.preview_session_id
    optSections.value = result.optional_sections || []
    optMissingFields.value = result.missing_fields || []
    optTemplateVersion.value = result.template_version || ''
    optCompanySubtype.value = result.company_subtype_resolved || ''
    showGenerateReport.value = false
    optDialogVisible.value = true
  } catch {
    ElMessage.error('生成报告正文预览失败')
  } finally {
    generating.value = false
  }
}

/** OPT 弹窗确认 → 两阶段第二步：confirm（入库，版本递增，真实 Word 模板填充） */
async function onReportOptConfirm(selections: Record<string, boolean>) {
  confirmReportLoading.value = true
  try {
    const res = await confirmReportBody(projectId.value, {
      year: year.value,
      preview_session_id: optPreviewSessionId.value,
      optional_sections: selections,
    })
    ElMessage.success('报告正文已生成并保存到交付中心')
    if (res.validation_warning) {
      ElMessage.warning(res.validation_warning)
    }
    optDialogVisible.value = false
    await loadList()
  } catch {
    ElMessage.error('生成报告正文失败')
  } finally {
    confirmReportLoading.value = false
  }
}

function onExportConfirm(_sections: string[]) {
  showExportDialog.value = false
  runGenerateReport()
}

/**
 * 一键生成全套（需求 14 / 设计 §14）。
 * 创建 ExportJob（job_type=full_deliverables）后轮询进度；完成时若有 KAM 警告则 Toast。
 * 报表 → 附注 → 报告正文顺序由后端执行器保证；前置守卫（试算表/报表就绪）由服务端校验。
 */
async function runGenerateFull() {
  // 前端先做依赖链根节点提示（报表就绪即视为试算表就绪），服务端再做权威校验
  if (!guardGenerate('reports')) return
  fullGenerating.value = true
  try {
    const job = await createFullDeliverables(projectId.value, {
      year: year.value,
      template_variant: 'simple',
    })
    ElMessage.success('已创建一键生成全套任务，正在生成…')
    const finalJob = await pollExportJob(job.id)
    await loadList()
    summarizeFullJob(finalJob)
  } catch (e: any) {
    const detail = e?.response?.data?.detail || e?.message || '一键生成全套失败'
    ElMessage.error(typeof detail === 'string' ? detail : '一键生成全套失败')
  } finally {
    fullGenerating.value = false
  }
}

/** 轮询 ExportJob 直至终态（succeeded/partial_failed/failed）或超时。 */
async function pollExportJob(jobId: string) {
  const TERMINAL = ['succeeded', 'partial_failed', 'failed', 'cancelled']
  let attempts = 0
  const maxAttempts = 60 // ~2min @ 2s
  // eslint-disable-next-line no-constant-condition
  while (attempts < maxAttempts) {
    const job = await fetchExportJob(projectId.value, jobId)
    if (TERMINAL.includes(job.status)) return job
    attempts += 1
    await new Promise((r) => setTimeout(r, 2000))
  }
  return await fetchExportJob(projectId.value, jobId)
}

/** 全套任务终态摘要：成功/部分失败提示 + KAM 警告 Toast（设计 §14 第 6 步）。 */
function summarizeFullJob(job: { status: string; payload: Record<string, unknown> | null; items: { status: string; word_export_task_id: string | null }[] }) {
  const kamWarning = job.payload?.kam_warning as string | null | undefined
  if (job.status === 'succeeded') {
    ElMessage.success(`全套交付件已生成（${job.items.length} 项）`)
  } else if (job.status === 'partial_failed') {
    const failed = job.items.filter((i) => i.status === 'failed').length
    ElMessage.warning(`全套生成部分完成：${failed} 项失败，可在任务中重试失败项`)
  } else if (job.status === 'failed') {
    ElMessage.error('全套生成失败，请检查前置数据后重试')
  }
  if (kamWarning) {
    ElMessage.warning(kamWarning)
  }
}
async function onSubmitApproval() {
  if (!selectedItem.value) return
  approvalLoading.value = true
  try {
    await submitApproval(projectId.value, selectedItem.value.task_id)
    ElMessage.success('已提交审批')
    await loadList()
  } catch {
    ElMessage.error('提交审批失败')
  } finally {
    approvalLoading.value = false
  }
}

async function onApprove() {
  if (!selectedItem.value) return
  approvalLoading.value = true
  try {
    await approveDeliverable(projectId.value, selectedItem.value.task_id, year.value)
    ElMessage.success('审批通过')
    await loadList()
  } catch {
    ElMessage.error('审批失败')
  } finally {
    approvalLoading.value = false
  }
}

async function onReject() {
  if (!selectedItem.value) return
  try {
    const { value } = await ElMessageBox.prompt('请输入驳回原因', '驳回审批', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    approvalLoading.value = true
    await rejectDeliverable(projectId.value, selectedItem.value.task_id, value)
    ElMessage.success('已驳回')
    await loadList()
  } catch {
    /* cancelled */
  } finally {
    approvalLoading.value = false
  }
}

async function runPackageDownload() {  packaging.value = true
  try {
    const res = await createPackage(projectId.value, { year: year.value, ignore_incomplete: true })
    if (res.warnings?.length) {
      ElMessage.warning(res.warnings.join('；'))
    }
    setTimeout(() => {
      downloadFile(packageFileUrl(projectId.value, res.job_id), { fileName: `deliverable_package.zip` })
    }, 1500)
    ElMessage.success('打包任务已创建')
  } catch {
    ElMessage.error('打包失败')
  } finally {
    packaging.value = false
  }
}

async function runArchive() {
  try {
    await ElMessageBox.confirm('确认归档本项目全部已确认/已签章交付物？', '项目归档')
    const res = await archiveDeliverables(projectId.value, { year: year.value, force: false })
    ElMessage.success(`已归档 ${res.archived_count} 项交付物`)
    await loadList()
  } catch {
    /* cancelled or failed */
  }
}

onMounted(loadList)
</script>

<style scoped>
.deliverable-center {
  padding: 20px 24px;
}
.deliverable-center__header {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 16px;
}
.deliverable-center__handbook-btn {
  margin-left: auto;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.deliverable-center__header-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  font-size: 24px;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border-radius: 10px;
}
.deliverable-center__header h2 {
  margin: 0 0 2px;
  font-size: 20px;
}
.deliverable-center__subtitle {
  margin: 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.deliverable-center__versions {
  margin-top: 12px;
}
</style>
