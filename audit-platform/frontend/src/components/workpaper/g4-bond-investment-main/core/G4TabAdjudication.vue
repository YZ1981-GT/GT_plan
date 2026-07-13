<template>
  <div class="g4-adjudication">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="审计目标：确认债权投资期末余额（成本、利息调整、应计利息、减值准备、摊余成本）真实、准确、完整，审定数与试算平衡表勾稽一致。"
      style="margin-bottom: 12px"
    />
    <!-- Section 标题栏 -->
    <div class="section-head">
      <h3 class="sheet-title">G4-1 债权投资审定表</h3>
      <div class="head-actions">
        <el-button size="small" @click="openReviewDialog('G4-1-adjudication')">💬复核</el-button>
      </div>
    </div>

    <!-- 工具栏：索引 chip -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G4-1" :context-project-id="props.projectId" /></span>
      </div>
    </div>

    <!-- 三层分组表格 -->
    <template v-for="group in adj.groups.value" :key="group.groupKey">
      <!-- 分组标题行（含展开/折叠控制） -->
      <div class="group-header" @click="toggleGroup(group.groupKey)">
        <el-icon class="collapse-icon" :class="{ 'is-collapsed': !expandedMap[group.groupKey] }">
          <ArrowDown />
        </el-icon>
        <span class="group-name">{{ group.groupName }}</span>
      </div>

      <!-- 分组内容（数据行 + 小计行） -->
      <div v-show="expandedMap[group.groupKey]" class="group-body">
        <el-table
          v-if="group.rows.length > 0 || group.subtotal"
          :data="getGroupTableData(group)"
          border
          size="small"
          :max-height="400"
          :row-class-name="rowClassName"
          class="adj-table"
        >
          <!-- 项目列 -->
          <el-table-column label="项目" width="160" fixed>
            <template #default="{ row }">
              <span :class="{ 'row-bold': row.isSubtotal }">{{ row.item }}</span>
            </template>
          </el-table-column>

          <!-- 期初(未审/AJE/RJE/审定) -->
          <el-table-column label="期初" align="center">
            <el-table-column label="未审" width="110" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="row.isEditable && !isReadonly"
                  :model-value="row.openingUnadjusted"
                  size="small" :controls="false"
                  style="width:100%"
                  @update:model-value="(v: number) => handleCellUpdate(group.groupKey, row.id, 'openingUnadjusted', v)"
                />
                <span v-else :class="{ 'row-bold': row.isSubtotal }">{{ fmt(row.openingUnadjusted) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="AJE" width="100" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="row.isEditable && !isReadonly"
                  :model-value="row.openingAJE"
                  size="small" :controls="false"
                  style="width:100%"
                  @update:model-value="(v: number) => handleCellUpdate(group.groupKey, row.id, 'openingAJE', v)"
                />
                <span v-else :class="{ 'row-bold': row.isSubtotal }">{{ fmt(row.openingAJE) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="RJE" width="100" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="row.isEditable && !isReadonly"
                  :model-value="row.openingRJE"
                  size="small" :controls="false"
                  style="width:100%"
                  @update:model-value="(v: number) => handleCellUpdate(group.groupKey, row.id, 'openingRJE', v)"
                />
                <span v-else :class="{ 'row-bold': row.isSubtotal }">{{ fmt(row.openingRJE) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="审定" width="120" align="right">
              <template #default="{ row }">
                <span
                  :class="{ 'row-bold': row.isSubtotal, 'formula-cell': !row.isSubtotal }"
                  :title="!row.isSubtotal ? '期初审定 = 期初未审 + AJE + RJE' : ''"
                >{{ fmt(row.openingAdjusted) }}</span>
              </template>
            </el-table-column>
          </el-table-column>

          <!-- 期末(未审/AJE/RJE/审定) -->
          <el-table-column label="期末" align="center">
            <el-table-column label="未审" width="120" align="right">
              <template #default="{ row }">
                <span
                  :class="{ 'row-bold': row.isSubtotal, 'formula-cell': !row.isSubtotal }"
                  :title="!row.isSubtotal ? '期末未审 = 期初审定 + 借方 - 贷方' : ''"
                >{{ fmt(row.closingUnadjusted) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="AJE" width="100" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="row.isEditable && !isReadonly"
                  :model-value="row.closingAJE"
                  size="small" :controls="false"
                  style="width:100%"
                  @update:model-value="(v: number) => handleCellUpdate(group.groupKey, row.id, 'closingAJE', v)"
                />
                <span v-else :class="{ 'row-bold': row.isSubtotal }">{{ fmt(row.closingAJE) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="RJE" width="100" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="row.isEditable && !isReadonly"
                  :model-value="row.closingRJE"
                  size="small" :controls="false"
                  style="width:100%"
                  @update:model-value="(v: number) => handleCellUpdate(group.groupKey, row.id, 'closingRJE', v)"
                />
                <span v-else :class="{ 'row-bold': row.isSubtotal }">{{ fmt(row.closingRJE) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="审定" width="120" align="right">
              <template #default="{ row }">
                <span
                  :class="{ 'row-bold': row.isSubtotal, 'formula-cell': !row.isSubtotal }"
                  :title="!row.isSubtotal ? '期末审定 = 期末未审 + AJE + RJE' : ''"
                >{{ fmt(row.closingAdjusted) }}</span>
              </template>
            </el-table-column>
          </el-table-column>

          <!-- 变动额 -->
          <el-table-column label="变动额" width="110" align="right">
            <template #default="{ row }">
              <span
                :class="{ 'row-bold': row.isSubtotal, 'formula-cell': !row.isSubtotal }"
                :title="!row.isSubtotal ? '变动额 = 期末审定 - 期初审定' : ''"
              >{{ fmt(row.changeAmount) }}</span>
            </template>
          </el-table-column>

          <!-- 变动率 -->
          <el-table-column label="变动率" width="100" align="right">
            <template #default="{ row }">
              <span
                :class="[
                  { 'row-bold': row.isSubtotal, 'formula-cell': !row.isSubtotal },
                  { 'rate-orange': isRateWarning(row.changeRate) },
                ]"
                :title="!row.isSubtotal ? '变动率 = (期末审定 - 期初审定) / 期初审定' : ''"
              >{{ fmtRate(row.changeRate) }}</span>
            </template>
          </el-table-column>

          <!-- 原因分析 -->
          <el-table-column label="原因分析" min-width="140">
            <template #default="{ row }">
              <el-input
                v-if="row.isEditable && !isReadonly"
                :model-value="row.reasonAnalysis"
                size="small"
                :class="{ 'reason-required': isRateWarning(row.changeRate) && !row.reasonAnalysis }"
                :placeholder="isRateWarning(row.changeRate) ? '变动率>20%，必填' : ''"
                @change="(v: string) => handleCellUpdate(group.groupKey, row.id, 'reasonAnalysis', v)"
              />
              <span v-else>{{ row.reasonAnalysis }}</span>
            </template>
          </el-table-column>

          <!-- 索引 -->
          <el-table-column label="索引" width="90">
            <template #default="{ row }">
              <template v-if="row.isEditable && !isReadonly">
                <el-input
                  :model-value="row.indexRef"
                  size="small"
                  @change="(v: string) => handleCellUpdate(group.groupKey, row.id, 'indexRef', v)"
                />
              </template>
              <GtIndexChip v-else-if="row.indexRef" :value="row.indexRef" />
            </template>
          </el-table-column>
        </el-table>

        <!-- 一年内到期行（仅原值组有） -->
        <div v-if="group.oneYearDeduct" class="one-year-row">
          <el-table :data="[group.oneYearDeduct]" border size="small" class="adj-table">
            <el-table-column label="项目" width="160" fixed>
              <template #default="{ row }">
                <span class="row-italic">{{ row.item }}</span>
              </template>
            </el-table-column>
            <el-table-column label="期初" align="center">
              <el-table-column label="审定" width="120" align="right">
                <template #default="{ row }">
                  <el-input-number
                    v-if="!isReadonly"
                    :model-value="row.openingAdjusted"
                    size="small" :controls="false" style="width:100%"
                    @update:model-value="(v: number) => adj.updateOneYearRow('openingAdjusted', v ?? 0)"
                  />
                  <span v-else>{{ fmt(row.openingAdjusted) }}</span>
                </template>
              </el-table-column>
            </el-table-column>
            <el-table-column label="期末" align="center">
              <el-table-column label="审定" width="120" align="right">
                <template #default="{ row }">
                  <el-input-number
                    v-if="!isReadonly"
                    :model-value="row.closingAdjusted"
                    size="small" :controls="false" style="width:100%"
                    @update:model-value="(v: number) => adj.updateOneYearRow('closingAdjusted', v ?? 0)"
                  />
                  <span v-else>{{ fmt(row.closingAdjusted) }}</span>
                </template>
              </el-table-column>
            </el-table-column>
            <el-table-column label="变动额" width="110" align="right">
              <template #default="{ row }">
                <span class="formula-cell" title="变动额 = 期末审定 - 期初审定">{{ fmt(row.changeAmount) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="变动率" width="100" align="right">
              <template #default="{ row }">
                <span class="formula-cell" title="变动率 = (期末-期初) / 期初">{{ fmtRate(row.changeRate) }}</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>
    </template>

    <!-- 一年内到期非流动资产列报数 -->
    <div class="one-year-maturity-section">
      <div class="group-header static">
        <span class="group-name">附加：一年内到期非流动资产列报数</span>
      </div>
      <el-table :data="[adj.oneYearMaturityRow.value]" border size="small" class="adj-table">
        <el-table-column label="项目" width="160" fixed>
          <template #default="{ row }"><span>{{ row.item }}</span></template>
        </el-table-column>
        <el-table-column label="期初审定" width="120" align="right">
          <template #default="{ row }">
            <span>{{ fmt(row.openingAdjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末审定" width="120" align="right">
          <template #default="{ row }">
            <span>{{ fmt(row.closingAdjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动额" width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="变动额 = 期末审定 - 期初审定">{{ fmt(row.changeAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动率" width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="变动率 = (期末-期初) / 期初">{{ fmtRate(row.changeRate) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 试算表数 + 差异 -->
    <div class="tb-diff-row">
      <span class="tb-label">试算平衡表数（科目1501）：</span>
      <span class="tb-amount">{{ fmt(adj.trialBalanceAmount.value) }}</span>
      <span :class="['diff-value', { 'diff-red': adj.hasVarianceHighlight.value }]">
        差异（审定-试算）：{{ fmt(adj.variance.value) }}
        <template v-if="!adj.hasVarianceHighlight.value"> ✓</template>
        <template v-else> ✗</template>
      </span>
    </div>

    <!-- 审计说明 -->
    <el-card class="note-card" shadow="never">
      <template #header>
        <div class="card-header"><span>审计说明</span></div>
      </template>
      <el-input
        v-model="adj.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="对债权投资审定表的审计说明..."
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card class="note-card" shadow="never">
      <template #header>
        <div class="card-header"><span>审计结论</span></div>
      </template>
      <el-input
        v-model="adj.auditConclusion.value"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="审计结论..."
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表为借方科目（资产类），期末未审 = 期初审定 + 借方发生额 - 贷方发生额</p>
        <p>2. 审定数 = 未审数 + 审计调整(AJE) + 重分类(RJE)</p>
        <p>3. 摊余成本 = 原值小计 - 减值小计</p>
        <p>4. 变动率超过20%需填写原因分析</p>
        <p>5. 差异 = 审定数（三、摊余成本行期末审定）- 试算表数</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G4TabAdjudication.vue — G4-1 债权投资审定表
 *
 * 三层结构：原值/减值/摊余成本，借方科目公式
 * EventBus publish substantive:adjudicated(accountCode='1501')
 * 展开/折叠分组（默认展开）
 * 公式列虚线下划线+cursor:help+tooltip
 * |变动率|>20%橙色高亮+原因分析必填
 * 差异≠0红色高亮
 * GtIndexChip索引列跳转
 * section标题栏右侧复核按钮（inject openReviewDialog）
 *
 * Spec: .kiro/specs/g4-bond-investment-main/ Req 3.1~3.13, 9.4, 11.1~11.4
 */
import { ref, reactive, computed, toRef, inject, onMounted } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'
import { useG4MainAdjudication } from '../../composables/useG4MainAdjudication'
import type { AdjudicationGroup, G4AdjudicationRow } from '../../composables/useG4MainAdjudication'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtIndexChip from '../../GtIndexChip.vue'

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
  // htmlData可能包含 checklist_responses 或 adj_data 等结构
  if (data.checklist_responses && typeof data.checklist_responses === 'object') {
    for (const [key, val] of Object.entries(data.checklist_responses)) {
      if (val && typeof val === 'object') {
        allResponses.value.set(key, val as ChecklistResponse)
      } else {
        allResponses.value.set(key, { item_id: key, conclusion: null, remark: String(val ?? '') })
      }
    }
  }
  // 直接键值对形式
  if (data.responses && Array.isArray(data.responses)) {
    for (const item of data.responses) {
      if (item?.item_id) {
        allResponses.value.set(item.item_id, item)
      }
    }
  }
}

onMounted(() => {
  hydrateFromHtmlData()
  adj.fetchTrialBalance()
})

// ─── composable ─────────────────────────────────────────────────────────────
const adj = useG4MainAdjudication({
  wpId: toRef(props, 'wpId') as any,
  projectId: toRef(props, 'projectId') as any,
  allResponses: allResponses,
  isReadonly: toRef(props, 'isReadonly') as any,
})

// ─── 展开/折叠状态（默认展开） ──────────────────────────────────────────────
const expandedMap = reactive<Record<string, boolean>>({
  'original-value': true,
  'impairment': true,
  'amortized-cost': true,
})

function toggleGroup(groupKey: string): void {
  expandedMap[groupKey] = !expandedMap[groupKey]
}

// ─── 表格数据组装（数据行 + 小计行合并） ─────────────────────────────────────
function getGroupTableData(group: AdjudicationGroup): G4AdjudicationRow[] {
  const rows: G4AdjudicationRow[] = [...group.rows]
  if (group.subtotal) {
    rows.push(group.subtotal)
  }
  return rows
}

// ─── 编辑处理 ────────────────────────────────────────────────────────────────
function handleCellUpdate(groupKey: string, rowKey: string, field: string, value: number | string): void {
  adj.updateCell(groupKey, rowKey, field, value ?? 0)
}

// ─── 行样式 ──────────────────────────────────────────────────────────────────
function rowClassName({ row }: { row: G4AdjudicationRow }): string {
  if (row.isSubtotal) return 'row-subtotal'
  return ''
}

// ─── 变动率阈值判断 ──────────────────────────────────────────────────────────
function isRateWarning(rate: number | null): boolean {
  if (rate === null || rate === undefined) return false
  return Math.abs(rate) > 0.2
}

// ─── 格式化 ──────────────────────────────────────────────────────────────────
function fmt(v: number | null | undefined): string {
  if (v == null) return ''
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function fmtRate(v: number | null | undefined): string {
  if (v == null) return '-'
  return (v * 100).toFixed(2) + '%'
}

const isReadonly = computed(() => props.isReadonly)
</script>

<style scoped>
.g4-adjudication { padding: 12px; font-size: var(--wp-font-size, 13px); }

/* Section 标题栏 */
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; }

/* 工具栏（索引 chip） */
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.tab-toolbar .toolbar-left { display: flex; gap: 8px; align-items: center; }
.tab-toolbar .toolbar-right { display: flex; gap: 6px; align-items: center; }
.tab-toolbar .chip-wrap { display: inline-flex; align-items: center; }

/* 分组标题 */
.group-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: #ecf5ff;
  border: 1px solid #d9ecff;
  border-radius: 4px;
  margin-top: 12px;
  cursor: pointer;
  user-select: none;
  transition: background 0.2s;
}
.group-header:hover { background: #d9ecff; }
.group-header.static { cursor: default; }
.group-header.static:hover { background: #ecf5ff; }
.group-name { font-weight: 600; font-size: var(--wp-font-size, 13px); color: #303133; }
.collapse-icon { transition: transform 0.2s; font-size: 14px; }
.collapse-icon.is-collapsed { transform: rotate(-90deg); }

/* 分组内容 */
.group-body { margin-bottom: 4px; }

/* 表格 */
.adj-table { margin-top: 4px; }

/* 公式列样式 */
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }

/* 行样式 */
.row-bold { font-weight: 700; }
.row-italic { font-style: italic; color: #606266; }
:deep(.row-subtotal) { background: #f5f7fa !important; font-weight: 700; }

/* 变动率橙色高亮 */
.rate-orange { color: #e6a23c; font-weight: 600; }

/* 原因分析必填提示 */
:deep(.reason-required .el-input__wrapper) {
  box-shadow: 0 0 0 1px #e6a23c inset;
}

/* 一年内到期行 */
.one-year-row { margin-top: 4px; padding-left: 16px; }
.one-year-maturity-section { margin-top: 8px; }

/* 试算表差异行 */
.tb-diff-row { display: flex; gap: 16px; margin: 16px 0; align-items: center; font-size: var(--wp-font-size, 13px); }
.tb-label { font-weight: 500; color: #606266; }
.tb-amount { font-weight: 600; }
.diff-value { font-weight: 600; }
.diff-red { color: #f56c6c; }

/* 审计说明/结论卡片 */
.note-card { margin-top: 12px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }

/* 编制提示 */
.guidance-details {
  margin-top: 16px;
  padding: 8px 12px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  font-size: 12px;
  color: #606266;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
}
.guidance-content p { margin: 4px 0; }
</style>
