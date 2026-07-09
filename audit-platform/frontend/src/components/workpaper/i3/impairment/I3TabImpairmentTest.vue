<template>
  <div class="i3-tab-impairment-test">
    <!-- 蓝色渐变引导区（CAS8先冲商誉规则说明）-->
    <div class="guidance-block">
      <div class="guidance-grid">
        <div class="guidance-step">
          <span class="step-num">①</span>
          <span>按资产组(CGU)确定含商誉的资产组账面价值</span>
        </div>
        <div class="guidance-step">
          <span class="step-num">②</span>
          <span>计算每个CGU可收回金额（跳转I3-7 DCF测试）</span>
        </div>
        <div class="guidance-step">
          <span class="step-num">③</span>
          <span>减值=MAX(资产组账面-可收回金额, 0)</span>
        </div>
        <div class="guidance-step">
          <span class="step-num">④</span>
          <span>分摊规则：先冲商誉（至零为止），剩余按比例分摊至其他资产</span>
        </div>
      </div>
    </div>

    <!-- 琥珀色方法论 block -->
    <div class="methodology-block">
      <p><strong>CAS8 减值分摊规则：</strong>含商誉的资产组发生减值时，减值损失金额应当先抵减分摊至资产组或者资产组组合中商誉的账面价值，再根据资产组或者资产组组合中除商誉之外的其他各项资产的账面价值所占比重，按比例抵减其他各项资产的账面价值。商誉减值损失一经确认，在以后会计期间不得转回。</p>
    </div>

    <!-- 主表区域 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">I3-6 商誉减值测试表（CGU分摊）</span>
          <div class="section-header-actions">
            <el-dropdown v-if="!isReadonly" trigger="click" @command="handleExportImport">
              <el-button size="small">导入导出 ▾</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
                  <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
                  <el-dropdown-item command="import-data" divided>导入数据</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button size="small" type="primary" link @click="handleAiGenerate">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
            <el-button size="small" circle @click="openReview('I3-6')">💬</el-button>
          </div>
        </div>
      </template>

      <!-- CGU 表格 -->
      <el-table
        :data="cguRows"
        border
        stripe
        size="small"
        class="impairment-table"
        :row-class-name="getRowClassName"
        row-key="rowId"
      >
        <el-table-column type="expand" width="30">
          <template #default="{ row, $index }">
            <!-- 展开区：其他资产子表 -->
            <div class="expand-section">
              <div class="expand-title">
                <span>其他资产明细 — {{ row.cguName }}</span>
                <el-button v-if="!isReadonly" size="small" @click="handleAddOtherAsset($index)">
                  + 新增资产
                </el-button>
              </div>
              <el-table
                :data="row.otherAssets"
                border
                size="small"
                class="other-assets-table"
              >
                <el-table-column type="index" label="#" width="40" align="center" />
                <el-table-column label="资产名称" min-width="150">
                  <template #default="{ row: asset, $index: assetIdx }">
                    <el-input
                      v-if="!isReadonly"
                      :model-value="asset.name"
                      size="small"
                      @blur="handleUpdateOtherAsset($index, assetIdx, 'name', ($event.target as HTMLInputElement).value)"
                    />
                    <span v-else>{{ asset.name || '-' }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="账面价值" min-width="130" align="right">
                  <template #default="{ row: asset, $index: assetIdx }">
                    <el-input-number
                      v-if="!isReadonly"
                      :model-value="asset.bookValue"
                      :controls="false"
                      size="small"
                      class="amt-input"
                      @change="handleUpdateOtherAsset($index, assetIdx, 'bookValue', $event)"
                    />
                    <span v-else class="amt-cell">{{ fmtAmt(asset.bookValue) }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="分摊减值" min-width="120" align="right">
                  <template #default="{ $index: assetIdx }">
                    <span class="formula-cell" title="按账面比例分摊（剩余减值）">
                      {{ fmtAmt(getOtherAllocationAmount($index, assetIdx)) }}
                    </span>
                  </template>
                </el-table-column>
                <el-table-column v-if="!isReadonly" label="" width="50" align="center">
                  <template #default="{ $index: assetIdx }">
                    <el-button size="small" type="danger" link @click="handleRemoveOtherAsset($index, assetIdx)">✕</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </template>
        </el-table-column>

        <!-- 序号 -->
        <el-table-column type="index" label="序号" width="50" align="center" />

        <!-- CGU名称 -->
        <el-table-column prop="cguName" label="资产组(CGU)名称" min-width="150" fixed>
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.cguName"
              size="small"
              @blur="handleUpdateCguName($index, ($event.target as HTMLInputElement).value)"
            />
            <span v-else>{{ row.cguName || '-' }}</span>
          </template>
        </el-table-column>

        <!-- 包含商誉 -->
        <el-table-column prop="goodwillAmount" label="包含商誉" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.goodwillAmount"
              :controls="false"
              size="small"
              class="amt-input"
              @change="handleUpdateGoodwill($index, $event)"
            />
            <span v-else class="amt-cell">{{ fmtAmt(row.goodwillAmount) }}</span>
          </template>
        </el-table-column>

        <!-- 资产组账面(含商誉) — 公式列 -->
        <el-table-column label="资产组账面(含商誉)" min-width="140" align="right">
          <template #header>
            <span class="formula-header" title="= 商誉 + Σ其他资产账面价值">资产组账面(含商誉)</span>
          </template>
          <template #default="{ row }">
            <span class="formula-cell" title="= 商誉 + Σ(其他资产账面)">{{ fmtAmt(row.cguBookValue) }}</span>
          </template>
        </el-table-column>

        <!-- 可收回金额 — 链接I3-7 -->
        <el-table-column label="可收回金额" min-width="160" align="right">
          <template #header>
            <span class="formula-header" title="来源：I3-7 DCF测试或手工输入">可收回金额</span>
          </template>
          <template #default="{ row, $index }">
            <div class="recoverable-cell">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.recoverableAmount"
                :controls="false"
                size="small"
                class="amt-input"
                @change="handleUpdateRecoverable($index, $event)"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.recoverableAmount) }}</span>
              <GtIndexChip value="I3-7" label="DCF" @click="navigateToSheet('I3-7')" />
            </div>
          </template>
        </el-table-column>

        <!-- 减值金额 — 公式列 -->
        <el-table-column label="减值金额" min-width="120" align="right">
          <template #header>
            <span class="formula-header" title="= MAX(资产组账面 - 可收回金额, 0)">减值金额</span>
          </template>
          <template #default="{ row }">
            <span
              :class="['formula-cell', { 'impaired-amount': row.impairmentAmount > 0 }]"
              title="= MAX(账面 - 可收回, 0)"
            >
              {{ fmtAmt(row.impairmentAmount) }}
            </span>
          </template>
        </el-table-column>

        <!-- 商誉分摊 — 公式列 -->
        <el-table-column label="商誉分摊" min-width="120" align="right">
          <template #header>
            <span class="formula-header" title="= MIN(减值金额, 包含商誉) — 先冲商誉至零">商誉分摊</span>
          </template>
          <template #default="{ row }">
            <span class="formula-cell" title="= MIN(减值, 商誉) — 先冲商誉">{{ fmtAmt(row.goodwillImpairment) }}</span>
          </template>
        </el-table-column>

        <!-- 其他资产分摊 — 公式列 -->
        <el-table-column label="其他资产分摊" min-width="130" align="right">
          <template #header>
            <span class="formula-header" title="= 减值金额 - 商誉分摊（按比例分摊至其他资产）">其他资产分摊</span>
          </template>
          <template #default="{ row }">
            <span class="formula-cell" title="= 减值 - 商誉分摊（按比例）">
              {{ fmtAmt(calcOtherImpairmentTotal(row)) }}
            </span>
          </template>
        </el-table-column>

        <!-- 操作列 -->
        <el-table-column v-if="!isReadonly" label="" width="50" align="center">
          <template #default="{ $index }">
            <el-button size="small" type="danger" link @click="handleRemoveCguRow($index)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 合计行 -->
      <div class="summary-row">
        <span class="summary-label">合计</span>
        <span class="summary-item">商誉合计: <strong>{{ fmtAmt(cguSummary.totalGoodwill) }}</strong></span>
        <span class="summary-item">资产组账面: <strong>{{ fmtAmt(cguSummary.totalCguBookValue) }}</strong></span>
        <span class="summary-item">可收回合计: <strong>{{ fmtAmt(cguSummary.totalRecoverable) }}</strong></span>
        <span class="summary-item" :class="{ 'impaired-amount': cguSummary.totalImpairment > 0 }">
          减值合计: <strong>{{ fmtAmt(cguSummary.totalImpairment) }}</strong>
        </span>
        <span class="summary-item">商誉减值: <strong>{{ fmtAmt(cguSummary.totalGoodwillImpairment) }}</strong></span>
        <span class="summary-item">其他分摊: <strong>{{ fmtAmt(cguSummary.totalOtherImpairment) }}</strong></span>
      </div>

      <!-- 新增CGU按钮 -->
      <div class="add-row-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddCguRow">+ 新增CGU</el-button>
      </div>
    </el-card>

    <!-- 商誉减值不可转回警告 -->
    <el-alert
      v-if="totalGoodwillImpairment > 0"
      type="warning"
      :closable="false"
      show-icon
      class="reversal-warning"
    >
      <template #title>
        商誉减值不可转回！本期商誉减值合计 <strong>{{ fmtAmt(totalGoodwillImpairment) }}</strong> 元，该减值损失在以后会计期间不得转回。
      </template>
    </el-alert>

    <!-- 审计说明与结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>审计说明与结论</span>
          <el-button size="small" type="primary" link @click="handleAiConclusion">
            <el-icon><MagicStick /></el-icon> AI生成
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写商誉减值测试结论（如：经对各资产组进行减值测试，商誉所在资产组的可收回金额均高于/低于其账面价值…）"
        :disabled="isReadonly"
        @blur="handleSaveConclusion"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>减值金额 = MAX(资产组账面价值(含商誉) - 可收回金额, 0)，不能为负</li>
        <li>分摊规则（CAS8两步法）：第一步先冲减商誉至零；第二步剩余按其他资产账面比例分摊</li>
        <li>可收回金额来源：点击 "I3-7" 芯片跳转至DCF测试表</li>
        <li>商誉减值损失一经确认，在以后会计期间<strong>不得转回</strong></li>
        <li>展开每行CGU可查看其他资产分摊明细</li>
        <li>含减值的行会以浅红色背景高亮显示</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I3TabImpairmentTest.vue — I3-6 商誉减值测试（CGU分摊）
 *
 * 按资产组(CGU)逐行显示：CGU名称|包含商誉|资产组账面(含商誉)|可收回金额|减值金额|商誉分摊|其他资产分摊
 * 减值=MAX(资产组账面-可收回金额, 0)
 * 分摊规则：先冲商誉→剩余按比例分摊
 * 商誉减值不可转回
 * 可收回金额列链接I3-7 DCF测试 (GtIndexChip)
 *
 * Spec: .kiro/specs/i3-goodwill/
 * Task: 4.7
 * Requirements: 5.1-5.5
 */
import { ref, inject, toRef, computed } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useI3Impairment, type CguRow } from '../../composables/useI3Impairment'
import GtIndexChip from '../../GtIndexChip.vue'

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

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── Composable ──────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)

const {
  cguRows,
  cguSummary,
  totalGoodwillImpairment,
  impairedRowIds,
  addCguRow,
  removeCguRow,
  updateGoodwillAmount,
  updateRecoverableAmount,
  updateCguName,
  addOtherAsset,
  removeOtherAsset,
  updateOtherAsset,
  exportCguRows,
} = useI3Impairment(
  toRef(props, 'wpId'),
  allResponsesRef as any,
  {
    onSave: (itemId: string, value: any) => emit('save', itemId, value),
  },
)

// ─── Local State ─────────────────────────────────────────────────────────────

const auditConclusion = ref('')

// ─── Row Highlight: impaired rows get light red background (Req 5) ───────────

function getRowClassName({ row }: { row: CguRow }): string {
  if (impairedRowIds.value.has(row.rowId)) {
    return 'row-impaired'
  }
  return ''
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** 计算单行其他资产分摊合计 */
function calcOtherImpairmentTotal(row: CguRow): number {
  if (!row.otherAllocations || row.otherAllocations.length === 0) return 0
  return row.otherAllocations.reduce((sum, a) => sum + a.amount, 0)
}

/** 获取指定CGU行指定其他资产的分摊金额 */
function getOtherAllocationAmount(cguIndex: number, assetIndex: number): number {
  const row = cguRows.value[cguIndex]
  if (!row || !row.otherAllocations) return 0
  const allocation = row.otherAllocations[assetIndex]
  return allocation?.amount ?? 0
}

// ─── Actions: CGU行管理 ──────────────────────────────────────────────────────

async function handleAddCguRow() {
  try {
    const { value: name } = await ElMessageBox.prompt(
      '请输入资产组(CGU)名称',
      '新增CGU',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '资产组名称不能为空',
      },
    )
    if (name) {
      addCguRow({ cguName: name.trim() })
    }
  } catch { /* cancelled */ }
}

function handleRemoveCguRow(index: number) {
  removeCguRow(index)
}

// ─── Actions: 字段更新 ───────────────────────────────────────────────────────

function handleUpdateGoodwill(index: number, value: number | null) {
  updateGoodwillAmount(index, value ?? 0)
}

function handleUpdateRecoverable(index: number, value: number | null) {
  updateRecoverableAmount(index, value ?? 0)
}

function handleUpdateCguName(index: number, value: string) {
  updateCguName(index, value)
}

// ─── Actions: 其他资产管理 ───────────────────────────────────────────────────

async function handleAddOtherAsset(cguIndex: number) {
  try {
    const { value: name } = await ElMessageBox.prompt(
      '请输入其他资产名称',
      '新增其他资产',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '资产名称不能为空',
      },
    )
    if (name) {
      addOtherAsset(cguIndex, { name: name.trim(), bookValue: 0 })
    }
  } catch { /* cancelled */ }
}

function handleRemoveOtherAsset(cguIndex: number, assetIndex: number) {
  removeOtherAsset(cguIndex, assetIndex)
}

function handleUpdateOtherAsset(
  cguIndex: number,
  assetIndex: number,
  field: 'name' | 'bookValue',
  value: string | number | null,
) {
  updateOtherAsset(cguIndex, assetIndex, field, value ?? 0)
}

// ─── Navigation ──────────────────────────────────────────────────────────────

function navigateToSheet(code: string) {
  emit('navigate-sheet', code)
}

// ─── Import/Export ───────────────────────────────────────────────────────────

function handleExportImport(command: string) {
  switch (command) {
    case 'export-template':
      console.log('[I3-6] Export template')
      break
    case 'export-data':
      console.log('[I3-6] Export data:', exportCguRows())
      break
    case 'import-data':
      console.log('[I3-6] Import data')
      break
  }
}

// ─── AI ──────────────────────────────────────────────────────────────────────

function handleAiGenerate() {
  console.log('[I3-6] AI generate impairment test')
}

function handleAiConclusion() {
  console.log('[I3-6] AI generate conclusion')
}

// ─── Save & Review ───────────────────────────────────────────────────────────

function handleSaveConclusion() {
  emit('save', 'I3-6-conclusion', auditConclusion.value)
}

function openReview(id: string) {
  openReviewDialog(id)
}

// ─── Format ──────────────────────────────────────────────────────────────────

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i3-tab-impairment-test { padding: 16px; font-size: 13px; }

/* 蓝色渐变引导区 */
.guidance-block {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6ecfa 100%);
  border: 1px solid #b3d8f0;
  border-radius: 8px;
  padding: 16px 20px;
  margin-bottom: 16px;
}
.guidance-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 24px;
}
.guidance-step {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 13px;
  color: #1a5276;
  line-height: 1.5;
}
.step-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #2980b9;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}

/* 琥珀色方法论 block */
.methodology-block {
  border-left: 4px solid var(--el-color-warning);
  background: #fffbeb;
  padding: 12px 16px;
  margin-bottom: 16px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  line-height: 1.6;
}

.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-title { font-weight: 600; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }

/* 主表格 */
.impairment-table { font-size: 13px; }
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }

/* 公式列样式 */
.formula-header {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
}
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}

/* 减值金额 >0 红色 */
.impaired-amount { color: var(--el-color-danger); font-weight: 600; }

/* 含减值的行浅红背景 */
:deep(.row-impaired) {
  background-color: #fef0f0 !important;
}
:deep(.row-impaired td) {
  background-color: #fef0f0 !important;
}

/* 可收回金额单元格 */
.recoverable-cell {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* 展开区：其他资产子表 */
.expand-section {
  padding: 12px 16px;
  background: #fafbfc;
}
.expand-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 12px;
  font-weight: 500;
  color: var(--el-text-color-regular);
}
.other-assets-table { font-size: 12px; }

/* 合计行 */
.summary-row {
  padding: 12px 0;
  font-size: 13px;
  border-top: 2px solid var(--el-border-color);
  margin-top: 12px;
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
  align-items: center;
}
.summary-label { font-weight: 700; min-width: 40px; }
.summary-item { font-variant-numeric: tabular-nums; }

.add-row-bar { margin-top: 12px; }

/* 不可转回警告 */
.reversal-warning { margin-bottom: 16px; }

.audit-note-card { margin-bottom: 12px; }

/* 编制提示 */
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
