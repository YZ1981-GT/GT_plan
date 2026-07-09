<template>
  <div class="l3-tab-detail">
    <!-- ═══ 返回目录 + 标题 + 操作栏 ═══ -->
    <div class="l3-detail-header">
      <div class="l3-detail-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">
          ← 返回目录
        </el-button>
        <h3 class="l3-detail-title">L3-2 长期借款明细表</h3>
      </div>
      <div class="l3-detail-header-right">
        <!-- 导入导出 -->
        <el-dropdown trigger="click" :disabled="isReadonly" @command="handleImportExport">
          <el-button size="small" :disabled="isReadonly || isExporting || isImporting">
            导入导出 ▾
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item command="exportData">导出数据</el-dropdown-item>
              <el-dropdown-item command="importData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <!-- AI辅助 -->
        <el-button size="small" @click="$emit('ai-assist', 'L3-2')">AI</el-button>
        <!-- 复核 -->
        <el-button size="small" @click="$emit('open-review', 'L3-2')">复核</el-button>
        <!-- 新增行 -->
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          @click="handleAddRow"
        >
          + 新增借款
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色：负债类方向说明） ═══ -->
    <div class="l3-methodology-context">
      <div class="l3-methodology-text">
        <strong>负债类贷方科目：</strong>
        期末余额 = 期初 + 本期借入（贷方） − 本期归还（借方）。
        明细合计应与审定表L3-1一致。32列按4区段切换，行数据全程同步。
        一年内到期金额自动判定（报告日起1年内到期部分重分类至流动负债）。
      </div>
    </div>

    <!-- ═══ 区段Tab切换（4区段：基础/金额/到期/担保） ═══ -->
    <div class="l3-segment-bar">
      <el-radio-group
        :model-value="activeSegment"
        size="small"
        @change="switchSegment"
      >
        <el-radio-button
          v-for="seg in L3_DETAIL_SEGMENTS"
          :key="seg.key"
          :value="seg.key"
        >
          {{ seg.label }}（{{ seg.fields.length }}列）
        </el-radio-button>
      </el-radio-group>

      <!-- 筛选区 -->
      <div class="l3-filter-area">
        <el-select
          v-model="filterBank"
          placeholder="筛选银行"
          clearable
          size="small"
          style="width: 130px"
          @change="handleFilterChange"
        >
          <el-option v-for="b in bankOptions" :key="b" :label="b" :value="b" />
        </el-select>
        <el-select
          v-model="filterType"
          placeholder="筛选类型"
          clearable
          size="small"
          style="width: 110px"
          @change="handleFilterChange"
        >
          <el-option v-for="t in loanTypeOptions" :key="t" :label="t" :value="t" />
        </el-select>
      </div>
    </div>

    <!-- ═══ 明细表主体（区段按 segment 显示列） ═══ -->
    <el-table
      :data="displayRows"
      border
      size="small"
      style="width: 100%"
      :row-class-name="getRowClassName"
      max-height="520"
    >
      <!-- 序号固定列 -->
      <el-table-column type="index" label="#" width="45" fixed />

      <!-- ═══ 区段1：基础信息（8列） ═══ -->
      <template v-if="activeSegment === 'basic'">
        <el-table-column prop="bank" label="借款银行" min-width="120">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly && !row._isTotal"
              :model-value="row.bank"
              size="small"
              @change="(val: string) => handleCellUpdate($index, 'bank', val)"
            />
            <span v-else class="l3-cell-text">{{ row.bank }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="contractNo" label="合同号" min-width="130">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly && !row._isTotal"
              :model-value="row.contractNo"
              size="small"
              @change="(val: string) => handleCellUpdate($index, 'contractNo', val)"
            />
            <span v-else>{{ row.contractNo }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="loanType" label="借款类型" min-width="100">
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly && !row._isTotal"
              :model-value="row.loanType"
              size="small"
              placeholder="选择"
              @change="(val: string) => handleCellUpdate($index, 'loanType', val)"
            >
              <el-option label="信用" value="信用" />
              <el-option label="保证" value="保证" />
              <el-option label="抵押" value="抵押" />
              <el-option label="质押" value="质押" />
            </el-select>
            <span v-else>{{ row.loanType }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="startDate" label="起始日" min-width="120">
          <template #default="{ row, $index }">
            <el-date-picker
              v-if="!isReadonly && !row._isTotal"
              :model-value="row.startDate"
              type="date"
              format="YYYY-MM-DD"
              value-format="YYYY-MM-DD"
              size="small"
              style="width: 100%"
              @change="(val: string) => handleCellUpdate($index, 'startDate', val || '')"
            />
            <span v-else>{{ row.startDate }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="dueDate" label="到期日" min-width="120">
          <template #default="{ row, $index }">
            <el-date-picker
              v-if="!isReadonly && !row._isTotal"
              :model-value="row.dueDate"
              type="date"
              format="YYYY-MM-DD"
              value-format="YYYY-MM-DD"
              size="small"
              style="width: 100%"
              @change="(val: string) => handleCellUpdate($index, 'dueDate', val || '')"
            />
            <span v-else>{{ row.dueDate }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="annualRate" label="年利率(%)" min-width="100" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly && !row._isTotal"
              :model-value="row.annualRate"
              :controls="false"
              :precision="4"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => handleCellUpdate($index, 'annualRate', val ?? 0)"
            />
            <span v-else>{{ row.annualRate ? (row.annualRate * 100).toFixed(2) + '%' : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="purpose" label="用途" min-width="120">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly && !row._isTotal"
              :model-value="row.purpose"
              size="small"
              @change="(val: string) => handleCellUpdate($index, 'purpose', val)"
            />
            <span v-else>{{ row.purpose || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="currency" label="币种" min-width="80">
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly && !row._isTotal"
              :model-value="row.currency"
              size="small"
              @change="(val: string) => handleCellUpdate($index, 'currency', val)"
            >
              <el-option label="CNY" value="CNY" />
              <el-option label="USD" value="USD" />
              <el-option label="EUR" value="EUR" />
              <el-option label="HKD" value="HKD" />
            </el-select>
            <span v-else>{{ row.currency }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 区段2：金额变动（4列，含公式列期末） ═══ -->
      <template v-if="activeSegment === 'movement'">
        <el-table-column prop="beginning" label="期初余额" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly && !row._isTotal"
              :model-value="row.beginning"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => handleCellUpdate($index, 'beginning', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.beginning) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="borrowed" label="本期借入(贷方)" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly && !row._isTotal"
              :model-value="row.borrowed"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => handleCellUpdate($index, 'borrowed', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.borrowed) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="repaid" label="本期归还(借方)" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly && !row._isTotal"
              :model-value="row.repaid"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => handleCellUpdate($index, 'repaid', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.repaid) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="140" align="right">
          <template #header>
            <el-tooltip content="期末 = 期初 + 本期借入(贷方) − 本期归还(借方)（负债类！）" placement="top">
              <span class="l3-formula-col-header">期末余额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip content="期末 = 期初 + 借入 − 归还" placement="top">
              <span class="l3-formula-cell">{{ fmtAmount(row.endBalance) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 区段3：到期分类（2列，含公式列一年内到期） ═══ -->
      <template v-if="activeSegment === 'maturity'">
        <el-table-column prop="dueDate" label="到期日" min-width="120">
          <template #default="{ row }">
            <span>{{ row.dueDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="一年内到期金额" min-width="150" align="right">
          <template #header>
            <el-tooltip content="报告日起一年内到期部分→重分类至流动负债" placement="top">
              <span class="l3-formula-col-header">一年内到期金额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip
              :content="row.currentPortion > 0 ? '到期日在报告日1年内，需重分类' : '到期日超过1年，无需重分类'"
              placement="top"
            >
              <span :class="['l3-formula-cell', { 'l3-maturity-highlight': row.currentPortion > 0 }]">
                {{ fmtAmount(row.currentPortion) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 区段4：担保信息（3列） ═══ -->
      <template v-if="activeSegment === 'guarantee'">
        <el-table-column prop="guaranteeType" label="担保方式" min-width="110">
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly && !row._isTotal"
              :model-value="row.guaranteeType"
              size="small"
              placeholder="选择"
              clearable
              @change="(val: string) => handleCellUpdate($index, 'guaranteeType', val)"
            >
              <el-option label="信用" value="信用" />
              <el-option label="保证" value="保证" />
              <el-option label="抵押" value="抵押" />
              <el-option label="质押" value="质押" />
              <el-option label="混合" value="混合" />
            </el-select>
            <span v-else>{{ row.guaranteeType || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="pledgeAsset" label="担保物/担保人" min-width="140">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly && !row._isTotal"
              :model-value="row.pledgeAsset"
              size="small"
              @change="(val: string) => handleCellUpdate($index, 'pledgeAsset', val)"
            />
            <span v-else>{{ row.pledgeAsset || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="pledgeValue" label="担保价值" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly && !row._isTotal"
              :model-value="row.pledgeValue"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => handleCellUpdate($index, 'pledgeValue', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.pledgeValue) }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- 操作列（非readonly时显示） -->
      <el-table-column
        v-if="!isReadonly"
        label="操作"
        width="60"
        fixed="right"
        align="center"
      >
        <template #default="{ $index, row }">
          <el-button
            v-if="!row._isTotal"
            type="danger"
            text
            size="small"
            @click="handleRemoveRow($index)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 合计行信息 + 勾稽校验 + 一年内到期 ═══ -->
    <div class="l3-detail-footer">
      <div class="l3-total-info">
        <span>合计期末余额：<strong>{{ fmtAmount(totalEndBalance) }}</strong></span>
        <span class="l3-total-sep">|</span>
        <span>一年内到期合计：<strong class="l3-maturity-total">{{ fmtAmount(totalCurrentPortion) }}</strong></span>
        <span class="l3-row-count">（共 {{ filteredRows.length }} 笔借款）</span>
      </div>
      <div class="l3-cross-check-row">
        <span class="l3-cross-check-label">与审定表L3-1交叉验证：</span>
        <span :class="crossCheckClass">
          <template v-if="crossCheckResult.isMatch">✓ 匹配</template>
          <template v-else>✗ 差额 {{ fmtAmount(crossCheckResult.diff) }}</template>
        </span>
      </div>
    </div>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l3-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>区段切换</strong>：32列按「基础信息/金额变动/到期分类/担保信息」4区段Tab切换，行数据全程同步</li>
        <li><strong>负债类公式</strong>：期末余额 = 期初 + 本期借入(贷方) − 本期归还(借方)，与资产类方向相反</li>
        <li><strong>一年内到期</strong>：系统自动判定报告日起一年内到期的借款金额，用于重分类RJE</li>
        <li><strong>动态行</strong>：点击"新增借款"输入银行名称后创建新行</li>
        <li><strong>导入导出</strong>：支持导出模板/导出数据/导入数据（xlsx格式）</li>
        <li><strong>勾稽</strong>：明细合计应与审定表L3-1期末合计一致；明细与L3-5利息测算按合同号对应</li>
      </ul>
    </details>

    <!-- 隐藏的文件上传input -->
    <input
      ref="fileInputRef"
      type="file"
      accept=".xlsx,.xls"
      style="display: none"
      @change="handleFileSelected"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * L3TabDetail — L3-2 长期借款明细表
 *
 * 32列宽表按4区段Tab切换（基础信息/金额变动/到期分类/担保信息），行同步。
 * - 区段1「基础信息」8列：银行/合同号/类型/起始日/到期日/利率/用途/币种
 * - 区段2「金额变动」4列：期初/借入(贷方)/归还(借方)/期末(公式列)
 * - 区段3「到期分类」2列：到期日/一年内到期金额(公式列)
 * - 区段4「担保信息」3列：担保方式/担保物/担保价值
 * - 动态行：ElMessageBox.prompt 输入银行名称后新增
 * - 导入导出：el-dropdown 三级（模板/数据/导入），useL3ImportExport sheet='L3-2'
 * - 公式列虚线+tooltip来源
 * - 方法论琥珀色
 * - AI+复核右对齐
 * - 13px font, l3- CSS prefix
 * - inject l3FormData, useL3Detail composable
 *
 * Spec: .kiro/specs/l3-long-term-loans/
 * Task: 4.3
 * Requirements: 3.1-3.6
 */
import { computed, inject, ref, type Ref } from 'vue'
import type { useL3FormData } from '@/components/workpaper/composables/useL3FormData'
import { useL3Detail, L3_DETAIL_SEGMENTS, type L3DetailRow } from '@/composables/useL3Detail'
import { useL3ImportExport } from '@/composables/useL3ImportExport'
import type { AdjudicationVsDetailResult } from '@/components/workpaper/composables/useL3CrossSheet'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

defineEmits<{
  (e: 'navigate', sheetName: string): void
  (e: 'ai-assist', section: string): void
  (e: 'open-review', section: string): void
}>()

// ─── Inject formData (由父组件 provide) ──────────────────────────────────────

const formData = inject<ReturnType<typeof useL3FormData>>('l3FormData')!

// ─── 明细行 reactive ref（从formData.allResponses中提取或独立管理） ─────────

const detailRows = ref<L3DetailRow[]>([])

// 从 checklist_responses 中还原行数据
function _loadRowsFromResponses(): void {
  const resp = formData.allResponses.value.get('L3-L3-2-rows')
  if (resp?.remark) {
    try {
      const parsed = JSON.parse(resp.remark)
      if (Array.isArray(parsed)) {
        detailRows.value = parsed
        return
      }
    } catch { /* ignore */ }
  }
  detailRows.value = []
}

// 初始加载
_loadRowsFromResponses()

// ─── 报告日（从 allResponses 或默认取年末） ──────────────────────────────────

const reportDate = computed(() => {
  const resp = formData.allResponses.value.get('L3-report-date')
  return resp?.remark || `${new Date().getFullYear()}-12-31`
})

// ─── Composable: 明细表业务逻辑 ─────────────────────────────────────────────

const {
  activeSegment,
  switchSegment,
  filteredRows,
  filterConfig,
  setFilter,
  computedRows,
  totalEndBalance,
  totalCurrentPortion,
  addRow,
  removeRow,
  updateRow,
} = useL3Detail(formData, detailRows, reportDate.value)

// ─── Composable: 导入导出 ────────────────────────────────────────────────────

const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)
const { exportTemplate, exportData, importData, isExporting, isImporting } =
  useL3ImportExport(wpIdRef, projectIdRef)

// ─── Inject 勾稽校验（审定表vs明细） ─────────────────────────────────────────

const adjudicationVsDetail = inject<Ref<AdjudicationVsDetailResult>>(
  'adjudicationVsDetail',
  computed(() => ({ diff: 0, isMatch: true })) as unknown as Ref<AdjudicationVsDetailResult>,
)

const crossCheckResult = computed<AdjudicationVsDetailResult>(() => adjudicationVsDetail.value)

const crossCheckClass = computed(() => ({
  'l3-cross-check-match': crossCheckResult.value.isMatch,
  'l3-cross-check-diff': !crossCheckResult.value.isMatch,
}))

// ─── 筛选状态 ────────────────────────────────────────────────────────────────

const filterBank = ref<string>('')
const filterType = ref<string>('')

/** 可选银行列表（从数据中提取） */
const bankOptions = computed(() => {
  const banks = new Set<string>()
  for (const row of detailRows.value) {
    if (row.bank) banks.add(row.bank)
  }
  return [...banks].sort()
})

/** 可选借款类型 */
const loanTypeOptions = computed(() => {
  const types = new Set<string>()
  for (const row of detailRows.value) {
    if (row.loanType) types.add(row.loanType)
  }
  return [...types].sort()
})

function handleFilterChange(): void {
  setFilter({
    bank: filterBank.value || undefined,
    loanType: filterType.value || undefined,
  })
}

// ─── 表格数据（含合计行） ────────────────────────────────────────────────────

interface DisplayRow extends L3DetailRow {
  _isTotal: boolean
}

const displayRows = computed<DisplayRow[]>(() => {
  const rows: DisplayRow[] = filteredRows.value.map(row => {
    // 从 computedRows 获取带有正确 endBalance + currentPortion 的行
    const computed = computedRows.value.find(
      cr => cr.bank === row.bank && cr.contractNo === row.contractNo,
    )
    return {
      ...row,
      endBalance: computed?.endBalance ?? row.endBalance,
      currentPortion: computed?.currentPortion ?? row.currentPortion,
      _isTotal: false,
    }
  })

  // 合计行
  rows.push({
    bank: '合  计',
    contractNo: '',
    loanType: '',
    startDate: '',
    dueDate: '',
    annualRate: 0,
    beginning: rows.reduce((s, r) => s + r.beginning, 0),
    borrowed: rows.reduce((s, r) => s + r.borrowed, 0),
    repaid: rows.reduce((s, r) => s + r.repaid, 0),
    endBalance: totalEndBalance.value,
    currentPortion: totalCurrentPortion.value,
    guaranteeType: '',
    pledgeAsset: '',
    pledgeValue: rows.reduce((s, r) => s + r.pledgeValue, 0),
    purpose: '',
    currency: '',
    remark: '',
    _isTotal: true,
  })

  return rows
})

// ─── 行样式 ──────────────────────────────────────────────────────────────────

function getRowClassName({ row }: { row: DisplayRow }): string {
  if (row._isTotal) return 'l3-total-row'
  return ''
}

// ─── 编辑处理 ────────────────────────────────────────────────────────────────

function handleCellUpdate(index: number, field: keyof L3DetailRow, value: string | number): void {
  // 排除合计行
  if (index >= filteredRows.value.length) return
  // 找到原始行索引
  const targetRow = filteredRows.value[index]
  const originalIndex = detailRows.value.indexOf(targetRow)
  if (originalIndex < 0) return
  updateRow(originalIndex, field, value)
}

// ─── 动态行操作 ──────────────────────────────────────────────────────────────

async function handleAddRow(): Promise<void> {
  await addRow()
}

function handleRemoveRow(index: number): void {
  if (index >= filteredRows.value.length) return
  const targetRow = filteredRows.value[index]
  const originalIndex = detailRows.value.indexOf(targetRow)
  if (originalIndex < 0) return
  removeRow(originalIndex)
}

// ─── 导入导出 ────────────────────────────────────────────────────────────────

const fileInputRef = ref<HTMLInputElement | null>(null)

function handleImportExport(command: string): void {
  switch (command) {
    case 'exportTemplate':
      exportTemplate('L3-2')
      break
    case 'exportData':
      exportData('L3-2')
      break
    case 'importData':
      fileInputRef.value?.click()
      break
  }
}

async function handleFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  const result = await importData(file, 'L3-2')
  if (result) {
    // 重新加载数据
    await formData.loadData()
    _loadRowsFromResponses()
  }
  // 清空文件选择，允许重复导入同一文件
  input.value = ''
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
.l3-tab-detail {
  padding: 12px;
  font-size: 13px;
}

/* ─── 头部 ─── */
.l3-detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.l3-detail-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.l3-detail-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.l3-detail-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

/* ─── 方法论上下文（琥珀色左边线+浅黄背景） ─── */
.l3-methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
  font-size: 13px;
  color: #5a4e3a;
  line-height: 1.6;
}

.l3-methodology-text strong {
  color: #b88230;
}

/* ─── 区段切换栏 ─── */
.l3-segment-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}

.l3-filter-area {
  display: flex;
  align-items: center;
  gap: 6px;
}

/* ─── 公式列表头（虚线下划线 + cursor:help） ─── */
.l3-formula-col-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 1px;
}

/* ─── 公式列单元格（虚线下划线 + cursor:help） ─── */
.l3-formula-cell {
  border-bottom: 1px dashed #c0c4cc;
  cursor: help;
  padding-bottom: 1px;
  display: inline-block;
}

/* ─── 一年内到期高亮（橙色） ─── */
.l3-maturity-highlight {
  color: #e6a23c;
  font-weight: 600;
  border-bottom-color: #e6a23c;
}

/* ─── 表格统一13px字体 ─── */
:deep(.el-table) {
  font-size: 13px;
}

:deep(.el-table th .cell) {
  font-size: 13px;
  font-weight: 600;
}

/* ─── 合计行样式 ─── */
:deep(.l3-total-row) {
  background-color: #f0f9eb !important;
  font-weight: 700;
}

/* ─── 底部合计+勾稽 ─── */
.l3-detail-footer {
  margin-top: 16px;
  padding: 10px 14px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.l3-total-info {
  font-size: 13px;
  color: #303133;
  display: flex;
  align-items: center;
  gap: 4px;
}

.l3-total-info strong {
  color: #409eff;
}

.l3-total-sep {
  color: #c0c4cc;
  margin: 0 4px;
}

.l3-maturity-total {
  color: #e6a23c !important;
}

.l3-row-count {
  color: #909399;
  margin-left: 6px;
}

.l3-cross-check-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.l3-cross-check-label {
  color: #606266;
}

.l3-cross-check-match {
  color: #67c23a;
  font-weight: 600;
}

.l3-cross-check-diff {
  color: #f56c6c;
  font-weight: 600;
}

/* ─── 编制提示折叠 ─── */
.l3-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 13px;
  color: #606266;
}

.l3-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.l3-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}

/* ─── 单元格文本 ─── */
.l3-cell-text {
  font-weight: 500;
}
</style>
