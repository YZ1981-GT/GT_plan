<!--
  G7TabImpairmentTest.vue — G7-17 减值测试表（33行×9列）

  核心特色：CAS8 减值判断标准
  - 减值金额(公式) = calcImpairmentAmount = MAX(0, 账面价值 - 可收回金额)
  - 减值迹象=是 → 可收回金额/FV-处置费用/使用价值 三列高亮必填
  - 减值迹象=否 → 三列灰色禁用
  - 减值金额>0 → 红色标记

  9列：被投资单位|账面价值|可收回金额|减值迹象(下拉:是/否)|
       减值金额(公式)|公允价值-处置费用|使用价值|审计结论(下拉)|索引

  Spec: .kiro/specs/g7-long-term-equity-method/
  Task: 8.2
  Requirements: 6.5, 6.6, 6.7, 7.4
-->
<template>
  <div class="g7-tab-impairment-test">
    <!-- 方法论上下文（琥珀色左边线+浅黄背景：CAS8减值判断标准） -->
    <div class="methodology-context">
      <p><strong>减值判断标准（CAS8）：</strong></p>
      <ul>
        <li>可收回金额 = MAX(公允价值 - 处置费用, 使用价值)</li>
        <li>减值金额 = MAX(0, 账面价值 - 可收回金额)</li>
        <li>减值迹象包括：被投资方持续亏损、净资产大幅下降、市场环境显著恶化、技术/法律变化等</li>
        <li>长期股权投资减值损失一经确认，不得转回</li>
      </ul>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：评价长期股权投资减值迹象识别及可收回金额估计的合理性，验证减值准备计提是否充分（CAS8）。"
      class="objective-alert"
    />

    <!-- section标题 + 操作按钮 -->
    <div class="section-head">
      <h3 class="sheet-title">G7-17 减值测试表</h3>
      <div class="head-actions">
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
        <el-button size="small" @click="handleAiConclusion">🤖AI辅助</el-button>
        <el-button size="small" @click="openReviewDialog('G7-17-impairment-test')">💬复核</el-button>
      </div>
    </div>

    <!-- 工具栏：索引 chip + 行数 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G7-17" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <!-- 9列表格 -->
    <el-table
      :data="rows"
      border
      size="small"
      max-height="580"
      class="impairment-test-table"
      row-key="id"
    >
      <!-- 序号 -->
      <el-table-column label="序号" width="55" align="center" fixed>
        <template #default="{ row }">{{ row.seq }}</template>
      </el-table-column>

      <!-- 1. 被投资单位 -->
      <el-table-column label="被投资单位" min-width="130" fixed>
        <template #default="{ row }">
          <el-input
            :model-value="row.investeeName"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => updateField(row.id, 'investeeName', v)"
          />
        </template>
      </el-table-column>

      <!-- 2. 账面价值 -->
      <el-table-column label="账面价值" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.bookValue"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            @change="(v: number | undefined) => handleBookValueChange(row.id, v ?? 0)"
          />
        </template>
      </el-table-column>

      <!-- 3. 可收回金额 -->
      <el-table-column label="可收回金额" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.recoverableAmount"
            size="small"
            :controls="false"
            :disabled="isReadonly || !row.hasImpairmentSign"
            :class="{ 'highlight-required': row.hasImpairmentSign, 'disabled-cell': !row.hasImpairmentSign }"
            style="width:100%"
            @change="(v: number | undefined) => handleRecoverableChange(row.id, v ?? 0)"
          />
        </template>
      </el-table-column>

      <!-- 4. 减值迹象(下拉:是/否) -->
      <el-table-column label="减值迹象" width="100" align="center">
        <template #default="{ row }">
          <el-select
            :model-value="row.hasImpairmentSign ? '是' : '否'"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => handleSignChange(row.id, v === '是')"
          >
            <el-option label="是" value="是" />
            <el-option label="否" value="否" />
          </el-select>
        </template>
      </el-table-column>

      <!-- 5. 减值金额(公式: MAX(0, 账面-可收回)) -->
      <el-table-column label="减值金额" min-width="120" align="right">
        <template #header>
          <span class="formula-header" title="= MAX(0, 账面价值 - 可收回金额)">
            减值金额
          </span>
        </template>
        <template #default="{ row }">
          <span
            class="formula-cell"
            :class="{ 'impairment-positive': row.impairmentAmount > 0 }"
            :title="`MAX(0, ${fmtNum(row.bookValue)} - ${fmtNum(row.recoverableAmount)}) = ${fmtNum(row.impairmentAmount)}`"
          >
            {{ fmtNum(row.impairmentAmount) }}
          </span>
        </template>
      </el-table-column>

      <!-- 6. 公允价值-处置费用 -->
      <el-table-column label="公允-处置费用" min-width="130" align="right">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.fvLessDisposalCost"
            size="small"
            :controls="false"
            :disabled="isReadonly || !row.hasImpairmentSign"
            :class="{ 'highlight-required': row.hasImpairmentSign, 'disabled-cell': !row.hasImpairmentSign }"
            style="width:100%"
            @change="(v: number | undefined) => updateField(row.id, 'fvLessDisposalCost', v ?? 0)"
          />
        </template>
      </el-table-column>

      <!-- 7. 使用价值 -->
      <el-table-column label="使用价值" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.valueInUse"
            size="small"
            :controls="false"
            :disabled="isReadonly || !row.hasImpairmentSign"
            :class="{ 'highlight-required': row.hasImpairmentSign, 'disabled-cell': !row.hasImpairmentSign }"
            style="width:100%"
            @change="(v: number | undefined) => updateField(row.id, 'valueInUse', v ?? 0)"
          />
        </template>
      </el-table-column>

      <!-- 8. 审计结论(下拉) -->
      <el-table-column label="审计结论" width="120" align="center">
        <template #default="{ row }">
          <el-select
            :model-value="row.auditConclusion"
            size="small"
            placeholder="请选择"
            clearable
            :disabled="isReadonly"
            @change="(v: string) => updateField(row.id, 'auditConclusion', v)"
          >
            <el-option label="无需计提" value="无需计提" />
            <el-option label="需计提" value="需计提" />
            <el-option label="已充分计提" value="已充分计提" />
          </el-select>
        </template>
      </el-table-column>

      <!-- 9. 索引 -->
      <el-table-column label="索引" width="90">
        <template #default="{ row }">
          <el-input
            :model-value="row.indexRef"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => updateField(row.id, 'indexRef', v)"
          />
        </template>
      </el-table-column>

      <!-- 操作列(删除) -->
      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-icon class="delete-icon" @click="handleRemoveRow(row.id)">
            <Delete />
          </el-icon>
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计说明 -->
    <el-card class="conclusion-card" shadow="never">
      <template #header>
        <div class="conclusion-header">
          <span>审计说明</span>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：可概述所执行程序、测试情况及结果，拟调整/未调整事项及其影响。"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 审计结论（AI辅助 impairment-conclusion） -->
    <el-card class="conclusion-card" shadow="never">
      <template #header>
        <div class="conclusion-header">
          <span>审计结论</span>
          <el-button size="small" :disabled="isReadonly" @click="handleAiConclusion">🤖AI辅助</el-button>
        </div>
      </template>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="对长期股权投资减值测试的审计结论..."
        @change="persistConclusion"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>减值迹象判断：被投资方持续亏损、经营恶化、净资产大幅下降、市价持续低于账面</li>
        <li>减值迹象=否时，可收回金额/公允-处置费用/使用价值三列自动禁用</li>
        <li>减值迹象=是时，上述三列高亮为必填项</li>
        <li>可收回金额 = MAX(公允价值-处置费用, 使用价值)，审计员选择较高者填入</li>
        <li>减值金额 = MAX(0, 账面价值 - 可收回金额)，系统自动计算</li>
        <li>长期股权投资减值损失一经确认，不得转回（CAS8）</li>
        <li>减值金额>0时将红色标记，提醒关注</li>
        <li>G7-17减值结果将联动main组审定表的减值准备列</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G7TabImpairmentTest — G7-17 减值测试表
 *
 * Spec: .kiro/specs/g7-long-term-equity-method/
 * Task: 8.2
 *
 * 核心逻辑：
 * - calcImpairmentAmount(bookValue, recoverableAmount) → MAX(0, 账面-可收回)
 * - 减值迹象=否 → 可收回金额/FV-处置/使用价值 三列灰色禁用
 * - 减值迹象=是 → 三列高亮必填
 * - 减值金额>0 → 红色标记
 *
 * Requirements: 6.5, 6.6, 6.7, 7.4
 */
import { ref, computed, inject, onMounted } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  calcImpairmentAmount,
  parseNum,
} from '../../composables/useG7EquityMethodFormulaEngine'
import { useG7EquityMethodFormData } from '../../composables/useG7EquityMethodFormData'
import type { ImpairmentTestRow } from '../../composables/useG7EquityMethodFormData'
import { api } from '@/services/apiProxy'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const isReadonly = computed(() => props.readonly ?? false)
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// ─── Data Layer ──────────────────────────────────────────────────────────────

const formData = useG7EquityMethodFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const SECTION_KEY = 'G7-17-impairment-test'
const CONCLUSION_KEY = 'G7-17-conclusion'
const AUDIT_NOTE_KEY = 'G7-17-audit-note'

/** 行数据(响应式) */
const rows = ref<ImpairmentTestRow[]>([])

/** 审计结论 */
const conclusion = ref('')

/** 审计说明（持久化 checklist_responses，conclusion:null） */
const auditNote = ref('')

function saveAuditNote(val: string): void {
  if (isReadonly.value) return
  auditNote.value = val
  formData.debouncedSave(AUDIT_NOTE_KEY, { remark: val, conclusion: null })
}

// ─── Initialize ──────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.load()

  // 从 htmlData 或 sheetCache 中恢复行数据
  const content = props.htmlData ?? formData.parseContent()?.impairmentTest
  if (content && Array.isArray((content as any).rows)) {
    rows.value = (content as any).rows.map((r: any, idx: number) => ({
      ...createEmptyRow(idx + 1),
      ...r,
    }))
    recalcAll()
  } else {
    // 初始化默认行
    rows.value = Array.from({ length: 5 }, (_, i) => createEmptyRow(i + 1))
  }

  // 恢复结论
  const savedConclusion = formData.data.value.get(CONCLUSION_KEY)
  if (savedConclusion?.conclusion) {
    conclusion.value = savedConclusion.conclusion
  }

  // 恢复审计说明
  const savedNote = formData.data.value.get(AUDIT_NOTE_KEY)
  if (savedNote?.remark) {
    auditNote.value = savedNote.remark
  }
})

// ─── Row Factory ─────────────────────────────────────────────────────────────

function createEmptyRow(seq: number, investeeName = ''): ImpairmentTestRow {
  return {
    id: `g17-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    seq,
    investeeName,
    bookValue: 0,
    recoverableAmount: 0,
    hasImpairmentSign: false,
    impairmentAmount: 0,
    fvLessDisposalCost: 0,
    valueInUse: 0,
    auditConclusion: '' as any,
    indexRef: '',
  }
}

// ─── Formula Recalculation ───────────────────────────────────────────────────

/** 对单行重新计算公式列：减值金额 = MAX(0, 账面 - 可收回) */
function recalcRow(row: ImpairmentTestRow): void {
  if (row.hasImpairmentSign) {
    row.impairmentAmount = calcImpairmentAmount(row.bookValue, row.recoverableAmount)
  } else {
    // 无减值迹象时：不计算减值（可收回金额被禁用，减值=0）
    row.impairmentAmount = 0
  }
}

/** 重新计算所有行公式 */
function recalcAll(): void {
  for (const row of rows.value) {
    recalcRow(row)
  }
}

// ─── Field Update Handlers ───────────────────────────────────────────────────

function updateField(rowId: string, field: keyof ImpairmentTestRow, value: any): void {
  const row = rows.value.find((r) => r.id === rowId)
  if (!row) return
  ;(row as any)[field] = value
  recalcRow(row)
  persistRows()
}

/** 账面价值变更 → 重算减值金额 */
function handleBookValueChange(rowId: string, value: number): void {
  const row = rows.value.find((r) => r.id === rowId)
  if (!row) return
  row.bookValue = value
  recalcRow(row)
  persistRows()
}

/** 可收回金额变更 → 重算减值金额 */
function handleRecoverableChange(rowId: string, value: number): void {
  const row = rows.value.find((r) => r.id === rowId)
  if (!row) return
  row.recoverableAmount = value
  recalcRow(row)
  persistRows()
}

/** 减值迹象切换 → 条件必填联动 + 重算减值金额 */
function handleSignChange(rowId: string, hasSign: boolean): void {
  const row = rows.value.find((r) => r.id === rowId)
  if (!row) return
  row.hasImpairmentSign = hasSign

  if (!hasSign) {
    // 减值迹象=否：清零三列并禁用
    row.recoverableAmount = 0
    row.fvLessDisposalCost = 0
    row.valueInUse = 0
  }

  recalcRow(row)
  persistRows()
}

// ─── Dynamic Rows ────────────────────────────────────────────────────────────

async function handleAddRow(): Promise<void> {
  try {
    const { value: name } = await ElMessageBox.prompt(
      '请输入被投资单位名称',
      '新增减值测试行',
      { confirmButtonText: '确定', cancelButtonText: '取消', inputPlaceholder: '被投资单位名称' },
    )
    if (!name?.trim()) {
      ElMessage.warning('被投资单位名称不能为空')
      return
    }
    const newRow = createEmptyRow(rows.value.length + 1, name.trim())
    rows.value.push(newRow)
    persistRows()
    ElMessage.success(`已新增: ${name.trim()}`)
  } catch {
    // 用户取消
  }
}

function handleRemoveRow(rowId: string): void {
  const idx = rows.value.findIndex((r) => r.id === rowId)
  if (idx < 0) return
  rows.value.splice(idx, 1)
  // 重排序号
  rows.value.forEach((r, i) => { r.seq = i + 1 })
  persistRows()
}

// ─── Persistence ─────────────────────────────────────────────────────────────

function persistRows(): void {
  formData.debouncedSave(SECTION_KEY, {
    conclusion: JSON.stringify({ rows: rows.value }),
  })
}

function persistConclusion(): void {
  formData.debouncedSave(CONCLUSION_KEY, { conclusion: conclusion.value })
}

// ─── AI Conclusion (impairment-conclusion) ───────────────────────────────────

async function handleAiConclusion(): Promise<void> {
  if (isReadonly.value) return
  try {
    const res = await api.post(
      `/api/workpapers/${props.wpId}/g7-equity-method/ai/impairment-conclusion`,
      { project_id: props.projectId, rows: rows.value },
    )
    const aiText = res?.data?.conclusion ?? res?.conclusion ?? ''
    if (aiText) {
      conclusion.value = conclusion.value ? `${conclusion.value}\n${aiText}` : aiText
      persistConclusion()
      ElMessage.success('AI结论已生成')
    } else {
      // Fallback: 本地生成
      generateLocalConclusion()
    }
  } catch {
    // AI端点不可用时本地生成
    generateLocalConclusion()
  }
}

function generateLocalConclusion(): void {
  const total = rows.value.length
  const withSign = rows.value.filter((r) => r.hasImpairmentSign).length
  const withImpairment = rows.value.filter((r) => r.impairmentAmount > 0).length
  const totalImpairment = rows.value.reduce((sum, r) => sum + parseNum(r.impairmentAmount), 0)

  const draft =
    `经检查，本期共有 ${total} 项长期股权投资纳入减值测试，` +
    `其中 ${withSign} 项存在减值迹象。` +
    (withImpairment > 0
      ? `经测算，${withImpairment} 项需计提减值准备，减值金额合计 ${fmtNum(totalImpairment)} 元。`
      : `经测算，各项投资可收回金额均不低于账面价值，无需计提减值准备。`) +
    ` 减值测试方法及结论恰当。`

  conclusion.value = conclusion.value ? `${conclusion.value}\n${draft}` : draft
  persistConclusion()
  ElMessage.success('已生成本地结论')
}

// ─── Import/Export (placeholder, composable from Task 9.2) ───────────────────

function handleExportTemplate(): void {
  ElMessage.info('导出模板功能将在导入导出模块完成后启用')
}
function handleExportData(): void {
  ElMessage.info('导出数据功能将在导入导出模块完成后启用')
}
function handleImportData(): void {
  ElMessage.info('导入数据功能将在导入导出模块完成后启用')
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** 数字格式化 */
function fmtNum(v: unknown): string {
  if (v === 0) return '0.00'
  if (typeof v === 'number') {
    return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return String(v ?? '')
}
</script>

<style scoped>
.g7-tab-impairment-test {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}
.objective-alert {
  margin-bottom: 12px;
}
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.tab-toolbar .toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.tab-toolbar .chip-wrap {
  display: inline-flex;
  align-items: center;
}

/* 方法论上下文：琥珀色左边线+浅黄背景 */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  margin-bottom: 14px;
  border-radius: 0 4px 4px 0;
  font-size: var(--wp-font-size, 13px);
  line-height: 1.7;
}
.methodology-context p {
  margin: 0 0 4px;
}
.methodology-context ul {
  margin: 0;
  padding-left: 18px;
}
.methodology-context li {
  margin-bottom: 2px;
}

/* section标题 */
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.sheet-title {
  margin: 0;
  font-size: 15px;
}
.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* 表格 */
.impairment-test-table {
  font-size: var(--wp-font-size, 13px);
}

/* 公式列header：虚线下划线 + cursor:help */
.formula-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
}

/* 公式值单元格 */
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  display: inline-block;
  min-width: 40px;
  text-align: right;
}

/* 减值金额>0时红色标记 */
.impairment-positive {
  color: #f56c6c;
  font-weight: 600;
}

/* 减值迹象=是时三列高亮 */
:deep(.highlight-required .el-input__wrapper),
:deep(.highlight-required .el-input-number__wrapper) {
  background-color: #fef0f0;
  border-color: #fab6b6;
}

/* 减值迹象=否时三列灰色禁用 */
:deep(.disabled-cell .el-input__wrapper),
:deep(.disabled-cell .el-input-number__wrapper) {
  background-color: #f5f7fa;
}

/* 删除图标 */
.delete-icon {
  cursor: pointer;
  color: #909399;
  transition: color 0.2s;
}
.delete-icon:hover {
  color: #f56c6c;
}

/* 审计结论卡片 */
.conclusion-card {
  margin-top: 14px;
}
.conclusion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* 编制提示 */
.prep-hint {
  margin-top: 12px;
  font-size: 12px;
  color: #909399;
}
.prep-hint summary {
  cursor: pointer;
}
.prep-hint ul {
  margin: 8px 0 0;
  padding-left: 18px;
}
</style>
