<template>
  <div class="aud-screen">
    <header class="aud-header">
      <h1 class="aud-header__title">报告正文</h1>
      <span class="aud-header__note">取税审底稿 1-01 与申报主表 A100000；{{ canManualEdit ? '摘录表金额可修改，' : '' }}正文为法定文书表述，不改措辞</span>
    </header>

    <section class="aud-panel">
      <p v-if="!year" class="sheet-empty">{{ yearLoading ? '正在读取项目信息…' : '项目未设置审核年度，请先在项目信息里填写' }}</p>
      <template v-else>
        <div class="citar-toolbar">
          <template v-if="canManualEdit">
            <label class="rb-date">报告日期
              <input v-model="dateDraft" class="citar-search rb-date__input" type="date" :disabled="!data || saving" />
            </label>
            <button class="citar-btn" type="button" :disabled="!data || saving || dateDraft === (data?.report_date || '')" @click="saveDate">
              {{ saving ? '保存中…' : '保存日期' }}
            </button>
          </template>
          <span v-else class="rb-date">报告日期 {{ data?.report_date || '未填' }}</span>
          <button class="citar-btn" type="button" :disabled="loading" @click="load">刷新</button>
          <button class="citar-btn citar-btn--primary" type="button" :disabled="!data || exporting" @click="exportWord">
            {{ exporting ? '导出中…' : '导出 Word' }}
          </button>
          <span v-if="canManualEdit" class="citar-toolbar__hint">报告号在「税审底稿 → 索引 → 填写参数」填写</span>
          <span v-else class="citar-toolbar__hint">{{ MANUAL_EDIT_DENIED_TIP }}</span>
        </div>

        <div v-for="n in data?.notices ?? []" :key="n" class="citar-notice">{{ n }}</div>
        <p v-if="loading && !data" class="sheet-empty">正在生成报告正文…</p>
        <p v-else-if="error" class="sheet-empty">{{ error }}</p>

        <CitarReportBodyAmounts v-if="data" :data="data" :project-id="projectId" :year="year" @saved="onAmountsSaved" />

        <div v-if="data" class="rb-preview" aria-label="报告正文 Word 版式预览" :aria-busy="previewLoading">
          <p v-if="previewLoading" class="sheet-empty">正在生成报告版式…</p>
          <p v-if="previewError" class="sheet-empty" role="alert">{{ previewError }}</p>
          <div v-if="missingFonts.length" class="citar-notice" role="status">
            OnlyOffice 服务器缺少{{ missingFonts.join('、') }}字体，预览的字形、行距和分页与 Word 有差异，导出的 Word 不受影响；请联系管理员安装字体
          </div>
          <VueOfficePdf
            v-if="documentSource"
            :key="documentRevision"
            class="rb-preview__pdf"
            :src="documentSource"
            :options="PDF_OPTIONS"
            :static-file-url="PDF_STATIC_URL"
            @rendered="previewLoading = false"
            @error="onPreviewError"
          />
        </div>
      </template>
    </section>
  </div>
</template>

<script setup lang="ts">
/**
 * 报告正文（CITAR 鉴证报告 · 报告正文）：报告封面 + 正文，数据取税审底稿 1-01 与申报主表 A100000。
 * 报告日期可填写保存；导出 Word 以案例报告为模板，只替换单位、年度、报告号、日期与 25 个金额。
 * 网页预览 = 导出的同一份 Word 经 OnlyOffice 转成 PDF（浏览器端 docx 预览排不准这份模板的空段高、
 * 文档网格与固定行高，版式与 Word 不一致）。
 */
import { onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import VueOfficePdf from '@vue-office/pdf'
import { ElMessage } from 'element-plus'
import { handleApiError } from '@/utils/errorHandler'
import {
  downloadTaxAssurance, fetchReportBody, fetchReportBodyPreview, previewErrorReason, saveReportDate, type ReportBodyData,
} from '../taxAssuranceApi'
import CitarReportBodyAmounts from '../components/CitarReportBodyAmounts.vue'
import { useCitarProject } from '../useCitarProject'
import { MANUAL_EDIT_DENIED_TIP, useManualEditPermission } from '@/composables/useManualEditPermission'

defineOptions({ name: 'CitarReportBody' })

/**
 * pdf.js 静态文件目录（组件默认取 unpkg，内网打不开）。OnlyOffice 转出的 PDF 字体全部内嵌、
 * 编码 Identity-H，不读 cmaps，这里只是不让它去外网。
 */
const PDF_STATIC_URL = `${import.meta.env.BASE_URL}pdfjs/`
/**
 * 页面显示宽度：A4 宽 210mm 在 96dpi 下约 794px，即 Word「100% 显示比例」。
 * 不设时组件按容器撑满（内容区约 1150px 宽 ⇒ 放大到约 140%）；容器比它窄时组件自动缩小。
 */
const PDF_OPTIONS = { width: 794 }

const { projectId, year, yearLoading } = useCitarProject()
const { canManualEdit } = useManualEditPermission()
const data = ref<ReportBodyData | null>(null)
const loading = ref(false)
const saving = ref(false)
const exporting = ref(false)
const error = ref('')
const dateDraft = ref('')
const documentSource = shallowRef<ArrayBuffer>()
const documentRevision = ref(0)
const previewLoading = ref(false)
const previewError = ref('')
const missingFonts = ref<string[]>([])

let seq = 0
let previewSeq = 0
async function loadPreview() {
  const mine = ++previewSeq
  documentSource.value = undefined
  previewError.value = ''
  missingFonts.value = []
  previewLoading.value = false
  if (!year.value) return
  previewLoading.value = true
  try {
    const res = await fetchReportBodyPreview(projectId.value, year.value)
    if (mine !== previewSeq) return
    missingFonts.value = res.missingFonts
    documentRevision.value++
    documentSource.value = res.pdf
  } catch (e) {
    if (mine !== previewSeq) return
    onPreviewError(e)
  }
}

function onPreviewError(e?: unknown) {
  previewLoading.value = false
  documentSource.value = undefined
  const reason = previewErrorReason(e)
  previewError.value = `报告版式预览生成失败${reason ? `：${reason}` : ''}。可点击刷新重试，或导出 Word 查看`
}

async function load() {
  const mine = ++seq
  // 切换项目或年度时立即清除旧文档，迟到的响应不得覆盖当前预览。
  previewSeq++
  documentSource.value = undefined
  previewError.value = ''
  previewLoading.value = false
  data.value = null
  error.value = ''
  loading.value = false
  if (!year.value) return
  loading.value = true
  try {
    const res = await fetchReportBody(projectId.value, year.value)
    if (mine !== seq) return
    data.value = res
    dateDraft.value = res.report_date || ''
    await loadPreview()
  } catch (e: any) {
    if (mine === seq) error.value = e?.response?.data?.detail || e?.message || '生成报告正文失败'
  } finally {
    if (mine === seq) loading.value = false
  }
}

async function saveDate() {
  if (!data.value || !year.value) return
  saving.value = true
  try {
    data.value = await saveReportDate(projectId.value, year.value, data.value.version, dateDraft.value || null)
    dateDraft.value = data.value.report_date || ''
    ElMessage.success('报告日期已保存')
    await loadPreview()
  } catch (e: any) {
    if (e?.response?.status === 409) ElMessage.warning('报告已被他人修改，请刷新后再保存')
    else handleApiError(e, '保存报告日期')
  } finally {
    saving.value = false
  }
}

/** 摘录表金额保存后：用返回的新数据，重载 Word 预览 */
async function onAmountsSaved(res: ReportBodyData) {
  data.value = res
  await loadPreview()
}

async function exportWord() {
  if (!year.value || !data.value) return
  exporting.value = true
  try {
    await downloadTaxAssurance('reportBodyExport', projectId.value, year.value, `${data.value.cover.client || '报告'}_${year.value}年度纳税申报审核报告.docx`)
  } catch (e) {
    handleApiError(e, '导出报告正文')
  } finally {
    exporting.value = false
  }
}

watch([projectId, year], load, { immediate: true })
onBeforeUnmount(() => { seq++; previewSeq++ })
</script>

<style scoped src="../styles/audited.css"></style>
<style scoped src="../styles/unaudited.css"></style>
<style scoped src="../styles/citar-data.css"></style>
<style scoped src="../styles/assurance-doc.css"></style>

<style scoped>
.rb-preview {
  min-width: 0;
}
/* 组件自带竖向滚动 + 懒渲染页面，必须给定高度；灰底与 Word「页面视图」一致 */
.rb-preview__pdf {
  height: calc(100vh - 220px);
  min-height: 480px;
  border: 1px solid #e4d8f3;
  border-radius: 6px;
}
</style>
