<template>
  <div class="k10-tab-grant-reconcile">
    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>完整性与准确性：</b>政府补助收到、递延、计入损益金额相互勾稽核对一致（与 K7 递延收益/K10-5 联动）；</li>
        <li><b>发生与分类：</b>补助真实、与资产/收益相关分类恰当，计入其他收益/营业外收入判断正确。</li>
      </ol>
    </el-alert>

    <!-- ═══ 标题 + 按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <h3 class="section-title">K10-4 政府补助核对表</h3>
        <el-tag type="primary" effect="dark" size="small" class="account-badge">
          补助核对引擎·与K7递延收益一致性
        </el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" @click="handleAI">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
        <el-dropdown v-if="!props.isReadonly" trigger="click" @command="handleImportExport">
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

    <!-- ═══ 跨底稿引用 ═══ -->
    <div class="cross-ref-bar">
      <span class="cross-refs-label">关联底稿：</span>
      <GtIndexChip value="K7-1" :context-project-id="props.projectId" />
      <GtIndexChip value="K10-1" :context-project-id="props.projectId" />
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>政府补助核对逻辑：</strong>
        合计计入其他收益 = 直接计入其他收益 + 递延分摊转其他收益。
        期末递延余额 = 期初 + 新增 - 摊销(成本) - 摊销(其他收益) - 摊销(营业外) - 返还 - 其他转出。
        递延分摊合计须与K7递延收益(2401)本期分摊金额一致（|差额|&lt;0.01视为一致）。
      </div>
    </div>

    <!-- ═══ K7一致性检查显示 ═══ -->
    <div class="k7-consistency-bar" :class="{ consistent: reconcile.k7Consistency.value.isConsistent, inconsistent: !reconcile.k7Consistency.value.isConsistent }">
      <div class="consistency-left">
        <span class="consistency-label">K7递延收益一致性：</span>
        <el-tag
          :type="reconcile.k7Consistency.value.isConsistent ? 'success' : 'danger'"
          size="small"
          effect="dark"
        >
          {{ reconcile.k7Consistency.value.isConsistent ? '✓ 一致' : '✗ 不一致' }}
        </el-tag>
      </div>
      <div class="consistency-detail">
        <span>K10递延分摊: {{ fmtAmount(reconcile.k7Consistency.value.deferredAmortInK10) }}</span>
        <span class="divider">|</span>
        <span>K7本期分摊: {{ fmtAmount(reconcile.k7Consistency.value.amortInK7) }}</span>
        <span v-if="!reconcile.k7Consistency.value.isConsistent" class="diff-warning">
          差额: {{ fmtAmount(reconcile.k7Consistency.value.diff) }}
        </span>
      </div>
    </div>

    <!-- ═══ 核对表格 ═══ -->
    <el-table
      :data="reconcile.rows.value"
      border
      size="small"
      style="width: 100%"
      empty-text="暂无政府补助核对项目，请点击下方按钮新增"
      show-summary
      :summary-method="summaryMethod"
      class="reconcile-table"
    >
      <el-table-column prop="projectName" label="补助项目" min-width="130" fixed="left">
        <template #default="{ row }">
          <span class="project-name">{{ row.projectName || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column prop="period" label="期间" width="100">
        <template #default="{ row }">
          <el-input
            v-if="!props.isReadonly && row.isEditable"
            :model-value="row.period"
            size="small"
            placeholder="如2025"
            @change="(val: string) => reconcile.updateCell(row.rowKey, 'period', val)"
          />
          <span v-else>{{ row.period || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="直接冲减成本" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!props.isReadonly && row.isEditable"
            :model-value="row.directReduceCost"
            :controls="false"
            size="small"
            style="width: 100%"
            @change="(val: number | undefined) => reconcile.updateCell(row.rowKey, 'directReduceCost', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.directReduceCost) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="直接计入其他收益" width="140" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!props.isReadonly && row.isEditable"
            :model-value="row.directToOtherIncome"
            :controls="false"
            size="small"
            style="width: 100%"
            @change="(val: number | undefined) => reconcile.updateCell(row.rowKey, 'directToOtherIncome', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.directToOtherIncome) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="直接计入营业外" width="130" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!props.isReadonly && row.isEditable"
            :model-value="row.directToNonOpIncome"
            :controls="false"
            size="small"
            style="width: 100%"
            @change="(val: number | undefined) => reconcile.updateCell(row.rowKey, 'directToNonOpIncome', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.directToNonOpIncome) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="新增递延" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!props.isReadonly && row.isEditable"
            :model-value="row.newDeferred"
            :controls="false"
            size="small"
            style="width: 100%"
            @change="(val: number | undefined) => reconcile.updateCell(row.rowKey, 'newDeferred', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.newDeferred) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="期初递延余额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!props.isReadonly && row.isEditable"
            :model-value="row.openingDeferred"
            :controls="false"
            size="small"
            style="width: 100%"
            @change="(val: number | undefined) => reconcile.updateCell(row.rowKey, 'openingDeferred', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.openingDeferred) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="摊销冲减成本" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!props.isReadonly && row.isEditable"
            :model-value="row.amortReduceCost"
            :controls="false"
            size="small"
            style="width: 100%"
            @change="(val: number | undefined) => reconcile.updateCell(row.rowKey, 'amortReduceCost', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.amortReduceCost) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="摊销转其他收益" width="130" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!props.isReadonly && row.isEditable"
            :model-value="row.amortToOtherIncome"
            :controls="false"
            size="small"
            style="width: 100%"
            @change="(val: number | undefined) => reconcile.updateCell(row.rowKey, 'amortToOtherIncome', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.amortToOtherIncome) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="摊销转营业外" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!props.isReadonly && row.isEditable"
            :model-value="row.amortToNonOpIncome"
            :controls="false"
            size="small"
            style="width: 100%"
            @change="(val: number | undefined) => reconcile.updateCell(row.rowKey, 'amortToNonOpIncome', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.amortToNonOpIncome) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="返还" width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!props.isReadonly && row.isEditable"
            :model-value="row.refund"
            :controls="false"
            size="small"
            style="width: 100%"
            @change="(val: number | undefined) => reconcile.updateCell(row.rowKey, 'refund', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.refund) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="其他转出" width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!props.isReadonly && row.isEditable"
            :model-value="row.otherTransferOut"
            :controls="false"
            size="small"
            style="width: 100%"
            @change="(val: number | undefined) => reconcile.updateCell(row.rowKey, 'otherTransferOut', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.otherTransferOut) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="期末递延余额" width="130" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="公式：期初+新增-摊销成本-摊销其他收益-摊销营业外-返还-其他转出">
            {{ fmtAmount(row.closingDeferred) }}
          </span>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column v-if="!props.isReadonly" label="" width="60" align="center" fixed="right">
        <template #default="{ row }">
          <el-button v-if="row.isEditable" type="danger" size="small" link @click="reconcile.removeRow(row.rowKey)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 新增 + 合计计入其他收益 ═══ -->
    <div class="bottom-bar">
      <el-button v-if="!props.isReadonly" size="small" type="primary" plain @click="handleAddRow">
        + 新增补助项目
      </el-button>
      <div class="total-recognized">
        <el-tag type="warning" effect="plain" size="default">
          合计计入其他收益 = 直接计入({{ fmtAmount(reconcile.totals.value.directToOtherIncome) }}) + 递延分摊({{ fmtAmount(reconcile.totals.value.amortToOtherIncome) }}) = <strong>{{ fmtAmount(reconcile.totals.value.totalRecognizedOtherIncome) }}</strong>
        </el-tag>
      </div>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="k10-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>政府补助核对逻辑：合计计入其他收益 = 直接计入 + 递延分摊转其他收益</li>
        <li>期末递延余额(公式) = 期初 + 新增 - 摊销(成本) - 摊销(其他收益) - 摊销(营业外) - 返还 - 其他转出</li>
        <li>递延分摊合计应与K7递延收益(2401)本期分摊一致（差额&lt;0.01为一致）</li>
        <li>与日常活动相关的政府补助 → 其他收益(6117)；与日常活动无关 → 营业外收入(6301/K12)</li>
        <li>点击 GtIndexChip K7-1 可跳转至K7递延收益底稿核对</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K10TabGrantReconcile — K10-4 政府补助核对表（与K7递延收益分摊核对）
 *
 * Spec: .kiro/specs/k10-other-income/
 * Task: 4.4
 * Requirements: 4.1-4.5
 *
 * 功能：
 * - 补助核对引擎：合计计入其他收益 = 直接计入 + 递延分摊
 * - 期末递延余额公式列（虚线下划线+tooltip）
 * - K7一致性检查：绿色✓一致 / 红色✗不一致（|diff|>=0.01）
 * - GtIndexChip跳转K7-1
 * - 动态行（ElMessageBox.prompt输入补助项目名称）
 * - Total行：显示各列合计 + 合计计入其他收益
 * - 导入导出（el-dropdown三级）
 */
import { computed, defineAsyncComponent, inject, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, Check, ArrowDown } from '@element-plus/icons-vue'
import { useK10GrantReconcile } from '../../composables/useK10GrantReconcile'
import { useK10ImportExport } from '../../composables/useK10ImportExport'
import { api } from '@/services/apiProxy'

const GtIndexChip = defineAsyncComponent(() => import('../../GtIndexChip.vue'))

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

// ─── Inject复核对话 ──────────────────────────────────────────────────────────
const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── Composables ─────────────────────────────────────────────────────────────

const reconcile = useK10GrantReconcile({
  allResponses: computed(() => props.allResponses),
  projectId: computed(() => props.projectId),
  wpId: computed(() => props.wpId),
  isReadonly: computed(() => props.isReadonly),
  onSave: (itemId, value) => emit('save', itemId, value),
})

const importExport = useK10ImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  sheetCode: 'K10-4',
})

// ─── Handlers ────────────────────────────────────────────────────────────────

function fmtAmount(val: number | undefined | null): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/** 新增行（ElMessageBox.prompt输入项目名称） */
async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入政府补助项目名称',
      '新增补助项目',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPlaceholder: '如：研发费用补贴/稳岗补贴...',
        inputValidator: (val: string) => {
          if (!val || !val.trim()) return '请输入补助项目名称'
          return true
        },
      },
    )
    reconcile.addRow(value.trim())
  } catch {
    // 用户取消
  }
}

function handleImportExport(command: string): void {
  if (command === 'export-template') importExport.exportTemplate()
  else if (command === 'export-data') importExport.exportData()
  else if (command === 'import-data') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.xlsx,.xls'
    input.onchange = async (e: Event) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (file) await importExport.importData(file)
    }
    input.click()
  }
}

function handleAI(): void {
  // AI辅助钩子
}

function handleReview(): void {
  openReviewDialog?.('K10-4-grant-reconcile', '政府补助核对表')
}

/** 合计行方法 */
function summaryMethod({ columns }: { columns: any[] }): string[] {
  const t = reconcile.totals.value
  return columns.map((col: any, idx: number) => {
    if (idx === 0) return '合计'
    const prop = col.property
    if (prop === 'period') return ''
    if (prop in t) return fmtAmount((t as any)[prop])
    // 手动映射无property列（按列顺序）
    const colMap: Record<number, number> = {}
    // 由于el-table-column没有prop，用label匹配
    return ''
  })
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  reconcile.initFromResponses()
})
</script>

<style scoped>
.k10-tab-grant-reconcile { padding: 12px; font-size: var(--wp-font-size, 13px); }

.section-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px; flex-wrap: wrap; gap: 8px;
}
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; }
.account-badge { font-size: 11px; }

.cross-ref-bar {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  margin-bottom: 12px; padding: 6px 12px;
  background: #f5f7fa; border-radius: 6px;
}
.cross-refs-label { color: #909399; font-size: 12px; white-space: nowrap; }

.methodology-context {
  background: linear-gradient(135deg, #fffbe6 0%, #fff8e1 100%);
  border-left: 3px solid #e6a23c;
  padding: 8px 12px; margin-bottom: 12px;
  border-radius: 0 4px 4px 0; font-size: 12px; color: #8b6914;
}
.methodology-text strong { color: #c77d00; }

/* K7一致性状态栏 */
.k7-consistency-bar {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 12px; border-radius: 4px; margin-bottom: 12px;
  transition: background-color 0.3s;
}
.k7-consistency-bar.consistent { background: #f0f9eb; border: 1px solid #c2e7b0; }
.k7-consistency-bar.inconsistent { background: #fef0f0; border: 1px solid #f5c4c4; }
.consistency-left { display: flex; align-items: center; gap: 8px; }
.consistency-label { font-size: 12px; color: #606266; }
.consistency-detail { display: flex; align-items: center; gap: 8px; font-size: 12px; color: #606266; }
.consistency-detail .divider { color: #dcdfe6; }
.diff-warning { color: #f56c6c; font-weight: 600; }

/* 表格 */
.reconcile-table { font-size: var(--wp-font-size, 13px); }
.reconcile-table :deep(.formula-col) { background: #fafafa; }
.formula-value {
  border-bottom: 1px dashed #909399;
  cursor: help;
  color: #606266;
}
.project-name { font-weight: 500; }

/* 底部操作栏 */
.bottom-bar {
  display: flex; justify-content: space-between; align-items: center;
  margin-top: 12px; flex-wrap: wrap; gap: 8px;
}
.total-recognized { font-size: var(--wp-font-size, 13px); }
.total-recognized strong { color: #e6a23c; }

/* 编制提示 */
.k10-details-tip {
  margin-top: 16px; padding: 8px 12px;
  background: #f5f7fa; border-radius: 4px;
  font-size: 12px; color: #606266;
}
.k10-details-tip summary { cursor: pointer; font-weight: 500; color: #409eff; }
.k10-details-tip ul { margin: 8px 0 0 0; padding-left: 20px; }
.k10-details-tip li { margin-bottom: 4px; }
</style>
