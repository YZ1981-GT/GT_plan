<template>
  <div class="aud-screen">
    <header class="aud-header">
      <h1 class="aud-header__title">审核说明</h1>
      <span class="aud-header__note">按样表「审核报告说明」规则从税审底稿与申报表智能生成{{ canManualEdit ? '；每段可直接修改、删除，改过的段可恢复自动文字' : '' }}</span>
    </header>

    <section class="aud-panel">
      <p v-if="!year" class="sheet-empty">{{ yearLoading ? '正在读取项目信息…' : '项目未设置审核年度，请先在项目信息里填写' }}</p>
      <template v-else>
        <div class="citar-toolbar">
          <button class="citar-btn" type="button" :disabled="loading || saving" @click="load">{{ loading ? '生成中…' : '智能生成' }}</button>
          <button class="citar-btn citar-btn--primary" type="button" :disabled="!data || exporting" @click="exportWord">
            {{ exporting ? '导出中…' : '导出 Word' }}
          </button>
          <span v-if="data" class="citar-toolbar__count">共 {{ data.paragraphs.length }} 段<template v-if="editedCount">，人工修改 {{ editedCount }} 段</template></span>
          <span class="citar-toolbar__hint">无数据的事项按规则自动隐藏；编号自动生成；底稿或申报表改动后点「智能生成」</span>
        </div>

        <div v-for="n in data?.notices ?? []" :key="n" class="citar-notice">{{ n }}</div>
        <div v-if="!canManualEdit" class="citar-notice">{{ MANUAL_EDIT_DENIED_TIP }}</div>
        <p v-if="loading && !data" class="sheet-empty">正在智能生成审核说明…</p>
        <p v-else-if="error" class="sheet-empty">{{ error }}</p>

        <details v-if="data?.deleted.length" class="rn-extra">
          <summary>已删除的段落（{{ data.deleted.length }}）</summary>
          <div v-for="d in data.deleted" :key="d.key" class="rn-extra__item">
            <span>{{ d.auto_text }}</span>
            <button v-if="canManualEdit" class="citar-btn" type="button" :disabled="saving" @click="dropEdit(d.key, '已恢复该段')">恢复</button>
          </div>
        </details>
        <details v-if="data?.orphans.length" class="rn-extra" open>
          <summary>数据变化后不再显示的修改（{{ data.orphans.length }}）</summary>
          <div v-for="o in data.orphans" :key="o.key" class="rn-extra__item">
            <span>{{ o.text === null ? `（删除）${o.auto ?? ''}` : o.text }}</span>
            <button v-if="canManualEdit" class="citar-btn" type="button" :disabled="saving" @click="dropEdit(o.key, '已丢弃该修改')">丢弃</button>
          </div>
        </details>

        <article v-if="data" class="rb-paper">
          <div class="rn-header">
            <span>{{ data.header[0] }}</span>
            <span>{{ data.header[1] }}</span>
          </div>
          <div
            v-for="(p, i) in data.paragraphs"
            :key="p.key + '-' + i"
            class="rn-item"
            :class="{ 'rn-item--edited': p.edited }"
          >
            <template v-if="editingKey === p.key">
              <div class="rn-edit" :style="indentStyle(p)">
                <span v-if="p.number" class="rn-edit__number">{{ p.number }}</span>
                <textarea v-model="draft" class="rn-edit__input" rows="3" :aria-label="`修改第 ${i + 1} 段`" />
              </div>
              <div class="rn-actions rn-actions--editing">
                <button class="citar-btn citar-btn--primary" type="button" :disabled="saving || !draft.trim()" @click="saveParagraph(p)">保存</button>
                <button class="citar-btn" type="button" :disabled="saving" @click="editingKey = ''">取消</button>
              </div>
            </template>
            <template v-else>
              <p class="rn-p" :class="paragraphClass(p)" :style="indentStyle(p)">{{ p.text }}</p>
              <div class="rn-tags">
                <span v-if="p.edited" class="rn-tag" :title="`自动文字：${p.auto_body}`">已修改</span>
                <span v-if="p.auto_changed" class="rn-tag rn-tag--warn" :title="`现在的自动文字：${p.auto_body}`">自动文字已变化</span>
              </div>
              <div v-if="canManualEdit" class="rn-actions">
                <button class="citar-btn" type="button" :disabled="saving" @click="startEdit(p)">修改</button>
                <button class="citar-btn" type="button" :disabled="saving" @click="deleteParagraph(p)">删除本段</button>
                <button v-if="p.edited" class="citar-btn" type="button" :disabled="saving" @click="dropEdit(p.key, '已恢复自动文字')">恢复自动文字</button>
              </div>
            </template>
          </div>
          <div class="rn-footer">{{ data.footer.join('　') }}</div>
        </article>
      </template>
    </section>
  </div>
</template>

<script setup lang="ts">
/**
 * 审核说明（CITAR 鉴证报告 · 审核说明）：生成、预览、逐段修改、导出 Word。
 * 段落由后端按规则表算好（显示 / 隐藏、编号、句末标点）；人工修改按段落键整份保存（spec citar-table-manual-edit R8）：
 * 修改 = 换正文（编号仍自动）、删除 = 本段不出且不占编号、恢复 = 去掉修改。预览与导出 Word 用同一份段落。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { handleApiError } from '@/utils/errorHandler'
import {
  downloadTaxAssurance, fetchReviewNotes, saveReviewNotes,
  type ReviewEdit, type ReviewNotesData, type ReviewParagraph,
} from '../taxAssuranceApi'
import { useCitarProject } from '../useCitarProject'
import { MANUAL_EDIT_DENIED_TIP, useManualEditPermission } from '@/composables/useManualEditPermission'

defineOptions({ name: 'CitarReviewNotes' })

const { projectId, year, yearLoading } = useCitarProject()
const { canManualEdit } = useManualEditPermission()
const data = ref<ReviewNotesData | null>(null)
const loading = ref(false)
const saving = ref(false)
const exporting = ref(false)
const error = ref('')
const editingKey = ref('')
const draft = ref('')

const editedCount = computed(() => Object.keys(data.value?.edits ?? {}).length)

let seq = 0
async function load() {
  if (!year.value) return
  const mine = ++seq
  loading.value = true
  error.value = ''
  editingKey.value = ''
  try {
    const res = await fetchReviewNotes(projectId.value, year.value)
    if (mine === seq) data.value = res
  } catch (e: any) {
    if (mine === seq) error.value = e?.response?.data?.detail || e?.message || '生成审核说明失败'
  } finally {
    if (mine === seq) loading.value = false
  }
}

/** 在已保存的修改上改一项后整份提交 */
async function commitEdits(next: Record<string, ReviewEdit>, okText: string): Promise<boolean> {
  if (!data.value || !year.value) return false
  saving.value = true
  try {
    data.value = await saveReviewNotes(projectId.value, year.value, data.value.version, next)
    editingKey.value = ''
    ElMessage.success(okText)
    return true
  } catch (e: any) {
    if (e?.response?.status === 409) ElMessage.warning('审核说明已被他人修改，请点「智能生成」后再改')
    else handleApiError(e, '保存审核说明')
    return false
  } finally {
    saving.value = false
  }
}

function startEdit(p: ReviewParagraph) {
  editingKey.value = p.key
  draft.value = p.body
}

function saveParagraph(p: ReviewParagraph) {
  const text = draft.value.trim()
  const next = { ...(data.value?.edits ?? {}) }
  // 改回与自动文字一样 ⇒ 等于恢复
  if (text === p.auto_body.trim()) delete next[p.key]
  else next[p.key] = { text, auto: p.auto_body }
  void commitEdits(next, '已保存本段')
}

async function deleteParagraph(p: ReviewParagraph) {
  try {
    await ElMessageBox.confirm(`删除「${p.text.slice(0, 40)}${p.text.length > 40 ? '…' : ''}」？删除后可在「已删除的段落」里恢复。`, '删除本段', {
      type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
    })
  } catch {
    return
  }
  void commitEdits({ ...(data.value?.edits ?? {}), [p.key]: { text: null, auto: p.auto_body } }, '已删除本段')
}

function dropEdit(key: string, okText: string) {
  const next = { ...(data.value?.edits ?? {}) }
  delete next[key]
  void commitEdits(next, okText)
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

<style scoped>
.rn-item {
  position: relative;
  margin: 0 -10px;
  padding: 0 10px;
  border-left: 3px solid transparent;
}

.rn-item:hover {
  background: var(--citar-c-fbf9fe);
}

.rn-item--edited {
  border-left-color: var(--citar-c-6e0ba6);
}

.rn-tags {
  position: absolute;
  top: 2px;
  right: 10px;
  display: flex;
  gap: 4px;
}

.rn-tag {
  padding: 0 6px;
  border-radius: 3px;
  background: #f1e6fb;
  font-size: var(--citar-fs-11, 11px);
  color: var(--citar-c-6e0ba6);
}

.rn-tag--warn {
  background: #fff3df;
  color: var(--citar-c-8a5300);
}

.rn-actions {
  display: none;
  gap: 6px;
  padding: 0 0 6px;
}

.rn-item:hover .rn-actions,
.rn-actions--editing {
  display: flex;
}

.rn-edit {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  padding: 6px 0;
}

.rn-edit__number {
  padding-top: 4px;
  white-space: nowrap;
}

.rn-edit__input {
  flex: 1;
  padding: 4px 6px;
  border: 1px solid var(--citar-c-6e0ba6);
  border-radius: var(--gt-radius-sm);
  font: inherit;
  line-height: 1.7;
  resize: vertical;
}

.rn-extra {
  margin: 0 0 12px;
  border: 1px solid #eadff3;
  border-radius: var(--gt-radius-sm);
  background: var(--citar-c-fbf9fe);
  font-size: var(--citar-fs-13);
}

.rn-extra summary {
  padding: 8px 12px;
  color: var(--citar-c-4c1273);
  font-weight: 600;
  cursor: pointer;
}

.rn-extra__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 6px 12px;
  color: var(--citar-c-5c5c68);
}
</style>
