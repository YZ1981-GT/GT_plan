<template>
  <div class="n1-tab-disclosure-soe">
    <!-- ═══ 标题 + 同步/跳转/AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">{{ N1_DISCLOSURE_SHEET_NAME.soe }}</h3>
        <el-tag type="success" size="small">国企 5 张披露表</el-tag>
      </div>
      <div class="section-header-right">
        <el-button
          size="small"
          type="success"
          class="sync-btn"
          :loading="syncing"
          @click="syncToDisclosureNotes"
        >
          同步到附注（{{ N1_NOTE_SECTION.soe }}）
        </el-button>
        <el-dropdown split-button size="small" type="primary" @click="jumpToNote('soe')">
          ↩ 跳转回附注（{{ N1_NOTE_SECTION.soe }}）
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="jumpToNote('soe')">国企版（{{ N1_NOTE_SECTION.soe }}）</el-dropdown-item>
              <el-dropdown-item @click="jumpToNote('listed')">上市版（{{ N1_NOTE_SECTION.listed }}）</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" :loading="aiLoading" @click="handleAI('conclusion')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <GtReviewTrigger :section-id="`N1-附注国企-${N1_NOTE_SECTION.soe}`" label="💬 复核" />
      </div>
    </div>

    <!-- ═══ 前置披露口径（源模板 R7 原文）═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>披露口径分支（源模板 R7）：</strong>{{ BRANCH_RULE }}
      </div>
      <div class="methodology-text methodology-sub">
        本页 5 张表逐字对齐源模板 <code>附注披露信息（国企）</code>：
        （1）A、已确认递延所得税资产和递延所得税负债；
        （2）A、互抵后的递延所得税资产或负债及对应的互抵后可抵扣或应纳税暂时性差异；
        （2）B、递延所得税资产和递延所得税负债互抵明细；
        （3）未确认递延所得税资产明细；
        （4）未确认递延所得税资产的可抵扣亏损将于以下年度到期。
        <strong>注意国企表（1）子列序与上市相反</strong>：「递延所得税资产/负债」在前、「可抵扣/应纳税暂时性差异」在后。
      </div>
    </div>

    <!-- ═══ 披露内部勾稽 ═══ -->
    <N1DisclosureConsistencyPanel
      :results="tables.checks.value"
      :project-id="props.projectId"
      :default-expanded="hasCheckError"
    />

    <!-- ═══（1）不以抵销后净额列示 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>（1）递延所得税资产和递延所得税负债不以抵销后的净额列示 —— A、已确认递延所得税资产和递延所得税负债</span>
          <el-button size="small" :loading="aiLoading" @click="handleAI('unoffset')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <N1DisclosureSegmentTable
        label-header="项  目"
        :columns="unoffsetColumns"
        :segments="tables.unoffsetSegments.value"
        :readonly="isReadonly"
        @change-cell="onUnoffsetCell"
        @change-label="onUnoffsetLabel"
        @add-row="tables.addUnoffsetRow"
        @remove-row="onUnoffsetRemove"
      />
      <div class="source-hint">
        <div v-for="(t, i) in UNOFFSET_HINTS" :key="i">{{ t }}</div>
      </div>
    </el-card>

    <!-- ═══（2）A 以抵销后净额列示 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>（2）递延所得税资产和递延所得税负债以抵销后的净额列示 —— A、互抵后的递延所得税资产或负债及对应的互抵后可抵扣或应纳税暂时性差异</span>
          <el-button size="small" :loading="aiLoading" @click="handleAI('netoffset')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <N1DisclosureSegmentTable
        label-header="项  目"
        :columns="netOffsetColumns"
        :segments="tables.netOffsetSegmentsSoe.value"
        :readonly="isReadonly"
        @change-cell="onNetOffsetCell"
        @change-label="onNetOffsetLabel"
        @add-row="tables.addNetOffsetRow"
        @remove-row="onNetOffsetRemove"
      />
    </el-card>

    <!-- ═══（2）B 互抵明细 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>（2）B、递延所得税资产和递延所得税负债互抵明细</span>
          <el-button size="small" :loading="aiLoading" @click="handleAI('offsetdetail')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <N1DisclosureSegmentTable
        label-header="项  目"
        :columns="offsetDetailColumns"
        :segments="tables.offsetDetailSegments.value"
        :readonly="isReadonly"
        @change-cell="onOffsetDetailCell"
        @change-label="onOffsetDetailLabel"
        @add-row="tables.addOffsetDetailRow"
        @remove-row="onOffsetDetailRemove"
      />
      <div class="source-hint">
        <div>{{ OFFSET_DETAIL_HINT }}</div>
      </div>
    </el-card>

    <!-- ═══（3）未确认递延所得税资产明细 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>（3）未确认递延所得税资产明细</span>
          <el-button size="small" :loading="aiLoading" @click="handleAI('unrecognized')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-alert
        v-if="!tables.lossPayload.value.hasData"
        type="info"
        :closable="false"
        show-icon
        class="pending-alert"
      >
        <template #title>「可抵扣亏损」行待 N1-5 编制</template>
        <template v-if="tables.lossPayload.value.isLegacyEstimate" #default>
          检测到旧版 N1-5 数据（推算值，非审计师确认／不确认录入），请完成 N1-5 新模型编制后刷新。
        </template>
      </el-alert>
      <N1DisclosureSegmentTable
        label-header="项  目"
        :columns="unrecognizedColumns"
        :segments="tables.unrecognizedSegments.value"
        :readonly="isReadonly"
        :allow-add-row="false"
        @change-cell="onUnrecognizedCell"
      />
      <div class="source-hint">
        <div>{{ UNRECOGNIZED_NOTE }}</div>
      </div>
    </el-card>

    <!-- ═══（4）可抵扣亏损到期年度 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>（4）未确认递延所得税资产的可抵扣亏损将于以下年度到期</span>
          <el-button size="small" :loading="aiLoading" @click="handleAI('lossexpiry')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <N1DisclosureSegmentTable
        label-header="年  份"
        :columns="lossExpiryColumns"
        :segments="tables.lossExpirySegments.value"
        :readonly="isReadonly"
        @change-cell="onLossExpiryCell"
        @change-label="onLossExpiryLabel"
        @add-row="tables.addLossExpiryRow"
        @remove-row="onLossExpiryRemove"
      />
      <div class="source-hint">
        <div>{{ LOSS_EXPIRY_NOTE }}</div>
      </div>
    </el-card>

    <!-- ═══ 披露说明与结论 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>披露说明与结论</span>
          <el-button size="small" :loading="aiLoading" @click="handleAI('conclusion')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="tables.conclusionNote.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="说明递延所得税资产确认依据、未确认部分原因、抵销与列示口径及与底稿的勾稽结论..."
        @change="onConclusionChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="n1-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>本页 5 张表逐字对齐致同源模板 <code>附注披露信息（国企）</code>，是附注 {{ N1_NOTE_SECTION.soe }} 的交付物源</li>
        <li>不以抵销后净额列示按（1）披露；以抵销后净额列示按（2）披露 —— 两者择一，另一张按源模板可删除</li>
        <li>表（1）两级表头：期末余额 / 年初余额，子列序为「递延所得税资产/负债」→「可抵扣/应纳税暂时性差异」（与上市相反）</li>
        <li>负债段第 4 项国企为「租赁形成」（上市为「使用权资产」），不要互相套用</li>
        <li>表（1）（2）各段小计 = 段内各项之和（源模板 =SUM(B13:B19) / =SUM(B36:B43) / =SUM(B46:B51)）</li>
        <li>表（3）「可抵扣亏损」行与表（4）合计必须相等（源模板 B72=B62 / C72=C62），由勾稽面板实时校验</li>
        <li>表（4）默认列示审计年度后 5 年；高新 / 科技型中小企业为 10 年，用「+ 新增行」补足</li>
        <li>审计过程（账面价值 / 计税基础 / 适用税率 / 确认依据）在 N1-2 明细表与 N1-4 测算表，不在披露表列示</li>
        <li>编辑后自动同步到附注（防抖 800ms），也可点「同步到附注」立即推送</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N1TabDisclosureSoe — 递延所得税资产附注披露（国企）
 *
 * Spec: `.kiro/specs/n1-deferred-tax-disclosure-template-alignment/`（R2 / R3 / R5）
 *
 * 结构逐字对齐源模板 `N1 递延所得税资产.xlsx` 的 `附注披露信息（国企）`（A1:IV74）：
 * 5 张表（比上市多一张（2）B 互抵明细）+ R7 前置口径 + R30/R31/R73 只读提示 + R74 跨表勾稽。
 *
 * 🔴 本组件此前是 6 个自造 section（把 N1-2 的账面价值/计税基础/确认依据等审计过程列
 * 当成披露内容，且缺（2）A/（2）B 两张表）→ 已按源模板重建。
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
// @ts-ignore
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
import { useAuditContext } from '@/composables/useAuditContext'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import { useN1FormData } from '../../composables/useN1FormData'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { N1_DISCLOSURE_SHEET_NAME, N1_NOTE_SECTION } from '../../composables/n1NoteSectionMap'
import { dataTableNames, serializeSyncedTableNames } from '../../composables/disclosureSyncedTables'
import {
  n1LossExpirySegColumns,
  n1NetOffsetSegColumnsSoe,
  n1OffsetDetailSegColumns,
  n1UnoffsetSegColumns,
  n1UnrecognizedSegColumns,
  useN1DisclosureTables,
} from '../../composables/useN1DisclosureTables'
import { generateN1Text } from '../../composables/useN1AiText'
import N1DisclosureSegmentTable from '../shared/N1DisclosureSegmentTable.vue'
import N1DisclosureConsistencyPanel from '../shared/N1DisclosureConsistencyPanel.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  year?: number
}>()

defineEmits<{ (e: 'navigate', sheetName: string): void }>()

// ─── 源模板只读文案（含中文引号，故只放 script 常量，不进模板属性）───────────

const BRANCH_RULE =
  '递延所得税资产和递延所得税负债不以抵销后的净额列示的，按（1）披露；'
  + '若递延所得税资产和递延所得税负债以抵销后的净额列示的，按（2）披露。'

const UNOFFSET_HINTS = [
  '【提示：资产减值准备，含“持有待售资产减值准备”】',
  '【注：计入其他综合收益的其他金融资产为计入其他综合收益的其他债权投资、其他权益工具投资。】',
  '源模板红字：递延所得税负债数据来源于递延所得税负债底稿。',
]

const OFFSET_DETAIL_HINT =
  '源模板（2）B：按项目列示本期互抵金额；仅在以抵销后净额列示时填列。'

const UNRECOGNIZED_NOTE =
  '列示由于未来能否获得足够的应纳税所得额具有不确定性，因此没有确认为递延所得税资产的可抵扣暂时性差异和可抵扣亏损。'

const LOSS_EXPIRY_NOTE =
  '【注：无法在资产负债表日确定全部可抵扣亏损情况的，可只填写能确定部分的金额及其到期年度，并在备注栏予以说明。】'

// ─── 上下文 ──────────────────────────────────────────────────────────────────

const router = useRouter()
const auditCtx = useAuditContext()
const isReadonly = computed(() => props.isReadonly ?? false)
const syncing = ref(false)
const aiLoading = ref(false)

const syncYear = computed(() => props.year || auditCtx.year.value || new Date().getFullYear())

const formData = useN1FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const tables = useN1DisclosureTables({
  variant: 'soe',
  allResponses: formData.allResponses,
  auditYear: syncYear,
})

const autoSync = useDisclosureAutoSync({ isReadonly: () => isReadonly.value })

const unoffsetColumns = computed(() => n1UnoffsetSegColumns('soe'))
const netOffsetColumns = computed(() => n1NetOffsetSegColumnsSoe())
const offsetDetailColumns = computed(() => n1OffsetDetailSegColumns())
const unrecognizedColumns = computed(() => n1UnrecognizedSegColumns('soe'))
const lossExpiryColumns = computed(() => n1LossExpirySegColumns('soe'))

const hasCheckError = computed(() => tables.checks.value.some((c) => c.level === 'error'))

// ─── 持久化（整表 JSON，一表一 item）────────────────────────────────────────

function persistUnoffset(): void {
  formData.debouncedSave(tables.itemIds.unoffset, {
    conclusion: JSON.stringify({
      asset: tables.assetRows.value,
      liability: tables.liabilityRows.value,
    }),
  })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function persistNetOffset(): void {
  formData.debouncedSave(tables.itemIds.netOffset, {
    conclusion: JSON.stringify({
      asset: tables.netOffsetAssetRows.value,
      liability: tables.netOffsetLiabilityRows.value,
    }),
  })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function persistOffsetDetail(): void {
  formData.debouncedSave(tables.itemIds.offsetDetail, {
    conclusion: JSON.stringify(tables.offsetDetailRows.value),
  })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function persistUnrecognized(): void {
  formData.debouncedSave(tables.itemIds.unrecognized, {
    conclusion: JSON.stringify(tables.unrecognizedRows.value),
  })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function persistLossExpiry(): void {
  formData.debouncedSave(tables.itemIds.lossExpiry, {
    conclusion: JSON.stringify(tables.lossExpiryRows.value),
  })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

// ─── 单元格 / 行名变更 ───────────────────────────────────────────────────────

type CellPayload = { seg: string; index: number; key: string; value: number | string }
type LabelPayload = { seg: string; index: number; value: string }

function onUnoffsetCell(p: CellPayload): void {
  const target = p.seg === 'asset' ? tables.assetRows : tables.liabilityRows
  const row = target.value[p.index]
  if (!row) return
  ;(row as Record<string, unknown>)[p.key] = p.value
  persistUnoffset()
}

function onUnoffsetLabel(p: LabelPayload): void {
  const target = p.seg === 'asset' ? tables.assetRows : tables.liabilityRows
  const row = target.value[p.index]
  if (!row) return
  row.item = p.value
  persistUnoffset()
}

function onUnoffsetRemove(p: { seg: string; index: number }): void {
  const target = p.seg === 'asset' ? tables.assetRows : tables.liabilityRows
  target.value = target.value.filter((_, i) => i !== p.index)
  persistUnoffset()
}

function onNetOffsetCell(p: CellPayload): void {
  const target = p.seg === 'asset' ? tables.netOffsetAssetRows : tables.netOffsetLiabilityRows
  const row = target.value[p.index]
  if (!row) return
  ;(row as Record<string, unknown>)[p.key] = p.value
  persistNetOffset()
}

function onNetOffsetLabel(p: LabelPayload): void {
  const target = p.seg === 'asset' ? tables.netOffsetAssetRows : tables.netOffsetLiabilityRows
  const row = target.value[p.index]
  if (!row) return
  row.item = p.value
  persistNetOffset()
}

function onNetOffsetRemove(p: { seg: string; index: number }): void {
  const target = p.seg === 'asset' ? tables.netOffsetAssetRows : tables.netOffsetLiabilityRows
  target.value = target.value.filter((_, i) => i !== p.index)
  persistNetOffset()
}

function onOffsetDetailCell(p: CellPayload): void {
  const row = tables.offsetDetailRows.value[p.index]
  if (!row) return
  ;(row as Record<string, unknown>)[p.key] = p.value
  persistOffsetDetail()
}

function onOffsetDetailLabel(p: LabelPayload): void {
  const row = tables.offsetDetailRows.value[p.index]
  if (!row) return
  row.item = p.value
  persistOffsetDetail()
}

function onOffsetDetailRemove(p: { seg: string; index: number }): void {
  tables.offsetDetailRows.value = tables.offsetDetailRows.value.filter((_, i) => i !== p.index)
  persistOffsetDetail()
}

function onUnrecognizedCell(p: CellPayload): void {
  const row = tables.unrecognizedRows.value[p.index]
  if (!row) return
  ;(row as Record<string, unknown>)[p.key] = p.value
  persistUnrecognized()
}

function onLossExpiryCell(p: CellPayload): void {
  const row = tables.lossExpiryRows.value[p.index]
  if (!row) return
  ;(row as Record<string, unknown>)[p.key] = p.value
  persistLossExpiry()
}

function onLossExpiryLabel(p: LabelPayload): void {
  const row = tables.lossExpiryRows.value[p.index]
  if (!row) return
  row.item = p.value
  persistLossExpiry()
}

function onLossExpiryRemove(p: { seg: string; index: number }): void {
  tables.lossExpiryRows.value = tables.lossExpiryRows.value.filter((_, i) => i !== p.index)
  persistLossExpiry()
}

function onConclusionChange(): void {
  formData.debouncedSave(tables.itemIds.conclusion, {
    remark: tables.conclusionNote.value || null,
  })
  emitNoteUpdated('conclusion-soe', tables.conclusionNote.value)
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

// ─── 附注事件 ────────────────────────────────────────────────────────────────

function emitNoteUpdated(section: string, text?: string): void {
  eventBus.emit('disclosure:note-text-updated', {
    wpCode: 'N1',
    section,
    accountCode: '1811',
    projectId: props.projectId,
    sectionIds: [N1_NOTE_SECTION.soe],
    ...(text !== undefined ? { text } : {}),
    timestamp: Date.now(),
  } as any)
}

// ─── 同步到附注 ──────────────────────────────────────────────────────────────

async function syncToDisclosureNotes(): Promise<void> {
  if (!props.projectId) {
    ElMessage.warning('缺少项目上下文，无法同步')
    return
  }
  syncing.value = true
  try {
    const payload = tables.buildPayload({ wpId: props.wpId, year: syncYear.value })
    const resp: any = await http.post(
      `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
      payload,
    )
    const data = resp?.data?.data ?? resp?.data
    if (data?.success) {
      ElMessage.success(
        `已${data.created ? '新建' : '更新'}附注 ${data.section_id}：${data.rows_synced} 行`
        + (data.texts_synced ? `，正文 ${data.texts_synced} 段` : ''),
      )
      markSynced(dataTableNames(payload.sub_table_data))
      emitNoteUpdated('sync-soe')
    } else {
      ElMessage.error('附注同步返回异常，请重试')
    }
  } catch (err: any) {
    if (err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError' || err?.__CANCEL__) return
    ElMessage.error(`附注同步失败：${err?.response?.data?.detail || err?.message || '未知错误'}`)
  } finally {
    syncing.value = false
  }
}

function markSynced(names: string[]): void {
  tables.syncedTables.value = names
  formData.debouncedSave(tables.itemIds.syncedTables, {
    conclusion: serializeSyncedTableNames(names),
  })
}

function jumpToNote(variant: DisclosureVariant): void {
  const route = buildNoteJumpRoute(props.projectId || '', 'N1', variant, syncYear.value)
  if (!route) {
    ElMessage.warning('缺少项目上下文，无法跳转附注')
    return
  }
  router.push(route)
}

// ─── AI 辅助 ─────────────────────────────────────────────────────────────────

const AI_PROMPTS: Record<string, string> = {
  unoffset:
    '请基于国企版「已确认递延所得税资产和递延所得税负债」（不以抵销后净额列示）表数据'
    + '撰写披露复核建议：资产段与负债段列示是否完整、各段小计与明细是否勾稽、'
    + '资产减值准备是否已含持有待售资产减值准备、'
    + '计入其他综合收益的其他金融资产口径是否按其他债权投资与其他权益工具投资列示。不得虚构数据。',
  netoffset:
    '请就「互抵后的递延所得税资产或负债及对应的互抵后可抵扣或应纳税暂时性差异」给出复核建议：'
    + '是否为同一纳税主体、互抵后金额与不以抵销后净额列示表的勾稽、'
    + '（1）与（2）是否择一披露而非重复披露。不得虚构数据。',
  offsetdetail:
    '请就「递延所得税资产和递延所得税负债互抵明细」给出复核建议：'
    + '本期互抵金额按项目列示是否完整、与互抵后余额表的勾稽关系。不得虚构数据。',
  unrecognized:
    '请撰写未确认递延所得税资产说明：可抵扣暂时性差异与可抵扣亏损未确认的原因'
    + '（未来能否获得足够应纳税所得额的不确定性）、管理层预测依据、与 N1-5 亏损检查表的勾稽。不得虚构数据。',
  lossexpiry:
    '请就未确认递延所得税资产的可抵扣亏损到期年度分布给出披露复核建议：'
    + '到期年度是否完整、合计是否等于未确认明细的「可抵扣亏损」行、'
    + '无法确定全部可抵扣亏损时是否已在备注栏说明。不得虚构数据。',
  conclusion:
    '请撰写国企版递延所得税资产附注披露说明与结论：确认依据、未确认部分原因、'
    + '不以抵销后净额列示与以抵销后净额列示的选择依据、'
    + '与审定表 N1-1 / 明细表 N1-2 / 亏损检查表 N1-5 的勾稽是否一致、披露完整性。不得虚构数据。',
}

async function handleAI(section: string): Promise<void> {
  if (aiLoading.value) return
  aiLoading.value = true
  try {
    const text = await generateN1Text({
      wpId: props.wpId,
      section: `n1-disclosure-soe-${section}`,
      prompt: AI_PROMPTS[section] || AI_PROMPTS.conclusion,
      context: {
        章节: N1_NOTE_SECTION.soe,
        审计年度: String(syncYear.value ?? ''),
        资产段小计期末: String(tables.assetSubtotal.value.endTax ?? ''),
        负债段小计期末: String(tables.liabilitySubtotal.value.endTax ?? ''),
        互抵后资产段小计期末: String(tables.netOffsetAssetSubtotal.value.netEnd ?? ''),
        未确认合计期末: String(tables.unrecognizedTotal.value.end ?? ''),
        亏损到期合计期末: String(tables.lossExpiryTotal.value.end ?? ''),
        勾稽不一致项数: String(tables.checks.value.filter((c) => c.level === 'error').length),
      },
      existingContent: section === 'conclusion' ? tables.conclusionNote.value : '',
    })
    if (!text) return
    if (section === 'conclusion') {
      tables.conclusionNote.value = text
      onConclusionChange()
      ElMessage.success('AI 已生成披露说明与结论')
    } else {
      const { ElMessageBox } = await import('element-plus')
      await ElMessageBox.alert(text, 'AI 披露复核建议', { confirmButtonText: '知道了' }).catch(() => {})
    }
  } finally {
    aiLoading.value = false
  }
}

// ─── 生命周期 ────────────────────────────────────────────────────────────────

function onAdjudicatedRefresh(): void {
  formData.loadData().then(() => {
    tables.restore()
    emitNoteUpdated('auto-refresh-soe')
  })
}

onMounted(async () => {
  await formData.loadData()
  tables.restore()
  eventBus.on('substantive:adjudicated', onAdjudicatedRefresh)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated', onAdjudicatedRefresh)
  autoSync.cancelPending()
})
</script>

<style scoped>
.n1-tab-disclosure-soe { padding: 12px; font-size: var(--wp-font-size, 13px); }

.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }

.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.7; }
.methodology-text strong { color: #b88230; }
.methodology-sub { margin-top: 6px; }

.disclosure-card { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }

.source-hint { margin-top: 10px; padding: 8px 10px; background: #fffbe6; border-left: 3px solid #f7ba2a; border-radius: 0 4px 4px 0; font-size: 12px; color: #8c6d1f; line-height: 1.7; }

.pending-alert { margin-bottom: 12px; }

.n1-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.n1-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.n1-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
