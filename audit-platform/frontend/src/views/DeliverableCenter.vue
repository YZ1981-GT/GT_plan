<template>
  <div class="deliverable-center">
    <div class="deliverable-center__header">
      <h2>交付件管理中心</h2>
      <p class="deliverable-center__subtitle">选择性导出 · 版本管理 · 在线预览 · 报告正文生成</p>
    </div>

    <CompletenessBanner :project-id="projectId" :year="year" />

    <DeliverableToolbar
      v-model:doc-type="filterDocType"
      v-model:status="filterStatus"
      v-model:keyword="filterKeyword"
      :generating="generating"
      :packaging="packaging"
      @refresh="loadList"
      @generate-report="openGenerateReport"
      @generate-reports="goGenerateReports"
      @generate-notes="goGenerateNotes"
      @package-download="runPackageDownload"
      @archive="runArchive"
    />

    <ApprovalPanel
      v-if="selectedItem"
      :task-id="selectedItem.task_id"
      :status="selectedItem.status"
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
        @toggle-versions="toggleVersions"
        @preview="openPreview"
        @download="downloadItem"
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
      preview-type="docx"
      :preview-url="editorUrl"
      :show-watermark="['draft', 'editing'].includes(editorItem.status)"
      @close="editorVisible = false"
    />

    <!-- 生成财务报表选择弹窗 -->
    <el-dialog v-model="showGenerateReports" title="生成财务报表" width="440px">
      <p style="margin: 0 0 12px; color: var(--el-text-color-secondary); font-size: 13px">
        请选择要导出的报表类型：
      </p>
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
      <el-form label-width="120px">
        <el-form-item label="审计意见类型">
          <el-select v-model="genForm.opinion_type" style="width: 100%">
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
        <el-button type="primary" :loading="generating" @click="runGenerateReport">生成正文</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { downloadFile } from '@/utils/http'
import ApprovalPanel from '@/components/deliverable/ApprovalPanel.vue'
import CompletenessBanner from '@/components/deliverable/CompletenessBanner.vue'
import OnlyOfficeEditor from '@/components/deliverable/OnlyOfficeEditor.vue'
import DeliverableToolbar from '@/components/deliverable/DeliverableToolbar.vue'
import DeliverableGroupList from '@/components/deliverable/DeliverableGroupList.vue'
import DeliverableVersionList from '@/components/deliverable/DeliverableVersionList.vue'
import DeliverableExportDialog from '@/components/deliverable/DeliverableExportDialog.vue'
import DeliverablePreview from '@/components/deliverable/DeliverablePreview.vue'
import {
  deliverableDownloadUrl,
  fetchDeliverables,
  fetchVersionChain,
  fetchCompleteness,
  approveDeliverable,
  archiveDeliverables,
  createPackage,
  packageFileUrl,
  renderDisclosureNotes,
  renderFinancialReports,
  renderReportBody,
  rejectDeliverable,
  submitApproval,
  deleteDeliverable,
  type DeliverableItem,
  type DeliverableVersion,
} from '@/services/deliverableApi'
import {
  checkGenerateReady,
  type DataReadiness,
  type GenerateEntryKey,
} from '@/components/deliverable/generateGuard'
import { useProjectStore } from '@/stores/project'

const route = useRoute()
const projectStore = useProjectStore()

const projectId = computed(() => route.params.projectId as string)
const year = computed(() => projectStore.year || new Date().getFullYear() - 1)

const loading = ref(false)
const generating = ref(false)
const packaging = ref(false)
const approvalLoading = ref(false)
const selectedItem = ref<DeliverableItem | null>(null)
const editorVisible = ref(false)
const editorItem = ref<DeliverableItem | null>(null)
const editorUrl = ref('')
const previewWatermark = ref(false)
const items = ref<DeliverableItem[]>([])
const grouped = ref<Record<string, DeliverableItem[]>>({})
const filterDocType = ref('')
const filterStatus = ref('')
const filterKeyword = ref('')
const expandedTaskId = ref<string | null>(null)
const versionChain = ref<DeliverableVersion[]>([])
const showExportDialog = ref(false)
const showGenerateReport = ref(false)
const showGenerateReports = ref(false)
const selectedReportTypes = ref<string[]>(['balance_sheet', 'income_statement', 'cash_flow_statement', 'equity_statement', 'impairment_provision'])
const previewVisible = ref(false)
const previewTitle = ref('')
const previewType = ref<'docx' | 'pdf' | 'html' | 'unsupported'>('html')
const previewUrl = ref('')
const previewHtml = ref('')

const genForm = ref({
  opinion_type: 'unqualified',
  company_type: 'non_listed',
  is_pie: false,
})

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
  financial_report: '财务报表',
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
  const suffix = item.file_name?.split('.').pop()?.toLowerCase()

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
    const res = await renderFinancialReports(projectId.value, {
      year: year.value,
      report_types: selectedReportTypes.value,
    })
    if (res.platform_persist_failed) {
      ElMessage.warning('平台留存失败，请从版本链重新下载')
    } else {
      ElMessage.success('财务报表已生成并保存到交付中心')
    }
    downloadFile(deliverableDownloadUrl(projectId.value, res.task_id, res.version_no), { fileName: `financial_reports_${year.value}.xlsx` })
    await loadList()
  } catch {
    ElMessage.error('生成财务报表失败')
  } finally {
    generating.value = false
  }
}

async function goGenerateNotes() {
  if (!guardGenerate('notes')) return
  generating.value = true
  try {
    const res = await renderDisclosureNotes(projectId.value, { year: year.value })
    if (res.platform_persist_failed) {
      ElMessage.warning('平台留存失败，请从版本链重新下载')
    } else {
      ElMessage.success('附注已生成并保存到交付中心')
    }
    downloadFile(deliverableDownloadUrl(projectId.value, res.task_id, res.version_no), { fileName: `disclosure_notes_${year.value}.docx` })
    await loadList()
  } catch {
    ElMessage.error('生成附注失败')
  } finally {
    generating.value = false
  }
}

async function runGenerateReport() {
  generating.value = true
  try {
    const res = await renderReportBody(projectId.value, {
      year: year.value,
      opinion_type: genForm.value.opinion_type,
      company_type: genForm.value.company_type,
      is_pie: genForm.value.is_pie,
      include_emphasis: genForm.value.opinion_type === 'unqualified_with_emphasis',
    })
    if (res.platform_persist_failed) {
      ElMessage.warning('平台留存失败，文件已生成但请尽快下载')
    } else {
      ElMessage.success('报告正文已生成并保存到交付中心')
    }
    if (res.validation_warning) {
      ElMessage.warning(res.validation_warning)
    }
    showGenerateReport.value = false
    await loadList()
  } catch {
    ElMessage.error('生成报告正文失败')
  } finally {
    generating.value = false
  }
}

function onExportConfirm(_sections: string[]) {
  showExportDialog.value = false
  runGenerateReport()
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

async function runPackageDownload() {
  packaging.value = true
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
.deliverable-center__header h2 {
  margin: 0 0 4px;
  font-size: 20px;
}
.deliverable-center__subtitle {
  margin: 0 0 16px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.deliverable-center__versions {
  margin-top: 12px;
}
</style>
