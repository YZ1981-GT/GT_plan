<template>
  <div class="h9-tab-adjudication">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：核实租赁负债及未确认融资费用期末余额的完整、准确与计价，验证与 H8 使用权资产初始确认的 CAS21 勾稽关系，为报表列报及 TB 回写提供审定依据。"
    />

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>租赁负债审定表：科目2205（贷方/负债类）+ 未确认融资费用（借方/负债备抵类）。负债类期末=期初+贷方-借方；备抵类期末=期初+借方-贷方。审定数=未审+AJE+RJE。净额=原值-未确认融资费用。</p>
    </div>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" plain :loading="adjPull.loading.value" @click="openBringInAdjustment">
          <el-icon><Download /></el-icon>带入调整
        </el-button>
        <el-dropdown v-if="!isReadonly" trigger="click" @command="handleFillFromDetail">
          <el-button size="small" type="primary">从明细带入 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="book">写入未审（保留 AJE/RJE）</el-dropdown-item>
              <el-dropdown-item command="full">按审定覆盖（清零 AJE/RJE）</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H9-1" :context-project-id="props.projectId" /></span>
        <el-tag size="small" type="info">共 {{ liabilityRows.length + unearnedRows.length }} 行</el-tag>
      </div>
    </div>

    <!-- 区块1: 租赁负债原值（贷方/负债类） -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>一、租赁负债原值（科目2205，贷方/负债类）</span>
          <div class="title-actions">
            <el-button v-if="!isReadonly" size="small" @click="handleAddLiabilityRow">+ 新增行</el-button>
            <el-button size="small" @click="$emit('open-review', 'adjudication-liability')">复核</el-button>
          </div>
        </div>
      </template>
      <el-table :data="liabilityRows" border size="small" class="formula-table" show-summary :summary-method="getLiabilitySummary">
        <el-table-column prop="name" label="项目（合同类型）" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="onCellChange(row.rowId, 'name', row.name)" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="beginBalance" label="期初余额" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.beginBalance" :controls="false" size="small"
              @change="(v: number | undefined) => onCellChange(row.rowId, 'beginBalance', v)" />
            <span v-else>{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="creditAmount" label="贷方发生(增加)" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.creditAmount" :controls="false" size="small"
              @change="(v: number | undefined) => onCellChange(row.rowId, 'creditAmount', v)" />
            <span v-else>{{ fmtAmt(row.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="debitAmount" label="借方发生(减少)" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.debitAmount" :controls="false" size="small"
              @change="(v: number | undefined) => onCellChange(row.rowId, 'debitAmount', v)" />
            <span v-else>{{ fmtAmt(row.debitAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="公式：期初+贷方-借方（负债类贷方科目）">{{ fmtAmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="unadjusted" label="未审数" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.unadjusted" :controls="false" size="small"
              @change="(v: number | undefined) => onCellChange(row.rowId, 'unadjusted', v)" />
            <span v-else>{{ fmtAmt(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="aje" label="AJE" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.aje" :controls="false" size="small"
              @change="(v: number | undefined) => onCellChange(row.rowId, 'aje', v)" />
            <span v-else>{{ fmtAmt(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="rje" label="RJE" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.rje" :controls="false" size="small"
              @change="(v: number | undefined) => onCellChange(row.rowId, 'rje', v)" />
            <span v-else>{{ fmtAmt(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="公式：未审+AJE+RJE">{{ fmtAmt(row.audited) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="reclassification" label="重分类(一年内到期)" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.reclassification" :controls="false" size="small"
              @change="(v: number | undefined) => onCellChange(row.rowId, 'reclassification', v)" />
            <span v-else>{{ fmtAmt(row.reclassification) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="报表数" width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="公式：审定−重分类">{{ fmtAmt(row.fsAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="beginFsAmount" label="期初报表数" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.beginFsAmount" :controls="false" size="small"
              @change="(v: number | undefined) => onCellChange(row.rowId, 'beginFsAmount', v)" />
            <span v-else>{{ fmtAmt(row.beginFsAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动额" width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmt(row.changeAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动率" width="90" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" :class="{ 'rate-warn': Math.abs(row.changeRate) > 0.3 }">
              {{ fmtRate(row.changeRate) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="50" align="center">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="handleDeleteRow(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 区块2: 未确认融资费用（借方/负债备抵类） -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>二、未确认融资费用（借方/负债备抵类）</span>
          <div class="title-actions">
            <el-button v-if="!isReadonly" size="small" @click="handleAddUnearnedRow">+ 新增行</el-button>
            <el-button size="small" @click="$emit('open-review', 'adjudication-unearned')">复核</el-button>
          </div>
        </div>
      </template>
      <el-table :data="unearnedRows" border size="small" class="formula-table" show-summary :summary-method="getUnearnedSummary">
        <el-table-column prop="name" label="项目（合同类型）" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="onCellChange(row.rowId, 'name', row.name)" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="beginBalance" label="期初余额" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.beginBalance" :controls="false" size="small"
              @change="(v: number | undefined) => onCellChange(row.rowId, 'beginBalance', v)" />
            <span v-else>{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="debitAmount" label="借方发生(增加)" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.debitAmount" :controls="false" size="small"
              @change="(v: number | undefined) => onCellChange(row.rowId, 'debitAmount', v)" />
            <span v-else>{{ fmtAmt(row.debitAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="creditAmount" label="贷方发生(摊销确认)" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.creditAmount" :controls="false" size="small"
              @change="(v: number | undefined) => onCellChange(row.rowId, 'creditAmount', v)" />
            <span v-else>{{ fmtAmt(row.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="公式：期初+借方-贷方（借方/负债备抵类）">{{ fmtAmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="unadjusted" label="未审数" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.unadjusted" :controls="false" size="small"
              @change="(v: number | undefined) => onCellChange(row.rowId, 'unadjusted', v)" />
            <span v-else>{{ fmtAmt(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="aje" label="AJE" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.aje" :controls="false" size="small"
              @change="(v: number | undefined) => onCellChange(row.rowId, 'aje', v)" />
            <span v-else>{{ fmtAmt(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="rje" label="RJE" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.rje" :controls="false" size="small"
              @change="(v: number | undefined) => onCellChange(row.rowId, 'rje', v)" />
            <span v-else>{{ fmtAmt(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="公式：未审+AJE+RJE">{{ fmtAmt(row.audited) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="reclassification" label="重分类(一年内到期)" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.reclassification" :controls="false" size="small"
              @change="(v: number | undefined) => onCellChange(row.rowId, 'reclassification', v)" />
            <span v-else>{{ fmtAmt(row.reclassification) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="报表数" width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="公式：审定−重分类">{{ fmtAmt(row.fsAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="beginFsAmount" label="期初报表数" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.beginFsAmount" :controls="false" size="small"
              @change="(v: number | undefined) => onCellChange(row.rowId, 'beginFsAmount', v)" />
            <span v-else>{{ fmtAmt(row.beginFsAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动额" width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmt(row.changeAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动率" width="90" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" :class="{ 'rate-warn': Math.abs(row.changeRate) > 0.3 }">
              {{ fmtRate(row.changeRate) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="50" align="center">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="handleDeleteRow(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 三、租赁负债净额 -->
    <el-card shadow="never" class="net-card">
      <div class="net-row">
        <span class="net-label">三、租赁负债净额（原值 − 未确认融资费用）</span>
        <div class="net-metrics">
          <span class="net-value">审定 {{ fmtAmt(netAudited) }} 元</span>
          <span class="net-fs">报表 {{ fmtAmt(netFsAmount) }} 元</span>
          <el-tag v-if="Math.abs(netChangeRate) > 0.3" type="danger" size="small" effect="plain">
            净额变动率 {{ fmtRate(netChangeRate) }}（&gt;30%，须说明主要原因）
          </el-tag>
          <el-tag v-else type="info" size="small" effect="plain">净额变动率 {{ fmtRate(netChangeRate) }}</el-tag>
        </div>
      </div>
    </el-card>

    <!-- 跨表勾稽：H9-1 vs H9-2 -->
    <el-card shadow="never" class="linkage-card">
      <template #header>
        <div class="section-title"><span>H9-1 ↔ H9-2 勾稽</span></div>
      </template>
      <div class="linkage-status" :class="adjudicationVsDetail.isMatch ? 'linkage-ok' : 'linkage-error'">
        <span v-if="adjudicationVsDetail.isMatch">✓ 审定合计与明细合计一致（±1 元）</span>
        <span v-else>
          ✗ 审定合计与明细不一致，差额 {{ adjudicationVsDetail.diff.toFixed(2) }} 元
          （H9-1={{ adjudicationTotal.toFixed(2) }}，H9-2={{ detailTotal.toFixed(2) }}）
        </span>
      </div>
    </el-card>

    <!-- H8-H9 联动校验区域 -->
    <el-card shadow="never" class="linkage-card">
      <template #header>
        <div class="section-title">
          <span>H8-H9 联动校验（CAS21）</span>
        </div>
      </template>
      <div class="linkage-content">
        <div class="linkage-formula">
          <span class="formula-label">核心公式：</span>
          <span>H9初始确认 ≈ H8初始计量 - 初始直接费用 + 租赁激励（±1元容差）</span>
        </div>
        <div class="linkage-status" :class="h8Linkage.isConsistent ? 'linkage-ok' : 'linkage-error'">
          <span>{{ h8Linkage.message }}</span>
          <span v-if="!h8Linkage.isConsistent && h8Linkage.diff !== 0" class="diff-badge">
            差额：{{ h8Linkage.diff > 0 ? '+' : '' }}{{ h8Linkage.diff.toFixed(2) }}元
          </span>
        </div>
      </div>
    </el-card>

    <!-- TB回写 -->
    <div v-if="!isReadonly" class="writeback-area">
      <el-button type="primary" @click="handleWriteback" :loading="writebackLoading">
        审定数回写TB（2205租赁负债 + 未确认融资费用）
      </el-button>
    </div>

    <!-- 审计说明+结论 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计说明与结论</span>
          <div class="title-actions">
            <el-button size="small" @click="$emit('open-review', 'adjudication-note')">复核</el-button>
          </div>
        </div>
      </template>
      <el-form label-position="top" size="small">
        <el-form-item label="审计说明">
          <el-input type="textarea" :autosize="{ minRows: 3 }" v-model="auditNoteLocal"
            :readonly="isReadonly" @change="handleSaveNote" placeholder="请输入审计说明..." />
        </el-form-item>
        <el-form-item label="审计结论">
          <el-input type="textarea" :autosize="{ minRows: 2 }" v-model="auditConclusionLocal"
            :readonly="isReadonly" @change="handleSaveConclusion" placeholder="请输入审计结论..." />
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>编制顺序：先编 H9-2/H9-3 明细 →「从明细带入」→ 填 AJE/RJE 与一年内到期重分类 → 核变动率 → 回写 TB</li>
        <li>租赁负债为贷方科目（负债类），期末=期初+贷方-借方；未确认融资费用为借方备抵，期末=期初+借方-贷方</li>
        <li>报表数=审定数−重分类(一年一年内到期)；变动额/率对齐 Excel 本期审定与上期比较</li>
        <li>净额变动率超过 30% 时须在审计说明中写明主要原因（模板红字要求）</li>
        <li>CAS21：H9初始确认≈H8初始计量-直接费用+激励（±1元）；H9-1 审定合计应与 H9-2 明细合计勾稽</li>
        <li>回写TB后自动发布 substantive:adjudicated 事件</li>
        <li>「带入调整」：从集中登记按科目 2205 拉取调整分录，逐笔分配到租赁负债原值行的 AJE/RJE，带入后审定数自动更新并联动附注</li>
      </ul>
    </details>

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="2205 租赁负债"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * H9TabAdjudication.vue — H9-1 审定表（负债类双区块+H8联动校验+TB回写）
 *
 * 三段结构：
 * 一、租赁负债原值（贷方/负债类，期末=期初+贷方-借方）
 * 二、未确认融资费用（借方/负债备抵类，期末=期初+借方-贷方）
 * 三、租赁负债净额（原值-未确认融资费用）
 *
 * + H8-H9 联动校验区（CAS21：H9初始≈H8初始-直接费用+激励，±1元容差）
 * + TB回写（2205+未确认融资费用）
 * + 审计说明/结论
 *
 * Spec: .kiro/specs/h9-lease-liabilities/
 * Task: 4.2
 * Requirements: 2.1-2.8, 8.1-8.4
 */
import { ref, toRef, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
import { useH9Adjudication, type H9AdjudicationRow } from '../../composables/useH9Adjudication'
import { useH9CrossSheet } from '../../composables/useH9CrossSheet'
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
  (e: 'open-ai', section: string): void
  (e: 'open-review', section: string): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const writebackLoading = ref(false)
const auditNoteLocal = ref('')
const auditConclusionLocal = ref('')

const allResponsesRef = toRef(props, 'allResponses')

const {
  liabilityRows, unearnedRows,
  liabilitySubtotal, unearnedSubtotal, netAudited, netFsAmount, netChangeRate,
  updateCell, addRow, deleteRow, fillFromDetail, syncAjeRjeFromAdjustment,
  publishAdjudicated, saveNote, saveConclusion,
  auditNote, auditConclusion,
} = useH9Adjudication({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef,
  onSave: (itemId, value) => emit('save', itemId, value),
  onWritebackTB: async (liability, unearned) => {
    emit('save', 'H9-1-liability-audited', liability)
    emit('save', 'H9-1-unearned-audited', unearned)
  },
})

const {
  h9VsH8Linkage,
  adjudicationVsDetail,
  adjudicationTotal,
  detailTotal,
} = useH9CrossSheet(allResponsesRef)
const h8Linkage = computed(() => h9VsH8Linkage.value)

// ─── 从集中登记带入调整（2205 租赁负债原值，负债贷方；分列 AJE/RJE，作用于原值行） ───
const bringInRows = computed(() =>
  liabilityRows.value.map((r) => ({
    rowKey: r.rowId,
    name: r.name,
    aje: Number(r.aje) || 0,
    rje: Number(r.rje) || 0,
  })),
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
  subjectPrefix: '2205',
  direction: 'credit',
  subjectCode: '2205',
  wpCode: 'H9',
  subjectLabel: '租赁负债(2205)',
  rows: bringInRows,
  updateCell: (rowKey: string, field: any, value: number) =>
    updateCell(rowKey, field === 'rje' ? 'rje' : 'aje', value),
  totalAudited: () => liabilitySubtotal.value.audited,
})

// H9-4 → H9-1 AJE/RJE 联动
function _onAdjustmentCreated(payload: any): void {
  const detail = payload?.detail ?? payload ?? {}
  if (detail.wpCode && detail.wpCode !== 'H9') return
  const res = syncAjeRjeFromAdjustment(
    Number(detail.ajeNet) || 0,
    Number(detail.rjeNet) || 0,
  )
  if (res.applied) ElMessage.success(res.message)
}

onMounted(() => {
  eventBus.on('adjustment:created', _onAdjustmentCreated)
})
onBeforeUnmount(() => {
  eventBus.off('adjustment:created', _onAdjustmentCreated)
})

// Sync local text refs
watch(auditNote, (v) => { auditNoteLocal.value = v }, { immediate: true })
watch(auditConclusion, (v) => { auditConclusionLocal.value = v }, { immediate: true })

function fmtAmt(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRate(v: number): string {
  if (!Number.isFinite(v) || v === 0) return '0.00%'
  return `${(v * 100).toFixed(2)}%`
}

function onCellChange(rowId: string, field: string, value: any) {
  updateCell(rowId, field, value)
}

function handleFillFromDetail(mode: 'book' | 'full') {
  const res = fillFromDetail(mode)
  if (!res.liabilityFilled && !res.unearnedFilled) {
    ElMessage.warning(res.message)
  } else {
    ElMessage.success(res.message)
  }
}

async function handleAddLiabilityRow() {
  const { value } = await ElMessageBox.prompt('请输入租赁合同类型名称', '新增负债行', {
    confirmButtonText: '确认', cancelButtonText: '取消', inputPlaceholder: '如：房屋租赁/设备租赁',
  })
  if (value) addRow(value, 'liability')
}

async function handleAddUnearnedRow() {
  const { value } = await ElMessageBox.prompt('请输入融资费用类型名称', '新增未确认融资费用行', {
    confirmButtonText: '确认', cancelButtonText: '取消', inputPlaceholder: '如：房屋租赁/设备租赁',
  })
  if (value) addRow(value, 'unearned')
}

function handleDeleteRow(rowId: string) {
  deleteRow(rowId)
}

async function handleWriteback() {
  writebackLoading.value = true
  try {
    // Call TB writeback API for 2205 租赁负债 (贷方/负债类)
    await http.put(`/projects/${props.projectId}/trial-balance/writeback`, {
      account_code: '2205',
      audited_amount: liabilitySubtotal.value.audited,
    })
    // Call TB writeback API for 未确认融资费用 (借方/负债备抵类)
    await http.put(`/projects/${props.projectId}/trial-balance/writeback`, {
      account_code: '1802',
      audited_amount: unearnedSubtotal.value.audited,
    })
    // Publish adjudicated event (dispatches 'substantive:adjudicated')
    await publishAdjudicated()
    ElMessage.success('审定数已回写TB（2205租赁负债 + 未确认融资费用）')
  } catch {
    ElMessage.warning('审定数回写失败，请手动确认试算表数据')
  } finally {
    writebackLoading.value = false
  }
}

function handleSaveNote() { saveNote(auditNoteLocal.value) }
function handleSaveConclusion() { saveConclusion(auditConclusionLocal.value) }

function getLiabilitySummary({ columns }: { columns: any[]; data: H9AdjudicationRow[] }) {
  return columns.map((_: any, idx: number) => {
    if (idx === 0) return '负债原值合计'
    const s = liabilitySubtotal.value
    const map: Record<number, number> = {
      1: s.beginBalance, 2: s.creditAmount, 3: s.debitAmount,
      4: s.endBalance, 5: s.unadjusted, 6: s.aje, 7: s.rje, 8: s.audited,
    }
    return map[idx] !== undefined ? fmtAmt(map[idx]) : ''
  })
}

function getUnearnedSummary({ columns }: { columns: any[]; data: H9AdjudicationRow[] }) {
  return columns.map((_: any, idx: number) => {
    if (idx === 0) return '融资费用合计'
    const s = unearnedSubtotal.value
    const map: Record<number, number> = {
      1: s.beginBalance, 2: s.debitAmount, 3: s.creditAmount,
      4: s.endBalance, 5: s.unadjusted, 6: s.aje, 7: s.rje, 8: s.audited,
    }
    return map[idx] !== undefined ? fmtAmt(map[idx]) : ''
  })
}
</script>

<style scoped>
.h9-tab-adjudication { padding: 16px; font-size: var(--wp-font-size, 13px); }

.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  border-radius: 0 6px 6px 0; margin-bottom: 16px; font-size: 12px; color: #92400e;
}

.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 6px; }

.objective-alert { margin-bottom: 12px; }
.tab-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px; flex-wrap: wrap; gap: 8px;
}
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }

.block-card { margin-bottom: 16px; }
.formula-table { font-size: var(--wp-font-size, 13px); }
.formula-table :deep(.formula-col) { background: #f0f9ff; }
.formula-value { border-bottom: 1px dashed #409eff; cursor: help; color: #409eff; }

.net-card { margin-bottom: 16px; }
.net-row { display: flex; align-items: center; justify-content: space-between; padding: 8px 0; flex-wrap: wrap; gap: 8px; }
.net-label { font-weight: 600; }
.net-metrics { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.net-value { font-size: 18px; font-weight: 700; color: var(--el-color-primary); }
.net-fs { font-size: 13px; color: var(--el-text-color-secondary); }
.rate-warn { color: #f56c6c; font-weight: 700; }

.linkage-card { margin-bottom: 16px; }
.linkage-content { padding: 4px 0; }
.linkage-formula { margin-bottom: 10px; font-size: 12px; color: var(--el-text-color-secondary); }
.formula-label { font-weight: 600; }
.linkage-status { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-radius: 6px; }
.linkage-ok { background: #f0f9eb; color: #67c23a; }
.linkage-error { background: #fef0f0; color: #f56c6c; }
.diff-badge { font-weight: 700; margin-left: 8px; }

.writeback-area { margin-bottom: 16px; text-align: right; }
.note-card { margin-bottom: 16px; }

.compile-hint {
  margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary);
  cursor: pointer; padding: 8px 12px; border-radius: 6px; background: #fafafa;
}
.compile-hint summary { font-weight: 600; margin-bottom: 6px; }
.compile-hint ul { padding-left: 18px; margin: 4px 0; line-height: 1.8; }
</style>
