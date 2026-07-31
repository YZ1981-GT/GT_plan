<template>
<div class="f1-disclosure-listed">
  <template v-if="!isApplicable">
    <el-alert type="info" title="当前项目不适用上市公司附注披露格式" :closable="false" show-icon />
  </template>
  <template v-else>
    <details class="guidance-details">
      <summary>编制提示</summary>
      <div class="guidance-content">
        <p>1. （1）按账龄披露：5 列（期末余额 / 上年年末余额各含金额+比例%），行序 = 各账龄段 → 小计 → 减：减值准备 → 合计；金额自 F1-2 审定账龄聚合（与 F1-1 按账龄勾稽），仅「减：减值准备」两格需手工录入。</p>
        <p>2. （2）账龄超过1年的重要预付款项：列为 债务人名称 / 账面余额 / 占预付款项合计的比例（%）/ 减值准备（上市列报格式无「账龄」「未结算的原因」列）；逐户原因展开行录入后点「据此生成说明」汇编到说明段落。</p>
        <p>3. （3）前五名：汇总披露格式自动生成；分别披露表按期末余额降序取前五，3 列。</p>
        <p>4. 账龄档数随项目账龄枚举（3年段 / 5年段 / 自定义）自动适配，在 F1-2 明细表切换。</p>
        <p>5. 「同步到附注」推送至附注模块「{{ noteSectionId }} 预付款项」。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：按上市公司列报要求披露预付款项账龄、超1年重要款项及前五名，确保与 F1-1/F1-2 勾稽并同步附注。"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button
          size="small"
          type="primary"
          plain
          :loading="isSyncing"
          :disabled="isReadonly"
          @click="syncToDisclosureNotes"
        >同步到附注</el-button>
        <el-button size="small" type="primary" plain :disabled="!projectId" @click="jumpToNote('listed')">↩ 跳转回附注</el-button>
        <el-button size="small" text type="primary" @click="showGuide = true">使用手册</el-button>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:F1-1" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:F1-2" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip :value="`Note:${noteSectionId}`" :context-project-id="projectId" /></span>
      </div>
    </div>

    <!-- (1) 账龄分析 -->
    <div class="disclosure-card">
      <h4 class="card-title">
        (1) 预付款项按账龄披露
        <el-tooltip content="数据来源：F1-2 审定账龄聚合 → 与 F1-1 按账龄勾稽" placement="top">
          <el-tag size="small" type="info">跨sheet取数</el-tag>
        </el-tooltip>
        <GtIndexChip value="wp:F1-1" :context-project-id="projectId" />
      </h4>
      <div class="methodology-context">
        源模板口径：账龄 + 期末余额{金额、比例%} + 上年年末余额{金额、比例%}；
        行序为各账龄段 → 小计 → 减：减值准备 → 合计。
        金额取自 F1-1 审定表「按账龄分类」审定数（= F1-2 明细表审定账龄聚合）。
      </div>
      <el-table :data="agingTableData" size="small" border stripe class="disclosure-table" style="width:100%">
        <el-table-column prop="label" label="账龄" min-width="140">
          <template #default="{ row }">
            <span :class="{ 'subtotal-label': row.isSummary }">{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" align="center">
          <el-table-column label="金额" min-width="140" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.rowId === '__impairment__'"
                :model-value="row.endAmount"
                size="small"
                :controls="false"
                :precision="2"
                :disabled="isReadonly"
                style="width:100%"
                @change="(v: number | undefined) => persistImpairment(v ?? 0)"
              />
              <span v-else class="cross-sheet-cell" :class="{ 'subtotal-val': row.isSummary }">
                {{ fmtAmount(row.endAmount) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="比例%" min-width="100" align="right">
            <template #default="{ row }">
              <span v-if="row.showPct" class="cross-sheet-cell">{{ fmtPct(row.endPct) }}</span>
              <span v-else class="muted">——</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="上年年末余额" align="center">
          <el-table-column label="金额" min-width="140" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.rowId === '__impairment__'"
                :model-value="row.priorAmount"
                size="small"
                :controls="false"
                :precision="2"
                :disabled="isReadonly"
                style="width:100%"
                @change="(v: number | undefined) => persistImpairmentPrior(v ?? 0)"
              />
              <span v-else class="cross-sheet-cell" :class="{ 'subtotal-val': row.isSummary }">
                {{ fmtAmount(row.priorAmount) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="比例%" min-width="100" align="right">
            <template #default="{ row }">
              <span v-if="row.showPct" class="cross-sheet-cell">{{ fmtPct(row.priorPct) }}</span>
              <span v-else class="muted">——</span>
            </template>
          </el-table-column>
        </el-table-column>
      </el-table>
      <p class="hint">
        账龄段随项目账龄枚举自动适配（当前 {{ agingRows.length }} 档）；
        勾稽：各段之和 = 小计，合计 = 小计 − 减：减值准备（期末 / 上年年末各独立）。
      </p>
      <div class="note-block">
        <div class="note-label">
          <span>说明：</span>
          <el-button
            class="ai-btn" size="small" type="primary" plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading && aiActiveSection === 'listed-note-aging'"
            @click="runAi('listed-note-aging')"
          >🤖 AI 辅助</el-button>
        </div>
        <el-input
          v-model="note1"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          placeholder="账龄披露说明..."
        />
      </div>
    </div>

    <!-- (2) 超1年重要 -->
    <div class="disclosure-card">
      <h4 class="card-title">
        (2) 账龄超过1年的重要预付款项
        <el-button size="small" :disabled="isReadonly" @click="addOver1Row()">+ 添加</el-button>
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="onComposeOver1Note">据此生成说明</el-button>
        <GtIndexChip value="wp:F1-2" :context-project-id="projectId" />
      </h4>
      <div class="methodology-context">
        源模板说明：（账龄超过1年的金额重要预付账款，应说明未及时结算的原因。）
        上市公司列报格式本表**不含**「账龄」「未结算的原因」列，原因在下方说明段落披露 ——
        逐户原因请展开行录入，再点「据此生成说明」汇编。
      </div>
      <el-table :data="over1TableData" size="small" border stripe class="disclosure-table" style="width:100%">
        <el-table-column type="expand">
          <template #default="{ row }">
            <div v-if="row.rowId !== '__total__'" class="expand-pane">
              <span class="expand-label">未及时结算的原因</span>
              <el-input
                :model-value="row.reason"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 5 }"
                :disabled="isReadonly"
                placeholder="说明该笔预付款项未及时结算的原因（供下方说明段落汇编，不作为附注列）"
                @change="(v: string) => updateOver1Reason(row.rowId, v)"
              />
            </div>
          </template>
        </el-table-column>
        <el-table-column label="债务人名称" min-width="160">
          <template #default="{ row }">
            <template v-if="row.rowId === '__total__'">
              <span class="subtotal-label">合计</span>
            </template>
            <template v-else-if="row.fromCrossSheet">
              <span class="cross-sheet-cell">{{ row.debtorName }}</span>
            </template>
            <template v-else>
              <el-input
                :model-value="row.debtorName"
                size="small"
                :disabled="isReadonly"
                @change="(v: string) => updateOver1Field(row.rowId, 'debtorName', v)"
              />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="账面余额" min-width="130" align="right">
          <template #default="{ row }">
            <template v-if="row.rowId === '__total__' || row.fromCrossSheet">
              <span :class="{ 'cross-sheet-cell': row.fromCrossSheet, 'subtotal-val': row.rowId === '__total__' }">
                {{ fmtAmount(row.endBalance) }}
              </span>
            </template>
            <template v-else>
              <el-input-number
                :model-value="row.endBalance"
                size="small"
                :controls="false"
                :precision="2"
                :disabled="isReadonly"
                style="width:100%"
                @change="(v: number | undefined) => updateOver1Field(row.rowId, 'endBalance', v ?? 0)"
              />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="占预付款项合计的比例（%）" min-width="170" align="right">
          <template #default="{ row }">
            <span>{{ fmtPct(row.proportionPct) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值准备" min-width="130" align="right">
          <template #default="{ row }">
            <template v-if="row.rowId === '__total__'">
              <span class="subtotal-val">{{ fmtAmount(row.impairment) }}</span>
            </template>
            <template v-else>
              <el-input-number
                :model-value="row.impairment"
                size="small"
                :controls="false"
                :precision="2"
                :disabled="isReadonly"
                style="width:100%"
                @change="(v: number | undefined) => updateOver1Field(row.rowId, 'impairment', v ?? 0)"
              />
            </template>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" min-width="64" width="64">
          <template #default="{ row }">
            <el-popconfirm
              v-if="!row.fromCrossSheet && row.rowId !== '__total__'"
              title="删除？"
              @confirm="removeOver1Row(row.rowId)"
            >
              <template #reference>
                <el-button size="small" type="danger" link>删</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
      <div class="note-block">
        <div class="note-label">
          <span>说明：</span>
          <el-button
            class="ai-btn" size="small" type="primary" plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading && aiActiveSection === 'listed-note-over1'"
            @click="runAi('listed-note-over1')"
          >🤖 AI 辅助</el-button>
        </div>
        <el-input
          v-model="note2"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          placeholder="账龄超过1年的金额重要预付账款，应说明未及时结算的原因。"
        />
      </div>
    </div>

    <!-- (3) 前五名 -->
    <div class="disclosure-card">
      <h4 class="card-title">
        (3) 按预付对象归集的预付款项期末余额前五名单位情况
        <GtIndexChip value="wp:F1-2" :context-project-id="projectId" />
      </h4>
      <div class="methodology-context">
        源模板说明：（按预付对象集中度，汇总或分别披露期末余额前五名的预付款项的期末余额及占预付款项期末余额合计数的比例。）
        两种格式择一披露 —— 集中度低用汇总格式，集中度高或单户重大用分别格式。
      </div>
      <p class="sub-label">汇总披露格式</p>
      <el-input
        type="textarea"
        :rows="2"
        :model-value="top5SummaryText"
        :disabled="isReadonly"
        placeholder="本期按预付对象归集的期末余额前五名预付款项汇总金额……"
        @change="(v: string) => persistTop5Summary(v)"
      />
      <p class="hint">留空则使用自动汇总：{{ top5SummaryAuto }}</p>

      <p class="sub-label">分别披露格式</p>
      <el-table :data="top5TableData" size="small" border stripe class="disclosure-table" style="width:100%">
        <el-table-column label="单位名称" min-width="180">
          <template #default="{ row }">
            <span :class="{ 'subtotal-label': row.rowId === '__total__' }">
              {{ row.rowId === '__total__' ? '合计' : row.entityName }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="预付款项期末余额" min-width="150" align="right">
          <template #default="{ row }">
            <span class="cross-sheet-cell" :class="{ 'subtotal-val': row.rowId === '__total__' }">
              {{ fmtAmount(row.endBalance) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="占预付款项期末余额合计数的比例%" min-width="200" align="right">
          <template #default="{ row }">
            <span class="cross-sheet-cell">{{ fmtPct(row.proportionPct) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <div class="note-block">
        <div class="note-label">
          <span>说明：</span>
          <el-button
            class="ai-btn" size="small" type="primary" plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading && aiActiveSection === 'listed-note-top5'"
            @click="runAi('listed-note-top5')"
          >🤖 AI 辅助</el-button>
        </div>
        <el-input
          v-model="note3"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          placeholder="前五名披露说明..."
        />
      </div>
    </div>
  </template>

  <F1DisclosureUsageGuide v-model="showGuide" variant="listed" />
</div>
</template>

<script setup lang="ts">
import { computed, ref, toRef, onUnmounted, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import { useF1DisclosureListed } from '../composables/useF1DisclosureListed'
import { useDisclosureAutoSync } from '../composables/useDisclosureAutoSync'
import { useF1AiGenerate, type F1AiSection } from '../composables/useF1AiGenerate'
import {
  buildF1ListedSubTableData,
  buildF1SyncPayload,
} from '../composables/f1DisclosureSyncPayload'
import { F1_NOTE_SECTION } from '../composables/f1NoteSectionMap'
import type { useF1CrossSheet } from '../composables/useF1CrossSheet'
import type { ChecklistResponse } from '../composables/useF1FormData'
import GtIndexChip from '../GtIndexChip.vue'
import F1DisclosureUsageGuide from './F1DisclosureUsageGuide.vue'

const props = withDefaults(defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  crossSheet: ReturnType<typeof useF1CrossSheet>
  applicableStandards?: string[]
  /** 审计年度（附注同步显式传 year，避免后端回退服务器自然年写错年度） */
  year?: number
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>(), {
  applicableStandards: () => [],
})

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>
const noteSectionId = F1_NOTE_SECTION.listed
const showGuide = ref(false)
const isSyncing = ref(false)

const router = useRouter()
// 跳转回附注模块（披露表 → 附注为单向推送；此处仅导航，方便相互编辑确认）
function jumpToNote(target: DisclosureVariant): void {
  const route = buildNoteJumpRoute(props.projectId || '', 'F1', target)
  if (!route) { ElMessage.warning('未找到对应的附注章节'); return }
  router.push(route)
}

// 保存后自动同步到附注（防抖/非阻塞/失败静默/只读 gate）：包装传入 composable 的
// saveImmediate/debouncedSave，使任一字段保存都触发一次与手动按钮同源的 syncToDisclosureNotes。
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
onUnmounted(() => autoSync.cancelPending())
const autoSaveImmediate = async (itemId: string, data: Partial<ChecklistResponse>): Promise<void> => {
  await props.saveImmediate(itemId, data)
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}
const autoDebouncedSave = (itemId: string, data: Partial<ChecklistResponse>): void => {
  props.debouncedSave(itemId, data)
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

const {
  isApplicable,
  agingRows,
  agingTotal,
  agingImpairmentRow,
  agingNet,
  persistImpairment,
  persistImpairmentPrior,
  applyComposedOver1Note,
  over1YearRows,
  over1YearTotal,
  addOver1Row,
  removeOver1Row,
  updateOver1Reason,
  updateOver1Field,
  top5Rows,
  top5Total,
  top5SummaryText,
  top5SummaryAuto,
  persistTop5Summary,
  note1,
  note2,
  note3,
  getSyncSnapshot,
} = useF1DisclosureListed({
  allResponses: allResponsesRef,
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  saveImmediate: autoSaveImmediate,
  debouncedSave: autoDebouncedSave,
  crossSheet: props.crossSheet,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
  applicableStandards: toRef(props, 'applicableStandards') as unknown as Ref<string[]>,
})

// ─── AI 辅助（每个说明文本域一个 section，键与同步 `_note_texts` 同名）───
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF1AiGenerate(
  toRef(props, 'wpId') as Ref<string>,
)
/** 当前正在生成的 section，只在该按钮上转圈 */
const aiActiveSection = ref<F1AiSection | ''>('')

/** 传给 AI 的上下文：账龄结构 + 集中度，避免模型凭空编数 */
function aiContext(): Record<string, unknown> {
  return {
    noteSection: noteSectionId,
    agingRows: (agingRows.value ?? []).map((r) => ({
      aging: r.label,
      endAmount: r.endAmount,
      endPct: r.endPct,
      priorAmount: r.priorAmount,
      priorPct: r.priorPct,
    })),
    agingSubtotal: agingTotal.value,
    impairment: agingImpairmentRow.value,
    agingNet: agingNet.value,
    over1YearRows: (over1YearRows.value ?? []).map((r) => ({
      debtor: r.debtorName,
      endBalance: r.endBalance,
      proportionPct: r.proportionPct,
      impairment: r.impairment,
      reason: r.reason,
    })),
    over1YearTotal: over1YearTotal.value,
    top5Rows: (top5Rows.value ?? []).map((r) => ({
      entity: r.entityName,
      endBalance: r.endBalance,
      proportionPct: r.proportionPct,
    })),
    top5Total: top5Total.value,
  }
}

/** section → 目标 ref + 弹窗标题（模板里 ref 自动解包，故由此表在 script 内回写） */
const AI_TARGETS: Record<string, { target: Ref<string>; title: string }> = {
  'listed-note-aging': { target: note1, title: 'AI 生成 · 预付款项按账龄披露说明' },
  'listed-note-over1': { target: note2, title: 'AI 生成 · 账龄超过1年的重要预付款项说明' },
  'listed-note-top5': { target: note3, title: 'AI 生成 · 前五名预付款项说明' },
}

async function runAi(section: F1AiSection): Promise<void> {
  if (props.isReadonly) return
  const entry = AI_TARGETS[section]
  if (!entry) return
  aiActiveSection.value = section
  try {
    const text = await generateAndConfirm(section, entry.target.value || '', aiContext(), entry.title)
    if (text) entry.target.value = text
  } finally {
    aiActiveSection.value = ''
  }
}

const over1TotalRow = computed(() => ({
  rowId: '__total__',
  debtorName: '合计',
  endBalance: over1YearTotal.value.endBalance,
  proportionPct: over1YearTotal.value.proportionPct,
  impairment: over1YearTotal.value.impairment,
  reason: '',
  fromCrossSheet: false,
}))

const top5TotalRow = computed(() => ({
  rowId: '__total__',
  entityName: '合计',
  endBalance: top5Total.value.endBalance,
  proportionPct: top5Total.value.proportionPct,
}))

/**
 * (1) 账龄表 = 各账龄段 + 小计 + 减：减值准备 + 合计（与附注 §五、7 同构）
 * `showPct`：减值准备行与合计行不参与比例校验（F7-8）→ 比例列显示 ——
 */
const agingTableData = computed(() => [
  ...(agingRows.value ?? []).map((r) => ({ ...r, isSummary: false, showPct: true })),
  { ...agingTotal.value, isSummary: true, showPct: true },
  { ...agingImpairmentRow.value, endPct: 0, priorPct: 0, isSummary: false, showPct: false },
  { ...agingNet.value, endPct: 0, priorPct: 0, isSummary: true, showPct: false },
])
/** 避免模板 spread 在 Ref 未就绪时抛出 “X is not iterable” */
const over1TableData = computed(() => [...(over1YearRows.value ?? []), over1TotalRow.value])
const top5TableData = computed(() => [...(top5Rows.value ?? []), top5TotalRow.value])

function onComposeOver1Note(): void {
  if (applyComposedOver1Note()) {
    ElMessage.success('已按逐户原因生成说明')
  } else {
    ElMessage.warning('请先在展开行填写「未及时结算的原因」')
  }
}

async function syncToDisclosureNotes() {
  const payload = buildF1SyncPayload(
    'listed',
    props.wpId,
    props.applicableStandards,
    buildF1ListedSubTableData(getSyncSnapshot()),
    props.year,
  )
  if (!payload) {
    ElMessage.warning('当前项目准则不适用上市公司附注同步')
    return
  }
  isSyncing.value = true
  try {
    const result: any = await api.post(
      `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
      payload,
    )
    const data = result?.data ?? result
    ElMessage.success(`已同步 ${Number(data?.rows_synced ?? 0)} 行到附注模块「${noteSectionId} 预付款项」`)
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function fmtPct(val: number | null | undefined): string {
  if (val == null || !isFinite(val) || val === 0) return '-'
  return `${val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`
}
</script>

<style scoped>
.f1-disclosure-listed {
  padding: 16px;
  font-size: 13px;
  width: 100%;
  box-sizing: border-box;
}
.f1-disclosure-listed :deep(.el-table) {
  --el-table-font-size: 13px;
  font-size: 13px;
  width: 100% !important;
}
.f1-disclosure-listed :deep(.el-table .cell) {
  font-size: 13px !important;
}
.f1-disclosure-listed :deep(.disclosure-table) {
  width: 100%;
}
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; }
.disclosure-card {
  margin-bottom: 20px;
  padding: 16px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  width: 100%;
  box-sizing: border-box;
}
.card-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.sub-label { margin: 12px 0 6px; font-size: 13px; font-weight: 600; color: #606266; }
.hint { margin: 4px 0 12px; font-size: 12px; color: #909399; }
.subtotal-label, .subtotal-val { font-weight: 700; }
.cross-sheet-cell { background: #ecf5ff; padding: 2px 6px; border-radius: 2px; }
.muted { color: #909399; }
.methodology-context {
  margin-bottom: 10px;
  padding: 8px 12px;
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  border-radius: 4px;
  font-size: 12px;
  color: #8a6d3b;
  line-height: 1.7;
}
.expand-pane { padding: 8px 24px; display: flex; align-items: flex-start; gap: 10px; }
.expand-label { font-size: 13px; color: #606266; white-space: nowrap; padding-top: 6px; }
.note-block { margin-top: 12px; }
/* 文本域标题行：AI 辅助按钮右对齐在同一行（平台底稿 UI 规范） */
.note-label {
  font-size: 13px;
  color: #606266;
  margin-bottom: 4px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.ai-btn { margin-left: auto; }
</style>
