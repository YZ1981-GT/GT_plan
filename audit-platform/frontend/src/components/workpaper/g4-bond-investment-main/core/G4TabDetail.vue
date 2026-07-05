<template>
  <div class="g4-detail">
    <!-- Section 标题栏 -->
    <div class="section-head">
      <h3 class="sheet-title">G4-2 债权投资明细表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="detail.addRow()">新增行</el-button>
        <!-- 导入导出 el-dropdown -->
        <el-dropdown trigger="click" size="small" @command="handleIECommand">
          <el-button size="small">
            导入导出 ▾
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export">导出数据</el-dropdown-item>
              <el-dropdown-item command="import">
                <el-upload
                  ref="importUploadRef"
                  :show-file-list="false"
                  accept=".xlsx"
                  :auto-upload="false"
                  :disabled="isReadonly || ie.importing.value"
                  @change="onImportFile"
                >
                  <span>导入数据</span>
                </el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="openReviewDialog('G4-2-detail')">💬复核</el-button>
      </div>
    </div>

    <!-- 资产负债表日设置 -->
    <div class="balance-date-bar">
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

    <!-- 到期日预警提示 -->
    <el-alert
      v-if="detail.hasOverdueItems.value"
      type="error"
      :closable="false"
      style="margin-bottom: 8px"
    >
      <template #title>
        <span>🔴 存在已逾期投资项目（{{ detail.maturityAlerts.value.filter(a => a.alertLevel === 'overdue').length }}笔）— 需评估ECL Stage升级</span>
      </template>
      <ul style="margin: 4px 0 0; padding-left: 18px; font-size: 12px; line-height: 1.8">
        <li v-for="a in detail.maturityAlerts.value.filter(a => a.alertLevel === 'overdue')" :key="a.rowId">{{ a.message }}</li>
      </ul>
    </el-alert>
    <el-alert
      v-if="detail.hasExpiringSoonItems.value"
      type="warning"
      :closable="false"
      style="margin-bottom: 8px"
    >
      <template #title>
        <span>🟠 即将到期投资（{{ detail.maturityAlerts.value.filter(a => a.alertLevel === 'expiring_soon').length }}笔）</span>
      </template>
      <ul style="margin: 4px 0 0; padding-left: 18px; font-size: 12px; line-height: 1.8">
        <li v-for="a in detail.maturityAlerts.value.filter(a => a.alertLevel === 'expiring_soon')" :key="a.rowId">{{ a.message }}</li>
      </ul>
    </el-alert>

    <!-- 5区段Tab（el-segmented切换列定义，不销毁el-table实例） -->
    <el-segmented
      v-model="detail.segment.value"
      :options="segmentOptions"
      size="small"
      class="segment-bar"
    />

    <!-- 数据分类展示 -->
    <template v-for="group in detail.categoryGroups.value" :key="group.category">
      <div v-if="group.rows.length > 0" class="category-group">
        <div class="category-title">{{ group.label }}</div>

        <!-- 单一el-table实例（行数据共享同一reactive数组，仅切换列定义） -->
        <el-table
          :data="group.rows"
          border
          size="small"
          :max-height="enableVirtualScroll ? 600 : undefined"
          highlight-current-row
          :current-row-key="currentRowKey(group.rows)"
          row-key="id"
          class="detail-table"
          @current-change="(row: BondDetailRow | null) => handleRowSelect(row, group.rows)"
        >
          <!-- 序号固定列 -->
          <el-table-column label="序号" width="55" align="center" fixed>
            <template #default="{ row }">{{ row.seq }}</template>
          </el-table-column>

          <!-- 投资项目固定列 -->
          <el-table-column label="投资项目" width="160" fixed>
            <template #default="{ row }">
              <el-input
                :model-value="row.investProject"
                size="small"
                :disabled="isReadonly"
                @change="(v: string) => detail.updateRow(row.id, { investProject: v })"
              />
            </template>
          </el-table-column>

          <!-- 动态列（根据当前区段Tab切换） -->
          <el-table-column
            v-for="col in activeColumnsFiltered"
            :key="String(col.prop)"
            :label="col.label"
            :min-width="col.width"
            align="right"
          >
            <template #default="{ row }">
              <!-- 公式列（只读 + 虚线下划线 + tooltip） -->
              <el-tooltip
                v-if="col.formula"
                :content="formulaHint(col.prop)"
                placement="top"
                :show-after="300"
              >
                <span class="formula-cell">{{ fmtNum(row[col.prop]) }}</span>
              </el-tooltip>

              <!-- 阶段划分下拉 -->
              <el-select
                v-else-if="col.type === 'stage'"
                :model-value="row[col.prop]"
                size="small"
                :disabled="isReadonly"
                @change="(v: string) => detail.updateRow(row.id, { [col.prop]: v })"
              >
                <el-option value="Stage1" label="Stage1" />
                <el-option value="Stage2" label="Stage2" />
                <el-option value="Stage3" label="Stage3" />
              </el-select>

              <!-- 投资种类下拉 -->
              <el-select
                v-else-if="col.type === 'select'"
                :model-value="row[col.prop]"
                size="small"
                :disabled="isReadonly"
                @change="(v: string) => detail.updateRow(row.id, { [col.prop]: v })"
              >
                <el-option v-for="opt in categoryOptions" :key="opt" :value="opt" :label="opt" />
              </el-select>

              <!-- 日期输入 -->
              <el-date-picker
                v-else-if="col.type === 'date'"
                :model-value="row[col.prop]"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                :disabled="isReadonly"
                style="width: 100%"
                @update:model-value="(v: string) => detail.updateRow(row.id, { [col.prop]: v ?? '' })"
              />

              <!-- 数值输入 -->
              <el-input-number
                v-else-if="col.type === 'number'"
                :model-value="row[col.prop]"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                style="width: 100%"
                :precision="4"
                @update:model-value="(v: number) => detail.updateRow(row.id, { [col.prop]: v ?? 0 })"
              />

              <!-- 文本输入 -->
              <el-input
                v-else
                :model-value="row[col.prop]"
                size="small"
                :disabled="isReadonly"
                @change="(v: string) => detail.updateRow(row.id, { [col.prop]: v })"
              />
            </template>
          </el-table-column>

          <!-- 操作列 -->
          <el-table-column label="操作" width="60" fixed="right">
            <template #default="{ row }">
              <el-button v-if="!isReadonly" size="small" type="danger" link @click="detail.removeRow(row.id)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </template>

    <!-- 底部：按投资种类分类小计 + 总计 -->
    <div class="totals">
      <div v-for="st in detail.subtotalsByCategory.value" :key="st.investCategory" class="subtotal-line">
        <span class="subtotal-label">{{ st.investCategory }}小计({{ st.count }})</span>
        面值 {{ fmtNum(st.totals.faceValue) }} ·
        期末小计 {{ fmtNum(st.totals.closingSubtotal) }} ·
        摊余成本 {{ fmtNum(st.totals.amortizedCost) }} ·
        账面价值 {{ fmtNum(st.totals.bookValue) }}
      </div>
      <div class="grand-total">
        <span class="subtotal-label">总计</span>
        面值 {{ fmtNum(detail.grandTotal.value.faceValue) }} ·
        期末小计 {{ fmtNum(detail.grandTotal.value.closingSubtotal) }} ·
        摊余成本 {{ fmtNum(detail.grandTotal.value.amortizedCost) }} ·
        账面价值 {{ fmtNum(detail.grandTotal.value.bookValue) }}
      </div>
    </div>

    <!-- 编制提示 -->
    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>期初小计 = 期初成本 + 期初利息调整 + 期初应计利息</li>
        <li>期初摊余成本 = 期初小计 - 期初减值准备</li>
        <li>本期变动小计 = 本期成本变动 + 本期利息调整变动 + 本期应计利息变动</li>
        <li>期末各项 = 期初对应项 + 本期变动对应项</li>
        <li>摊余成本 = 期末小计 - 减值准备期末数</li>
        <li>一年内到期小计 = 一年内到期账面余额 - 一年内到期减值</li>
        <li>期末账面价值 = 摊余成本 - 一年内到期小计</li>
        <li>数据分类按到期日与资产负债表日比较：到期日≤资产负债表日+1年归入"一年内到期"</li>
        <li>行数超过50行自动启用虚拟滚动优化性能</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G4TabDetail.vue — G4-2 债权投资明细表（44列→5区段Tab）
 *
 * Spec: .kiro/specs/g4-bond-investment-main/ Task 6.2
 * Requirements: 5.1, 5.12~5.17, 11.2, 11.5, 11.8
 *
 * 核心设计：
 * - Tab切换不销毁el-table实例，仅切换列定义(columns computed)
 * - 行数据共享同一reactive数组，5区段引用同一rows
 * - selectedRowIndex跨Tab同步（切换前后行索引不变）
 * - 行数>50启用虚拟滚动
 * - 公式列tooltip显示公式来源
 * - 新增行时空白名称阻止创建（composable内ElMessageBox.prompt + inputPattern）
 */
import { ref, computed, inject, onMounted, toRef } from 'vue'
import {
  useG4MainDetail,
  G4_INVEST_CATEGORY_OPTIONS,
  G4_DETAIL_SEGMENTS,
  type BondDetailRow,
  type G4DetailColumn,
} from '../../composables/useG4MainDetail'
import { useG4MainImportExport } from '../../composables/useG4MainImportExport'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// ─── 从 htmlData 中构建 allResponses Map ────────────────────────────────────
const allResponses = ref<Map<string, ChecklistResponse>>(new Map())

function hydrateFromHtmlData(): void {
  if (!props.htmlData) return
  const data = props.htmlData
  if (data.checklist_responses && typeof data.checklist_responses === 'object') {
    for (const [key, val] of Object.entries(data.checklist_responses)) {
      if (val && typeof val === 'object') {
        allResponses.value.set(key, val as ChecklistResponse)
      } else {
        allResponses.value.set(key, { item_id: key, conclusion: String(val ?? ''), remark: null })
      }
    }
  }
  if (data.responses && Array.isArray(data.responses)) {
    for (const item of data.responses) {
      if (item?.item_id) {
        allResponses.value.set(item.item_id, item)
      }
    }
  }
}

/** debouncedSave — persist via parent save mechanism */
function debouncedSave(itemId: string, data: Partial<ChecklistResponse>): void {
  allResponses.value.set(itemId, {
    item_id: itemId,
    conclusion: data.conclusion ?? null,
    remark: data.remark ?? null,
  })
}

onMounted(() => {
  hydrateFromHtmlData()
})

// ─── Composable ─────────────────────────────────────────────────────────────
const detail = useG4MainDetail({
  allResponses,
  debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as any,
})

// ─── 导入导出 ───────────────────────────────────────────────────────────────
const ie = useG4MainImportExport({ wpId: computed(() => props.wpId) })

function handleIECommand(cmd: string): void {
  if (cmd === 'template') ie.exportTemplate('G4-2')
  else if (cmd === 'export') ie.exportData('G4-2')
  // import handled by el-upload
}

async function onImportFile(f: { raw?: File } | File): Promise<void> {
  const file = f instanceof File ? f : (f.raw ?? null)
  if (!file) return
  await ie.importData('G4-2', file)
}

// ─── 区段选项（el-segmented） ────────────────────────────────────────────────
const segmentOptions = G4_DETAIL_SEGMENTS.map((s) => ({ label: s.label, value: s.key }))

const categoryOptions = G4_INVEST_CATEGORY_OPTIONS

// ─── 动态列（过滤掉已作为fixed列展示的序号和投资项目） ─────────────────────────
const activeColumnsFiltered = computed<G4DetailColumn[]>(() => {
  return detail.activeColumns.value.filter(
    (c) => c.prop !== 'seq' && c.prop !== 'investProject',
  )
})

// ─── 虚拟滚动：行数>50启用 ──────────────────────────────────────────────────
const enableVirtualScroll = computed<boolean>(() => detail.rows.value.length > 50)

// ─── 行选中同步（跨Tab同步 selectedRowIndex） ────────────────────────────────
function handleRowSelect(row: BondDetailRow | null, groupRows: BondDetailRow[]): void {
  if (!row) {
    detail.selectedRowIndex.value = -1
    return
  }
  // 行索引基于全局rows（非分组内rows）
  const globalIdx = detail.rows.value.findIndex((r) => r.id === row.id)
  detail.selectedRowIndex.value = globalIdx
}

function currentRowKey(groupRows: BondDetailRow[]): string | undefined {
  if (detail.selectedRowIndex.value < 0) return undefined
  const globalRow = detail.rows.value[detail.selectedRowIndex.value]
  if (!globalRow) return undefined
  // 仅当该行在当前分组中才高亮
  const found = groupRows.find((r) => r.id === globalRow.id)
  return found?.id
}

// ─── 公式列tooltip提示 ──────────────────────────────────────────────────────
const FORMULA_HINTS: Partial<Record<keyof BondDetailRow, string>> = {
  openingSubtotal: '期初小计 = 期初成本 + 期初利息调整 + 期初应计利息',
  openingAmortizedCost: '期初摊余成本 = 期初小计 - 期初减值准备',
  periodChangeSubtotal: '本期变动小计 = 成本变动 + 利息调整变动 + 应计利息变动',
  closingCost: '期末成本 = 期初成本 + 本期成本变动',
  closingInterestAdj: '期末利息调整 = 期初利息调整 + 本期利息调整变动',
  closingAccruedInterest: '期末应计利息 = 期初应计利息 + 本期应计利息变动',
  closingSubtotal: '期末小计 = 期末成本 + 期末利息调整 + 期末应计利息',
  amortizedCost: '摊余成本 = 期末小计 - 减值准备期末数',
  oneYearSubtotal: '一年内到期小计 = 一年内到期余额 - 一年内到期减值',
  bookValue: '期末账面价值 = 摊余成本 - 一年内到期小计',
}

function formulaHint(prop: keyof BondDetailRow): string {
  return FORMULA_HINTS[prop] ?? '公式计算列'
}

// ─── 格式化 ──────────────────────────────────────────────────────────────────
function fmtNum(v: unknown): string {
  if (v == null) return ''
  const n = Number(v)
  if (!Number.isFinite(n)) return ''
  return n.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}
</script>

<style scoped>
.g4-detail { padding: 12px; font-size: 13px; }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; }
.balance-date-bar { margin-bottom: 10px; display: flex; align-items: center; gap: 8px; }
.date-label { font-size: 13px; color: #606266; }
.segment-bar { margin-bottom: 12px; }
.category-group { margin-bottom: 16px; }
.category-title { font-size: 13px; font-weight: 600; color: #303133; margin-bottom: 8px; padding: 4px 8px; background: #f5f7fa; border-left: 3px solid #409eff; }
.detail-table { font-size: 13px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; display: inline-block; min-width: 40px; text-align: right; }
.totals { margin-top: 12px; font-size: 12px; color: #606266; }
.subtotal-line { padding: 2px 0; }
.subtotal-label { font-weight: 600; margin-right: 8px; }
.grand-total { margin-top: 6px; padding-top: 6px; border-top: 1px solid #dcdfe6; font-weight: 600; color: #303133; }
.prep-hint { margin-top: 16px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; font-weight: 500; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
</style>
