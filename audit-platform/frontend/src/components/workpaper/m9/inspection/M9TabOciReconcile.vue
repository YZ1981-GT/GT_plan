<template>
  <div class="m9-tab-oci-reconcile">
    <!-- ═══ 标题 + DualMode + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M9-4 OCI核对表（多来源核对）</h3>
        <el-tag type="danger" effect="dark" size="small" class="core-badge">核心</el-tag>
      </div>
      <div class="section-header-right">
        <el-segmented
          v-model="dualMode.mode.value"
          :options="dualMode.modeOptions.value"
          size="small"
          @change="(val: any) => dualMode.switchMode(val)"
        />
        <el-button size="small" @click="handleAI('reconcile')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
        <el-button type="primary" size="small" :loading="isSaving" @click="handleSave">
          保存
        </el-button>
      </div>
    </div>

    <!-- ═══ 蓝色渐变引导区（3步） ═══ -->
    <div class="m9-guide">
      <div class="m9-guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>OCI核对步骤</span>
      </div>
      <div class="m9-guide-steps">
        <div class="step-item">
          <span class="step-num">①</span>
          <span class="step-text">确认来源数据（G8其他权益工具投资公允变动 / J2设定受益计划重计量 / 外币折算 / 套期 / 其他债权）</span>
        </div>
        <div class="step-item">
          <span class="step-num">②</span>
          <span class="step-text">比对账面OCI（从M9-2明细表取本期OCI增加贷方发生额，按税后净额核对）</span>
        </div>
        <div class="step-item">
          <span class="step-num">③</span>
          <span class="step-text">分析差异（核对差异=来源金额(税后)−账面OCI增加，差异超阈值红色高亮并说明原因）</span>
        </div>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>OCI多来源核对逻辑：</strong>
        其他综合收益汇聚多来源——G8其他权益工具投资公允价值变动、J2设定受益计划重计量、外币财务报表折算差额、
        其他债权投资公允变动、现金流量套期损益。核对差异 = 来源金额(税后) − 账面OCI增加。
        各项目按税后净额列示：本期税前发生 − 所得税影响 = 税后净额。
        分"以后不能重分类进损益"和"以后能重分类进损益"两大类分别核对。
      </div>
    </div>

    <!-- ═══ G8/J2来源状态提示 ═══ -->
    <div v-if="!g8Ready || !j2Ready" class="source-pending-tip">
      <el-icon><WarningFilled /></el-icon>
      <span v-if="!g8Ready">待G8数据就绪</span>
      <span v-if="!g8Ready && !j2Ready"> | </span>
      <span v-if="!j2Ready">待J2数据就绪</span>
    </div>

    <!-- ═══ 双区块 el-table: 不可重分类来源（G8+J2） ═══ -->
    <div class="block-section">
      <div class="block-header">
        <h4 class="block-title">一、以后不能重分类进损益的OCI来源</h4>
        <div class="block-header-right">
          <el-button size="small" @click="handleAI('nonReclass')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
          <el-button
            v-if="!isReadonly"
            size="small"
            type="primary"
            plain
            @click="handleAddRow('nonReclass')"
          >
            + 新增来源
          </el-button>
        </div>
      </div>

      <el-table
        :data="nonReclassTableData"
        border
        size="small"
        style="width: 100%"
        :row-class-name="getRowClassName"
      >
        <!-- 来源底稿 -->
        <el-table-column prop="sourceName" label="来源底稿" min-width="160" fixed>
          <template #default="{ row }">
            <template v-if="isSubtotalRow(row)">
              <span class="total-row-label">{{ row.sourceName }}</span>
            </template>
            <template v-else-if="!isReadonly">
              <el-input
                :model-value="row.sourceName"
                size="small"
                placeholder="来源底稿名称"
                @change="(val: string) => handleUpdate(row, 'sourceName', val)"
              />
            </template>
            <template v-else>{{ row.sourceName || '—' }}</template>
          </template>
        </el-table-column>

        <!-- 来源金额(税前) -->
        <el-table-column label="来源金额(税前)" width="130" align="right">
          <template #default="{ row }">
            <template v-if="!isSubtotalRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.sourcePreTax"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdate(row, 'sourcePreTax', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.sourcePreTax) }}</span>
          </template>
        </el-table-column>

        <!-- 所得税影响 -->
        <el-table-column label="所得税影响" width="120" align="right">
          <template #default="{ row }">
            <template v-if="!isSubtotalRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.sourceTaxEffect"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdate(row, 'sourceTaxEffect', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.sourceTaxEffect) }}</span>
          </template>
        </el-table-column>

        <!-- 来源金额(税后) 公式列 -->
        <el-table-column label="来源金额(税后)" width="135" align="right">
          <template #header>
            <el-tooltip content="公式: 来源金额(税后) = 税前 − 所得税影响" placement="top">
              <span class="formula-col-header">来源金额(税后)</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.sourceAfterTax) }}</span>
          </template>
        </el-table-column>

        <!-- 账面OCI增加 -->
        <el-table-column label="账面OCI增加" width="130" align="right">
          <template #default="{ row }">
            <template v-if="!isSubtotalRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.bookedOciIncrease"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdate(row, 'bookedOciIncrease', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.bookedOciIncrease) }}</span>
          </template>
        </el-table-column>

        <!-- 核对差异 公式列 + 红色高亮 -->
        <el-table-column label="核对差异" width="120" align="right">
          <template #header>
            <el-tooltip content="公式: 核对差异 = 来源金额(税后) − 账面OCI增加" placement="top">
              <span class="formula-col-header">核对差异</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span :class="['formula-value', { 'diff-warning': isDiffHighlighted(row) }]">
              {{ fmtAmount(row.reconcileDiff) }}
            </span>
          </template>
        </el-table-column>

        <!-- 差异说明 -->
        <el-table-column label="差异说明" min-width="150">
          <template #default="{ row }">
            <template v-if="!isSubtotalRow(row) && !isReadonly">
              <el-input
                :model-value="row.diffExplanation"
                size="small"
                placeholder="说明差异原因"
                @change="(val: string) => handleUpdate(row, 'diffExplanation', val)"
              />
            </template>
            <span v-else>{{ row.diffExplanation || '—' }}</span>
          </template>
        </el-table-column>

        <!-- 来源编码 -->
        <el-table-column label="来源编码" width="90" align="center">
          <template #default="{ row }">
            <span v-if="!isSubtotalRow(row)" class="source-code-cell">{{ row.sourceWpCode || '—' }}</span>
          </template>
        </el-table-column>

        <!-- 跳转（GtIndexChip） -->
        <el-table-column label="跳转" width="80" align="center">
          <template #default="{ row }">
            <GtIndexChip
              v-if="!isSubtotalRow(row) && row.sourceWpCode"
              :value="row.sourceWpCode"
            />
          </template>
        </el-table-column>

        <!-- 操作列 -->
        <el-table-column v-if="!isReadonly" label="" width="60" align="center">
          <template #default="{ row }">
            <el-button
              v-if="!isSubtotalRow(row)"
              type="danger"
              size="small"
              link
              @click="handleRemoveRow(row)"
            >删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ═══ 双区块 el-table: 可重分类来源（债权+套期+外币） ═══ -->
    <div class="block-section">
      <div class="block-header">
        <h4 class="block-title">二、以后能重分类进损益的OCI来源</h4>
        <div class="block-header-right">
          <el-button size="small" @click="handleAI('reclass')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
          <el-button
            v-if="!isReadonly"
            size="small"
            type="primary"
            plain
            @click="handleAddRow('reclass')"
          >
            + 新增来源
          </el-button>
        </div>
      </div>

      <el-table
        :data="reclassTableData"
        border
        size="small"
        style="width: 100%"
        :row-class-name="getRowClassName"
      >
        <!-- 来源底稿 -->
        <el-table-column prop="sourceName" label="来源底稿" min-width="160" fixed>
          <template #default="{ row }">
            <template v-if="isSubtotalRow(row)">
              <span class="total-row-label">{{ row.sourceName }}</span>
            </template>
            <template v-else-if="!isReadonly">
              <el-input
                :model-value="row.sourceName"
                size="small"
                placeholder="来源底稿名称"
                @change="(val: string) => handleUpdate(row, 'sourceName', val)"
              />
            </template>
            <template v-else>{{ row.sourceName || '—' }}</template>
          </template>
        </el-table-column>

        <!-- 来源金额(税前) -->
        <el-table-column label="来源金额(税前)" width="130" align="right">
          <template #default="{ row }">
            <template v-if="!isSubtotalRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.sourcePreTax"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdate(row, 'sourcePreTax', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.sourcePreTax) }}</span>
          </template>
        </el-table-column>

        <!-- 所得税影响 -->
        <el-table-column label="所得税影响" width="120" align="right">
          <template #default="{ row }">
            <template v-if="!isSubtotalRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.sourceTaxEffect"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdate(row, 'sourceTaxEffect', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.sourceTaxEffect) }}</span>
          </template>
        </el-table-column>

        <!-- 来源金额(税后) 公式列 -->
        <el-table-column label="来源金额(税后)" width="135" align="right">
          <template #header>
            <el-tooltip content="公式: 来源金额(税后) = 税前 − 所得税影响" placement="top">
              <span class="formula-col-header">来源金额(税后)</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.sourceAfterTax) }}</span>
          </template>
        </el-table-column>

        <!-- 账面OCI增加 -->
        <el-table-column label="账面OCI增加" width="130" align="right">
          <template #default="{ row }">
            <template v-if="!isSubtotalRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.bookedOciIncrease"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdate(row, 'bookedOciIncrease', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.bookedOciIncrease) }}</span>
          </template>
        </el-table-column>

        <!-- 核对差异 公式列 + 红色高亮 -->
        <el-table-column label="核对差异" width="120" align="right">
          <template #header>
            <el-tooltip content="公式: 核对差异 = 来源金额(税后) − 账面OCI增加" placement="top">
              <span class="formula-col-header">核对差异</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span :class="['formula-value', { 'diff-warning': isDiffHighlighted(row) }]">
              {{ fmtAmount(row.reconcileDiff) }}
            </span>
          </template>
        </el-table-column>

        <!-- 差异说明 -->
        <el-table-column label="差异说明" min-width="150">
          <template #default="{ row }">
            <template v-if="!isSubtotalRow(row) && !isReadonly">
              <el-input
                :model-value="row.diffExplanation"
                size="small"
                placeholder="说明差异原因"
                @change="(val: string) => handleUpdate(row, 'diffExplanation', val)"
              />
            </template>
            <span v-else>{{ row.diffExplanation || '—' }}</span>
          </template>
        </el-table-column>

        <!-- 来源编码 -->
        <el-table-column label="来源编码" width="90" align="center">
          <template #default="{ row }">
            <span v-if="!isSubtotalRow(row)" class="source-code-cell">{{ row.sourceWpCode || '—' }}</span>
          </template>
        </el-table-column>

        <!-- 跳转（GtIndexChip） -->
        <el-table-column label="跳转" width="80" align="center">
          <template #default="{ row }">
            <GtIndexChip
              v-if="!isSubtotalRow(row) && row.sourceWpCode"
              :value="row.sourceWpCode"
            />
          </template>
        </el-table-column>

        <!-- 操作列 -->
        <el-table-column v-if="!isReadonly" label="" width="60" align="center">
          <template #default="{ row }">
            <el-button
              v-if="!isSubtotalRow(row)"
              type="danger"
              size="small"
              link
              @click="handleRemoveRow(row)"
            >删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ═══ 合计行 ═══ -->
    <div class="grand-total-section">
      <el-table :data="[grandTotalRow]" border size="small" style="width: 100%">
        <el-table-column label="来源底稿" min-width="160" fixed>
          <template #default><span class="grand-total-label">合 计</span></template>
        </el-table-column>
        <el-table-column label="来源金额(税前)" width="130" align="right">
          <template #default>{{ fmtAmount(grandTotalPreTax) }}</template>
        </el-table-column>
        <el-table-column label="所得税影响" width="120" align="right">
          <template #default>{{ fmtAmount(grandTotalTaxEffect) }}</template>
        </el-table-column>
        <el-table-column label="来源金额(税后)" width="135" align="right">
          <template #default>
            <span class="formula-value">{{ fmtAmount(totalSummary.totalSourceAfterTax) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账面OCI增加" width="130" align="right">
          <template #default>{{ fmtAmount(totalSummary.totalBookedIncrease) }}</template>
        </el-table-column>
        <el-table-column label="核对差异" width="120" align="right">
          <template #default>
            <span :class="['formula-value', { 'diff-warning': Math.abs(totalSummary.totalDiff) > 0.01 }]">
              {{ fmtAmount(totalSummary.totalDiff) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="差异说明" min-width="150">
          <template #default>—</template>
        </el-table-column>
        <el-table-column label="来源编码" width="90" align="center">
          <template #default>—</template>
        </el-table-column>
        <el-table-column label="跳转" width="80" align="center">
          <template #default>—</template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ═══ 核对结论区 ═══ -->
    <div class="reconcile-conclusion">
      <div v-if="totalSummary.isAllReconciled" class="conclusion-pass">
        <el-icon><CircleCheckFilled /></el-icon>
        <span>核对结论：全部一致，OCI各来源与账面核对无差异</span>
      </div>
      <div v-else class="conclusion-fail">
        <el-icon><CircleCloseFilled /></el-icon>
        <span>核对结论：存在差异（不可重分类差异: {{ fmtAmount(nonReclassSummary.totalDiff) }}；可重分类差异: {{ fmtAmount(reclassSummary.totalDiff) }}），请核实来源数据</span>
      </div>
    </div>

    <!-- ═══ 分类小计摘要 ═══ -->
    <div class="category-summary">
      <el-tag type="info" size="small" effect="plain">
        不可重分类来源合计(税后): {{ fmtAmount(nonReclassSummary.totalSourceAfterTax) }}
      </el-tag>
      <el-tag type="info" size="small" effect="plain">
        可重分类来源合计(税后): {{ fmtAmount(reclassSummary.totalSourceAfterTax) }}
      </el-tag>
      <el-tag :type="totalSummary.isAllReconciled ? 'success' : 'danger'" size="small" effect="plain">
        总差异: {{ fmtAmount(totalSummary.totalDiff) }}
      </el-tag>
    </div>

    <!-- ═══ 审计结论区（el-card包裹） ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">核对说明与审计结论</span>
          <el-button size="small" @click="handleAI('conclusion')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写OCI核对说明与审计结论..."
        :disabled="isReadonly"
        @change="saveConclusion"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠底部） ═══ -->
    <details class="m9-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>OCI核对表是M9底稿的<strong>核心功能</strong>：验证OCI完整性与准确性</li>
        <li>核对差异 = 来源金额(税后) − 账面OCI增加（贷方发生额）</li>
        <li>各项OCI按<strong>税后净额</strong>列示：本期税前发生 − 所得税影响 = 税后净额</li>
        <li>不可重分类来源：G8其他权益工具投资公允价值变动、J2设定受益计划重计量</li>
        <li>可重分类来源：其他债权投资公允变动、现金流量套期损益、外币财务报表折算差额</li>
        <li>差异超过阈值(0.01)自动红色高亮，需补充差异说明</li>
        <li>G8/J2数据通过EventBus自动接收（'g8:fair-value-changed' / 'j2:remeasured'）</li>
        <li>通过cross_wp_references关联G8、J2底稿，GtIndexChip可跳转溯源</li>
        <li>42×9结构，13公式全部前端实时计算</li>
      </ul>
    </details>
  </div>
</template>


<script setup lang="ts">
/**
 * M9TabOciReconcile — M9-4 OCI核对表（多来源核对，核心！）
 *
 * Spec: .kiro/specs/m9-other-comprehensive-income/
 * Task: 4.4
 * Requirements: 4.1-4.8
 *
 * 核心特征：OCI多来源核对
 * - 双区块：不可重分类来源(G8+J2) + 可重分类来源(债权+套期+外币)
 * - 9列: 来源底稿 | 来源金额(税前) | 所得税影响 | 来源金额(税后) | 账面OCI增加 | 核对差异 | 差异说明 | 来源编码 | 跳转
 * - 13公式全部前端实时计算（via useM9OciReconcile composable）
 * - 差异|diff|>threshold红色高亮(.diff-warning class)
 * - GtIndexChip for G8/J2 cross-reference
 * - EventBus 订阅: 'g8:fair-value-changed' / 'j2:remeasured'
 * - 42×9 structure, 13 formulas
 *
 * UI规范: 13px font; formula columns dashed underline + cursor:help + tooltip;
 *         AI辅助按钮section标题右对齐; 蓝色渐变引导区; 方法论上下文琥珀色块
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  MagicStick, Check, InfoFilled, WarningFilled,
  CircleCheckFilled, CircleCloseFilled,
} from '@element-plus/icons-vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { useM9FormData } from '../../composables/useM9FormData'
import { useM9DualMode } from '../../composables/useM9DualMode'
import {
  useM9OciReconcile,
  M9_RECONCILE_DEFAULT_SOURCES,
  type M9ReconcileRow,
  type M9ReconcileCategory,
} from '../../composables/useM9OciReconcile'
import { useVersionTrail } from '../../composables/useVersionTrail'

const props = defineProps<{ wpId: string; projectId: string; isReadonly: boolean }>()
const emit = defineEmits<{ (e: 'navigate', sheetName: string): void; (e: 'save'): void }>()

// ─── Inject复核对话 ──────────────────────────────────────────────────────────
const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── Composables ─────────────────────────────────────────────────────────────
const formData = useM9FormData({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })
const dualMode = useM9DualMode({ wpId: computed(() => props.wpId) })
const versionTrail = useVersionTrail({ projectId: computed(() => props.projectId), workpaperId: computed(() => props.wpId) })

// 核对行数据（初始化默认来源）
const reconcileRows = ref<M9ReconcileRow[]>(
  M9_RECONCILE_DEFAULT_SOURCES.map((src, i) => ({
    key: `m9-reconcile-default-${i}`,
    sourceName: src.name,
    sourceType: src.type,
    category: src.category,
    sourcePreTax: 0,
    sourceTaxEffect: 0,
    sourceAfterTax: 0,
    bookedOciIncrease: 0,
    reconcileDiff: 0,
    diffExplanation: '',
    sourceWpCode: src.wpCode,
    crossRefId: '',
  })),
)

const {
  computedRows,
  nonReclassRows,
  reclassRows,
  nonReclassSummary,
  reclassSummary,
  totalSummary,
  isHighlighted,
  addRow,
  removeRow,
  updateRow,
  updateFromSource,
  subscribeG8FairValue,
  subscribeJ2Remeasured,
  saveReconcileData,
} = useM9OciReconcile(formData, reconcileRows)

// ─── G8/J2 来源就绪状态 ──────────────────────────────────────────────────────
const g8Ready = ref(false)
const j2Ready = ref(false)

// ─── UI State ────────────────────────────────────────────────────────────────
const isSaving = ref(false)
const auditConclusion = ref('')

// ─── 表格数据（数据行 + 小计行） ─────────────────────────────────────────────

interface TableRow extends M9ReconcileRow { _rowType?: 'data' | 'subtotal' }

const nonReclassTableData = computed<TableRow[]>(() => {
  const rows: TableRow[] = nonReclassRows.value.map(r => ({ ...r, _rowType: 'data' as const }))
  // 小计行
  rows.push({
    key: 'nonReclass-subtotal',
    sourceName: '不可重分类小计',
    sourceType: 'other',
    category: 'nonReclass',
    sourcePreTax: nonReclassRows.value.reduce((s, r) => s + r.sourcePreTax, 0),
    sourceTaxEffect: nonReclassRows.value.reduce((s, r) => s + r.sourceTaxEffect, 0),
    sourceAfterTax: nonReclassSummary.value.totalSourceAfterTax,
    bookedOciIncrease: nonReclassSummary.value.totalBookedIncrease,
    reconcileDiff: nonReclassSummary.value.totalDiff,
    diffExplanation: '',
    sourceWpCode: '',
    crossRefId: '',
    _rowType: 'subtotal',
  })
  return rows
})

const reclassTableData = computed<TableRow[]>(() => {
  const rows: TableRow[] = reclassRows.value.map(r => ({ ...r, _rowType: 'data' as const }))
  // 小计行
  rows.push({
    key: 'reclass-subtotal',
    sourceName: '可重分类小计',
    sourceType: 'other',
    category: 'reclass',
    sourcePreTax: reclassRows.value.reduce((s, r) => s + r.sourcePreTax, 0),
    sourceTaxEffect: reclassRows.value.reduce((s, r) => s + r.sourceTaxEffect, 0),
    sourceAfterTax: reclassSummary.value.totalSourceAfterTax,
    bookedOciIncrease: reclassSummary.value.totalBookedIncrease,
    reconcileDiff: reclassSummary.value.totalDiff,
    diffExplanation: '',
    sourceWpCode: '',
    crossRefId: '',
    _rowType: 'subtotal',
  })
  return rows
})

// ─── 合计行 ──────────────────────────────────────────────────────────────────
const grandTotalRow = computed(() => ({ id: 'grand-total' }))
const grandTotalPreTax = computed(() => computedRows.value.reduce((s, r) => s + r.sourcePreTax, 0))
const grandTotalTaxEffect = computed(() => computedRows.value.reduce((s, r) => s + r.sourceTaxEffect, 0))

// ─── 行类型判断 ──────────────────────────────────────────────────────────────
function isSubtotalRow(row: TableRow): boolean { return row._rowType === 'subtotal' }

function getRowClassName({ row }: { row: TableRow; rowIndex: number }): string {
  if (row._rowType === 'subtotal') return 'subtotal-row'
  if (row._rowType === 'data' && isHighlighted(row as M9ReconcileRow)) return 'highlighted-row'
  return ''
}

function isDiffHighlighted(row: TableRow): boolean {
  if (row._rowType === 'subtotal') return Math.abs(row.reconcileDiff) > 0.01
  return isHighlighted(row as M9ReconcileRow)
}

// ─── 行操作 ──────────────────────────────────────────────────────────────────
function handleUpdate(row: TableRow, field: string, value: any): void {
  const rawIdx = reconcileRows.value.findIndex(r => r.key === row.key)
  if (rawIdx >= 0) updateRow(rawIdx, field as keyof M9ReconcileRow, value)
}

function handleRemoveRow(row: TableRow): void {
  const rawIdx = reconcileRows.value.findIndex(r => r.key === row.key)
  if (rawIdx >= 0) removeRow(rawIdx)
}

async function handleAddRow(category: M9ReconcileCategory): Promise<void> {
  try {
    const { value: name } = await ElMessageBox.prompt('请输入来源底稿名称', '新增核对来源', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: category === 'nonReclass'
        ? '如：其他权益工具投资公允变动'
        : '如：外币财务报表折算差额',
      inputValidator: (v: string) => (v && v.trim() ? true : '来源名称不能为空'),
    })
    if (!name || !name.trim()) return
    addRow(name.trim(), undefined, category)
  } catch { /* 用户取消 */ }
}

// ─── 格式化 ──────────────────────────────────────────────────────────────────
function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 保存 ────────────────────────────────────────────────────────────────────
async function handleSave(): Promise<void> {
  isSaving.value = true
  try {
    await saveReconcileData()
    await versionTrail.createSnapshot('M9-4 OCI核对表保存')
    emit('save')
  } finally {
    isSaving.value = false
  }
}

function saveConclusion(): void {
  formData.debouncedSave('M9-4-conclusion', { remark: auditConclusion.value })
}

// ─── AI辅助 + 复核 ──────────────────────────────────────────────────────────
function handleAI(_section: string): void {
  // AI辅助调用（占位，由AI模块集成）
}

function handleReview(): void {
  openReviewDialog('m9-4-reconcile', 'M9-4 OCI核对表')
}

// ─── EventBus 订阅（G8/J2来源自动接收） ──────────────────────────────────────
let unsubG8: (() => void) | null = null
let unsubJ2: (() => void) | null = null

onMounted(async () => {
  await formData.loadData()

  // 从 checklist_responses 恢复核对结论
  const saved = formData.getField('4', 'conclusion')
  if (saved) auditConclusion.value = String(saved)

  // 订阅G8公允价值变动
  unsubG8 = subscribeG8FairValue(({ amount, afterTax }) => {
    g8Ready.value = true
    updateFromSource('G8', amount, amount - afterTax)
  })

  // 订阅J2设定受益计划重计量
  unsubJ2 = subscribeJ2Remeasured(({ amount, afterTax }) => {
    j2Ready.value = true
    updateFromSource('J2', amount, amount - afterTax)
  })
})

onUnmounted(() => {
  unsubG8?.()
  unsubJ2?.()
})
</script>

<style scoped>
.m9-tab-oci-reconcile {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── Section Header ─── */
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 8px;
}

.section-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.core-badge {
  font-size: 11px;
}

/* ─── 蓝色渐变引导区 ─── */
.m9-guide {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6eaf8 100%);
  border: 1px solid #b3d9f2;
  border-radius: 8px;
  padding: 14px 20px;
  margin-bottom: 16px;
}

.m9-guide-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  color: #1a73e8;
  margin-bottom: 10px;
  font-size: var(--wp-font-size, 13px);
}

.m9-guide-steps {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px 24px;
}

.step-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #374151;
}

.step-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #1a73e8;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
}

.step-text {
  font-size: var(--wp-font-size, 13px);
  line-height: 1.5;
}

/* ─── 方法论上下文（琥珀色） ─── */
.methodology-context {
  border-left: 4px solid #f59e0b;
  background: #fffbeb;
  padding: 12px 16px;
  margin-bottom: 16px;
  border-radius: 0 6px 6px 0;
}

.methodology-text {
  font-size: var(--wp-font-size, 13px);
  color: #78350f;
  line-height: 1.7;
}

/* ─── G8/J2来源待就绪提示 ─── */
.source-pending-tip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  margin-bottom: 16px;
  background: #fef3cd;
  border: 1px solid #ffc107;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #856404;
}

/* ─── Block Section ─── */
.block-section {
  margin-bottom: 20px;
}

.block-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.block-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.block-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

/* ─── 公式列（虚线下划线+cursor:help） ─── */
.formula-col-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 2px;
}

.formula-value {
  color: #606266;
  font-style: italic;
}

/* ─── 差异红色高亮 ─── */
.diff-warning {
  color: #f56c6c !important;
  font-weight: 600;
}

/* ─── 小计行 ─── */
.total-row-label {
  font-weight: 600;
  color: #303133;
}

.grand-total-label {
  font-weight: 700;
  color: #303133;
  font-size: var(--wp-font-size, 13px);
}

:deep(.subtotal-row) {
  background-color: #f5f7fa !important;
  font-weight: 500;
}

:deep(.highlighted-row) {
  background-color: #fef0f0 !important;
}

/* ─── 合计区 ─── */
.grand-total-section {
  margin-bottom: 16px;
}

/* ─── 核对结论区 ─── */
.reconcile-conclusion {
  margin-bottom: 12px;
  padding: 12px 20px;
  border-radius: 8px;
}

.conclusion-pass {
  display: flex;
  align-items: center;
  gap: 8px;
  background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%);
  border: 1px solid #81c784;
  border-radius: 8px;
  padding: 12px 20px;
  color: #2e7d32;
  font-weight: 500;
  font-size: 14px;
}

.conclusion-pass .el-icon {
  font-size: 20px;
  color: #43a047;
}

.conclusion-fail {
  display: flex;
  align-items: center;
  gap: 8px;
  background: linear-gradient(135deg, #ffebee 0%, #ffcdd2 100%);
  border: 1px solid #e57373;
  border-radius: 8px;
  padding: 12px 20px;
  color: #c62828;
  font-weight: 500;
  font-size: 14px;
}

.conclusion-fail .el-icon {
  font-size: 20px;
  color: #e53935;
}

/* ─── 分类摘要 ─── */
.category-summary {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

/* ─── 审计结论卡片 ─── */
.audit-note-card {
  margin-bottom: 16px;
}

.audit-note-card .section-header {
  margin-bottom: 0;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

/* ─── 来源编码列 ─── */
.source-code-cell {
  font-family: 'Fira Code', 'Consolas', monospace;
  font-size: 12px;
  color: #606266;
}

/* ─── 编制提示折叠 ─── */
.m9-details-tip {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.m9-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.m9-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}

/* ─── 表格全局 ─── */
:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}

:deep(.el-table .el-table__header th) {
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
}
</style>
