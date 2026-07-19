<template>
  <div class="g6-detail" data-testid="g6-detail">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="审计目标：确认其他债权投资明细的存在与权利归属；成本/利息调整/应计利息及公允价值计价准确；一年内到期分类与列报恰当，为 G6-1 审定表提供明细支撑。"
      style="margin-bottom: 12px"
    />

    <div class="section-head">
      <h3 class="sheet-title">G6-2 其他债权投资明细表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="detail.addRow()">
          + 投资项目
        </el-button>
        <el-dropdown trigger="click" size="small" @command="handleDropdownCommand">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item
                v-for="opt in dropdownOptions"
                :key="opt.command"
                :command="opt.command"
                :disabled="opt.disabled"
              >{{ opt.label }}</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="openReviewDialog('G6-2-detail')">💬复核</el-button>
      </div>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="date-label">资产负债表日：</span>
        <el-date-picker
          :model-value="detail.balanceSheetDate.value"
          type="date"
          size="small"
          value-format="YYYY-MM-DD"
          placeholder="请选择"
          :disabled="isReadonly"
          style="width: 160px"
          @update:model-value="(v: string) => detail.setBalanceSheetDate(v ?? '')"
        />
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G6-2" :context-project-id="props.projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G6-1" :context-project-id="props.projectId" /></span>
        <el-tag size="small" type="info">共 {{ detail.rows.value.length }} 行</el-tag>
        <el-tag size="small" type="success">期末审定合计 {{ fmtNum(detail.fvAuditedTotal.value) }}</el-tag>
      </div>
    </div>

    <el-alert
      v-if="detail.hasOverdueItems.value"
      type="error"
      :closable="false"
      style="margin-bottom: 8px"
      :title="`存在已逾期投资（${detail.maturityAlerts.value.filter(a => a.alertLevel === 'overdue').length}笔）— 需评估 ECL Stage`"
    />
    <el-alert
      v-if="detail.hasExpiringSoonItems.value"
      type="warning"
      :closable="false"
      style="margin-bottom: 8px"
      :title="`即将到期投资（${detail.maturityAlerts.value.filter(a => a.alertLevel === 'expiring_soon').length}笔）`"
    />

    <el-segmented
      v-model="detail.segment.value"
      :options="segmentOptions"
      size="small"
      class="segment-bar"
    />

    <template v-for="group in detail.categoryGroups.value" :key="group.category">
      <div v-if="group.rows.length > 0 || showEmptyGroups" class="category-group">
        <div class="category-title">{{ group.label }}</div>
        <el-table
          :data="groupDisplayRows(group.rows)"
          border
          size="small"
          max-height="360"
          row-key="id"
          :row-class-name="rowClassName"
          class="detail-table"
        >
          <el-table-column label="序号" width="55" align="center" fixed>
            <template #default="{ row }">
              <span v-if="row._isTotal" class="total-label">小计</span>
              <span v-else>{{ row.seq }}</span>
            </template>
          </el-table-column>

          <el-table-column
            v-for="col in detail.activeColumns.value"
            :key="col.prop"
            :label="col.label"
            :min-width="col.width"
            :align="col.type === 'number' || col.type === 'rate' || col.formula ? 'right' : 'left'"
          >
            <template #default="{ row }">
              <template v-if="row._isTotal">
                <span v-if="isSumCol(col.prop)" class="total-num">{{ fmtCell(row, col) }}</span>
              </template>
              <template v-else-if="col.formula">
                <el-tooltip :content="col.tooltip || ''" placement="top" :disabled="!col.tooltip">
                  <span class="formula-cell">{{ fmtCell(row, col) }}</span>
                </el-tooltip>
              </template>
              <template v-else-if="isReadonly">
                <span>{{ fmtCell(row, col) }}</span>
              </template>
              <template v-else-if="col.type === 'select'">
                <el-select
                  :model-value="String(row[col.prop] ?? '')"
                  size="small"
                  style="width: 100%"
                  @change="(v: string) => detail.updateRow(row.id, col.prop, v)"
                >
                  <el-option v-for="o in G6_INVEST_CATEGORY_OPTIONS" :key="o" :label="o" :value="o" />
                </el-select>
              </template>
              <template v-else-if="col.type === 'date'">
                <el-date-picker
                  :model-value="row[col.prop] as string"
                  type="date"
                  size="small"
                  value-format="YYYY-MM-DD"
                  style="width: 100%"
                  @update:model-value="(v: string) => detail.updateRow(row.id, col.prop, v ?? '')"
                />
              </template>
              <template v-else-if="col.type === 'rate'">
                <el-input-number
                  :model-value="Number(row[col.prop] ?? 0) * 100"
                  size="small"
                  :controls="false"
                  :precision="4"
                  class="compact-num"
                  @change="(v: number) => detail.updateRow(row.id, col.prop, (v ?? 0) / 100)"
                />
              </template>
              <template v-else-if="col.type === 'number'">
                <el-input-number
                  :model-value="Number(row[col.prop] ?? 0)"
                  size="small"
                  :controls="false"
                  :precision="2"
                  class="compact-num"
                  @change="(v: number) => detail.updateRow(row.id, col.prop, v ?? 0)"
                />
              </template>
              <template v-else>
                <el-input
                  :model-value="String(row[col.prop] ?? '')"
                  size="small"
                  @change="(v: string) => detail.updateRow(row.id, col.prop, v)"
                />
              </template>
            </template>
          </el-table-column>

          <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
            <template #default="{ row }">
              <el-popconfirm v-if="!row._isTotal" title="确认删除？" @confirm="detail.removeRow(row.id)">
                <template #reference>
                  <el-icon class="delete-icon"><Delete /></el-icon>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </template>

    <!-- 合计行摘要 -->
    <div class="grand-total-bar">
      <span>合计：期末小计 <strong>{{ fmtNum(detail.grandTotal.value.closingSubtotal) }}</strong></span>
      <span>期末公允价值审定 <strong>{{ fmtNum(detail.grandTotal.value.closingAudited) }}</strong></span>
      <span>期末报表数 <strong>{{ fmtNum(detail.grandTotal.value.closingReportAmount) }}</strong></span>
    </div>

    <G6AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      :note="detail.auditNote.value"
      :conclusion="detail.auditConclusion.value"
      @update:note="(v: string) => { detail.auditNote.value = v }"
      @update:conclusion="(v: string) => { detail.auditConclusion.value = v }"
      note-ai-section="detail-note"
      conclusion-ai-section="detail-conclusion"
      :related-context="{
        行数: detail.rows.value.length,
        期末审定合计: detail.fvAuditedTotal.value,
        期末报表数合计: detail.fvReportTotal.value,
      }"
      note-placeholder="填写审计说明：存在性、计价（摊余成本分量/公允价值）、一年内到期分类与列报测试情况。"
      note-hint="可概述程序测试结果、拟调整/未调整事项及范围受限影响。"
      conclusion-placeholder="A、未见异常。B、除上述调整事项外其余未见异常。C、存在重大未调整事项，不可确认。"
      conclusion-hint="按 A/B/C 口径评价明细表测试结果。"
    />

    <details class="prep-hint">
      <summary>编制提示（对齐 Excel G6-2）</summary>
      <ul>
        <li>期初/期末小计 = 成本 + 利息调整 + 应计利息；利息调整贷方余额填负数。</li>
        <li>审定数 = 公允价值 + 调整数（按公允价值口径，非摊余成本口径）。</li>
        <li>期末成本/利息调整/应计利息 = 期初对应项 + 本期变动（自动计算）。</li>
        <li>期初报表数 = 审定数 − 超过一年到期的部分；期末报表数 = 审定数 − 一年内到期余额。</li>
        <li>按到期日相对资产负债表日自动分为「其他流动资产」与「超过一年」两类。</li>
        <li>期末公允价值审定合计应与 G6-1「一、公允价值」勾稽。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G6TabDetail.vue — 对齐 Excel《明细表G6-2》（33列→4区段Tab）
 *
 * 改进相对源模板/旧实现：
 * - 列与公式对齐 Excel（审定=FV+调整；期末分项=期初+变动；报表数扣减）
 * - 按到期日自动分类；资产负债表日 + 逾期预警
 * - 去掉模板外冗余列（持有数量/合同条件/FV层次等改由 SPPI 组承载）
 */
import { ref, computed, toRef, inject, watch } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import {
  useG6MainDetail,
  G6_DETAIL_SEGMENTS,
  G6_INVEST_CATEGORY_OPTIONS,
  type OtherBondDetailRow,
  type G6DetailColumn,
} from '../../composables/useG6MainDetail'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import {
  useG6MainImportExport,
  type G6MainImportableSheet,
} from '../../composables/useG6MainImportExport'
import GtIndexChip from '../../GtIndexChip.vue'
import G6AuditTextCards from '../G6AuditTextCards.vue'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses?: Map<string, ChecklistResponse>
}>()

const emit = defineEmits<{ imported: [] }>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const isReadonly = computed(() => props.isReadonly)
const showEmptyGroups = false

const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
watch(
  () => props.allResponses,
  (source) => {
    if (!source) return
    allResponses.value = source
  },
  { immediate: true, deep: true },
)

const detail = useG6MainDetail({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses,
  isReadonly,
  htmlData: toRef(props, 'htmlData'),
})

// 父组件 checklist 就绪后重载
watch(
  () => props.allResponses?.size,
  () => detail.reload(),
  { immediate: true },
)

const segmentOptions = G6_DETAIL_SEGMENTS.map((s) => ({ label: s.label, value: s.key }))

type DisplayRow = OtherBondDetailRow & { _isTotal?: boolean; id: string }

function groupDisplayRows(list: OtherBondDetailRow[]): DisplayRow[] {
  if (!list.length) return []
  const totals = detail.sumRows(list)
  const totalRow: DisplayRow = {
    ...list[0],
    id: `total-${list[0]?.id || 'x'}`,
    seq: 0,
    investProject: '',
    _isTotal: true,
    ...totals,
  } as DisplayRow
  return [...list, totalRow]
}

function isSumCol(prop: keyof OtherBondDetailRow): boolean {
  return typeof detail.grandTotal.value[prop as string] === 'number'
}

function rowClassName({ row }: { row: DisplayRow }): string {
  return row._isTotal ? 'row-total' : ''
}

function fmtNum(v: unknown): string {
  const n = Number(v)
  if (!Number.isFinite(n) || n === 0) return '-'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtCell(row: DisplayRow, col: G6DetailColumn): string {
  const v = row[col.prop]
  if (col.type === 'rate' && typeof v === 'number') {
    return `${(v * 100).toFixed(2)}%`
  }
  if (col.type === 'number' || col.formula) return fmtNum(v)
  return String(v ?? '')
}

const ie = useG6MainImportExport({
  wpId: computed(() => props.wpId),
  onImported: () => {
    detail.reload()
    emit('imported')
  },
})
const dropdownOptions = computed(() => ie.getDropdownOptions('G6-2'))

async function handleDropdownCommand(command: string) {
  const [action, sheet] = command.split(':') as [string, G6MainImportableSheet]
  if (action === 'export-template') await ie.exportTemplate(sheet)
  else if (action === 'export-data') await ie.exportData(sheet)
  else if (action === 'import-data') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.xlsx,.xls'
    input.onchange = async (e: Event) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (file) await ie.importData(sheet, file)
    }
    input.click()
  }
}
</script>

<style scoped>
.g6-detail { padding: 12px 16px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.sheet-title { font-size: 15px; font-weight: 600; margin: 0; }
.head-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.tab-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 8px; flex-wrap: wrap; gap: 8px;
}
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.date-label { font-size: 13px; color: #606266; }
.chip-wrap { display: inline-flex; }
.segment-bar { margin-bottom: 12px; }
.category-group { margin-bottom: 16px; }
.category-title {
  font-weight: 600; font-size: 13px; color: #303133;
  padding: 8px 10px; background: #ecf5ff; border: 1px solid #d9ecff;
  border-radius: 4px 4px 0 0;
}
.detail-table { width: 100%; }
.detail-table :deep(.row-total) { background-color: #f0f9eb; font-weight: 600; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.total-num, .total-label { font-weight: 600; }
.compact-num { width: 100%; }
.compact-num :deep(.el-input__inner) { text-align: right; }
.delete-icon { cursor: pointer; color: #f56c6c; }
.delete-icon:hover { color: #e6001f; }
.grand-total-bar {
  display: flex; gap: 20px; flex-wrap: wrap;
  margin: 12px 0; padding: 10px 12px;
  background: #fafafa; border: 1px solid #ebeef5; border-radius: 4px;
  font-size: 13px; color: #606266;
}
.prep-hint {
  margin-top: 12px; padding: 8px 12px;
  background: #f5f7fa; border-radius: 4px; font-size: 12px; color: #606266;
}
.prep-hint summary { cursor: pointer; font-weight: 500; }
.prep-hint ul { margin: 6px 0 0; padding-left: 20px; }
.prep-hint li { margin-bottom: 3px; }
</style>
