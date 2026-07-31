<template>
  <div class="k2-tab-amortization">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>
        <b>CAS14合同取得成本摊销测算：</b>
        直线法 = 取得成本 ÷ 摊销期总月数 × 本期月数；进度法 = 取得成本 × (本期履约进度 - 上期履约进度)。
        逐合同独立计算测算摊销额，与企业账面核对差异，超过重要性水平的差异标红提示调整。
      </p>
    </div>

    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>计价和分摊：</b>合同取得成本的摊销方法（直线法/进度法）与摊销期恰当，本期摊销额计算准确；</li>
        <li><b>完整性：</b>所有应摊销的合同取得成本均已按期摊销，摊销后余额与账面核对一致。</li>
      </ol>
    </el-alert>

    <!-- 区段Tab -->
    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>K2-5 摊销测算表</span>
          <div class="title-actions">
            <!-- Cross-validation badge -->
            <el-tag
              v-if="crossValidation"
              :type="crossValidation.isMatch ? 'success' : 'danger'"
              size="small"
              effect="plain"
              class="cross-badge"
            >
              K2-4↔K2-5 {{ crossValidation.isMatch ? '✓一致' : `差异${fmtAmt(crossValidation.diff)}` }}
            </el-tag>

            <!-- 重要性水平 -->
            <el-input-number
              v-model="materiality"
              :controls="false"
              :min="0"
              :precision="2"
              size="small"
              :disabled="isReadonly"
              placeholder="重要性水平"
              class="materiality-input"
              @change="handleMaterialityChange"
            />
            <span class="materiality-label">重要性水平</span>

            <!-- 导入导出 -->
            <el-dropdown trigger="click" :disabled="isReadonly" @command="handleImportExport">
              <el-button size="small">
                导入导出 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
                  <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
                  <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
      </template>

      <!-- el-segmented 区段切换 -->
      <div class="segment-bar">
        <el-segmented
          v-model="activeSection"
          :options="sectionOptions"
          size="default"
          @change="handleSectionChange"
        />
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          @click="handleAddRow"
        >+ 新增行</el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="warning"
          plain
          @click="handleImportFromK24"
        >从K2-4带入</el-button>
      </div>

      <!-- 表格 -->
      <el-table
        :data="rows"
        border
        stripe
        size="small"
        max-height="520"
        class="amort-table"
        :row-class-name="getRowClassName"
      >
        <el-table-column type="index" label="#" width="40" fixed />

        <!-- 基础区段列 -->
        <template v-if="activeSection === 0">
          <el-table-column prop="contractNo" label="合同编号" width="130" show-overflow-tooltip>
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                v-model="row.contractNo"
                size="small"
                class="cell-input"
                @change="handleCellChange(row.rowId, 'contractNo', $event)"
              />
              <span v-else>{{ row.contractNo }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="cost" label="取得成本" width="130" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                v-model="row.cost"
                :controls="false"
                size="small"
                :min="0"
                :precision="2"
                class="cell-input"
                @change="handleCellChange(row.rowId, 'cost', $event)"
              />
              <span v-else class="amount-cell">{{ fmtAmt(row.cost) }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="method" label="摊销方法" width="120" align="center">
            <template #default="{ row }">
              <el-segmented
                v-if="!isReadonly"
                :model-value="row.method"
                :options="methodOptions"
                size="small"
                class="method-segmented"
                @change="handleMethodSwitch(row.rowId, $event as string)"
              />
              <span v-else>{{ row.method }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="totalPeriods" label="摊销期(月)" width="100" align="center">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                v-model="row.totalPeriods"
                :controls="false"
                size="small"
                :min="0"
                :max="600"
                class="cell-input"
                @change="handleCellChange(row.rowId, 'totalPeriods', $event)"
              />
              <span v-else>{{ row.totalPeriods }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="currentPeriods" label="本期期数(月)" width="110" align="center">
            <template #header>
              <el-tooltip content="直线法使用：本期计提摊销的月数" placement="top">
                <span class="formula-header">本期期数(月)</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                v-model="row.currentPeriods"
                :controls="false"
                size="small"
                :min="0"
                :max="600"
                class="cell-input"
                @change="handleCellChange(row.rowId, 'currentPeriods', $event)"
              />
              <span v-else>{{ row.currentPeriods }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="startDate" label="起始日" width="130">
            <template #default="{ row }">
              <el-date-picker
                v-if="!isReadonly"
                v-model="row.startDate"
                type="date"
                size="small"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                class="cell-input"
                @change="handleCellChange(row.rowId, 'startDate', $event)"
              />
              <span v-else>{{ row.startDate }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="currentProgress" label="本期进度" width="100" align="center">
            <template #header>
              <el-tooltip content="进度法使用：本期累计履约进度(0~100%)" placement="top">
                <span class="formula-header">本期进度</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                v-model="row.currentProgress"
                :controls="false"
                size="small"
                :min="0"
                :max="1"
                :step="0.01"
                :precision="4"
                class="cell-input"
                @change="handleCellChange(row.rowId, 'currentProgress', $event)"
              />
              <span v-else class="percent-cell">{{ fmtPercent(row.currentProgress) }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="priorProgress" label="上期进度" width="100" align="center">
            <template #header>
              <el-tooltip content="进度法使用：上期累计履约进度(0~100%)" placement="top">
                <span class="formula-header">上期进度</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                v-model="row.priorProgress"
                :controls="false"
                size="small"
                :min="0"
                :max="1"
                :step="0.01"
                :precision="4"
                class="cell-input"
                @change="handleCellChange(row.rowId, 'priorProgress', $event)"
              />
              <span v-else class="percent-cell">{{ fmtPercent(row.priorProgress) }}</span>
            </template>
          </el-table-column>
        </template>

        <!-- 测算区段列 -->
        <template v-if="activeSection === 1">
          <el-table-column prop="contractNo" label="合同编号" width="130" fixed show-overflow-tooltip>
            <template #default="{ row }">
              <span>{{ row.contractNo }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="calculatedAmort" label="本期应摊销" width="140" align="right">
            <template #header>
              <el-tooltip content="直线:cost/总期×本期期数; 进度:cost×(本期进度-上期进度)" placement="top">
                <span class="formula-header">本期应摊销</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span class="formula-cell">{{ fmtAmt(row.calculatedAmort) }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="accumulatedAmort" label="累计摊销" width="130" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                v-model="row.accumulatedAmort"
                :controls="false"
                size="small"
                :min="0"
                :precision="2"
                class="cell-input"
                @change="handleCellChange(row.rowId, 'accumulatedAmort', $event)"
              />
              <span v-else class="amount-cell">{{ fmtAmt(row.accumulatedAmort) }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="amortizedBalance" label="摊余成本" width="140" align="right">
            <template #header>
              <el-tooltip content="取得成本 - 累计摊销" placement="top">
                <span class="formula-header">摊余成本</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span class="formula-cell">{{ fmtAmt(row.amortizedBalance) }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="bookedAmort" label="企业摊销" width="130" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                v-model="row.bookedAmort"
                :controls="false"
                size="small"
                :precision="2"
                class="cell-input"
                @change="handleCellChange(row.rowId, 'bookedAmort', $event)"
              />
              <span v-else class="amount-cell">{{ fmtAmt(row.bookedAmort) }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="variance" label="差异" width="120" align="right">
            <template #header>
              <el-tooltip content="测算摊销 - 企业摊销" placement="top">
                <span class="formula-header">差异</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span
                :class="['formula-cell', { 'variance-danger': isVarianceExceeded(row.rowId) }]"
              >{{ fmtAmt(row.variance) }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="conclusion" label="结论" width="130">
            <template #default="{ row }">
              <el-select
                v-if="!isReadonly"
                v-model="row.conclusion"
                size="small"
                clearable
                placeholder="请选择"
                class="cell-input"
                @change="handleCellChange(row.rowId, 'conclusion', $event)"
              >
                <el-option
                  v-for="opt in conclusionOptions"
                  :key="opt"
                  :label="opt"
                  :value="opt"
                />
              </el-select>
              <el-tag
                v-else-if="row.conclusion"
                :type="getConclTagType(row.conclusion)"
                size="small"
              >{{ row.conclusion }}</el-tag>
            </template>
          </el-table-column>

          <el-table-column prop="remark" label="备注" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                v-model="row.remark"
                size="small"
                class="cell-input"
                @change="handleCellChange(row.rowId, 'remark', $event)"
              />
              <span v-else>{{ row.remark }}</span>
            </template>
          </el-table-column>
        </template>

        <!-- 操作列 -->
        <el-table-column v-if="!isReadonly" label="操作" width="60" fixed="right" align="center">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="handleRemoveRow(row.rowId)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 底部合计行 -->
      <div class="subtotal-bar">
        <span class="subtotal-label">合计（{{ subtotals.count }} 行）：</span>
        <span class="subtotal-item">取得成本 <b>{{ fmtAmt(subtotals.cost) }}</b></span>
        <span class="subtotal-item">测算摊销 <b>{{ fmtAmt(subtotals.calculatedAmort) }}</b></span>
        <span class="subtotal-item">累计摊销 <b>{{ fmtAmt(subtotals.accumulatedAmort) }}</b></span>
        <span class="subtotal-item">摊余成本 <b>{{ fmtAmt(subtotals.amortizedBalance) }}</b></span>
        <span class="subtotal-item">企业摊销 <b>{{ fmtAmt(subtotals.bookedAmort) }}</b></span>
        <span class="subtotal-item" :class="{ 'variance-danger-text': Math.abs(subtotals.variance) > materiality && materiality > 0 }">
          差异合计 <b>{{ fmtAmt(subtotals.variance) }}</b>
        </span>
      </div>
    </el-card>

    <!-- 到期/已摊完预警 -->
    <el-alert v-if="expiredContracts.length > 0" type="warning" :closable="false" style="margin-bottom:12px">
      <template #title>⚠️ {{ expiredContracts.length }} 个合同已摊销完毕（摊余成本≤0）</template>
      <div style="font-size:12px;margin-top:4px">
        {{ expiredContracts.map(r => r.contractNo || '(未命名)').join('、') }}
        —— 请确认是否应转出其他流动资产
      </div>
    </el-alert>

    <!-- 差异超重要性 → 建议AJE -->
    <el-card v-if="varianceExceedRows.size > 0 && !isReadonly" shadow="never" class="suggest-aje-card">
      <template #header>
        <div class="section-title">
          <span>建议调整分录（{{ varianceExceedRows.size }} 笔差异超重要性水平）</span>
          <el-button size="small" type="primary" @click="handlePushSuggestedAJE">一键推送至K2-3</el-button>
        </div>
      </template>
      <el-table :data="suggestedAjeRows" border size="small" style="font-size:13px">
        <el-table-column label="合同" prop="contractNo" width="130" />
        <el-table-column label="差异方向" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.variance > 0 ? 'danger' : 'warning'" size="small">{{ row.variance > 0 ? '少摊' : '多摊' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="差异金额" width="130" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(Math.abs(row.variance)) }}</span></template>
        </el-table-column>
        <el-table-column label="建议分录" min-width="200">
          <template #default="{ row }">
            <span v-if="row.variance > 0">借：销售费用/管理费用 {{ fmtAmt(row.variance) }}　贷：其他流动资产 {{ fmtAmt(row.variance) }}</span>
            <span v-else>借：其他流动资产 {{ fmtAmt(Math.abs(row.variance)) }}　贷：销售费用/管理费用 {{ fmtAmt(Math.abs(row.variance)) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" style="margin-bottom:12px">
      <template #header>
        <div class="section-title">
          <span>审计说明</span>
          <div class="title-actions">
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
        placeholder="概述摊销测算过程与结果：方法选择依据、差异原因分析、是否需要调整..."
        @blur="persistNote"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" style="margin-bottom:12px">
      <template #header>
        <div class="section-title">
          <span>审计结论</span>
          <div class="title-actions">
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
        placeholder="基于上述摊销测算，形成审计结论..."
        @blur="persistConclusion"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示（CAS14 / CAS15）</summary>
      <ul>
        <li>直线法：cost ÷ 摊销期总月数 × 本期月数（适用于均匀受益的合同取得成本）</li>
        <li>进度法：cost × (本期累计履约进度 - 上期累计履约进度)（适用于产出法/投入法确定进度的合同）</li>
        <li>差异 = 测算应摊销 - 企业账面摊销，正值=企业少摊（需补提），负值=企业多摊（需冲回）</li>
        <li>差异超过重要性水平 → 红色高亮 + 建议AJE，可一键推送至K2-3调整分录</li>
        <li>摊余成本≤0表示已摊销完毕，应关注是否仍有对应合同义务或应转出</li>
        <li>摊销方法变更视为会计估计变更，应有充分依据并披露</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K2TabAmortization.vue — K2-5 摊销测算表
 *
 * 28列 × 最多66行，37公式列，2区段Tab切换(基础/测算)。
 * 直线法/进度法 per-row el-segmented 切换。
 * 差异>重要性水平 → 红色高亮。
 * 66行使用 el-table max-height 原生滚动。
 *
 * Spec: .kiro/specs/k2-other-current-assets/
 * Task: 4.5
 * Requirements: 5.1-5.7
 */
import { ref, computed, toRef, watch, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import { fmtAmount } from '@/utils/formatters'
import http from '@/utils/http'
import { K2_GROSS_FALLBACK_STANDARD } from '../../composables/k2AccountScope'
import { eventBus } from '@/utils/eventBus'
import {
  useK2Amortization,
  K2_AMORT_SECTION_LABELS,
  type K2AmortMethod,
  type K2AmortSection,
} from '../../composables/useK2Amortization'
import { useK2CrossSheet } from '../../composables/useK2CrossSheet'
import { useK2ImportExport } from '../../composables/useK2ImportExport'

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

// ─── Composable Integration ──────────────────────────────────────────────────

const allResponsesRef = toRef(props, 'allResponses')

const {
  rows,
  activeSection,
  materiality,
  subtotals,
  varianceExceedRows,
  switchSection,
  switchMethod,
  updateCell,
  recalcAll,
  addRow,
  removeRow,
  importRows,
  exportRows,
} = useK2Amortization(allResponsesRef, {
  onSave: (itemId, value) => emit('save', itemId, value),
})

const { contractCostVsAmort } = useK2CrossSheet(allResponsesRef)

const wpIdRef = toRef(props, 'wpId')
const { exportTemplate, exportData, importData } = useK2ImportExport({ wpId: wpIdRef })

// ─── Section Options ─────────────────────────────────────────────────────────

const sectionOptions = K2_AMORT_SECTION_LABELS.map((label, idx) => ({
  label,
  value: idx,
}))

const methodOptions = ['直线法', '进度法']
const conclusionOptions = ['正常', '差异不重大', '差异重大-需调整', '待确认']

// ─── Cross-validation badge ──────────────────────────────────────────────────

const crossValidation = computed(() => contractCostVsAmort.value)

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleSectionChange(val: number | string): void {
  switchSection(val as K2AmortSection)
}

function handleCellChange(rowId: string, field: string, value: any): void {
  updateCell(rowId, field, value)
}

function handleMethodSwitch(rowId: string, method: string): void {
  switchMethod(rowId, method as K2AmortMethod)
}

function handleMaterialityChange(val: number | undefined): void {
  emit('save', 'K2-5-materiality', String(val ?? 0))
}

async function handleAddRow(): Promise<void> {
  const { value: contractNo } = await ElMessageBox.prompt(
    '请输入合同编号',
    '新增摊销行',
    { confirmButtonText: '确认', cancelButtonText: '取消', inputPlaceholder: '合同编号（如C-001）' },
  ).catch(() => ({ value: '' }))
  if (contractNo === undefined) return
  addRow(contractNo || `C-${String(rows.value.length + 1).padStart(3, '0')}`)
  recalcAll()
}

/** 从K2-4合同取得成本明细带入（自动填入合同编号、取得成本、摊销方法、摊销期） */
function handleImportFromK24(): void {
  const k24Data = props.allResponses.get('K2-4-contract-cost-rows')
  if (!k24Data?.remark) {
    ElMessage.warning('K2-4合同取得成本明细暂无数据，请先编制K2-4')
    return
  }
  try {
    const parsed = JSON.parse(k24Data.remark)
    const contractRows = (Array.isArray(parsed) ? parsed : [])
      .filter((r: any) => r.contractNo && r.isCapitalized)
    if (contractRows.length === 0) {
      ElMessage.info('K2-4中未找到已资本化的合同（仅带入isCapitalized=true的行）')
      return
    }
    let importedCount = 0
    for (const item of contractRows) {
      const existing = rows.value.find((r) => r.contractNo === item.contractNo)
      if (!existing) {
        addRow(item.contractNo)
        const newRow = rows.value[rows.value.length - 1]
        if (newRow) {
          updateCell(newRow.rowId, 'cost', Number(item.beginBalance ?? 0) + Number(item.periodIncrease ?? 0))
          if (item.amortMethod) updateCell(newRow.rowId, 'method', item.amortMethod)
          if (item.amortPeriod) updateCell(newRow.rowId, 'totalPeriods', Number(item.amortPeriod))
        }
        importedCount++
      }
    }
    recalcAll()
    if (importedCount > 0) {
      ElMessage.success(`已从K2-4带入 ${importedCount} 个合同`)
    } else {
      ElMessage.info('所有合同已存在，无需带入')
    }
  } catch {
    ElMessage.warning('解析K2-4数据失败')
  }
}

function handleRemoveRow(rowId: string): void {
  removeRow(rowId)
}

async function handleImportExport(command: string): Promise<void> {
  try {
    if (command === 'export-template') {
      await exportTemplate('K2-5')
    } else if (command === 'export-data') {
      await exportData('K2-5')
    } else if (command === 'import-data') {
      // 创建隐藏文件输入
      const input = document.createElement('input')
      input.type = 'file'
      input.accept = '.xlsx,.xls'
      input.onchange = async () => {
        const file = input.files?.[0]
        if (!file) return
        try {
          const result = await importData('K2-5', file)
          if (result && result.rowCount > 0) {
            ElMessage.success(`成功导入 ${result.rowCount} 行`)
          }
        } catch (err: any) {
          ElMessage.error(err?.message || '导入失败')
        }
      }
      input.click()
    }
  } catch (err: any) {
    ElMessage.error(err?.message || '导入导出失败')
  }
}

// ─── Audit Note / Conclusion / Expired / Suggested AJE ───────────────────────

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const auditNote = ref('')
const auditConclusion = ref('')

// 加载审计说明/结论
watch(allResponsesRef, () => {
  const noteItem = props.allResponses.get('K2-5-audit-note')
  auditNote.value = noteItem?.remark ?? ''
  const conclItem = props.allResponses.get('K2-5-audit-conclusion')
  auditConclusion.value = conclItem?.remark ?? ''
}, { immediate: true })

function persistNote(): void {
  emit('save', 'K2-5-audit-note', { remark: auditNote.value })
}
function persistConclusion(): void {
  emit('save', 'K2-5-audit-conclusion', { remark: auditConclusion.value })
}

/** 已摊销完毕（摊余成本≤0）的合同 */
const expiredContracts = computed(() =>
  rows.value.filter(r => r.cost > 0 && r.amortizedBalance <= 0),
)

/** 建议AJE行（差异超重要性） */
const suggestedAjeRows = computed(() =>
  rows.value.filter(r => varianceExceedRows.value.has(r.rowId)),
)

/** 一键推送建议AJE至K2-3 */
function handlePushSuggestedAJE(): void {
  const ajeItems = suggestedAjeRows.value.map(r => ({
    contractNo: r.contractNo,
    variance: r.variance,
    direction: r.variance > 0 ? '少摊-补提' : '多摊-冲回',
  }))
  // 通过 eventBus 发布建议，K2-3可订阅消费
  try {
    eventBus.emit('adjustment:created', {
      wpCode: 'K2',
      accountCode: K2_GROSS_FALLBACK_STANDARD,
      source: 'K2-5-amort-variance',
      suggestedEntries: ajeItems,
      totalVariance: subtotals.value.variance,
    })
    ElMessage.success(`已推送 ${ajeItems.length} 笔建议AJE至K2-3`)
  } catch {
    ElMessage.warning('推送失败')
  }
}

/** AI生成审计说明 */
async function handleAiNote(): Promise<void> {
  try {
    const context: Record<string, string> = {
      accountCode: K2_GROSS_FALLBACK_STANDARD,
      sheet: 'K2-5',
      rowCount: String(rows.value.length),
      totalCost: String(subtotals.value.cost),
      totalCalculated: String(subtotals.value.calculatedAmort),
      totalBooked: String(subtotals.value.bookedAmort),
      totalVariance: String(subtotals.value.variance),
      materiality: String(materiality.value),
      exceedCount: String(varianceExceedRows.value.size),
      expiredCount: String(expiredContracts.value.length),
    }
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      prompt: '请生成合同取得成本摊销测算审计说明，概述摊销方法选择依据、测算结果与企业差异分析、是否需要调整',
      context,
      existingContent: auditNote.value,
      section: 'K2-5-amort-note',
    })
    const generated = res?.data?.data?.content || res?.data?.content || ''
    if (generated) { auditNote.value = generated; persistNote(); ElMessage.success('AI内容已填入') }
    else ElMessage.warning('AI未生成内容')
  } catch { ElMessage.warning('AI生成失败') }
}

/** AI生成审计结论 */
async function handleAiConclusion(): Promise<void> {
  try {
    const context: Record<string, string> = {
      accountCode: K2_GROSS_FALLBACK_STANDARD,
      sheet: 'K2-5',
      totalVariance: String(subtotals.value.variance),
      materiality: String(materiality.value),
      exceedCount: String(varianceExceedRows.value.size),
    }
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      prompt: '请生成合同取得成本摊销测算的审计结论',
      context,
      existingContent: auditConclusion.value,
      section: 'K2-5-amort-conclusion',
    })
    const generated = res?.data?.data?.content || res?.data?.content || ''
    if (generated) { auditConclusion.value = generated; persistConclusion(); ElMessage.success('AI内容已填入') }
    else ElMessage.warning('AI未生成内容')
  } catch { ElMessage.warning('AI生成失败') }
}

function handleReview(): void { openReviewDialog('K2-5-conclusion') }

// ─── Variance Check ──────────────────────────────────────────────────────────

function isVarianceExceeded(rowId: string): boolean {
  return varianceExceedRows.value.has(rowId)
}

function getRowClassName({ row }: { row: any }): string {
  if (isVarianceExceeded(row.rowId)) return 'row-variance-exceed'
  return ''
}

function getConclTagType(conclusion: string): 'success' | 'warning' | 'danger' | 'info' {
  if (conclusion === '正常') return 'success'
  if (conclusion === '差异不重大') return 'warning'
  if (conclusion === '差异重大-需调整') return 'danger'
  return 'info'
}

// ─── Format Helpers ──────────────────────────────────────────────────────────

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return fmtAmount(val)
}

function fmtPercent(val: number | null | undefined): string {
  if (val == null) return '-'
  return `${(val * 100).toFixed(2)}%`
}

// ─── Recalc on mount (ensure formula columns are computed) ───────────────────

watch(() => rows.value.length, () => {
  recalcAll()
}, { immediate: true })
</script>

<style scoped>
.k2-tab-amortization {
  padding: 12px 0;
}

.methodology-context {
  border-left: 3px solid #e6a23c;
  background: #fef9e7;
  padding: 8px 12px;
  margin-bottom: 12px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}

.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 14px;
  font-weight: 600;
}

.title-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.cross-badge {
  font-size: 11px;
}

.materiality-input {
  width: 110px;
}

.materiality-label {
  font-size: 12px;
  color: #909399;
  white-space: nowrap;
}

.segment-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.amort-table {
  font-size: var(--wp-font-size, 13px);
}

.amort-table :deep(.cell-input) {
  width: 100%;
}

.amort-table :deep(.cell-input .el-input__inner),
.amort-table :deep(.cell-input .el-input-number__decrease),
.amort-table :deep(.cell-input .el-input-number__increase) {
  font-size: var(--wp-font-size, 13px);
}

.method-segmented {
  --el-segmented-item-selected-bg-color: var(--el-color-primary-light-3);
}

.formula-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
}

.formula-cell {
  border-bottom: 1px dashed #c0c4cc;
  cursor: help;
  padding-bottom: 1px;
}

.amount-cell {
  font-variant-numeric: tabular-nums;
}

.percent-cell {
  color: #409eff;
}

.variance-danger {
  color: #f56c6c;
  font-weight: 600;
  background: rgba(245, 108, 108, 0.08);
  padding: 2px 4px;
  border-radius: 2px;
}

.variance-danger-text {
  color: #f56c6c;
  font-weight: 600;
}

/* 差异超过重要性的行高亮 */
.amort-table :deep(.row-variance-exceed) {
  background-color: rgba(245, 108, 108, 0.06) !important;
}

.amort-table :deep(.row-variance-exceed:hover > td) {
  background-color: rgba(245, 108, 108, 0.12) !important;
}

.subtotal-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  padding: 10px 12px;
  margin-top: 8px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
}

.subtotal-label {
  color: #606266;
  font-weight: 500;
}

.subtotal-item {
  color: #303133;
}

.subtotal-item b {
  font-variant-numeric: tabular-nums;
  margin-left: 4px;
}
</style>
