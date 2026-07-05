<template>
  <div class="l2-tab-detail">
    <!-- ═══ 标题行 + AI + 复核按钮 ═══ -->
    <div class="detail-header">
      <h3 class="detail-title">L2-2 应付利息明细表</h3>
      <div class="detail-header-actions">
        <el-button type="primary" text size="small" @click="handleAI">
          <el-icon><MagicStick /></el-icon> AI
        </el-button>
        <el-button
          v-if="!isReadonly"
          type="primary"
          text
          size="small"
          @click="handleReview"
        >
          复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>明细表核对要求：</strong>
        按借款/债券逐笔列示应付利息，期末应付 = 期初 + 本期计提 − 本期支付（负债类方向）。
        明细合计应与L2-1审定表期末一致。与L1短期借款/L3长期借款利息测算核对验证计提准确性。
      </div>
    </div>

    <!-- ═══ 计提核对指示器（接收L1/L3） ═══ -->
    <div class="accrual-check-bar">
      <div class="accrual-check-item">
        <span class="accrual-label">L1/L3计提核对：</span>
        <template v-if="isInterestDataReady">
          <span :class="accrualCheckClass">
            <template v-if="accrualVsL1L3.isConsistent">
              ✓ 一致（差额 {{ fmtAmount(accrualVsL1L3.diff) }}）
            </template>
            <template v-else>
              ✗ 差额 {{ fmtAmount(accrualVsL1L3.diff) }}（测算−账面）
            </template>
          </span>
        </template>
        <template v-else>
          <span class="accrual-pending">⏳ 待L1/L3利息测算完成</span>
        </template>
      </div>
      <div class="accrual-check-item">
        <span class="accrual-label">L1测算：</span>
        <span>{{ fmtAmount(l1EstimatedInterest) }}</span>
        <span style="margin-left: 12px" class="accrual-label">L3测算：</span>
        <span>{{ fmtAmount(l3EstimatedInterest) }}</span>
      </div>
    </div>

    <!-- ═══ 工具栏：搜索 + 导入导出 + 新增行 ═══ -->
    <div class="detail-toolbar">
      <el-input
        v-model="searchQuery"
        placeholder="搜索合同名称/来源..."
        clearable
        size="small"
        style="width: 220px"
        :prefix-icon="Search"
      />

      <!-- 区段Tab切换 -->
      <el-segmented
        v-model="activeArea"
        :options="areaOptions"
        size="small"
      />

      <!-- 导入导出 dropdown -->
      <el-dropdown
        v-if="!isReadonly"
        trigger="click"
        @command="handleImportExportCommand"
      >
        <el-button size="small" type="default">
          导入导出 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="exportTemplate">导出模板</el-dropdown-item>
            <el-dropdown-item command="exportData">导出数据</el-dropdown-item>
            <el-dropdown-item command="importData" divided>导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <!-- 新增行 -->
      <el-button
        v-if="!isReadonly"
        type="primary"
        size="small"
        @click="handleAddRow"
      >
        <el-icon><Plus /></el-icon> 新增行
      </el-button>
    </div>

    <!-- ═══ 明细表主体（区段Tab控制列显隐，行同步） ═══ -->
    <el-card shadow="never" class="detail-table-card">
      <el-table
        :data="displayRows"
        border
        size="small"
        style="width: 100%"
        :row-class-name="getRowClassName"
        max-height="560"
      >
        <!-- ─── 序号列（固定） ─── -->
        <el-table-column type="index" label="#" width="42" fixed align="center" />

        <!-- ═══ Tab 1: 来源+未审 (A~K) ═══ -->
        <template v-if="activeArea === 'source'">
          <el-table-column prop="source" label="来源类别" min-width="110">
            <template #default="{ row }">
              <template v-if="row.rowId !== '__subtotal__' && !isReadonly">
                <el-select
                  :model-value="row.source"
                  placeholder="选择"
                  size="small"
                  style="width: 100%"
                  @change="(val: string) => updateCell(row.rowId, 'source', val)"
                >
                  <el-option
                    v-for="opt in SOURCE_OPTIONS"
                    :key="opt"
                    :label="opt"
                    :value="opt"
                  />
                </el-select>
              </template>
              <span v-else :class="{ 'row-bold': row.rowId === '__subtotal__' }">
                {{ row.source || row.contractName }}
              </span>
            </template>
          </el-table-column>

          <el-table-column prop="contractName" label="合同/借款名称" min-width="150">
            <template #default="{ row }">
              <template v-if="row.rowId !== '__subtotal__' && !isReadonly">
                <el-input
                  :model-value="row.contractName"
                  size="small"
                  placeholder="合同名称"
                  @change="(val: string) => updateCell(row.rowId, 'contractName', val)"
                />
              </template>
              <span v-else :class="{ 'row-bold': row.rowId === '__subtotal__' }">
                {{ row.contractName }}
              </span>
            </template>
          </el-table-column>

          <el-table-column prop="currency" label="币种" width="70" align="center">
            <template #default="{ row }">
              <template v-if="row.rowId !== '__subtotal__' && !isReadonly">
                <el-input
                  :model-value="row.currency"
                  size="small"
                  style="width: 100%"
                  @change="(val: string) => updateCell(row.rowId, 'currency', val)"
                />
              </template>
              <span v-else>{{ row.currency }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="principal" label="本金" min-width="110" align="right">
            <template #default="{ row }">
              <template v-if="row.rowId !== '__subtotal__' && !isReadonly">
                <el-input-number
                  :model-value="row.principal"
                  :controls="false"
                  size="small"
                  style="width: 100%"
                  @change="(val: number | undefined) => updateCell(row.rowId, 'principal', val ?? 0)"
                />
              </template>
              <span v-else>{{ fmtAmount(row.principal) }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="rate" label="年利率(%)" width="90" align="right">
            <template #default="{ row }">
              <template v-if="row.rowId !== '__subtotal__' && !isReadonly">
                <el-input-number
                  :model-value="row.rate"
                  :controls="false"
                  :precision="4"
                  size="small"
                  style="width: 100%"
                  @change="(val: number | undefined) => updateCell(row.rowId, 'rate', val ?? 0)"
                />
              </template>
              <span v-else>{{ row.rate ? `${row.rate}%` : '-' }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="periodStart" label="计息起" width="110">
            <template #default="{ row }">
              <template v-if="row.rowId !== '__subtotal__' && !isReadonly">
                <el-date-picker
                  :model-value="row.periodStart"
                  type="date"
                  value-format="YYYY-MM-DD"
                  size="small"
                  style="width: 100%"
                  placeholder="起"
                  @update:model-value="(val: string) => updateCell(row.rowId, 'periodStart', val || '')"
                />
              </template>
              <span v-else>{{ row.periodStart || '-' }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="periodEnd" label="计息止" width="110">
            <template #default="{ row }">
              <template v-if="row.rowId !== '__subtotal__' && !isReadonly">
                <el-date-picker
                  :model-value="row.periodEnd"
                  type="date"
                  value-format="YYYY-MM-DD"
                  size="small"
                  style="width: 100%"
                  placeholder="止"
                  @update:model-value="(val: string) => updateCell(row.rowId, 'periodEnd', val || '')"
                />
              </template>
              <span v-else>{{ row.periodEnd || '-' }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="beginBalance" label="期初应付" min-width="110" align="right">
            <template #default="{ row }">
              <template v-if="row.rowId !== '__subtotal__' && !isReadonly">
                <el-input-number
                  :model-value="row.beginBalance"
                  :controls="false"
                  size="small"
                  style="width: 100%"
                  @change="(val: number | undefined) => updateCell(row.rowId, 'beginBalance', val ?? 0)"
                />
              </template>
              <span v-else>{{ fmtAmount(row.beginBalance) }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="accrued" label="本期计提" min-width="110" align="right">
            <template #default="{ row }">
              <template v-if="row.rowId !== '__subtotal__' && !isReadonly">
                <el-input-number
                  :model-value="row.accrued"
                  :controls="false"
                  size="small"
                  style="width: 100%"
                  @change="(val: number | undefined) => updateCell(row.rowId, 'accrued', val ?? 0)"
                />
              </template>
              <span v-else>{{ fmtAmount(row.accrued) }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="paid" label="本期支付" min-width="110" align="right">
            <template #default="{ row }">
              <template v-if="row.rowId !== '__subtotal__' && !isReadonly">
                <el-input-number
                  :model-value="row.paid"
                  :controls="false"
                  size="small"
                  style="width: 100%"
                  @change="(val: number | undefined) => updateCell(row.rowId, 'paid', val ?? 0)"
                />
              </template>
              <span v-else>{{ fmtAmount(row.paid) }}</span>
            </template>
          </el-table-column>

          <!-- 期末应付（公式列：虚线下划线+tooltip） -->
          <el-table-column label="期末应付" min-width="120" align="right">
            <template #header>
              <el-tooltip content="期末应付 = 期初 + 本期计提 − 本期支付（负债类）" placement="top">
                <span class="formula-col-header">期末应付</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <el-tooltip content="= 期初 + 计提 − 支付" placement="top">
                <span class="formula-cell">{{ fmtAmount(row.endBalance) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
        </template>

        <!-- ═══ Tab 2: 调整 (L~Q) ═══ -->
        <template v-if="activeArea === 'adjustment'">
          <el-table-column prop="contractName" label="合同名称" min-width="150" fixed>
            <template #default="{ row }">
              <span :class="{ 'row-bold': row.rowId === '__subtotal__' }">
                {{ row.contractName || row.source }}
              </span>
            </template>
          </el-table-column>

          <el-table-column prop="entityReclass" label="重分类" min-width="110" align="right">
            <template #default="{ row }">
              <template v-if="row.rowId !== '__subtotal__' && !isReadonly">
                <el-input-number
                  :model-value="row.entityReclass"
                  :controls="false"
                  size="small"
                  style="width: 100%"
                  @change="(val: number | undefined) => updateCell(row.rowId, 'entityReclass', val ?? 0)"
                />
              </template>
              <span v-else>{{ fmtAmount(row.entityReclass) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="期末未审" min-width="120" align="right">
            <template #header>
              <el-tooltip content="期末未审 = 期末应付 + 重分类" placement="top">
                <span class="formula-col-header">期末未审</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <el-tooltip content="= 期末应付 + 重分类" placement="top">
                <span class="formula-cell">{{ fmtAmount(row.endUnadjusted) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>

          <el-table-column prop="aje" label="AJE" min-width="100" align="right">
            <template #default="{ row }">
              <template v-if="row.rowId !== '__subtotal__' && !isReadonly">
                <el-input-number
                  :model-value="row.aje"
                  :controls="false"
                  size="small"
                  style="width: 100%"
                  @change="(val: number | undefined) => updateCell(row.rowId, 'aje', val ?? 0)"
                />
              </template>
              <span v-else>{{ fmtAmount(row.aje) }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="rje" label="RJE" min-width="100" align="right">
            <template #default="{ row }">
              <template v-if="row.rowId !== '__subtotal__' && !isReadonly">
                <el-input-number
                  :model-value="row.rje"
                  :controls="false"
                  size="small"
                  style="width: 100%"
                  @change="(val: number | undefined) => updateCell(row.rowId, 'rje', val ?? 0)"
                />
              </template>
              <span v-else>{{ fmtAmount(row.rje) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="审定数" min-width="120" align="right">
            <template #header>
              <el-tooltip content="审定 = 期末未审 + AJE + RJE" placement="top">
                <span class="formula-col-header">审定数</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <el-tooltip content="= 期末未审 + AJE + RJE" placement="top">
                <span class="formula-cell">{{ fmtAmount(row.audited) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
        </template>

        <!-- ═══ Tab 3: 审定 (R~U) ═══ -->
        <template v-if="activeArea === 'audited'">
          <el-table-column prop="contractName" label="合同名称" min-width="150" fixed>
            <template #default="{ row }">
              <span :class="{ 'row-bold': row.rowId === '__subtotal__' }">
                {{ row.contractName || row.source }}
              </span>
            </template>
          </el-table-column>

          <el-table-column prop="adjustedBegin" label="审定期初" min-width="120" align="right">
            <template #default="{ row }">
              <template v-if="row.rowId !== '__subtotal__' && !isReadonly">
                <el-input-number
                  :model-value="row.adjustedBegin"
                  :controls="false"
                  size="small"
                  style="width: 100%"
                  @change="(val: number | undefined) => updateCell(row.rowId, 'adjustedBegin', val ?? 0)"
                />
              </template>
              <span v-else>{{ fmtAmount(row.adjustedBegin) }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="adjustedAccrued" label="审定计提" min-width="120" align="right">
            <template #default="{ row }">
              <template v-if="row.rowId !== '__subtotal__' && !isReadonly">
                <el-input-number
                  :model-value="row.adjustedAccrued"
                  :controls="false"
                  size="small"
                  style="width: 100%"
                  @change="(val: number | undefined) => updateCell(row.rowId, 'adjustedAccrued', val ?? 0)"
                />
              </template>
              <span v-else>{{ fmtAmount(row.adjustedAccrued) }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="adjustedPaid" label="审定支付" min-width="120" align="right">
            <template #default="{ row }">
              <template v-if="row.rowId !== '__subtotal__' && !isReadonly">
                <el-input-number
                  :model-value="row.adjustedPaid"
                  :controls="false"
                  size="small"
                  style="width: 100%"
                  @change="(val: number | undefined) => updateCell(row.rowId, 'adjustedPaid', val ?? 0)"
                />
              </template>
              <span v-else>{{ fmtAmount(row.adjustedPaid) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="审定期末" min-width="120" align="right">
            <template #header>
              <el-tooltip content="审定期末 = 审定期初 + 审定计提 − 审定支付（负债类）" placement="top">
                <span class="formula-col-header">审定期末</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <el-tooltip content="= 审定期初 + 审定计提 − 审定支付" placement="top">
                <span class="formula-cell">{{ fmtAmount(row.adjustedEnd) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
        </template>

        <!-- ═══ Tab 4: 逾期+附注 (V~AA) ═══ -->
        <template v-if="activeArea === 'overdue'">
          <el-table-column prop="contractName" label="合同名称" min-width="150" fixed>
            <template #default="{ row }">
              <span :class="{ 'row-bold': row.rowId === '__subtotal__' }">
                {{ row.contractName || row.source }}
              </span>
            </template>
          </el-table-column>

          <el-table-column prop="overdueMonths" label="逾期月数" width="90" align="center">
            <template #default="{ row }">
              <template v-if="row.rowId !== '__subtotal__' && !isReadonly">
                <el-input-number
                  :model-value="row.overdueMonths"
                  :controls="false"
                  :min="0"
                  size="small"
                  style="width: 100%"
                  @change="(val: number | undefined) => updateCell(row.rowId, 'overdueMonths', val ?? 0)"
                />
              </template>
              <span v-else :class="{ 'overdue-text': row.overdueMonths > 0 }">
                {{ row.overdueMonths || '-' }}
              </span>
            </template>
          </el-table-column>

          <el-table-column prop="overdueReason" label="逾期原因" min-width="150">
            <template #default="{ row }">
              <template v-if="row.rowId !== '__subtotal__' && !isReadonly">
                <el-input
                  :model-value="row.overdueReason"
                  size="small"
                  placeholder="填写原因"
                  @change="(val: string) => updateCell(row.rowId, 'overdueReason', val)"
                />
              </template>
              <span v-else>{{ row.overdueReason || '-' }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="pledgeType" label="抵质押类型" min-width="110">
            <template #default="{ row }">
              <template v-if="row.rowId !== '__subtotal__' && !isReadonly">
                <el-select
                  :model-value="row.pledgeType"
                  placeholder="选择"
                  size="small"
                  clearable
                  style="width: 100%"
                  @change="(val: string) => updateCell(row.rowId, 'pledgeType', val)"
                >
                  <el-option label="信用" value="信用" />
                  <el-option label="抵押" value="抵押" />
                  <el-option label="质押" value="质押" />
                  <el-option label="保证" value="保证" />
                </el-select>
              </template>
              <span v-else>{{ row.pledgeType || '-' }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="noteRef" label="附注引用" min-width="100">
            <template #default="{ row }">
              <template v-if="row.rowId !== '__subtotal__' && !isReadonly">
                <el-input
                  :model-value="row.noteRef"
                  size="small"
                  placeholder="附注编号"
                  @change="(val: string) => updateCell(row.rowId, 'noteRef', val)"
                />
              </template>
              <span v-else>{{ row.noteRef || '-' }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="isOverdue" label="逾期" width="60" align="center">
            <template #default="{ row }">
              <span v-if="row.isOverdue" class="overdue-badge">是</span>
              <span v-else>-</span>
            </template>
          </el-table-column>

          <el-table-column prop="remark" label="备注" min-width="150">
            <template #default="{ row }">
              <template v-if="row.rowId !== '__subtotal__' && !isReadonly">
                <el-input
                  :model-value="row.remark"
                  size="small"
                  placeholder="备注"
                  @change="(val: string) => updateCell(row.rowId, 'remark', val)"
                />
              </template>
              <span v-else>{{ row.remark || '-' }}</span>
            </template>
          </el-table-column>
        </template>

        <!-- ═══ 操作列（所有Tab共用） ═══ -->
        <el-table-column
          v-if="!isReadonly"
          label="操作"
          width="60"
          align="center"
          fixed="right"
        >
          <template #default="{ row }">
            <el-button
              v-if="row.rowId !== '__subtotal__'"
              type="danger"
              text
              size="small"
              @click="handleRemoveRow(row.rowId)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 逾期统计 ═══ -->
    <div v-if="overdueRows.length > 0" class="overdue-summary">
      <el-icon><WarningFilled /></el-icon>
      逾期笔数：{{ overdueRows.length }} 笔，逾期金额合计：{{ fmtAmount(overdueTotal) }}
    </div>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>来源+未审</strong>：按借款/债券逐笔录入，期末应付 = 期初 + 计提 − 支付（负债类方向）</li>
        <li><strong>调整</strong>：期末未审 = 期末应付 + 重分类；审定 = 期末未审 + AJE + RJE</li>
        <li><strong>审定验证</strong>：审定期末 = 审定期初 + 审定计提 − 审定支付</li>
        <li><strong>逾期</strong>：逾期月数 > 0 自动标红高亮，须填写逾期原因</li>
        <li><strong>合计</strong>：明细合计应与L2-1审定表期末余额一致</li>
        <li><strong>计提核对</strong>：L1/L3利息测算金额应与本期计提合计一致</li>
        <li><strong>导入</strong>：可通过"导入导出"下载模板 → 填写 → 上传导入批量数据</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L2TabDetail.vue — L2-2 应付利息明细表（27列区段Tab+计提核对）
 *
 * 核心功能：
 * - 27列宽表拆为4区段Tab（来源+未审/调整/审定/逾期+附注），行同步
 * - 动态行新增（ElMessageBox.prompt输入名称确认后创建）/ 删除
 * - 公式列：期末应付=期初+计提-支付（负债类，虚线下划线+tooltip）
 * - 计提核对：接收L1/L3利息测算 vs 账面计提（accrualVsL1L3指示器）
 * - 导入导出：el-dropdown三级（useL2ImportExport）
 * - 搜索框：按合同名称/来源过滤
 * - 逾期行红色高亮 + 小计行
 *
 * Spec: .kiro/specs/l2-interest-payable/
 * Task: 4.3
 * Requirements: 3.1-3.5, 4.1-4.5
 *
 * 科目：2231 应付利息（贷方/负债类！）
 */
import { computed, inject, toRef, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Plus, ArrowDown, MagicStick, WarningFilled } from '@element-plus/icons-vue'
import { useL2FormData } from '../../composables/useL2FormData'
import { useL2Detail, SOURCE_OPTIONS, type DetailRow, type AreaGroup } from '../../composables/useL2Detail'
import { useL2CrossSheet } from '../../composables/useL2CrossSheet'
import { useL2ImportExport } from '../../composables/useL2ImportExport'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

// ─── Inject openReviewDialog ─────────────────────────────────────────────────

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>(
  'openReviewDialog',
  () => {},
)

// ─── Composable: useL2FormData ───────────────────────────────────────────────

const {
  allResponses,
  loadData,
  saveField,
  debouncedSave,
} = useL2FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

// 加载数据
loadData()

// ─── Composable: useL2Detail ─────────────────────────────────────────────────

const {
  rows,
  filteredRows,
  subtotalRow,
  overdueRows,
  overdueTotal,
  searchQuery,
  activeArea,
  addRow,
  removeRow,
  updateCell,
  batchImportRows,
} = useL2Detail({
  allResponses,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  debouncedSave,
  saveField,
})

// ─── Composable: useL2CrossSheet（计提核对） ─────────────────────────────────

const {
  accrualVsL1L3,
  l1EstimatedInterest,
  l3EstimatedInterest,
  isInterestDataReady,
} = useL2CrossSheet(allResponses)

// ─── Composable: useL2ImportExport ───────────────────────────────────────────

const {
  exportTemplate,
  exportData,
  importData,
} = useL2ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

// ─── 区段Tab选项 ─────────────────────────────────────────────────────────────

const areaOptions = [
  { label: '来源+未审', value: 'source' },
  { label: '调整', value: 'adjustment' },
  { label: '审定', value: 'audited' },
  { label: '逾期+附注', value: 'overdue' },
]

// ─── 展示行（filteredRows + subtotal） ───────────────────────────────────────

const displayRows = computed<DetailRow[]>(() => {
  return [...filteredRows.value, subtotalRow.value]
})

// ─── 计提核对样式 ─────────────────────────────────────────────────────────────

const accrualCheckClass = computed(() => ({
  'accrual-consistent': accrualVsL1L3.value.isConsistent,
  'accrual-diff': !accrualVsL1L3.value.isConsistent,
}))

// ─── 行样式（逾期红色高亮+合计行绿色） ───────────────────────────────────────

function getRowClassName({ row }: { row: DetailRow }): string {
  if (row.rowId === '__subtotal__') return 'subtotal-row'
  if (row.isOverdue) return 'overdue-row'
  return ''
}

// ─── 新增行（必须弹 ElMessageBox.prompt 输入名称确认） ────────────────────────

async function handleAddRow(): Promise<void> {
  try {
    const { value: name } = await ElMessageBox.prompt(
      '请输入合同/借款名称',
      '新增明细行',
      {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '名称不能为空',
        inputPlaceholder: '如：XX银行短期借款',
      },
    )
    if (name) {
      addRow()
      // 立即设置名称到新增的最后一行
      const lastRow = rows.value[rows.value.length - 1]
      if (lastRow) {
        updateCell(lastRow.rowId, 'contractName', name.trim())
      }
    }
  } catch {
    // 用户取消
  }
}

// ─── 删除行 ──────────────────────────────────────────────────────────────────

function handleRemoveRow(rowId: string): void {
  removeRow(rowId)
  ElMessage.success('已删除')
}

// ─── 导入导出 ────────────────────────────────────────────────────────────────

/** 隐藏的 file input ref */
const fileInputRef = ref<HTMLInputElement | null>(null)

async function handleImportExportCommand(command: string): Promise<void> {
  switch (command) {
    case 'exportTemplate':
      await exportTemplate('L2-2')
      break
    case 'exportData':
      await exportData('L2-2')
      break
    case 'importData':
      triggerFileInput()
      break
  }
}

function triggerFileInput(): void {
  // 创建隐藏的 file input 触发选择
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls'
  input.style.display = 'none'
  input.addEventListener('change', async () => {
    const file = input.files?.[0]
    if (file) {
      const result = await importData(file, 'L2-2')
      if (result.success && result.rowCount) {
        // 刷新数据（重新loadData触发watch）
        await loadData()
      }
    }
    document.body.removeChild(input)
  })
  document.body.appendChild(input)
  input.click()
}

// ─── AI辅助 ──────────────────────────────────────────────────────────────────

function handleAI(): void {
  ElMessage.info('AI辅助分析功能建设中...')
}

// ─── 复核 ────────────────────────────────────────────────────────────────────

function handleReview(): void {
  openReviewDialog('L2-2-detail', 'L2-2 应付利息明细表')
}

// ─── 金额格式化 ──────────────────────────────────────────────────────────────

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) {
    return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  }
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.l2-tab-detail {
  padding: 12px;
  font-size: 13px;
}

/* ─── 标题行 + AI/复核按钮右对齐 ─── */
.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.detail-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

.detail-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ─── 方法论上下文（琥珀色左边线+浅黄背景） ─── */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 14px;
  font-size: 13px;
  color: #5a4e3a;
  line-height: 1.6;
}

.methodology-text strong {
  color: #b88230;
}

/* ─── 计提核对指示器 ─── */
.accrual-check-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 16px;
  margin-bottom: 14px;
  padding: 8px 12px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 13px;
}

.accrual-check-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.accrual-label {
  color: #606266;
  font-weight: 500;
}

.accrual-consistent {
  color: #67c23a;
  font-weight: 600;
}

.accrual-diff {
  color: #f56c6c;
  font-weight: 600;
}

.accrual-pending {
  color: #e6a23c;
  font-style: italic;
}

/* ─── 工具栏 ─── */
.detail-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

/* ─── 表格卡片 ─── */
.detail-table-card {
  margin-bottom: 12px;
}

/* ─── 公式列表头（虚线下划线 + cursor:help） ─── */
.formula-col-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 1px;
}

/* ─── 公式列单元格（虚线下划线 + cursor:help） ─── */
.formula-cell {
  border-bottom: 1px dashed #c0c4cc;
  cursor: help;
  padding-bottom: 1px;
  display: inline-block;
}

/* ─── 行粗体 ─── */
.row-bold {
  font-weight: 700;
}

/* ─── 合计行样式 ─── */
:deep(.subtotal-row) {
  background-color: #f0f9eb !important;
  font-weight: 700;
}

/* ─── 逾期行红色高亮 ─── */
:deep(.overdue-row) {
  background-color: #fef0f0 !important;
}

.overdue-text {
  color: #f56c6c;
  font-weight: 600;
}

.overdue-badge {
  color: #fff;
  background: #f56c6c;
  border-radius: 4px;
  padding: 1px 6px;
  font-size: 11px;
  font-weight: 600;
}

/* ─── 逾期统计 ─── */
.overdue-summary {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: #fef0f0;
  border: 1px solid #fbc4c4;
  border-radius: 6px;
  margin-bottom: 12px;
  font-size: 13px;
  color: #f56c6c;
  font-weight: 500;
}

/* ─── 表格统一13px字体 ─── */
:deep(.el-table) {
  font-size: 13px;
}

:deep(.el-table th .cell) {
  font-size: 13px;
  font-weight: 600;
}

/* ─── 编制提示折叠 ─── */
.l2-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 13px;
  color: #606266;
}

.l2-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.l2-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
