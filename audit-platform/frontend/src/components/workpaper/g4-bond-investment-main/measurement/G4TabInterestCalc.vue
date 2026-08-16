<template>
  <div class="g4-tab-interest-calc">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="审计目标：确认债权投资利息收入按实际利率法计算准确，实际利率与票面利率差异合理，测算合计与 G4-1 审定利息收入一致。"
      style="margin-bottom: 12px"
    />
    <!-- Section标题栏 + 新增投资项目 + 复核按钮 -->
    <div class="section-head">
      <h3 class="sheet-title">G4-4 利息收入测算表（实际利率法）</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="calc.addGroup()">
          + 新增投资项目
        </el-button>
        <el-button size="small" type="success" plain :disabled="isReadonly" @click="calc.confirmInterestWriteback()">
          预览并回写 G4-2/G4-3
        </el-button>
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
        <el-button size="small" @click="openReview">💬复核</el-button>
      </div>
    </div>

    <!-- 工具栏：索引 chip + 项目数 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G4-4" :context-project-id="props.projectId" /></span>
        <el-tag size="small" type="info">共 {{ calc.computedGroups.value.length }} 个项目</el-tag>
      </div>
    </div>

    <!-- 无分组占位 -->
    <el-empty v-if="calc.computedGroups.value.length === 0" description="暂无投资项目，点击“新增投资项目”开始" />

    <!-- 利率合理性告警 -->
    <el-alert
      v-if="calc.hasRateWarnings.value"
      type="warning"
      :closable="false"
      style="margin-bottom: 12px"
    >
      <template #title>
        <span>⚠️ 利率合理性提示（{{ calc.rateWarnings.value.length }}项）</span>
      </template>
      <ul style="margin: 4px 0 0; padding-left: 18px; font-size: 12px; line-height: 1.8">
        <li v-for="w in calc.rateWarnings.value" :key="w.groupId">{{ w.message }}</li>
      </ul>
    </el-alert>

    <!-- 各投资项目分组 -->
    <div
      v-for="group in calc.computedGroups.value"
      :key="group.id"
      class="interest-group"
    >
      <!-- 分组标题栏 -->
      <div class="group-header">
        <span class="group-title">══ {{ group.projectName }} ══</span>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="danger"
          link
          @click="handleRemoveGroup(group.id, group.projectName)"
        >
          🗑️ 删除该项目
        </el-button>
      </div>

      <!-- (一) 确定初始入账价值 (9列, 1行) -->
      <div class="section-sub-title">(一) 确定初始入账价值</div>
      <el-table :data="[group.initial]" border size="small" class="initial-table">
        <el-table-column label="投资项目" width="130">
          <template #default>
            <span>{{ group.projectName }}</span>
          </template>
        </el-table-column>

        <el-table-column label="面值总额" width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="row.faceValueTotal"
              size="small"
              style="width:100%"
              @change="(v: number | undefined) => calc.updateInitialField(group.id, 'faceValueTotal', v ?? 0)"
            />
            <span v-else>{{ fmt(row.faceValueTotal) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="初始计量日" width="130">
          <template #default="{ row }">
            <el-date-picker
              v-if="!isReadonly"
              :model-value="row.initialDate"
              type="date"
              size="small"
              value-format="YYYY-MM-DD"
              style="width:100%"
              @update:model-value="(v: string) => calc.updateInitialField(group.id, 'initialDate', v ?? '')"
            />
            <span v-else>{{ row.initialDate }}</span>
          </template>
        </el-table-column>

        <el-table-column label="到期日" width="130">
          <template #default="{ row }">
            <el-date-picker
              v-if="!isReadonly"
              :model-value="row.maturityDate"
              type="date"
              size="small"
              value-format="YYYY-MM-DD"
              style="width:100%"
              @update:model-value="(v: string) => calc.updateInitialField(group.id, 'maturityDate', v ?? '')"
            />
            <span v-else>{{ row.maturityDate }}</span>
          </template>
        </el-table-column>

        <el-table-column label="购买对价" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.purchasePrice"
              size="small"
              :controls="false"
              :precision="2"
              style="width:100%"
              @change="(v: number | undefined) => calc.updateInitialField(group.id, 'purchasePrice', v ?? 0)"
            />
            <span v-else>{{ fmt(row.purchasePrice) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="交易费用" width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="row.transactionCost"
              size="small"
              style="width:100%"
              @change="(v: number | undefined) => calc.updateInitialField(group.id, 'transactionCost', v ?? 0)"
            />
            <span v-else>{{ fmt(row.transactionCost) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="初始入账价值" width="130" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="初始入账价值 = 购买对价 + 交易费用">
              {{ fmt(row.initialCarryingAmount) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="票面利率" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.couponRate"
              size="small"
              :controls="false"
              :precision="6"
              :step="0.001"
              style="width:100%"
              @change="(v: number | undefined) => calc.updateInitialField(group.id, 'couponRate', v ?? 0)"
            />
            <span v-else>{{ fmtRate(row.couponRate) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="实际利率" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.effectiveRate"
              size="small"
              :controls="false"
              :precision="6"
              :step="0.001"
              style="width:100%"
              @change="(v: number | undefined) => calc.updateInitialField(group.id, 'effectiveRate', v ?? 0)"
            />
            <span v-else>{{ fmtRate(row.effectiveRate) }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- (二) 计算利息收入 (10列, 多行=多计息期间) -->
      <div class="section-sub-title section-two-head">
        <span>(二) 计算利息收入</span>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="success"
          link
          @click="calc.addPeriod(group.id)"
        >
          + 新增计息期间
        </el-button>
      </div>

      <el-table :data="group.periods" border size="small" class="periods-table">
        <el-table-column label="截止日" width="130">
          <template #default="{ row }">
            <el-date-picker
              v-if="!isReadonly"
              :model-value="row.cutoffDate"
              type="date"
              size="small"
              value-format="YYYY-MM-DD"
              style="width:100%"
              @update:model-value="(v: string) => calc.updatePeriodField(group.id, row.id, 'cutoffDate', v ?? '')"
            />
            <span v-else>{{ row.cutoffDate }}</span>
          </template>
        </el-table-column>

        <el-table-column label="期初账面总额" width="130" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="row.openingBalance"
              size="small"
              style="width:100%"
              @change="(v: number | undefined) => calc.updatePeriodField(group.id, row.id, 'openingBalance', v ?? 0)"
            />
            <span v-else>{{ fmt(row.openingBalance) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="期初减值准备" width="130" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="row.openingImpairment"
              size="small"
              style="width:100%"
              @change="(v: number | undefined) => calc.updatePeriodField(group.id, row.id, 'openingImpairment', v ?? 0)"
            />
            <span v-else>{{ fmt(row.openingImpairment) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="期初摊余成本" width="130" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="期初摊余成本 = 期初账面总额 - 期初减值准备">
              {{ fmt(row.openingAmortizedCost) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="实际利息收入" width="130" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="实际利息收入 = 期初摊余成本 × 实际利率 × 计息天数/365">
              {{ fmt(row.effectiveInterest) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="现金流入" width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="现金流入 = 面值总额 × 票面利率 × 计息天数/365">
              {{ fmt(row.cashInflow) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="已收回本金" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.principalRepaid"
              size="small"
              :controls="false"
              :precision="2"
              style="width:100%"
              @change="(v: number | undefined) => calc.updatePeriodField(group.id, row.id, 'principalRepaid', v ?? 0)"
            />
            <span v-else>{{ fmt(row.principalRepaid) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="期末账面总额" width="130" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="期末账面总额 = 期初账面 + 实际利息 - 现金流入 - 已收回本金">
              {{ fmt(row.closingBalance) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="计息天数" width="100" align="center">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.days"
              size="small"
              :controls="false"
              :min="1"
              :max="366"
              style="width:100%"
              @change="(v: number | undefined) => calc.updatePeriodField(group.id, row.id, 'days', v ?? 365)"
            />
            <span v-else>{{ row.days }}</span>
          </template>
        </el-table-column>

        <!-- 操作列：删除计息期间行 -->
        <el-table-column v-if="!isReadonly" label="" width="50" align="center">
          <template #default="{ row }">
            <el-button
              size="small"
              type="danger"
              link
              :disabled="group.periods.length <= 1"
              @click="calc.removePeriod(group.id, row.id)"
            >
              删
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 底部：合计对比行 -->
    <div v-if="calc.computedGroups.value.length > 0" class="summary-section">
      <div class="summary-compare" :class="{ 'variance-alert': calc.isVarianceHighlight() }">
        <span class="summary-label">合计对比</span>
        <span class="summary-item">
          利息测算合计：<strong>{{ fmt(calc.summary.value.totalEffectiveInterest) }}</strong>
        </span>
        <span class="summary-item summary-benchmark">
          审定利息收入基准：
          <el-input-number
            v-if="!isReadonly"
            :model-value="calc.summary.value.g4_1InterestAdjusted"
            size="small"
            :controls="false"
            :precision="2"
            style="width:140px"
            @change="(v: number | undefined) => calc.setInterestBenchmark(v ?? 0)"
          />
          <strong v-else>{{ fmt(calc.summary.value.g4_1InterestAdjusted) }}</strong>
        </span>
        <span class="summary-item" :class="{ 'red-highlight': calc.isVarianceHighlight() }">
          差异：<strong>{{ fmt(calc.summary.value.variance) }}</strong>
          <template v-if="calc.isVarianceHighlight()"> 超差 &gt;0.01</template>
        </span>
      </div>

      <details class="g4-guide-details">
        <summary>编制提示</summary>
        <div class="g4-guide-content">
          <p>1. 对齐 Excel《利息收入测算表》：（一）初始入账价值；（二）计算利息收入（9列，无减值阶段列）。</p>
          <p>2. 实际利息收入 = 期初摊余成本 × 实际利率 × 计息天数/365；期初摊余成本 = 期初账面 − 减值准备。</p>
          <p>3. 首期期初账面默认=初始入账价值；后续期间期初在未填时自动按上期期末倒轧。</p>
          <p>4. 期末账面总额 = 期初账面 + 实际利息 − 现金流入 − 已收回本金。</p>
          <p>5. 测算合计应与审定利息收入基准勾稽（可手填，或自动引用 G4-3 中 6011 账项调整净额），|差异|≤0.01。</p>
          <p>6. 利率精度建议≥4位小数；实际利率与票面利率相差&gt;2% 时给出提示。</p>
        </div>
      </details>
    </div>

    <G4AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="auditConclusion"
      note-ai-section="interest-note"
      conclusion-ai-section="interest-conclusion"
      :related-context="{
        投资项目数: calc.computedGroups.value.length,
        测算利息合计: calc.summary.value.totalEffectiveInterest,
        审定利息: calc.summary.value.g4_1InterestAdjusted,
        差异: calc.summary.value.variance,
      }"
      note-placeholder="填写审计说明：实际利率法利息测算的执行情况、利率合理性判断与测算差异分析结果。"
      note-hint="覆盖实际利率法测算程序与差异分析。"
      conclusion-hint="按 A/B/C 口径评价利息收入确认准确性。"
    />
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * G4TabInterestCalc.vue — G4-4 利息测算表（实际利率法双section分组）
 *
 * Spec: .kiro/specs/g4-bond-investment-main/ Task 6.4
 * Requirements: 7.1~7.11, 11.1~11.5
 *
 * 功能：
 * - 每个投资项目独立成组，组间分隔线+标题
 * - (一)确定初始入账价值(9列) + (二)计算利息收入(10列，多行=多计息期间)
 * - 减值阶段Stage下拉选择(Stage1/Stage2/Stage3)
 * - 底部：合计对比行 + 审计结论textarea(AI按钮) + 编制提示details折叠
 * - 新增投资项目ElMessageBox.prompt输入名称
 * - section(二)支持动态行增删
 *
 * 使用 useG4MainInterestCalc composable（已实现）
 */
import { ref, computed, watch, inject, onMounted } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useG4MainInterestCalc } from '../../composables/useG4MainInterestCalc'
import { useG4MainImportExport } from '../../composables/useG4MainImportExport'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtIndexChip from '../../GtIndexChip.vue'
import G4AuditTextCards from '../G4AuditTextCards.vue'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses?: Map<string, ChecklistResponse>
}>()

const emit = defineEmits<{ imported: [] }>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// ─── allResponses：优先使用父级共享 Map ───
const allResponses = ref<Map<string, ChecklistResponse>>(new Map())

watch(
  () => props.allResponses,
  (source) => {
    if (!source) return
    allResponses.value = source
  },
  { immediate: true, deep: true },
)

// ─── seed from htmlData（仅在父级未提供数据时） ───
if ((!props.allResponses || props.allResponses.size === 0) && props.htmlData?.interestCalc) {
  const seed = props.htmlData.interestCalc
  if (seed.groups) {
    allResponses.value.set('G4-4-interest-calc', {
      item_id: 'G4-4-interest-calc',
      conclusion: seed.conclusion || null,
      remark: JSON.stringify(seed.groups),
    })
  }
}

// ─── 初始化 composable ───
const isReadonlyRef = ref(props.isReadonly)
watch(() => props.isReadonly, (v) => { isReadonlyRef.value = v })
const calc = useG4MainInterestCalc({
  allResponses,
  isReadonly: isReadonlyRef,
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── 导入导出 ───
const ie = useG4MainImportExport({ wpId: computed(() => props.wpId) })

function handleIECommand(cmd: string): void {
  if (cmd === 'template') ie.exportTemplate('G4-4')
  else if (cmd === 'export') ie.exportData('G4-4')
}

async function onImportFile(f: { raw?: File } | File): Promise<void> {
  const file = f instanceof File ? f : (f.raw ?? null)
  if (!file) return
  const result = await ie.importData('G4-4', file)
  if (result) {
    emit('imported')
    window.setTimeout(() => calc.loadGroups(), 80)
  }
}

// ─── 审计结论 / 说明 ───
const CONCLUSION_KEY = 'G4-4-interestcalc-audit-conclusion'
const NOTE_KEY = 'G4-4-interestcalc-audit-note'
const auditConclusion = ref('')
const auditNote = ref('')

function readSaved(key: string): string {
  const cr = props.htmlData?.checklist_responses
  if (cr && typeof cr === 'object' && (cr as Record<string, any>)[key]) {
    const v = (cr as Record<string, any>)[key]
    return typeof v === 'object' ? (v.remark ?? '') : String(v ?? '')
  }
  const resp = props.htmlData?.responses
  if (Array.isArray(resp)) {
    const found = resp.find((r: any) => r?.item_id === key)
    if (found?.remark) return found.remark
  }
  return ''
}

/** debouncedSave — 经 g4:save-items 由父组件落库 */
function debouncedSave(itemId: string, data: Partial<ChecklistResponse>): void {
  if (props.isReadonly) return
  const item: ChecklistResponse = {
    item_id: itemId,
    conclusion: data.conclusion ?? null,
    remark: data.remark ?? null,
  }
  allResponses.value.set(itemId, item)
  try {
    window.dispatchEvent(new CustomEvent('g4:save-items', { detail: { items: [item] } }))
  } catch { /* silent */ }
}

watch(auditNote, (val) => {
  debouncedSave(NOTE_KEY, { conclusion: null, remark: val })
})
watch(auditConclusion, (val) => {
  debouncedSave(CONCLUSION_KEY, { conclusion: null, remark: val })
})

onMounted(() => {
  auditNote.value = readSaved(NOTE_KEY)
  auditConclusion.value = readSaved(CONCLUSION_KEY)
})

// ─── 事件处理 ───

/** 打开复核对话 */
function openReview(): void {
  openReviewDialog('G4-4-interest-calc')
}

/** 删除投资项目确认 */
async function handleRemoveGroup(groupId: string, projectName: string): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确认删除投资项目"${projectName}"及其所有计息期间数据？`,
      '删除确认',
      {
        confirmButtonText: '确认删除',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
    calc.removeGroup(groupId)
  } catch {
    // 用户取消
  }
}

/** 格式化金额 */
function fmt(v: number | null | undefined): string {
  if (v == null) return '-'
  if (v === 0) return '0.00'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/** 格式化利率 (小数→百分比展示) */
function fmtRate(v: number | null | undefined): string {
  if (v == null || v === 0) return '-'
  return `${(v * 100).toFixed(4)}%`
}
</script>

<style scoped>
.g4-tab-interest-calc {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.sheet-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* 工具栏（索引 chip） */
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.tab-toolbar .toolbar-left { display: flex; gap: 8px; align-items: center; }
.tab-toolbar .toolbar-right { display: flex; gap: 6px; align-items: center; }
.tab-toolbar .chip-wrap { display: inline-flex; align-items: center; }

/* 审计说明卡片 */
.audit-note-card { margin-top: 12px; }
.audit-note-card .card-header { display: flex; align-items: center; justify-content: space-between; font-weight: 500; }

/* ─── 分组样式 ─── */
.interest-group {
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 2px solid #e4e7ed;
}

.interest-group:last-child {
  border-bottom: none;
}

.group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  padding: 8px 12px;
  background: linear-gradient(90deg, #ecf5ff, #f0f9ff);
  border-radius: 4px;
  border-left: 4px solid #409eff;
}

.group-title {
  font-weight: 700;
  font-size: 14px;
  color: #303133;
}

/* ─── Section子标题 ─── */
.section-sub-title {
  font-weight: 600;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  margin: 10px 0 6px;
  padding-left: 4px;
}

.section-two-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* ─── 表格 ─── */
.initial-table,
.periods-table {
  width: 100%;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 公式单元格 ─── */
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  font-weight: 600;
  color: #303133;
}

/* ─── 合计对比区域 ─── */
.summary-section {
  margin-top: 16px;
}

.summary-compare {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 16px;
  padding: 10px 16px;
  background: #f0f9eb;
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
  border: 1px solid #e1f3d8;
}

.summary-compare.variance-alert {
  background: #fef0f0;
  border: 1px solid #f56c6c;
}

.summary-label {
  font-weight: 700;
  color: #606266;
}

.summary-item {
  color: #303133;
}

.red-highlight {
  color: #f56c6c;
  font-weight: 700;
}

/* ─── 审计结论卡片 ─── */
.conclusion-card {
  margin-top: 12px;
}

.conclusion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}

/* ─── 编制提示 ─── */
.g4-guide-details {
  margin-top: 16px;
}

.g4-guide-details summary {
  cursor: pointer;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  font-weight: 600;
}

.g4-guide-content {
  padding: 8px 12px;
  background: #fffbeb;
  border-left: 3px solid #f59e0b;
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.8;
}

.g4-guide-content p {
  margin: 0;
}
</style>
