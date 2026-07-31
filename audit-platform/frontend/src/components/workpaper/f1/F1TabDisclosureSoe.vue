<template>
<div class="f1-disclosure-soe">
  <template v-if="!isApplicable">
    <el-alert type="info" title="当前项目不适用国企附注披露格式" :closable="false" show-icon />
  </template>
  <template v-else>
    <details class="guidance-details">
      <summary>编制提示</summary>
      <div class="guidance-content">
        <p>1. （1）按账龄列示：期末数/期初数各含账面余额（金额+比例（%））与减值准备；账面余额自 F1-2 审定账龄聚合，减值准备逐段录入。行序 = 各账龄段 → 小计 → 减：减值准备 → 合计。</p>
        <p>2. （2）账龄超过1年的大额预付款项：债权单位可填；债务单位/余额/账龄自 F1-5 带入，须补「未结算的原因」。</p>
        <p>3. （3）按欠款方归集的期末余额前五名：按期末余额降序；减值准备可手工录入。</p>
        <p>4. 账龄档数随项目账龄枚举（3年段 / 5年段 / 自定义）自动适配，在 F1-2 明细表切换；超1年行的账龄下拉同步排除首档。</p>
        <p>5. 「同步到附注」推送至附注模块「{{ noteSectionId }} 预付款项」——逐段减值准备聚合为一行。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：按国有企业财务报告及国资监管要求披露预付款项账龄、超1年大额及前五名，与 F1-1/F1-2 勾稽并同步附注。"
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
        <el-button size="small" type="primary" plain :disabled="!projectId" @click="jumpToNote('soe')">↩ 跳转回附注</el-button>
        <el-button size="small" text type="primary" @click="showGuide = true">使用手册</el-button>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:F1-1" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:F1-2" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip :value="`Note:${noteSectionId}`" :context-project-id="projectId" /></span>
      </div>
    </div>

    <!-- (1) 账龄列示 -->
    <div class="disclosure-card">
      <h4 class="card-title">
        (1) 预付款项按账龄列示
        <el-tooltip content="账面余额自 F1-2 审定账龄聚合；坏账准备可手工录入" placement="top">
          <el-tag size="small" type="info">跨sheet取数</el-tag>
        </el-tooltip>
        <GtIndexChip value="wp:F1-1" :context-project-id="projectId" />
      </h4>
      <div class="methodology-context">
        源模板口径：账龄 + 期末数{账面余额（金额、比例（%））、减值准备} + 期初数{同上}。
        账面余额取自 F1-1 审定表「按账龄分类」审定数；减值准备逐账龄段录入。
        同步到附注时逐段减值准备聚合为「减：减值准备」一行（附注模版与校验预设 F7-7 口径），
        「合计」行 = 小计 − 减：减值准备。
      </div>
      <el-table :data="agingTableData" size="small" border stripe>
        <el-table-column prop="label" label="账龄" width="150">
          <template #default="{ row }">
            <span :class="{ 'subtotal-label': row.isSummary }">{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末数" align="center">
          <el-table-column label="账面余额" align="center">
            <el-table-column label="金额" width="130" align="right">
              <template #default="{ row }">
                <span class="cross-sheet-cell" :class="{ 'subtotal-val': row.isSummary }">
                  {{ fmtAmount(row.endAmount) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="比例（%）" width="100" align="right">
              <template #default="{ row }">
                <span v-if="row.showPct" class="cross-sheet-cell">{{ fmtPct(row.endPct) }}</span>
                <span v-else class="muted">——</span>
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="减值准备" width="120" align="right">
            <template #default="{ row }">
              <template v-if="row.isDerived">
                <span class="muted">——</span>
              </template>
              <template v-else-if="row.isSummary">
                <span class="subtotal-val">{{ fmtAmount(row.endBadDebt) }}</span>
              </template>
              <template v-else>
                <el-input-number
                  :model-value="row.endBadDebt"
                  size="small"
                  :controls="false"
                  :precision="2"
                  :disabled="isReadonly"
                  style="width:100%"
                  @change="(v: number | undefined) => updateAgingBadDebt(row.key, 'end', v ?? 0)"
                />
              </template>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期初数" align="center">
          <el-table-column label="账面余额" align="center">
            <el-table-column label="金额" width="130" align="right">
              <template #default="{ row }">
                <span class="cross-sheet-cell" :class="{ 'subtotal-val': row.isSummary }">
                  {{ fmtAmount(row.priorAmount) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="比例（%）" width="100" align="right">
              <template #default="{ row }">
                <span v-if="row.showPct" class="cross-sheet-cell">{{ fmtPct(row.priorPct) }}</span>
                <span v-else class="muted">——</span>
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="减值准备" width="120" align="right">
            <template #default="{ row }">
              <template v-if="row.isDerived">
                <span class="muted">——</span>
              </template>
              <template v-else-if="row.isSummary">
                <span class="subtotal-val">{{ fmtAmount(row.priorBadDebt) }}</span>
              </template>
              <template v-else>
                <el-input-number
                  :model-value="row.priorBadDebt"
                  size="small"
                  :controls="false"
                  :precision="2"
                  :disabled="isReadonly"
                  style="width:100%"
                  @change="(v: number | undefined) => updateAgingBadDebt(row.key, 'prior', v ?? 0)"
                />
              </template>
            </template>
          </el-table-column>
        </el-table-column>
      </el-table>
      <p class="hint">
        账龄段随项目账龄枚举自动适配（当前 {{ agingRows.length }} 档）；
        勾稽：各段之和 = 小计；合计 = 小计 − 减：减值准备（期末 / 期初各独立）。
      </p>
      <div class="note-block">
        <div class="note-label">
          <span>说明：</span>
          <el-button
            class="ai-btn" size="small" type="primary" plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading && aiActiveSection === 'soe-note-aging'"
            @click="runAi('soe-note-aging')"
          >🤖 AI 辅助</el-button>
        </div>
        <el-input
          v-model="note1"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          placeholder="账龄列示说明..."
        />
      </div>
    </div>

    <!-- (2) 超1年 -->
    <div class="disclosure-card">
      <h4 class="card-title">
        (2) 账龄超过1年的大额预付款项
        <el-button size="small" :disabled="isReadonly" @click="addOver1Row()">+ 添加</el-button>
        <GtIndexChip value="wp:F1-5" :context-project-id="projectId" />
      </h4>
      <div class="methodology-context">
        源模板口径：债权单位 / 债务单位 / 期末余额 / 账龄 / 未结算的原因，五列齐备。
        债务单位、期末余额、账龄自 F1-5「账龄1年以上的大额预付账款检查表」带入；
        完整性校验：期末余额 ≠ 0 的行四列均不得为空。
      </div>
      <el-table :data="over1TableData" size="small" border stripe>
        <el-table-column label="债权单位" min-width="120">
          <template #default="{ row }">
            <template v-if="row.rowId === '__total__'">
              <span class="subtotal-label">合计</span>
            </template>
            <template v-else>
              <el-input
                :model-value="row.creditorUnit"
                size="small"
                :disabled="isReadonly"
                @change="(v: string) => updateOver1Field(row.rowId, 'creditorUnit', v)"
              />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="债务单位" min-width="140">
          <template #default="{ row }">
            <template v-if="row.rowId === '__total__'" />
            <template v-else-if="row.fromCrossSheet">
              <span class="cross-sheet-cell">{{ row.debtorUnit }}</span>
            </template>
            <template v-else>
              <el-input
                :model-value="row.debtorUnit"
                size="small"
                :disabled="isReadonly"
                @change="(v: string) => updateOver1Field(row.rowId, 'debtorUnit', v)"
              />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="120" align="right">
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
                :disabled="isReadonly"
                @change="(v: number | undefined) => updateOver1Field(row.rowId, 'endBalance', v ?? 0)"
              />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="账龄" width="140">
          <template #default="{ row }">
            <el-select
              v-if="row.rowId !== '__total__'"
              :model-value="row.agingLabel"
              size="small"
              :disabled="isReadonly"
              filterable
              allow-create
              clearable
              placeholder="选择账龄"
              @change="(v: string) => updateOver1Field(row.rowId, 'agingLabel', v ?? '')"
            >
              <el-option v-for="opt in over1AgingOptions" :key="opt" :label="opt" :value="opt" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="未结算的原因" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="row.rowId !== '__total__'"
              :model-value="row.reason"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => updateOver1Field(row.rowId, 'reason', v)"
            />
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56">
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
            :loading="aiLoading && aiActiveSection === 'soe-note-over1'"
            @click="runAi('soe-note-over1')"
          >🤖 AI 辅助</el-button>
        </div>
        <el-input
          v-model="note2"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          placeholder="超1年重要预付款项说明..."
        />
      </div>
    </div>

    <!-- (3) 前五名 -->
    <div class="disclosure-card">
      <h4 class="card-title">
        (3) 按欠款方归集的期末余额前五名的预付款项情况
        <GtIndexChip value="wp:F1-2" :context-project-id="projectId" />
      </h4>
      <div class="methodology-context">
        源模板口径：债务人名称 / 账面余额 / 占预付款项合计的比例（%）/ 减值准备。
        按期末账面余额降序自 F1-2 明细表归集前五名；占比分母 = 按账龄表小计行期末金额。
      </div>
      <el-table :data="top5TableData" size="small" border stripe>
        <el-table-column label="债务人名称" min-width="160">
          <template #default="{ row }">
            <span :class="{ 'subtotal-label': row.rowId === '__total__' }">
              {{ row.rowId === '__total__' ? '合计' : row.debtorName }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="账面余额" width="130" align="right">
          <template #default="{ row }">
            <span class="cross-sheet-cell" :class="{ 'subtotal-val': row.rowId === '__total__' }">
              {{ fmtAmount(row.endBalance) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="占预付款项合计的比例（%）" width="180" align="right">
          <template #default="{ row }">
            <span class="cross-sheet-cell">{{ fmtPct(row.proportionPct) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值准备" width="120" align="right">
          <template #default="{ row }">
            <template v-if="row.rowId === '__total__'">
              <span class="subtotal-val">{{ fmtAmount(row.badDebt) }}</span>
            </template>
            <template v-else>
              <el-input-number
                :model-value="row.badDebt"
                size="small"
                :controls="false"
                :precision="2"
                :disabled="isReadonly"
                style="width:100%"
                @change="(v: number | undefined) => updateTop5BadDebt(row.debtorName, v ?? 0)"
              />
            </template>
          </template>
        </el-table-column>
      </el-table>
      <div class="note-block">
        <div class="note-label">
          <span>说明：</span>
          <el-button
            class="ai-btn" size="small" type="primary" plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading && aiActiveSection === 'soe-note-top5'"
            @click="runAi('soe-note-top5')"
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

  <F1DisclosureUsageGuide v-model="showGuide" variant="soe" />
</div>
</template>

<script setup lang="ts">
import { computed, ref, toRef, onBeforeUnmount, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import { useF1DisclosureSoe } from '../composables/useF1DisclosureSoe'
import { useF1AiGenerate, type F1AiSection } from '../composables/useF1AiGenerate'
import {
  buildF1SoeSubTableData,
  buildF1SyncPayload,
} from '../composables/f1DisclosureSyncPayload'
import { F1_NOTE_SECTION } from '../composables/f1NoteSectionMap'
import type { useF1CrossSheet } from '../composables/useF1CrossSheet'
import type { ChecklistResponse } from '../composables/useF1FormData'
import { ADJUDICATION_LABEL_BY_SEGMENT_KEY } from '../composables/agingPresets'
import GtIndexChip from '../GtIndexChip.vue'
import F1DisclosureUsageGuide from './F1DisclosureUsageGuide.vue'
import { useDisclosureAutoSync } from '../composables/useDisclosureAutoSync'

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
const noteSectionId = F1_NOTE_SECTION.soe
const showGuide = ref(false)
const isSyncing = ref(false)

// 保存后自动同步到附注（防抖/非阻塞/失败静默/只读 gate；与手动按钮同源 syncToDisclosureNotes）
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
onBeforeUnmount(() => autoSync.cancelPending())
// 包装 saveImmediate/debouncedSave 使任一字段保存都触发一次自动同步
const autoSaveImmediate = async (itemId: string, data: Partial<ChecklistResponse>): Promise<void> => {
  await props.saveImmediate(itemId, data)
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}
const autoDebouncedSave = (itemId: string, data: Partial<ChecklistResponse>): void => {
  props.debouncedSave(itemId, data)
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

const router = useRouter()
// 跳转回附注模块（披露表 → 附注为单向推送；此处仅导航，方便相互编辑确认）
function jumpToNote(target: DisclosureVariant): void {
  const route = buildNoteJumpRoute(props.projectId || '', 'F1', target)
  if (!route) { ElMessage.warning('未找到对应的附注章节'); return }
  router.push(route)
}

/** 超1年行账龄下拉：跟项目/明细枚举（排除 1年以内） */
const over1AgingOptions = computed(() => {
  const segs = props.crossSheet.agingSegments?.value || []
  const labels = segs
    .filter((s) => s.key !== 'within1' && s.dayFrom >= 366)
    .map((s) => ADJUDICATION_LABEL_BY_SEGMENT_KEY[s.key] || s.label)
  if (labels.length) return labels
  return segs
    .filter((s) => s.key !== 'within1')
    .map((s) => ADJUDICATION_LABEL_BY_SEGMENT_KEY[s.key] || s.label)
})

const {
  isApplicable,
  agingRows,
  agingTotal,
  agingImpairmentRow,
  agingNet,
  updateAgingBadDebt,
  over1YearRows,
  over1YearTotal,
  addOver1Row,
  removeOver1Row,
  updateOver1Field,
  top5Rows,
  top5Total,
  updateTop5BadDebt,
  note1,
  note2,
  note3,
  getSyncSnapshot,
} = useF1DisclosureSoe({
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
      creditorUnit: r.creditorUnit,
      debtorUnit: r.debtorUnit,
      endBalance: r.endBalance,
      aging: r.agingLabel,
      reason: r.reason,
    })),
    over1YearTotal: over1YearTotal.value,
    top5Rows: (top5Rows.value ?? []).map((r) => ({
      debtor: r.debtorName,
      endBalance: r.endBalance,
      proportionPct: r.proportionPct,
      badDebt: r.badDebt,
    })),
    top5Total: top5Total.value,
  }
}

const AI_TARGETS: Record<string, { target: Ref<string>; title: string }> = {
  'soe-note-aging': { target: note1, title: 'AI 生成 · 预付款项按账龄列示说明' },
  'soe-note-over1': { target: note2, title: 'AI 生成 · 账龄超过1年的大额预付款项说明' },
  'soe-note-top5': { target: note3, title: 'AI 生成 · 前五名预付款项说明' },
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
  creditorUnit: '',
  debtorUnit: '',
  endBalance: over1YearTotal.value.endBalance,
  agingLabel: '',
  reason: '',
  fromCrossSheet: false,
}))

const top5TotalRow = computed(() => ({
  rowId: '__total__',
  debtorName: '合计',
  endBalance: top5Total.value.endBalance,
  proportionPct: top5Total.value.proportionPct,
  badDebt: top5Total.value.badDebt,
}))

/**
 * (1) 账龄表 = 各账龄段 + 小计 + 减：减值准备 + 合计（与附注 §八、7 同构）
 * `isDerived`：派生行的减值准备列显示 ——（其值已在「减：减值准备」行的金额列体现）
 * `showPct`：减值准备行与合计行不参与比例校验（F7-8）
 */
const agingTableData = computed(() => [
  ...(agingRows.value ?? []).map((r) => ({ ...r, isSummary: false, isDerived: false, showPct: true })),
  { ...agingTotal.value, isSummary: true, isDerived: false, showPct: true },
  {
    ...agingImpairmentRow.value,
    key: 'impairment',
    endPct: 0,
    priorPct: 0,
    endBadDebt: 0,
    priorBadDebt: 0,
    isSummary: false,
    isDerived: true,
    showPct: false,
  },
  {
    ...agingNet.value,
    key: 'net',
    endPct: 0,
    priorPct: 0,
    endBadDebt: 0,
    priorBadDebt: 0,
    isSummary: true,
    isDerived: true,
    showPct: false,
  },
])
/** 避免模板 spread 在 Ref 未就绪时抛出 “X is not iterable” */
const over1TableData = computed(() => [...(over1YearRows.value ?? []), over1TotalRow.value])
const top5TableData = computed(() => [...(top5Rows.value ?? []), top5TotalRow.value])

async function syncToDisclosureNotes() {
  const payload = buildF1SyncPayload(
    'soe',
    props.wpId,
    props.applicableStandards,
    buildF1SoeSubTableData(getSyncSnapshot()),
    props.year,
  )
  if (!payload) {
    ElMessage.warning('当前项目准则不适用国企附注同步')
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
.f1-disclosure-soe { padding: 16px; }
.f1-disclosure-soe :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
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
.subtotal-label, .subtotal-val { font-weight: 700; }
.cross-sheet-cell { background: #ecf5ff; padding: 2px 6px; border-radius: 2px; }
.muted { color: #909399; }
.hint { margin: 6px 0 0; font-size: 12px; color: #909399; }
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
