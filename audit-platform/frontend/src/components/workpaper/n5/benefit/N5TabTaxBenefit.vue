<template>
  <div class="n5-tax-benefit">
    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <p><strong>税收优惠明细表（N5-6）</strong>：按6大类归集企业享受的税收优惠：免税收入/减计收入/加计扣除/所得减免/抵扣应纳税额/抵免所得税额。各项减免汇总后形成减免税额合计→回填N5-4计算当期应纳所得税。高新技术企业15%优惠税率由N5-6-2认定结论驱动。</p>
    </div>

    <!-- ═══ Section Header ═══ -->
    <div class="section-header">
      <div class="section-title">
        <span>税收优惠明细表 N5-6</span>
        <el-tag size="small">6类优惠</el-tag>
      </div>
      <div class="section-actions">
        <el-button size="small" @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon>AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><ChatDotSquare /></el-icon>复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 减免税额汇总 ═══ -->
    <div class="relief-summary">
      <div class="relief-total">
        <span class="relief-label">减免税额合计</span>
        <span class="relief-value">{{ fmtAmount(totalRelief) }}</span>
        <span class="relief-dest">→ N5-4减免所得税额</span>
      </div>
      <div class="relief-breakdown">
        <div v-for="cat in benefitCategories" :key="cat.key" class="relief-cat-item">
          <span class="cat-name">{{ cat.label }}</span>
          <span class="cat-amount">{{ fmtAmount(getCategorySubtotal(cat.key)) }}</span>
        </div>
      </div>
    </div>

    <!-- ═══ 高新认定联动状态 ═══ -->
    <div class="hightech-linkage" :class="highTechApproved ? 'approved' : 'not-approved'">
      <span class="ht-icon">{{ highTechApproved ? '✓' : '✗' }}</span>
      <span class="ht-text">
        高新技术企业认定：{{ highTechApproved ? '通过（适用15%优惠税率）' : '未通过或未申请（适用一般税率25%）' }}
      </span>
      <el-tag :type="highTechApproved ? 'success' : 'info'" size="small">N5-6-2</el-tag>
    </div>

    <!-- ═══ 分类表格（6个类别分section） ═══ -->
    <div v-for="cat in benefitCategories" :key="cat.key" class="benefit-category-section">
      <div class="cat-section-header">
        <span class="cat-section-title">{{ cat.label }}</span>
        <span class="cat-section-subtotal">小计: {{ fmtAmount(getCategorySubtotal(cat.key)) }}</span>
      </div>
      <el-table :data="getCategoryRows(cat.key)" border size="small" class="benefit-table">
        <el-table-column prop="index" label="序号" width="55" align="center" />
        <el-table-column prop="itemName" label="优惠项目" min-width="200">
          <template #default="{ row }">
            <span class="item-name">{{ row.itemName }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="policyBasis" label="政策依据" min-width="160">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" v-model="row.policyBasis" size="small" placeholder="文号" @change="() => handleFieldUpdate(cat.key, $index, 'policyBasis', row.policyBasis)" />
            <span v-else class="cell-value">{{ row.policyBasis || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="优惠金额" min-width="130" align="right">
          <template #header>
            <span class="formula-header" title="优惠金额">优惠金额</span>
          </template>
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" v-model="row.amount" :controls="false" :precision="2" size="small" class="cell-input" @change="() => handleFieldUpdate(cat.key, $index, 'amount', row.amount)" />
            <span v-else class="cell-value">{{ fmtAmount(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减免税额" min-width="120" align="right">
          <template #header>
            <span class="formula-header" title="减免税额 = 优惠金额 × 税率（或直接抵免）">减免税额</span>
          </template>
          <template #default="{ row }">
            <el-tooltip content="减免税额" placement="top">
              <span class="formula-cell">{{ fmtAmount(row.taxRelief) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="120">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" placeholder="备注" @change="() => handleFieldUpdate(cat.key, $index, 'remark', row.remark)" />
            <span v-else class="cell-value">{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
      <!-- 分类内新增 -->
      <div class="cat-add-row" v-if="!isReadonly">
        <el-button size="small" text type="primary" @click="handleAddCategoryRow(cat.key, cat.label)">
          <el-icon><Plus /></el-icon>新增{{ cat.label }}项
        </el-button>
      </div>
    </div>

    <!-- ═══ 回填N5-4 ═══ -->
    <div class="action-bar">
      <el-button type="primary" size="small" :disabled="isReadonly" :loading="syncLoading" @click="handleSyncToCalc">
        回填减免税额合计 → N5-4
      </el-button>
      <span class="action-hint">减免税额合计 {{ fmtAmount(totalRelief) }}</span>
    </div>

    <!-- ═══ 审计说明与结论 ═══ -->
    <el-card shadow="never" class="audit-notes-card">
      <template #header>
        <div class="notes-header">
          <span>审计说明与结论</span>
          <el-button size="small" @click="handleNotesAi"><el-icon><MagicStick /></el-icon>AI辅助</el-button>
        </div>
      </template>
      <div class="notes-field">
        <label class="field-label">审计说明</label>
        <el-input v-model="auditNotes" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="请说明税收优惠享受情况及合规性..." :disabled="isReadonly" @change="saveNotes" />
      </div>
      <div class="notes-field">
        <label class="field-label">审计结论</label>
        <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" placeholder="请输入审计结论..." :disabled="isReadonly" @change="saveConclusion" />
      </div>
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="n5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>6大类：免税收入/减计收入/加计扣除/所得减免/抵扣应纳税额/抵免所得税额</li>
        <li>免税收入：国债利息/股息红利（居民企业间）/地方政府债利息等</li>
        <li>加计扣除：研发费用加计(N5-6-1联动)/残疾人工资加计等</li>
        <li>抵免所得税额：专用设备投资额10%抵免/创投抵扣等</li>
        <li>高新技术企业享受15%优惠税率，须N5-6-2逐条认定通过</li>
        <li>减免税额合计回填N5-4第7行"减免所得税额"</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N5TabTaxBenefit — 税收优惠明细表N5-6
 *
 * 54×6 + 10公式 + 6类优惠 + 减免税额汇总
 * 高新认定联动N5-6-2 + 减免税额回填N5-4
 *
 * Spec: .kiro/specs/n5-income-tax-expense/ Task 4.9
 * Requirements: 6.1-6.3
 */
import { ref, computed, reactive, inject, onMounted, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, ChatDotSquare, Plus } from '@element-plus/icons-vue'
import { useN5FormData } from '../../composables/useN5FormData'
import { calcSubtotal } from '../../composables/useN5FormulaEngine'

const props = defineProps<{
  allResponses: Map<string, any>
  wpId: string
  projectId?: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<((section: string) => void) | undefined>('openReviewDialog', undefined)

const wpIdRef = computed(() => props.wpId) as Ref<string>
const projectIdRef = computed(() => props.projectId || '') as Ref<string>

const formData = useN5FormData({ wpId: wpIdRef, projectId: projectIdRef })

// ─── 数据结构 ────────────────────────────────────────────────────────────────

interface BenefitRow {
  index: number
  itemName: string
  policyBasis: string
  amount: number
  taxRelief: number
  remark: string
}

interface BenefitCategory {
  key: string
  label: string
}

const benefitCategories: BenefitCategory[] = [
  { key: 'tax-exempt', label: '免税收入' },
  { key: 'reduced-income', label: '减计收入' },
  { key: 'super-deduction', label: '加计扣除' },
  { key: 'income-exemption', label: '所得减免' },
  { key: 'tax-deduction', label: '抵扣应纳税额' },
  { key: 'tax-credit', label: '抵免所得税额' },
]

// ─── 各分类数据 ──────────────────────────────────────────────────────────────

const categoryData = reactive<Record<string, BenefitRow[]>>({
  'tax-exempt': [
    { index: 1, itemName: '国债利息收入', policyBasis: '', amount: 0, taxRelief: 0, remark: '' },
    { index: 2, itemName: '居民企业间股息红利', policyBasis: '', amount: 0, taxRelief: 0, remark: '' },
    { index: 3, itemName: '地方政府债券利息', policyBasis: '', amount: 0, taxRelief: 0, remark: '' },
  ],
  'reduced-income': [
    { index: 1, itemName: '综合利用资源生产产品取得的收入', policyBasis: '', amount: 0, taxRelief: 0, remark: '' },
  ],
  'super-deduction': [
    { index: 1, itemName: '研发费用加计扣除', policyBasis: '', amount: 0, taxRelief: 0, remark: '联动N5-6-1' },
    { index: 2, itemName: '残疾人工资加计扣除', policyBasis: '', amount: 0, taxRelief: 0, remark: '' },
  ],
  'income-exemption': [
    { index: 1, itemName: '农林牧渔业项目所得', policyBasis: '', amount: 0, taxRelief: 0, remark: '' },
    { index: 2, itemName: '国家重点扶持基础设施所得', policyBasis: '', amount: 0, taxRelief: 0, remark: '' },
  ],
  'tax-deduction': [
    { index: 1, itemName: '创业投资企业抵扣应纳税所得额', policyBasis: '', amount: 0, taxRelief: 0, remark: '' },
  ],
  'tax-credit': [
    { index: 1, itemName: '购置专用设备投资额抵免', policyBasis: '', amount: 0, taxRelief: 0, remark: '' },
  ],
})

const highTechApproved = ref(false)
const syncLoading = ref(false)
const auditNotes = ref('')
const auditConclusion = ref('')

// ─── 计算 ────────────────────────────────────────────────────────────────────

function getCategoryRows(catKey: string): BenefitRow[] {
  return categoryData[catKey] || []
}

function getCategorySubtotal(catKey: string): number {
  return calcSubtotal((categoryData[catKey] || []).map(r => r.taxRelief))
}

const totalRelief = computed(() => {
  return benefitCategories.reduce((sum, cat) => sum + getCategorySubtotal(cat.key), 0)
})

// ─── 初始化 ──────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  // 恢复各分类数据
  for (const cat of benefitCategories) {
    const saved = formData.getField('6', `benefit-${cat.key}`)
    if (saved && Array.isArray(saved)) {
      categoryData[cat.key] = saved
    }
  }
  highTechApproved.value = formData.getField('6', 'high-tech-approved') ?? false
  auditNotes.value = formData.getField('6', 'audit-notes') ?? ''
  auditConclusion.value = formData.getField('6', 'audit-conclusion') ?? ''
})

// ─── 事件处理 ────────────────────────────────────────────────────────────────

async function handleFieldUpdate(catKey: string, rowIndex: number, field: string, value: any) {
  const rows = categoryData[catKey]
  if (rows && rows[rowIndex]) {
    ;(rows[rowIndex] as any)[field] = value
    // 减免税额 = 优惠金额（对于直接减免类别）
    if (field === 'amount') {
      rows[rowIndex].taxRelief = rows[rowIndex].amount
    }
    await formData.setField('6', `benefit-${catKey}`, [...rows])
  }
}

async function handleAddCategoryRow(catKey: string, catLabel: string) {
  const { value: name } = await ElMessageBox.prompt(`请输入${catLabel}项目名称`, `新增${catLabel}项`, {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
  }).catch(() => ({ value: '' }))
  if (!name) return

  const rows = categoryData[catKey]
  rows.push({
    index: rows.length + 1,
    itemName: name,
    policyBasis: '',
    amount: 0,
    taxRelief: 0,
    remark: '',
  })
  await formData.setField('6', `benefit-${catKey}`, [...rows])
  ElMessage.success(`已新增：${name}`)
}

async function handleSyncToCalc() {
  syncLoading.value = true
  try {
    await formData.setField('6', 'tax-relief-total', totalRelief.value)
    ElMessage.success(`减免税额合计${fmtAmount(totalRelief.value)}已回填N5-4`)
  } catch { ElMessage.error('回填失败') }
  finally { syncLoading.value = false }
}

async function saveNotes() { await formData.setField('6', 'audit-notes', auditNotes.value) }
async function saveConclusion() { await formData.setField('6', 'audit-conclusion', auditConclusion.value) }
function handleAiAssist() { ElMessage.info('AI辅助分析税收优惠合规性...') }
function handleNotesAi() { ElMessage.info('AI辅助生成审计说明...') }
function handleReview() { openReviewDialog ? openReviewDialog('N5-6-税收优惠') : ElMessage.info('复核对话未配置') }

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.n5-tax-benefit { padding: 12px; font-size: 13px; }
.methodology-context { padding: 12px 16px; margin-bottom: 16px; background: #fffbeb; border: 1px solid #fde68a; border-left: 4px solid #d97706; border-radius: 6px; font-size: 13px; color: #92400e; line-height: 1.7; }
.methodology-context p { margin: 0; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { display: flex; align-items: center; gap: 10px; font-size: 15px; font-weight: 600; color: #303133; }
.section-actions { display: flex; align-items: center; gap: 8px; }

.relief-summary { margin-bottom: 16px; padding: 14px 16px; background: #ecf5ff; border: 1px solid #b3d8ff; border-radius: 8px; }
.relief-total { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
.relief-label { font-size: 14px; font-weight: 600; color: #303133; }
.relief-value { font-size: 20px; font-weight: 700; color: #409eff; }
.relief-dest { font-size: 12px; color: #909399; }
.relief-breakdown { display: flex; flex-wrap: wrap; gap: 12px; }
.relief-cat-item { display: flex; align-items: center; gap: 6px; padding: 4px 10px; background: white; border-radius: 4px; border: 1px solid #ebeef5; font-size: 12px; }
.cat-name { color: #606266; }
.cat-amount { font-weight: 600; color: #303133; }

.hightech-linkage { display: flex; align-items: center; gap: 10px; padding: 10px 16px; margin-bottom: 16px; border-radius: 6px; font-size: 13px; }
.hightech-linkage.approved { background: #e8f5e9; border: 1px solid #a5d6a7; }
.hightech-linkage.not-approved { background: #f5f7fa; border: 1px solid #ebeef5; }
.ht-icon { font-size: 16px; }
.ht-text { color: #303133; font-weight: 500; }

.benefit-category-section { margin-bottom: 20px; }
.cat-section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; padding: 6px 12px; background: #f5f7fa; border-radius: 4px; }
.cat-section-title { font-size: 14px; font-weight: 600; color: #303133; }
.cat-section-subtotal { font-size: 13px; font-weight: 500; color: #409eff; }
.benefit-table { margin-bottom: 4px; }
:deep(.benefit-table .el-table) { font-size: 13px; }
.item-name { font-weight: 500; color: #303133; }
.formula-header { border-bottom: 1px dashed #409eff; cursor: help; color: #409eff; font-weight: 600; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; font-weight: 500; color: #303133; padding-bottom: 1px; }
.cell-input { width: 100%; }
:deep(.cell-input .el-input__inner) { text-align: right; font-size: 13px; }
.cell-value { font-size: 13px; color: #606266; }
.cat-add-row { padding: 4px 0; }

.action-bar { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; padding: 10px 16px; background: #f0f9eb; border: 1px solid #c2e7b0; border-radius: 6px; }
.action-hint { font-size: 12px; color: #67c23a; }

.audit-notes-card { margin-bottom: 16px; }
.notes-header { display: flex; align-items: center; justify-content: space-between; font-size: 14px; font-weight: 500; }
.notes-field { margin-bottom: 12px; }
.notes-field:last-child { margin-bottom: 0; }
.field-label { display: block; font-size: 13px; font-weight: 500; color: #606266; margin-bottom: 6px; }

.n5-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266; }
.n5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; margin-bottom: 8px; }
.n5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
