<template>
  <div class="g6-tab-interest-calculation">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：验证其他债权投资按实际利率法确认利息收入的准确性，核实实际利率确定的合理性与摊余成本逐期结转的正确性。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button
          v-if="!isReadonly"
          size="small"
          type="success"
          plain
          :loading="syncing"
          @click="syncFromMain"
        >
          从 G6-1/G6-2 更新
        </el-button>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G6-6" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ interest.groups.value.length }} 个投资项目</el-tag>
      </div>
    </div>

    <!-- 方法论上下文（琥珀色左边线+浅黄背景） -->
    <div class="methodology-context">
      <p><strong>实际利率法确认利息收入：</strong></p>
      <p>利息收入 = 摊余成本 × 实际利率 × 计息天数 / 365</p>
      <p>期末摊余成本 = 期初摊余成本 + 实际利息收入 - 现金流入（票息）</p>
      <p style="color: #92400e; font-size: 11px; margin-top: 4px;">
        依据CAS22《金融工具确认和计量》，其他债权投资按实际利率法确认利息收入并调整摊余成本。
      </p>
    </div>

    <!-- ═══ 投资项目分组卡片 ═══ -->
    <template v-if="interest.groups.value.length > 0">
      <el-card
        v-for="group in interest.groups.value"
        :key="group.id"
        shadow="never"
        class="group-card"
      >
        <!-- 分组header -->
        <template #header>
          <div class="group-header">
            <div class="group-info">
              <span class="group-name">{{ group.investProject }}</span>
              <div class="group-params">
                <span class="param-item">
                  面值：
                  <el-input-number
                    v-if="!isReadonly"
                    :model-value="group.faceValue"
                    size="small" :controls="false" :precision="2"
                    style="width: 120px"
                    @update:model-value="(v: number | undefined) => interest.updateGroupHeader(group.id, 'faceValue', v ?? 0)"
                  />
                  <span v-else>{{ fmtNum(group.faceValue) }}</span>
                </span>
                <span class="param-item">
                  票面利率：
                  <el-input-number
                    v-if="!isReadonly"
                    :model-value="group.couponRate * 100"
                    size="small" :controls="false" :precision="4"
                    style="width: 90px"
                    @update:model-value="(v: number | undefined) => interest.updateGroupHeader(group.id, 'couponRate', (v ?? 0) / 100)"
                  />
                  <span v-else>{{ (group.couponRate * 100).toFixed(4) }}</span>%
                </span>
                <span class="param-item">
                  实际利率：
                  <el-input-number
                    v-if="!isReadonly"
                    :model-value="group.effectiveRate * 100"
                    size="small" :controls="false" :precision="4"
                    style="width: 90px"
                    @update:model-value="(v: number | undefined) => interest.updateGroupHeader(group.id, 'effectiveRate', (v ?? 0) / 100)"
                  />
                  <span v-else>{{ (group.effectiveRate * 100).toFixed(4) }}</span>%
                </span>
              </div>
            </div>
            <div class="group-actions">
              <el-tag size="small" type="info">
                利息小计：{{ fmtNum(interest.getGroupInterestTotal(group.id)) }}
              </el-tag>
              <el-button
                v-if="!isReadonly"
                size="small" type="danger" link
                @click="interest.removeGroup(group.id)"
              >🗑️ 删除项目</el-button>
            </div>
          </div>
        </template>

        <!-- 多期表格 -->
        <el-table :data="group.periods" border size="small" class="period-table">
          <el-table-column label="截止日" width="120">
            <template #default="{ row }">
              <el-date-picker
                v-if="!isReadonly"
                :model-value="row.periodEnd"
                type="date"
                size="small"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                placeholder="选择日期"
                style="width: 110px"
                @update:model-value="(v: string) => interest.updatePeriod(group.id, row.id, 'periodEnd', v || '')"
              />
              <span v-else>{{ row.periodEnd || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期初摊余成本" width="140" align="right">
            <template #default="{ row, $index }">
              <el-input-number
                v-if="!isReadonly && $index === 0"
                :model-value="row.openingAmortized"
                size="small" :controls="false" :precision="2"
                style="width: 120px"
                @update:model-value="(v: number | undefined) => interest.updatePeriod(group.id, row.id, 'openingAmortized', v ?? 0)"
              />
              <span v-else class="formula-cell" title="期初摊余 = 上期期末摊余">
                {{ fmtNum(row.openingAmortized) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="实际利息收入" width="140" align="right">
            <template #default="{ row }">
              <span
                class="formula-cell"
                title="实际利息 = 期初摊余 × 实际利率 × 天数/365"
              >{{ fmtNum(row.effectiveInterest) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="现金流入" width="130" align="right">
            <template #default="{ row }">
              <span
                class="formula-cell"
                title="现金流入 = 面值 × 票面利率 × 天数/365"
              >{{ fmtNum(row.cashInflow) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末摊余成本" width="140" align="right">
            <template #default="{ row }">
              <span
                class="formula-cell"
                title="期末摊余 = 期初 + 实际利息 - 现金流入"
              >{{ fmtNum(row.endingAmortized) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="天数" width="80" align="center">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.days"
                size="small" :controls="false" :min="1" :max="366"
                style="width: 60px"
                @update:model-value="(v: number | undefined) => interest.updatePeriod(group.id, row.id, 'days', v ?? 180)"
              />
              <span v-else>{{ row.days }}</span>
            </template>
          </el-table-column>
          <el-table-column label="备注" min-width="120">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                :model-value="row.remark"
                size="small" placeholder="备注..."
                @update:model-value="(v: string) => interest.updatePeriod(group.id, row.id, 'remark', v)"
              />
              <span v-else>{{ row.remark || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="" width="50" align="center">
            <template #default="{ row }">
              <el-button
                size="small" type="danger" link
                @click="interest.removePeriod(group.id, row.id)"
              >🗑️</el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- 组内新增期间 -->
        <div v-if="!isReadonly" class="add-period-bar">
          <el-button size="small" @click="interest.addPeriod(group.id)">
            + 新增期间
          </el-button>
        </div>
      </el-card>
    </template>

    <el-empty v-else description="暂无投资项目，请点击“新增投资项目”添加" :image-size="60" />

    <!-- 底部操作区 -->
    <div class="bottom-actions">
      <el-button v-if="!isReadonly" type="primary" size="small" @click="interest.addGroup()">
        + 新增投资项目
      </el-button>
      <G6SppiImportExportDropdown
        v-if="wpId"
        :wp-id="wpId"
        sheet="G6-6"
        :disabled="isReadonly"
        @imported="onImported"
      />
    </div>

    <!-- ═══ 底部交叉验证 ═══ -->
    <el-card shadow="never" class="cross-validation-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">交叉验证</span>
        </div>
      </template>
      <div class="cv-grid">
        <div class="cv-item">
          <span class="cv-label">本表利息合计</span>
          <span class="cv-value">{{ fmtNum(interest.totalInterest.value) }}</span>
        </div>
        <div class="cv-item">
          <span class="cv-label">G6-1利息调整本期变动</span>
          <el-input-number
            v-if="!isReadonly"
            v-model="interest.auditedInterest.value"
            size="small" :controls="false" :precision="2"
            style="width: 140px"
            @change="handleSave"
          />
          <span v-else class="cv-value">{{ fmtNum(interest.auditedInterest.value) }}</span>
          <span class="cv-hint">可手工改为账面利息收入</span>
        </div>
        <div class="cv-item">
          <span class="cv-label">差异</span>
          <span
            class="cv-value"
            :class="{
              'cv-pass': interest.crossValidationPassed.value,
              'cv-fail': !interest.crossValidationPassed.value,
            }"
          >
            {{ fmtNum(interest.crossValidationDiff.value) }}
            <el-icon v-if="interest.crossValidationPassed.value" style="color: #10b981; margin-left: 4px;">✓</el-icon>
            <el-icon v-else style="color: #ef4444; margin-left: 4px;">✗</el-icon>
          </span>
        </div>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">审计说明</span>
          <div class="section-actions">
            <el-button
              size="small"
              :disabled="isReadonly || aiLoading"
              :loading="aiLoading"
              @click="handleAiNote"
            >🤖 AI辅助</el-button>
          </div>
        </div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述实际利率法测算的测试情况及结果、与审定表（G6-1）利息调整/利息收入的交叉验证、拟调整与未调整事项及其影响。"
        @update:model-value="saveAuditNote"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">审计结论</span>
          <div class="section-actions">
            <el-button
              size="small"
              :disabled="isReadonly || aiLoading"
              :loading="aiLoading"
              @click="handleAi"
            >🤖 AI辅助</el-button>
            <el-button size="small" @click="openReview('G6-6-interest')">💬复核</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="interest.conclusion.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="对利息测算结果的审计结论：利息收入计算方法是否恰当、实际利率确定是否合理..."
        @input="handleSave"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="guide-details">
      <summary>📋 编制提示</summary>
      <div class="guide-content">
        <p>1. 实际利率在初始确认时确定，后续不因市场利率变动而调整</p>
        <p>2. 验证实际利率与票面利率的差异：溢价/折价购入时实际利率≠票面利率</p>
        <p>3. 每期利息收入 = 期初摊余成本 × 实际利率 × 计息天数/365</p>
        <p>4. 现金流入（票息）= 面值 × 票面利率 × 计息天数/365</p>
        <p>5. 期末摊余成本 = 期初 + 实际利息 - 现金流入（摊余成本逐期调整）</p>
        <p>6. 交叉验证：本表利息合计与 G6-1 利息调整本期变动（或账面利息收入）勾稽</p>
        <p>7. 优先用「从 G6-1/G6-2 更新」带入项目、面值、利率与期初摊余成本</p>
        <p>8. 关注计息天数的准确性（实际天数法vs30/360法）</p>
        <p>9. 浮动利率债券需关注利率重置日的处理</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G6TabInterestCalculation.vue — G6-6 利息测算表（实际利率法分组结构）
 *
 * Spec: .kiro/specs/g6-other-bond-investment-sppi/ Task 5.2
 * Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
 *
 * 功能：
 * - 方法论上下文(琥珀色): "实际利率法确认利息收入=摊余成本×实际利率×计息天数/365"
 * - 投资项目分组（每项目一个分组card: 面值|票面利率|实际利率）
 * - 每组内多期表格：截止日|期初摊余|实际利息(公式)|现金流入(公式)|期末摊余(公式)|天数
 * - 动态: +新增投资项目(ElMessageBox.prompt) / +新增期间
 * - 底部交叉验证: 利息合计 vs G6-1审定表利息调整
 * - 审计结论textarea + AI按钮 + 编制提示折叠
 */
import { computed, inject, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useG6SppiInterest } from '../../composables/useG6SppiInterest'
import { useG6SppiFormData } from '../../composables/useG6SppiFormData'
import { useG6SppiAiGenerate } from '../../composables/useG6SppiAiGenerate'
import {
  fetchG61InterestAdjPeriodChange,
  fetchG62DetailRows,
  mapG62RowsToInterestSeeds,
  parseG6ChecklistPayload,
} from '../../composables/g6CrossHelpers'
import GtIndexChip from '../../GtIndexChip.vue'
import G6SppiImportExportDropdown from '../G6SppiImportExportDropdown.vue'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{ imported: [] }>()

// ─── 复核对话 inject ───
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

function openReview(sectionId: string): void {
  openReviewDialog(sectionId)
}

// ─── 数据层 ───
const formData = useG6SppiFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
const interest = useG6SppiInterest()
const wpIdRef = computed(() => props.wpId)
const { generateAndConfirm, loading: aiLoading } = useG6SppiAiGenerate(wpIdRef)
const syncing = ref(false)

const DATA_KEY = 'G6-6-interest-data'
const ROWS_KEY = 'G6-6-rows'
const NOTE_KEY = 'G6-6-interest-calc-audit-note'
const auditNote = ref('')

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  formData.debouncedSave(NOTE_KEY, { remark: val })
}

function initFromData(): void {
  // 1) UI 主键：嵌套 G6-6-interest-data
  const primary = parseG6ChecklistPayload(formData.allResponses.value.get(DATA_KEY))
  if (primary && (Array.isArray(primary.groups) || primary.crossValidation || primary.conclusion)) {
    interest.loadData(primary)
    return
  }
  // 2) IE 兼容：扁平 G6-6-rows
  const flat = parseG6ChecklistPayload(formData.allResponses.value.get(ROWS_KEY))
  if (Array.isArray(flat) && flat.length) {
    interest.loadData(flat)
    return
  }
  if (flat?.groups) {
    interest.loadData(flat)
    return
  }
  // 3) render-config / sheetCache 兜底
  const content = formData.parseContent()
  if (content.interest) {
    interest.loadData(content.interest as any)
  }
}

// ─── 数据加载 ───
onMounted(async () => {
  await formData.loadAll()
  initFromData()
  const noteResp = formData.allResponses.value.get(NOTE_KEY)
  if (noteResp?.remark) auditNote.value = noteResp.remark
})

watch(() => props.htmlData, (newData) => {
  if (newData) initFromData()
})

watch(
  () => {
    const a = formData.allResponses.value.get(DATA_KEY)
    const b = formData.allResponses.value.get(ROWS_KEY)
    return [a?.conclusion, a?.remark, b?.conclusion, b?.remark].join('|')
  },
  (fp, prev) => {
    if (prev != null && fp !== prev) initFromData()
  },
)

// ─── 保存：嵌套主键 + 扁平兼容双写 ───
function handleSave(): void {
  if (props.isReadonly) return
  const nested = interest.toJSON()
  formData.debouncedSave(DATA_KEY, {
    conclusion: JSON.stringify(nested),
  })
  formData.debouncedSave(ROWS_KEY, {
    conclusion: JSON.stringify(interest.flattenGroups()),
  })
}

async function onImported(): Promise<void> {
  await formData.loadAll()
  initFromData()
  const noteResp = formData.allResponses.value.get(NOTE_KEY)
  if (noteResp?.remark) auditNote.value = noteResp.remark
  emit('imported')
}

async function syncFromMain(): Promise<void> {
  if (props.isReadonly) return
  syncing.value = true
  try {
    const [detailRows, interestAdjChange] = await Promise.all([
      fetchG62DetailRows(props.projectId),
      fetchG61InterestAdjPeriodChange(props.projectId),
    ])
    const seeds = mapG62RowsToInterestSeeds(detailRows)
    const { added, updated } = interest.mergeSeedsFromDetail(seeds)
    if (interestAdjChange != null) {
      interest.auditedInterest.value = interestAdjChange
    }
    handleSave()
    if (!seeds.length && interestAdjChange == null) {
      ElMessage.warning('未找到 G6-1/G6-2 数据，请确认 Main 底稿已编制')
    } else {
      ElMessage.success(
        `已同步：新增 ${added} 项，更新 ${updated} 项` +
          (interestAdjChange != null ? `；G6-1利息调整本期变动 ${interestAdjChange}` : ''),
      )
    }
  } catch {
    ElMessage.warning('同步 G6-1/G6-2 失败，请稍后重试')
  } finally {
    syncing.value = false
  }
}

// watch groups / conclusion 深度变化保存
watch(() => interest.groups.value, () => {
  handleSave()
}, { deep: true })

watch(() => interest.conclusion.value, () => {
  handleSave()
})

function aiContext() {
  return {
    groupCount: interest.groups.value.length,
    totalInterest: interest.totalInterest.value,
    auditedInterest: interest.auditedInterest.value,
    crossValidationDiff: interest.crossValidationDiff.value,
    projects: interest.groups.value.map((g) => g.investProject),
  }
}

// ─── AI辅助 ───
async function handleAiNote(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'interest-note',
    auditNote.value || '',
    aiContext(),
    'AI 利息测算审计说明',
  )
  if (text) saveAuditNote(text)
}

async function handleAi(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'interest-conclusion',
    interest.conclusion.value || '',
    aiContext(),
    'AI 利息测算审计结论',
  )
  if (text) {
    interest.conclusion.value = text
    handleSave()
  }
}

// ─── 数字格式化 ───
function fmtNum(v: number | undefined, decimals = 2): string {
  if (v === undefined || v === null) return '-'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

// ─── 暴露接口 ───
defineExpose({
  toJSON: () => interest.toJSON(),
  syncFromMain,
})
</script>

<style scoped>
.g6-tab-interest-calculation {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 审计目标 / 工具栏 ─── */
.objective-alert {
  margin-bottom: 12px;
}
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}
.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 6px;
}
.chip-wrap {
  display: inline-flex;
  align-items: center;
}

/* ─── 方法论上下文（琥珀色左边线+浅黄背景）─── */
.methodology-context {
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #fffbeb;
  border-left: 4px solid #f59e0b;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.8;
}

.methodology-context p {
  margin: 0 0 2px;
}

/* ─── 分组卡片 ─── */
.group-card {
  margin-bottom: 16px;
}

.group-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 8px;
}

.group-info {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.group-name {
  font-weight: 600;
  font-size: 14px;
}

.group-params {
  display: flex;
  gap: 16px;
  align-items: center;
  flex-wrap: wrap;
}

.param-item {
  font-size: 12px;
  color: #606266;
}

.group-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* ─── 期间表格 ─── */
.period-table {
  font-size: var(--wp-font-size, 13px);
}

/* ─── 公式列样式 ─── */
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding: 2px 4px;
  display: inline-block;
}

/* ─── 新增期间 ─── */
.add-period-bar {
  margin-top: 8px;
  text-align: left;
}

/* ─── 底部操作 ─── */
.bottom-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  margin: 16px 0;
}

.import-export-dropdown {
  margin-left: 8px;
}

/* ─── 交叉验证 ─── */
.cross-validation-card {
  margin-bottom: 16px;
}

.cv-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  align-items: center;
}

.cv-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.cv-label {
  font-size: 12px;
  color: #909399;
}
.cv-hint {
  font-size: 11px;
  color: #a8abb2;
}

.cv-value {
  font-size: 14px;
  font-weight: 600;
}

.cv-pass {
  color: #10b981;
}

.cv-fail {
  color: #ef4444;
}

/* ─── Section卡片通用 ─── */
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.section-title {
  font-weight: 600;
  font-size: 14px;
}

.section-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* ─── 审计结论 ─── */
.conclusion-card {
  margin-bottom: 16px;
}

/* ─── 编制提示 ─── */
.guide-details {
  margin-top: 16px;
}

.guide-details summary {
  cursor: pointer;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  font-weight: 600;
}

.guide-content {
  padding: 8px 12px;
  background: #fffbeb;
  border-left: 3px solid #f59e0b;
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.8;
}

.guide-content p {
  margin: 0;
}
</style>
