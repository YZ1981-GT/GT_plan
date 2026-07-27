<template>
  <div class="j1-tab-disclosure">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        审计目标：验证应付职工薪酬附注披露（上市公司口径）各项目期初、增减变动、期末的完整性与准确性，确保附注列示与审定表、明细表勾稽一致，满足披露要求。
      </template>
    </el-alert>

    <!-- 工具栏：同步到附注 + 跳转回附注 -->
    <div class="disc-toolbar">
      <el-button size="small" type="success" :disabled="isReadonly" :loading="syncLoading" @click="syncToDisclosureNotes">
        同步到附注（五、40）
      </el-button>
      <el-button size="small" type="primary" plain :disabled="!projectId" @click="jumpToNote">
        ↩ 跳转回附注（五、40）
      </el-button>
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
          附注汇总期末合计 {{ fmtN(summaryRows.at(-1)?.endBalance ?? 0) }}
          ｜审定表 J1-1 期末审定合计 {{ fmtN(adjudicationEndTotal) }}
          ｜差异 {{ fmtN(summaryVsAdjudicationDiff) }}
          {{ Math.abs(summaryVsAdjudicationDiff) < 0.01 ? '（勾稽一致）' : '（请核查或点「从审定表/明细表带入」）' }}
        </template>
      </el-alert>
      <el-table :data="summaryRows" border size="small"
        :row-class-name="({ row }) => row.isSubtotal ? 'subtotal-row' : ''">
        <el-table-column label="项 目" min-width="240">
          <template #default="{ row }">
            <template v-if="row.isSubtotal"><span class="subtotal-label">{{ row.label }}</span></template>
            <el-input v-else v-model="row.label" size="small" :disabled="isReadonly" placeholder="输入项目名称" />
          </template>
        </el-table-column>
        <el-table-column label="上年年末数" align="right">
          <template #default="{ row }">
            <template v-if="row.isSubtotal">{{ fmtN(row.beginBalance) }}</template>
            <el-input-number v-else v-model="row.beginBalance" :controls="false" :precision="2"
              size="small" :disabled="isReadonly" @change="recalcRow(row)" />
          </template>
        </el-table-column>
        <el-table-column label="本期增加" align="right">
          <template #default="{ row }">
            <template v-if="row.isSubtotal">{{ fmtN(row.increase) }}</template>
            <el-input-number v-else v-model="row.increase" :controls="false" :precision="2"
              size="small" :disabled="isReadonly" @change="recalcRow(row)" />
          </template>
        </el-table-column>
        <el-table-column label="本期减少" align="right">
          <template #default="{ row }">
            <template v-if="row.isSubtotal">{{ fmtN(row.decrease) }}</template>
            <el-input-number v-else v-model="row.decrease" :controls="false" :precision="2"
              size="small" :disabled="isReadonly" @change="recalcRow(row)" />
          </template>
        </el-table-column>
        <el-table-column label="期末数" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell" title="期末=期初+增加-减少">{{ fmtN(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="36" align="center">
          <template #default="{ row }">
            <el-button v-if="!row.isSubtotal" type="danger" link size="small" :disabled="isReadonly" @click="removeSummaryRow(row.id)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 编制提示（折叠） -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1、辞退福利包括（1）预期在其确认的年度报告期间期末后12个月内完全支付的辞退福利；（2）补偿款超过1年支付的辞退计划将于年度报告期间期末后12个月内支付的款项，例如内退计划将于下一年支付的金额。</p>
        <p>2、一年内到期的其他福利，指一年内到期的其他长期福利（不含设定受益计划）；应根据"长期应付职工薪酬"项目分析填列。</p>
      </div>
    </details>

    <!-- 第二部分：（1）短期薪酬 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="group-header">
          <span class="section-title">（1）短期薪酬</span>
          <el-button size="small" type="primary" plain :disabled="isReadonly" @click="addRow('short_term')">+ 新增行</el-button>
        </div>
      </template>
      <el-table :data="[...shortTermRows, shortTermSubtotal]" border size="small"
        highlight-current-row @current-change="(r) => selectedRow = r"
        :row-class-name="({ row }) => row.isSubtotal ? 'subtotal-row' : (row.indent ? 'indent-row' : '')">
        <el-table-column label="项 目" min-width="240">
          <template #default="{ row }">
            <template v-if="row.isSubtotal"><span class="subtotal-label">{{ row.label }}</span></template>
            <template v-else-if="row.indent">
              <el-input v-model="row.label" size="small" :disabled="isReadonly" style="padding-left:16px" placeholder="输入子项名称" />
            </template>
            <template v-else><span>{{ row.label }}</span></template>
          </template>
        </el-table-column>
        <el-table-column label="上年年末数" align="right">
          <template #default="{ row }">
            <template v-if="row.isSubtotal">{{ fmtN(row.beginBalance) }}</template>
            <el-input-number v-else v-model="row.beginBalance" :controls="false" :precision="2" size="small" :disabled="isReadonly" @change="recalcRow(row)" />
          </template>
        </el-table-column>
        <el-table-column label="本期增加" align="right">
          <template #default="{ row }">
            <template v-if="row.isSubtotal">{{ fmtN(row.increase) }}</template>
            <el-input-number v-else v-model="row.increase" :controls="false" :precision="2" size="small" :disabled="isReadonly" @change="recalcRow(row)" />
          </template>
        </el-table-column>
        <el-table-column label="本期减少" align="right">
          <template #default="{ row }">
            <template v-if="row.isSubtotal">{{ fmtN(row.decrease) }}</template>
            <el-input-number v-else v-model="row.decrease" :controls="false" :precision="2" size="small" :disabled="isReadonly" @change="recalcRow(row)" />
          </template>
        </el-table-column>
        <el-table-column label="期末数" align="right" class-name="auto-calc-col">
          <template #default="{ row }"><span class="formula-cell" title="期末=期初+增加-减少">{{ fmtN(row.endBalance) }}</span></template>
        </el-table-column>
        <el-table-column label="" width="36" align="center">
          <template #default="{ row }">
            <el-button v-if="!row.isSubtotal && row.indent" type="danger" link size="small" :disabled="isReadonly" @click="removeRow(row.id, 'short_term')">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="section-note-area">
        <div class="note-header"><label class="note-label">说明</label>
          <el-button size="small" type="primary" plain @click="aiGenerate('short-term-note')" :disabled="isReadonly">🤖 AI辅助</el-button>
        </div>
        <el-input type="textarea" v-model="notes.shortTerm" :disabled="isReadonly"
          @change="persistDebounced()"
          :autosize="{ minRows: 2, maxRows: 5 }" size="small"
          placeholder="1、（企业本期为职工提供的各项非货币性福利形式、其计算依据。）&#10;2、（企业依据短期利润分享计划提供的职工薪酬计算依据。）" />
      </div>
    </el-card>

    <!-- 第三部分：（2）设定提存计划 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="group-header">
          <span class="section-title">（2）设定提存计划</span>
          <el-button size="small" type="primary" plain :disabled="isReadonly" @click="addRow('post_employment')">+ 新增行</el-button>
        </div>
      </template>
      <el-table :data="[...postEmploymentRows, postEmploymentSubtotal]" border size="small"
        highlight-current-row @current-change="(r) => selectedRow = r"
        :row-class-name="({ row }) => row.isSubtotal ? 'subtotal-row' : (row.indent ? 'indent-row' : '')">
        <el-table-column label="项 目" min-width="240">
          <template #default="{ row }">
            <template v-if="row.isSubtotal"><span class="subtotal-label">{{ row.label }}</span></template>
            <template v-else-if="row.indent">
              <el-input v-model="row.label" size="small" :disabled="isReadonly" style="padding-left:16px" placeholder="输入子项名称" />
            </template>
            <template v-else><span>{{ row.label }}</span></template>
          </template>
        </el-table-column>
        <el-table-column label="上年年末数" align="right">
          <template #default="{ row }">
            <template v-if="row.isSubtotal">{{ fmtN(row.beginBalance) }}</template>
            <el-input-number v-else v-model="row.beginBalance" :controls="false" :precision="2" size="small" :disabled="isReadonly" @change="recalcRow(row)" />
          </template>
        </el-table-column>
        <el-table-column label="本期增加" align="right">
          <template #default="{ row }">
            <template v-if="row.isSubtotal">{{ fmtN(row.increase) }}</template>
            <el-input-number v-else v-model="row.increase" :controls="false" :precision="2" size="small" :disabled="isReadonly" @change="recalcRow(row)" />
          </template>
        </el-table-column>
        <el-table-column label="本期减少" align="right">
          <template #default="{ row }">
            <template v-if="row.isSubtotal">{{ fmtN(row.decrease) }}</template>
            <el-input-number v-else v-model="row.decrease" :controls="false" :precision="2" size="small" :disabled="isReadonly" @change="recalcRow(row)" />
          </template>
        </el-table-column>
        <el-table-column label="期末数" align="right" class-name="auto-calc-col">
          <template #default="{ row }"><span class="formula-cell" title="期末=期初+增加-减少">{{ fmtN(row.endBalance) }}</span></template>
        </el-table-column>
        <el-table-column label="" width="36" align="center">
          <template #default="{ row }">
            <el-button v-if="!row.isSubtotal && row.indent" type="danger" link size="small" :disabled="isReadonly" @click="removeRow(row.id, 'post_employment')">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="section-note-area">
        <div class="note-header"><label class="note-label">说明</label>
          <el-button size="small" type="primary" plain @click="aiGenerate('post-employment-note')" :disabled="isReadonly">🤖 AI辅助</el-button>
        </div>
        <el-input type="textarea" v-model="notes.postEmployment" :disabled="isReadonly"
          @change="persistDebounced()"
          :autosize="{ minRows: 2, maxRows: 5 }" size="small"
          placeholder="（设定提存计划的性质、计算缴费金额的公式或依据）&#10;【提示：其他长期职工福利指符合设定提存计划条件的其他长期职工福利】" />
      </div>
    </el-card>

    <!-- 第四部分：（3）辞退福利 -->
    <el-card shadow="never" class="section-card">
      <template #header><span class="section-title">（3）辞退福利</span></template>
      <div class="section-note-area">
        <div class="note-header"><label class="note-label">说明</label>
          <el-button size="small" type="primary" plain @click="aiGenerate('severance-note')" :disabled="isReadonly">🤖 AI辅助</el-button>
        </div>
        <el-input type="textarea" v-model="notes.severance" :disabled="isReadonly"
          @change="persistDebounced()"
          :autosize="{ minRows: 2, maxRows: 5 }" size="small"
          placeholder="辞退福利的性质、内容及计算依据。&#10;（注：应付职工薪酬、设定受益计划净负债（净资产）、一年后支付的辞退福利及其他长期职工福利本期减少一般不得超过期初数加本期增加数之和）" />
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
import { ref, computed, onMounted, onBeforeUnmount, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import GtIndexChip from '../../GtIndexChip.vue'
import { eventBus } from '@/utils/eventBus'
import { useAuditContext } from '@/composables/useAuditContext'
import {
  buildJ1SyncPayload,
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
const NOTE_KEYS = ['shortTerm', 'postEmployment', 'severance'] as const
const allResponsesRef = computed(
  () => props.allResponses ?? new Map<string, ChecklistItem>(),
) as unknown as Ref<Map<string, ChecklistItem>>

async function defaultSave(items: ChecklistItem[]): Promise<void> {
  const http = (await import('@/utils/http')).default
  await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, { items })
}

const {
  summaryData, summaryRows,
  shortTermData, shortTermSubtotal,
  postEmploymentData, postEmploymentSubtotal,
  notes, hydrate, persist, persistDebounced, onRowChange,
  adjudicationEndTotal, summaryVsAdjudicationDiff, pullFromSources,
} = useJ1DisclosureSections({
  variant: 'listed',
  defaults: { summary: DEFAULT_SUMMARY, shortTerm: DEFAULT_SHORT_TERM, postEmployment: DEFAULT_POST },
  allResponses: allResponsesRef,
  saveImmediate: (items) => (props.saveImmediate ?? defaultSave)(items),
  isReadonly: computed(() => isReadonly) as Ref<boolean>,
  noteKeys: [...NOTE_KEYS],
})

const shortTermRows = computed(() => shortTermData.value)
const postEmploymentRows = computed(() => postEmploymentData.value)

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
      year: useAuditContext().year.value,
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
    autoSync.scheduleAutoSync(syncToDisclosureNotes)
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

function addRow(category: string) {
  if (isReadonly) return
  const arr = category === 'short_term' ? shortTermData : postEmploymentData
  const newRow: DRow = { id: `${category}-${Date.now()}`, label: '', category, indent: 1,
    beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 }
  const sel = selectedRow.value
  if (sel && !sel.isSubtotal && sel.category === category) {
    const idx = arr.value.findIndex(r => r.id === sel.id)
    if (idx >= 0) { arr.value.splice(idx + 1, 0, newRow); persist(); autoSync.scheduleAutoSync(syncToDisclosureNotes); return }
  }
  arr.value.push(newRow)
  persist()
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function removeRow(id: string, category: string) {
  const arr = category === 'short_term' ? shortTermData : postEmploymentData
  const idx = arr.value.findIndex(r => r.id === id)
  if (idx >= 0) { arr.value.splice(idx, 1); persist(); autoSync.scheduleAutoSync(syncToDisclosureNotes) }
}

function fmtN(v: number | null | undefined): string {
  if (!v) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
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
          汇总表期末合计: String(summaryRows.value.at(-1)?.endBalance ?? 0),
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
.disc-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
.section-card { margin-bottom: 16px; }
.section-card :deep(.el-card__header) { padding: 8px 16px; }
.section-card :deep(.el-card__body) { padding: 12px 16px; }
.section-card :deep(.el-table) { font-size: 13px !important; }
.section-card :deep(.el-table th), .section-card :deep(.el-table td) { font-size: 13px !important; padding: 4px 6px !important; }
.section-card :deep(.el-input-number) { width: 100%; }
.section-card :deep(.el-input-number .el-input__inner) { text-align: right; font-size: 13px; }
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
