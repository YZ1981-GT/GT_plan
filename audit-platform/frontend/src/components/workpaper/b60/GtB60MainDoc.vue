<script setup lang="ts">
/**
 * GtB60MainDoc — B60 主底稿（总体审计策略及具体审计计划）结构化编辑器
 *
 * 按源模板 15 章 / 38 表忠实渲染；取代原 26 章自由文本编辑器。
 * - 普通 section：checklist_responses（B60-M-*）
 * - 第七章 SCOT+ 路由表（T26/T27）：scot-rows 后端 + B50 一键带入 + GtIndexChip 循环/程序索引
 * - 第六章风险汇总：B50 一键带入（财报层次/认定层次）
 * - 叙述章节：🤖AI 辅助
 *
 * Spec: b60-strategy-rework（直接修复）
 */
import { ref, computed, inject, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { useB60MainDoc } from './composables/useB60MainDoc'
import { B60_MAIN_SECTIONS, type MainDocSection } from './constants/mainDocSchema'
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  readonly?: boolean
}>()

// GtB60Bundle 通过 provide('scheduleAutoSnapshot', ...) 与 useWorkpaperReviewProvide 提供
const scheduleAutoSnapshot = inject<() => void>('scheduleAutoSnapshot', () => {})
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const {
  store, scotRows, amountRows, saveStatus, loading,
  markDirty, addScotRow, removeScotRow, scheduleScotSave,
  fetchB50Rows, importFsRisks, importAssertionRisks, importScotFromAccounts, flush,
} = useB60MainDoc({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })

defineExpose({ flushPendingSaves: flush })

const sections = B60_MAIN_SECTIONS

// ── 左侧导航 ──
const activeId = ref('')
const cardRefs = ref<Record<string, HTMLElement>>({})
function setCardRef(id: string, el: any) { if (el) cardRefs.value[id] = el.$el || el }
function scrollTo(id: string) {
  activeId.value = id
  cardRefs.value[id]?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
function navLabel(s: MainDocSection): string {
  // 顶层章节标题去掉子标题部分，保持导航简洁
  return s.title.length > 22 ? s.title.slice(0, 22) + '…' : s.title
}

// ── fields ──
function fieldVal(sid: string, key: string): string { return store[sid]?.[key] ?? '' }
function setField(sid: string, key: string, v: string) {
  if (!store[sid]) store[sid] = {}
  store[sid][key] = v; markDirty(sid)
}
// ── questionnaire ──
function qAnswer(sid: string, key: string): string { return store[sid]?.[key]?.answer ?? '' }
function qNote(sid: string, key: string): string { return store[sid]?.[key]?.note ?? '' }
function setQAnswer(sid: string, key: string, v: string) {
  if (!store[sid]) store[sid] = {}
  if (!store[sid][key]) store[sid][key] = { answer: '', note: '' }
  store[sid][key].answer = v; markDirty(sid)
}
function setQNote(sid: string, key: string, v: string) {
  if (!store[sid]) store[sid] = {}
  if (!store[sid][key]) store[sid][key] = { answer: '', note: '' }
  store[sid][key].note = v; markDirty(sid)
}
// ── table ──
function tableRows(sid: string): Record<string, string>[] { return store[sid]?.rows ?? [] }
function setCell(sid: string, idx: number, key: string, v: string) {
  const rows = tableRows(sid); if (rows[idx]) { rows[idx][key] = v; markDirty(sid) }
}
async function addRow(s: MainDocSection) {
  if (!store[s.id]) store[s.id] = { rows: [] }
  if (!store[s.id].rows) store[s.id].rows = []
  const empty: Record<string, string> = {}
  ;(s.columns || []).forEach((c) => (empty[c.key] = ''))
  if (s.rowLabel && s.columns && s.columns.length > 0) {
    try {
      const { value } = await ElMessageBox.prompt(`请输入${s.rowLabel}名称`, '新增行', { confirmButtonText: '确定', cancelButtonText: '取消' })
      empty[s.columns[0].key] = value || ''
    } catch { return }
  }
  store[s.id].rows.push(empty); markDirty(s.id)
}
function removeRow(sid: string, idx: number) { tableRows(sid).splice(idx, 1); markDirty(sid) }
function yesnoOptions(t?: string): string[] { return t === 'yesnona' ? ['是', '否', '不适用'] : ['是', '否'] }

// ── B50 一键带入 ──
const b50Loading = ref(false)
async function doImportB50(kind: 'fs' | 'assertion') {
  b50Loading.value = true
  try {
    const { fs_risks, assertion_risks } = await fetchB50Rows()
    const n = kind === 'fs' ? importFsRisks(fs_risks) : importAssertionRisks(assertion_risks)
    if (n > 0) { ElMessage.success(`已从 B50 带入 ${n} 条风险`); scheduleAutoSnapshot() }
    else ElMessage.info('B50 无新增风险可带入（或尚未编制 B50）')
  } finally { b50Loading.value = false }
}
async function doImportScot() {
  b50Loading.value = true
  try {
    const { accounts } = await fetchB50Rows()
    const n = importScotFromAccounts(accounts)
    if (n > 0) { ElMessage.success(`已从 B50 带入 ${n} 个科目到 SCOT+`); scheduleAutoSnapshot() }
    else ElMessage.info('B50 无新增科目可带入（或尚未编制 B50）')
  } finally { b50Loading.value = false }
}

// ── SCOT+ 行编辑 ──
const APPROACH_OPTIONS = ['综合性', '实质性', '综合性与实质性结合']
const RELY_OPTIONS = ['是', '否', '待测']
function updateScotCell(rowType: 'scot' | 'amount', idx: number, key: string, v: string) {
  const arr = rowType === 'scot' ? scotRows.value : amountRows.value
  if (arr[idx]) { (arr[idx] as any)[key] = v; scheduleScotSave() }
}

// ── AI 辅助 ──
const aiLoading = ref<Record<string, boolean>>({})
const aiVisible = ref(false)
const aiContent = ref('')
let aiTarget: { sid: string; key: string } | null = null
async function doAi(s: MainDocSection, f: { key: string; label: string }) {
  const k = `${s.id}.${f.key}`
  aiLoading.value[k] = true
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: `${s.id}-${f.key}`,
      prompt: `${s.title} - ${f.label}`,
      context: { chapter: String(s.title), field: String(f.label) },
    })
    const content = res?.data?.content || res?.data?.data?.content || ''
    if (!content) { ElMessage.warning('AI 生成失败，请稍后重试'); return }
    aiContent.value = content
    aiTarget = { sid: s.id, key: f.key }
    aiVisible.value = true
  } catch { ElMessage.warning('AI 生成失败，请稍后重试') }
  finally { aiLoading.value[k] = false }
}
function applyAi() {
  if (aiTarget) {
    const cur = fieldVal(aiTarget.sid, aiTarget.key)
    setField(aiTarget.sid, aiTarget.key, cur ? `${cur}\n\n${aiContent.value}` : aiContent.value)
  }
  aiVisible.value = false; aiContent.value = ''; aiTarget = null
}

function handleReview(sid: string) { openReviewDialog(sid) }
</script>

<template>
  <div class="b60-main-doc" v-loading="loading">
    <div class="save-bar">
      <span class="save-status" :class="`save-status--${saveStatus}`">
        {{ saveStatus === 'saved' ? '✓ 已保存' : saveStatus === 'saving' ? '保存中…' : '● 未保存' }}
      </span>
    </div>

    <div class="doc-layout">
      <!-- 左侧导航 -->
      <div class="nav-panel">
        <div class="nav-title">章节导航（15 章）</div>
        <div class="nav-list">
          <div
            v-for="s in sections"
            :key="s.id"
            class="nav-item"
            :class="{ 'nav-item--active': activeId === s.id }"
            @click="scrollTo(s.id)"
          >{{ navLabel(s) }}</div>
        </div>
      </div>

      <!-- 右侧内容 -->
      <div class="content-panel">
        <el-card
          v-for="s in sections"
          :key="s.id"
          :ref="(el: any) => setCardRef(s.id, el)"
          shadow="never"
          class="section-card"
        >
          <template #header>
            <div class="section-head">
              <span class="section-title">{{ s.title }}</span>
              <div class="section-actions">
                <GtIndexChip v-for="c in (s.refCodes || [])" :key="c" :value="'wp:' + c" />
                <el-button
                  v-if="s.b50Import"
                  size="small" type="primary" plain :loading="b50Loading"
                  @click="doImportB50(s.b50Import)"
                >📥 从 B50 带入</el-button>
                <el-button size="small" @click="handleReview(s.id)">💬</el-button>
              </div>
            </div>
          </template>

          <details v-if="s.hint" class="amber-hint" open>
            <summary>编制提示</summary>
            <div class="hint-content">{{ s.hint }}</div>
          </details>

          <!-- fields -->
          <div v-if="s.kind === 'fields'" class="fields-grid">
            <div v-for="f in s.fields" :key="f.key" class="field-row">
              <label class="field-label">
                {{ f.label }}
                <el-button
                  v-if="s.ai && (f.type === 'textarea')"
                  size="small" type="primary" plain class="ai-btn"
                  :loading="aiLoading[`${s.id}.${f.key}`]"
                  @click="doAi(s, f)"
                >🤖 AI</el-button>
              </label>
              <div class="field-control">
                <el-input
                  v-if="f.type === 'textarea'" type="textarea" :autosize="{ minRows: 3 }"
                  :model-value="fieldVal(s.id, f.key)" :disabled="readonly"
                  @update:model-value="(v: string) => setField(s.id, f.key, v)"
                />
                <el-date-picker
                  v-else-if="f.type === 'date'" :model-value="fieldVal(s.id, f.key)"
                  type="date" value-format="YYYY-MM-DD" :disabled="readonly"
                  @update:model-value="(v: string) => setField(s.id, f.key, v)"
                />
                <el-select
                  v-else-if="f.type === 'select'" :model-value="fieldVal(s.id, f.key)"
                  :disabled="readonly" clearable
                  @update:model-value="(v: string) => setField(s.id, f.key, v)"
                >
                  <el-option v-for="o in f.options" :key="o" :label="o" :value="o" />
                </el-select>
                <el-radio-group
                  v-else-if="f.type === 'yesno' || f.type === 'yesnona'"
                  :model-value="fieldVal(s.id, f.key)" :disabled="readonly"
                  @update:model-value="(v: string) => setField(s.id, f.key, v as string)"
                >
                  <el-radio v-for="o in yesnoOptions(f.type)" :key="o" :value="o">{{ o }}</el-radio>
                </el-radio-group>
                <el-input
                  v-else :model-value="fieldVal(s.id, f.key)" :disabled="readonly"
                  @update:model-value="(v: string) => setField(s.id, f.key, v)"
                />
                <span v-if="f.hint" class="field-hint">{{ f.hint }}</span>
              </div>
            </div>
          </div>

          <!-- questionnaire -->
          <div v-else-if="s.kind === 'questionnaire'" class="questionnaire">
            <template v-for="(g, gi) in s.groups" :key="gi">
              <div v-if="g.label" class="q-group">{{ g.label }}</div>
              <div v-for="q in g.items" :key="q.key" class="q-item" :class="{ 'q-item--signal': qAnswer(s.id, q.key) === '是' }">
                <div class="q-label">{{ q.label }}</div>
                <div class="q-controls">
                  <el-radio-group :model-value="qAnswer(s.id, q.key)" :disabled="readonly"
                    @update:model-value="(v: string) => setQAnswer(s.id, q.key, v as string)">
                    <el-radio v-for="o in yesnoOptions(q.type)" :key="o" :value="o">{{ o }}</el-radio>
                  </el-radio-group>
                  <el-input :model-value="qNote(s.id, q.key)" :disabled="readonly" size="small"
                    placeholder="说明" class="q-note"
                    @update:model-value="(v: string) => setQNote(s.id, q.key, v)" />
                </div>
              </div>
            </template>
          </div>

          <!-- SCOT+ 路由表（T26） -->
          <div v-else-if="s.scot === 'scot'" class="table-wrap">
            <el-table :data="scotRows" size="small" border>
              <el-table-column type="index" label="#" width="42" />
              <el-table-column label="底稿索引号" min-width="120">
                <template #default="{ row, $index }">
                  <el-input :model-value="row.scot_id" :disabled="readonly" size="small"
                    @update:model-value="(v: string) => updateScotCell('scot', $index, 'scot_id', v)" />
                </template>
              </el-table-column>
              <el-table-column label="交易类别/账户余额/披露名称" min-width="180">
                <template #default="{ row, $index }">
                  <el-input :model-value="row.name" :disabled="readonly" size="small"
                    @update:model-value="(v: string) => updateScotCell('scot', $index, 'name', v)" />
                </template>
              </el-table-column>
              <el-table-column label="具体交易、账户和披露" min-width="180">
                <template #default="{ row, $index }">
                  <el-input :model-value="row.detail" :disabled="readonly" size="small" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }"
                    @update:model-value="(v: string) => updateScotCell('scot', $index, 'detail', v)" />
                </template>
              </el-table-column>
              <el-table-column label="拟采取的方案" min-width="150">
                <template #default="{ row, $index }">
                  <el-select :model-value="row.approach" :disabled="readonly" size="small" clearable
                    @update:model-value="(v: string) => updateScotCell('scot', $index, 'approach', v)">
                    <el-option v-for="o in APPROACH_OPTIONS" :key="o" :label="o" :value="o" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column label="循环代码" width="100">
                <template #default="{ row, $index }">
                  <el-input :model-value="row.cycle_code" :disabled="readonly" size="small"
                    @update:model-value="(v: string) => updateScotCell('scot', $index, 'cycle_code', v)" />
                </template>
              </el-table-column>
              <el-table-column label="拟用程序底稿索引" min-width="130">
                <template #default="{ row, $index }">
                  <div class="cell-chip">
                    <el-input :model-value="row.procedure_wp_index" :disabled="readonly" size="small"
                      @update:model-value="(v: string) => updateScotCell('scot', $index, 'procedure_wp_index', v)" />
                    <GtIndexChip v-if="row.procedure_wp_index" :value="'wp:' + row.procedure_wp_index" />
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="是否依赖控制" width="110">
                <template #default="{ row, $index }">
                  <el-select :model-value="row.rely_on_controls" :disabled="readonly" size="small" clearable
                    @update:model-value="(v: string) => updateScotCell('scot', $index, 'rely_on_controls', v)">
                    <el-option v-for="o in RELY_OPTIONS" :key="o" :label="o" :value="o" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column label="风险ID / B50行号" min-width="120">
                <template #default="{ row, $index }">
                  <el-input :model-value="row.risk_id" :disabled="readonly" size="small"
                    @update:model-value="(v: string) => updateScotCell('scot', $index, 'risk_id', v)" />
                </template>
              </el-table-column>
              <el-table-column v-if="!readonly" label="操作" width="64" align="center">
                <template #default="{ $index }">
                  <el-button link type="danger" size="small" @click="removeScotRow('scot', $index)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
            <div class="scot-actions" v-if="!readonly">
              <el-button size="small" @click="addScotRow('scot')">+ 新增 SCOT+ 行</el-button>
              <el-button size="small" type="primary" plain :loading="b50Loading" @click="doImportScot">📥 从 B50 带入科目</el-button>
            </div>
          </div>

          <!-- 仅金额重大项目（T27） -->
          <div v-else-if="s.scot === 'amount'" class="table-wrap">
            <el-table :data="amountRows" size="small" border>
              <el-table-column type="index" label="#" width="42" />
              <el-table-column label="底稿索引号" min-width="110">
                <template #default="{ row, $index }">
                  <el-input :model-value="row.scot_id" :disabled="readonly" size="small"
                    @update:model-value="(v: string) => updateScotCell('amount', $index, 'scot_id', v)" />
                </template>
              </el-table-column>
              <el-table-column label="仅金额重大的交易、账户余额和披露" min-width="200">
                <template #default="{ row, $index }">
                  <el-input :model-value="row.name" :disabled="readonly" size="small"
                    @update:model-value="(v: string) => updateScotCell('amount', $index, 'name', v)" />
                </template>
              </el-table-column>
              <el-table-column label="拟采取的方案" min-width="150">
                <template #default="{ row, $index }">
                  <el-select :model-value="row.approach" :disabled="readonly" size="small" clearable
                    @update:model-value="(v: string) => updateScotCell('amount', $index, 'approach', v)">
                    <el-option v-for="o in APPROACH_OPTIONS" :key="o" :label="o" :value="o" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column label="循环代码" width="100">
                <template #default="{ row, $index }">
                  <el-input :model-value="row.cycle_code" :disabled="readonly" size="small"
                    @update:model-value="(v: string) => updateScotCell('amount', $index, 'cycle_code', v)" />
                </template>
              </el-table-column>
              <el-table-column label="拟用程序底稿索引" min-width="130">
                <template #default="{ row, $index }">
                  <div class="cell-chip">
                    <el-input :model-value="row.procedure_wp_index" :disabled="readonly" size="small"
                      @update:model-value="(v: string) => updateScotCell('amount', $index, 'procedure_wp_index', v)" />
                    <GtIndexChip v-if="row.procedure_wp_index" :value="'wp:' + row.procedure_wp_index" />
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="整合审计是否做业务层控制测试" min-width="140">
                <template #default="{ row, $index }">
                  <el-select :model-value="row.control_test" :disabled="readonly" size="small" clearable
                    @update:model-value="(v: string) => updateScotCell('amount', $index, 'control_test', v)">
                    <el-option v-for="o in ['是', '否', '不适用']" :key="o" :label="o" :value="o" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column v-if="!readonly" label="操作" width="64" align="center">
                <template #default="{ $index }">
                  <el-button link type="danger" size="small" @click="removeScotRow('amount', $index)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
            <div class="scot-actions" v-if="!readonly">
              <el-button size="small" @click="addScotRow('amount')">+ 新增行</el-button>
            </div>
          </div>

          <!-- 普通 table -->
          <div v-else-if="s.kind === 'table'" class="table-wrap">
            <el-table :data="tableRows(s.id)" size="small" border>
              <el-table-column type="index" label="#" width="42" />
              <el-table-column v-for="col in s.columns" :key="col.key" :label="col.label" :min-width="col.minWidth || 120">
                <template #default="{ row, $index }">
                  <el-select v-if="col.type === 'select'" :model-value="row[col.key]" :disabled="readonly" size="small" clearable
                    @update:model-value="(v: string) => setCell(s.id, $index, col.key, v)">
                    <el-option v-for="o in col.options" :key="o" :label="o" :value="o" />
                  </el-select>
                  <el-radio-group v-else-if="col.type === 'yesno' || col.type === 'yesnona'" :model-value="row[col.key]" :disabled="readonly" size="small"
                    @update:model-value="(v: string) => setCell(s.id, $index, col.key, v as string)">
                    <el-radio v-for="o in yesnoOptions(col.type)" :key="o" :value="o">{{ o }}</el-radio>
                  </el-radio-group>
                  <el-date-picker v-else-if="col.type === 'date'" :model-value="row[col.key]" type="date" value-format="YYYY-MM-DD" :disabled="readonly" size="small"
                    @update:model-value="(v: string) => setCell(s.id, $index, col.key, v)" />
                  <el-input v-else-if="col.type === 'textarea'" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }" :model-value="row[col.key]" :disabled="readonly" size="small"
                    @update:model-value="(v: string) => setCell(s.id, $index, col.key, v)" />
                  <el-input v-else :model-value="row[col.key]" :disabled="readonly" size="small"
                    @update:model-value="(v: string) => setCell(s.id, $index, col.key, v)" />
                </template>
              </el-table-column>
              <el-table-column v-if="s.addable && !readonly" label="操作" width="64" align="center">
                <template #default="{ $index }">
                  <el-button link type="danger" size="small" @click="removeRow(s.id, $index)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
            <el-button v-if="s.addable && !readonly" size="small" class="add-row-btn" @click="addRow(s)">
              + 新增{{ s.rowLabel || '行' }}
            </el-button>
          </div>
        </el-card>
      </div>
    </div>

    <!-- AI 预览 -->
    <el-dialog v-model="aiVisible" title="AI 生成内容预览" width="600px">
      <div class="ai-preview">{{ aiContent }}</div>
      <template #footer>
        <el-button @click="aiVisible = false">取消</el-button>
        <el-button type="primary" @click="applyAi">采纳</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.b60-main-doc { font-size: 13px; display: flex; flex-direction: column; height: 100%; }
.save-bar { padding: 4px 8px; border-bottom: 1px solid #ebeef5; }
.save-status { font-size: 12px; }
.save-status--saved { color: #67c23a; }
.save-status--saving { color: #909399; }
.save-status--unsaved { color: #e6a23c; }

.doc-layout { display: flex; flex: 1; overflow: hidden; }
.nav-panel { width: 240px; min-width: 240px; border-right: 1px solid #ebeef5; overflow-y: auto; background: #fafafa; max-height: 70vh; }
.nav-title { padding: 10px 12px; font-weight: 600; font-size: 13px; border-bottom: 1px solid #ebeef5; }
.nav-list { padding: 6px 0; }
.nav-item { padding: 7px 12px; cursor: pointer; font-size: 12px; color: #606266; line-height: 1.4; border-left: 2px solid transparent; }
.nav-item:hover { background: #ecf5ff; }
.nav-item--active { background: #e6f1fc; border-left-color: var(--el-color-primary); }

.content-panel { flex: 1; overflow-y: auto; padding: 14px; max-height: 70vh; }
.section-card { margin-bottom: 14px; border-left: 3px solid var(--el-color-primary); }
.section-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.section-title { font-size: 13px; font-weight: 600; color: #303133; }
.section-actions { display: flex; align-items: center; gap: 6px; flex-shrink: 0; flex-wrap: wrap; }

.amber-hint { border-left: 3px solid #f59e0b; background: #fffbeb; padding: 8px 12px; margin-bottom: 12px; border-radius: 4px; }
.amber-hint summary { cursor: pointer; font-weight: 500; color: #92400e; font-size: 12px; }
.hint-content { margin-top: 6px; color: #78350f; font-size: 12px; line-height: 1.6; }

.fields-grid { display: flex; flex-direction: column; gap: 12px; }
.field-row { display: flex; align-items: flex-start; gap: 12px; }
.field-label { width: 200px; min-width: 200px; color: #606266; padding-top: 6px; display: flex; align-items: center; gap: 6px; }
.ai-btn { padding: 2px 6px; }
.field-control { flex: 1; display: flex; flex-direction: column; gap: 4px; }
.field-hint { color: #909399; font-size: 12px; }

.questionnaire { display: flex; flex-direction: column; gap: 8px; }
.q-group { font-weight: 600; color: #409eff; margin: 8px 0 4px; }
.q-item { padding: 8px 10px; border: 1px solid #ebeef5; border-radius: 4px; }
.q-item--signal { background: #fef0f0; border-color: #fbc4c4; }
.q-label { color: #303133; line-height: 1.5; margin-bottom: 6px; }
.q-controls { display: flex; align-items: center; gap: 12px; }
.q-note { flex: 1; max-width: 420px; }

.table-wrap { overflow-x: auto; }
.cell-chip { display: flex; align-items: center; gap: 4px; }
.add-row-btn, .scot-actions { margin-top: 8px; }
.scot-actions { display: flex; gap: 8px; }

.ai-preview { white-space: pre-wrap; line-height: 1.7; font-size: 13px; max-height: 400px; overflow-y: auto; }
</style>
