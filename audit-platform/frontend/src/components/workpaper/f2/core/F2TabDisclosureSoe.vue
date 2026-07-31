<script setup lang="ts">
/** F2TabDisclosureSoe — 附注披露（国企），对齐源模板结构 */
import { inject, ref, toRef, watch, onBeforeUnmount, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import { useF2DisclosureSoe } from '../../composables/useF2DisclosureSoe'
import { DR_COL_LABELS, DR_INPUT_COLS } from '../../composables/f2DataResourceInventory'
import { useF2AiGenerate, type F2AiSection } from '../../composables/useF2AiGenerate'
import WpAmountInput from '../../shared/WpAmountInput.vue'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'
import F2ReviewChip from '../shared/F2ReviewChip.vue'
import {
  buildF2SoeSubTableData,
  buildF2SyncPayload,
} from '../../composables/f2DisclosureSyncPayload'
import { F2_NOTE_SECTION } from '../../composables/f2NoteSectionMap'
import type { ChecklistResponse } from '../../composables/useF2FormData'
import GtIndexChip from '../../GtIndexChip.vue'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  applicableStandards: string[]
}>()

const displayPrefs = useDisplayPrefsStore()

/** 只读金额统一走平台单一真源，响应顶栏「显示设置」的单位与小数位 */
function fmtAmount(v: number | null | undefined): string {
  return displayPrefs.fmtAmount(v)
}

/** (5) 数据资源表：段标题行加浅底强调 */
function drRowClass({ row }: { row: { kind: string } }): string {
  return row.kind === 'section' ? 'dr-section-row' : ''
}

const {
  isApplicable,
  section1Rows, section1Total,
  section2Rows, section2Total,
  drRows, drIsEmpty, drTieFailures,
  noteCategory, s3BorrowText, s4AmortText, noteText, landNote,
  dataUpdatedVisible,
  isManualClassRow, updateS1Field,
  updateS2Field,
  updateDrCell,
  getSyncSnapshot,
} = useF2DisclosureSoe({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  applicableStandards: toRef(props, 'applicableStandards') as Ref<string[]>,
})

const isSyncing = ref(false)
const noteSectionId = F2_NOTE_SECTION.soe

/** 多区块导入后重载 allResponses（由 WorkpaperEditor 提供） */
const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
async function onImported(): Promise<void> {
  await reloadWorkpaperData?.()
}

// ─── AI 辅助（每个文本域一个 section，键与同步 _note_texts 同名）───
const wpIdRef = toRef(() => props.wpId || '') as Ref<string>
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2AiGenerate(wpIdRef)
const aiActiveSection = ref<F2AiSection | ''>('')

/** 传给 AI 的上下文：合计口径 + 勾稽状态，避免模型凭空编数 */
function aiContext(): Record<string, unknown> {
  return {
    noteSection: noteSectionId,
    endGrossTotal: section1Total.value.endGross,
    endImpairmentTotal: section1Total.value.endImpairment,
    endNetTotal: section1Total.value.endNet,
    impairmentTieDiff: section2Total.value.tieDiff,
    dataResourceTieFailures: drTieFailures.value.length,
  }
}

/** 模板里 ref 自动解包，故由此表在 script 作用域内回写 */
const AI_TARGETS: Record<string, { target: Ref<string>; title: string }> = {
  'soe-note-category': { target: noteCategory, title: 'AI 生成 · 存货分类说明' },
  'soe-note-land': { target: landNote, title: 'AI 生成 · 土地储备说明' },
  'soe-note-borrow': { target: s3BorrowText, title: 'AI 生成 · 借款费用资本化说明' },
  'soe-note-amort': { target: s4AmortText, title: 'AI 生成 · 合同履约成本摊销说明' },
  'soe-note': { target: noteText, title: 'AI 生成 · 其他附注说明' },
}

async function runAi(section: F2AiSection): Promise<void> {
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

// 保存后自动同步到附注（防抖/非阻塞/失败静默/只读 gate；与手动按钮同源 syncToDisclosureNotes）
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
onBeforeUnmount(() => autoSync.cancelPending())

// 🔴 触发条件必须监听**实际数据**，不能只监听提示横幅（详见上市 Tab 同位注释）：
// `dataUpdatedVisible` 只表示「上游 F2-1 数据已更新」的横幅可见性，用户改跌价准备变动 /
// 数据资源 / 5 个文本域都不会触发。`section1Rows` 已覆盖上游变化场景。
// 🔴 不加 mounted 一次性防护（会吞掉「切走再切回后的第一次编辑」，详见上市 Tab 同位注释）。
watch(
  [
    section1Rows, section2Rows, drRows,
    noteCategory, s3BorrowText, s4AmortText, noteText, landNote,
  ],
  () => { autoSync.scheduleAutoSync(syncToDisclosureNotes) },
  { deep: true },
)

const router = useRouter()
// 跳转回附注模块（披露表 → 附注为单向推送；此处仅导航，方便相互编辑确认）
function jumpToNote(target: DisclosureVariant): void {
  const route = buildNoteJumpRoute(props.projectId || '', 'F2', target)
  if (!route) { ElMessage.warning('未找到对应的附注章节'); return }
  router.push(route)
}

async function syncToDisclosureNotes(): Promise<void> {
  if (isSyncing.value || !props.projectId || props.isReadonly) return
  const payload = buildF2SyncPayload(
    'soe',
    props.wpId,
    props.applicableStandards,
    buildF2SoeSubTableData(getSyncSnapshot()),
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
    ElMessage.success(`已同步 ${Number(data?.rows_synced ?? 0)} 行到附注模块「${noteSectionId} 存货」`)
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}
</script>

<template>
  <div class="f2-disclosure-soe">
    <el-alert v-if="!isApplicable" type="info" title="当前项目不适用国企附注披露格式" :closable="false" show-icon />

    <template v-else>
      <details class="guidance-details">
        <summary>📋 编制提示</summary>
        <div class="guidance-content">
          <p>1. （1）存货分类：账面余额/跌价准备/账面价值 × 期末与期初，自 F2-1 跨 sheet 取数；「其中」行不计入合计。</p>
          <p>2. 原材料=材料+在途；自制半成品及在产品含开发成本；库存商品含开发产品。</p>
          <p>3. （2）跌价变动：期末=期初+计提+其他−转回−转销−其他，应与（1）期末跌价勾稽。</p>
          <p>4. （3）借款费用资本化 /（4）合同履约成本本期摊销：文字披露，说明金额与计算标准。</p>
          <p>5. （5）确认为存货的数据资源：三段式（账面原值/跌价准备/账面价值），期末与账面价值为公式；仅在确认数据资源时填列。</p>
          <p>6. 可「同步到附注」推送至附注模块「{{ noteSectionId }} 存货」。</p>
        </div>
      </details>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="objective-alert"
        title="审计目标：核实国有企业存货附注披露的分类、账面价值与跌价准备完整准确，确保与 F2-1 及主管部门列报要求一致。"
      />

      <div class="tab-toolbar">
        <div class="toolbar-left">
          <el-button size="small" type="primary" plain :loading="isSyncing" :disabled="isReadonly" @click="syncToDisclosureNotes">
            同步到附注
          </el-button>
          <el-button size="small" type="primary" plain :disabled="!projectId" @click="jumpToNote('soe')">↩ 跳转回附注</el-button>
          <!-- 多区块导入导出：一区块一 sheet + 文本域集中「文本说明」sheet（后端 _f2_disclosure_import_export） -->
          <CycleImportExportDropdown
            :wp-id="props.wpId"
            api-prefix="f2"
            sheet="F2-note-soe"
            :disabled="isReadonly"
            @imported="onImported"
          />
          <F2ReviewChip section-id="F2-note-soe" />
        </div>
        <div class="toolbar-right">
          <el-tag size="small">单位：{{ displayPrefs.unitSuffix }}</el-tag>
          <span class="chip-wrap"><GtIndexChip value="wp:F2-1" :context-project-id="projectId" /></span>
          <span class="chip-wrap"><GtIndexChip :value="`Note:${noteSectionId}`" :context-project-id="projectId" /></span>
        </div>
      </div>

      <el-alert
        v-if="dataUpdatedVisible"
        type="info"
        title="审定表数据已更新，附注分类/跌价变动已自动刷新"
        :closable="false"
        show-icon
        class="update-bar"
      />

      <!-- (1) 存货分类 -->
      <div class="disclosure-card">
        <h4 class="card-title">
          (1) 存货分类
          <el-tooltip content="数据来源：F2-1 审定表；「其中」行不计入合计" placement="top">
            <el-tag size="small" type="info">跨sheet取数</el-tag>
          </el-tooltip>
          <GtIndexChip value="wp:F2-1" :context-project-id="projectId" />
        </h4>
        <el-table :data="[...section1Rows, section1Total]" size="small" border stripe style="width:100%" row-class-name="soe-row">
          <el-table-column prop="label" label="项目" min-width="220" fixed>
            <template #default="{ row }">
              <span
                :class="{
                  'subtotal-label': row.rowKey === '__total__',
                  'detail-label': row.kind === 'detail',
                }"
              >{{ row.label }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末数" align="center">
            <el-table-column label="账面余额" min-width="120" align="right">
              <template #default="{ row }">
                <WpAmountInput
                  v-if="isManualClassRow(row.rowKey)"
                  :model-value="row.endGross"
                  :disabled="isReadonly"
                  :aria-label="`${row.label} 期末账面余额`"
                  @change="(v: number) => updateS1Field(row.rowKey, 'endGross', v)"
                />
                <span v-else class="cross-sheet-cell">{{ fmtAmount(row.endGross) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="跌价准备/合同履约成本减值准备" min-width="150" align="right">
              <template #default="{ row }">
                <WpAmountInput
                  v-if="isManualClassRow(row.rowKey)"
                  :model-value="row.endImpairment"
                  :disabled="isReadonly"
                  :aria-label="`${row.label} 期末跌价准备`"
                  @change="(v: number) => updateS1Field(row.rowKey, 'endImpairment', v)"
                />
                <span v-else class="cross-sheet-cell">{{ fmtAmount(row.endImpairment) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="账面价值" min-width="120" align="right">
              <template #default="{ row }">
                <span class="cross-sheet-cell">{{ fmtAmount(row.endNet) }}</span>
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="期初数" align="center">
            <el-table-column label="账面余额" min-width="120" align="right">
              <template #default="{ row }">
                <WpAmountInput
                  v-if="isManualClassRow(row.rowKey)"
                  :model-value="row.priorGross"
                  :disabled="isReadonly"
                  :aria-label="`${row.label} 期初账面余额`"
                  @change="(v: number) => updateS1Field(row.rowKey, 'priorGross', v)"
                />
                <span v-else class="cross-sheet-cell">{{ fmtAmount(row.priorGross) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="跌价准备/合同履约成本减值准备" min-width="150" align="right">
              <template #default="{ row }">
                <WpAmountInput
                  v-if="isManualClassRow(row.rowKey)"
                  :model-value="row.priorImpairment"
                  :disabled="isReadonly"
                  :aria-label="`${row.label} 期初跌价准备`"
                  @change="(v: number) => updateS1Field(row.rowKey, 'priorImpairment', v)"
                />
                <span v-else class="cross-sheet-cell">{{ fmtAmount(row.priorImpairment) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="账面价值" min-width="120" align="right">
              <template #default="{ row }">
                <span class="cross-sheet-cell">{{ fmtAmount(row.priorNet) }}</span>
              </template>
            </el-table-column>
          </el-table-column>
        </el-table>
        <p class="hint-text">
          注：房地产开发企业应在「其他」中披露土地储备的面积、本期增加及期末余额等情况。
          「其他」与「其中：尚未开发的土地储备」两行无对应存货科目，账面余额与跌价准备可手工录入；
          「数据资源」行自 (5) 数据资源表联动；其余行自 F2-1 审定表跨表取数（只读）。
          账面价值恒为「账面余额 − 跌价准备」派生值。
        </p>
        <div class="note-block">
          <div class="note-label">
            <span>土地储备说明</span>
            <el-button
              class="ai-btn" size="small" type="primary" plain
              :disabled="isReadonly || !aiAvailable"
              :loading="aiLoading && aiActiveSection === 'soe-note-land'"
              @click="runAi('soe-note-land')"
            >🤖 AI 辅助</el-button>
          </div>
          <el-input v-model="landNote" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" :disabled="isReadonly" placeholder="土地储备面积、本期增加及期末余额..." />
          <div class="note-label mt-8">
            <span>存货分类补充说明</span>
            <el-button
              class="ai-btn" size="small" type="primary" plain
              :disabled="isReadonly || !aiAvailable"
              :loading="aiLoading && aiActiveSection === 'soe-note-category'"
              @click="runAi('soe-note-category')"
            >🤖 AI 辅助</el-button>
          </div>
          <el-input v-model="noteCategory" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" :disabled="isReadonly" placeholder="存货分类补充说明..." />
        </div>
      </div>

      <!-- (2) 跌价准备变动 -->
      <div class="disclosure-card">
        <h4 class="card-title">
          (2) 存货跌价准备及合同履约成本减值准备
          <el-tooltip content="期初/计提默认取自 F2-1；期末公式勾稽（1）期末跌价" placement="top">
            <el-tag size="small" type="info">跨sheet取数</el-tag>
          </el-tooltip>
        </h4>
        <el-alert
          v-if="Math.abs(section2Total.tieDiff) >= 0.01"
          type="warning"
          :closable="false"
          show-icon
          class="tie-alert"
          :title="`跌价准备合计勾稽差异 ${fmtAmount(section2Total.tieDiff)}（变动表期末 − 分类表期末跌价）`"
        />
        <el-table :data="[...section2Rows, section2Total]" size="small" border stripe style="width:100%">
          <el-table-column prop="label" label="存货种类" min-width="200" fixed>
            <template #default="{ row }">
              <span
                :class="{
                  'subtotal-label': row.rowKey === '__total__',
                  'detail-label': row.kind === 'detail',
                }"
              >{{ row.label }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期初数" min-width="100" align="right">
            <template #default="{ row }">
              <span class="cross-sheet-cell">{{ fmtAmount(row.opening) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期增加" align="center">
            <el-table-column label="计提" min-width="100" align="right">
              <template #default="{ row }">
                <span v-if="row.rowKey === '__total__'" class="subtotal-label">{{ fmtAmount(row.incProvision) }}</span>
                <el-input-number
                  v-else
                  :model-value="row.incProvision"
                  :controls="false"
                  :precision="2"
                  size="small"
                  :disabled="isReadonly"
                  style="width:100%"
                  @change="(v: number | undefined) => updateS2Field(row.rowKey, 'incProvision', v ?? 0)"
                />
              </template>
            </el-table-column>
            <el-table-column label="其他" min-width="90" align="right">
              <template #default="{ row }">
                <span v-if="row.rowKey === '__total__'" class="subtotal-label">{{ fmtAmount(row.incOther) }}</span>
                <el-input-number
                  v-else
                  :model-value="row.incOther"
                  :controls="false"
                  :precision="2"
                  size="small"
                  :disabled="isReadonly"
                  style="width:100%"
                  @change="(v: number | undefined) => updateS2Field(row.rowKey, 'incOther', v ?? 0)"
                />
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="本期减少" align="center">
            <el-table-column label="转回" min-width="90" align="right">
              <template #default="{ row }">
                <span v-if="row.rowKey === '__total__'" class="subtotal-label">{{ fmtAmount(row.decReversal) }}</span>
                <el-input-number
                  v-else
                  :model-value="row.decReversal"
                  :controls="false"
                  :precision="2"
                  size="small"
                  :disabled="isReadonly"
                  style="width:100%"
                  @change="(v: number | undefined) => updateS2Field(row.rowKey, 'decReversal', v ?? 0)"
                />
              </template>
            </el-table-column>
            <el-table-column label="转销" min-width="90" align="right">
              <template #default="{ row }">
                <span v-if="row.rowKey === '__total__'" class="subtotal-label">{{ fmtAmount(row.decWriteOff) }}</span>
                <el-input-number
                  v-else
                  :model-value="row.decWriteOff"
                  :controls="false"
                  :precision="2"
                  size="small"
                  :disabled="isReadonly"
                  style="width:100%"
                  @change="(v: number | undefined) => updateS2Field(row.rowKey, 'decWriteOff', v ?? 0)"
                />
              </template>
            </el-table-column>
            <el-table-column label="其他" min-width="90" align="right">
              <template #default="{ row }">
                <span v-if="row.rowKey === '__total__'" class="subtotal-label">{{ fmtAmount(row.decOther) }}</span>
                <el-input-number
                  v-else
                  :model-value="row.decOther"
                  :controls="false"
                  :precision="2"
                  size="small"
                  :disabled="isReadonly"
                  style="width:100%"
                  @change="(v: number | undefined) => updateS2Field(row.rowKey, 'decOther', v ?? 0)"
                />
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="期末数" min-width="100" align="right">
            <template #default="{ row }">
              <span :class="{ 'tie-warn': Math.abs(row.tieDiff) >= 0.01, 'subtotal-label': row.rowKey === '__total__' }">
                {{ fmtAmount(row.ending) }}
              </span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- (3) 借款费用资本化 -->
      <div class="disclosure-card">
        <h4 class="card-title">
          (3) 借款费用资本化
          <el-button
            class="ai-btn" size="small" type="primary" plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading && aiActiveSection === 'soe-note-borrow'"
            @click="runAi('soe-note-borrow')"
          >🤖 AI 辅助</el-button>
        </h4>
        <el-input
          v-model="s3BorrowText"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 5 }"
          :disabled="isReadonly"
          placeholder="存货期末余额中含有借款费用资本化金额为XXX元。计算标准和依据..."
        />
      </div>

      <!-- (4) 合同履约成本摊销 -->
      <div class="disclosure-card">
        <h4 class="card-title">
          (4) 合同履约成本本期摊销金额的说明
          <el-button
            class="ai-btn" size="small" type="primary" plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading && aiActiveSection === 'soe-note-amort'"
            @click="runAi('soe-note-amort')"
          >🤖 AI 辅助</el-button>
        </h4>
        <el-input
          v-model="s4AmortText"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 5 }"
          :disabled="isReadonly"
          placeholder="说明合同履约成本本期摊销金额..."
        />
      </div>

      <!-- (5) 确认为存货的数据资源 -->
      <div class="disclosure-card">
        <h4 class="card-title">
          (5) 确认为存货的数据资源
          <el-tooltip content="期末余额 / 账面价值 / 合计列为公式，按《企业数据资源相关会计处理暂行规定》三段式披露" placement="top">
            <el-tag size="small" type="info">公式联动</el-tag>
          </el-tooltip>
        </h4>
        <el-alert
          v-if="drIsEmpty"
          type="info"
          :closable="false"
          show-icon
          class="dr-empty-alert"
          title="本表仅在存货中确认数据资源时填列；（1）分类表「数据资源」行为 0 时可不填。"
        />
        <el-alert
          v-for="chk in drTieFailures"
          :key="chk.key"
          type="warning"
          :closable="false"
          show-icon
          class="dr-empty-alert"
          :title="`勾稽差异 ${fmtAmount(chk.diff)}：${chk.label} 本表合计 ${fmtAmount(chk.detail)} ≠ （1）分类表「数据资源」行 ${fmtAmount(chk.classified)}（${chk.preset}）`"
        />
        <el-table :data="drRows" size="small" border stripe style="width:100%" :row-class-name="drRowClass">
          <el-table-column label="项目" min-width="180" fixed>
            <template #default="{ row }">
              <span :class="{ 'dr-section': row.kind === 'section', 'dr-sub': row.indent === 1 }">{{ row.label }}</span>
              <el-tooltip v-if="row.subExcess" content="「其中」子项之和已超过本行金额，请复核" placement="top">
                <span class="tie-warn dr-warn-flag">⚠</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column
            v-for="col in DR_INPUT_COLS"
            :key="col"
            :label="DR_COL_LABELS[col]"
            min-width="150"
            align="right"
          >
            <template #default="{ row }">
              <span v-if="row.kind === 'section'" />
              <span v-else-if="row.kind === 'derived'" class="cross-sheet-cell">{{ fmtAmount(row[col]) }}</span>
              <WpAmountInput
                v-else
                :model-value="row[col]"
                :disabled="isReadonly"
                :aria-label="`${DR_COL_LABELS[col]} ${row.label}`"
                @change="(v: number) => updateDrCell(row.rowKey, col, v)"
              />
            </template>
          </el-table-column>
          <el-table-column min-width="140" align="right">
            <template #header>
              <el-tooltip content="合计 = 外购 + 自行加工 + 其他方式取得（源模板校验 F9-11）" placement="top">
                <span class="formula-header">合计</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span v-if="row.kind === 'section'" />
              <span v-else class="cross-sheet-cell">{{ fmtAmount(row.total) }}</span>
            </template>
          </el-table-column>
        </el-table>
        <p class="hint-text">
          4.期末余额＝1.期初余额＋2.本期增加金额−3.本期减少金额；期末/期初账面价值＝账面原值−跌价准备。
          「其中」子项为部分列示，独立录入，其之和不应超过所属小节金额。
        </p>
        <p class="hint-text">
          上述信息若已在会计政策、其他项目附注中披露，可索引至相关内容。
        </p>
      </div>

      <div class="disclosure-card">
        <h4 class="card-title">
          其他附注说明
          <el-button
            class="ai-btn" size="small" type="primary" plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading && aiActiveSection === 'soe-note'"
            @click="runAi('soe-note')"
          >🤖 AI 辅助</el-button>
        </h4>
        <el-input
          v-model="noteText"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          :disabled="isReadonly"
          placeholder="其他应披露事项..."
        />
      </div>
    </template>
  </div>
</template>

<style scoped>
.f2-disclosure-soe { padding: 12px; font-size: var(--wp-font-size, 13px); }
.f2-disclosure-soe :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f2-disclosure-soe :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.update-bar, .tie-alert { margin-bottom: 12px; }
.disclosure-card { margin-bottom: 24px; }
.card-title { margin: 0 0 10px; font-size: 14px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.subtotal-label { font-weight: 600; }
.detail-label { color: #606266; padding-left: 12px; }
.cross-sheet-cell { color: #409eff; }
.tie-warn { color: #e6a23c; font-weight: 600; }
.hint-text { margin: 8px 0; font-size: 12px; color: #909399; line-height: 1.5; }
.note-block { margin-top: 10px; }
/* 文本域标题行：AI 辅助按钮右对齐在同一行（平台底稿 UI 规范） */
.note-label {
  font-size: 12px;
  color: #606266;
  margin-bottom: 4px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.ai-btn { margin-left: auto; }
.mt-8 { margin-top: 8px; }
/* 公式列表头：虚线下划线 + tooltip 标注取数来源（平台表格 UI 规范） */
.formula-header { border-bottom: 1px dashed var(--el-color-primary); cursor: help; }
/* (5) 数据资源表 */
.dr-empty-alert { margin-bottom: 10px; }
.dr-section { font-weight: 600; }
.dr-sub { padding-left: 16px; color: #606266; }
.dr-warn-flag { margin-left: 4px; cursor: help; }
.f2-disclosure-soe :deep(.dr-section-row) { background: #f5f7fa; }
</style>
