<template>
  <div class="audit-report-page">
    <div class="ar-header">
      <h2 class="ar-title">审计报告</h2>
      <div class="ar-actions">
        <el-button @click="showGenerateDialog = true" type="primary">生成报告</el-button>
        <el-button v-if="report" @click="onStatusChange('review')"
          :disabled="report.status === 'final'">提交复核</el-button>
        <el-button v-if="report" @click="onStatusChange('final')"
          :disabled="report.status === 'final'" type="success">定稿</el-button>
      </div>
    </div>

    <div v-if="!report && !loading" class="empty-state">
      <p>暂无审计报告，请先生成</p>
      <el-button type="primary" @click="showGenerateDialog = true">生成报告</el-button>
    </div>

    <el-row v-if="report" :gutter="12" class="ar-body">
      <!-- 左侧：段落导航 -->
      <el-col :span="5">
        <div class="panel nav-panel">
          <h4 class="panel-title">段落导航</h4>
          <div class="nav-info">
            <el-tag size="small">{{ opinionLabel(report.opinion_type) }}</el-tag>
            <el-tag size="small" type="info">{{ report.company_type === 'listed' ? '上市公司' : '非上市' }}</el-tag>
            <el-tag size="small" :type="statusTagType(report.status)">{{ statusLabel(report.status) }}</el-tag>
          </div>
          <el-menu :default-active="activeSection" @select="onSectionSelect" class="section-menu">
            <el-menu-item v-for="s in sectionNames" :key="s" :index="s">
              {{ s }}
            </el-menu-item>
          </el-menu>
        </div>
      </el-col>

      <!-- 中间：编辑器 -->
      <el-col :span="12">
        <div class="panel editor-panel">
          <div class="editor-header">
            <h4>{{ activeSection }}</h4>
          </div>
          <el-input v-model="sectionContent" type="textarea" :rows="16"
            :disabled="report.status === 'final'" placeholder="段落内容" />
          <div class="editor-footer">
            <el-button type="primary" @click="onSaveParagraph" :loading="saveLoading"
              :disabled="report.status === 'final'">保存段落</el-button>
          </div>
        </div>
      </el-col>

      <!-- 右侧：财务数据面板 -->
      <el-col :span="7">
        <div class="panel data-panel">
          <h4 class="panel-title">财务数据引用</h4>
          <div v-if="report.financial_data" class="fin-data-list">
            <div v-for="(val, key) in report.financial_data" :key="key" class="fin-data-item">
              <span class="fin-key">{{ key }}</span>
              <span class="fin-val">{{ fmtAmt(val) }}</span>
            </div>
          </div>
          <div v-else class="empty-hint">暂无财务数据</div>
          <div class="data-meta" v-if="report">
            <div v-if="report.report_date">报告日期: {{ report.report_date }}</div>
            <div v-if="report.signing_partner">签字合伙人: {{ report.signing_partner }}</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 生成报告弹窗 -->
    <el-dialog v-model="showGenerateDialog" title="生成审计报告" width="450px">
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
const report = ref<AuditReportData | null>(null)
const activeSection = ref('')
const sectionContent = ref('')
const showGenerateDialog = ref(false)
const genForm = ref({ opinion_type: 'unqualified', company_type: 'non_listed' })

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

onMounted(fetchReport)
</script>

<style scoped>
.audit-report-page { padding: 16px; }
.ar-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.ar-title { margin: 0; color: var(--gt-color-primary); font-size: 20px; }
.ar-actions { display: flex; gap: 8px; }
.ar-body { height: calc(100vh - 180px); }
.panel { background: #fff; border-radius: var(--gt-radius-sm); padding: 12px; box-shadow: var(--gt-shadow-sm); height: 100%; overflow-y: auto; }
.panel-title { margin: 0 0 8px; font-size: 14px; color: var(--gt-color-primary); }
.nav-info { display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 8px; }
.section-menu { border-right: none; }
.editor-header { margin-bottom: 8px; }
.editor-header h4 { margin: 0; font-size: 15px; }
.editor-footer { margin-top: 12px; text-align: right; }
.fin-data-list { margin-bottom: 12px; }
.fin-data-item { display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px solid #f0f0f0; font-size: 13px; }
.fin-key { color: #666; }
.fin-val { font-weight: 600; color: var(--gt-color-primary); }
.data-meta { font-size: 12px; color: #999; margin-top: 8px; }
.empty-state { text-align: center; padding: 60px 0; color: #999; }
.empty-hint { color: #999; font-size: 13px; text-align: center; padding: 20px 0; }
</style>
