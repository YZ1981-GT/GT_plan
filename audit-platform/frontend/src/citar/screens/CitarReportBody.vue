<template>
  <div class="aud-screen">
    <header class="aud-header">
      <h1 class="aud-header__title">报告正文</h1>
      <span class="aud-header__note">取税审底稿 1-01 与申报主表 A100000；正文为法定文书表述，不改措辞</span>
    </header>

    <section class="aud-panel">
      <p v-if="!year" class="sheet-empty">{{ yearLoading ? '正在读取项目信息…' : '项目未设置审核年度，请先在项目信息里填写' }}</p>
      <template v-else>
        <div class="citar-toolbar">
          <label class="rb-date">报告日期
            <input v-model="dateDraft" class="citar-search rb-date__input" type="date" :disabled="!data || saving" />
          </label>
          <button class="citar-btn" type="button" :disabled="!data || saving || dateDraft === (data?.report_date || '')" @click="saveDate">
            {{ saving ? '保存中…' : '保存日期' }}
          </button>
          <button class="citar-btn" type="button" :disabled="loading" @click="load">刷新</button>
          <button class="citar-btn citar-btn--primary" type="button" :disabled="!data || exporting" @click="exportWord">
            {{ exporting ? '导出中…' : '导出 Word' }}
          </button>
          <span class="citar-toolbar__hint">报告号在「税审底稿 → 索引 → 填写参数」填写</span>
        </div>

        <div v-for="n in data?.notices ?? []" :key="n" class="citar-notice">{{ n }}</div>
        <p v-if="loading && !data" class="sheet-empty">正在生成报告正文…</p>
        <p v-else-if="error" class="sheet-empty">{{ error }}</p>

        <div v-if="data" ref="previewContainer" class="rb-preview" aria-label="报告正文 Word 预览" :aria-busy="previewLoading">
          <p v-if="previewLoading" class="sheet-empty">正在载入报告版式…</p>
          <p v-if="previewError" class="sheet-empty" role="alert">{{ previewError }}</p>
          <VueOfficeDocx
            v-if="documentSource"
            :key="documentRevision"
            :src="documentSource"
            :options="previewOptions"
            @rendered="onPreviewRendered"
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
 */
import { onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import VueOfficeDocx from '@vue-office/docx'
import '@vue-office/docx/lib/index.css'
import { ElMessage } from 'element-plus'
import { handleApiError } from '@/utils/errorHandler'
import { downloadTaxAssurance, fetchReportBody, fetchReportBodyDocument, saveReportDate, type ReportBodyData } from '../taxAssuranceApi'
import { useCitarProject } from '../useCitarProject'

defineOptions({ name: 'CitarReportBody' })

const { projectId, year, yearLoading } = useCitarProject()
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
const previewContainer = ref<HTMLElement>()
const previewOptions = {
  breakPages: true, ignoreLastRenderedPageBreak: false,
  renderHeaders: true, renderFooters: true, useBase64URL: true,
}

let seq = 0
let previewSeq = 0
async function loadPreview() {
  const mine = ++previewSeq
  documentSource.value = undefined
  previewError.value = ''
  previewLoading.value = false
  if (!year.value) return
  previewLoading.value = true
  try {
    const source = await fetchReportBodyDocument(projectId.value, year.value)
    if (mine !== previewSeq) return
    documentRevision.value++
    documentSource.value = source
  } catch {
    if (mine !== previewSeq) return
    onPreviewError()
  }
}

function onPreviewRendered() {
  // 同一位置同时有显式分页和 Word 缓存分页时，预览器会多生成一张空白页。
  for (const page of previewContainer.value?.querySelectorAll('section.docx') ?? []) {
    const body = page.querySelector('article')
    if (body && !body.textContent?.trim() && !body.querySelector('img, table, svg, canvas')) {
      page.remove()
    }
  }
  previewLoading.value = false
}

function onPreviewError() {
  previewLoading.value = false
  previewError.value = '报告版式加载失败，请点击刷新重试，或导出 Word 查看'
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
  overflow-x: auto;
}
.rb-preview :deep(.vue-office-docx) {
  height: auto;
  overflow: visible;
}
.rb-preview :deep(.docx-wrapper) {
  min-width: fit-content;
}
/* 案例封面无页眉；预览器在首页未定义页眉时会误用正文页眉。 */
.rb-preview :deep(section.docx:first-of-type > header) {
  visibility: hidden;
}
</style>
