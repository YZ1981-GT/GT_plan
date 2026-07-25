<template>
  <div class="h8-tab-adjudication">
    <details class="compile-hint" open>
      <summary>📋 编制提示（对齐 Excel 使用权资产、累计折旧及减值准备审定表 H8-1）</summary>
      <div class="hint-content">
        <p>1. 四区块：一、原值(1901) → 二、累计折旧(1902) → 三、减值准备(1903) → 四、净额=原值−折旧−减值。</p>
        <p>2. 列组：期初/期末 × 未审·账项调整·审定 + 本期审定与上期审定比较（变动额/率）。审定=未审+账项调整。</p>
        <p>3. 默认分类：房屋及建筑物 / 机器设备 / 运输设备 / 办公设备 / 其他设备；可从 H8-3 回写期末账项调整（1901/1902 按未审权重分摊）。</p>
        <p>4. 变动率≥{{ CHANGE_RATE_THRESHOLD }}% 须在说明(1)解释；说明(2)(3)分别覆盖简化处理与转租；与 TB 差异行核对后回写试算表。</p>
        <p>5.「带入调整」：从集中登记按科目 1901 拉取调整分录，逐笔分配到原值分类行的期末账项调整，带入后审定数自动更新并联动附注。</p>
        <p class="excel-tip">提示：账项调整应与 H8-3 / 调整分录模块勾稽；CAS21 初始计量须与 H9 勾稽（使用权资产=H9+直接费用−激励）。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：核实使用权资产原值、累计折旧及减值准备期初/期末审定数；账项调整与 H8-3 勾稽；净值=原值−折旧−减值；变动分析充分；与 TB/H9 一致后回写试算表。"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button
          size="small"
          type="primary"
          plain
          :loading="adjPull.loading.value"
          @click="openBringInAdjustment"
        >
          <el-icon><Download /></el-icon>带入调整
        </el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          plain
          @click="handleFillH82"
        >
          从 H8-2 按类别带入
        </el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          plain
          :disabled="!canSyncH83"
          @click="handleSyncH83"
        >
          从 H8-3 回写期末账项调整
        </el-button>
        <el-button
          v-if="!isReadonly && significantNetChanges.length"
          size="small"
          plain
          @click="handleSignificantDraft"
        >
          重大变动→说明(1)
        </el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          :loading="writebackLoading"
          @click="handleWriteback"
        >
          审定数回写TB
        </el-button>
        <el-tag
          v-if="h83Sync.rowCount > 0 || h83Sync.rouCostAjeNet !== 0"
          size="small"
          type="info"
          effect="plain"
        >
          H8-3：1901账项 {{ fmtAmt(h83Sync.rouCostAjeNet) }} / 1902 {{ fmtAmt(h83Sync.rouDepAjeNet) }}
        </el-tag>
        <el-tag v-if="significantNetChanges.length" size="small" type="warning" effect="plain">
          净值变动≥{{ CHANGE_RATE_THRESHOLD }}%：{{ significantNetChanges.length }} 项
        </el-tag>
        <el-tag size="small" :type="h9Linkage.isConsistent ? 'success' : 'danger'" effect="plain">
          {{ h9Linkage.isConsistent ? 'H8↔H9一致' : 'H8↔H9需核对' }}
        </el-tag>
        <el-tag
          v-if="detailCrossCheck.hasCostWarning"
          size="small"
          type="warning"
          effect="plain"
        >
          原值≠H8-2（差 {{ fmtAmt(detailCrossCheck.costDiff) }}）
        </el-tag>
        <el-tag
          v-if="detailCrossCheck.hasDepWarning"
          size="small"
          type="warning"
          effect="plain"
        >
          折旧≠H8-2（差 {{ fmtAmt(detailCrossCheck.depDiff) }}）
        </el-tag>
        <el-tag
          v-if="detailCrossCheck.hasImpairWarning"
          size="small"
          type="warning"
          effect="plain"
        >
          减值≠H8-2（差 {{ fmtAmt(detailCrossCheck.impairDiff) }}）
        </el-tag>
        <el-tag
          v-if="h82CategoryGap.unmatchedCount > 0"
          size="small"
          type="warning"
          effect="plain"
        >
          非标准类别 {{ h82CategoryGap.unmatchedCount }}
        </el-tag>
        <el-tag
          v-else-if="detailCrossCheck.detailCount && detailCrossCheck.isConsistent && !h82CategoryGap.unmatchedCount"
          size="small"
          type="success"
          effect="plain"
        >
          与 H8-2 勾稽一致
        </el-tag>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H8-1" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:H8-2" :validate="false" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:H8-3" :validate="false" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:H9-1" :validate="false" /></span>
        <el-button size="small" circle @click="openReview('H8-1')">💬</el-button>
      </div>
    </div>

    <el-alert
      v-if="showH82Remediation"
      type="warning"
      :closable="false"
      show-icon
      class="warn-alert"
    >
      <template #title>
        <span>H8-1 与 H8-2 勾稽异常，可一键重新带入未审数（保留账项调整）</span>
      </template>
      <div class="remediation-body">
        <ul class="remediation-list">
          <li v-if="detailCrossCheck.hasCostWarning">
            原值差额 {{ fmtAmt(detailCrossCheck.costDiff) }}（H8-1 {{ fmtAmt(detailCrossCheck.costDiff + detailCrossCheck.detailCost) }} vs H8-2 {{ fmtAmt(detailCrossCheck.detailCost) }}）
          </li>
          <li v-if="detailCrossCheck.hasDepWarning">
            折旧差额 {{ fmtAmt(detailCrossCheck.depDiff) }}
          </li>
          <li v-if="detailCrossCheck.hasImpairWarning">
            减值差额 {{ fmtAmt(detailCrossCheck.impairDiff) }}
          </li>
          <li v-if="h82CategoryGap.unmatchedCount">
            非标准类别 {{ h82CategoryGap.unmatchedCount }}：{{ h82CategoryGap.unmatchedCategories.join('、') }}（金额已归一到映射后类别，请复核）
          </li>
        </ul>
        <div class="remediation-actions">
          <el-button
            v-if="!isReadonly"
            size="small"
            type="primary"
            @click="handleFillH82"
          >
            重新从 H8-2 带入
          </el-button>
          <el-button size="small" @click="emit('navigate-sheet', 'H8-2')">打开 H8-2</el-button>
        </div>
      </div>
    </el-alert>

    <el-alert
      v-if="!h9Linkage.isConsistent"
      type="warning"
      :closable="false"
      show-icon
      class="warn-alert"
      :title="h9Linkage.message"
    />

    <el-card v-if="contractVariance.length > 0" shadow="never" class="variance-card">
      <template #header>
        <div class="section-title">
          <span>H8↔H9 按合同差额（|差|&gt;1 元）</span>
          <el-tag size="small" type="danger">{{ contractVariance.length }} 份</el-tag>
        </div>
      </template>
      <el-table :data="contractVariance" border size="small" max-height="240">
        <el-table-column prop="contractNo" label="合同号" width="120" fixed />
        <el-table-column prop="assetName" label="资产" min-width="100" show-overflow-tooltip />
        <el-table-column label="H8入账" width="110" align="right">
          <template #default="{ row }">{{ fmtAmt(row.h8Initial) }}</template>
        </el-table-column>
        <el-table-column label="H9初始" width="110" align="right">
          <template #default="{ row }">{{ fmtAmt(row.h9Initial) }}</template>
        </el-table-column>
        <el-table-column label="直接费用" width="100" align="right">
          <template #default="{ row }">{{ fmtAmt(row.directCost) }}</template>
        </el-table-column>
        <el-table-column label="激励" width="90" align="right">
          <template #default="{ row }">{{ fmtAmt(row.incentive) }}</template>
        </el-table-column>
        <el-table-column label="应入账" width="110" align="right">
          <template #default="{ row }">{{ fmtAmt(row.expected) }}</template>
        </el-table-column>
        <el-table-column label="差额" width="100" align="right">
          <template #default="{ row }">
            <span class="diff-bad">{{ fmtAmt(row.diff) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <p class="var-hint">CAS21：应入账 = H9初始 + 直接费用 − 激励。可跳转 H8-2 / H9-2 按合同核对。</p>
    </el-card>

    <!-- 一~三 区块 -->
    <el-card v-for="blk in blocks" :key="blk.key" shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>{{ blk.title }}</span>
          <el-button v-if="!isReadonly" size="small" @click="handleAdd(blk.key)">+ 分类</el-button>
        </div>
      </template>
      <el-table
        :data="blk.rows"
        border
        stripe
        size="small"
        class="adj-table"
        :row-class-name="adjRowClass"
      >
        <el-table-column label="项目" min-width="120" fixed>
          <template #default="{ row }">
            <span v-if="row.isSubtotal" class="subtotal-label">{{ row.category }}</span>
            <el-input
              v-else-if="!isReadonly"
              :model-value="row.category"
              size="small"
              @change="(v: string) => updateCell(blk.key, row.rowId, 'category', v)"
            />
            <span v-else>{{ row.category }}</span>
          </template>
        </el-table-column>

        <el-table-column label="期初数" align="center">
          <el-table-column label="未审数" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!row.isSubtotal && !isReadonly"
                :model-value="row.beginUnadjusted"
                :controls="false"
                size="small"
                class="amt-input"
                @change="(v: number | undefined) => updateCell(blk.key, row.rowId, 'beginUnadjusted', v ?? 0)"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.beginUnadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账项调整" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!row.isSubtotal && !isReadonly"
                :model-value="row.beginAdjustment"
                :controls="false"
                size="small"
                class="amt-input"
                @change="(v: number | undefined) => updateCell(blk.key, row.rowId, 'beginAdjustment', v ?? 0)"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.beginAdjustment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定数" min-width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="审定=未审+账项调整">{{ fmtAmt(row.beginAudited) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="期末数" align="center">
          <el-table-column label="未审数" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!row.isSubtotal && !isReadonly"
                :model-value="row.endUnadjusted"
                :controls="false"
                size="small"
                class="amt-input"
                @change="(v: number | undefined) => updateCell(blk.key, row.rowId, 'endUnadjusted', v ?? 0)"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.endUnadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账项调整" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!row.isSubtotal && !isReadonly"
                :model-value="row.endAdjustment"
                :controls="false"
                size="small"
                class="amt-input"
                @change="(v: number | undefined) => updateCell(blk.key, row.rowId, 'endAdjustment', v ?? 0)"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.endAdjustment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定数" min-width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="审定=未审+账项调整">{{ fmtAmt(row.endAudited) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="本期审定数与上期审定数的比较" align="center">
          <el-table-column label="变动额" min-width="100" align="right">
            <template #default="{ row }">
              <span :class="{ 'sig-rate': row.isSignificant }">{{ fmtAmt(row.changeAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="变动率" min-width="90" align="right">
            <template #default="{ row }">
              <span :class="{ 'sig-rate': row.isSignificant }">{{ fmtRate(row.changeRate) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column v-if="!isReadonly" label="" width="56" align="center" fixed="right">
          <template #default="{ row }">
            <el-popconfirm v-if="!row.isSubtotal" title="确认删除？" @confirm="deleteRow(row.rowId)">
              <template #reference>
                <el-button size="small" type="danger" link>删</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 四、净额 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>四、净额（原值 − 累计折旧 − 减值准备）</span>
          <span class="net-badge">期末审定净值 {{ fmtAmt(netAudited) }}</span>
        </div>
      </template>
      <el-table :data="netRows" border stripe size="small" class="adj-table" :row-class-name="netRowClass">
        <el-table-column prop="category" label="项目" min-width="120" fixed />
        <el-table-column label="期初审定净额" min-width="120" align="right">
          <template #default="{ row }"><span class="amt-cell">{{ fmtAmt(row.beginNet) }}</span></template>
        </el-table-column>
        <el-table-column label="期末审定净额" min-width="120" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.endNet) }}</span></template>
        </el-table-column>
        <el-table-column label="变动额" min-width="110" align="right">
          <template #default="{ row }">
            <span :class="{ 'sig-rate': row.isSignificant }">{{ fmtAmt(row.changeAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动率" min-width="100" align="right">
          <template #default="{ row }">
            <span :class="{ 'sig-rate': row.isSignificant }">{{ fmtRate(row.changeRate) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 试算平衡表数 / 差异 -->
    <el-card shadow="never" class="block-card">
      <template #header><span>与试算平衡表核对</span></template>
      <el-table :data="tbDiffRows" border size="small" class="adj-table">
        <el-table-column prop="label" label="项目" min-width="160" />
        <el-table-column label="本表未审数" min-width="120" align="right">
          <template #default="{ row }">{{ fmtAmt(row.scheduleAmount) }}</template>
        </el-table-column>
        <el-table-column label="试算平衡表数" min-width="120" align="right">
          <template #default="{ row }">{{ fmtAmt(row.tbAmount) }}</template>
        </el-table-column>
        <el-table-column label="差异" min-width="110" align="right">
          <template #default="{ row }">
            <span :class="{ 'diff-err': Math.abs(row.difference) >= 0.01 }">{{ fmtAmt(row.difference) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <p class="sheet-note">
        试算平衡表数优先取 TB 导入数；未导入时差异以本表未审为基数（可在分类行录入未审后核对）。
      </p>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header><span>审计说明</span></template>
      <el-form label-position="top" size="small">
        <el-form-item
          :label="`(1) 使用权资产净额较上期审定数增减变动的原因（尤其变动率超过${CHANGE_RATE_THRESHOLD}%的）`"
        >
          <el-input
            v-model="qualNotes.fluctuation"
            type="textarea"
            :autosize="{ minRows: 2 }"
            :disabled="isReadonly"
            placeholder="说明重大增减变动原因…"
            @change="saveQual"
          />
        </el-form-item>
        <el-form-item label="(2) 简化处理的短期租赁、低价值资产租赁及未纳入租赁负债计量的可变租赁付款额情况">
          <el-input
            v-model="qualNotes.simplified"
            type="textarea"
            :autosize="{ minRows: 2 }"
            :disabled="isReadonly"
            placeholder="可交叉索引 H8-13 简化处理检查表…"
            @change="saveQual"
          />
        </el-form-item>
        <el-form-item label="(3) 转租使用权资产取得的收入情况">
          <el-input
            v-model="qualNotes.sublease"
            type="textarea"
            :autosize="{ minRows: 2 }"
            :disabled="isReadonly"
            placeholder="无转租可填「不适用」…"
            @change="saveQual"
          />
        </el-form-item>
        <el-form-item label="其他说明">
          <el-input
            v-model="auditNoteLocal"
            type="textarea"
            :autosize="{ minRows: 2 }"
            :disabled="isReadonly"
            @change="saveNoteLocal"
          />
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计结论</span>
          <div v-if="!isReadonly" class="title-actions">
            <el-button size="small" @click="applyConclusion('A')">模板A</el-button>
            <el-button size="small" @click="applyConclusion('B')">模板B</el-button>
            <el-button size="small" @click="applyConclusion('C')">模板C</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="auditConclusionLocal"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="A、未见异常。B、除上述调整外未见异常。C、存在重大未调整事项或范围受限，不可确认。"
        @change="saveConclusionLocal"
      />
    </el-card>

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="1901 使用权资产"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * H8TabAdjudication.vue — H8-1 审定表
 * 四区块 Excel 列结构 + H8-3 账项回写 + H9/TB 勾稽
 */
import { ref, computed, toRef, inject, reactive, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import {
  useH8Adjudication,
  CHANGE_RATE_THRESHOLD,
  type H8AdjBlock,
} from '../../composables/useH8Adjudication'
import { useH8CrossSheet } from '../../composables/useH8CrossSheet'
import { useAuditContext } from '@/composables/useAuditContext'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'writeback-tb', costAudited: number, depAudited: number, impairAudited?: number): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})

const allResponsesRef = computed(() => props.allResponses)
const isReadonly = computed(() => props.isReadonly)
const projectId = computed(() => props.projectId)
const writebackLoading = ref(false)

const {
  costDisplayRows,
  depDisplayRows,
  impairDisplayRows,
  netRows,
  netAudited,
  significantNetChanges,
  tbDiffRows,
  detailCrossCheck,
  h82CategoryGap,
  auditNote,
  auditConclusion,
  qualitativeNotes,
  updateCell,
  addRow,
  deleteRow,
  publishAdjudicated,
  saveNote,
  saveConclusion,
  saveQualitativeNotes,
  applyConclusionTemplate,
  applySignificantFluctuationDraft,
  syncEndAdjFromH83,
  fillFromH82Detail,
} = useH8Adjudication({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
  isReadonly: toRef(props, 'isReadonly'),
  onSave: (itemId, value) => {
    saveResponse(itemId, value)
    emit('save', itemId, value)
  },
  onWritebackTB: async (cost, dep, impair) => {
    emit('writeback-tb', cost, dep, impair)
  },
})

const { h8VsH9Linkage, h83AdjustmentSync, h8H9ContractVariance } = useH8CrossSheet(allResponsesRef as any)
const h9Linkage = computed(() => h8VsH9Linkage.value)
const contractVariance = computed(() => h8H9ContractVariance.value)
const h83Sync = computed(() => h83AdjustmentSync.value)
const showH82Remediation = computed(
  () =>
    detailCrossCheck.value.hasCostWarning
    || detailCrossCheck.value.hasDepWarning
    || detailCrossCheck.value.hasImpairWarning
    || h82CategoryGap.value.unmatchedCount > 0,
)
const canSyncH83 = computed(
  () =>
    h83Sync.value.rowCount > 0 ||
    Math.abs(h83Sync.value.rouCostAjeNet) >= 0.005 ||
    Math.abs(h83Sync.value.rouCostRjeNet) >= 0.005 ||
    Math.abs(h83Sync.value.rouDepAjeNet) >= 0.005,
)

const blocks = computed(() => [
  { key: 'cost' as H8AdjBlock, title: '一、使用权资产原值（科目1901）', rows: costDisplayRows.value },
  { key: 'dep' as H8AdjBlock, title: '二、累计折旧（科目1902·备抵）', rows: depDisplayRows.value },
  { key: 'impair' as H8AdjBlock, title: '三、减值准备（科目1903·备抵）', rows: impairDisplayRows.value },
])

// ─── 从集中登记带入调整（1901 使用权资产原值，资产借方；双期单一账项调整列，作用于期末） ───
const bringInRows = computed(() =>
  costDisplayRows.value
    .filter((r: any) => !r.isSubtotal)
    .map((r: any) => ({ rowKey: r.rowId, name: r.category, aje: 0, rje: 0 })),
)
const {
  adjPull,
  visible: bringInVisible,
  rowOptions: bringInRowOptions,
  open: openBringInAdjustment,
  apply: onBringInApply,
} = useAdjudicationBringIn({
  projectId: toRef(props, 'projectId') as any,
  year: useAuditContext().year as any,
  subjectPrefix: '1901',
  direction: 'debit',
  subjectCode: '1901',
  wpCode: 'H8',
  subjectLabel: '使用权资产(1901)',
  rows: bringInRows,
  // 单一「账项调整」列（审定=未审+账项调整）：aje/rje 净额均累加至原值行期末账项调整（增量累加）
  updateCell: (rowKey: string, _field: any, value: number) => {
    const row = costDisplayRows.value.find((r: any) => r.rowId === rowKey && !r.isSubtotal)
    const live = Number(row?.endAdjustment) || 0
    updateCell('cost', rowKey, 'endAdjustment', Math.round((live + value) * 100) / 100)
  },
  totalAudited: () => netAudited.value,
})

const auditNoteLocal = ref(auditNote.value)
const auditConclusionLocal = ref(auditConclusion.value)
const qualNotes = reactive({ ...qualitativeNotes.value })

watch(auditNote, (v) => {
  auditNoteLocal.value = v
})
watch(auditConclusion, (v) => {
  auditConclusionLocal.value = v
})
watch(
  qualitativeNotes,
  (v) => {
    Object.assign(qualNotes, v)
  },
  { deep: true },
)

function fmtAmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '—'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRate(v: number | null | undefined): string {
  if (v == null) return '—'
  return `${v.toFixed(2)}%`
}

async function handleAdd(block: H8AdjBlock) {
  const { value } = await ElMessageBox.prompt('请输入资产分类', '新增分类行', {
    confirmButtonText: '确认',
    cancelButtonText: '取消',
    inputPlaceholder: '如：房屋及建筑物',
  })
  if (value) addRow(value, block)
}

function handleFillH82() {
  const res = fillFromH82Detail('book')
  if (res.costFilled || res.depFilled || res.impairFilled) ElMessage.success(res.message)
  else ElMessage.info(res.message)
}

function handleSyncH83() {
  const res = syncEndAdjFromH83(
    h83Sync.value.rouCostAjeNet,
    h83Sync.value.rouCostRjeNet,
    h83Sync.value.rouDepAjeNet,
    h83Sync.value.rouDepRjeNet,
  )
  if (res.applied) ElMessage.success(res.message)
  else ElMessage.info(res.message)
}

function handleSignificantDraft() {
  applySignificantFluctuationDraft()
  Object.assign(qualNotes, qualitativeNotes.value)
  ElMessage.success('已写入说明(1)')
}

async function handleWriteback() {
  writebackLoading.value = true
  try {
    await publishAdjudicated()
    ElMessage.success('已回写 TB（1901/累计折旧）')
  } finally {
    writebackLoading.value = false
  }
}

function saveQual() {
  qualitativeNotes.value = { ...qualNotes }
  saveQualitativeNotes()
}
function saveNoteLocal() {
  saveNote(auditNoteLocal.value)
}
function saveConclusionLocal() {
  saveConclusion(auditConclusionLocal.value)
}
function applyConclusion(k: 'A' | 'B' | 'C') {
  applyConclusionTemplate(k)
  auditConclusionLocal.value = auditConclusion.value
}
function openReview(id: string) {
  openReviewDialog(id)
}
function adjRowClass({ row }: { row: { isSubtotal?: boolean; isSignificant?: boolean } }) {
  if (row.isSubtotal) return 'row-subtotal'
  if (row.isSignificant) return 'row-significant'
  return ''
}
function netRowClass({ row }: { row: { isSubtotal?: boolean; isSignificant?: boolean } }) {
  return adjRowClass({ row })
}
</script>

<style scoped>
.h8-tab-adjudication { padding: 16px; font-size: var(--wp-font-size, 13px); }
.compile-hint {
  margin-bottom: 12px; font-size: 12px; color: var(--el-text-color-secondary);
  border: 1px solid var(--el-border-color-lighter); border-radius: 6px;
  padding: 8px 12px; background: var(--el-fill-color-blank);
}
.compile-hint summary { cursor: pointer; font-weight: 600; color: var(--el-text-color-primary); }
.hint-content { margin-top: 8px; line-height: 1.6; }
.hint-content p { margin: 4px 0; }
.excel-tip { color: var(--el-color-warning-dark-2); margin-top: 8px !important; }
.objective-alert, .warn-alert { margin-bottom: 12px; }
.variance-card { margin-bottom: 12px; }
.variance-card .diff-bad { color: var(--el-color-danger); font-variant-numeric: tabular-nums; }
.var-hint { margin: 8px 0 0; font-size: 12px; color: var(--el-text-color-secondary); }
.remediation-body { margin-top: 4px; }
.remediation-list { margin: 0 0 8px; padding-left: 18px; font-size: 12px; line-height: 1.5; }
.remediation-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.tab-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  gap: 8px; flex-wrap: wrap; margin-bottom: 12px;
}
.toolbar-left, .toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; }
.block-card, .note-card { margin-bottom: 14px; }
.section-title {
  display: flex; align-items: center; justify-content: space-between; gap: 8px; font-weight: 600;
}
.title-actions { display: flex; gap: 6px; }
.net-badge { font-weight: 500; font-size: 13px; color: var(--el-color-primary); }
.adj-table { font-size: var(--wp-font-size, 13px); width: 100%; }
.amt-cell, .formula-cell { font-variant-numeric: tabular-nums; }
.formula-cell { color: var(--el-color-primary); }
.sig-rate { color: var(--el-color-danger); font-weight: 600; }
.diff-err { color: var(--el-color-danger); font-weight: 600; }
.subtotal-label { font-weight: 600; }
.sheet-note { margin: 8px 0 0; font-size: 12px; color: var(--el-text-color-secondary); }
:deep(.row-subtotal) { background: var(--el-fill-color-light) !important; font-weight: 600; }
:deep(.row-significant) { background: var(--el-color-warning-light-9) !important; }
:deep(.amt-input) { width: 100%; }
</style>
