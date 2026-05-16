<template>
  <div class="gt-audit-report gt-fade-in">
    <GtPageHeader title="审计报告" @back="router.push('/projects')">
      <template #actions>
        <GtToolbar @formula="() => {}" :show-edit-toggle="true" :is-editing="isEditing" @edit-toggle="isEditing ? exitEdit() : enterEdit()">
          <template #left>
            <el-button size="small" @click="showGenerateDialog = true" round>生成报告</el-button>
            <SharedTemplatePicker
              config-type="report_template"
              :project-id="projectId"
              :get-config-data="getReportConfigData"
              @applied="onReportTemplateApplied"
            />
            <el-button v-if="report" size="small" @click="onStatusChange('review')" :disabled="isLocked" round>提交复核</el-button>
            <el-button v-if="report" size="small" @click="onStatusChange('final')" :disabled="isLocked" round>定稿</el-button>
            <el-button size="small" @click="onExportWord" :loading="exportingWord" round>导出 Word</el-button>
            <el-button size="small" @click="onPickKnowledge" round title="选择知识库文档作为参考上下文">📚 知识库</el-button>
          </template>
        </GtToolbar>
      </template>
    </GtPageHeader>

    <!-- R8-S2-03：Stale 状态横幅 -->
    <div v-if="stale.isStale.value" class="gt-stale-banner">
      <span class="gt-stale-icon">⚠️</span>
      <span class="gt-stale-text">
        上游数据已变更（{{ stale.staleCount.value }} 张底稿待重算），报告引用数据可能过时
      </span>
      <el-button size="small" type="primary" :loading="stale.loading.value" @click="onStaleRecalc">
        🔄 点击重算
      </el-button>
    </div>

    <div v-if="isEditing" class="gt-edit-mode-ribbon"><span class="gt-edit-mode-icon">✏️</span> 编辑中 · 请记得保存</div>

    <!-- 编辑锁提示 -->
    <el-alert v-if="editLock.locked.value && !editLock.isMine.value" type="warning" :closable="false" style="margin-bottom: 8px">
      {{ editLock.lockedBy.value || '其他用户' }} 正在编辑，当前为只读模式
    </el-alert>

    <!-- 错报超限警告横幅（需求 20.2） -->
    <el-alert
      v-if="misstatementWarning"
      type="error"
      show-icon
      :closable="false"
      style="margin-bottom: 12px"
    >
      <template #title>⚠️ 未更正错报累计金额已超过整体重要性水平</template>
      <div style="font-size: var(--gt-font-size-xs); margin-top: 4px">
        请在未更正错报汇总表中更正错报或说明不更正原因，否则无法签字定稿
      </div>
    </el-alert>

    <div v-if="!report && !loading" class="gt-ar-empty-state">
      <p>暂无审计报告，请先生成</p>
      <el-button type="primary" @click="showGenerateDialog = true">生成报告</el-button>
    </div>

    <el-row v-if="report" :gutter="12" class="gt-ar-body">
      <!-- 左侧：段落导航 -->
      <el-col :span="5">
        <div class="gt-ar-panel gt-ar-nav-panel">
          <h4 class="gt-ar-panel-title">段落导航</h4>
          <div class="gt-ar-nav-info">
            <el-tag size="small">{{ opinionLabel(report.opinion_type) }}</el-tag>
            <el-tag size="small" type="info">{{ report.company_type === 'listed' ? '上市公司' : '非上市' }}</el-tag>
            <el-tag size="small" :type="(statusTagType(report.status)) || undefined">{{ statusLabel(report.status) }}</el-tag>
            <el-tag
              v-if="isLocked && (report as any).bound_dataset_id"
              size="small"
              type="info"
              effect="plain"
            >🔒 数据版本：已锁定</el-tag>
          </div>
          <el-menu :default-active="activeSection" @select="onSectionSelect" class="gt-ar-section-menu">
            <el-menu-item v-for="s in sectionNames" :key="s" :index="s">
              {{ s }}
            </el-menu-item>
          </el-menu>
        </div>
      </el-col>

      <!-- 中间：编辑器 -->
      <el-col :span="12">
        <div class="gt-ar-panel gt-ar-editor-panel">
          <div class="gt-ar-editor-header">
            <h4>{{ activeSection }}</h4>
            <el-tag v-if="report.status === REPORT_STATUS.DRAFT" size="small" type="info">可编辑</el-tag>
            <el-tag v-else-if="report.status === REPORT_STATUS.REVIEW" size="small" type="warning">⚠ 审阅中</el-tag>
            <el-tag v-else-if="report.status === REPORT_STATUS.EQCR_APPROVED" size="small" type="danger">🔒 EQCR 已锁定</el-tag>
            <el-tag v-else-if="report.status === REPORT_STATUS.FINAL" size="small" type="success">🔒 已定稿</el-tag>
          </div>
          <div class="gt-ar-edit-hint" v-if="!isLocked">
            直接编辑下方文本，修改单位名称、简称、关键审计事项等内容后点击保存
          </div>
          <div class="gt-ar-edit-hint" v-else-if="report.status === 'eqcr_approved'" style="background: var(--gt-color-wheat-light); color: var(--gt-color-wheat);">
            🔒 EQCR 已锁定审计意见，如需修改请联系独立复核合伙人解锁
          </div>
          <div v-if="knowledgeContextText" class="gt-ar-edit-hint" style="background: var(--gt-color-success-light); color: var(--gt-color-success); margin-bottom: 8px;">
            📎 已加载 {{ knowledgeDocCount }} 篇知识库参考文档
            <el-button size="small" link @click="clearKnowledgeContext" style="margin-left: 8px; color: var(--gt-color-success);">清除</el-button>
          </div>
          <el-input v-model="sectionContent" type="textarea" :rows="20"
            :disabled="isLocked" placeholder="段落内容"
            class="gt-ar-textarea" />
          <div class="gt-ar-editor-footer">
            <el-button type="primary" @click="onSaveParagraph" :loading="saveLoading"
              :disabled="isLocked">保存段落</el-button>
            <el-button @click="onRefreshFinancialData" :loading="refreshLoading"
              :disabled="isLocked">刷新财务数据</el-button>
          </div>
        </div>
      </el-col>

      <!-- 右侧：财务数据面板 -->
      <el-col :span="7">
        <div class="gt-ar-panel gt-ar-data-panel">
          <h4 class="gt-ar-panel-title">财务数据引用</h4>
          <div v-if="report.financial_data" class="gt-ar-fin-data-list">
            <div v-for="(val, key) in report.financial_data" :key="key" class="gt-ar-fin-data-item">
              <span class="gt-ar-fin-key">{{ key }}</span>
              <span class="gt-ar-fin-val">{{ fmtAmt(val) }}</span>
            </div>
          </div>
          <div v-else class="gt-ar-empty-hint">暂无财务数据</div>
          <div class="gt-ar-data-meta" v-if="report">
            <div v-if="report.report_date">报告日期: {{ report.report_date }}</div>
            <div v-if="report.signing_partner">签字合伙人: {{ report.signing_partner }}</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 生成报告弹窗 -->
    <el-dialog append-to-body v-model="showGenerateDialog" title="生成审计报告" width="500px">
      <el-form label-width="100px">
        <el-form-item label="意见类型">
          <el-select v-model="genForm.opinion_type" style="width: 100%" :disabled="isLocked">
            <el-option label="标准无保留意见" value="unqualified" />
            <el-option label="保留意见" value="qualified" />
            <el-option label="否定意见" value="adverse" />
            <el-option label="无法表示意见" value="disclaimer" />
          </el-select>
          <div v-if="report?.status === 'eqcr_approved'" style="font-size: var(--gt-font-size-xs); color: var(--gt-color-wheat); margin-top: 4px">
            🔒 EQCR 已锁定，意见类型不可修改
          </div>
        </el-form-item>
        <el-form-item label="公司类型">
          <el-select v-model="genForm.company_type" style="width: 100%">
            <el-option label="非上市公司" value="non_listed" />
            <el-option label="上市公司" value="listed" />
          </el-select>
        </el-form-item>
        <el-form-item label="报表口径">
          <el-select v-model="genForm.report_scope" style="width: 100%">
            <el-option label="单体报表" value="standalone" />
            <el-option label="合并报表" value="consolidated" />
          </el-select>
        </el-form-item>
        <el-form-item label="单位简称">
          <el-input v-model="genForm.entity_short_name" placeholder="如 XX公司，留空则用全称" />
          <div style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-top: 4px">
            生成后正文中的简称可随时修改
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showGenerateDialog = false">取消</el-button>
        <el-button type="primary" @click="onGenerate" :loading="genLoading" :disabled="isLocked">生成</el-button>
      </template>
    </el-dialog>

    <!-- 知识库文档选择弹窗 [R3.7] -->
    <KnowledgePickerDialog v-model:visible="knowledgePickerVisible" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  generateAuditReport, getAuditReport, updateAuditReportParagraph,
  updateAuditReportStatus, refreshAuditReportFinancialData, exportAuditReportWord,
  getMisstatementSummary,
  type AuditReportData,
} from '@/services/auditPlatformApi'
import SharedTemplatePicker from '@/components/shared/SharedTemplatePicker.vue'
import { fmtAmount } from '@/utils/formatters'
import { useDictStore } from '@/stores/dict'
import { useKnowledge, knowledgePickerVisible } from '@/composables/useKnowledge'
import { useEditMode } from '@/composables/useEditMode'
import { confirmLeave } from '@/utils/confirm'
import KnowledgePickerDialog from '@/components/common/KnowledgePickerDialog.vue'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import GtToolbar from '@/components/common/GtToolbar.vue'
import { useEditingLock } from '@/composables/useEditingLock'
import { REPORT_STATUS } from '@/constants/statusEnum'
import { handleApiError } from '@/utils/errorHandler'

const route = useRoute()
const router = useRouter()
const dictStore = useDictStore()
const { isEditing, isDirty, enterEdit, exitEdit, markDirty, clearDirty } = useEditMode()
const projectId = computed(() => route.params.projectId as string)
const year = computed(() => Number(route.query.year) || new Date().getFullYear())

// R8-S2-03：Stale 状态追踪
import { useStaleStatus } from '@/composables/useStaleStatus'
const stale = useStaleStatus(projectId)
async function onStaleRecalc() {
  await stale.recalc()
  await fetchReport()
}

const editLock = useEditingLock({
  resourceId: computed(() => 'report_' + (route.params.projectId as string || '')),
  resourceType: 'other',  // 审计报告无后端锁端点，降级为前端检测
  autoAcquire: false,
})

// 编辑锁联动：进入编辑时 acquire，退出时 release；他人持锁时强制退出
watch(() => isEditing.value, async (editing) => {
  if (editing) await editLock.acquire()
  else editLock.release()
})
watch(() => editLock.isMine.value, (mine) => {
  if (!mine && isEditing.value) exitEdit()
})

const loading = ref(false)
const genLoading = ref(false)
const saveLoading = ref(false)
const refreshLoading = ref(false)
const exportingWord = ref(false)
const report = ref<AuditReportData | null>(null)
const activeSection = ref('')
const sectionContent = ref('')
const showGenerateDialog = ref(false)
const misstatementWarning = ref(false)
const genForm = ref({
  opinion_type: 'unqualified',
  company_type: 'non_listed',
  report_scope: 'standalone',
  entity_short_name: '',
})

// ── 知识库上下文 [R3.7] ──
const { pickDocuments, buildContext } = useKnowledge()
const knowledgeContextText = ref('')
const knowledgeDocCount = ref(0)

async function onPickKnowledge() {
  const docs = await pickDocuments({ title: '选择参考文档（审计报告编辑时使用）', maxSelect: 5 })
  if (docs.length) {
    knowledgeContextText.value = await buildContext(docs)
    knowledgeDocCount.value = docs.length
    ElMessage.success(`已加载 ${docs.length} 篇参考文档`)
  }
}

function clearKnowledgeContext() {
  knowledgeContextText.value = ''
  knowledgeDocCount.value = 0
}

const sectionNames = computed(() => {
  if (!report.value?.paragraphs) return []
  return Object.keys(report.value.paragraphs)
})

const isLocked = computed(() => {
  const s = report.value?.status
  return s === REPORT_STATUS.EQCR_APPROVED || s === REPORT_STATUS.FINAL
})

watch(activeSection, (s) => {
  if (report.value?.paragraphs && s) {
    sectionContent.value = report.value.paragraphs[s] || ''
  }
})

const fmtAmt = fmtAmount

function opinionLabel(t: string) {
  const m: Record<string, string> = { unqualified: '无保留', qualified: '保留', adverse: '否定', disclaimer: '无法表示' }
  return m[t] || t
}

function statusLabel(s: string) {
  return dictStore.label('report_status', s)
}

function statusTagType(s: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  return dictStore.type('report_status', s) as '' | 'success' | 'warning' | 'info' | 'danger' | 'primary'
}

function onSectionSelect(s: string) { activeSection.value = s }

async function fetchReport() {
  loading.value = true
  try {
    report.value = await getAuditReport(projectId.value, year.value)
    if (sectionNames.value.length && !activeSection.value) {
      activeSection.value = sectionNames.value[0]
    }
  } catch { report.value = null }
  finally { loading.value = false }
}

async function onGenerate() {
  genLoading.value = true
  try {
    await generateAuditReport(projectId.value, year.value, genForm.value.opinion_type, genForm.value.company_type)
    ElMessage.success('审计报告生成完成')
    showGenerateDialog.value = false
    await fetchReport()
  } finally { genLoading.value = false }
}

async function onSaveParagraph() {
  if (!report.value || !activeSection.value) return
  saveLoading.value = true
  try {
    await updateAuditReportParagraph(report.value.id, activeSection.value, { content: sectionContent.value })
    report.value.paragraphs[activeSection.value] = sectionContent.value
    ElMessage.success('段落保存成功')
  } finally { saveLoading.value = false }
}

async function onStatusChange(status: string) {
  if (!report.value) return
  try {
    await updateAuditReportStatus(report.value.id, status)
    report.value.status = status
    ElMessage.success(`状态已更新为${statusLabel(status)}`)
  } catch { /* error handled by http interceptor */ }
}

async function onExportWord() {
  exportingWord.value = true
  try {
    const blob = await exportAuditReportWord(projectId.value, year.value)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `审计报告_${year.value}.docx`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('Word 导出成功')
  } catch (e: any) {
    handleApiError(e, 'Word 导出')
  } finally {
    exportingWord.value = false
  }
}

async function onRefreshFinancialData() {
  if (!report.value) return
  refreshLoading.value = true
  try {
    const result = await refreshAuditReportFinancialData(projectId.value, year.value)
    if (result?.financial_data) {
      report.value.financial_data = result.financial_data
    }
    ElMessage.success('财务数据已刷新')
  } catch (e: any) {
    // 降级：如果专用端点不可用，走重新生成
    try {
      await generateAuditReport(projectId.value, year.value, report.value.opinion_type, report.value.company_type)
      await fetchReport()
      ElMessage.success('财务数据已刷新（通过重新生成）')
    } catch {
      ElMessage.warning('刷新失败，请确认报表已生成')
    }
  } finally { refreshLoading.value = false }
}

onMounted(async () => {
  await fetchReport()
  // 需求 20.2：检查未更正错报是否超过重要性水平
  try {
    const summary = await getMisstatementSummary(projectId.value, year.value)
    if (summary?.exceeds_materiality === true) {
      misstatementWarning.value = true
    }
  } catch { /* 静默失败，不影响主流程 */ }
  // R8-S2-14：关闭浏览器/刷新前警告
  window.addEventListener('beforeunload', onBeforeUnload)
})

onUnmounted(() => {
  window.removeEventListener('beforeunload', onBeforeUnload)
})

// R8-S2-14：未保存拦截
onBeforeRouteLeave(async (_to, _from, next) => {
  if (!isDirty.value) { next(); return }
  try {
    await confirmLeave('审计报告')
    next()
  } catch {
    next(false)
  }
})

function onBeforeUnload(e: BeforeUnloadEvent) {
  if (isDirty.value) {
    e.preventDefault()
    e.returnValue = ''
  }
}

// ── 共享模板 ──
function getReportConfigData(): Record<string, any> {
  if (!report.value) return {}
  return {
    opinion_type: report.value.opinion_type,
    company_type: report.value.company_type,
    paragraphs: report.value.paragraphs || {},
    status: report.value.status,
  }
}

function onReportTemplateApplied(data: Record<string, any>) {
  if (!report.value) {
    ElMessage.warning('请先生成报告再引用模板')
    return
  }
  const paragraphs = data?.paragraphs || {}
  if (!Object.keys(paragraphs).length) {
    ElMessage.warning('模板中无段落数据')
    return
  }
  let applied = 0
  for (const [key, content] of Object.entries(paragraphs)) {
    if (report.value.paragraphs && !report.value.paragraphs[key]) {
      report.value.paragraphs[key] = content as string
      applied++
    }
  }
  if (applied > 0) {
    ElMessage.success(`已引用 ${applied} 个段落（已有内容的段落不覆盖）`)
    // 刷新当前编辑区
    if (activeSection.value && report.value.paragraphs?.[activeSection.value]) {
      sectionContent.value = report.value.paragraphs[activeSection.value]
    }
  } else {
    ElMessage.info('所有段落已有内容，未覆盖')
  }
}
</script>

<style scoped>
.gt-audit-report { padding: var(--gt-space-5); }

.gt-ar-actions { display: flex; gap: var(--gt-space-2); align-items: center; flex-wrap: wrap; }
.gt-ar-body { height: calc(100vh - 180px); }

.gt-ar-panel {
  background: var(--gt-color-bg-white); border-radius: var(--gt-radius-md);
  padding: var(--gt-space-4); box-shadow: var(--gt-shadow-sm);
  height: 100%; overflow-y: auto;
  border: 1px solid rgba(75, 45, 119, 0.04);
  transition: box-shadow var(--gt-transition-base);
}
.gt-ar-panel:hover { box-shadow: var(--gt-shadow-md); }

.gt-ar-panel-title {
  margin: 0 0 var(--gt-space-3); font-size: var(--gt-font-size-md); font-weight: 600;
  color: var(--gt-color-primary);
  display: flex; align-items: center; gap: 8px;
}
.gt-ar-panel-title::before {
  content: '';
  width: 3px; height: 14px;
  background: var(--gt-gradient-primary);
  border-radius: 2px;
}

.gt-ar-nav-info { display: flex; gap: var(--gt-space-1); flex-wrap: wrap; margin-bottom: var(--gt-space-3); }
.gt-ar-section-menu { border-right: none; }

.gt-ar-editor-header {
  margin-bottom: var(--gt-space-3);
  padding-bottom: var(--gt-space-3);
  border-bottom: 1px solid rgba(75, 45, 119, 0.06);
}
.gt-ar-editor-header h4 { margin: 0; font-size: var(--gt-font-size-md); font-weight: 600; }
.gt-ar-edit-hint {
  font-size: var(--gt-font-size-xs); color: var(--gt-color-teal);
  padding: 6px 10px; margin-bottom: var(--gt-space-2);
  background: var(--gt-color-teal-light); border-radius: var(--gt-radius-sm);
}
.gt-ar-textarea :deep(.el-textarea__inner) {
  font-family: var(--gt-font-family);
  font-size: var(--gt-font-size-base);
  line-height: 1.8;
}
.gt-ar-editor-footer { margin-top: var(--gt-space-4); text-align: right; padding-top: var(--gt-space-3); border-top: 1px solid rgba(75, 45, 119, 0.06); display: flex; justify-content: flex-end; gap: var(--gt-space-2); }

/* 财务数据面板 */
.gt-ar-fin-data-list { margin-bottom: var(--gt-space-3); }
.gt-ar-fin-data-item {
  display: flex; justify-content: space-between;
  padding: var(--gt-space-2) var(--gt-space-2);
  border-radius: var(--gt-radius-sm);
  font-size: var(--gt-font-size-sm);
  transition: background var(--gt-transition-fast);
}
.gt-ar-fin-data-item:hover { background: var(--gt-color-primary-bg); }
.gt-ar-fin-data-item:not(:last-child) { border-bottom: 1px solid rgba(75, 45, 119, 0.04); }
.gt-ar-fin-key { color: var(--gt-color-text-secondary); }
.gt-ar-fin-val { font-weight: 700; color: var(--gt-color-primary); }
.gt-ar-data-meta { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-top: var(--gt-space-2); }
.gt-ar-empty-state { text-align: center; padding: 60px 0; color: var(--gt-color-text-tertiary); }
.gt-ar-empty-hint { color: var(--gt-color-text-tertiary); font-size: var(--gt-font-size-sm); text-align: center; padding: var(--gt-space-5) 0; }
</style>
