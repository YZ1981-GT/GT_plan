<template>
  <div class="k7-tab-amort-calc">
    <!-- ═══ 蓝色渐变引导区 ═══ -->
    <div class="guide-steps">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">1</span>确认补助总额</div>
        <div class="guide-step"><span class="step-num">2</span>确定分摊方法和期限</div>
        <div class="guide-step"><span class="step-num">3</span>测算本期应分摊</div>
        <div class="guide-step"><span class="step-num">4</span>比较差异</div>
      </div>
    </div>

    <!-- ═══ Section标题 + AI + 复核 ═══ -->
    <div class="section-header">
      <h3>K7-4 政府补助分摊测算表</h3>
      <div class="header-actions">
        <el-button size="small" type="primary" plain :loading="aiLoading" @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI分摊结论
        </el-button>
        <el-button size="small" @click="openReviewDialog?.('K7-4', '测算表K7-4')">💬 复核</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>
        <b>CAS16政府补助分摊测算：</b>
        <strong>与资产相关</strong>→按资产使用寿命直线分摊（本期=总额/总期数×本期期数）；
        <strong>与收益相关</strong>→补偿以后期间费用分期计入，补偿已发生→一次性计入。
        差异=测算分摊−企业分摊，超过重要性水平({{ fmtNum(calc.materialityValue.value) }})红色标记。
      </p>
    </div>

    <!-- ═══ 差异预警 ═══ -->
    <div v-if="calc.hasExceededVariance.value" class="variance-alert">
      <el-alert type="error" :closable="false" show-icon>
        <template #title>
          存在 {{ calc.exceededItems.value.length }} 项分摊差异超过重要性水平，请关注并调整
        </template>
      </el-alert>
    </div>

    <!-- ═══ 工具栏 ═══ -->
    <div class="toolbar-bar">
      <el-button size="small" :disabled="isReadonly" @click="handleAddRow">＋ 新增测算项</el-button>
      <div style="flex:1" />
      <span class="cross-ref-label">分摊去向：</span>
      <GtIndexChip value="K10" :context-project-id="props.projectId" />
      <GtIndexChip value="K12" :context-project-id="props.projectId" />
    </div>

    <!-- ═══ 测算表 ═══ -->
    <el-table
      :data="calc.calcRows.value"
      border
      size="small"
      style="width: 100%"
      :row-class-name="calcRowClass"
      max-height="480"
      class="amort-table"
    >
      <el-table-column label="补助项目" min-width="140" fixed>
        <template #default="{ row }">
          <span>{{ row.project }}</span>
        </template>
      </el-table-column>

      <el-table-column label="补助总额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            v-model="row.grantTotal"
            :controls="false"
            size="small"
            :precision="2"
            style="width:100px"
            @change="(v:number) => calc.updateCell(row.rowId, 'grantTotal', v)"
          />
          <span v-else class="amount-cell">{{ fmtNum(row.grantTotal) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="相关类型" width="120">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.relatedType"
            size="small"
            @change="(v: string) => calc.updateCell(row.rowId, 'relatedType', v)"
          >
            <el-option v-for="opt in calc.RELATED_TYPE_OPTIONS" :key="opt" :label="opt" :value="opt" />
          </el-select>
          <span v-else>{{ row.relatedType }}</span>
        </template>
      </el-table-column>

      <el-table-column label="分摊方法" width="110">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.amortMethod"
            size="small"
            @change="(v: string) => calc.updateCell(row.rowId, 'amortMethod', v)"
          >
            <el-option v-for="opt in calc.METHOD_OPTIONS" :key="opt" :label="opt" :value="opt" />
          </el-select>
          <span v-else>{{ row.amortMethod }}</span>
        </template>
      </el-table-column>

      <el-table-column label="总期数(月)" width="95" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            v-model="row.totalPeriods"
            :controls="false"
            size="small"
            :min="0"
            style="width:72px"
            @change="(v:number) => calc.updateCell(row.rowId, 'totalPeriods', v)"
          />
          <span v-else>{{ row.totalPeriods }}</span>
        </template>
      </el-table-column>

      <el-table-column label="本期(月)" width="85" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            v-model="row.currentPeriods"
            :controls="false"
            size="small"
            :min="0"
            style="width:65px"
            @change="(v:number) => calc.updateCell(row.rowId, 'currentPeriods', v)"
          />
          <span v-else>{{ row.currentPeriods }}</span>
        </template>
      </el-table-column>

      <!-- 公式列：本期应分摊 -->
      <el-table-column label="本期应分摊" width="120" align="right">
        <template #header>
          <el-tooltip content="直线法=总额/总期数×本期期数；一次性计入=全额" placement="top">
            <span class="formula-header">本期应分摊</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-tooltip content="直线法=总额/总期数×本期期数" placement="top">
            <span class="formula-cell formula-underline">{{ fmtNum(row.calculatedAmort) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>

      <el-table-column label="累计分摊" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            v-model="row.accumulatedAmort"
            :controls="false"
            size="small"
            :precision="2"
            style="width:95px"
            @change="(v:number) => calc.updateCell(row.rowId, 'accumulatedAmort', v)"
          />
          <span v-else class="amount-cell">{{ fmtNum(row.accumulatedAmort) }}</span>
        </template>
      </el-table-column>

      <!-- 公式列：期末余额 -->
      <el-table-column label="期末余额" width="110" align="right">
        <template #header>
          <el-tooltip content="期末余额=补助总额-累计分摊" placement="top">
            <span class="formula-header">期末余额</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-tooltip content="期末余额=补助总额-累计分摊" placement="top">
            <span class="formula-cell formula-underline">{{ fmtNum(row.remainingBalance) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>

      <el-table-column label="企业分摊" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            v-model="row.enterpriseAmort"
            :controls="false"
            size="small"
            :precision="2"
            style="width:95px"
            @change="(v:number) => calc.updateCell(row.rowId, 'enterpriseAmort', v)"
          />
          <span v-else class="amount-cell">{{ fmtNum(row.enterpriseAmort) }}</span>
        </template>
      </el-table-column>

      <!-- 公式列：差异 -->
      <el-table-column label="差异" width="120" align="right">
        <template #header>
          <el-tooltip content="差异=测算分摊-企业分摊" placement="top">
            <span class="formula-header">差异</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-tooltip content="差异=测算分摊-企业分摊" placement="top">
            <span
              class="formula-cell formula-underline"
              :class="{ 'variance-exceeded': row.isVarianceExceeded }"
            >{{ fmtNum(row.variance) }}</span>
          </el-tooltip>
          <el-tag
            v-if="row.isVarianceExceeded"
            type="danger"
            size="small"
            class="exceed-tag"
          >需调整</el-tag>
        </template>
      </el-table-column>

      <el-table-column label="结论" width="120">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.conclusion"
            size="small"
            clearable
            placeholder="请选择"
            @change="(v: string) => calc.updateCell(row.rowId, 'conclusion', v)"
          >
            <el-option v-for="opt in calc.CONCLUSION_OPTIONS" :key="opt" :label="opt" :value="opt" />
          </el-select>
          <span v-else>{{ row.conclusion || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
        <template #default="{ row }">
          <el-button type="danger" link size="small" @click="calc.removeRow(row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 底部合计行 ═══ -->
    <div class="subtotal-bar">
      <span class="subtotal-label">合计（{{ calc.subtotals.value.count }} 笔）</span>
      <span class="subtotal-item">补助总额 <b>{{ fmtNum(calc.subtotals.value.grantTotal) }}</b></span>
      <span class="subtotal-item">测算分摊 <b>{{ fmtNum(calc.subtotals.value.calculatedAmort) }}</b></span>
      <span class="subtotal-item">累计分摊 <b>{{ fmtNum(calc.subtotals.value.accumulatedAmort) }}</b></span>
      <span class="subtotal-item">期末余额 <b>{{ fmtNum(calc.subtotals.value.remainingBalance) }}</b></span>
      <span class="subtotal-item">企业分摊 <b>{{ fmtNum(calc.subtotals.value.enterpriseAmort) }}</b></span>
      <span
        class="subtotal-item"
        :class="{ 'variance-exceeded': Math.abs(calc.subtotals.value.variance) > calc.materialityValue.value }"
      >差异合计 <b>{{ fmtNum(calc.subtotals.value.variance) }}</b></span>
    </div>

    <!-- ═══ 审计结论区 ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-header">
          <span class="conclusion-title">审计结论</span>
          <el-button
            size="small"
            type="primary"
            plain
            :loading="aiConclusionLoading"
            @click="handleAiConclusionGenerate"
          >
            <el-icon><MagicStick /></el-icon> AI生成
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="请输入审计结论或点击AI生成..."
        @blur="handleConclusionBlur"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="k7-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>直线法分摊 = 补助总额 / 分摊期总期数 × 本期期数</li>
        <li>一次性计入：补偿已发生费用/损失→全额计入当期损益</li>
        <li>期末余额 = 补助总额 − 累计分摊</li>
        <li>差异 = 测算分摊 − 企业账面分摊（正数=企业少摊）</li>
        <li>差异超重要性水平({{ fmtNum(calc.materialityValue.value) }})红色标记，需关注调整</li>
        <li>分摊去向：与日常活动相关→其他收益(K10)；无关→营业外收入(K12)</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K7TabAmortizationCalc.vue — K7-4 政府补助分摊测算表
 * 23公式 + 分摊引擎 + 差异标记 + AI辅助 + GtIndexChip联动K10/K12
 *
 * Spec: .kiro/specs/k7-deferred-income/ | Task: 4.4
 * Requirements: 4.1-4.7
 */
import { ref, inject, watch, defineAsyncComponent, type Ref } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { useK7AmortizationCalc } from '../../composables/useK7AmortizationCalc'

const GtIndexChip = defineAsyncComponent(() => import('../../GtIndexChip.vue'))

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Ref<Map<string, any>>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(id: string, label?: string) => void>(
  'openReviewDialog',
  undefined,
)

// ─── Composable ──────────────────────────────────────────────────────────────

const calc = useK7AmortizationCalc({
  allResponses: props.allResponses,
  saveResponse: (field: string, value: any) => { emit('save', field, value) },
})

// ─── Audit Conclusion State ──────────────────────────────────────────────────

const auditConclusion = ref('')
const aiLoading = ref(false)
const aiConclusionLoading = ref(false)

const CONCLUSION_ITEM_ID = 'K7-4-conclusion'

// Load conclusion from allResponses
watch(
  () => props.allResponses.value,
  (responses) => {
    const item = responses.get(CONCLUSION_ITEM_ID)
    const raw = item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : '')
    auditConclusion.value = raw || ''
  },
  { immediate: true },
)

function handleConclusionBlur(): void {
  emit('save', CONCLUSION_ITEM_ID, { remark: auditConclusion.value })
}

// ─── Handlers ────────────────────────────────────────────────────────────────

async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入补助项目名称', '新增测算项', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '例如：XX设备购置补助',
      inputValidator: (val) => (!val?.trim() ? '项目名称不能为空' : true),
    })
    if (value?.trim()) calc.addRow(value.trim())
  } catch { /* cancelled */ }
}

/** AI生成分摊结论（section标题行按钮） */
async function handleAiGenerate(): Promise<void> {
  aiLoading.value = true
  try {
    const context = buildAiContext()
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'amort-conclusion',
      prompt: '请根据政府补助分摊测算结果，生成分摊合理性审计结论（简洁专业，关注差异及异常项）',
      context,
      existingContent: auditConclusion.value || undefined,
    })
    const content = res.data?.data?.content
    if (content) {
      auditConclusion.value = content
      emit('save', CONCLUSION_ITEM_ID, { remark: content })
      ElMessage.success('AI结论已生成')
    }
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.message || 'AI生成失败')
  } finally {
    aiLoading.value = false
  }
}

/** AI生成审计结论区按钮 */
async function handleAiConclusionGenerate(): Promise<void> {
  aiConclusionLoading.value = true
  try {
    const context = buildAiContext()
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'amort-conclusion',
      prompt: '请根据政府补助分摊测算结果，生成完整的审计结论，包括测算方法、差异分析及建议',
      context,
      existingContent: auditConclusion.value || undefined,
    })
    const content = res.data?.data?.content
    if (content) {
      auditConclusion.value = content
      emit('save', CONCLUSION_ITEM_ID, { remark: content })
      ElMessage.success('AI结论已生成')
    }
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.message || 'AI生成失败')
  } finally {
    aiConclusionLoading.value = false
  }
}

function buildAiContext(): string {
  const s = calc.subtotals.value
  const exceeded = calc.exceededItems.value
  return (
    `K7-4分摊测算：共${s.count}笔政府补助，` +
    `补助总额${fmtNum(s.grantTotal)}，测算分摊${fmtNum(s.calculatedAmort)}，` +
    `企业分摊${fmtNum(s.enterpriseAmort)}，差异合计${fmtNum(s.variance)}，` +
    `重要性水平${fmtNum(calc.materialityValue.value)}。` +
    (exceeded.length > 0
      ? `超重要性项${exceeded.length}项：${exceeded.map(r => `${r.project}(差异${fmtNum(r.variance)})`).join('、')}。`
      : '各项差异均未超过重要性水平。')
  )
}

// ─── Row class ───────────────────────────────────────────────────────────────

function calcRowClass({ row }: { row: any }): string {
  if (row.isVarianceExceeded) return 'variance-row'
  return ''
}

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function fmtNum(v: number | null | undefined): string {
  if (v == null) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k7-tab-amort-calc {
  padding: 12px;
  font-size: 13px;
}

/* ═══ 蓝色渐变引导区 ═══ */
.guide-steps {
  background: linear-gradient(135deg, #e6f4ff 0%, #bae0ff 100%);
  border-radius: 8px;
  padding: 14px 20px;
  margin-bottom: 14px;
}

.guide-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 24px;
}

.guide-step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #1d3557;
  font-weight: 500;
}

.step-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #1890ff;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}

/* ═══ Section Header ═══ */
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.header-actions {
  display: flex;
  gap: 8px;
}

/* ═══ 方法论上下文 ═══ */
.methodology-context {
  background: #fffbeb;
  border-left: 4px solid #f59e0b;
  padding: 10px 14px;
  margin-bottom: 12px;
  border-radius: 4px;
  font-size: 13px;
  color: #78350f;
  line-height: 1.6;
}

/* ═══ 差异预警 ═══ */
.variance-alert {
  margin-bottom: 12px;
}

/* ═══ 工具栏 ═══ */
.toolbar-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 6px;
}

.cross-ref-label {
  font-size: 12px;
  color: #909399;
}

/* ═══ 表格 ═══ */
.amort-table {
  font-size: 13px;
}

.amount-cell {
  font-variant-numeric: tabular-nums;
}

.formula-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
}

.formula-cell {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: #303133;
}

.formula-underline {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 1px;
}

.variance-exceeded {
  color: #f56c6c !important;
  font-weight: 700;
  background: #fef0f0;
  padding: 2px 4px;
  border-radius: 3px;
}

.exceed-tag {
  margin-left: 4px;
  vertical-align: middle;
}

/* 差异超过重要性的行红色浅背景 */
:deep(.variance-row) {
  background-color: rgba(245, 108, 108, 0.06) !important;
}

:deep(.variance-row:hover > td) {
  background-color: rgba(245, 108, 108, 0.12) !important;
}

:deep(.el-table) {
  font-size: 13px;
}

/* ═══ 合计行 ═══ */
.subtotal-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  margin: 12px 0;
  padding: 10px 14px;
  border-top: 2px solid #dcdfe6;
  background: #f5f7fa;
  border-radius: 0 0 6px 6px;
  font-size: 13px;
  font-weight: 500;
}

.subtotal-label {
  color: #606266;
  font-weight: 600;
}

.subtotal-item {
  color: #303133;
}

.subtotal-item b {
  font-variant-numeric: tabular-nums;
  margin-left: 4px;
}

/* ═══ 审计结论 ═══ */
.conclusion-card {
  margin-top: 16px;
}

.conclusion-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

/* ═══ 编制提示 ═══ */
.k7-details-tip {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 13px;
  color: #606266;
}

.k7-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
}

.k7-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
