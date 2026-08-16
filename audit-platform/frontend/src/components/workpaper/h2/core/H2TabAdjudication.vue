<template>
  <div class="h2-tab-adjudication">
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：核实在建工程原值(1604)及减值准备期末余额的存在、完整与计价；审定净值=原值−减值；与 H2-2/TB 勾稽，为报表列报与转固提供审定依据。"
    />

    <!-- 四表取数科目溯源面板 -->
    <WpSemanticAccountSourcePanel
      :source="htmlData?.tb_source_codes"
      :slot-order="['gross', 'eng_mat', 'impairment']"
      :slot-labels="{ gross: '在建工程', eng_mat: '工程物资', impairment: '在建工程减值准备' }"
      hint="科目定位：BS-029 在建工程 = TB('1604')"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          plain
          @click="handleSyncFromH22"
        >
          从 H2-2 同步工程
        </el-button>
        <el-button
          v-if="!isReadonly && h23Sync.rowCount > 0"
          size="small"
          plain
          @click="handleSyncFromH23"
        >
          从 H2-3 回写期末账项调整
        </el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          plain
          @click="handleSeedMaterials"
        >
          从 TB 带入工程物资
        </el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          plain
          :disabled="!hasFourTableSeed"
          :title="hasFourTableSeed ? '按 1604 叶子子科目带入期初/期末未审数' : '四表库暂无在建工程明细子科目'"
          @click="handleSeedFromFourTable"
        >
          从四表库带入未审数
        </el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          plain
          :loading="adjPull.loading.value"
          @click="openBringInAdjustment"
        >
          <el-icon><Download /></el-icon>带入调整
        </el-button>
        <el-tag size="small" type="info" effect="plain">
          TB·1604 未审 {{ fmtAmt(tbData.unadjusted_amount) }} / 审定 {{ fmtAmt(tbData.audited_amount) }}
        </el-tag>
        <el-tag
          v-if="Math.abs(state.unadjustedVsTbDiff.value) > 0.01 && state.costDetailRows.value.length"
          size="small"
          type="warning"
          effect="plain"
        >
          未审合计 vs TB差 {{ fmtAmt(state.unadjustedVsTbDiff.value) }}
        </el-tag>
        <el-tag v-if="h23Sync.rowCount > 0" size="small" type="info" effect="plain">
          H2-3：1604账项净额 {{ fmtAmt(h23Sync.cipAjeNet) }}（{{ h23Sync.rowCount }}行）
        </el-tag>
        <el-tag
          v-if="h23Sync.rowCount > 0 && Math.abs(h23AdjDiff) > 0.01"
          size="small"
          type="warning"
          effect="plain"
        >
          与本期期末账项合计差 {{ fmtAmt(h23AdjDiff) }}
        </el-tag>
        <el-tag
          v-if="state.significantNetChanges.value.length"
          size="small"
          type="danger"
          effect="plain"
        >
          净值变动≥{{ state.CHANGE_RATE_THRESHOLD }}%：{{ state.significantNetChanges.value.length }} 项
        </el-tag>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H2-1" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:H2-2" :validate="false" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:H2-3" :validate="false" /></span>
        <el-tag size="small" type="info">工程 {{ state.costDetailRows.value.length }} 项</el-tag>
        <el-button size="small" link type="default" @click="openReview('H2-1')">💬 复核</el-button>
      </div>
    </div>

    <!-- 一、原值 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>一、在建工程原值（科目1604）</span>
          <el-button size="small" circle @click="openReview('H2-1-cost')">💬</el-button>
        </div>
      </template>
      <AdjAmountTable
        :rows="costDisplayRows"
        :is-readonly="isReadonly"
        block="cost"
        @cell-change="onCellChange"
        @remove="handleRemoveRow"
      />
      <div v-if="!isReadonly" class="add-row-bar">
        <el-button size="small" @click="handleAddRow">+ 新增工程项目</el-button>
      </div>
    </el-card>

    <!-- 二、减值准备 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>二、减值准备</span>
          <span class="section-hint">可与 H2-15/H2-16 勾稽</span>
        </div>
      </template>
      <AdjAmountTable
        :rows="impairDisplayRows"
        :is-readonly="isReadonly"
        block="impair"
        @cell-change="onCellChange"
        @remove="handleRemoveRow"
      />
    </el-card>

    <!-- 三、净值 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>三、净值（=原值−减值）</span>
          <el-tag
            v-if="Math.abs(state.netIdentityDiff.value) > 0.01"
            size="small"
            type="danger"
          >
            身份校验差 {{ fmtAmt(state.netIdentityDiff.value) }}
          </el-tag>
          <el-tag v-else size="small" type="success" effect="plain">身份校验通过</el-tag>
        </div>
      </template>
      <el-table
        :data="state.netRows.value"
        border
        stripe
        size="small"
        class="adj-table"
        :row-class-name="netRowClass"
      >
        <el-table-column prop="name" label="项目" min-width="140" fixed />
        <el-table-column label="期初未审" min-width="110" align="right">
          <template #default="{ row }">
            <span class="amt-cell">{{ fmtAmt(row.beginUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初审定" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="原值期初审定−减值期初审定">{{ fmtAmt(row.beginAudited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末未审" min-width="110" align="right">
          <template #default="{ row }">
            <span class="amt-cell">{{ fmtAmt(row.endUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末审定" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="原值期末审定−减值期末审定">{{ fmtAmt(row.endAudited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定变动额" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtAmt(row.auditedChange) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定变动率" min-width="100" align="right">
          <template #default="{ row }">
            <span :class="{ 'rate-significant': row.isSignificant }">
              {{ fmtRate(row.auditedChangeRate) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
      <p class="net-hint">
        审定净值合计 <b>{{ fmtAmt(state.netTotalRow.value?.endAudited) }}</b>
        （期初 {{ fmtAmt(state.netTotalRow.value?.beginAudited) }}）。
        变动率绝对值≥{{ state.CHANGE_RATE_THRESHOLD }}% 须在下方说明(1)解释原因。
      </p>
    </el-card>

    <!-- 与试算平衡表核对 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header"><span>与试算平衡表核对</span></div>
      </template>
      <el-table :data="state.tbCompareRows.value" size="small" border>
        <el-table-column prop="label" label="项目" min-width="180" />
        <el-table-column label="审定数" align="right" min-width="130">
          <template #default="{ row }">
            <template v-if="row.label.includes('1605') && !isReadonly">
              <WpAmountInput
                :model-value="state.materialsAudited.value"
                size="small"
                class="amt-input"
                @change="(v: number) => state.updateMaterials('audited', v ?? 0)"
              />
            </template>
            <span v-else class="amt-cell">{{ fmtAmt(row.audited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="试算平衡表" align="right" min-width="130">
          <template #default="{ row }">
            <template v-if="row.label.includes('1605') && !isReadonly">
              <el-input-number
                :model-value="state.materialsTb.value"
                :controls="false"
                size="small"
                class="amt-input"
                @change="(v: number) => state.updateMaterials('tbAmount', v ?? 0)"
              />
            </template>
            <span v-else class="amt-cell">{{ fmtAmt(row.tbAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异" align="right" min-width="120">
          <template #default="{ row }">
            <span :class="{ 'error-amount': Math.abs(row.difference) > 0.01 }">
              {{ fmtAmt(row.difference) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 交叉验证 -->
    <el-alert
      v-if="Math.abs(state.detailDiff.value) > 0.01"
      type="warning"
      :closable="false"
      show-icon
      class="cross-alert"
      :title="`交叉验证：原值审定合计 vs H2-2 差异 ${fmtAmt(state.detailDiff.value)}`"
    />
    <el-alert
      v-if="Math.abs(state.impairDetailDiff.value) > 0.01 && state.impairTotalRow.value.endAudited !== 0"
      type="warning"
      :closable="false"
      show-icon
      class="cross-alert"
      :title="`交叉验证：减值审定合计 vs H2-2 差异 ${fmtAmt(state.impairDetailDiff.value)}`"
    />
    <el-alert
      v-if="Math.abs(state.transferDiff.value) > 0.01"
      type="warning"
      :closable="false"
      show-icon
      class="cross-alert"
      :title="`交叉验证：H2-2 转固合计 vs H2-5 差异 ${fmtAmt(state.transferDiff.value)}`"
    />

    <el-card
      v-if="state.triangleErrors.value.length > 0"
      shadow="never"
      class="block-card"
    >
      <template #header>
        <div class="section-header">
          <span>三角勾稽校验异常（H2-2，含转固扣减）</span>
          <GtIndexChip value="wp:H2-2" label="→ H2-2明细表" />
        </div>
      </template>
      <el-table :data="state.triangleErrors.value" size="small" border>
        <el-table-column prop="name" label="工程项目" min-width="150" />
        <el-table-column label="差额" min-width="120" align="right">
          <template #default="{ row }">
            <span class="error-amount">{{ fmtAmt(row.diff) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 审计说明（结构化，对齐源模板） -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header"><span>审计说明</span></div>
      </template>
      <div class="qual-grid">
        <div class="qual-item">
          <label>
            (1) 净值重大变动原因
            <span class="req-hint">（变动率≥{{ state.CHANGE_RATE_THRESHOLD }}%须说明）</span>
          </label>
          <el-input
            v-model="state.qualitativeNotes.value.fluctuation"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 5 }"
            :disabled="isReadonly"
            :placeholder="fluctuationPlaceholder"
            @blur="state.saveQualitativeNotes()"
          />
        </div>
        <div class="qual-item">
          <label>(2) 本期转入固定资产情况</label>
          <el-input
            v-model="state.qualitativeNotes.value.transferToFa"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }"
            :disabled="isReadonly"
            :placeholder="`本期转固合计参考 H2-2：${fmtAmt(state.transferFromH22.value)} 元；请说明项目及与 H2-5 勾稽…`"
            @blur="state.saveQualitativeNotes()"
          />
        </div>
        <div class="qual-item">
          <label>(3) 其他说明</label>
          <el-input
            v-model="state.qualitativeNotes.value.other"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }"
            :disabled="isReadonly"
            placeholder="减值迹象、BOT 等特殊事项、与程序表/附注相关说明…"
            @blur="state.saveQualitativeNotes()"
          />
        </div>
      </div>
      <el-divider content-position="left">综合说明</el-divider>
      <el-input
        v-model="state.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="概述取数来源、勾稽结果、重大调整及风险应对…"
        :disabled="isReadonly"
        @blur="state.saveNote(state.auditNote.value)"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>审计结论</span>
          <div v-if="!isReadonly" class="conclusion-actions">
            <el-button size="small" @click="state.applyConclusionTemplate('A')">套用 A</el-button>
            <el-button size="small" @click="state.applyConclusionTemplate('B')">套用 B</el-button>
            <el-button size="small" type="warning" @click="state.applyConclusionTemplate('C')">套用 C</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="state.auditConclusion.value"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="参考：A、未见异常。 B、除上述重大不符事项应当作为调整事项予以调整外，其余未见异常。 C、由于存在重大未调整事项或范围限制，不可确认。"
        :disabled="isReadonly"
        @blur="state.saveConclusion(state.auditConclusion.value)"
      />
    </el-card>

    <div v-if="!isReadonly" class="action-bar">
      <el-button type="primary" :loading="publishing" @click="handlePublish">
        确认审定 → 回写TB
      </el-button>
    </div>

    <details class="edit-tips">
      <summary>编制提示（对齐致同源模板）</summary>
      <ul>
        <li>结构：一、原值 → 二、减值准备 → 三、净值；列组为期初/期末×未审·账项调整·审定 + 变动额/率。</li>
        <li>审定数=未审数+账项调整；净值=原值−减值（身份校验自动执行）。</li>
        <li>优先「从 H2-2 同步工程」带入未审/审定；H2-3 确认后回写期末账项调整（按未审权重分摊）。</li>
        <li>工具栏显示 TB·1604 未审/审定；未审合计与 TB 差异超容差时黄色提示。</li>
        <li>「从 TB 带入工程物资」写入 1605 核对行；「确认审定」回写 trial_balance(1604) 并发布 EventBus。</li>
        <li>三角勾稽（期末=期初+增加−减少−转固）在 H2-2 实施，本表展示异常。</li>
        <li>净值变动率≥{{ state.CHANGE_RATE_THRESHOLD }}% 须在说明(1)解释；转固情况填入说明(2)。</li>
        <li>BOT 业务按《企业会计准则解释第2号》判断确认为无形资产或长期应收款。</li>
        <li>「带入调整」：从集中登记按科目 1604 拉取调整分录（资产借方净额=借−贷），逐笔分配到各工程的期末账项调整（增量累加），带入后审定数自动更新并联动附注。</li>
      </ul>
    </details>

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="1604 在建工程"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * H2TabAdjudication.vue — H2-1 审定表
 * 对齐致同：原值 / 减值 / 净值 + 试算核对 + 结构化说明 + 结论 A/B/C
 */
import { ref, computed, inject, toRef, defineComponent, h, onMounted } from 'vue'
import { Download } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox, ElTable, ElTableColumn, ElInputNumber, ElButton } from 'element-plus'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
import {
  buildHSeedCells,
  getHSeedSpec,
  readHSegmentPrefill,
  applyHSeedCells,
  type HSeedRowAdapter,
} from '../../composables/hCycleAdjudicationSeed'
import {
  planAdjudicationPrefill,
  resolveAdjPrefillWrites,
  describeAdjPrefillPlan,
  describeAdjPrefillConflicts,
  planHasWork,
} from '../../composables/shared/adjudicationPrefillPlan'
import {
  useH2Adjudication,
  type H2AdjudicationBlock,
  type H2AdjudicationRow,
} from '../../composables/useH2Adjudication'
import { useH2CrossSheet } from '../../composables/useH2CrossSheet'
import { cacheH2CipSnapshot, parseH2CipFromAdjudicatedEvent } from '../../composables/h2CipBridge'
import { useAuditContext } from '@/composables/useAuditContext'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import WpSemanticAccountSourcePanel from '../../shared/WpSemanticAccountSourcePanel.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  htmlData?: any
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const publishing = ref(false)

const allResponsesRef = computed(() => props.allResponses)
const { adjustmentSync, detailTotals, transferSummary } = useH2CrossSheet(allResponsesRef as any)
const h23Sync = computed(() => adjustmentSync.value)

/** 从 render-config htmlData.tb_values 解析 1604/1605 */
function parseTbFromHtml(html: any) {
  const tv = html?.tb_values || {}
  return {
    unadjusted_amount: Number(tv.cip_1604_unadjusted ?? tv.cip_unadjusted ?? 0) || 0,
    audited_amount: Number(tv.cip_1604_audited ?? tv.cip_audited ?? 0) || 0,
    materials_unadjusted: Number(tv.eng_mat_1605_unadjusted ?? tv.eng_mat_unadjusted ?? 0) || 0,
    materials_audited: Number(tv.eng_mat_1605_audited ?? tv.eng_mat_audited ?? 0) || 0,
  }
}

const tbData = ref(parseTbFromHtml(props.htmlData))

async function refreshTbFromApi() {
  if (!props.projectId) return
  try {
    const res = await http.get(`/api/projects/${props.projectId}/trial-balance`, {
      params: { account_prefix: '160' },
      _silent: true,
    } as any)
    const list: any[] = Array.isArray(res?.data ?? res)
      ? (res?.data ?? res)
      : (res?.data?.items ?? [])
    let unadjusted = 0
    let audited = 0
    let matUnadj = 0
    let matAud = 0
    for (const item of list) {
      const code = String(item.standard_account_code ?? item.account_code ?? '')
      if (code === '1604' || code.startsWith('1604')) {
        unadjusted += Number(item.unadjusted_amount ?? 0)
        audited += Number(item.audited_amount ?? 0)
      } else if (code === '1605' || code.startsWith('1605')) {
        matUnadj += Number(item.unadjusted_amount ?? 0)
        matAud += Number(item.audited_amount ?? 0)
      }
    }
    // htmlData 有种子时优先保留非零种子，API 覆盖
    const seeded = parseTbFromHtml(props.htmlData)
    tbData.value = {
      unadjusted_amount: unadjusted || seeded.unadjusted_amount,
      audited_amount: audited || seeded.audited_amount,
      materials_unadjusted: matUnadj || seeded.materials_unadjusted,
      materials_audited: matAud || seeded.materials_audited,
    }
  } catch {
    tbData.value = parseTbFromHtml(props.htmlData)
  }
}

onMounted(() => {
  void refreshTbFromApi()
})

const state = useH2Adjudication({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
  isReadonly: toRef(props, 'isReadonly'),
  tbData: tbData as any,
  detailTotals,
  transferSummary,
  onSave: (itemId: string, value: any) => {
    const existing = props.allResponses.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    const remark = typeof value === 'string' ? value : JSON.stringify(value)
    props.allResponses.set(itemId, { ...existing, item_id: itemId, remark })
    saveResponse(itemId, value)
  },
  onWritebackTB: async (auditedAmount: number) => {
    try {
      await http.put(`/api/projects/${props.projectId}/trial-balance/writeback`, {
        account_code: '1604',
        audited_amount: auditedAmount,
      })
      tbData.value = { ...tbData.value, audited_amount: auditedAmount }
      ElMessage.success('已回写试算平衡表 1604')
    } catch {
      ElMessage.warning('审定数回写失败，请手动确认试算表数据')
    }
  },
  onPublishEvent: (event, payload) => {
    const detail = { ...(payload || {}), projectId: props.projectId }
    eventBus.emit(event as any, detail)
    // 供 H4 国企披露跨底稿回放 CIP 三栏
    if (event === 'substantive:adjudicated') {
      const snap = parseH2CipFromAdjudicatedEvent(detail)
      if (snap && props.projectId) cacheH2CipSnapshot(props.projectId, snap)
    }
  },
})

const h23AdjDiff = computed(
  () => state.costTotalRow.value.endAdjustment - h23Sync.value.cipAjeNet,
)

// ─── 从集中登记带入调整（1604 在建工程，资产借方；单一账项调整列→带入期末账项调整，增量累加） ───
const bringInRows = computed(() =>
  state.costDetailRows.value.map((r) => ({ rowKey: r.rowId, name: r.name, aje: 0, rje: 0 })),
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
  subjectPrefix: '1604',
  direction: 'debit',
  subjectCode: '1604',
  wpCode: 'H2',
  subjectLabel: '在建工程(1604)',
  rows: bringInRows,
  // 单一账项调整列：忽略 field，读期末账项调整实时值增量累加
  updateCell: (rowKey: string, _field: any, value: number) => {
    const r = state.costDetailRows.value.find((x) => x.rowId === rowKey)
    const cur = Number(r?.endAdjustment) || 0
    state.updateCell('cost', rowKey, 'endAdjustment', cur + value)
  },
  totalAudited: () => state.costTotalRow.value.endAudited,
})

const costDisplayRows = computed(() => [
  ...state.costDetailRows.value,
  state.costTotalRow.value,
])
const impairDisplayRows = computed(() => [
  ...state.impairDetailRows.value,
  state.impairTotalRow.value,
])

const fluctuationPlaceholder = computed(() => {
  const names = state.significantNetChanges.value.map((r) => r.name).join('、')
  return names
    ? `以下工程净值变动率≥${state.CHANGE_RATE_THRESHOLD}%：${names}。请说明主要原因…`
    : `若净值变动率≥${state.CHANGE_RATE_THRESHOLD}%，请说明主要原因…`
})

function netRowClass({ row }: { row: { isTotal?: boolean; isSignificant?: boolean } }) {
  if (row.isTotal) return 'total-row'
  if (row.isSignificant) return 'significant-row'
  return ''
}

function onCellChange(block: H2AdjudicationBlock, rowId: string, field: string, value: number) {
  state.updateCell(block, rowId, field, value ?? 0)
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入工程项目名称', '新增工程', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    if (value) state.addProjectRow(value)
  } catch {
    /* cancelled */
  }
}

function handleRemoveRow(rowId: string) {
  state.removeProjectRow(rowId)
}

function handleSyncFromH22() {
  const res = state.syncFromH22('overwrite')
  if (res.applied) ElMessage.success(res.message)
  else ElMessage.warning(res.message)
}

function handleSyncFromH23() {
  const res = state.syncEndAdjustmentFromH23(h23Sync.value.cipAjeNet)
  if (res.applied) ElMessage.success(res.message)
  else ElMessage.warning(res.message)
}

// ─── 从四表库带入未审数（1604 叶子子科目 → 工程行）─────────────────────────
// 后端 `adjudication_segment_prefill` 在改造前是全平台 dead output（零消费方），
// 这里是它的第一个消费点。手工优先 / 幂等 / 不兜底三条由共享件保证。
const hSeedSpec = getHSeedSpec('H2')

const fourTableSeed = computed(() => {
  const payload = readHSegmentPrefill(props.htmlData)
  if (!payload || !hSeedSpec) return null
  return buildHSeedCells(hSeedSpec, payload)
})

const hasFourTableSeed = computed(() => (fourTableSeed.value?.cells.length ?? 0) > 0)

/** 行键（工程名）→ rowId；建行走 `addProjectRow`（同时建原值+减值两行） */
const h2SeedAdapter: HSeedRowAdapter = {
  findRowId: (rowKey) =>
    state.costRows.value.find((r) => !r.isTotal && !r.isSubtotal && r.name === rowKey)?.rowId ??
    null,
  createRow: (rowKey) => {
    state.addProjectRow(rowKey)
    return state.costRows.value.find((r) => r.name === rowKey)?.rowId ?? null
  },
  writeCell: (rowId, field, amount) => {
    state.updateCell('cost', rowId, field, amount)
  },
}

async function handleSeedFromFourTable() {
  if (props.isReadonly) return
  const built = fourTableSeed.value
  if (!built || built.cells.length === 0) {
    ElMessage.info('四表库暂无在建工程明细子科目，或该科目未导入')
    return
  }

  const plan = planAdjudicationPrefill(
    built.cells,
    (cell) => {
      const row = state.costRows.value.find(
        (r) => !r.isTotal && !r.isSubtotal && r.name === cell.rowKey,
      )
      if (!row) return null
      const v = (row as unknown as Record<string, unknown>)[cell.field]
      // 0 视为「未填」——审定表新建行的数值字段默认就是 0
      return v === 0 ? null : (v as number | null)
    },
    { unclassified: built.unclassified, absentSlots: built.absentSlots },
  )

  if (!planHasWork(plan)) {
    ElMessage.info(describeAdjPrefillPlan(plan))
    return
  }

  let mode: AdjPrefillMode = 'fill-blank'
  if (plan.conflicts.length > 0) {
    try {
      await ElMessageBox.confirm(
        `以下单元格已有录入且与四表库不一致：\n\n${describeAdjPrefillConflicts(plan)}\n\n选择「覆盖」将以四表库金额替换，选择「仅补空值」保留现有录入。`,
        '手工录入与四表库不一致',
        {
          type: 'warning',
          confirmButtonText: '覆盖',
          cancelButtonText: '仅补空值',
          distinguishCancelAndClose: true,
        },
      )
      mode = 'overwrite'
    } catch (e) {
      if (e === 'close') return // 点 ✕ = 取消整个操作
      mode = 'fill-blank'
    }
  }

  const toWrite = resolveAdjPrefillWrites(plan, mode)
  const res = applyHSeedCells(toWrite, h2SeedAdapter)

  const parts = [describeAdjPrefillPlan(plan)]
  if (res.created > 0) parts.push(`新建 ${res.created} 个工程行`)
  if (res.failed.length > 0) {
    parts.push(`${res.failed.length} 格建行失败未写入`)
    ElMessage.warning(parts.join('；'))
    return
  }
  ElMessage.success(parts.join('；'))
}

async function handleSeedMaterials() {
  const soft = state.seedMaterialsFromTb('fillEmpty')
  if (soft.applied) {
    ElMessage.success(soft.message)
    return
  }
  if (soft.message.includes('已有录入')) {
    try {
      await ElMessageBox.confirm('工程物资已有数据，是否用 TB 覆盖？', '强制带入', {
        type: 'warning',
        confirmButtonText: '覆盖',
        cancelButtonText: '取消',
      })
    } catch {
      return
    }
    const hard = state.seedMaterialsFromTb('overwrite')
    if (hard.applied) ElMessage.success(hard.message)
    else ElMessage.warning(hard.message)
    return
  }
  ElMessage.warning(soft.message)
}

async function handlePublish() {
  publishing.value = true
  try {
    await state.publishAdjudicated()
  } finally {
    publishing.value = false
  }
}

function openReview(id: string) {
  openReviewDialog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRate(val: number | null | undefined): string {
  if (val == null) return '-'
  return `${val.toFixed(1)}%`
}

/** 原值/减值共用金额表 */
const AdjAmountTable = defineComponent({
  name: 'H2AdjAmountTable',
  props: {
    rows: { type: Array as () => H2AdjudicationRow[], required: true },
    isReadonly: { type: Boolean, default: false },
    block: { type: String as () => H2AdjudicationBlock, required: true },
  },
  emits: ['cell-change', 'remove'],
  setup(p, { emit }) {
    function rowClass({ row }: { row: H2AdjudicationRow }) {
      if (row.isTotal) return 'total-row'
      if (row.isSignificant) return 'significant-row'
      return ''
    }
    function cell(
      row: H2AdjudicationRow,
      field: keyof H2AdjudicationRow,
      editable: boolean,
    ) {
      if (editable && row.isEditable && !row.isTotal && !p.isReadonly) {
        return h(ElInputNumber, {
          modelValue: row[field] as number,
          controls: false,
          size: 'small',
          class: 'amt-input',
          onChange: (v: number | undefined) =>
            emit('cell-change', p.block, row.rowId, field, v ?? 0),
        })
      }
      const isFormula =
        field === 'beginAudited' ||
        field === 'endAudited' ||
        field === 'unadjustedChange' ||
        field === 'auditedChange'
      return h(
        'span',
        {
          class: isFormula ? 'formula-cell amt-cell' : 'amt-cell',
          title: isFormula ? '审定=未审+账项调整' : undefined,
        },
        fmtAmt(row[field] as number),
      )
    }
    function rateCell(row: H2AdjudicationRow, field: 'unadjustedChangeRate' | 'auditedChangeRate') {
      return h(
        'span',
        { class: { 'rate-significant': row.isSignificant && field === 'auditedChangeRate' } },
        fmtRate(row[field]),
      )
    }

    return () =>
      h(
        ElTable,
        {
          data: p.rows,
          border: true,
          stripe: true,
          size: 'small',
          class: 'adj-table',
          rowClassName: rowClass,
        },
        {
          default: () => [
            h(ElTableColumn, { prop: 'name', label: '项目', minWidth: 140, fixed: true }),
            h(ElTableColumn, { label: '期初数', align: 'center' }, {
              default: () => [
                h(ElTableColumn, { label: '未审数', minWidth: 110, align: 'right' }, {
                  default: ({ row }: { row: H2AdjudicationRow }) =>
                    cell(row, 'beginUnadjusted', true),
                }),
                h(ElTableColumn, { label: '账项调整', minWidth: 110, align: 'right' }, {
                  default: ({ row }: { row: H2AdjudicationRow }) =>
                    cell(row, 'beginAdjustment', true),
                }),
                h(ElTableColumn, { label: '审定数', minWidth: 110, align: 'right' }, {
                  default: ({ row }: { row: H2AdjudicationRow }) =>
                    cell(row, 'beginAudited', false),
                }),
              ],
            }),
            h(ElTableColumn, { label: '期末数', align: 'center' }, {
              default: () => [
                h(ElTableColumn, { label: '未审数', minWidth: 110, align: 'right' }, {
                  default: ({ row }: { row: H2AdjudicationRow }) =>
                    cell(row, 'endUnadjusted', true),
                }),
                h(ElTableColumn, { label: '账项调整', minWidth: 110, align: 'right' }, {
                  default: ({ row }: { row: H2AdjudicationRow }) =>
                    cell(row, 'endAdjustment', true),
                }),
                h(ElTableColumn, { label: '审定数', minWidth: 110, align: 'right' }, {
                  default: ({ row }: { row: H2AdjudicationRow }) =>
                    cell(row, 'endAudited', false),
                }),
              ],
            }),
            h(ElTableColumn, { label: '本期变动', align: 'center' }, {
              default: () => [
                h(ElTableColumn, { label: '未审变动', minWidth: 110, align: 'right' }, {
                  default: ({ row }: { row: H2AdjudicationRow }) =>
                    cell(row, 'unadjustedChange', false),
                }),
                h(ElTableColumn, { label: '未审变动率', minWidth: 90, align: 'right' }, {
                  default: ({ row }: { row: H2AdjudicationRow }) =>
                    rateCell(row, 'unadjustedChangeRate'),
                }),
                h(ElTableColumn, { label: '审定变动', minWidth: 110, align: 'right' }, {
                  default: ({ row }: { row: H2AdjudicationRow }) =>
                    cell(row, 'auditedChange', false),
                }),
                h(ElTableColumn, { label: '审定变动率', minWidth: 90, align: 'right' }, {
                  default: ({ row }: { row: H2AdjudicationRow }) =>
                    rateCell(row, 'auditedChangeRate'),
                }),
              ],
            }),
            !p.isReadonly
              ? h(ElTableColumn, { label: '', width: 50 }, {
                  default: ({ row }: { row: H2AdjudicationRow }) =>
                    row.isEditable && !row.isTotal
                      ? h(
                          ElButton,
                          {
                            size: 'small',
                            type: 'danger',
                            link: true,
                            onClick: () => emit('remove', row.rowId),
                          },
                          () => '✕',
                        )
                      : null,
                })
              : null,
          ],
        },
      )
  },
})
</script>

<style scoped>
.h2-tab-adjudication { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; gap: 8px; flex-wrap: wrap; }
.toolbar-left, .toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.section-hint { font-size: 12px; color: var(--el-text-color-secondary); font-weight: 400; }
.adj-table { font-size: var(--wp-font-size, 13px); }
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.rate-significant { color: var(--el-color-danger); font-weight: 600; }
.net-hint { margin: 10px 0 0; font-size: 12px; color: var(--el-text-color-secondary); }
.add-row-bar { margin-top: 12px; }
.audit-note-card { margin-bottom: 12px; }
.qual-grid { display: flex; flex-direction: column; gap: 12px; margin-bottom: 8px; }
.qual-item label { display: block; margin-bottom: 4px; font-size: 13px; font-weight: 500; }
.req-hint { color: var(--el-color-danger); font-weight: 400; font-size: 12px; }
.conclusion-actions { display: flex; gap: 6px; }
.cross-alert { margin-bottom: 12px; }
.action-bar { margin-top: 16px; text-align: right; }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
:deep(.total-row) { font-weight: 600; background-color: var(--el-fill-color-light) !important; }
:deep(.significant-row) { background-color: var(--el-color-danger-light-9) !important; }
</style>

