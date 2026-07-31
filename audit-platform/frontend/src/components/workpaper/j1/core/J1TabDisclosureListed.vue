<template>
  <div class="j1-tab-disclosure">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        审计目标：验证应付职工薪酬附注披露（上市公司口径）各项目期初、增减变动、期末的完整性与准确性，确保附注列示与审定表、明细表勾稽一致，满足披露要求。
      </template>
    </el-alert>

    <!-- 工具栏：同步到附注 + 跳转回附注 + 取数追溯 + 复核 -->
    <div class="disc-toolbar">
      <el-button size="small" type="success" :disabled="isReadonly" :loading="syncLoading" @click="syncToDisclosureNotes">
        同步到附注（五、40）
      </el-button>
      <el-button size="small" type="primary" plain :disabled="!projectId" @click="jumpToNote">
        ↩ 跳转回附注（五、40）
      </el-button>
      <!-- 多区块导入导出：一区块一 sheet + 说明域集中「文本说明」sheet（后端 _j1_disclosure_import_export） -->
      <CycleImportExportDropdown
        :wp-id="props.wpId"
        api-prefix="j1"
        sheet="J1-note-listed"
        :disabled="isReadonly"
        @imported="onImported"
      />
      <span class="chip-wrap"><GtIndexChip value="wp:J1-1" :context-project-id="projectId" /></span>
      <span class="chip-wrap"><GtIndexChip value="wp:J1-2" :context-project-id="projectId" /></span>
      <span class="chip-wrap"><GtIndexChip :value="`Note:${J1_NOTE_SECTION.listed}`" :context-project-id="projectId" /></span>
      <GtReviewTrigger section-id="J1-disclosure-listed" />
    </div>

    <!-- 披露内部勾稽（源模板 Excel 公式可判定的关系） -->
    <J1DisclosureConsistencyPanel
      :result="consistency"
      :project-id="projectId"
      :default-expanded="consistency.errorCount > 0"
    />

    <!-- 方法论上下文（源模板 R13~R15 红字提示，嵌在汇总表上方） -->
    <div class="methodology-block">
      <p>【提示：</p>
      <p>1、辞退福利包括（1）预期在其确认的年度报告期间期末后12个月内完全支付的辞退福利；（2）补偿款超过1年支付的辞退计划将于年度报告期间期末后12个月内支付的款项，例如内退计划将于下一年支付的金额。</p>
      <p>2、一年内到期的其他福利：指一年内到期的其他长期福利（不含设定受益计划）；应根据「长期应付职工薪酬」项目分析填列。】</p>
    </div>

    <!-- 第一部分：应付职工薪酬汇总 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="group-header">
          <span class="section-title">应付职工薪酬</span>
          <div class="header-actions">
            <el-button size="small" type="warning" plain :disabled="isReadonly" @click="pullFromAdjudication">
              从审定表/明细表带入
            </el-button>
            <el-button size="small" type="primary" plain :disabled="isReadonly" @click="addSummaryRow()">+ 新增行</el-button>
          </div>
        </div>
      </template>
      <el-alert v-if="adjudicationEndTotal !== 0" :closable="false" show-icon
        :type="Math.abs(summaryVsAdjudicationDiff) < 0.01 ? 'success' : 'warning'" class="recon-alert">
        <template #title>
          附注汇总期末合计 {{ fmtN(summaryEndTotal) }}
          ｜审定表 J1-1 期末审定合计 {{ fmtN(adjudicationEndTotal) }}
          ｜差异 {{ fmtN(summaryVsAdjudicationDiff) }}
          {{ Math.abs(summaryVsAdjudicationDiff) < 0.01 ? '（勾稽一致）' : '（请核查或点「从审定表/明细表带入」）' }}
        </template>
      </el-alert>
      <J1MovementTable
        :rows="summaryData"
        :subtotal="summaryTotal"
        begin-label="上年年末数"
        end-label="期末数"
        label-editable="all"
        removable="all"
        :is-readonly="isReadonly"
        @row-change="recalcRow"
        @remove="removeSummaryRow"
      />
    </el-card>

    <!-- 第二部分：（1）短期薪酬 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="group-header">
          <span class="section-title">（1）短期薪酬</span>
          <div class="header-actions">
            <el-button size="small" type="warning" plain :disabled="isReadonly" @click="pullDetail">
              从 J1-2 明细带入
            </el-button>
            <el-button size="small" type="primary" plain :disabled="isReadonly" @click="addRow('short_term')">+ 新增行</el-button>
            <GtReviewTrigger section-id="J1-disclosure-listed-short-term" />
          </div>
        </div>
      </template>
      <J1MovementTable
        :rows="shortTermData"
        :subtotal="shortTermSubtotal"
        begin-label="上年年末数"
        end-label="期末数"
        :derived-ids="shortTermDerivedIds"
        selectable
        :is-readonly="isReadonly"
        @row-change="recalcRow"
        @remove="(id) => removeRow(id, 'short_term')"
        @current-change="(r) => selectedRow = r"
      />
      <div class="section-note-area">
        <div class="note-header"><label class="note-label">说明</label>
          <el-button size="small" type="primary" plain @click="aiGenerate('short-term-note')" :disabled="isReadonly">🤖 AI辅助</el-button>
        </div>
        <el-input type="textarea" v-model="notes.shortTerm" :disabled="isReadonly"
          @change="persistDebounced()"
          :autosize="{ minRows: 5 }" size="small"
          :placeholder="NOTE_FIELDS[0].placeholder" />
      </div>
    </el-card>

    <!-- 第三部分：（2）设定提存计划 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="group-header">
          <span class="section-title">（2）设定提存计划</span>
          <div class="header-actions">
            <el-button size="small" type="warning" plain :disabled="isReadonly" @click="pullDetail">
              从 J1-2 明细带入
            </el-button>
            <el-button size="small" type="primary" plain :disabled="isReadonly" @click="addRow('post_employment')">+ 新增行</el-button>
            <GtReviewTrigger section-id="J1-disclosure-listed-post-employment" />
          </div>
        </div>
      </template>
      <!-- 方法论上下文（源模板 R51 红字提示） -->
      <div class="methodology-block">
        <p>【提示：其他长期职工福利指符合设定提存计划条件的其他长期职工福利】</p>
      </div>
      <J1MovementTable
        :rows="postEmploymentData"
        :subtotal="postEmploymentSubtotal"
        begin-label="上年年末数"
        end-label="期末数"
        :derived-ids="postEmploymentDerivedIds"
        selectable
        :is-readonly="isReadonly"
        @row-change="recalcRow"
        @remove="(id) => removeRow(id, 'post_employment')"
        @current-change="(r) => selectedRow = r"
      />
      <div class="section-note-area">
        <div class="note-header"><label class="note-label">说明</label>
          <el-button size="small" type="primary" plain @click="aiGenerate('post-employment-note')" :disabled="isReadonly">🤖 AI辅助</el-button>
        </div>
        <el-input type="textarea" v-model="notes.postEmployment" :disabled="isReadonly"
          @change="persistDebounced()"
          :autosize="{ minRows: 5 }" size="small"
          :placeholder="NOTE_FIELDS[1].placeholder" />
      </div>
    </el-card>

    <!-- 第四部分：（3）辞退福利 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="group-header">
          <span class="section-title">（3）辞退福利</span>
          <div class="header-actions">
            <GtReviewTrigger section-id="J1-disclosure-listed-severance" />
          </div>
        </div>
      </template>
      <!-- 方法论上下文（源模板 R54 红字注，逐字口径） -->
      <div class="methodology-block">
        <p>（注：应付职工薪酬、设定受益计划净负债（净资产）、一年后支付的辞退福利及其他长期职工福利本期减少，一般与现金流量表「支付给职工以及为职工支付的现金」一致，除非存在代扣税未交、实物发放等情形。）</p>
      </div>
      <div class="section-note-area">
        <div class="note-header"><label class="note-label">说明</label>
          <el-button size="small" type="primary" plain @click="aiGenerate('severance-note')" :disabled="isReadonly">🤖 AI辅助</el-button>
        </div>
        <el-input type="textarea" v-model="notes.severance" :disabled="isReadonly"
          @change="persistDebounced()"
          :autosize="{ minRows: 5 }" size="small"
          :placeholder="NOTE_FIELDS[2].placeholder" />
      </div>
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 依据 CAS 30《财务报表列报》及 CAS 9，上市公司应按短期薪酬、离职后福利等分项披露变动情况。</p>
        <p>2. "期末数"列为自动计算（期初+增加-减少），灰色底纹。</p>
        <p>3. 附注披露金额应与审定表（J1-1）期末审定数勾稽一致。</p>
        <p>4. 辞退福利、非货币性福利等重大项目须单独说明性质和计算依据。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, onMounted, onBeforeUnmount, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'
import J1MovementTable from './J1MovementTable.vue'
import J1DisclosureConsistencyPanel from './J1DisclosureConsistencyPanel.vue'
import { buildJ1Consistency } from '../../composables/j1DisclosureConsistency'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { eventBus } from '@/utils/eventBus'
import { useAuditContext } from '@/composables/useAuditContext'
import {
  buildJ1SyncPayload,
  j1NoteKeys,
  J1_LISTED_NOTE_FIELDS,
  J1_NOTE_SECTION,
  type J1DisclosureSnapshot,
} from '../../composables/j1NoteSectionMap'
import { buildNoteJumpRoute } from '@/views/composables/noteDisclosureReverseJump'
import {
  useJ1DisclosureSections,
  type J1DisclosureRow as DRow,
  type ChecklistItem,
} from '@/composables/workpaper/j1/useJ1DisclosureSections'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'

const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
  allResponses?: Map<string, ChecklistItem>
  isReadonly?: boolean
  saveImmediate?: (items: ChecklistItem[]) => Promise<void>
}>()

const isReadonly = props.isReadonly ?? false
const autoSync = useDisclosureAutoSync({ isReadonly: () => isReadonly })
const projectId = props.projectId || ''

// 🔴 必须在 setup 顶层取审计上下文：`useAuditContext()` 内部用 `useRoute()`（inject）+
// `onScopeDispose()`，在 async 点击处理器里调用会拿到 undefined 的 route → TypeError
// → 整个 `syncToDisclosureNotes` 在 `http.post` 之前就抛错，同步按钮与自动同步**全程是死的**
// （2026-07-30 浏览器实测发现：零网络请求 + 只弹「同步到附注失败」，vitest 与
// get_diagnostics 都查不出）。
const { year: auditYear } = useAuditContext()

const selectedRow = ref<DRow | null>(null)

// ── 汇总表固定行（合计行由 composable computed 生成，历史实现恒为 0） ─────
const DEFAULT_SUMMARY: DRow[] = [
  { id: 's-1', label: '短期薪酬', category: 'summary', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 's-2', label: '离职后福利-设定提存计划', category: 'summary', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 's-3', label: '辞退福利', category: 'summary', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 's-4', label: '一年内到期的其他福利', category: 'summary', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
]

// ── （1）短期薪酬明细 ──────────────────────────────────────
const DEFAULT_SHORT_TERM: DRow[] = ([
  { id: 'st-1', label: '工资、奖金、津贴和补贴', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'st-2', label: '职工福利费', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'st-3', label: '社会保险费', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'st-4', label: '其中：1. 医疗保险费', category: 'short_term', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'st-5', label: '2. 工伤保险费', category: 'short_term', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'st-6', label: '3. 生育保险费', category: 'short_term', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'st-7', label: '住房公积金', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'st-8', label: '工会经费和职工教育经费', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'st-9', label: '短期带薪缺勤', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'st-10', label: '短期利润分享计划', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'st-11', label: '非货币性福利', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'st-12', label: '其他短期薪酬', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
]) as DRow[]

// ── （2）设定提存计划 ──────────────────────────────────────
const DEFAULT_POST: DRow[] = ([
  { id: 'pe-1', label: '离职后福利', category: 'post_employment', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'pe-2', label: '其中：1. 基本养老保险费', category: 'post_employment', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'pe-3', label: '2. 失业保险费', category: 'post_employment', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'pe-4', label: '3. 企业年金缴费', category: 'post_employment', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'pe-5', label: '4. 其他', category: 'post_employment', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'pe-6', label: '其他长期职工福利（不适用的删除）', category: 'post_employment', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'pe-7', label: '其中：1. xxx', category: 'post_employment', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'pe-8', label: '2. 其他', category: 'post_employment', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
]) as DRow[]

// ── 数据 + 持久化（共享 composable：hydrate / 防抖落库 / 合计 computed） ──
/** 说明文本域定义（单一真源在 `j1NoteSectionMap`，与推给附注的 `_note_texts` 同源） */
const NOTE_FIELDS = J1_LISTED_NOTE_FIELDS
const allResponsesRef = computed(
  () => props.allResponses ?? new Map<string, ChecklistItem>(),
) as unknown as Ref<Map<string, ChecklistItem>>

async function defaultSave(items: ChecklistItem[]): Promise<void> {
  const http = (await import('@/utils/http')).default
  await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, { items })
}

const {
  summaryData,
  shortTermData, shortTermSubtotal,
  postEmploymentData, postEmploymentSubtotal,
  summaryTotal,
  notes, hydrate, persist, persistDebounced, onRowChange,
  adjudicationEndTotal, summaryVsAdjudicationDiff, pullFromSources, pullDetailSections,
  shortTermDerivedIds, postEmploymentDerivedIds, syncParentSums,
} = useJ1DisclosureSections({
  variant: 'listed',
  defaults: { summary: DEFAULT_SUMMARY, shortTerm: DEFAULT_SHORT_TERM, postEmployment: DEFAULT_POST },
  allResponses: allResponsesRef,
  saveImmediate: (items) => (props.saveImmediate ?? defaultSave)(items),
  isReadonly: computed(() => isReadonly) as Ref<boolean>,
  noteKeys: j1NoteKeys('listed'),
})


// ── 通用方法 ──────────────────────────────────────────────
function recalcRow(row: DRow) {
  onRowChange(row)
}

/** 从 J1-1 审定表（期初审定）+ J1-2 明细表（审定增减）带入汇总表 */
async function pullFromAdjudication() {
  if (isReadonly) return
  try {
    await ElMessageBox.confirm(
      '将按分类带入：期初数取审定表 J1-1 期初审定数，本期增加/减少取明细表 J1-2 审定增减数，期末数自动计算。仅覆盖来源侧存在数据的分类行。是否继续？',
      '从审定表/明细表带入',
      { confirmButtonText: '带入', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  const matched = pullFromSources()
  if (matched === 0) {
    ElMessage.warning('未取到审定表/明细表数据，请先编制 J1-1 或 J1-2')
    return
  }
  ElMessage.success(`已带入 ${matched} 个分类行`)
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

/**
 * 明细两表「从 J1-2 明细带入」（审定口径）
 *
 * 源模板里本页每一行都引用 J1-2（`A18='明细表J1-2 '!J13`、`A42='明细表J1-2 '!J38` …），
 * 故按行名带入而非只带汇总。「其中：医疗保险费」聚合 J1-2 的基本 + 补充医疗保险费，
 * 「工会经费和职工教育经费」聚合 J1-2 的两行（均为源模板公式明示）。
 */
async function pullDetail() {
  if (isReadonly) return
  try {
    await ElMessageBox.confirm(
      '将按项目名从 J1-2 明细表带入审定数（未审 + 调整）：期初/本期增加/本期减少，期末自动计算。' +
      '仅覆盖能匹配到的行，未匹配的披露行保持原值；J1-2 中未匹配的顶层项目会追加为新行。是否继续？',
      '从 J1-2 明细带入',
      { confirmButtonText: '带入', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  const { shortTerm, postEmployment } = pullDetailSections()
  const matched = shortTerm.matched + postEmployment.matched
  const appended = shortTerm.appended + postEmployment.appended
  if (matched === 0 && appended === 0) {
    ElMessage.warning('未取到 J1-2 明细表数据，请先编制明细表')
    return
  }
  const skipped = [...shortTerm.skippedSubItems, ...postEmployment.skippedSubItems]
  ElMessage.success(
    `已带入 ${matched} 行` +
    (appended ? `，追加 ${appended} 行` : '') +
    // 未匹配的「其中：」子项金额已含在父行，如实提示而不臆造归属
    (skipped.length ? `；${skipped.length} 个子项未匹配（金额已含在父行，未重复计入）` : ''),
  )
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

/** 同步到附注 */
const syncLoading = ref(false)
async function syncToDisclosureNotes() {
  if (isReadonly) return
  syncLoading.value = true
  try {
    const snapshot: J1DisclosureSnapshot = {
      summary: summaryData.value,
      shortTerm: shortTermData.value,
      postEmployment: postEmploymentData.value,
      notes: notes.value as Record<string, string>,
    }
    const { body } = buildJ1SyncPayload({
      variant: 'listed',
      wpId: props.wpId,
      year: auditYear.value,
      snapshot,
    })
    const http = (await import('@/utils/http')).default
    await http.post(
      `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
      body,
    )
    eventBus.emit('disclosure:note-text-updated', {
      wpCode: 'J1',
      accountCode: '2211',
      projectId: props.projectId,
      sectionIds: [J1_NOTE_SECTION.listed],
    } as any)
    ElMessage.success('已同步到附注（五、40）')
    // 🔴 这里**不能**再 `scheduleAutoSync(syncToDisclosureNotes)` —— 那是调度自己，
    // 800ms 后会再发一次同样的 POST（自触发）。自动同步只应由**数据变更**触发
    // （增删行 / 从明细带入 / AI 写入），2026-07-30 浏览器实测发现该自触发会让
    // 用户在一次成功同步后又收到一条莫名的「同步到附注失败」。
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '同步到附注失败，请重试')
  } finally {
    syncLoading.value = false
  }
}

/** 跳转回附注 */
const router = useRouter()
function jumpToNote() {
  const route = buildNoteJumpRoute(props.projectId, 'J1', 'listed')
  if (route) router.push(route)
}

// ── 多区块导入导出（共享组件 CycleImportExportDropdown → J1 既有三端点） ──────
/** 导入后重载 allResponses（由主入口 provide），否则界面停留在旧值 */
const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)

/**
 * 导入是后端直写 `checklist_responses`，组件本地 ref 不会自动跟随
 * → 重载共享 allResponses 后必须再 `hydrate()`，否则界面停在导入前的值；
 * 随后触发一次自动同步，把导入结果推给附注。
 */
async function onImported(): Promise<void> {
  await reloadWorkpaperData?.()
  hydrate()
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function addSummaryRow() {
  if (isReadonly) return
  summaryData.value.push({ id: `s-${Date.now()}`, label: '', category: 'summary', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 })
  persist()
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function removeSummaryRow(id: string) {
  const idx = summaryData.value.findIndex(r => r.id === id)
  if (idx >= 0) { summaryData.value.splice(idx, 1); persist(); autoSync.scheduleAutoSync(syncToDisclosureNotes) }
}

/** 汇总表期末合计（勾稽 alert / AI 上下文用；合计行由 composable computed 产出） */
const summaryEndTotal = computed(() => summaryTotal.value.endBalance)

/** 披露内部勾稽（纯函数引擎，只取源模板 Excel 公式可判定的关系） */
const consistency = computed(() =>
  buildJ1Consistency({
    variant: 'listed',
    summary: summaryData.value,
    shortTerm: shortTermData.value,
    postEmployment: postEmploymentData.value,
    adjudicationEndTotal: adjudicationEndTotal.value,
  }),
)

function addRow(category: string) {
  if (isReadonly) return
  const arr = category === 'short_term' ? shortTermData : postEmploymentData
  const newRow: DRow = { id: `${category}-${Date.now()}`, label: '', category, indent: 1,
    beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 }
  const sel = selectedRow.value
  if (sel && !sel.isSubtotal && sel.category === category) {
    const idx = arr.value.findIndex(r => r.id === sel.id)
    if (idx >= 0) { arr.value.splice(idx + 1, 0, newRow); afterRowSetChange(); return }
  }
  arr.value.push(newRow)
  afterRowSetChange()
}

function removeRow(id: string, category: string) {
  const arr = category === 'short_term' ? shortTermData : postEmploymentData
  const idx = arr.value.findIndex(r => r.id === id)
  if (idx >= 0) { arr.value.splice(idx, 1); afterRowSetChange() }
}

/** 增删行后：父行随「其中：」子项集合变化重新上卷，再落库 + 自动同步 */
function afterRowSetChange() {
  syncParentSums()
  persist()
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

/** 只读金额统一走平台单一真源（表格内的展示由 J1MovementTable 负责） */
const displayPrefs = useDisplayPrefsStore()
function fmtN(v: number | null | undefined): string {
  return displayPrefs.fmtAmount(v ?? 0)
}

async function aiGenerate(section: string) {
  try {
    // 附注说明的 AI 上下文：带上本表各分区期末数，避免空 context 生成空话
    const { data } = await (await import('@/utils/http')).default.post(
      `/api/workpapers/${props.wpId}/ai/generate-text`,
      {
        section: `j1-disclosure-listed-${section}`,
        context: {
          短期薪酬期末合计: String(shortTermSubtotal.value.endBalance),
          设定提存期末合计: String(postEmploymentSubtotal.value.endBalance),
          汇总表期末合计: String(summaryEndTotal.value),
        },
      },
    )
    const text = data?.data?.content || data?.content || ''
    if (!text) return
    const keyMap: Record<string, string> = {
      'short-term-note': 'shortTerm',
      'post-employment-note': 'postEmployment',
      'severance-note': 'severance',
    }
    const key = keyMap[section]
    if (key) {
      notes.value[key] = text
      persist()
      autoSync.scheduleAutoSync(syncToDisclosureNotes)
    }
  } catch { /* AI不可用时静默 */ }
}

onMounted(() => {
  hydrate()
})

onBeforeUnmount(() => autoSync.cancelPending())
</script>

<style scoped>
.j1-tab-disclosure { padding: 16px; }
.audit-objective { margin-bottom: 14px; }
.disc-toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 12px; }
.chip-wrap { display: inline-flex; align-items: center; }
.section-card { margin-bottom: 16px; }
.section-card :deep(.el-card__header) { padding: 8px 16px; }
.section-card :deep(.el-card__body) { padding: 12px 16px; }
.section-card :deep(.el-table) { font-size: 13px !important; }
.section-card :deep(.el-table th), .section-card :deep(.el-table td) { font-size: 13px !important; padding: 4px 6px !important; }
/* 可编辑金额格由 WpAmountInput（el-input）渲染，右对齐/等宽数字在其内部 scoped 样式里 */
.section-card :deep(.el-input__inner) { font-size: 13px; }
.section-title { font-weight: 600; font-size: 14px; }
.group-header { display: flex; justify-content: space-between; align-items: center; }
.header-actions { display: flex; gap: 8px; align-items: center; }
.recon-alert { margin-bottom: 8px; }
.recon-alert :deep(.el-alert__title) { font-size: 13px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
:deep(.subtotal-row) { background-color: #f5f7fa !important; font-weight: 600; }
:deep(.indent-row) { color: #606266; }
.subtotal-label { font-weight: 600; }
.methodology-block { margin: 12px 0; padding: 10px 14px; border-left: 3px solid #e6a23c; background: #fdf6ec; border-radius: 4px; font-size: 13px; color: #a16717; line-height: 1.6; }
.methodology-block p { margin: 2px 0; }
.section-note { margin-top: 8px; padding: 8px 12px; font-size: 13px; color: #606266; line-height: 1.6; }
.blue-note { color: #409eff; }
.section-note-area { margin-top: 10px; padding: 8px 12px; }
.note-label { font-size: 13px; font-weight: 500; color: #606266; }
.note-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.section-note-area :deep(.el-textarea__inner) { font-size: 13px; }
.audit-note-card { margin-top: 12px; }
.audit-note-card :deep(.el-card__header) { padding: 8px 16px; font-weight: 600; font-size: 13px; }
.audit-note-card :deep(.el-card__body) { padding: 12px 16px; }
.audit-note-card :deep(.el-textarea__inner) { font-size: 13px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
</style>
