<!--
  K3TabDetail.vue — K3-2 明细表（27列3区段+账龄+疑似未入账标记+动态行+3年以上高亮+导入导出）

  3区段Tab切换(el-segmented: 基础|账龄|检查)，同行同步
  区段0 基础：序号/往来对象/性质(下拉)/关联关系(下拉)/期初/本期增加(贷方)/本期减少(借方)/期末(公式:虚线)
  区段1 账龄：往来对象(只读)/1年以内/1-2年/2-3年/3年以上/账龄合计(公式)/期末余额(公式)——3年以上>0的行橙色背景!
  区段2 检查：往来对象/形成原因/预计偿付时间/凭证号/结论(下拉)/疑似未入账(checkbox)/备注
  动态行新增：el-button"+ 新增"→ElMessageBox.prompt输入往来对象确认后创建
  底部统计卡片：往来笔数/期末合计/3年以上占比(百分比)
  el-dropdown导入导出(导出模板/导出数据/导入数据)——useK3ImportExport消费
  公式列虚线下划线+cursor:help+tooltip
  合计行固定底部
  表格字体13px
  AI按钮(section标题行右侧)
  编制提示(details折叠底部)
  Consumes: useK3Detail composable

  Spec: .kiro/specs/k3-other-payables/ Task 4.3
  Requirements: 3.1-3.6, 7.4
-->
<template>
  <div class="k3-tab-detail">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>K3-2明细表按往来对象逐笔列示其他应付款余额及账龄分布。<strong>负债类科目</strong>：期末=期初+贷方(增加)-借方(减少)。3年以上长期挂账标记橙色提示风险。账龄合计应等于期末余额。</p>
    </div>

    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>完整性：</b>所有应当记录的其他应付款均已记录（负债完整性重点）；</li>
        <li><b>存在：</b>资产负债表中记录的其他应付款是存在的，且已记录在恰当的账户中；</li>
        <li><b>计价和分摊：</b>其他应付款以恰当的金额包括在财务报表中，相关计价或分摊调整已恰当记录。</li>
      </ol>
    </el-alert>

    <!-- 标题栏 + 操作 -->
    <div class="section-head">
      <h3 class="sheet-title">K3-2 其他应付款明细表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" link @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" :disabled="isReadonly" @click="handleAddRow">＋ 新增</el-button>
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
        <el-button size="small" @click="handleReview">💬 复核</el-button>
      </div>
    </div>

    <!-- 3区段 el-segmented -->
    <el-segmented
      v-model="activeSegmentIdx"
      :options="segmentOptions"
      size="default"
      class="segment-bar"
    />

    <!-- 表格 -->
    <el-table
      :data="detail.detailRows.value"
      border
      size="small"
      :max-height="520"
      class="detail-table"
      :row-class-name="rowClassName"
      show-summary
      :summary-method="summaryMethod"
    >
      <!-- ═══ 区段0 基础 ═══ -->
      <template v-if="activeSegmentIdx === 0">
        <el-table-column label="序号" width="55" align="center">
          <template #default="{ row }">{{ row.seqNo }}</template>
        </el-table-column>
        <el-table-column label="往来对象" min-width="160">
          <template #default="{ row }">
            <span>{{ row.counterparty }}</span>
          </template>
        </el-table-column>
        <el-table-column label="性质" min-width="130">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.nature"
              size="small"
              placeholder="选择性质"
              @change="(v: string) => detail.updateCell(row.rowId, 'nature', v)"
            >
              <el-option v-for="opt in natureOptions" :key="opt" :label="opt" :value="opt" />
            </el-select>
            <span v-else>{{ row.nature || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="关联关系" min-width="140">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.relatedParty"
              size="small"
              placeholder="关联关系"
              @change="(v: string) => detail.updateCell(row.rowId, 'relatedParty', v)"
            >
              <el-option v-for="opt in relatedPartyOptions" :key="opt" :label="opt" :value="opt" />
            </el-select>
            <span v-else>{{ row.relatedParty || '-' }}</span>
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
              @change="(v: number) => detail.updateCell(row.rowId, 'beginBalance', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期增加(贷方)" min-width="135" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.increase"
              size="small"
              :controls="false"
              class="amount-input"
              @change="(v: number) => detail.updateCell(row.rowId, 'increase', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少(借方)" min-width="135" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.decrease"
              size="small"
              :controls="false"
              class="amount-input"
              @change="(v: number) => detail.updateCell(row.rowId, 'decrease', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="130" align="right">
          <template #default="{ row }">
            <el-tooltip content="期末=期初+贷方-借方（负债类）" placement="top">
              <span class="formula-cell">{{ fmtAmt(row.endBalance) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 区段1 账龄（动态，基于 bands from useAgingConfig） ═══ -->
      <template v-if="activeSegmentIdx === 1">
        <el-table-column label="往来对象" min-width="160">
          <template #default="{ row }">
            <span>{{ row.counterparty }}</span>
          </template>
        </el-table-column>
        <el-table-column
          v-for="band in bands"
          :key="band.key"
          :label="band.label"
          min-width="120"
          align="right"
        >
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.agingAudited[band.key] ?? 0"
              size="small"
              :controls="false"
              class="amount-input"
              @change="(v: number) => detail.updateCell(row.rowId, `agingAudited.${band.key}`, v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.agingAudited[band.key]) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账龄合计" min-width="120" align="right">
          <template #default="{ row }">
            <el-tooltip content="=各账龄段之和" placement="top">
              <span class="formula-cell">{{ fmtAmt(row.agingTotal) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="120" align="right">
          <template #default="{ row }">
            <el-tooltip content="勾稽：账龄合计应=期末余额" placement="top">
              <span
                class="formula-cell"
                :class="{ 'reconcile-error': row.agingTotal !== row.endBalance && row.endBalance !== 0 }"
              >{{ fmtAmt(row.endBalance) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 区段2 检查 ═══ -->
      <template v-if="activeSegmentIdx === 2">
        <el-table-column label="往来对象" min-width="160">
          <template #default="{ row }">
            <span>{{ row.counterparty }}</span>
          </template>
        </el-table-column>
        <el-table-column label="形成原因" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.formationReason"
              size="small"
              placeholder="形成原因"
              @change="(v: string) => detail.updateCell(row.rowId, 'formationReason', v)"
            />
            <span v-else>{{ row.formationReason || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="预计偿付时间" min-width="130">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.repaymentDate"
              size="small"
              placeholder="如：2026-06"
              @change="(v: string) => detail.updateCell(row.rowId, 'repaymentDate', v)"
            />
            <span v-else>{{ row.repaymentDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭证号" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.voucherRef"
              size="small"
              placeholder="凭证号"
              @change="(v: string) => detail.updateCell(row.rowId, 'voucherRef', v)"
            />
            <span v-else>{{ row.voucherRef || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="结论" min-width="110">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.checkConclusion"
              size="small"
              placeholder="结论"
              @change="(v: string) => detail.updateCell(row.rowId, 'checkConclusion', v)"
            >
              <el-option v-for="opt in conclusionOptions" :key="opt" :label="opt" :value="opt" />
            </el-select>
            <span v-else>{{ row.checkConclusion || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="疑似未入账" width="100" align="center">
          <template #default="{ row }">
            <el-checkbox
              :model-value="row.suspectedUnrecorded"
              :disabled="isReadonly"
              @change="(v: boolean) => detail.updateCell(row.rowId, 'suspectedUnrecorded', v)"
            />
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.remark"
              size="small"
              placeholder="备注"
              @change="(v: string) => detail.updateCell(row.rowId, 'remark', v)"
            />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- 操作列（所有区段共享） -->
      <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
        <template #default="{ $index }">
          <el-button size="small" type="danger" link @click="handleRemoveRow($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部统计卡片 -->
    <div class="stats-bar">
      <el-tag type="info" effect="plain">往来笔数: {{ detail.subtotals.value.count }}</el-tag>
      <el-tag type="primary" effect="plain">期末合计: {{ fmtAmt(detail.subtotals.value.endBalance) }}</el-tag>
      <el-tag
        :type="agingOver3YPercent > 30 ? 'danger' : agingOver3YPercent > 10 ? 'warning' : 'success'"
        effect="plain"
      >3年以上占比: {{ fmtPercent(agingOver3YPercent) }}</el-tag>
    </div>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>27列拆为3区段Tab切换（基础/账龄/检查），行数据同步</li>
        <li><strong>负债类科目</strong>：期末余额=期初余额+本期增加(贷方)-本期减少(借方)</li>
        <li>账龄区间基于项目级配置动态生成，账龄合计应与期末余额一致（不一致红色提示）</li>
        <li>3年以上账龄>0的行标记橙色背景（长期挂账风险），需关注是否转营业外收入</li>
        <li>"疑似未入账"复选框标记完整性认定风险项（反向截止测试发现的漏记负债）</li>
        <li>新增行需弹窗输入往来对象名称后创建</li>
        <li>明细合计应与K3-1审定表其他应付款期末一致</li>
        <li>导入导出支持按模板批量录入明细</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K3TabDetail.vue — K3-2 明细表（27列3区段+账龄+疑似未入账标记+动态行+3年以上高亮+导入导出）
 * Spec: .kiro/specs/k3-other-payables/ | Task: 4.3
 * Requirements: 3.1-3.6, 7.4
 *
 * Consumes: useK3Detail composable + useK3ImportExport composable
 * 科目: 2241 其他应付款（贷方/负债类）
 */
import { ref, computed, inject, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useK3Detail, type K3DetailRow } from '../../composables/useK3Detail'
import { useK3ImportExport } from '../../composables/useK3ImportExport'

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

// ─── Injections ──────────────────────────────────────────────────────────────

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── Constants ───────────────────────────────────────────────────────────────

const natureOptions = ['保证金及押金', '往来款', '代收代付', '其他']
const relatedPartyOptions = ['非关联', '控股子公司', '联营/合营企业', '关键管理人员', '关联自然人', '其他关联方']
const conclusionOptions = ['正常', '异常', '长期挂账', '待确认']

const segmentOptions = [
  { label: '基础', value: 0 },
  { label: '账龄', value: 1 },
  { label: '检查', value: 2 },
]

// ─── Composables ─────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)

const detail = useK3Detail({
  allResponses: allResponsesRef as any,
  saveResponse: (itemId: string, value: any) => {
    emit('save', itemId, value)
  },
  projectId: toRef(props, 'projectId'),
})

const { bands } = detail

const {
  exportTemplate,
  exportData,
  importData,
} = useK3ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetCode: 'K3-2',
})

// ─── 区段状态 ────────────────────────────────────────────────────────────────

const activeSegmentIdx = ref(0)

// ─── 3年以上占比 ──────────────────────────────────────────────────────────────

const agingOver3YPercent = computed(() => {
  const endTotal = detail.subtotals.value.endBalance
  if (!endTotal || endTotal === 0) return 0
  // 动态计算3年以上：从 agingAudited 中找 over3/y3to4/y4to5/over5 key
  const over3Keys = ['y3to4', 'y4to5', 'over5', 'over3']
  const over3y = detail.detailRows.value.reduce((sum, r) => {
    let rowSum = 0
    for (const k of over3Keys) {
      if (k in r.agingAudited) rowSum += (r.agingAudited[k] || 0)
    }
    return sum + rowSum
  }, 0)
  return Math.round((over3y / endTotal) * 10000) / 100
})

// ─── 行样式：3年以上>0橙色背景（Req 3.5） ────────────────────────────────────

function rowClassName({ row }: { row: K3DetailRow }): string {
  // 3年以上>0的行橙色背景（动态 key 检测）
  const over3Keys = ['y3to4', 'y4to5', 'over5', 'over3']
  for (const k of over3Keys) {
    if (k in row.agingAudited && (row.agingAudited[k] || 0) > 0) return 'aging-over3y-row'
  }
  return ''
}

// ─── 合计行 (show-summary) ───────────────────────────────────────────────────

function summaryMethod({ columns }: { columns: any[] }): string[] {
  return columns.map((col, idx) => {
    if (idx === 0) return '合计'
    const key = col.property
    if (!key) return ''

    // 基础区段合计
    if (activeSegmentIdx.value === 0) {
      if (['beginBalance', 'increase', 'decrease', 'endBalance'].includes(key)) {
        const total = detail.detailRows.value.reduce((sum, r) => sum + ((r as any)[key] || 0), 0)
        return fmtAmt(total)
      }
    }
    // 账龄区段合计（动态列无 property，skip）
    if (activeSegmentIdx.value === 1) {
      if (key === 'agingTotal' || key === 'endBalance') {
        const total = detail.detailRows.value.reduce((sum, r) => sum + ((r as any)[key] || 0), 0)
        return fmtAmt(total)
      }
    }
    return ''
  })
}

// ─── 行操作 ──────────────────────────────────────────────────────────────────

async function handleAddRow() {
  await detail.addRow()
}

function handleRemoveRow(idx: number) {
  const row = detail.detailRows.value[idx]
  if (!row) return
  ElMessageBox.confirm(
    `确定删除往来对象"${row.counterparty}"？删除后不可恢复。`,
    '确认删除',
    {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    },
  ).then(() => {
    detail.removeRow(idx)
    ElMessage.success('已删除')
  }).catch(() => {
    // 用户取消
  })
}

// ─── 导入导出 ─────────────────────────────────────────────────────────────────

function handleExportTemplate() { exportTemplate() }
function handleExportData() { exportData() }

function handleImportData() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls'
  input.onchange = async (e) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return
    const result = await importData(file)
    if (result && result.rowCount > 0) {
      // 重新加载数据 — composable内部watch触发即可
    }
  }
  input.click()
}

// ─── AI / 复核 ───────────────────────────────────────────────────────────────

function handleAiGenerate() {
  console.log('[K3-2] AI generate: detail')
}
function handleReview() { openReviewDialog('K3-2-detail') }

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(val: number): string {
  return `${val.toFixed(2)}%`
}
</script>

<style scoped>
.k3-tab-detail {
  padding: 16px;
  font-size: var(--wp-font-size, 13px);
}

/* 方法论上下文（琥珀色左边线+浅黄背景） */
.methodology-context {
  border-left: 4px solid var(--el-color-warning);
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 16px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  line-height: 1.6;
}

/* 标题栏 */
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
}
.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* el-segmented 区段栏 */
.segment-bar {
  margin-bottom: 12px;
}

/* 表格 */
.detail-table {
  font-size: var(--wp-font-size, 13px);
}
.amount-cell {
  font-variant-numeric: tabular-nums;
}
.amount-input {
  width: 100%;
}

/* 公式列：虚线下划线 + cursor:help */
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}

/* 账龄合计≠期末 红色提示 */
.reconcile-error {
  color: var(--el-color-danger);
  border-bottom-color: var(--el-color-danger);
}

/* 3年以上>0的行橙色背景 (Req 3.5) */
.detail-table :deep(.aging-over3y-row) {
  background-color: #fff7ed !important;
}
.detail-table :deep(.aging-over3y-row:hover > td) {
  background-color: #ffedd5 !important;
}

/* 合计行固定底部 */
.detail-table :deep(.el-table__footer-wrapper) {
  font-weight: 600;
  position: sticky;
  bottom: 0;
  z-index: 2;
  background: var(--el-bg-color);
}

/* 统计栏 */
.stats-bar {
  display: flex;
  gap: 12px;
  margin-top: 12px;
  padding: 10px 0;
  flex-wrap: wrap;
}

/* 编制提示 */
.compile-hint {
  margin-top: 16px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.compile-hint summary {
  cursor: pointer;
  font-weight: 500;
}
.compile-hint ul {
  padding-left: 20px;
  margin-top: 8px;
  line-height: 1.8;
}
</style>
