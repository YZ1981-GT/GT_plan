<!--
  G3TabAdjudication.vue — G3-1 审定表（按被投资方分行 + 同比分析）

  借方科目 1131 应收股利：
    期初审定 = 期初未审 + AJE + RJE（期初 AJE/RJE 仅用于前期差错/重述）
    期末未审 = 期初审定 + 本期宣告(借方) - 本期收回(贷方)
    期末审定 = 期末未审 + AJE + RJE
    变动额/率 = 期末审定 vs 期初审定；|变动率|>30% 原因分析必填

  行结构：被投资方逐行(动态增删) + 合计(加粗) + 试算表数 + 差异
  账龄条：参照 G3-5 拆分一年内 / 一年以上（对齐 Excel 模板口径）

  Spec: .kiro/specs/g3-dividend-receivable/ Task 6.1
  Requirements: 3.1~3.10
-->
<template>
  <div class="g3-adjudication">
    <div class="section-head">
      <h3 class="sheet-title">G3-1 应收股利审定表</h3>
      <div class="head-actions tab-toolbar">
        <el-button size="small" type="primary" plain :loading="adjPull.loading.value" @click="openBringInAdjustment">
          <el-icon><Download /></el-icon>带入调整
        </el-button>
        <el-button size="small" :disabled="isReadonly" @click="adj.addRow()">＋ 新增被投资方</el-button>
        <el-button size="small" :disabled="isReadonly" @click="onSyncFromDetail">从 G3-2 汇总</el-button>
        <el-button size="small" :disabled="isReadonly || !projectId" :loading="tbLoading" @click="onFetchTb">
          取试算 1131
        </el-button>
        <el-button
          size="small"
          :type="showOpeningAdj ? 'warning' : 'default'"
          @click="showOpeningAdj = !showOpeningAdj"
        >
          {{ showOpeningAdj ? '隐藏期初调整列' : '显示期初调整列' }}
        </el-button>
        <G3ImportExportDropdown
          v-if="wpId"
          :wp-id="wpId"
          sheet="G3-1"
          :disabled="isReadonly"
          @imported="emit('imported')"
        />
        <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('G3-1-adjudication')">💬复核</el-button>
        <GtIndexChip value="wp:G3-1" :context-project-id="projectId" />
        <el-tag size="small" type="info">共 {{ adj.dataRows.value.length }} 行</el-tag>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：核实应收股利各被投资方期初/期末审定金额的准确性与完整性，分析重大波动与一年以上款项可收回性，验证与调整分录、试算平衡表的勾稽一致，为报表列报提供审定依据。"
    />

    <el-alert
      v-if="adj.hasOpeningAdjustments.value && !showOpeningAdj"
      type="warning"
      :closable="false"
      show-icon
      class="objective-alert"
      title="检测到非零期初账项/重分类调整。期初调整仅用于前期差错更正或重述；可点「显示期初调整列」查看并复核。"
    />

    <!-- 四表库取数溯源（口径：期末余额） -->

    <WpFourTableSourcePanel

      :source-codes="tbSourceCodes"

      gross-label="应收股利"

    />


    <el-table
      :data="tableData"
      border
      size="small"
      max-height="480"
      :row-class-name="rowClassName"
    >
      <!-- 被投资方名称 -->
      <el-table-column label="被投资方名称" width="160" fixed>
        <template #default="{ row }">
          <span v-if="row._type !== 'data'" :class="rowLabelClass(row)">{{ row.investeeName }}</span>
          <el-input
            v-else
            :model-value="row.investeeName"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => adj.updateCell(row.id, 'investeeName', v)"
          />
        </template>
      </el-table-column>

      <!-- 持股比例 -->
      <el-table-column label="持股比例(%)" width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row._type === 'data'"
            :model-value="row.shareholdingRatio"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            :precision="2"
            style="width:100%"
            @update:model-value="(v: number) => adj.updateCell(row.id, 'shareholdingRatio', v ?? 0)"
          />
          <span v-else :class="rowLabelClass(row)" />
        </template>
      </el-table-column>

      <!-- 期初 -->
      <el-table-column label="期初">
        <el-table-column label="未审" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row._type === 'data'"
              :model-value="row.openingUnadjusted"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              style="width:100%"
              @update:model-value="(v: number) => adj.updateCell(row.id, 'openingUnadjusted', v ?? 0)"
            />
            <span v-else :class="rowLabelClass(row)">{{ fmtNum(row.openingUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column
          v-if="showOpeningAdj"
          label="AJE（前期差错）"
          width="110"
          align="right"
        >
          <template #header>
            <span title="仅用于前期差错更正/重述；常规项目期初应等于上期审定期末">AJE（前期差错）</span>
          </template>
          <template #default="{ row }">
            <el-input-number
              v-if="row._type === 'data'"
              :model-value="row.openingAJE"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              style="width:100%"
              @update:model-value="(v: number) => adj.updateCell(row.id, 'openingAJE', v ?? 0)"
            />
            <span v-else :class="rowLabelClass(row)">{{ fmtNum(row.openingAJE) }}</span>
          </template>
        </el-table-column>
        <el-table-column
          v-if="showOpeningAdj"
          label="RJE（重述）"
          width="100"
          align="right"
        >
          <template #header>
            <span title="仅用于前期重分类重述">RJE（重述）</span>
          </template>
          <template #default="{ row }">
            <el-input-number
              v-if="row._type === 'data'"
              :model-value="row.openingRJE"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              style="width:100%"
              @update:model-value="(v: number) => adj.updateCell(row.id, 'openingRJE', v ?? 0)"
            />
            <span v-else :class="rowLabelClass(row)">{{ fmtNum(row.openingRJE) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定" width="120" align="right">
          <template #default="{ row }">
            <span
              :class="[rowLabelClass(row), { 'formula-cell': row._type === 'data' }]"
              :title="row._type === 'data' ? '期初审定 = 期初未审 + AJE + RJE（无前期差错时等于上期期末审定）' : ''"
            >
              {{ fmtNum(row.openingAdjusted) }}
            </span>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- 本期宣告(借方) -->
      <el-table-column label="本期宣告(借方)" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row._type === 'data'"
            :model-value="row.currentDeclared"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => adj.updateCell(row.id, 'currentDeclared', v ?? 0)"
          />
          <span v-else :class="rowLabelClass(row)">{{ fmtNum(row.currentDeclared) }}</span>
        </template>
      </el-table-column>

      <!-- 本期收回(贷方) -->
      <el-table-column label="本期收回(贷方)" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row._type === 'data'"
            :model-value="row.currentReceived"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => adj.updateCell(row.id, 'currentReceived', v ?? 0)"
          />
          <span v-else :class="rowLabelClass(row)">{{ fmtNum(row.currentReceived) }}</span>
        </template>
      </el-table-column>

      <!-- 期末 -->
      <el-table-column label="期末">
        <el-table-column label="未审" width="120" align="right">
          <template #default="{ row }">
            <span
              :class="[rowLabelClass(row), { 'formula-cell': row._type === 'data' }]"
              :title="row._type === 'data' ? '期末未审 = 期初审定 + 本期宣告 - 本期收回' : ''"
            >
              {{ fmtNum(row.closingUnadjusted) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row._type === 'data'"
              :model-value="row.closingAJE"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              style="width:100%"
              @update:model-value="(v: number) => adj.updateCell(row.id, 'closingAJE', v ?? 0)"
            />
            <span v-else :class="rowLabelClass(row)">{{ fmtNum(row.closingAJE) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RJE" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row._type === 'data'"
              :model-value="row.closingRJE"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              style="width:100%"
              @update:model-value="(v: number) => adj.updateCell(row.id, 'closingRJE', v ?? 0)"
            />
            <span v-else :class="rowLabelClass(row)">{{ fmtNum(row.closingRJE) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定" width="120" align="right">
          <template #default="{ row }">
            <span
              :class="[rowLabelClass(row), { 'formula-cell': row._type === 'data' }]"
              :title="row._type === 'data' ? '期末审定 = 期末未审 + AJE + RJE' : ''"
            >
              {{ fmtNum(row.closingAdjusted) }}
            </span>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- 同比分析（期末审定 vs 期初审定） -->
      <el-table-column label="同比（审定）">
        <el-table-column label="变动额" width="110" align="right">
          <template #default="{ row }">
            <span
              v-if="row._type === 'data' || row._type === 'subtotal'"
              :class="[rowLabelClass(row), 'formula-cell']"
              title="变动额 = 期末审定 − 期初审定"
            >
              {{ fmtNum(row.changeAmount) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="变动率" width="90" align="right">
          <template #default="{ row }">
            <span
              v-if="row._type === 'data' || row._type === 'subtotal'"
              :class="[
                rowLabelClass(row),
                'formula-cell',
                { 'rate-orange': row.changeRateHighlight },
              ]"
              title="|变动率|&gt;30% 须填写原因分析"
            >
              {{ fmtRate(row.changeRate) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="原因分析" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="row._type === 'data'"
              :model-value="row.reasonAnalysis"
              size="small"
              :disabled="isReadonly"
              :class="{ 'reason-required': row.reasonRequired && !String(row.reasonAnalysis || '').trim() }"
              :placeholder="row.reasonRequired ? '变动率&gt;30%，必填' : ''"
              @change="(v: string) => adj.updateCell(row.id, 'reasonAnalysis', v)"
            />
          </template>
        </el-table-column>
      </el-table-column>

      <!-- 备注 -->
      <el-table-column label="备注" width="140">
        <template #default="{ row }">
          <el-input
            v-if="row._type === 'data'"
            :model-value="row.remark"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => adj.updateCell(row.id, 'remark', v)"
          />
        </template>
      </el-table-column>

      <!-- 索引 -->
      <el-table-column label="索引" width="100">
        <template #default="{ row }">
          <GtIndexChip
            v-if="row._type === 'data' && row.indexRef"
            :value="row.indexRef"
          />
          <el-input
            v-else-if="row._type === 'data'"
            :model-value="row.indexRef"
            size="small"
            :disabled="isReadonly"
            placeholder="索引"
            @change="(v: string) => adj.updateCell(row.id, 'indexRef', v)"
          />
        </template>
      </el-table-column>

      <!-- 操作列(删除) -->
      <el-table-column v-if="!isReadonly" label="" width="50" align="center">
        <template #default="{ row }">
          <el-icon
            v-if="row._type === 'data'"
            class="delete-icon"
            @click="adj.removeRow(row.id)"
          >
            <Delete />
          </el-icon>
        </template>
      </el-table-column>
    </el-table>

    <!-- 账龄汇总条（对齐 Excel 一年内/一年以上） -->
    <div class="aging-strip" :class="{ 'aging-warn': adj.agingSummary.value.overAgeExceedsTotal }">
      <span class="aging-title">账龄汇总（对照 Excel / 勾稽 G3-5）</span>
      <span>一年以内：{{ fmtNum(adj.agingSummary.value.within1YearAmount) }}</span>
      <span>
        一年以上：{{ fmtNum(adj.agingSummary.value.over1YearAmount) }}
        <template v-if="adj.agingSummary.value.over1YearCount">
          （{{ adj.agingSummary.value.over1YearCount }} 笔）
        </template>
      </span>
      <span class="aging-hint">
        <template v-if="adj.agingSummary.value.source === 'empty'">
          尚未从 G3-5 取到逾期明细；一年以上默认为 0，请在 G3-5 填写约定付款日与应收金额。
        </template>
        <template v-else-if="adj.agingSummary.value.overAgeExceedsTotal">
          一年以上金额大于期末审定合计，请核对 G3-5 与 G3-1 是否一致。
        </template>
        <template v-else>
          一年以上 = G3-5 逾期≥365 天金额合计；一年以内 = 期末审定合计 − 一年以上。明细见 G3-5。
        </template>
      </span>
    </div>

    <!-- 试算表数 + 差异 -->
    <div class="tb-diff-row">
      <span class="tb-label">试算平衡表数（1131）：</span>
      <el-input-number
        :model-value="adj.trialBalanceAmount.value"
        size="small"
        :controls="false"
        :disabled="isReadonly"
        style="width:140px"
        @update:model-value="(v: number) => adj.setTrialBalance(v ?? 0)"
      />
      <span :class="['diff-value', { 'diff-red': adj.hasVarianceHighlight.value }]">
        差异：{{ fmtNum(adj.variance.value) }}
        <template v-if="!adj.hasVarianceHighlight.value"> ✓</template>
        <template v-else> ✗</template>
      </span>
      <el-tag v-if="adj.hasReasonGaps.value" size="small" type="warning">存在未填波动原因</el-tag>
    </div>

    <G3AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      :note="adj.auditNote.value"
      :conclusion="adj.auditConclusion.value"
      @update:note="(v: string) => { adj.auditNote.value = v }"
      @update:conclusion="(v: string) => { adj.auditConclusion.value = v }"
      note-ai-section="adjudication-note"
      conclusion-ai-section="adjudication-conclusion"
      :related-context="{
        审定合计: adj.subtotalRow.value?.closingAdjusted,
        试算表数: adj.trialBalanceAmount.value,
        差异: adj.variance.value,
        一年以内: adj.agingSummary.value.within1YearAmount,
        一年以上: adj.agingSummary.value.over1YearAmount,
        合计变动率: adj.subtotalRow.value?.changeRate,
      }"
      note-placeholder="填写审计说明：（1）期初/期末变动比例超过30%的原因（金额、业务背景）；（2）对账龄一年以上的应收股利，说明对方情况、长期挂账原因及可收回性/减值判断（索引 G3-5）；（3）其他需说明事项。"
      note-hint="须覆盖重大波动（>30%）、一年以上款项可收回性及试算勾稽/调整事项。"
      conclusion-hint="按 A/B/C 口径评价科目 1131 审定结果。"
    />

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示（对齐致同模板 + CAS）</summary>
      <div class="guidance-content">
        <p>1. 按被投资方立行审定（优于仅按账龄汇总）；账龄一年内/一年以上由上表汇总条对照 G3-5 勾稽，服务披露与可收回性评价。</p>
        <p>2. 借方科目 1131：期初审定 = 期初未审 + AJE + RJE。期初 AJE/RJE 默认隐藏，仅前期差错更正或重述时启用。</p>
        <p>3. 期末未审 = 期初审定 + 本期宣告(借方) − 本期收回(贷方)；期末审定 = 期末未审 + AJE + RJE。</p>
        <p>4. 变动额/变动率按期末审定 vs 期初审定自动计算；|变动率|&gt;30% 须填原因分析并在审计说明中展开。</p>
        <p>5. 特别风险关注：关联方分红与资金占用、异常或复杂交易、重大会计估计（减值）。证据索引链至 G3-2/G3-4/G3-5/G3-3。</p>
        <p>6. 合计行审定金额应与试算平衡表数(1131)核对一致；可点「取试算 1131」；审定变更自动回写试算。G3-3「确认调整」后净调整落入「账项调整汇总」期末 AJE/RJE，并联动调整分录模块。</p>
        <p>7. 「带入调整」：可从集中登记按科目 1131 拉取调整分录，逐笔分配到各被投资方行的期末 AJE/RJE，带入后审定数自动更新并联动附注。</p>
        <p class="cas-basis">CAS 依据：《中国注册会计师审计准则第 1301 号——审计证据》、《中国注册会计师审计准则第 1323 号——关联方》、《企业会计准则第 2 号——长期股权投资》及相关减值规定。</p>
      </div>
    </details>

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="1131 应收股利"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, toRef, inject } from 'vue'
import { Delete, Download } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useG3Adjudication } from '../composables/useG3Adjudication'
import type { G3AdjudicationRow } from '../composables/useG3Adjudication'
import { useAuditContext } from '@/composables/useAuditContext'
import { useAdjudicationBringIn } from '../composables/useAdjudicationBringIn'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import GtIndexChip from '../GtIndexChip.vue'
import G3ImportExportDropdown from './G3ImportExportDropdown.vue'
import G3AuditTextCards from './G3AuditTextCards.vue'
import type { ChecklistResponse } from '../composables/useF1FormData'
import WpFourTableSourcePanel from '../shared/WpFourTableSourcePanel.vue'

const props = defineProps<{
  /** render 下发的本 sheet html_data（含 tb_source_codes） */
  htmlData?: Record<string, any> | null
  wpId: string
  projectId: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  /** 审计年度（取试算 1131 必填） */
  auditYear?: number | string | null
}>()


/**
 * 四表库取数溯源（消费 render 下发的 `tb_source_codes`，消除 dead output）。
 *
 * 科目由后端按**科目名**逐项目解析（`four_table/g_cycle_specs.G3_SPEC`），
 * 取数口径 = 期末余额。前端单一真源见 `composables/gCycleAccountScope.ts`。
 */
const tbSourceCodes = computed(() => props.htmlData?.tb_source_codes ?? null)
const emit = defineEmits<{ imported: [] }>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const adj = useG3Adjudication({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  auditYear: toRef(props, 'auditYear'),
})

// ─── 从集中登记带入调整（1131 应收股利，资产借方；带入期末 AJE/RJE） ────────────
const bringInRows = computed(() =>
  adj.dataRows.value.map((r) => ({ rowKey: r.id, name: r.investeeName, aje: r.closingAJE, rje: r.closingRJE })),
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
  subjectPrefix: '1131',
  direction: 'debit',
  subjectCode: '1131',
  wpCode: 'G3',
  subjectLabel: '应收股利(1131)',
  rows: bringInRows,
  updateCell: (rowKey: string, field: any, value: number) =>
    adj.updateCell(rowKey, field === 'rje' ? 'closingRJE' : 'closingAJE', value),
  totalAudited: () => adj.subtotalRow.value.closingAdjusted,
})

/** 期初 AJE/RJE 默认收起，减少「期初也会调」的误导 */
const showOpeningAdj = ref(false)

function onSyncFromDetail() {
  const { added, updated } = adj.syncFromDetail()
  if (added + updated === 0) {
    ElMessage.warning('G3-2 明细尚无可汇总的被投资方，请先填写明细表')
    return
  }
  ElMessage.success(`已从 G3-2 汇总：更新 ${updated} 行，新增 ${added} 行（已保留 AJE/RJE）`)
}

const tbLoading = ref(false)
async function onFetchTb() {
  if (props.auditYear == null || props.auditYear === '') {
    ElMessage.warning('缺少审计年度，无法取试算 1131')
    return
  }
  tbLoading.value = true
  try {
    const amount = await adj.fetchTrialBalance()
    if (amount == null) {
      ElMessage.warning('未取到试算 1131，请确认项目已导入试算平衡表')
    } else {
      ElMessage.success(`试算 1131：${fmtNum(amount)}（已写入核对参考）`)
    }
  } finally {
    tbLoading.value = false
  }
}

// ─── Table data: data rows + subtotal + trial balance + variance ───
interface DisplayRow extends G3AdjudicationRow {
  _type: 'data' | 'subtotal' | 'tb' | 'variance'
}

function emptyMeta(
  type: 'tb' | 'variance',
  id: string,
  investeeName: string,
  closingAdjusted: number,
): DisplayRow {
  return {
    id,
    investeeName,
    shareholdingRatio: 0,
    openingUnadjusted: 0,
    openingAJE: 0,
    openingRJE: 0,
    openingAdjusted: 0,
    closingUnadjusted: 0,
    closingAJE: 0,
    closingRJE: 0,
    closingAdjusted,
    currentDeclared: 0,
    currentReceived: 0,
    changeAmount: 0,
    changeRate: '',
    changeRateHighlight: false,
    reasonRequired: false,
    reasonAnalysis: '',
    remark: '',
    indexRef: '',
    _type: type,
  }
}

const tableData = computed<DisplayRow[]>(() => {
  const rows: DisplayRow[] = adj.dataRows.value.map((r) => ({ ...r, _type: 'data' as const }))

  rows.push({
    ...adj.subtotalRow.value,
    _type: 'subtotal',
  })

  rows.push(emptyMeta('tb', 'tb', '试算表数(1131)', adj.trialBalanceAmount.value))
  rows.push(emptyMeta('variance', 'variance', '差异', adj.variance.value))

  return rows
})

function rowClassName({ row }: { row: DisplayRow }): string {
  if (row._type === 'subtotal') return 'row-subtotal'
  if (row._type === 'variance' && adj.hasVarianceHighlight.value) return 'row-variance-red'
  if (row._type === 'tb') return 'row-tb'
  return ''
}

function rowLabelClass(row: DisplayRow): string {
  if (row._type === 'subtotal') return 'row-bold'
  if (row._type === 'variance' && adj.hasVarianceHighlight.value) return 'row-bold diff-red'
  if (row._type === 'tb') return 'row-tb-label'
  return ''
}

function fmtNum(v: unknown): string {
  if (v === 0) return '0.00'
  if (typeof v === 'number') return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return String(v ?? '')
}

function fmtRate(rate: number | '' | 'N/A' | undefined): string {
  if (rate === '' || rate === undefined) return '—'
  if (rate === 'N/A') return 'N/A'
  return `${(rate * 100).toFixed(2)}%`
}
</script>

<style scoped>
.g3-adjudication {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}

.sheet-title {
  margin: 0;
  font-size: 15px;
}

.head-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}

/* 公式列样式：虚线下划线 + cursor:help */
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
}

.rate-orange {
  color: #e6a23c;
  font-weight: 600;
}

.reason-required :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px #e6a23c inset;
}

.row-bold {
  font-weight: 600;
}

.row-tb-label {
  color: #606266;
  font-style: italic;
}

.aging-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 20px;
  align-items: baseline;
  margin: 12px 0 4px;
  padding: 10px 12px;
  background: #f4f9ff;
  border: 1px solid #d9ecff;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
}

.aging-strip.aging-warn {
  background: #fdf6ec;
  border-color: #f5dab1;
}

.aging-title {
  font-weight: 600;
  color: #303133;
}

.aging-hint {
  flex: 1 1 100%;
  color: #909399;
  font-size: 12px;
  line-height: 1.5;
}

/* 试算表数 + 差异行 */
.tb-diff-row {
  display: flex;
  gap: 16px;
  margin: 16px 0;
  align-items: center;
  font-size: var(--wp-font-size, 13px);
  flex-wrap: wrap;
}

.tb-label {
  font-weight: 500;
}

.diff-value {
  font-weight: 600;
}

.diff-red {
  color: #f56c6c;
}

/* 行样式 */
:deep(.row-subtotal) {
  font-weight: 600;
  background-color: #f5f7fa;
}

:deep(.row-variance-red) {
  color: #f56c6c;
  font-weight: 600;
}

:deep(.row-tb) {
  color: #606266;
  font-style: italic;
  background-color: #fafafa;
}

/* 删除图标 */
.delete-icon {
  cursor: pointer;
  color: #909399;
  transition: color 0.2s;
}

.delete-icon:hover {
  color: #f56c6c;
}

/* 审计目标 */
.objective-alert {
  margin-bottom: 12px;
}

/* 编制提示 */
.guidance-details {
  margin-top: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p {
  margin: 2px 0;
}
.guidance-content .cas-basis {
  margin-top: 6px;
  color: #909399;
  font-size: 12px;
}
</style>
