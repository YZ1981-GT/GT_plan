<!--
  I5TabAdjudication.vue — I5-1 其他非流动资产审定表

  对齐致同 Excel：未审滚动 → 账项调整 → 审定；本期 vs 上期变动；
  自 I5-2 带入；AJE 自 I5-3；与 TB 1911 勾稽
-->
<template>
  <div class="i5-adjudication">
    <div class="section-header">
      <span class="section-title">I5-1 其他非流动资产审定表</span>
      <div class="section-actions">
        <el-button size="small" type="default" text @click="handleReview">复核</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>审计目标</template>
      检查其他非流动资产(1911)期末余额的存在性、完整性、准确性及列报恰当性；
      确认分类与期限适当；审定数＝未审＋AJE＋RJE，与试算平衡表勾稽一致。
    </el-alert>

    <div class="methodology-context">
      <p>
        <b>编制逻辑（对齐 Excel I5-1）：</b>
        明细取数(I5-2 原值/减值/净值) → 审定矩阵(期初/期末×未审·账项·重分类·审定) →
        可编辑净值滚动 + I5-3 AJE/RJE → 与 TB 1911 勾稽；变动率上期为 0 显示 N/A。
      </p>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-right">
        <GtIndexChip value="wp:I5-1" :context-project-id="projectId" />
        <el-tag size="small" type="info">{{ rows.length }} 个项目</el-tag>
        <el-tag size="small" type="success">审定 {{ fmtAmount(subtotals.audited) }}</el-tag>
        <el-tag size="small" :type="Math.abs(tbDifference) > 0.01 ? 'danger' : 'success'">
          {{ Math.abs(tbDifference) > 0.01 ? `TB差异 ${fmtAmount(tbDifference)}` : '✓ TB一致' }}
        </el-tag>
        <el-tag v-if="crossCheck.hasWarning" size="small" type="warning">与明细勾稽差异</el-tag>
        <el-button size="small" @click="navigateTo('I5-2')">I5-2 →</el-button>
        <el-button size="small" @click="navigateTo('I5-3')">I5-3 →</el-button>
      </div>
    </div>

    <WpFourTableSourcePanel
      :source-codes="tbSourceCodes"
      :gross-label="sourceConfig.grossLabel"
      :provision-label="sourceConfig.provisionLabel"
      :fallback-row-code="sourceConfig.fallbackRowCode"
      :hints="sourceConfig.hints"
    />

    <el-alert
      v-if="reconciliationStatus === 'mismatch'"
      type="error"
      title="三角勾稽不平：期末 ≠ 期初+增加-减少，请检查数据"
      show-icon
      :closable="false"
      class="adj-warning"
    />
    <el-alert
      v-if="crossCheck.hasWarning"
      type="warning"
      :closable="false"
      show-icon
      class="adj-warning"
      :title="`与 I5-2 勾稽：期初差 ${fmtAmount(crossCheck.beginDiff)} / 期末差 ${fmtAmount(crossCheck.endDiff)} / 审定vs明细 ${fmtAmount(crossCheck.auditedVsDetailDiff)}`"
    />
    <el-alert
      v-if="hasAjeApprox"
      type="warning"
      :closable="false"
      show-icon
      class="adj-warning"
      title="系统近似分摊：部分 AJE/RJE 按未审占比分摊自 I5-3，请按项目人工复核后改数（改后自动清除「近似」标记）"
    />

    <!-- Excel 式期初/期末 × 未审·账项·重分类·审定 + 变动（原值|减值|净值） -->
    <el-card shadow="never" class="layer-card">
      <template #header>
        <div class="card-header">
          <span class="block-title">
            {{ hasThreeLayerDetail ? '审定矩阵（原值 / 减值 / 净值，只读，对齐 Excel I5-1）' : '期初 / 期末审定矩阵（只读）' }}
          </span>
          <el-tag v-if="hasThreeLayerDetail" size="small" type="success">已链 I5-2 三层</el-tag>
        </div>
      </template>
      <el-table
        :data="threeLayerLeadRows"
        border
        size="small"
        class="layer-table"
        max-height="420"
        :row-class-name="leadRowClassName"
      >
        <el-table-column prop="label" label="项目" min-width="160" fixed>
          <template #default="{ row }">
            <strong v-if="row.isSection">{{ row.label }}</strong>
            <span v-else>{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初数" align="center">
          <el-table-column prop="beginUnadj" label="未审数" min-width="96" align="right">
            <template #default="{ row }">{{ row.isSection ? '' : fmtAmount(row.beginUnadj) }}</template>
          </el-table-column>
          <el-table-column prop="beginAje" label="账项调整" min-width="96" align="right">
            <template #default="{ row }">{{ row.isSection ? '' : fmtAmount(row.beginAje) }}</template>
          </el-table-column>
          <el-table-column prop="beginRje" label="重分类调整" min-width="96" align="right">
            <template #default="{ row }">{{ row.isSection ? '' : fmtAmount(row.beginRje) }}</template>
          </el-table-column>
          <el-table-column prop="beginAudited" label="审定数" min-width="96" align="right">
            <template #default="{ row }">{{ row.isSection ? '' : fmtAmount(row.beginAudited) }}</template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期末数" align="center">
          <el-table-column prop="endUnadj" label="未审数" min-width="96" align="right">
            <template #default="{ row }">{{ row.isSection ? '' : fmtAmount(row.endUnadj) }}</template>
          </el-table-column>
          <el-table-column prop="endAje" label="账项调整" min-width="96" align="right">
            <template #default="{ row }">{{ row.isSection ? '' : fmtAmount(row.endAje) }}</template>
          </el-table-column>
          <el-table-column prop="endRje" label="重分类调整" min-width="96" align="right">
            <template #default="{ row }">{{ row.isSection ? '' : fmtAmount(row.endRje) }}</template>
          </el-table-column>
          <el-table-column prop="endAudited" label="审定数" min-width="96" align="right">
            <template #default="{ row }">{{ row.isSection ? '' : fmtAmount(row.endAudited) }}</template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="本期审定与上期审定比较" align="center">
          <el-table-column prop="varianceAmount" label="变动额" min-width="96" align="right">
            <template #default="{ row }">{{ row.isSection ? '' : fmtAmount(row.varianceAmount) }}</template>
          </el-table-column>
          <el-table-column label="变动率" min-width="88" align="right">
            <template #default="{ row }">{{ row.isSection ? '' : formatI5VarianceRate(row.varianceRate) }}</template>
          </el-table-column>
        </el-table-column>
      </el-table>
    </el-card>

    <div class="action-bar">
      <el-button size="small" type="primary" plain :loading="adjPull.loading.value" @click="openBringInAdjustment">
        <el-icon><Download /></el-icon>带入调整
      </el-button>
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="seedFromI52">从 I5-2 带入</el-button>
      <el-button size="small" plain :disabled="isReadonly" @click="syncFromI53">从 I5-3 同步调整</el-button>
      <el-button size="small" plain :disabled="isReadonly" @click="() => applyTbData()">TB写入未审</el-button>
      <el-button size="small" plain :disabled="isReadonly" @click="() => applyPriorFromTb()">写入上期审定</el-button>
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="addRow">+ 新增</el-button>
      <el-button size="small" type="success" :disabled="isReadonly" @click="handleSave">保存并回写</el-button>
    </div>

    <div v-if="useVirtualScroll" class="virtual-toolbar">
      <el-alert type="info" :closable="false" class="virtual-hint">
        行数较多（{{ rows.length }} 行）· {{ browseMode ? '虚拟滚动速览' : '表格编辑' }}模式 · 双击行可切换编辑
      </el-alert>
      <el-button size="small" @click="browseMode = !browseMode">
        {{ browseMode ? '切换表格编辑' : '切换虚拟速览' }}
      </el-button>
    </div>

    <el-table-v2
      v-if="useVirtualScroll && browseMode"
      :columns="virtualColumns"
      :data="rows"
      :width="tableWidth"
      :height="520"
      :row-height="36"
      :header-height="40"
      :row-event-handlers="rowEventHandlers"
      fixed
      class="virtual-table"
    />

    <div v-else class="table-section">
      <el-table
        :data="pagedAdjudicationRows"
        border
        size="small"
        :row-class-name="getRowClassName"
        class="adjudication-table"
        show-summary
        :summary-method="getSummaryMethod"
        max-height="520"
      >
        <el-table-column prop="projectName" label="项目" min-width="140" fixed>
          <template #default="{ row }">
            <span>{{ row.projectName }}</span>
            <el-tag v-if="row.fromDetail" size="small" type="info" class="src-tag">I5-2</el-tag>
            <el-tag v-if="row.ajeApprox" size="small" type="warning" class="src-tag">近似</el-tag>
            <el-button
              v-if="row.projectName"
              size="small"
              text
              type="primary"
              class="row-i53-btn"
              @click="navigateToI53(row.projectName)"
            >I5-3</el-button>
            <el-button
              v-if="row.isEditable !== false && !isReadonly"
              size="small"
              type="danger"
              text
              class="row-delete-btn"
              @click="removeRow(row.rowId)"
            >删</el-button>
          </template>
        </el-table-column>

        <el-table-column label="未审滚动（期初/增/减/期末）" align="center">
          <el-table-column prop="beginBalance" label="期初" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.isEditable !== false && !isReadonly"
                :model-value="row.beginBalance"
                size="small"
                :controls="false"
                :precision="2"
                class="amt-input"
                @change="(v: number | undefined) => onCellChange(row.rowId, 'beginBalance', v ?? 0)"
              />
              <span v-else>{{ fmtAmount(row.beginBalance) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="increase" label="本期增加" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.isEditable !== false && !isReadonly"
                :model-value="row.increase"
                size="small"
                :controls="false"
                :precision="2"
                class="amt-input"
                @change="(v: number | undefined) => onCellChange(row.rowId, 'increase', v ?? 0)"
              />
              <span v-else>{{ fmtAmount(row.increase) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="decrease" label="本期减少(含重分类)" min-width="120" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.isEditable !== false && !isReadonly"
                :model-value="row.decrease"
                size="small"
                :controls="false"
                :precision="2"
                class="amt-input"
                @change="(v: number | undefined) => onCellChange(row.rowId, 'decrease', v ?? 0)"
              />
              <span v-else>{{ fmtAmount(row.decrease) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末" min-width="100" align="right">
            <template #header>
              <el-tooltip content="期末 = 期初 + 增加 − 减少" placement="top">
                <span class="formula-col-header">期末</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span class="formula-value" :class="{ 'cell-error-text': row.hasError }">{{ fmtAmount(row.endBalance) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="未审 · 调整 · 审定" align="center">
          <el-table-column prop="unadjusted" label="未审" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.isEditable !== false && !isReadonly"
                :model-value="row.unadjusted"
                size="small"
                :controls="false"
                :precision="2"
                class="amt-input"
                @change="(v: number | undefined) => onCellChange(row.rowId, 'unadjusted', v ?? 0)"
              />
              <span v-else>{{ fmtAmount(row.unadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="aje" label="AJE" min-width="90" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.isEditable !== false && !isReadonly"
                :model-value="row.aje"
                size="small"
                :controls="false"
                :precision="2"
                class="amt-input"
                @change="(v: number | undefined) => onCellChange(row.rowId, 'aje', v ?? 0)"
              />
              <span v-else>{{ fmtAmount(row.aje) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="rje" label="RJE" min-width="90" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.isEditable !== false && !isReadonly"
                :model-value="row.rje"
                size="small"
                :controls="false"
                :precision="2"
                class="amt-input"
                @change="(v: number | undefined) => onCellChange(row.rowId, 'rje', v ?? 0)"
              />
              <span v-else>{{ fmtAmount(row.rje) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定数" min-width="100" align="right">
            <template #header>
              <el-tooltip content="审定 = 未审 + AJE + RJE" placement="top">
                <span class="formula-col-header">审定数</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span class="formula-value">{{ fmtAmount(row.audited) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="与上期审定比较" align="center">
          <el-table-column prop="priorAudited" label="上期审定" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.isEditable !== false && !isReadonly"
                :model-value="row.priorAudited"
                size="small"
                :controls="false"
                :precision="2"
                class="amt-input"
                @change="(v: number | undefined) => onCellChange(row.rowId, 'priorAudited', v ?? 0)"
              />
              <span v-else>{{ fmtAmount(row.priorAudited) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="变动额" min-width="100" align="right">
            <template #default="{ row }">{{ fmtAmount(row.varianceAmount) }}</template>
          </el-table-column>
          <el-table-column label="变动率" min-width="90" align="right">
            <template #default="{ row }">{{ formatI5VarianceRate(row.varianceRate) }}</template>
          </el-table-column>
        </el-table-column>
      </el-table>
      <el-pagination
        v-if="useVirtualScroll && !browseMode && rows.length > editPageSize"
        v-model:current-page="editPage"
        :page-size="editPageSize"
        :total="rows.length"
        layout="total, prev, pager, next"
        class="edit-pagination"
      />
    </div>

    <div class="tb-section">
      <div class="block-header">
        <span class="block-title">TB取数与差异（合计 / TB数据 / 差异）</span>
      </div>
      <el-table :data="differenceRows" border size="small" class="adjudication-table tb-table">
        <el-table-column prop="label" label="科目" min-width="160" />
        <el-table-column prop="tbAmount" label="TB未审数" min-width="120" align="right">
          <template #default="{ row }">{{ fmtAmount(row.tbAmount) }}</template>
        </el-table-column>
        <el-table-column prop="audited" label="审定表审定数" min-width="120" align="right">
          <template #default="{ row }">{{ fmtAmount(row.audited) }}</template>
        </el-table-column>
        <el-table-column prop="difference" label="差异" min-width="120" align="right">
          <template #default="{ row }">
            <span :class="{ 'difference-warning': Math.abs(row.difference) > 0.01 }">
              {{ fmtAmount(row.difference) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-card class="audit-note-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>1、审计说明</span>
          <el-button
            v-if="!isReadonly"
            size="small"
            type="primary"
            text
            @click="fillVarianceNoteDraft(false)"
          >生成变动说明草稿（&gt;30%）</el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 12 }"
        placeholder="（1）期末较期初变动及超 30% 原因…&#10;可点「生成变动说明草稿」自动填入（上期为 0 显示 N/A，避免除零）。"
        :disabled="isReadonly"
        @blur="() => saveNote(auditNote)"
      />
    </el-card>

    <el-card class="audit-note-card" shadow="never">
      <template #header>
        <div class="card-header"><span>（2）权属、抵押情况说明</span></div>
      </template>
      <el-input
        v-model="ownershipPledge"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="说明产权归属、抵押/质押/查封及其他权利限制；无则填「未发现抵押或权利限制」。"
        :disabled="isReadonly"
        @blur="() => saveOwnershipPledge(ownershipPledge)"
      />
    </el-card>

    <el-card class="audit-note-card" shadow="never">
      <template #header>
        <div class="card-header"><span>重大事项说明（风险 / 调整）</span></div>
      </template>
      <el-input
        v-model="significantMatters"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="A. 风险评估：是否存在特别风险（舞弊/复杂交易/重大关联方）及应对…&#10;B. 重大发现/调整：原因、金额、索引（I5-3 等）…"
        :disabled="isReadonly"
        @blur="() => saveSignificantMatters(significantMatters)"
      />
    </el-card>

    <el-card class="audit-note-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>2、审计结论</span>
          <div class="card-header-actions">
            <el-select
              v-if="!isReadonly"
              size="small"
              placeholder="Excel 结论模板 A/B/C"
              style="width: 220px"
              @change="applyConclusionTemplate"
            >
              <el-option v-for="t in I5_CONCLUSION_OPTIONS" :key="t.key" :label="t.label" :value="t.key" />
            </el-select>
            <el-button size="small" type="primary" text :disabled="isReadonly" @click="fillConclusionDraft">生成草稿</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="选择 A/B/C 模板或生成草稿后可再编辑…"
        :disabled="isReadonly"
        @blur="() => saveConclusion(auditConclusion)"
      />
    </el-card>

    <details class="compile-hint" open>
      <summary>编制说明（对齐 Excel I5-1）</summary>
      <ol>
        <li>其他非流动资产核算预计无法在一年（或一个正常营业周期）内变现或耗用的非流动资产，如预付土地出让金、预付工程/房屋设备款、合同资产（非流动部分）等。</li>
        <li>资产类借方科目 1911：期末＝期初＋增加−减少（含到期转出/重分类至流动资产等）。</li>
        <li>审定矩阵分列「账项调整」(AJE) 与「重分类调整」(RJE)；审定数＝未审＋账项＋重分类。</li>
        <li>明细合计(I5-2)、调整分录(I5-3)应与本表勾稽；TB 差异须为 0 后方可回写。</li>
        <li>变动率＝（本期审定−上期审定）/|上期审定|；上期为 0 时显示 N/A（勿出现 #DIV/0!）。变动率超过 30% 的项目须在审计说明中解释原因。</li>
        <li>权属、抵押情况应单独说明；审计结论可选用 A/B/C 模板。</li>
        <li>「带入调整」：从集中登记按科目 1911 拉取调整分录，逐笔分配到各项目的 AJE/RJE，带入后审定数自动更新并联动附注。</li>
      </ol>
    </details>

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="1911 其他非流动资产"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, toRef, inject, onMounted, onUnmounted, ref, h } from 'vue'
import { ElNotification } from 'element-plus'
import { useVirtualTable, type VirtualColumn } from '@/composables/useVirtualTable'
import { setI5NavHighlight, consumeI5NavHighlight } from '../../composables/i5NavBridge'
import {
  useI5Adjudication,
  formatI5VarianceRate,
  I5_CONCLUSION_OPTIONS,
  type I5AdjudicationRow,
} from '../../composables/useI5Adjudication'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import { useAuditContext } from '@/composables/useAuditContext'
import { Download } from '@element-plus/icons-vue'
import GtIndexChip from '../../GtIndexChip.vue'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import WpFourTableSourcePanel from '../../shared/WpFourTableSourcePanel.vue'
import { getICycleSourceConfig, extractTbSourceCodes } from '../../composables/useICycleFourTableSource'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  tbData: { unadjusted1911: number; audited1911: number; priorAudited1911?: number }
  isReadonly: boolean
  htmlData?: Record<string, unknown> | null
}>()

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
  'save': [itemId: string, value: any]
}>()

const openReviewDialog = inject<(section?: string) => void>('openReviewDialog', () => {})

const sourceConfig = getICycleSourceConfig('I5')
const tbSourceCodes = computed(() => extractTbSourceCodes(props.htmlData))

const {
  rows,
  auditNote,
  auditConclusion,
  significantMatters,
  ownershipPledge,
  subtotals,
  leadMatrixRows,
  threeLayerLeadRows,
  hasThreeLayerDetail,
  crossCheck,
  reconciliationStatus,
  hasAjeApprox,
  tbDifference,
  differenceRows,
  addRow,
  removeRow,
  updateCell,
  seedFromI52,
  syncFromI53,
  applyTbData,
  applyPriorFromTb,
  fillConclusionDraft,
  fillVarianceNoteDraft,
  applyConclusionTemplate,
  writeback,
  saveNote,
  saveConclusion,
  saveSignificantMatters,
  saveOwnershipPledge,
} = useI5Adjudication(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  toRef(props, 'allResponses'),
  {
    tbUnadjusted1911: computed(() => props.tbData?.unadjusted1911 ?? 0),
    tbAudited1911: computed(() => props.tbData?.audited1911 ?? 0),
    tbPriorAudited1911: computed(() => props.tbData?.priorAudited1911 ?? 0),
    onSave: (itemId: string, value: any) => emit('save', itemId, value),
  },
)

// ─── 从集中登记带入调整（1911 其他非流动资产，资产借方；带入 AJE/RJE） ───
const bringInRows = computed(() =>
  rows.value.map((r) => ({ rowKey: r.rowId, name: r.projectName, aje: r.aje, rje: r.rje })),
)
const {
  adjPull,
  visible: bringInVisible,
  rowOptions: bringInRowOptions,
  open: openBringInAdjustment,
  apply: onBringInApply,
} = useAdjudicationBringIn({
  projectId: computed(() => props.projectId) as any,
  year: useAuditContext().year as any,
  subjectPrefix: '1911',
  direction: 'debit',
  subjectCode: '1911',
  wpCode: 'I5',
  subjectLabel: '其他非流动资产(1911)',
  rows: bringInRows,
  updateCell: (rowKey: string, field: any, value: number) => updateCell(rowKey, field, value),
  totalAudited: () => subtotals.value.audited,
})

const BROWSE_THRESHOLD = 30
const browseMode = ref(true)
const tableWidth = ref(1200)
const editPage = ref(1)
const editPageSize = 50
const useVirtualScroll = computed(() => rows.value.length > BROWSE_THRESHOLD)

const virtualColumns = computed<VirtualColumn[]>(() => {
  const fmt = (v: unknown) => fmtAmount(Number(v) || 0)
  const numCol = (key: string, title: string, w = 100): VirtualColumn => ({
    key,
    dataKey: key,
    title,
    width: w,
    align: 'right',
    cellRenderer: ({ cellData }) => h('span', {}, fmt(cellData)),
  })
  return [
    { key: 'projectName', dataKey: 'projectName', title: '项目', width: 160 },
    numCol('endBalance', '期末', 100),
    numCol('unadjusted', '未审', 90),
    numCol('aje', 'AJE', 90),
    numCol('rje', 'RJE', 90),
    numCol('audited', '审定', 100),
    numCol('varianceAmount', '变动额', 100),
  ]
})

const { rowEventHandlers } = useVirtualTable({
  rows,
  columns: virtualColumns,
  width: tableWidth,
  height: 520,
  onRowDblclick: () => { browseMode.value = false },
})

const pagedAdjudicationRows = computed(() => {
  if (!useVirtualScroll.value || browseMode.value) return rows.value
  const start = (editPage.value - 1) * editPageSize
  return rows.value.slice(start, start + editPageSize)
})

function getSummaryMethod({ columns }: { columns: any[] }) {
  const sums: string[] = []
  const sub = subtotals.value
  columns.forEach((col, idx) => {
    if (idx === 0) { sums[idx] = '合计'; return }
    const prop = col.property as string | undefined
    if (prop && (sub as any)[prop] != null && typeof (sub as any)[prop] === 'number') {
      sums[idx] = fmtAmount((sub as any)[prop])
      return
    }
    const label = col.label
    if (label === '期末') { sums[idx] = fmtAmount(sub.endBalance); return }
    if (label === '审定数') { sums[idx] = fmtAmount(sub.audited); return }
    if (label === '变动额') { sums[idx] = fmtAmount(sub.varianceAmount); return }
    if (label === '变动率') { sums[idx] = formatI5VarianceRate(sub.varianceRate); return }
    sums[idx] = ''
  })
  return sums
}

function getRowClassName({ row }: { row: I5AdjudicationRow }): string {
  if (row.hasError) return 'row-has-error'
  return ''
}

function leadRowClassName({ row }: { row: any }): string {
  if (row.isSection) return 'lead-section-row'
  if (row.tbMismatch) return 'lead-tb-mismatch-row'
  if (row.isTotal) return 'lead-total-row'
  if (row.layer === 'impairment') return 'lead-imp-row'
  if (row.layer === 'net') return 'lead-net-row'
  if (row.layer === 'tb') return 'lead-tb-row'
  return ''
}

function onCellChange(rowId: string, field: keyof I5AdjudicationRow, value: number): void {
  updateCell(rowId, field, value)
}

async function handleSave(): Promise<void> {
  await writeback(false)
}

function handleReview(): void {
  openReviewDialog('I5-1 审定表')
}

function navigateTo(wpCode: string): void {
  emit('navigate-sheet', wpCode)
}

function navigateToI53(projectName: string): void {
  setI5NavHighlight(projectName, 'I5-1')
  emit('navigate-sheet', 'I5-3')
}

function onAdjustmentsChanged(): void {
  ElNotification({
    title: 'I5-3 调整已更新',
    message: '可点击「从 I5-3 同步调整」更新审定表',
    type: 'info',
    duration: 5000,
  })
}

onMounted(() => {
  window.addEventListener('i5:adjustments-changed', onAdjustmentsChanged)
  const nav = consumeI5NavHighlight()
  if (nav?.from === 'I5-3' && nav.projectName) {
    ElNotification({
      title: 'I5-3 来源定位',
      message: `已跳转审定表，请核对项目「${nav.projectName}」的 AJE/RJE`,
      type: 'info',
      duration: 6000,
    })
  }
})

onUnmounted(() => {
  window.removeEventListener('i5:adjustments-changed', onAdjustmentsChanged)
})

function fmtAmount(value: number | null | undefined): string {
  if (value == null) return '-'
  if (Math.abs(value) < 0.005) return '-'
  return value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i5-adjudication {
  font-size: var(--wp-font-size, 13px);
  padding: 16px;
}
.section-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 12px;
}
.section-title { font-size: 15px; font-weight: 600; }
.objective-alert { margin-bottom: 14px; }
.methodology-context {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 12px 16px;
  margin-bottom: 16px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.8;
}
.methodology-context p { margin: 0; }
.tab-toolbar { margin-bottom: 12px; }
.toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.adj-warning { margin-bottom: 10px; }
.layer-card { margin-bottom: 14px; }
.layer-card :deep(.el-card__header) { padding: 10px 14px; background: #fafafa; font-weight: 600; }
.layer-table :deep(.lead-total-row td) { font-weight: 600; background: #f0f9ff !important; }
.layer-table :deep(.lead-section-row td) { font-weight: 600; background: #fafafa !important; color: #606266; }
.layer-table :deep(.lead-imp-row td) { background: #fffbeb; }
.layer-table :deep(.lead-net-row td) { background: #f0fdf4; }
.layer-table :deep(.lead-tb-row td) { background: #f8fafc; font-style: italic; }
.layer-table :deep(.lead-tb-mismatch-row td) { background: #fef2f2 !important; color: #dc2626; font-weight: 600; }
.layer-table :deep(.lead-section-row td) { font-weight: 600; background: #f8fafc !important; color: #1e3a5f; }
.layer-table :deep(.lead-imp-row td) { background: #fffbeb !important; }
.layer-table :deep(.lead-net-row td) { background: #f0fdf4 !important; }
.card-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.action-bar { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.table-section { margin-bottom: 20px; }
.virtual-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.virtual-hint { flex: 1; margin: 0; }
.edit-pagination { margin-top: 8px; justify-content: flex-end; }
.row-i53-btn { margin-left: 4px; }
.adjudication-table { font-size: var(--wp-font-size, 13px); }
.adjudication-table :deep(.el-table__footer td) { font-weight: 600; background: #f0f9ff; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; padding-bottom: 2px; }
.formula-value { border-bottom: 1px dashed #c0c4cc; cursor: help; padding-bottom: 1px; font-weight: 500; }
.adjudication-table :deep(.row-has-error td) { background: #fef2f2 !important; }
.cell-error-text { color: #dc2626; font-weight: 600; }
.row-delete-btn { margin-left: 4px; font-size: 11px; padding: 2px 4px; }
.src-tag { margin-left: 4px; }
.amt-input { width: 100%; }
.amt-input :deep(.el-input__inner) { text-align: right; }
.tb-section { margin-bottom: 20px; }
.block-header { display: flex; align-items: center; justify-content: space-between; padding: 8px 0; font-weight: 600; }
.difference-warning { color: #dc2626; font-weight: 600; }
.audit-note-card { margin-bottom: 16px; }
.audit-note-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; }
.card-header {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 14px; font-weight: 500;
}
.card-header-actions { display: flex; gap: 8px; align-items: center; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ol { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 6px; line-height: 1.6; }
</style>
