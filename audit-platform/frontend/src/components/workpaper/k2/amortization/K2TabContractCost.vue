<!--
  K2TabContractCost.vue — K2-4 合同取得成本明细表（57公式+3区段+资本化判断+动态行）

  23列宽表拆3区段 el-segmented 切换：
    区段0 "合同"：合同编号/客户/合同金额/取得成本类型/是否资本化/CAS14三条件
    区段1 "摊销"：期初余额/本期增加/本期摊销/期末余额(公式)
    区段2 "检查"：摊销方法/摊销期/凭证号/结论

  核心功能：
  1. CAS14资本化判断面板（蓝色信息区+三个toggle+自动结论）
  2. 公式列：期末余额=期初+增加-摊销（虚线下划线+tooltip）
  3. 交叉验证badge：K2-4合计 vs K2-1审定合同取得成本
  4. "+新增" → ElMessageBox.prompt合同编号 → 创建行
  5. el-dropdown "导入导出 ▾"
  6. 方法论上下文块（琥珀色）
  7. 底部合计栏

  Spec: .kiro/specs/k2-other-current-assets/ Task 4.4
  Requirements: 4.1-4.6
-->
<template>
  <div class="k2-tab-contract-cost">
    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景）═══ -->
    <div class="methodology-context">
      <p>
        <strong>CAS14 合同取得成本资本化条件：</strong>企业为取得合同发生的增量成本预期能够收回的，
        应当作为合同取得成本确认为一项资产。增量成本是指企业不取得合同就不会发生的成本（如销售佣金）。
        资本化三条件：①增量成本 ②预期可收回 ③与合同直接相关。三条件均满足方可资本化，否则发生时费用化。
      </p>
    </div>

    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>存在：</b>记录的合同取得成本是存在的，且已记录于恰当的账户；</li>
        <li><b>计价和分摊：</b>合同取得成本的确认和计量符合 CAS14，资本化条件判断恰当，以恰当金额列示；</li>
        <li><b>列报与披露：</b>合同取得成本已按企业会计准则规定作出恰当列报。</li>
      </ol>
    </el-alert>

    <!-- ═══ 标题栏 + 操作按钮 ═══ -->
    <div class="section-head">
      <h3 class="sheet-title">K2-4 合同取得成本明细表</h3>
      <div class="head-actions">
        <!-- 交叉验证badge -->
        <el-tag
          v-if="crossValidation"
          :type="crossValidation.isMatch ? 'success' : 'danger'"
          effect="plain"
          size="small"
          class="cross-badge"
        >
          {{ crossValidation.isMatch ? '✓ K2-1一致' : `✗ K2-1差异 ${fmtAmt(crossValidation.diff)}` }}
        </el-tag>
        <el-button size="small" :disabled="isReadonly" @click="handleAddRow">＋ 新增</el-button>
        <el-button size="small" :disabled="isReadonly" type="warning" plain @click="handleImportFromDetail">从K2-2带入</el-button>
        <el-dropdown trigger="click" size="small">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item @click="handleImportData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <!-- ═══ CAS14 资本化判断面板（蓝色引导区）═══ -->
    <div v-if="selectedRow" class="cas14-panel">
      <div class="cas14-header">
        <span class="cas14-title">CAS14 资本化判断 — {{ selectedRow.contractNo || '(未命名)' }}</span>
        <el-tag
          :type="isSuggestedCapitalize ? 'success' : 'warning'"
          effect="dark"
          size="small"
        >
          {{ isSuggestedCapitalize ? '建议资本化' : '建议费用化' }}
        </el-tag>
      </div>
      <div class="cas14-conditions">
        <div class="condition-item">
          <span class="condition-label">① 增量成本</span>
          <el-switch
            :model-value="selectedRow.isIncremental"
            :disabled="isReadonly"
            active-text="是"
            inactive-text="否"
            @change="(v: boolean) => handleConditionChange('isIncremental', v)"
          />
        </div>
        <div class="condition-item">
          <span class="condition-label">② 预期可收回</span>
          <el-switch
            :model-value="selectedRow.isRecoverable"
            :disabled="isReadonly"
            active-text="是"
            inactive-text="否"
            @change="(v: boolean) => handleConditionChange('isRecoverable', v)"
          />
        </div>
        <div class="condition-item">
          <span class="condition-label">③ 与合同直接相关</span>
          <el-switch
            :model-value="selectedRow.isDirectlyRelated"
            :disabled="isReadonly"
            active-text="是"
            inactive-text="否"
            @change="(v: boolean) => handleConditionChange('isDirectlyRelated', v)"
          />
        </div>
      </div>
    </div>

    <!-- ═══ 3区段 el-segmented ═══ -->
    <div class="segment-bar">
      <el-segmented
        v-model="activeSegment"
        :options="segmentOptions"
        size="default"
      />
    </div>

    <!-- ═══ 表格 ═══ -->
    <el-table
      :data="rows"
      border
      size="small"
      :max-height="480"
      highlight-current-row
      class="contract-cost-table"
      @current-change="handleRowSelect"
    >
      <!-- 固定列：序号 -->
      <el-table-column label="#" width="50" align="center" fixed>
        <template #default="{ $index }">{{ $index + 1 }}</template>
      </el-table-column>

      <!-- ═══ 区段0: 合同 ═══ -->
      <template v-if="activeSegment === '合同'">
        <el-table-column label="合同编号" min-width="130">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.contractNo"
              size="small"
              @change="(v: string) => updateCell(row.rowId, 'contractNo', v)"
            />
            <span v-else>{{ row.contractNo || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="客户" min-width="140">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.customer"
              size="small"
              @change="(v: string) => updateCell(row.rowId, 'customer', v)"
            />
            <span v-else>{{ row.customer || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="合同金额" min-width="130" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.contractAmount"
              size="small"
              :controls="false"
              class="amount-input"
              @change="(v: number) => updateCell(row.rowId, 'contractAmount', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.contractAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="取得成本类型" min-width="120">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.costType"
              size="small"
              placeholder="选择"
              @change="(v: string) => updateCell(row.rowId, 'costType', v)"
            >
              <el-option v-for="opt in costTypeOptions" :key="opt" :label="opt" :value="opt" />
            </el-select>
            <span v-else>{{ row.costType || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="资本化" width="80" align="center">
          <template #default="{ row }">
            <el-tag
              :type="row.isCapitalized ? 'success' : 'info'"
              size="small"
              effect="plain"
            >
              {{ row.isCapitalized ? '是' : '否' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="增量成本" width="90" align="center">
          <template #default="{ row }">
            <el-switch
              v-if="!isReadonly"
              :model-value="row.isIncremental"
              size="small"
              @change="(v: boolean) => { updateCell(row.rowId, 'isIncremental', v); autoUpdateCapitalized(row.rowId) }"
            />
            <el-icon v-else :color="row.isIncremental ? '#67c23a' : '#909399'">
              <component :is="row.isIncremental ? 'CircleCheckFilled' : 'CircleCloseFilled'" />
            </el-icon>
          </template>
        </el-table-column>
        <el-table-column label="可收回" width="90" align="center">
          <template #default="{ row }">
            <el-switch
              v-if="!isReadonly"
              :model-value="row.isRecoverable"
              size="small"
              @change="(v: boolean) => { updateCell(row.rowId, 'isRecoverable', v); autoUpdateCapitalized(row.rowId) }"
            />
            <el-icon v-else :color="row.isRecoverable ? '#67c23a' : '#909399'">
              <component :is="row.isRecoverable ? 'CircleCheckFilled' : 'CircleCloseFilled'" />
            </el-icon>
          </template>
        </el-table-column>
        <el-table-column label="直接相关" width="90" align="center">
          <template #default="{ row }">
            <el-switch
              v-if="!isReadonly"
              :model-value="row.isDirectlyRelated"
              size="small"
              @change="(v: boolean) => { updateCell(row.rowId, 'isDirectlyRelated', v); autoUpdateCapitalized(row.rowId) }"
            />
            <el-icon v-else :color="row.isDirectlyRelated ? '#67c23a' : '#909399'">
              <component :is="row.isDirectlyRelated ? 'CircleCheckFilled' : 'CircleCloseFilled'" />
            </el-icon>
          </template>
        </el-table-column>
        <!-- 操作列 -->
        <el-table-column label="操作" width="60" align="center" fixed="right">
          <template #default="{ row }">
            <el-popconfirm
              title="确认删除此行?"
              confirm-button-text="删除"
              cancel-button-text="取消"
              @confirm="handleRemoveRow(row.rowId)"
            >
              <template #reference>
                <el-button type="danger" link size="small" :disabled="isReadonly">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 区段1: 摊销 ═══ -->
      <template v-if="activeSegment === '摊销'">
        <el-table-column label="合同编号" min-width="130">
          <template #default="{ row }">
            <span>{{ row.contractNo || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" min-width="130" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.beginBalance"
              size="small"
              :controls="false"
              class="amount-input"
              @change="(v: number) => updateCell(row.rowId, 'beginBalance', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期增加" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.periodIncrease"
              size="small"
              :controls="false"
              class="amount-input"
              @change="(v: number) => updateCell(row.rowId, 'periodIncrease', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.periodIncrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期摊销" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.periodAmort"
              size="small"
              :controls="false"
              class="amount-input"
              @change="(v: number) => updateCell(row.rowId, 'periodAmort', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.periodAmort) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="130" align="right">
          <template #default="{ row }">
            <el-tooltip content="期末=期初+增加-摊销" placement="top">
              <span class="formula-cell">{{ fmtAmt(row.endBalance) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="成本率" width="90" align="center">
          <template #default="{ row }">
            <el-tooltip :content="`取得成本率 = 期末余额 / 合同金额 = ${costRatio(row)}`" placement="top">
              <span :class="['formula-cell', { 'rate-warn': costRatioNum(row) > 50 }]">{{ costRatio(row) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 区段2: 检查 ═══ -->
      <template v-if="activeSegment === '检查'">
        <el-table-column label="合同编号" min-width="130">
          <template #default="{ row }">
            <span>{{ row.contractNo || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="摊销方法" min-width="100">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.amortMethod"
              size="small"
              @change="(v: string) => updateCell(row.rowId, 'amortMethod', v)"
            >
              <el-option label="直线法" value="直线法" />
              <el-option label="进度法" value="进度法" />
            </el-select>
            <span v-else>{{ row.amortMethod || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="摊销期(月)" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.amortPeriod"
              size="small"
              :controls="false"
              :min="0"
              class="amount-input"
              @change="(v: number) => updateCell(row.rowId, 'amortPeriod', v ?? 0)"
            />
            <span v-else>{{ row.amortPeriod || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭证号" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.voucherRef"
              size="small"
              placeholder="凭证"
              @change="(v: string) => updateCell(row.rowId, 'voucherRef', v)"
            />
            <span v-else>{{ row.voucherRef || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="结论" min-width="100">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.conclusion"
              size="small"
              placeholder="选择"
              @change="(v: string) => updateCell(row.rowId, 'conclusion', v)"
            >
              <el-option label="正常" value="正常" />
              <el-option label="异常" value="异常" />
              <el-option label="待确认" value="待确认" />
            </el-select>
            <el-tag v-else :type="conclusionType(row.conclusion)" size="small" effect="plain">
              {{ row.conclusion || '-' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="180">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.remark"
              size="small"
              placeholder="备注"
              @change="(v: string) => updateCell(row.rowId, 'remark', v)"
            />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
      </template>
    </el-table>

    <!-- ═══ 底部合计栏 ═══ -->
    <div class="subtotals-bar">
      <el-tag type="info" effect="plain">合同数: {{ subtotals.count }}</el-tag>
      <el-tag type="primary" effect="plain">合同金额合计: {{ fmtAmt(subtotals.contractAmount) }}</el-tag>
      <el-tag type="primary" effect="plain">期初合计: {{ fmtAmt(subtotals.beginBalance) }}</el-tag>
      <el-tag type="success" effect="plain">增加合计: {{ fmtAmt(subtotals.periodIncrease) }}</el-tag>
      <el-tag type="warning" effect="plain">摊销合计: {{ fmtAmt(subtotals.periodAmort) }}</el-tag>
      <el-tag type="primary" effect="dark">期末合计: {{ fmtAmt(subtotals.endBalance) }}</el-tag>
      <el-button v-if="!isReadonly && capitalizedWithAmortRows.length > 0" size="small" type="success" plain style="margin-left:auto" @click="handlePushToK25">
        推送至K2-5（{{ capitalizedWithAmortRows.length }}笔）
      </el-button>
    </div>

    <!-- 隐藏的文件上传 -->
    <input
      ref="fileInputRef"
      type="file"
      accept=".xlsx,.xls"
      style="display: none"
      @change="handleFileSelected"
    />

    <!-- 费用化提示（有不满足资本化条件的行） -->
    <el-alert v-if="nonCapitalizedRows.length > 0" type="warning" :closable="false" style="margin:12px 0">
      <template #title>⚠️ {{ nonCapitalizedRows.length }} 个合同不满足CAS14资本化条件（建议费用化）</template>
      <div style="font-size:12px;margin-top:4px">
        {{ nonCapitalizedRows.map(r => r.contractNo || '(未命名)').join('、') }}
        —— 不满足"增量+可收回+直接相关"三条件，应在发生时计入费用（销售费用/管理费用），不应列示为其他流动资产
      </div>
    </el-alert>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示（CAS14 / CAS15）</summary>
      <ul>
        <li>CAS14§95：企业为取得合同发生的增量成本预期能够收回的，作为合同取得成本确认为一项资产</li>
        <li>增量成本=企业不取得合同就不会发生的成本（典型：销售佣金、投标费）；差旅费通常不满足增量条件</li>
        <li>资本化三条件全满足→确认资产（本表列示）；任一不满足→发生时费用化（不应在本表）</li>
        <li>摊销方法选择：合同履约进度可靠计量→进度法；无法可靠计量→直线法（按合同期限均摊）</li>
        <li>期末余额(公式)=期初+增加-摊销；合计应与K2-1审定表"合同取得成本"行一致</li>
        <li>区段2"检查"核对摊销方法/期限是否与合同条款一致、计算是否准确（与K2-5测算对比）</li>
        <li>合同金额远大于取得成本属正常（佣金率通常1%~5%）；取得成本率异常高应关注</li>
      </ul>
    </details>

    <!-- 审计说明 -->
    <el-card shadow="never" style="margin-bottom:12px">
      <template #header>
        <div class="section-title-row">
          <span class="card-title">审计说明</span>
          <div style="display:flex;gap:8px;align-items:center">
            <el-button size="small" type="primary" link :disabled="isReadonly" @click="handleAiNote">
              🤖 AI生成
            </el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="概述合同取得成本资本化判断过程、摊销方法选择依据、与K2-5测算核对情况..."
        @blur="persistNote"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" style="margin-bottom:12px">
      <template #header>
        <div class="section-title-row">
          <span class="card-title">审计结论</span>
          <div style="display:flex;gap:8px;align-items:center">
            <el-button size="small" type="primary" link :disabled="isReadonly" @click="handleAiConclusion">
              🤖 AI生成
            </el-button>
            <el-button size="small" type="default" link @click="handleReview">💬 复核</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="基于上述分析，形成合同取得成本审计结论..."
        @blur="persistConclusion"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * K2TabContractCost.vue — K2-4 合同取得成本明细表
 *
 * 57公式 + 3区段(合同/摊销/检查) + CAS14资本化判断 + 动态行
 *
 * Composable: useK2ContractCost (data/logic) + useK2ImportExport (导入导出) + useK2CrossSheet (交叉验证)
 * Props: wpId, projectId, allResponses, isReadonly
 * Emits: save, navigate-sheet
 *
 * Spec: .kiro/specs/k2-other-current-assets/
 * Task: 4.4
 * Requirements: 4.1-4.6
 */
import { ref, computed, toRef, inject, watch } from 'vue'
import { CircleCheckFilled, CircleCloseFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import {
  useK2ContractCost,
  type K2ContractCostRow,
} from '../../composables/useK2ContractCost'
import { useK2ImportExport } from '../../composables/useK2ImportExport'
import { useK2CrossSheet } from '../../composables/useK2CrossSheet'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

// ─── Composables ─────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)

const {
  rows,
  activeSection,
  subtotals,
  capitalizationSuggestions,
  updateCell,
  recalcAll,
  addRow,
  removeRow,
  importRows,
  exportRows,
} = useK2ContractCost(allResponsesRef, {
  onSave: (itemId, value) => emit('save', itemId, value),
})

const { exportTemplate, exportData, importData } = useK2ImportExport({
  wpId: toRef(props, 'wpId'),
})

const { contractCostVsAmort } = useK2CrossSheet(allResponsesRef)

// ─── Segment Tabs ────────────────────────────────────────────────────────────

const segmentOptions = ['合同', '摊销', '检查']
const activeSegment = ref<string>('合同')

// ─── Selected Row (for CAS14 panel) ──────────────────────────────────────────

const selectedRowId = ref<string | null>(null)

const selectedRow = computed(() => {
  if (!selectedRowId.value) return rows.value.length > 0 ? rows.value[0] : null
  return rows.value.find((r) => r.rowId === selectedRowId.value) ?? null
})

const isSuggestedCapitalize = computed(() => {
  if (!selectedRow.value) return false
  return capitalizationSuggestions.value.get(selectedRow.value.rowId) ?? false
})

function handleRowSelect(row: K2ContractCostRow | null): void {
  selectedRowId.value = row?.rowId ?? null
}

// ─── CAS14 Condition Toggle ──────────────────────────────────────────────────

/** 行内直接toggle后自动更新isCapitalized（三条件均满足=资本化） */
function autoUpdateCapitalized(rowId: string): void {
  const row = rows.value.find(r => r.rowId === rowId)
  if (!row) return
  const allMet = row.isIncremental && row.isRecoverable && row.isDirectlyRelated
  if (row.isCapitalized !== allMet) {
    updateCell(rowId, 'isCapitalized', allMet)
  }
}

function handleConditionChange(field: 'isIncremental' | 'isRecoverable' | 'isDirectlyRelated', value: boolean): void {
  if (!selectedRow.value) return
  updateCell(selectedRow.value.rowId, field, value)
  // Auto-update isCapitalized based on all 3 conditions
  const row = selectedRow.value
  const allMet = (field === 'isIncremental' ? value : row.isIncremental)
    && (field === 'isRecoverable' ? value : row.isRecoverable)
    && (field === 'isDirectlyRelated' ? value : row.isDirectlyRelated)
  updateCell(selectedRow.value.rowId, 'isCapitalized', allMet)
}

// ─── Cross-validation ────────────────────────────────────────────────────────

const crossValidation = computed(() => {
  // K2-4 total vs K2-1 审定合同取得成本
  return contractCostVsAmort.value
})

// ─── Constants ───────────────────────────────────────────────────────────────

const costTypeOptions = ['佣金', '手续费', '差旅费', '投标费', '其他']

// ─── Actions ─────────────────────────────────────────────────────────────────

async function handleAddRow(): Promise<void> {
  // composable的addRow内含ElMessageBox.prompt弹窗，直接调用即可
  await addRow()
}

/** 从K2-2明细表带入"合同取得成本"性质行（无弹窗批量） */
function handleImportFromDetail(): void {
  const detailRows = props.allResponses.get('K2-2-detail-rows')
  if (!detailRows?.remark) {
    ElMessage.warning('K2-2明细表暂无数据，请先编制明细表')
    return
  }
  try {
    const parsed = JSON.parse(detailRows.remark)
    const contractRows = (Array.isArray(parsed) ? parsed : [])
      .filter((r: any) => r.nature === '合同取得成本' && r.name)
    if (contractRows.length === 0) {
      ElMessage.info('K2-2中未找到"合同取得成本"性质的项目')
      return
    }
    let importedCount = 0
    for (const item of contractRows) {
      const existing = rows.value.find((r) => r.contractNo === item.name || r.customer === item.name)
      if (!existing) {
        // 直接push行数据，不走addRow弹窗
        const newRow: K2ContractCostRow = {
          rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}-${importedCount}`,
          contractNo: item.name,
          customer: '',
          contractAmount: 0,
          costType: '',
          isCapitalized: false,
          isIncremental: false,
          isRecoverable: false,
          isDirectlyRelated: false,
          beginBalance: Number(item.beginBalance ?? 0),
          periodIncrease: Number(item.increase ?? 0),
          periodAmort: Number(item.decrease ?? 0),
          endBalance: 0,
          amortMethod: '直线法',
          amortPeriod: 0,
          voucherRef: '',
          conclusion: '',
          remark: '从K2-2带入',
        }
        // 计算期末
        newRow.endBalance = newRow.beginBalance + newRow.periodIncrease - newRow.periodAmort
        rows.value.push(newRow)
        importedCount++
      }
    }
    if (importedCount > 0) {
      recalcAll()
      emit('save', 'K2-4-rows', { remark: JSON.stringify(rows.value) })
      ElMessage.success(`已从K2-2带入 ${importedCount} 个合同取得成本项目`)
    } else {
      ElMessage.info('所有项目已存在，无需带入')
    }
  } catch {
    ElMessage.warning('解析K2-2数据失败')
  }
}

function handleRemoveRow(rowId: string): void {
  removeRow(rowId)
}

// ─── Import/Export ───────────────────────────────────────────────────────────

const fileInputRef = ref<HTMLInputElement | null>(null)

function handleExportTemplate(): void {
  exportTemplate('K2-4')
}

function handleExportData(): void {
  exportData('K2-4')
}

function handleImportData(): void {
  fileInputRef.value?.click()
}

async function handleFileSelected(event: Event): Promise<void> {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  const result = await importData('K2-4', file)
  if (result && result.rowCount > 0) {
    // Re-trigger load from allResponses (import updates backend data)
    recalcAll()
  }
  // Reset file input
  target.value = ''
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function costRatio(row: K2ContractCostRow): string {
  if (!row.contractAmount || row.contractAmount === 0) return '-'
  const ratio = (row.endBalance / row.contractAmount) * 100
  return `${ratio.toFixed(1)}%`
}

function costRatioNum(row: K2ContractCostRow): number {
  if (!row.contractAmount || row.contractAmount === 0) return 0
  return (row.endBalance / row.contractAmount) * 100
}

function conclusionType(conclusion: string): 'success' | 'danger' | 'warning' | 'info' {
  switch (conclusion) {
    case '正常': return 'success'
    case '异常': return 'danger'
    case '待确认': return 'warning'
    default: return 'info'
  }
}

// ─── 审计说明 / 结论 / AI / 复核 / 费用化提示 ────────────────────────────────

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const auditNote = ref('')
const auditConclusion = ref('')

// 不满足资本化条件的行（CAS14三条件至少一个为false且beginBalance>0或periodIncrease>0）
const nonCapitalizedRows = computed(() =>
  rows.value.filter(r => !r.isCapitalized && (r.beginBalance > 0 || r.periodIncrease > 0)),
)

// 加载审计说明/结论
watch(allResponsesRef, () => {
  const noteItem = props.allResponses.get('K2-4-audit-note')
  auditNote.value = noteItem?.remark ?? ''
  const conclItem = props.allResponses.get('K2-4-audit-conclusion')
  auditConclusion.value = conclItem?.remark ?? ''
}, { immediate: true })

function persistNote(): void {
  emit('save', 'K2-4-audit-note', { remark: auditNote.value })
}
function persistConclusion(): void {
  emit('save', 'K2-4-audit-conclusion', { remark: auditConclusion.value })
}

async function handleAiNote(): Promise<void> {
  try {
    const context: Record<string, string> = {
      accountCode: '1231',
      sheet: 'K2-4',
      contractCount: String(rows.value.length),
      capitalizedCount: String(rows.value.filter(r => r.isCapitalized).length),
      nonCapitalizedCount: String(nonCapitalizedRows.value.length),
      endBalanceTotal: String(subtotals.value.endBalance),
      crossValidation: crossValidation.value ? (crossValidation.value.isMatch ? '与K2-1一致' : `与K2-1差异${crossValidation.value.diff}`) : '未计算',
    }
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      prompt: '请生成合同取得成本(CAS14)明细表审计说明，概述资本化判断过程、摊销方法选择依据、与K2-5测算核对情况',
      context,
      existingContent: auditNote.value,
      section: 'K2-4-contract-cost-note',
    })
    const generated = res?.data?.data?.content || res?.data?.content || ''
    if (generated) { auditNote.value = generated; persistNote(); ElMessage.success('AI内容已填入') }
    else ElMessage.warning('AI未生成内容')
  } catch { ElMessage.warning('AI生成失败') }
}

async function handleAiConclusion(): Promise<void> {
  try {
    const context: Record<string, string> = {
      accountCode: '1231',
      sheet: 'K2-4',
      capitalizedCount: String(rows.value.filter(r => r.isCapitalized).length),
      nonCapitalizedCount: String(nonCapitalizedRows.value.length),
      endBalanceTotal: String(subtotals.value.endBalance),
    }
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      prompt: '请生成合同取得成本明细表审计结论',
      context,
      existingContent: auditConclusion.value,
      section: 'K2-4-contract-cost-conclusion',
    })
    const generated = res?.data?.data?.content || res?.data?.content || ''
    if (generated) { auditConclusion.value = generated; persistConclusion(); ElMessage.success('AI内容已填入') }
    else ElMessage.warning('AI未生成内容')
  } catch { ElMessage.warning('AI生成失败') }
}

function handleReview(): void { openReviewDialog('K2-4-conclusion') }

/** 已资本化且有摊销参数的行（可推送K2-5） */
const capitalizedWithAmortRows = computed(() =>
  rows.value.filter(r => r.isCapitalized && r.amortMethod && r.amortPeriod > 0),
)

/** 推送已资本化合同至K2-5（持久化到allResponses供K2-5"从K2-4带入"读取） */
function handlePushToK25(): void {
  const data = capitalizedWithAmortRows.value.map(r => ({
    contractNo: r.contractNo,
    beginBalance: r.beginBalance,
    periodIncrease: r.periodIncrease,
    amortMethod: r.amortMethod,
    amortPeriod: r.amortPeriod,
    isCapitalized: true,
  }))
  // 持久化到K2-4-contract-cost-rows供K2-5的handleImportFromK24读取
  emit('save', 'K2-4-contract-cost-rows', { remark: JSON.stringify(data) })
  ElMessage.success(`已推送 ${data.length} 笔已资本化合同数据，切换到K2-5可一键带入`)
}
</script>

<style scoped>
.k2-tab-contract-cost {
  padding: 12px 16px;
  font-size: var(--wp-font-size, 13px);
}

/* ═══ 方法论上下文（琥珀色左边线+浅黄背景）═══ */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  margin-bottom: 14px;
  border-radius: 4px;
  font-size: 12.5px;
  color: #5a4b35;
  line-height: 1.6;
}

/* ═══ 标题栏 ═══ */
.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.sheet-title {
  font-size: 15px;
  font-weight: 600;
  margin: 0;
  color: #303133;
}

.head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.cross-badge {
  cursor: pointer;
}

/* ═══ CAS14 资本化判断面板（蓝色引导区）═══ */
.cas14-panel {
  background: linear-gradient(135deg, #ecf5ff 0%, #f0f9ff 100%);
  border: 1px solid #b3d8ff;
  border-radius: 8px;
  padding: 14px 18px;
  margin-bottom: 14px;
}

.cas14-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.cas14-title {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
  color: #409eff;
}

.cas14-conditions {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
}

.condition-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.condition-label {
  font-size: 12.5px;
  color: #606266;
  white-space: nowrap;
}

/* ═══ 区段栏 ═══ */
.segment-bar {
  margin-bottom: 12px;
}

/* ═══ 表格 ═══ */
.contract-cost-table {
  font-size: var(--wp-font-size, 13px);
  margin-bottom: 12px;
}

.contract-cost-table :deep(.el-table__row) {
  font-size: var(--wp-font-size, 13px);
}

.amount-input {
  width: 100%;
}

.amount-input :deep(.el-input__inner) {
  text-align: right;
}

.amount-cell {
  font-variant-numeric: tabular-nums;
}

/* 公式列样式：虚线下划线 + cursor:help */
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  font-variant-numeric: tabular-nums;
  color: #303133;
}

/* ═══ 底部合计栏 ═══ */
.subtotals-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding: 10px 0;
  border-top: 1px solid #ebeef5;
  align-items: center;
}

/* ═══ 编制提示 ═══ */
.compile-hint {
  margin: 12px 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.compile-hint summary {
  cursor: pointer;
  font-weight: 500;
}
.compile-hint ul {
  padding-left: 18px;
  margin-top: 8px;
  line-height: 1.8;
}

/* ═══ section-title-row ═══ */
.section-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.card-title {
  font-weight: 600;
}

/* ═══ 成本率异常高亮 ═══ */
.rate-warn {
  color: #f56c6c;
  font-weight: 600;
}
</style>
