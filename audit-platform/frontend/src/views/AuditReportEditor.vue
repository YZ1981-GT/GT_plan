<template>
  <div class="gt-audit-report gt-fade-in">
    <div class="gt-ar-header">
      <div class="gt-ar-banner">
        <div class="gt-ar-banner-text">
          <h2>审计报告</h2>
          <p v-if="report">{{ opinionLabel(report.opinion_type) }} · {{ report.company_type === 'listed' ? '上市公司' : '非上市' }} · {{ statusLabel(report.status) }}</p>
          <p v-else>选择意见类型生成报告</p>
        </div>
        <div class="gt-ar-banner-actions">
          <el-button size="small" @click="showGenerateDialog = true" round>生成报告</el-button>
          <el-button v-if="report" size="small" @click="onStatusChange('review')" :disabled="report.status === 'final'" round>提交复核</el-button>
          <el-button v-if="report" size="small" @click="onStatusChange('final')" :disabled="report.status === 'final'" round>定稿</el-button>
        </div>
      </div>
    </div>

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
            <el-tag size="small" :type="statusTagType(report.status)">{{ statusLabel(report.status) }}</el-tag>
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
            <el-tag v-if="report.status !== 'final'" size="small" type="info">可编辑</el-tag>
            <el-tag v-else size="small" type="success">已定稿</el-tag>
          </div>
          <div class="gt-ar-edit-hint" v-if="report.status !== 'final'">
            直接编辑下方文本，修改单位名称、简称、关键审计事项等内容后点击保存
          </div>
          <el-input v-model="sectionContent" type="textarea" :rows="20"
            :disabled="report.status === 'final'" placeholder="段落内容"
            class="gt-ar-textarea" />
          <div class="gt-ar-editor-footer">
            <el-button type="primary" @click="onSaveParagraph" :loading="saveLoading"
              :disabled="report.status === 'final'">保存段落</el-button>
            <el-button @click="onRefreshFinancialData" :loading="refreshLoading"
              :disabled="report.status === 'final'">刷新财务数据</el-button>
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
          <el-select v-model="genForm.opinion_type" style="width: 100%">
            <el-option label="标准无保留意见" value="unqualified" />
            <el-option label="保留意见" value="qualified" />
            <el-option label="否定意见" value="adverse" />
            <el-option label="无法表示意见" value="disclaimer" />
          </el-select>
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
          <el-input v-model="genForm.entity_short_name" placeholder="如"XX公司"，留空则用全称" />
          <div style="font-size: 12px; color: #999; margin-top: 4px">
            生成后正文中的简称可随时修改
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showGenerateDialog = false">取消</el-button>
        <el-button type="primary" @click="onGenerate" :loading="genLoading">生成</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  generateAuditReport, getAuditReport, updateAuditReportParagraph,
  updateAuditReportStatus, type AuditReportData,
} from '@/services/auditPlatformApi'

const route = useRoute()
const projectId = computed(() => route.params.projectId as string)
const year = computed(() => Number(route.query.year) || new Date().getFullYear())

const loading = ref(false)
const genLoading = ref(false)
const saveLoading = ref(false)
const refreshLoading = ref(false)
const report = ref<AuditReportData | null>(null)
const activeSection = ref('')
const sectionContent = ref('')
const showGenerateDialog = ref(false)
const genForm = ref({
  opinion_type: 'unqualified',
  company_type: 'non_listed',
  report_scope: 'standalone',
  entity_short_name: '',
})

const sectionNames = computed(() => {
  if (!report.value?.paragraphs) return []
  return Object.keys(report.value.paragraphs)
})

watch(activeSection, (s) => {
  if (report.value?.paragraphs && s) {
    sectionContent.value = report.value.paragraphs[s] || ''
  }
})

function fmtAmt(v: any): string {
  if (v === null || v === undefined) return '-'
  const n = typeof v === 'string' ? parseFloat(v) || 0 : v
  if (n === 0) return '-'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function opinionLabel(t: string) {
  const m: Record<string, string> = { unqualified: '无保留', qualified: '保留', adverse: '否定', disclaimer: '无法表示' }
  return m[t] || t
}

function statusLabel(s: string) {
  const m: Record<string, string> = { draft: '草稿', review: '复核中', final: '已定稿' }
  return m[s] || s
}

function statusTagType(s: string) {
  const m: Record<string, string> = { draft: 'info', review: 'warning', final: 'success' }
  return m[s] || 'info'
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

async function onRefreshFinancialData() {
  if (!report.value) return
  refreshLoading.value = true
  try {
    // 重新生成会刷新财务数据但保留用户编辑的段落
    await generateAuditReport(projectId.value, year.value, report.value.opinion_type, report.value.company_type)
    await fetchReport()
    ElMessage.success('财务数据已刷新，段落内容已保留')
  } finally { refreshLoading.value = false }
}

onMounted(fetchReport)
</script>

<style scoped>
.gt-audit-report { padding: var(--gt-space-5); }

.gt-ar-header {
  margin-bottom: var(--gt-space-4);
}
.gt-ar-banner {
  display: flex; justify-content: space-between; align-items: center;
  background: var(--gt-gradient-primary);
  border-radius: var(--gt-radius-lg);
  padding: 18px 28px;
  color: #fff;
  position: relative; overflow: hidden;
  box-shadow: 0 4px 20px rgba(75, 45, 119, 0.2);
  background-image: var(--gt-gradient-primary), linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px);
  background-size: 100% 100%, 20px 20px, 20px 20px;
}
.gt-ar-banner::before {
  content: '';
  position: absolute; top: -40%; right: -10%;
  width: 45%; height: 180%;
  background: radial-gradient(ellipse, rgba(255,255,255,0.07) 0%, transparent 65%);
  pointer-events: none;
}
.gt-ar-banner-text h2 { margin: 0 0 2px; font-size: 18px; font-weight: 700; }
.gt-ar-banner-text p { margin: 0; font-size: 12px; opacity: 0.75; }
.gt-ar-banner-actions {
  display: flex; gap: 8px; align-items: center;
  position: relative; z-index: 1;
}
.gt-ar-banner-actions .el-button { background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.25); color: #fff; }
.gt-ar-banner-actions .el-button:hover { background: rgba(255,255,255,0.25); }
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
