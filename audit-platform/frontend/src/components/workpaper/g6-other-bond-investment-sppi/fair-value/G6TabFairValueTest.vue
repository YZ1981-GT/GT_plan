<template>
  <div class="g6-tab-fair-value-test">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实其他债权投资以公允价值计量的恰当性，验证公允价值层次（L1/L2/L3）划分与估值方法的合理性，确认 FVOCI 公允价值计量准确。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:G6-5" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ fairValue.rows.value.length }} 行</el-tag>
    </div>

    <!-- 2区段Tab切换 -->
    <el-tabs v-model="fairValue.activeTab.value" class="fv-tabs">
      <el-tab-pane label="基础+审定" name="tab1" />
      <el-tab-pane label="估值详情" name="tab2" />
    </el-tabs>

    <!-- ═══ Tab1: 基础+审定(10列) ═══ -->
    <el-card v-show="fairValue.activeTab.value === 'tab1'" shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">公允价值测试 — 基础+审定</span>
          <div class="section-actions">
            <el-tag v-if="fairValue.diffCount.value > 0" type="danger" size="small">
              {{ fairValue.diffCount.value }}项差异
            </el-tag>
            <el-button size="small" :disabled="isReadonly" @click="handleAi">🤖 AI辅助</el-button>
            <el-button size="small" @click="openReview('G6-5-fair-value')">💬复核</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="fairValue.rows.value"
        border
        size="small"
        class="fv-table"
        highlight-current-row
        :current-row-key="currentRowId"
        row-key="id"
        @current-change="handleRowChange"
      >
        <el-table-column type="index" label="序号" width="50" align="center" />
        <el-table-column label="投资项目" prop="investProject" min-width="120">
          <template #default="{ row }">
            <div class="name-cell">
              <span>{{ row.investProject }}</span>
              <el-button
                v-if="!isReadonly"
                size="small" type="danger" link
                @click="fairValue.removeRow(row.id)"
              >🗑️</el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="面值" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.faceValue"
              size="small" :controls="false" :precision="2"
              style="width: 90px"
              @update:model-value="(v: number | undefined) => fairValue.updateRow(row.id, 'faceValue', v ?? 0)"
            />
            <span v-else>{{ fmtNum(row.faceValue) }}</span>
          </template>
        </el-table-column>
        <!-- 期末未审 3列 -->
        <el-table-column label="期末未审-数量" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.unadjQty"
              size="small" :controls="false" :precision="0"
              style="width: 80px"
              @update:model-value="(v: number | undefined) => fairValue.updateRow(row.id, 'unadjQty', v ?? 0)"
            />
            <span v-else>{{ row.unadjQty }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末未审-单价" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.unadjPrice"
              size="small" :controls="false" :precision="4"
              style="width: 90px"
              @update:model-value="(v: number | undefined) => fairValue.updateRow(row.id, 'unadjPrice', v ?? 0)"
            />
            <span v-else>{{ fmtNum(row.unadjPrice, 4) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末未审-公允价值" width="130" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.unadjFairValue"
              size="small" :controls="false" :precision="2"
              style="width: 110px"
              @update:model-value="(v: number | undefined) => fairValue.updateRow(row.id, 'unadjFairValue', v ?? 0)"
            />
            <span v-else>{{ fmtNum(row.unadjFairValue) }}</span>
          </template>
        </el-table-column>
        <!-- 期末审定 3列 -->
        <el-table-column label="期末审定-数量" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.auditedQty"
              size="small" :controls="false" :precision="0"
              style="width: 80px"
              @update:model-value="(v: number | undefined) => fairValue.updateRow(row.id, 'auditedQty', v ?? 0)"
            />
            <span v-else>{{ row.auditedQty }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末审定-单价" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.auditedPrice"
              size="small" :controls="false" :precision="4"
              style="width: 90px"
              @update:model-value="(v: number | undefined) => fairValue.updateRow(row.id, 'auditedPrice', v ?? 0)"
            />
            <span v-else>{{ fmtNum(row.auditedPrice, 4) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末审定-公允价值" width="130" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.auditedFairValue"
              size="small" :controls="false" :precision="2"
              style="width: 110px"
              @update:model-value="(v: number | undefined) => fairValue.updateRow(row.id, 'auditedFairValue', v ?? 0)"
            />
            <span v-else>{{ fmtNum(row.auditedFairValue) }}</span>
          </template>
        </el-table-column>
        <!-- 差异（公式列，红色高亮） -->
        <el-table-column label="差异" width="110" align="right">
          <template #default="{ row }">
            <span
              class="formula-cell"
              :style="fairValue.getDiffCellStyle(row)"
              title="差异 = 审定公允价值 - 未审公允价值"
            >{{ fmtNum(row.difference) }}</span>
          </template>
        </el-table-column>
        <!-- 公允价值层次 -->
        <el-table-column label="公允价值层次" width="120" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.fairValueLevel"
              size="small"
              placeholder="选择层次"
              :class="{ 'l3-warning': fairValue.hasL3Errors(row) }"
              style="width: 100%"
              @change="(v: string) => fairValue.updateRow(row.id, 'fairValueLevel', v)"
            >
              <el-option value="L1" label="L1 活跃市场报价" />
              <el-option value="L2" label="L2 可观察输入值" />
              <el-option value="L3" label="L3 不可观察输入值" />
            </el-select>
            <el-tag v-else :type="row.fairValueLevel === 'L3' ? 'danger' : 'info'" size="small">
              {{ row.fairValueLevel || '-' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>

      <!-- L3校验提示 -->
      <el-alert
        v-if="fairValue.l3ValidationSummary.value.length > 0"
        type="warning"
        :closable="false"
        class="l3-alert"
      >
        <template #title>
          Level3校验提示：以下项目估值详情未填写完整
        </template>
        <ul class="l3-error-list">
          <li v-for="item in fairValue.l3ValidationSummary.value" :key="item.row.id">
            {{ item.row.investProject }}：缺少{{ item.errors.join('、') }}
          </li>
        </ul>
      </el-alert>
    </el-card>

    <!-- ═══ Tab2: 估值详情(8列) ═══ -->
    <el-card v-show="fairValue.activeTab.value === 'tab2'" shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">公允价值测试 — 估值详情</span>
          <div class="section-actions">
            <el-button size="small" :disabled="isReadonly" @click="handleAi">🤖 AI辅助</el-button>
            <el-button size="small" @click="openReview('G6-5-valuation-detail')">💬复核</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="fairValue.rows.value"
        border
        size="small"
        class="fv-table"
        highlight-current-row
        :current-row-key="currentRowId"
        row-key="id"
        @current-change="handleRowChange"
      >
        <el-table-column type="index" label="序号" width="50" align="center" />
        <el-table-column label="投资项目" prop="investProject" min-width="120" />
        <el-table-column label="估值方法" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.valuationMethod"
              size="small" placeholder="估值方法..."
              :class="{ 'l3-required': fairValue.isLevel3(row) && !row.valuationMethod }"
              @update:model-value="(v: string) => fairValue.updateRow(row.id, 'valuationMethod', v)"
            />
            <span v-else>{{ row.valuationMethod || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="与上期一致性" width="100" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.consistencyWithPrior"
              size="small" placeholder="选择"
              style="width: 100%"
              @change="(v: string) => fairValue.updateRow(row.id, 'consistencyWithPrior', v)"
            >
              <el-option value="一致" label="一致" />
              <el-option value="不一致" label="不一致" />
              <el-option value="首次" label="首次" />
            </el-select>
            <span v-else>{{ row.consistencyWithPrior || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="来源机构" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.sourceInstitution"
              size="small" placeholder="来源机构..."
              @update:model-value="(v: string) => fairValue.updateRow(row.id, 'sourceInstitution', v)"
            />
            <span v-else>{{ row.sourceInstitution || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="输入值来源" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.inputSource"
              size="small" placeholder="输入值来源..."
              @update:model-value="(v: string) => fairValue.updateRow(row.id, 'inputSource', v)"
            />
            <span v-else>{{ row.inputSource || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="估值技术" min-width="130">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.valuationTechnique"
              size="small" placeholder="估值技术..."
              :class="{ 'l3-required': fairValue.isLevel3(row) && !row.valuationTechnique }"
              @update:model-value="(v: string) => fairValue.updateRow(row.id, 'valuationTechnique', v)"
            />
            <span v-else>{{ row.valuationTechnique || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="不可观察输入值" min-width="130">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.unobservableInputs"
              size="small" placeholder="不可观察输入值..."
              :class="{ 'l3-required': fairValue.isLevel3(row) && !row.unobservableInputs }"
              @update:model-value="(v: string) => fairValue.updateRow(row.id, 'unobservableInputs', v)"
            />
            <span v-else>{{ row.unobservableInputs || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="估值文件索引" width="110">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.valuationFileRef"
              size="small" placeholder="索引..."
              @update:model-value="(v: string) => fairValue.updateRow(row.id, 'valuationFileRef', v)"
            />
            <span v-else>{{ row.valuationFileRef || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 底部操作区 -->
    <div class="bottom-actions">
      <el-button v-if="!isReadonly" type="primary" size="small" @click="fairValue.addRow()">
        + 新增行
      </el-button>
      <el-dropdown v-if="!isReadonly" size="small" class="import-export-dropdown">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
            <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
            <el-dropdown-item @click="handleImportData">导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <!-- 层次分布统计 -->
    <div class="level-summary">
      <el-tag type="success" size="small">L1: {{ fairValue.levelSummary.value.L1 }}</el-tag>
      <el-tag type="warning" size="small">L2: {{ fairValue.levelSummary.value.L2 }}</el-tag>
      <el-tag type="danger" size="small">L3: {{ fairValue.levelSummary.value.L3 }}</el-tag>
      <el-tag v-if="fairValue.levelSummary.value.unset > 0" type="info" size="small">
        未设: {{ fairValue.levelSummary.value.unset }}
      </el-tag>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-header"><span class="section-title">审计说明</span></div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述公允价值来源与估值方法的测试情况及结果、L3 层次关键假设的合理性评价、拟调整与未调整事项及其影响。"
        @update:model-value="saveAuditNote"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">审计结论</span>
          <div class="section-actions">
            <el-button size="small" :disabled="isReadonly" @click="handleAi">🤖 AI辅助</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="fairValue.conclusion.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="对公允价值测试结果的审计结论..."
        @input="handleSave"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="guide-details">
      <summary>📋 编制提示</summary>
      <div class="guide-content">
        <p>1. 核实期末公允价值来源是否可靠（L1活跃市场报价/L2可观察输入值/L3不可观察输入值）</p>
        <p>2. L3层次需重点关注估值方法、估值技术和不可观察输入值的合理性</p>
        <p>3. 差异（审定-未审）不为零时需分析差异原因并记录处理措施</p>
        <p>4. 检查公允价值层次分类是否恰当，有无应归入L3而错误归入L1/L2的情况</p>
        <p>5. 对比与上期估值方法的一致性，变化时应评价变更理由的合理性</p>
        <p>6. L3估值需评价关键假设和不可观察输入值的敏感性分析</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G6TabFairValueTest.vue — G6-5 公允价值测试表（2区段Tab + Level分层）
 *
 * Spec: .kiro/specs/g6-other-bond-investment-sppi/ Task 4.2
 * Requirements: 2.1, 2.2
 *
 * 功能：
 * - Tab1基础+审定(10列): 投资项目|面值|期末未审(数量/单价/公允价值)|期末审定(数量/单价/公允价值)|差异(公式)|公允价值层次(下拉L1/L2/L3)
 * - Tab2估值详情(8列): 投资项目|估值方法|与上期一致性|来源机构|输入值来源|估值技术|不可观察输入值|估值文件索引
 * - 差异列红色高亮(|diff|>0)
 * - L3校验：层次=L3时Tab2相关字段必填
 * - 动态行增删(ElMessageBox.prompt) + 导入导出
 */
import { computed, inject, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useG6SppiFairValue } from '../../composables/useG6SppiFairValue'
import { useG6SppiFormData } from '../../composables/useG6SppiFormData'
import type { FairValueItem } from '../../composables/useG6SppiFairValue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

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
const fairValue = useG6SppiFairValue()

// ─── 当前选中行 ───
const currentRowId = computed(() => {
  const rows = fairValue.rows.value
  if (rows.length === 0) return ''
  const idx = fairValue.selectedRowIndex.value
  return rows[idx]?.id || rows[0]?.id || ''
})

function handleRowChange(row: FairValueItem | null): void {
  if (!row) return
  const idx = fairValue.rows.value.findIndex(r => r.id === row.id)
  if (idx >= 0) fairValue.selectedRowIndex.value = idx
}

// ─── 审计说明（独立持久化 checklist_responses） ───
const NOTE_KEY = 'G6-5-fair-value-test-audit-note'
const auditNote = ref('')

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  formData.debouncedSave(NOTE_KEY, { remark: val })
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

function initFromData(): void {
  const content = formData.parseContent()
  if (content.fairValue) {
    fairValue.loadData(content.fairValue)
  }
}

// ─── 保存 ───
function handleSave(): void {
  formData.debouncedSave('G6-5-fair-value-data', {
    conclusion: JSON.stringify(fairValue.toJSON()),
  })
}

// watch rows 深度变化保存
watch(() => fairValue.rows.value, () => {
  handleSave()
}, { deep: true })

// ─── AI辅助 ───
function handleAi(): void {
  ElMessage.info('AI辅助(公允价值结论)功能将在AI模块完成后启用')
}

// ─── 导入导出（占位） ───
function handleExportTemplate(): void {
  ElMessage.info('导出模板功能将在导入导出模块完成后启用')
}
function handleExportData(): void {
  ElMessage.info('导出数据功能将在导入导出模块完成后启用')
}
function handleImportData(): void {
  ElMessage.info('导入数据功能将在导入导出模块完成后启用')
}

// ─── 数字格式化 ───
function fmtNum(v: number | undefined, decimals = 2): string {
  if (v === undefined || v === null) return '-'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

// ─── 暴露接口 ───
defineExpose({
  toJSON: () => fairValue.toJSON(),
})
</script>

<style scoped>
.g6-tab-fair-value-test {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 审计目标 / 工具栏 ─── */
.objective-alert {
  margin-bottom: 12px;
}
.tab-toolbar {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}
.chip-wrap {
  display: inline-flex;
  align-items: center;
}

/* ─── Tabs ─── */
.fv-tabs {
  margin-bottom: 12px;
}

/* ─── Section卡片 ─── */
.section-card {
  margin-bottom: 16px;
}

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

/* ─── 表格 ─── */
.fv-table {
  font-size: var(--wp-font-size, 13px);
}

/* ─── 名称单元格 ─── */
.name-cell {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

/* ─── 公式列样式 ─── */
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding: 2px 4px;
  display: inline-block;
}

/* ─── L3校验 ─── */
.l3-warning :deep(.el-input__wrapper),
.l3-warning :deep(.el-select__wrapper) {
  box-shadow: 0 0 0 1px #f56c6c inset;
}

.l3-required :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px #e6a23c inset;
}

.l3-alert {
  margin-top: 12px;
}

.l3-error-list {
  margin: 4px 0 0 16px;
  padding: 0;
  font-size: 12px;
}

/* ─── 底部操作 ─── */
.bottom-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  margin: 12px 0;
}

.import-export-dropdown {
  margin-left: 8px;
}

/* ─── 层次分布 ─── */
.level-summary {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
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
