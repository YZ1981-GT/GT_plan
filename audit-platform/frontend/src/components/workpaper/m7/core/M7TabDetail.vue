<!--
  M7TabDetail.vue — M7-2 明细表（计提+使用，27列 → 3区段Tab）

  3区段Tab切换：计提(贷方增加) / 费用化使用(借方减少) / 资本化使用(借方减少+转固)
  区段间行同步：所有区段共享同一行集合，切换Tab只改可见列
  22公式实时计算：权益类 期末=期初+贷方(计提)-借方(使用)
  动态行新增（ElMessageBox.prompt输入名称）+ 删除
  导入导出三级（el-dropdown）useM7ImportExport

  Spec: .kiro/specs/m7-special-reserve/ Task 4.3
  Requirements: 3.1-3.5
-->
<template>
  <div class="m7-tab-detail">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M7-2 专项储备明细表</h3>
        <el-tag type="warning" size="small">27列·3区段Tab</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
          <el-icon><Plus /></el-icon> 新增项目
        </el-button>
        <el-dropdown :disabled="isReadonly" @command="handleImportExport" trigger="click">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item command="exportData">导出数据</el-dropdown-item>
              <el-dropdown-item command="importData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" :loading="aiLoading === 'detail'" @click="handleAI('detail')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文琥珀块 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>M7-2 专项储备明细表（27列按3区段Tab管理）：</strong>
        计提区（项目名称/期初余额/本期计提/期末余额/期初AJE·RJE/计提AJE·RJE/审定期初·审定计提） →
        费用化使用区（费用性支出/使用AJE·RJE/审定使用） →
        资本化使用区（资本性支出/审定期末/上期对比/变动额·率/备注）。
        <em>权益类贷方：期末=期初+贷方(计提)-借方(使用)</em>
      </div>
    </div>

    <!-- ═══ M7-1 审定表交叉验证状态 ═══ -->
    <el-alert
      v-if="!crossSheetMatch"
      type="error"
      :closable="false"
      show-icon
      class="cross-sheet-alert"
    >
      <template #title>
        明细合计与审定表M7-1不一致：差额 {{ fmtAmount(crossSheetDiff) }} 元
      </template>
    </el-alert>
    <el-alert
      v-else-if="computedRows.length > 0"
      type="success"
      :closable="false"
      show-icon
      class="cross-sheet-alert"
    >
      <template #title>
        ✓ 明细合计与审定表M7-1一致（审定期末合计 {{ fmtAmount(totals.auditedEnd) }}）
      </template>
    </el-alert>

    <!-- ═══ 区段Tab切换器（el-segmented） ═══ -->
    <el-segmented v-model="activeSegment" :options="segmentOptions" size="default" class="segment-switcher" />

    <!-- ═══ 明细表主体 ═══ -->
    <el-table :data="computedRows" border size="small" style="width: 100%" highlight-current-row :row-class-name="rowClassName">
      <el-table-column type="index" label="#" width="50" align="center" fixed />
      <el-table-column prop="itemName" label="项目名称" min-width="160" fixed>
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" :model-value="row.itemName" size="small" @change="(val: string) => handleUpdate($index, 'itemName', val)" />
          <span v-else>{{ row.itemName || '—' }}</span>
        </template>
      </el-table-column>

      <!-- ═══ 区段1: 计提（贷方增加） ═══ -->
      <template v-if="activeSegment === 'accrual'">
        <el-table-column label="期初余额" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.beginning" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'beginning', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.beginning) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期计提" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.creditAccrual" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'creditAccrual', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.creditAccrual) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="130" align="right">
          <template #header>
            <el-tooltip content="期末=期初+本期计提-本期使用（权益类贷方）" placement="top">
              <span class="formula-col-header">期末余额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初AJE" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.beginAje" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'beginAje', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.beginAje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初RJE" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.beginRje" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'beginRje', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.beginRje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="计提AJE" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.accrualAje" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'accrualAje', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.accrualAje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="计提RJE" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.accrualRje" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'accrualRje', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.accrualRje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定期初" min-width="130" align="right">
          <template #header>
            <el-tooltip content="审定期初=期初+期初AJE+期初RJE" placement="top">
              <span class="formula-col-header">审定期初</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.auditedBegin) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定计提" min-width="130" align="right">
          <template #header>
            <el-tooltip content="审定计提=本期计提+计提AJE+计提RJE" placement="top">
              <span class="formula-col-header">审定计提</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.auditedAccrual) }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 区段2: 费用化使用（借方减少—直接冲减） ═══ -->
      <template v-if="activeSegment === 'expense'">
        <el-table-column label="费用化支出" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.debitExpense" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'debitExpense', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.debitExpense) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="使用AJE" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.usageAje" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'usageAje', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.usageAje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="使用RJE" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.usageRje" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'usageRje', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.usageRje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="使用合计" min-width="130" align="right">
          <template #header>
            <el-tooltip content="使用合计=费用化支出+资本化支出" placement="top">
              <span class="formula-col-header">使用合计</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.debitTotal) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定使用" min-width="130" align="right">
          <template #header>
            <el-tooltip content="审定使用=使用合计+使用AJE+使用RJE" placement="top">
              <span class="formula-col-header">审定使用</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.auditedUsage) }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 区段3: 资本化使用（借方减少—转固定资产） ═══ -->
      <template v-if="activeSegment === 'capital'">
        <el-table-column label="资本化支出" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.debitCapital" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'debitCapital', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.debitCapital) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定期末" min-width="130" align="right">
          <template #header>
            <el-tooltip content="审定期末=审定期初+审定计提-审定使用（权益类贷方）" placement="top">
              <span class="formula-col-header">审定期末</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value formula-value--primary">{{ fmtAmount(row.auditedEnd) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上期期初" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.priorBeginning" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'priorBeginning', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.priorBeginning) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上期计提" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.priorAccrual" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'priorAccrual', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.priorAccrual) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上期使用" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.priorUsage" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'priorUsage', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.priorUsage) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上期期末" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.priorEnd" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'priorEnd', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.priorEnd) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动额" min-width="120" align="right">
          <template #header>
            <el-tooltip content="变动额=审定期末-上期期末" placement="top">
              <span class="formula-col-header">变动额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.changeAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动率" min-width="100" align="right">
          <template #header>
            <el-tooltip content="变动率=(审定期末-上期期末)/上期期末" placement="top">
              <span class="formula-col-header">变动率</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtPercent(row.changeRate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="150">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small" @change="(val: string) => handleUpdate($index, 'remark', val)" />
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 操作列 ═══ -->
      <el-table-column v-if="!isReadonly" label="操作" width="70" align="center" fixed="right">
        <template #default="{ $index }">
          <el-popconfirm title="确认删除该项目？" @confirm="handleRemoveRow($index)">
            <template #reference>
              <el-button type="danger" text size="small">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 合计行（sticky bottom） ═══ -->
    <div class="summary-bar">
      <span>审定期末合计：<strong class="formula-value--primary">{{ fmtAmount(totals.auditedEnd) }}</strong></span>
      <span>审定计提合计：<strong>{{ fmtAmount(totals.auditedAccrual) }}</strong></span>
      <span>审定使用合计：<strong>{{ fmtAmount(totals.auditedUsage) }}</strong></span>
      <span>共 <strong>{{ computedRows.length }}</strong> 个项目</span>
    </div>

    <!-- ═══ 编制提示details折叠底部 ═══ -->
    <details class="m7-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>27列按3区段Tab拆分（计提/费用化使用/资本化使用），行跨区段同步</li>
        <li><strong>权益类贷方</strong>：期末=期初+贷方(计提)-借方(使用)</li>
        <li>公式列（虚线下划线）：E=B+C-D期末 | L=B+F+G审定期初 | M=C+H+J审定计提 | N=D+I+K审定使用 | O=L+M-N审定期末</li>
        <li>计提（贷方增加）：安全生产费/维简费等按产量或收入计提</li>
        <li>费用化使用（借方减少）：直接冲减专项储备</li>
        <li>资本化使用（借方减少）：形成固定资产+全额折旧冲减专项储备（联动H1）</li>
        <li>明细合计应与审定表M7-1核对一致</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M7TabDetail — M7-2 专项储备明细表（27列·3区段Tab）
 *
 * Requirements: 3.1-3.5
 * - 27列区段Tab(计提/费用化/资本化) with el-segmented switch, row sync across tabs
 * - Use useM7FormData + useM7Detail composable
 * - 22公式实时计算 in computed rows
 * - Dynamic row add (ElMessageBox.prompt for name) + delete
 * - 导入导出 el-dropdown (useM7ImportExport)
 * - Font 13px, formula columns dashed underline + tooltip
 * - 合计行 (sticky bottom or highlighted)
 * - With M7-1 审定表交叉验证 status indicator
 * - 方法论上下文琥珀块 + section AI button + 复核按钮
 * - 编制提示details折叠底部
 *
 * 科目：4201 专项储备（贷方/权益类！期末=期初+贷方-借方）
 */
import { computed, inject, onMounted, ref } from 'vue'
import { Plus, MagicStick, Check } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useM7FormData } from '../../composables/useM7FormData'
import {
  useM7Detail,
  type M7DetailRow,
  M7_DETAIL_SEGMENTS,
  M7_DETAIL_DEFAULT_ITEMS,
} from '../../composables/useM7Detail'
import { useM7ImportExport } from '../../composables/useM7ImportExport'
import { useM7CrossSheet } from '../../composables/useM7CrossSheet'
import type { GenerateWorkpaperAiText } from '../../composables/useWorkpaperScaffold'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})
const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')
const aiLoading = ref('')

// ─── FormData + Composables ──────────────────────────────────────────────────

const formData = useM7FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  sheetName: 'M7-2',
})

const detailRows = ref<M7DetailRow[]>([])

const {
  activeSegment,
  computedRows,
  totals,
  addRow,
  removeRow,
  updateRow,
} = useM7Detail(formData, detailRows)

const {
  exportTemplate,
  exportData,
  importData: importFile,
} = useM7ImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const { adjudicationVsDetail } = useM7CrossSheet(formData.allResponses)

// ─── Segment options for el-segmented ────────────────────────────────────────

const segmentOptions = M7_DETAIL_SEGMENTS.map(s => ({
  label: s.label,
  value: s.key,
}))

// ─── Cross-sheet validation ──────────────────────────────────────────────────

const crossSheetMatch = computed(() => adjudicationVsDetail.value.isMatch)
const crossSheetDiff = computed(() => adjudicationVsDetail.value.diff)

// ─── Row class for summary row highlighting ──────────────────────────────────

function rowClassName({ row }: { row: M7DetailRow; rowIndex: number }): string {
  if (row.itemName === '合计') return 'summary-row'
  return ''
}

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleAddRow() { addRow() }
function handleRemoveRow(index: number) { removeRow(index) }

function handleUpdate(index: number, field: keyof M7DetailRow, value: string | number) {
  updateRow(index, field, value)
}

function handleImportExport(command: string) {
  switch (command) {
    case 'exportTemplate':
      exportTemplate('M7-2')
      break
    case 'exportData':
      exportData('M7-2')
      break
    case 'importData': {
      const input = document.createElement('input')
      input.type = 'file'
      input.accept = '.xlsx,.xls'
      input.onchange = async (e: Event) => {
        const file = (e.target as HTMLInputElement).files?.[0]
        if (file) {
          const result = await importFile('M7-2', file)
          if (result?.success) {
            await formData.loadData()
            _restoreRowsFromResponses()
            ElMessage.success(`导入完成，共 ${result.rowCount} 行`)
          }
        }
      }
      input.click()
      break
    }
  }
}

async function handleAI(section: string): Promise<void> {
  if (props.isReadonly) return
  aiLoading.value = section
  try {
    const context: Record<string, string> = {
      科目: '4201 专项储备（权益类·贷方）/ 明细表 M7-2',
      审定期末合计: fmtAmount(totals.value.auditedEnd),
      审定计提合计: fmtAmount(totals.value.auditedAccrual),
      审定使用合计: fmtAmount(totals.value.auditedUsage),
      项目数: String(computedRows.value.length),
      '与M7-1核对': crossSheetMatch.value ? '一致' : `差额 ${fmtAmount(crossSheetDiff.value)}`,
    }
    const text = await generateAiText({ section: `m7-detail-${section}`, context })
    if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
    ElMessageBox.alert(text, 'AI 辅助建议', { confirmButtonText: '知道了' }).catch(() => {})
  } catch { ElMessage.warning('AI 生成失败，请稍后重试') } finally { aiLoading.value = '' }
}

function handleReview() {
  openReviewDialog?.('M7-2-detail', 'M7-2 明细表')
}

// ─── Formatting ──────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(val: number): string {
  if (val === 0) return '—'
  return (val * 100).toFixed(2) + '%'
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  _restoreRowsFromResponses()
})

/**
 * 从 checklist_responses 恢复明细行数据
 * 完整行数据存储在 item_id="M7-2-full-data" 的 remark 中
 * 行概要存储在 item_id="M7-2-rows" 的 remark 中
 */
function _restoreRowsFromResponses() {
  // 优先读取完整数据（包含数值列）
  const fullDataResp = formData.allResponses.value.get('M7-2-full-data')
  if (fullDataResp?.remark) {
    try {
      const fullData = JSON.parse(fullDataResp.remark)
      if (Array.isArray(fullData) && fullData.length > 0) {
        detailRows.value = fullData.map((r: any) => _toDetailRow(r))
        return
      }
    } catch { /* parse failed */ }
  }

  // 降级：从行概要恢复
  const rowsResp = formData.allResponses.value.get('M7-2-rows')
  if (rowsResp?.remark) {
    try {
      const savedRows = JSON.parse(rowsResp.remark)
      if (Array.isArray(savedRows) && savedRows.length > 0) {
        detailRows.value = savedRows.map((r: any) => _toDetailRow(r))
        return
      }
    } catch { /* parse failed */ }
  }

  // 最终降级：使用默认明细行
  if (detailRows.value.length === 0) {
    detailRows.value = M7_DETAIL_DEFAULT_ITEMS.map((name, i) => _createEmptyRow(name, i))
  }
}

/** 将保存的对象转为M7DetailRow（补齐缺失字段） */
function _toDetailRow(r: any): M7DetailRow {
  return {
    key: r.key || `m7-detail-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    itemName: r.itemName || '',
    beginning: r.beginning || 0,
    creditAccrual: r.creditAccrual || 0,
    debitExpense: r.debitExpense || 0,
    debitCapital: r.debitCapital || 0,
    debitTotal: 0,
    endBalance: 0,
    beginAje: r.beginAje || 0,
    beginRje: r.beginRje || 0,
    accrualAje: r.accrualAje || 0,
    accrualRje: r.accrualRje || 0,
    usageAje: r.usageAje || 0,
    usageRje: r.usageRje || 0,
    auditedBegin: 0,
    auditedAccrual: 0,
    auditedUsage: 0,
    auditedEnd: 0,
    priorBeginning: r.priorBeginning || 0,
    priorAccrual: r.priorAccrual || 0,
    priorUsage: r.priorUsage || 0,
    priorEnd: r.priorEnd || 0,
    changeAmount: 0,
    changeRate: 0,
    remark: r.remark || '',
  }
}

/** 创建空白行 */
function _createEmptyRow(name: string, index: number): M7DetailRow {
  return {
    key: `m7-detail-default-${index}-${Date.now()}`,
    itemName: name,
    beginning: 0,
    creditAccrual: 0,
    debitExpense: 0,
    debitCapital: 0,
    debitTotal: 0,
    endBalance: 0,
    beginAje: 0,
    beginRje: 0,
    accrualAje: 0,
    accrualRje: 0,
    usageAje: 0,
    usageRje: 0,
    auditedBegin: 0,
    auditedAccrual: 0,
    auditedUsage: 0,
    auditedEnd: 0,
    priorBeginning: 0,
    priorAccrual: 0,
    priorUsage: 0,
    priorEnd: 0,
    changeAmount: 0,
    changeRate: 0,
    remark: '',
  }
}
</script>

<style scoped>
.m7-tab-detail { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }
.cross-sheet-alert { margin-bottom: 12px; }
.segment-switcher { margin-bottom: 12px; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.formula-value--primary { color: #67c23a; font-weight: 600; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.el-table .summary-row) { background: #f0f9eb !important; font-weight: 600; }
.summary-bar { display: flex; gap: 24px; padding: 10px 16px; margin-top: 12px; background: #f5f7fa; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; flex-wrap: wrap; position: sticky; bottom: 0; z-index: 5; }
.m7-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.m7-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.m7-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
