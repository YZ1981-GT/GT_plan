<template>
  <div class="aud-screen">
    <header class="aud-header">
      <h1 class="aud-header__title">审核说明</h1>
      <span class="aud-header__note">按样表「审核报告说明」规则从税审底稿与申报表生成；修改文字请导出 Word 后编辑</span>
    </header>

    <section class="aud-panel">
      <p v-if="!year" class="sheet-empty">{{ yearLoading ? '正在读取项目信息…' : '项目未设置审核年度，请先在项目信息里填写' }}</p>
      <template v-else>
        <div class="citar-toolbar">
          <button class="citar-btn" type="button" :disabled="loading" @click="load">{{ loading ? '生成中…' : '重新生成' }}</button>
          <button class="citar-btn citar-btn--primary" type="button" :disabled="!data || exporting" @click="exportWord">
            {{ exporting ? '导出中…' : '导出 Word' }}
          </button>
          <span v-if="data" class="citar-toolbar__count">共 {{ data.paragraphs.length }} 段</span>
          <span class="citar-toolbar__hint">无数据的事项按规则自动隐藏；底稿或申报表改动后点「重新生成」</span>
        </div>

        <div v-for="n in data?.notices ?? []" :key="n" class="citar-notice">{{ n }}</div>
        <p v-if="loading && !data" class="sheet-empty">正在生成审核说明…</p>
        <p v-else-if="error" class="sheet-empty">{{ error }}</p>

        <article v-if="data" class="rb-paper">
          <div class="rn-header">
            <span>{{ data.header[0] }}</span>
            <span>{{ data.header[1] }}</span>
          </div>
          <p
            v-for="(p, i) in data.paragraphs"
            :key="p.row + '-' + i"
            class="rn-p"
            :class="paragraphClass(p)"
            :style="indentStyle(p)"
          >{{ p.text }}</p>
          <div class="rn-footer">{{ data.footer.join('　') }}</div>
        </article>
      </template>
    </section>
  </div>
</template>

<script setup lang="ts">
/**
 * 审核说明（CITAR 鉴证报告 · 审核说明）：只做生成、预览、导出 Word（用户 2026-11-03）。
 * 段落由后端按规则表算好（显示 / 隐藏、编号、句末标点），这里只按样式排版。
 */
import { ref, watch } from 'vue'
import { handleApiError } from '@/utils/errorHandler'
import { downloadTaxAssurance, fetchReviewNotes, type ReviewNotesData, type ReviewParagraph } from '../taxAssuranceApi'
import { useCitarProject } from '../useCitarProject'

defineOptions({ name: 'CitarReviewNotes' })

const { projectId, year, yearLoading } = useCitarProject()
const data = ref<ReviewNotesData | null>(null)
const loading = ref(false)
const exporting = ref(false)
const error = ref('')

let seq = 0
async function load() {
  if (!year.value) return
  const mine = ++seq
  loading.value = true
  error.value = ''
  try {
    const res = await fetchReviewNotes(projectId.value, year.value)
    if (mine === seq) data.value = res
  } catch (e: any) {
    if (mine === seq) error.value = e?.response?.data?.detail || e?.message || '生成审核说明失败'
  } finally {
    if (mine === seq) loading.value = false
  }
}

async function exportWord() {
  if (!year.value) return
  exporting.value = true
  try {
    await downloadTaxAssurance('reviewNotesExport', projectId.value, year.value, `${year.value}年度纳税申报审核报告说明.docx`)
  } catch (e) {
    handleApiError(e, '导出审核说明')
  } finally {
    exporting.value = false
  }
}

function paragraphClass(p: ReviewParagraph) {
  return [
    p.level ? `rn-p--h${p.level}` : p.style === '文本2' ? 'rn-p--text2' : 'rn-p--text1',
    p.bold ? 'rn-p--bold' : '',
  ]
}

/** 规则表 H 列缩进（厘米）→ 左内边距 */
function indentStyle(p: ReviewParagraph) {
  const [left] = p.indent
  return left ? { marginLeft: `${left}cm` } : undefined
}

watch([projectId, year], load, { immediate: true })
</script>

<style scoped src="../styles/audited.css"></style>
<style scoped src="../styles/unaudited.css"></style>
<style scoped src="../styles/citar-data.css"></style>
<style scoped src="../styles/assurance-doc.css"></style>
