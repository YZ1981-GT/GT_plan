<!--
  CellTraceDialog.vue — 单元格溯源弹窗（Sprint 2 Task 2.4）

  Spec:    .kiro/specs/disclosure-note-full-revamp/ Sprint 2 Task 2.4
  Design:  D5 CellTrace 溯源链 — 三栏布局
  Reqs:    R3.1 验收 21、22

  三栏布局：
    - 左栏 (300px)：binding 元数据 — source / account_codes / agg / mode
    - 中栏 (flex:1)：公式展开 — formula_resolved + computed_value / computed_at
    - 右栏 (flex:2)：evidence 数据行表格（trial_balance / ledger / aux_balance 三 tab）

  事件：
    - update:modelValue: boolean    弹窗关闭
    - penetrate-to-tb { account_code }   点击 evidence 行 → 跳 TrialBalance

  接口：GET /api/disclosure-notes/{note_id}/cells/{row_idx}/{col_idx}/trace（模板取数绑定，?table_index= 第几张表）
        GET /api/disclosure-notes/{pid}/{year}/{section}/cell-sources（最终来源诊断，spec note-chain-followup-optimizations R2）
  底稿来源的格（投影表，sourceRef 带 subTableKey）没有模板取数绑定，只显示最终来源。
-->
<template>
  <el-dialog
    :model-value="modelValue"
    title="单元格溯源"
    width="1100px"
    :append-to-body="true"
    destroy-on-close
    @update:model-value="onClose"
  >
    <section v-if="canDiagnose" v-loading="sourcesLoading" class="gt-cell-source" data-test="cell-sources">
      <el-alert v-if="sourcesError" :title="sourcesError" type="warning" show-icon :closable="false" />
      <template v-else-if="sources">
        <div class="gt-cell-source-final">
          <span class="gt-cell-source-final__label">最终来源</span>
          <el-tag type="success" size="small">{{ sources.final?.label || '—' }}</el-tag>
          <span class="gt-cell-source-final__detail">{{ sources.final?.detail }}</span>
        </div>
        <div class="gt-cell-source-meta">
          {{ sources.target_label }} · 当前值 {{ formatValue(sources.value) }} · 存在{{ sources.storage?.text }}
        </div>
        <el-alert
          v-for="item in sources.conflicts || []"
          :key="item.kind + item.message"
          :title="item.message"
          type="warning"
          show-icon
          :closable="false"
          class="gt-cell-source-conflict"
        />
        <table class="gt-cell-source-steps">
          <tr v-for="item in sources.steps || []" :key="item.kind + item.detail">
            <td class="gt-cell-source-steps__label">{{ item.label }}</td>
            <td><el-tag :type="stepStatus(item.status).type" size="small">{{ stepStatus(item.status).text }}</el-tag></td>
            <td class="gt-cell-source-steps__detail">{{ item.detail }}</td>
          </tr>
        </table>
      </template>
    </section>
    <div v-if="!isSubTableCell" v-loading="loading" class="gt-cell-trace-body">
      <!-- 错误降级：友好提示 -->
      <el-alert
        v-if="errorState"
        :title="errorTitle"
        :description="errorDesc"
        :type="errorState === 'no_binding' && canDiagnose ? 'info' : 'warning'"
        show-icon
        :closable="false"
        class="gt-cell-trace-error"
      />

      <!-- 三栏主体 -->
      <div v-else-if="trace" class="gt-cell-trace-cols">
        <!-- 左栏：binding 元数据 -->
        <section class="gt-cell-trace-col gt-cell-trace-col--left">
          <h4 class="gt-cell-trace-col-title">📌 binding 元数据</h4>
          <dl class="gt-cell-trace-meta">
            <dt>数据源</dt>
            <dd>{{ trace.binding?.source || '—' }}</dd>
            <dt>字段</dt>
            <dd>{{ trace.binding?.field || '—' }}</dd>
            <dt>科目编码</dt>
            <dd>
              <el-tag
                v-for="code in (trace.binding?.account_codes || [])"
                :key="code"
                size="small"
                style="margin: 2px 4px 2px 0"
              >{{ code }}</el-tag>
              <span v-if="!(trace.binding?.account_codes || []).length">—</span>
            </dd>
            <dt>聚合方式</dt>
            <dd>{{ trace.binding?.agg || 'sum' }}</dd>
            <dt>模式</dt>
            <dd>
              <el-tag
                :type="modeTagType(trace.binding?.mode)"
                size="small"
              >{{ trace.binding?.mode || 'auto' }}</el-tag>
            </dd>
            <dt>语义</dt>
            <dd>{{ trace.semantic || '—' }}</dd>
            <dt>binding_id</dt>
            <dd class="gt-cell-trace-meta-mono">{{ trace.binding_id || '—' }}</dd>
          </dl>
        </section>

        <!-- 中栏：公式展开 + computed_value -->
        <section class="gt-cell-trace-col gt-cell-trace-col--mid">
          <h4 class="gt-cell-trace-col-title">🧮 公式展开</h4>
          <pre class="gt-cell-trace-formula">{{ trace.formula_resolved || '—' }}</pre>
          <dl class="gt-cell-trace-meta">
            <dt>计算结果</dt>
            <dd class="gt-cell-trace-value">{{ formatValue(trace.computed_value) }}</dd>
            <dt>所在行</dt>
            <dd>{{ trace.row_label || '—' }}</dd>
            <dt>计算时间</dt>
            <dd class="gt-cell-trace-meta-mono">{{ trace.computed_at || '—' }}</dd>
          </dl>
        </section>

        <!-- 右栏：evidence 数据行表格（3 tab） -->
        <section class="gt-cell-trace-col gt-cell-trace-col--right">
          <h4 class="gt-cell-trace-col-title">📋 命中数据行</h4>
          <el-tabs v-model="activeTab" type="border-card" size="small">
            <el-tab-pane
              :label="`试算表 (${tbCount})`"
              name="trial_balance"
            >
              <el-table
                v-if="tbRows.length"
                :data="tbRows"
                size="small"
                border
                stripe
                max-height="380"
                @row-click="onEvidenceRowClick"
              >
                <el-table-column prop="account_code" label="科目代码" width="120" />
                <el-table-column prop="audited" label="审定数" align="right" />
                <el-table-column prop="opening" label="期初余额" align="right" />
                <el-table-column label="操作" width="120">
                  <template #default="{ row }">
                    <el-button
                      size="small"
                      link
                      type="primary"
                      @click.stop="onPenetrate(row)"
                    >🔗 跳试算表</el-button>
                  </template>
                </el-table-column>
              </el-table>
              <el-empty v-else description="无命中试算表行" :image-size="60" />
            </el-tab-pane>

            <el-tab-pane
              :label="`序时账 (${ledgerCount})`"
              name="ledger"
            >
              <el-table
                v-if="ledgerRows.length"
                :data="ledgerRows"
                size="small"
                border
                stripe
                max-height="380"
                @row-click="onEvidenceRowClick"
              >
                <el-table-column prop="account_code" label="科目代码" width="120" />
                <el-table-column prop="voucher_date" label="日期" width="110" />
                <el-table-column prop="debit" label="借方" align="right" />
                <el-table-column prop="credit" label="贷方" align="right" />
                <el-table-column prop="summary" label="摘要" min-width="180" />
              </el-table>
              <el-empty v-else description="无命中序时账行" :image-size="60" />
            </el-tab-pane>

            <el-tab-pane
              :label="`辅助余额 (${auxCount})`"
              name="aux_balance"
            >
              <el-table
                v-if="auxRows.length"
                :data="auxRows"
                size="small"
                border
                stripe
                max-height="380"
                @row-click="onEvidenceRowClick"
              >
                <el-table-column prop="account_code" label="科目代码" width="120" />
                <el-table-column prop="aux_type" label="辅助类型" width="100" />
                <el-table-column prop="aux_name" label="辅助名称" min-width="150" />
                <el-table-column prop="closing" label="期末余额" align="right" />
                <el-table-column prop="opening" label="期初余额" align="right" />
              </el-table>
              <el-empty v-else description="无命中辅助余额行" :image-size="60" />
            </el-tab-pane>
          </el-tabs>
        </section>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import * as P from '@/services/apiPaths'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { fetchCellSources, stepStatus, type CellSourceRef, type CellSourcesResult } from './cellSources'

interface BindingMeta {
  source?: string
  field?: string
  account_codes?: string[]
  agg?: string
  mode?: string
  aux_type?: string
  bucket?: string
}

interface TbEvidenceRow {
  account_code?: string
  audited?: number | string
  opening?: number | string
  unadjusted?: number | string
}

interface LedgerEvidenceRow {
  account_code?: string
  voucher_date?: string | null
  debit?: number
  credit?: number
  summary?: string
}

interface AuxEvidenceRow {
  account_code?: string
  aux_type?: string
  aux_name?: string
  closing?: number
  opening?: number
}

interface TraceResponse {
  binding?: BindingMeta
  binding_id?: string
  formula_resolved?: string
  computed_value?: unknown
  computed_at?: string
  semantic?: string
  row_label?: string
  evidence?: {
    trial_balance_rows?: TbEvidenceRow[]
    ledger_sample?: LedgerEvidenceRow[]
    aux_balance_sample?: AuxEvidenceRow[]
  }
  error?: string
  axis?: string
  row_count?: number
  col_count?: number
}

interface Props {
  modelValue: boolean
  noteId: string
  rowIdx: number
  colIdx: number
  /** 第几张表（存储下标；模板取数绑定按它取表） */
  tableIndex?: number
  /** 最终来源诊断用：项目 / 年度 / 章节 + 存储坐标；缺任一项不诊断 */
  projectId?: string
  year?: number | null
  noteSection?: string
  sourceRef?: CellSourceRef | null
}

const props = withDefaults(defineProps<Props>(), {
  tableIndex: 0, projectId: '', year: null, noteSection: '', sourceRef: null,
})
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'penetrate-to-tb', payload: { account_code: string }): void
}>()

const loading = ref(false)
const trace = ref<TraceResponse | null>(null)
const errorState = ref<string | null>(null)
const activeTab = ref<'trial_balance' | 'ledger' | 'aux_balance'>('trial_balance')

const errorTitle = computed(() => {
  switch (errorState.value) {
    case 'no_binding': return '无 binding 配置'
    case 'binding_not_found': return '未找到对应 binding 定义'
    case 'cell_index_out_of_range': return '单元格索引越界'
    case 'note_not_found': return '附注章节不存在'
    case 'fetch_failed': return '加载溯源数据失败'
    default: return '未知错误'
  }
})

const errorDesc = computed(() => {
  switch (errorState.value) {
    case 'no_binding':
      return canDiagnose.value
        ? '这一格没有模板取数绑定；数是谁写的见上方「最终来源」'
        : '当前单元格未配置数据源 binding（手工填写或老数据）— 无法溯源'
    case 'binding_not_found':
      return 'binding_id 在模板中不存在 — 可能模板已变更，建议重新生成附注'
    case 'cell_index_out_of_range':
      return '单元格行/列索引超出实际表格范围'
    case 'note_not_found':
      return '附注章节已删除或访问权限不足'
    case 'fetch_failed':
      return '后端调用失败，请稍后重试或联系管理员'
    default:
      return ''
  }
})

const tbRows = computed<TbEvidenceRow[]>(
  () => trace.value?.evidence?.trial_balance_rows || [],
)
const ledgerRows = computed<LedgerEvidenceRow[]>(
  () => trace.value?.evidence?.ledger_sample || [],
)
const auxRows = computed<AuxEvidenceRow[]>(
  () => trace.value?.evidence?.aux_balance_sample || [],
)
const tbCount = computed(() => tbRows.value.length)
const ledgerCount = computed(() => ledgerRows.value.length)
const auxCount = computed(() => auxRows.value.length)

function modeTagType(mode?: string): 'primary' | 'success' | 'warning' | 'danger' | 'info' {
  if (mode === 'auto') return 'success'
  if (mode === 'manual') return 'warning'
  if (mode === 'locked') return 'danger'
  return 'info'
}

const prefs = useDisplayPrefsStore()

function formatValue(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'number') return prefs.fmt(v)
  return String(v)
}

// ─── 最终来源诊断（spec note-chain-followup-optimizations R2）───────────────
const canDiagnose = computed(() => !!(props.projectId && props.year && props.noteSection && props.sourceRef))
/** 底稿来源（投影表）的格没有模板取数绑定：不请求旧溯源接口，只显示最终来源 */
const isSubTableCell = computed(() => !!props.sourceRef?.subTableKey)
const sources = ref<CellSourcesResult | null>(null)
const sourcesLoading = ref(false)
const sourcesError = ref<string | null>(null)

function sourcesErrorText(err: any): string {
  const status = err?.response?.status
  const detail = err?.response?.data?.detail ?? err?.response?.data?.message
  if (status === 403) return '无权查看本项目附注，最终来源不可用'
  return `最终来源加载失败：${typeof detail === 'string' && detail ? detail : '请稍后重试'}`
}

async function loadSources(): Promise<void> {
  if (!canDiagnose.value || !props.sourceRef) return
  sourcesLoading.value = true
  sourcesError.value = null
  sources.value = null
  try {
    const data = await fetchCellSources(props.projectId, Number(props.year), props.noteSection, props.sourceRef)
    if (data?.error) sourcesError.value = data.message || '定位不到这一格'
    else sources.value = data
  } catch (err) {
    sourcesError.value = sourcesErrorText(err)
  } finally {
    sourcesLoading.value = false
  }
}

async function loadTrace(): Promise<void> {
  if (!props.noteId || isSubTableCell.value) return
  loading.value = true
  errorState.value = null
  trace.value = null
  try {
    const url = P.disclosureNotes.cellTrace(props.noteId, props.rowIdx, props.colIdx)
    const data = props.tableIndex
      ? await api.get(url, { params: { table_index: props.tableIndex } })
      : await api.get(url)
    if (data && data.error) {
      errorState.value = data.error
      // 即使是 no_binding，仍把基础信息保留给中栏展示 computed_value
      trace.value = data
    } else {
      trace.value = data
    }
  } catch (err) {
    errorState.value = 'fetch_failed'
    // 友好提示但不阻断弹窗
    ElMessage.warning('溯源数据加载失败')
  } finally {
    loading.value = false
  }
}

function onClose(v: boolean): void {
  emit('update:modelValue', v)
}

/** 表格行点击：emit penetrate-to-tb 让父组件跳转 */
function onEvidenceRowClick(row: TbEvidenceRow | LedgerEvidenceRow | AuxEvidenceRow): void {
  const code = row.account_code
  if (code) {
    emit('penetrate-to-tb', { account_code: String(code) })
  }
}

function onPenetrate(row: TbEvidenceRow): void {
  if (row.account_code) {
    emit('penetrate-to-tb', { account_code: String(row.account_code) })
  }
}

watch(
  () => [props.modelValue, props.noteId, props.rowIdx, props.colIdx, props.tableIndex, props.sourceRef] as const,
  ([open]) => {
    if (open) {
      loadTrace()
      loadSources()
    }
  },
  { immediate: true },
)
</script>

<style scoped>
.gt-cell-source {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 10px 12px;
  margin-bottom: 12px;
  font-size: 13px;
}
.gt-cell-source-final {
  display: flex;
  align-items: center;
  gap: 8px;
}
.gt-cell-source-final__label {
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.gt-cell-source-final__detail,
.gt-cell-source-meta {
  color: var(--el-text-color-secondary);
  word-break: break-word;
}
.gt-cell-source-meta {
  margin: 6px 0;
}
.gt-cell-source-conflict {
  margin: 6px 0;
}
.gt-cell-source-steps {
  width: 100%;
  border-collapse: collapse;
  margin-top: 6px;
}
.gt-cell-source-steps td {
  border-top: 1px solid var(--el-border-color-lighter);
  padding: 4px 6px;
  vertical-align: top;
}
.gt-cell-source-steps__label {
  width: 150px;
  color: var(--el-text-color-secondary);
}
.gt-cell-source-steps__detail {
  word-break: break-word;
}
.gt-cell-trace-body {
  min-height: 480px;
}
.gt-cell-trace-error {
  margin: 12px 0;
}
.gt-cell-trace-cols {
  display: flex;
  gap: 12px;
  align-items: stretch;
}
.gt-cell-trace-col {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 12px;
  background: var(--el-bg-color);
  min-height: 460px;
}
.gt-cell-trace-col--left {
  width: 300px;
  flex: 0 0 300px;
}
.gt-cell-trace-col--mid {
  flex: 1 1 auto;
  min-width: 0;
}
.gt-cell-trace-col--right {
  flex: 2 1 0;
  min-width: 0;
}
.gt-cell-trace-col-title {
  margin: 0 0 12px 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  border-bottom: 2px solid var(--el-color-primary-light-7);
  padding-bottom: 6px;
}
.gt-cell-trace-meta {
  margin: 0;
  display: grid;
  grid-template-columns: 90px 1fr;
  gap: 6px 10px;
  font-size: 13px;
}
.gt-cell-trace-meta dt {
  color: var(--el-text-color-secondary);
  font-weight: 500;
}
.gt-cell-trace-meta dd {
  margin: 0;
  color: var(--el-text-color-primary);
  word-break: break-word;
}
.gt-cell-trace-meta-mono {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
}
.gt-cell-trace-formula {
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 10px 12px;
  margin: 0 0 14px 0;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--el-color-primary);
}
.gt-cell-trace-value {
  font-size: 18px;
  font-weight: 600;
  color: var(--el-color-success);
}
</style>
