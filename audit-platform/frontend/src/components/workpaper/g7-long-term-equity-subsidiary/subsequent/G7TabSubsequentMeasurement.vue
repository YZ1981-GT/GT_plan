<!--
  G7TabSubsequentMeasurement.vue — G7-10 子公司后续计量测试表（成本法）

  48行×11列：被投资单位|期初余额|本期增加|减值计提|被投资方宣告股利|持股比例|
  应确认投资收益(公式=calcCostMethodIncome)|期末余额(公式=calcSubsequentBalance)|
  企业账面期末|差异|审计结论

  方法论上下文: CAS2成本法后续计量规则
  公式列: calcCostMethodIncome(dividend, ratio) + calcSubsequentBalance(opening, addition, impairment)
  差异=期末余额(计算)-企业账面 → 差异>重要性水平时红色高亮
  动态行增删+导入导出(sheet='G7-10')

  Spec: .kiro/specs/g7-long-term-equity-subsidiary/ Task 6.1
  Requirements: 4.1, 4.2, 4.3, 4.4
-->
<template>
  <div class="g7-tab-subsequent">
    <!-- 方法论上下文区域（琥珀色左边线+浅黄背景） -->
    <div class="methodology-context">
      <p class="methodology-title">CAS2 成本法后续计量规则：</p>
      <ul class="methodology-list">
        <li>子公司个别报表采用<strong>成本法</strong>核算长期股权投资</li>
        <li>除追加投资/减值外，<strong>不调整长投账面价值</strong></li>
        <li>被投资方宣告分派现金股利时确认<strong>投资收益</strong>（= 股利 × 持股比例）</li>
        <li>期末账面 = 期初 + 本期增加(追加投资) - 减值计提</li>
        <li>差异 = 计算期末余额 - 企业账面期末数（差异超重要性水平需关注）</li>
      </ul>
    </div>

    <!-- 蓝色渐变引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-no">①</span>逐行录入被投资单位后续计量数据</div>
        <div class="guide-step"><span class="step-no">②</span>系统自动计算投资收益和期末余额</div>
        <div class="guide-step"><span class="step-no">③</span>核对企业期末数，差异自动标红</div>
        <div class="guide-step"><span class="step-no">④</span>AI辅助生成审计结论</div>
      </div>
    </div>

    <!-- 重要性水平设置 -->
    <div class="materiality-bar">
      <span class="materiality-label">重要性水平：</span>
      <el-input-number
        v-if="!isReadonly"
        v-model="materialityLevel"
        :controls="false"
        :precision="2"
        size="small"
        style="width: 160px"
        placeholder="重要性水平(元)"
      />
      <span v-else class="materiality-value">{{ fmtNum(materialityLevel) }}</span>
      <span class="materiality-hint">（|差异| 超过此值将红色高亮）</span>
    </div>

    <!-- 顶部工具栏 -->
    <div class="section-head">
      <h3 class="sheet-title">G7-10 子公司后续计量测试表（成本法）</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
          + 被投资单位
        </el-button>
        <el-dropdown trigger="click" size="small" @command="handleImportExportCommand">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export">导出数据</el-dropdown-item>
              <el-dropdown-item command="import">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="handleAiConclusion">🤖 AI辅助</el-button>
        <el-button size="small" @click="openReviewDialog('G7-10-subsequent')">💬复核</el-button>
      </div>
    </div>

    <!-- 表格（48行×11列，max-height虚拟滚动） -->
    <el-table
      :data="rows"
      border
      size="small"
      max-height="580"
      highlight-current-row
      row-key="id"
      class="subsequent-table"
    >
      <el-table-column label="序号" width="55" align="center" fixed>
        <template #default="{ row }">{{ row.seq }}</template>
      </el-table-column>

      <el-table-column label="被投资单位" min-width="150" fixed>
        <template #default="{ row }">
          <span class="investee-name">{{ row.investeeName }}</span>
        </template>
      </el-table-column>

      <el-table-column label="期初余额" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.openingBalance" size="small"
            :controls="false" :precision="2" class="compact-num"
            @change="(v: number) => updateFieldWithRecalc(row.id, 'openingBalance', v)" />
          <span v-else>{{ fmtNum(row.openingBalance) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="本期增加" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.additionInvestment" size="small"
            :controls="false" :precision="2" class="compact-num"
            @change="(v: number) => updateFieldWithRecalc(row.id, 'additionInvestment', v)" />
          <span v-else>{{ fmtNum(row.additionInvestment) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="减值计提" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.impairmentLoss" size="small"
            :controls="false" :precision="2" class="compact-num"
            @change="(v: number) => updateFieldWithRecalc(row.id, 'impairmentLoss', v)" />
          <span v-else>{{ fmtNum(row.impairmentLoss) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="被投资方宣告股利" min-width="140" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.declaredDividend" size="small"
            :controls="false" :precision="2" class="compact-num"
            @change="(v: number) => updateFieldWithRecalc(row.id, 'declaredDividend', v)" />
          <span v-else>{{ fmtNum(row.declaredDividend) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="持股比例" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.shareholdingRatio" size="small"
            :controls="false" :precision="4" :min="0" :max="1" class="compact-num"
            @change="(v: number) => updateFieldWithRecalc(row.id, 'shareholdingRatio', v)" />
          <span v-else>{{ (row.shareholdingRatio * 100).toFixed(2) }}%</span>
        </template>
      </el-table-column>

      <el-table-column label="应确认投资收益" min-width="140" align="right">
        <template #default="{ row }">
          <el-tooltip content="投资收益 = 被投资方宣告股利 × 持股比例" placement="top">
            <span class="formula-cell">{{ fmtNum(row.investmentIncome) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>

      <el-table-column label="期末余额" min-width="130" align="right">
        <template #default="{ row }">
          <el-tooltip content="期末余额 = 期初 + 本期增加 - 减值计提" placement="top">
            <span class="formula-cell">{{ fmtNum(row.closingBalance) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>

      <el-table-column label="企业账面期末" min-width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.companyEndingBalance" size="small"
            :controls="false" :precision="2" class="compact-num"
            @change="(v: number) => updateFieldWithRecalc(row.id, 'companyEndingBalance', v)" />
          <span v-else>{{ fmtNum(row.companyEndingBalance) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="差异" min-width="120" align="right">
        <template #default="{ row }">
          <el-tooltip content="差异 = 期末余额(计算) - 企业账面期末" placement="top">
            <span class="formula-cell" :class="varianceClass(row.variance)">
              {{ fmtNum(row.variance) }}
            </span>
          </el-tooltip>
        </template>
      </el-table-column>

      <el-table-column label="审计结论" min-width="150">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.auditConclusion" size="small" style="width:100%"
            @change="(v: string) => updateField(row.id, 'auditConclusion', v)">
            <el-option value="无差异" label="无差异" />
            <el-option value="差异可接受" label="差异可接受" />
            <el-option value="需进一步调查" label="需进一步调查" />
            <el-option value="需调整" label="需调整" />
          </el-select>
          <span v-else>{{ row.auditConclusion }}</span>
        </template>
      </el-table-column>

      <!-- 操作列（删除） -->
      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-popconfirm :title="`确认删除「${row.investeeName}」?`" @confirm="removeRow(row.id)">
            <template #reference>
              <el-button type="danger" link size="small">✕</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部：审计结论 el-card + AI辅助按钮 -->
    <el-card class="conclusion-card" shadow="never">
      <template #header>
        <div class="conclusion-header">
          <span>综合审计结论</span>
          <el-button size="small" :disabled="isReadonly" @click="handleAiConclusion">
            🤖 AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="对子公司投资后续计量测试结果的综合评价（投资收益确认是否合理、账面价值增减是否准确）..."
      />
    </el-card>

    <!-- 编制提示 details 折叠 -->
    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>子公司投资采用成本法：不因被投资方净资产变动而调整长投账面</li>
        <li>投资收益确认时点：被投资方<strong>宣告</strong>分派现金股利时（非实际收到时）</li>
        <li>投资收益 = 宣告股利 × 持股比例，不区分取得前后利润</li>
        <li>本期增加：追加投资（增资）计入初始投资成本</li>
        <li>减值计提：长投存在减值迹象时，按可收回金额与账面的差额计提</li>
        <li>差异为0表示后续计量准确，差异较大时需核实原因</li>
        <li>持股比例变动但未丧失控制权时，仍用成本法（合并报表调整权益）</li>
      </ul>
    </details>
  </div>
</template>


<script setup lang="ts">
/**
 * G7TabSubsequentMeasurement — G7-10 子公司后续计量测试表（成本法）
 *
 * Spec: .kiro/specs/g7-long-term-equity-subsidiary/ Task 6.1
 *
 * 48行×11列：被投资单位|期初余额|本期增加|减值计提|被投资方宣告股利|持股比例|
 * 应确认投资收益(公式)|期末余额(公式)|企业账面期末|差异|审计结论
 *
 * 公式引擎：
 * - calcCostMethodIncome(dividend, ratio) → 投资收益
 * - calcSubsequentBalance(opening, addition, impairment) → 期末余额
 * - 差异 = closingBalance - companyEndingBalance
 *
 * 差异>重要性水平时红色高亮
 * 动态行增删(ElMessageBox.prompt命名) + 导入导出(sheet='G7-10') + AI辅助
 *
 * Requirements: 4.1, 4.2, 4.3, 4.4
 */
import { ref, reactive, inject, computed, toRef, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  calcCostMethodIncome,
  calcSubsequentBalance,
  parseNum,
} from '../../composables/useG7SubFormulaEngine'
import { useG7SubImportExport } from '../../composables/useG7SubImportExport'
import http from '@/utils/http'

// ─── 类型定义 ────────────────────────────────────────────────────────────────

interface G7SubsequentRow {
  id: string
  seq: number
  investeeName: string
  openingBalance: number
  additionInvestment: number
  impairmentLoss: number
  declaredDividend: number
  shareholdingRatio: number
  investmentIncome: number      // 公式: declaredDividend × shareholdingRatio
  closingBalance: number        // 公式: opening + addition - impairment
  companyEndingBalance: number
  variance: number              // 公式: closingBalance - companyEndingBalance
  auditConclusion: string
}

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'save', payload: { rows: G7SubsequentRow[]; materialityLevel: number; conclusion: string }): void
}>()

const isReadonly = computed(() => props.readonly ?? false)

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// ─── 导入导出 composable ─────────────────────────────────────────────────────

const wpIdRef = toRef(props, 'wpId')
const { exportTemplate, exportData, importData } = useG7SubImportExport({ wpId: wpIdRef })

// ─── 行数据 ──────────────────────────────────────────────────────────────────

const rows = reactive<G7SubsequentRow[]>([])
const conclusion = ref<string>('')
const materialityLevel = ref<number>(0)

function createEmptyRow(seq: number, investeeName: string): G7SubsequentRow {
  return {
    id: crypto.randomUUID(),
    seq,
    investeeName,
    openingBalance: 0,
    additionInvestment: 0,
    impairmentLoss: 0,
    declaredDividend: 0,
    shareholdingRatio: 0,
    investmentIncome: 0,
    closingBalance: 0,
    companyEndingBalance: 0,
    variance: 0,
    auditConclusion: '',
  }
}

// ─── 公式重算（核心） ────────────────────────────────────────────────────────

function recalcRow(row: G7SubsequentRow): void {
  // P4: 投资收益 = 被投资方宣告股利 × 持股比例
  row.investmentIncome = calcCostMethodIncome(row.declaredDividend, row.shareholdingRatio)
  // P5: 期末余额 = 期初 + 本期增加 - 减值计提
  row.closingBalance = calcSubsequentBalance(row.openingBalance, row.additionInvestment, row.impairmentLoss)
  // 差异 = 期末余额(计算) - 企业账面期末
  row.variance = Math.round((row.closingBalance - parseNum(row.companyEndingBalance)) * 100) / 100
}

// ─── 字段更新 ────────────────────────────────────────────────────────────────

function updateField(id: string, field: keyof G7SubsequentRow, value: any) {
  const row = rows.find(r => r.id === id)
  if (row) {
    ;(row as any)[field] = value
  }
}

function updateFieldWithRecalc(id: string, field: keyof G7SubsequentRow, value: any) {
  const row = rows.find(r => r.id === id)
  if (row) {
    ;(row as any)[field] = value ?? 0
    recalcRow(row)
  }
}

// ─── 重要性水平判断 ──────────────────────────────────────────────────────────

/**
 * |差异| > 重要性水平 → 红色高亮
 */
function isOverMateriality(variance: number): boolean {
  const level = parseNum(materialityLevel.value)
  if (level <= 0) return false
  return Math.abs(parseNum(variance)) > level
}

function varianceClass(variance: number): string {
  if (isOverMateriality(variance)) return 'variance-warning'
  if (Math.abs(variance) > 0.01) return 'variance-exists'
  return ''
}

// ─── 动态行增删（ElMessageBox.prompt + 名称唯一性校验） ──────────────────────

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入被投资单位名称', '新增被投资单位', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '被投资单位名称不能为空',
      inputValidator: (val: string) => {
        if (!val?.trim()) return '被投资单位名称不能为空'
        const exists = rows.some(r => r.investeeName === val.trim())
        if (exists) return `「${val.trim()}」已存在，请勿重复添加`
        return true
      },
    })
    if (value?.trim()) {
      const newRow = createEmptyRow(rows.length + 1, value.trim())
      rows.push(newRow)
      ElMessage.success(`已添加「${value.trim()}」`)
    }
  } catch {
    // 用户取消
  }
}

function removeRow(id: string) {
  const idx = rows.findIndex(r => r.id === id)
  if (idx >= 0) {
    rows.splice(idx, 1)
    rows.forEach((r, i) => { r.seq = i + 1 })
  }
}

// ─── AI生成审计结论 ──────────────────────────────────────────────────────────

async function handleAiConclusion() {
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/g7-sub/ai/subsequent-conclusion`,
      { existingContent: conclusion.value, relatedContext: { sheet: 'G7-10', rows: [...rows], materialityLevel: materialityLevel.value } },
    )
    const text = res?.data?.data?.conclusion || res?.data?.conclusion || res?.data?.text || ''
    if (text) {
      conclusion.value = text
      ElMessage.success('AI结论已生成')
    } else {
      ElMessage.warning('AI未能生成有效结论')
    }
  } catch {
    ElMessage.info('AI辅助生成后续计量结论(subsequent-conclusion)将在AI模块完成后启用')
  }
}

// ─── 导入导出 ────────────────────────────────────────────────────────────────

async function handleImportExportCommand(command: string) {
  if (command === 'template') {
    await exportTemplate('G7-10')
  } else if (command === 'export') {
    await exportData('G7-10')
  } else if (command === 'import') {
    // 触发文件选择
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.xlsx,.xls'
    input.onchange = async (e: Event) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (!file) return
      const result = await importData('G7-10', file)
      if (result) {
        // 重新加载数据（后端已保存，重新获取）
        ElMessage.success('导入完成，请刷新数据')
      }
    }
    input.click()
  }
}

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function fmtNum(v: unknown): string {
  if (v === 0) return '0.00'
  if (typeof v === 'number') {
    return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return String(v ?? '')
}

// ─── 数据加载 ────────────────────────────────────────────────────────────────

function loadFromHtmlData(data: Record<string, any> | null): void {
  if (!data) return
  rows.length = 0

  const subData = data.subsequentMeasurement || data.subsequent_measurement || data
  const rawRows = subData?.rows || []
  conclusion.value = subData?.conclusion || ''
  materialityLevel.value = parseNum(subData?.materialityLevel ?? subData?.materiality_level ?? 0)

  if (Array.isArray(rawRows) && rawRows.length > 0) {
    for (let i = 0; i < rawRows.length; i++) {
      const raw = rawRows[i]
      const row: G7SubsequentRow = {
        ...createEmptyRow(i + 1, raw.investeeName || ''),
        ...raw,
        seq: i + 1,
        id: raw.id || crypto.randomUUID(),
      }
      rows.push(row)
      recalcRow(row)
    }
  }
}

/**
 * 导出当前数据（供父组件保存调用）
 */
function getData(): { rows: G7SubsequentRow[]; materialityLevel: number; conclusion: string } {
  return {
    rows: [...rows],
    materialityLevel: materialityLevel.value,
    conclusion: conclusion.value,
  }
}

defineExpose({ getData, loadFromHtmlData })

onMounted(() => {
  loadFromHtmlData(props.htmlData)
})
</script>

<style scoped>
.g7-tab-subsequent { padding: 12px; font-size: var(--wp-font-size, 13px); }

/* 方法论上下文（琥珀色左边线+浅黄背景） */
.methodology-context {
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #fffbeb;
  border-left: 4px solid #f59e0b;
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
  line-height: 1.7;
}
.methodology-title { margin: 0 0 6px; font-weight: 600; color: #92400e; }
.methodology-list { margin: 0; padding-left: 18px; color: #78350f; }
.methodology-list li { margin-bottom: 2px; }

/* 蓝色渐变引导区 */
.guide-area {
  margin-bottom: 16px;
  padding: 12px 16px;
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  border-radius: 6px;
}
.guide-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 24px;
}
.guide-step {
  font-size: var(--wp-font-size, 13px);
  color: #1e40af;
  line-height: 1.6;
}
.step-no {
  display: inline-block;
  width: 20px;
  height: 20px;
  line-height: 20px;
  text-align: center;
  background: #3b82f6;
  color: #fff;
  border-radius: 50%;
  font-size: 11px;
  margin-right: 6px;
}

/* 重要性水平栏 */
.materiality-bar {
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.materiality-label { font-weight: 500; color: #303133; white-space: nowrap; }
.materiality-value { font-weight: 600; color: #409eff; }
.materiality-hint { font-size: 11px; color: #909399; }

/* 顶部工具栏 */
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; align-items: center; }

/* 表格 */
.subsequent-table { font-size: var(--wp-font-size, 13px); }
.compact-num { width: 100%; }
.investee-name { font-weight: 500; color: #303133; }

/* 公式列：虚线下划线 + cursor:help */
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 1px;
}

/* 差异颜色 */
.variance-warning { color: #f56c6c; font-weight: 600; }
.variance-exists { color: #e6a23c; font-weight: 500; }

/* 审计结论卡片 */
.conclusion-card { margin-top: 16px; }
.conclusion-header { display: flex; justify-content: space-between; align-items: center; }

/* 编制提示 */
.prep-hint { margin-top: 16px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; font-weight: 500; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; line-height: 1.8; }
</style>
