<script setup lang="ts">
/**
 * NotePriorYearImportDialog — 上传上年附注 Word，逐表核对「上年期末 → 本年期初」后写入
 * （spec consol-note-header-library-and-node-reaggregate R6.6 / design §15.6）。
 *
 * 认不出的表不再静默丢弃：预览列出本年每张有期初列的表的状态与原因；自动认出的默认勾选，待确认的可改选上年表、
 * 逐列指定上年列或不导入。写入时重传同一文件并带预览给的文件指纹（文件变了 / 附注被改过 ⇒ 服务端拒绝，必须重新预览）。
 * 只填空格、不覆盖已有值；正文可选是否一并导入（会替换本年正文，内容模板写过的章节不动），导入正文前二次确认。
 */
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { notifyBatchError } from '@/composables/useNoteTextBatch'
import {
  applyPriorYear, appliedText, columnsText, fillableOf, hasMappedColumn, initialChoices, METHOD_LABELS,
  previewPriorYear, previewSummary, priorTableLabel, setColumn, STATUS_META, STATUS_ORDER, switchPriorTable, tableLabel,
  toDecisions, type PlanStatus, type PriorYearApplied, type PriorYearPreview, type TableChoice, type TablePlanItem,
} from './notePriorYearImport'

const props = defineProps<{ visible: boolean; projectId: string; year: number }>()
const emit = defineEmits<{ 'update:visible': [value: boolean]; 'applied': [result: PriorYearApplied] }>()

const MAX_BYTES = 50 * 1024 * 1024
const fileInput = ref<HTMLInputElement | null>(null)
const file = ref<File | null>(null)
const preview = ref<PriorYearPreview | null>(null)
const choices = ref<Record<string, TableChoice>>({})
const importText = ref(true)
const filter = ref<PlanStatus | 'all'>('all')
const editingKey = ref<string | null>(null)
const loading = ref(false)
const applying = ref(false)
const error = ref('')
/** 写入被拒（文件变了 / 附注被改过 / 确认不合法）⇒ 预览已不代表服务端现状，必须重新预览 */
const stale = ref(false)
/** 预览后改过勾选或对应（关闭前确认） */
const touched = ref(false)

const priorById = computed(() => new Map((preview.value?.prior_tables ?? []).map(t => [t.id, t])))
const shownTables = computed(() => (preview.value?.tables ?? [])
  .filter(t => filter.value === 'all' || t.status === filter.value))
const plan = computed(() => preview.value ? toDecisions(preview.value, choices.value) : { decisions: [], problems: [] })
const withText = computed(() => importText.value && (preview.value?.text_sections ?? 0) > 0)
const canApply = computed(() => !!preview.value && !stale.value && !applying.value && !loading.value
  && !plan.value.problems.length && (plan.value.decisions.length > 0 || withText.value))

async function onFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const picked = input.files?.[0]
  input.value = ''
  if (!picked) return
  const reject = !/\.docx$/i.test(picked.name) ? '仅支持 .docx 文件（.doc 请先在 Word 里另存为 .docx）'
    : picked.size > MAX_BYTES ? '文件大小不能超过 50MB' : ''
  if (reject) {
    error.value = `${picked.name}：${reject}`
    ElMessage.error(error.value)
    return
  }
  file.value = picked
  await runPreview()
}

async function runPreview() {
  if (!file.value) return
  loading.value = true
  error.value = ''
  try {
    const result = await previewPriorYear(props.projectId, props.year, file.value)
    if (result.status !== 'preview') {
      preview.value = null
      error.value = result.message
      return
    }
    preview.value = result
    choices.value = initialChoices(result)
    stale.value = false
    touched.value = false
    editingKey.value = null
    filter.value = result.counts.needs_confirm ? 'needs_confirm' : 'all'
  } catch (e) {
    const err = notifyBatchError(e, '上年附注解析失败', props.projectId, true, file.value.name)
    if (err.code !== 'CANCELED') error.value = err.message
  } finally {
    loading.value = false
  }
}

function update(key: string, next: TableChoice) {
  choices.value = { ...choices.value, [key]: next }
  touched.value = true
}

function setInclude(item: TablePlanItem, include: boolean) {
  const choice = choices.value[item.key]
  if (!choice) return
  update(item.key, { ...choice, include })
  if (include && !choice.priorTableId) editingKey.value = item.key  // 勾了但还没选上年表：直接展开让用户选
}

function onPickTable(item: TablePlanItem, value: unknown) {
  update(item.key, switchPriorTable(item, typeof value === 'string' && value ? value : null))
}

function onPickColumn(item: TablePlanItem, col: number, value: unknown) {
  const choice = choices.value[item.key]
  if (choice) update(item.key, setColumn(choice, col, typeof value === 'number' ? value : null))
}

/** 上年表下拉：本节的表在前（有现成列对应），其他章节的表在后（逐列指定） */
function tableOptions(item: TablePlanItem) {
  const own = new Set(item.candidates)
  const all = preview.value?.prior_tables ?? []
  return [
    { label: '上年本节的表', options: all.filter(t => own.has(t.id)) },
    { label: '上年其他章节的表（需逐列指定）', options: all.filter(t => !own.has(t.id)) },
  ].filter(g => g.options.length)
}

function chosenPrior(item: TablePlanItem) {
  const tid = choices.value[item.key]?.priorTableId
  return tid ? priorById.value.get(tid) : undefined
}

/** 「上年表：… ；期初余额 ← 期末余额」；没选上年表只说不导入 */
function mappingText(item: TablePlanItem): string {
  const prior = chosenPrior(item)
  if (!prior) return '上年表：不导入'
  return `上年表：${priorTableLabel(prior, item)}；${columnsText(item, choices.value[item.key], prior)}`
}

function fillText(item: TablePlanItem): string {
  const choice = choices.value[item.key]
  if (!choice?.priorTableId) return '未选上年表'
  if (!hasMappedColumn(choice)) return '未指定列（点「调整」逐列指定）'
  const n = fillableOf(item, choice)
  return n === null ? '可填格数以写入结果为准' : n ? `可填 ${n} 格` : '可填 0 格（行名对不上或本年已有值）'
}

async function onApply() {
  if (!preview.value || !file.value || !canApply.value) return
  const { decisions } = plan.value
  if (withText.value) {
    const tables = decisions.length ? `，并把上年期末数填进 ${decisions.length} 张表的期初列（只填空格）` : ''
    try {
      await ElMessageBox.confirm(
        `将用上年正文替换本年 ${preview.value.text_sections} 节附注的正文（内容模板写过的章节不动）${tables}。确定写入？`,
        '导入上年附注', { confirmButtonText: '确定写入', cancelButtonText: '取消', type: 'warning' })
    } catch {
      return
    }
  }
  applying.value = true
  error.value = ''
  try {
    const result = await applyPriorYear(props.projectId, props.year, file.value, preview.value.file_sha256,
      decisions, withText.value)
    if (result.status !== 'success') {
      error.value = result.message
      stale.value = true
      return
    }
    ElMessage.success(appliedText(result, decisions.length))
    emit('applied', result)
    emit('update:visible', false)
  } catch (e) {
    const err = notifyBatchError(e, '导入上年附注失败', props.projectId)
    if (err.code === 'CANCELED') return
    error.value = err.message
    if (err.message.includes('重新预览')) stale.value = true
  } finally {
    applying.value = false
  }
}

async function onBeforeClose(done: () => void) {
  if (touched.value) {
    try {
      await ElMessageBox.confirm('已调整的勾选与列对应还没写入，确定关闭？', '提示',
        { confirmButtonText: '关闭', cancelButtonText: '继续调整', type: 'warning' })
    } catch {
      return
    }
  }
  done()
}
</script>

<template>
  <el-dialog :model-value="visible" title="📅 导入上年附注" width="80%" top="5vh" append-to-body destroy-on-close
    :close-on-click-modal="false" :before-close="onBeforeClose" @update:model-value="(v: boolean) => emit('update:visible', v)">
    <div class="gt-npy-bar">
      <el-button type="primary" size="small" :loading="loading" @click="fileInput?.click()">📄 选择上年附注 Word</el-button>
      <input ref="fileInput" type="file" accept=".docx" style="display: none" @change="onFileSelected" />
      <span v-if="file" class="gt-npy-muted">{{ file.name }}</span>
      <el-button v-if="file && preview" size="small" :loading="loading" @click="runPreview">🔄 重新预览</el-button>
    </div>
    <el-alert v-if="error" type="error" :closable="false" show-icon :title="error" />
    <el-alert v-if="stale" type="warning" :closable="false" show-icon
      title="预览已过期（上传的文件或本年附注在预览后变了），请点「重新预览」后再写入" />
    <div v-if="!preview" class="gt-npy-empty">
      <p>上传上年附注 Word（.docx）：按标题对上本年章节，把上年表格的期末数填进本年表格的期初列（只填空格，不覆盖已有值）</p>
      <p>认不出的表会逐张列出原因，由你选择上年表或逐列指定后再写入</p>
    </div>
    <template v-else>
      <div class="gt-npy-summary">{{ previewSummary(preview) }}</div>
      <details v-if="preview.unmatched_sections.length" class="gt-npy-muted">
        <summary>上年没有对应的标题（前 {{ preview.unmatched_sections.length }} 个）</summary>
        {{ preview.unmatched_sections.join('、') }}
      </details>
      <el-radio-group v-model="filter" size="small" class="gt-npy-filter">
        <el-radio-button value="all">全部（{{ preview.tables.length }}）</el-radio-button>
        <el-radio-button v-for="s in STATUS_ORDER" :key="s" :value="s">{{ STATUS_META[s].label }}（{{ preview.counts[s] }}）</el-radio-button>
      </el-radio-group>
      <div class="gt-npy-list">
        <div v-if="!shownTables.length" class="gt-npy-empty">没有这一类的表</div>
        <div v-for="item in shownTables" :key="item.key" class="gt-npy-item" :data-key="item.key">
          <div class="gt-npy-head">
            <el-checkbox :model-value="choices[item.key]?.include" @update:model-value="(v: unknown) => setInclude(item, Boolean(v))" />
            <strong>{{ tableLabel(item) }}</strong>
            <el-tag size="small" :type="STATUS_META[item.status].type">{{ STATUS_META[item.status].label }}</el-tag>
            <el-tag v-if="item.method" size="small" effect="plain">{{ METHOD_LABELS[item.method] }}</el-tag>
            <span class="gt-npy-muted">{{ fillText(item) }}</span>
            <div style="flex: 1" />
            <el-button size="small" link type="primary" @click="editingKey = editingKey === item.key ? null : item.key">
              {{ editingKey === item.key ? '收起' : '调整' }}</el-button>
          </div>
          <div v-if="item.reason" class="gt-npy-reason">⚠️ {{ item.reason }}</div>
          <div class="gt-npy-muted gt-npy-map">{{ mappingText(item) }}</div>
          <div v-if="editingKey === item.key" class="gt-npy-edit">
            <div class="gt-npy-col">
              <span class="gt-npy-col-label">上年表</span>
              <el-select :model-value="choices[item.key]?.priorTableId" filterable clearable placeholder="不导入这张表"
                class="gt-npy-table-select" @update:model-value="(v: unknown) => onPickTable(item, v)">
                <el-option-group v-for="g in tableOptions(item)" :key="g.label" :label="g.label">
                  <el-option v-for="t in g.options" :key="t.id" :value="t.id" :label="priorTableLabel(t, item)" />
                </el-option-group>
              </el-select>
            </div>
            <div v-for="col in item.opening_columns" :key="col.col" class="gt-npy-col">
              <span class="gt-npy-col-label" :title="col.label">{{ col.label }} ←</span>
              <el-select :model-value="choices[item.key]?.colMap[String(col.col)]" clearable placeholder="不导入此列"
                class="gt-npy-col-select" :disabled="!choices[item.key]?.priorTableId"
                @update:model-value="(v: unknown) => onPickColumn(item, col.col, v)">
                <el-option v-for="pc in chosenPrior(item)?.columns ?? []" :key="pc.col" :value="pc.col" :label="pc.label" />
              </el-select>
            </div>
          </div>
        </div>
      </div>
    </template>
    <template #footer>
      <div v-if="plan.problems.length" class="gt-npy-problem">⚠️ {{ plan.problems.slice(0, 3).join('；') }}
        <template v-if="plan.problems.length > 3">等 {{ plan.problems.length }} 张表</template>（取消勾选或补全后才能写入）</div>
      <el-checkbox v-if="preview" v-model="importText" :disabled="!preview.text_sections" class="gt-npy-text">
        同时导入上年正文（{{ preview.text_sections }} 节，会替换本年正文；内容模板写过的章节不动）</el-checkbox>
      <el-button @click="onBeforeClose(() => emit('update:visible', false))">取消</el-button>
      <el-button type="success" :loading="applying" :disabled="!canApply" @click="onApply">
        ✅ 确认写入（{{ plan.decisions.length }} 张表）</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.gt-npy-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.gt-npy-muted { color: var(--el-text-color-secondary); font-size: 13px; }
.gt-npy-empty { text-align: center; color: var(--el-text-color-placeholder); padding: 40px 0; }
.gt-npy-summary { margin: 8px 0; font-size: 13px; }
.gt-npy-filter { margin: 8px 0; }
.gt-npy-list { max-height: 60vh; overflow-y: auto; border: 1px solid var(--el-border-color-lighter); border-radius: 6px; padding: 8px 12px; }
.gt-npy-item { padding: 8px 0; border-bottom: 1px dashed var(--el-border-color-lighter); }
.gt-npy-head { display: flex; align-items: center; gap: 8px; }
.gt-npy-reason { font-size: 12px; color: var(--el-color-warning); padding: 2px 0 2px 24px; }
.gt-npy-map { padding-left: 24px; }
.gt-npy-edit { display: flex; flex-direction: column; gap: 6px; padding: 8px 0 0 24px; }
.gt-npy-col { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.gt-npy-col-label { flex: 0 0 200px; text-align: right; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.gt-npy-table-select { width: 560px; }
.gt-npy-col-select { width: 260px; }
.gt-npy-problem { text-align: left; font-size: 12px; color: var(--el-color-danger); margin-bottom: 8px; }
.gt-npy-text { margin-right: 16px; }
</style>
