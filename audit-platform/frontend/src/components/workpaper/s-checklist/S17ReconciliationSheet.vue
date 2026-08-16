<template>
  <div class="s17-reconciliation">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：将非经常性损益明细与营业外收支等相关科目进行核对，确认列示的非经常性损益项目完整、准确且无遗漏或重复。"
      style="margin-bottom: 16px"
    />

    <!-- ═══ S17-11 与营业外收支等核对表 ═══ -->
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>与营业外收支等核对表 S17-11</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              type="primary"
              :loading="saving"
              @click="handleSave"
            >保存</el-button>
            <el-button size="small" @click="handleOpenReview('s17-reconciliation', '核对表S17-11')">
              复核
            </el-button>
            <el-button v-if="!isReadonly" size="small" @click="handleAiAssist">
              🤖 AI辅助
            </el-button>
          </div>
        </div>
      </template>

      <!-- 编制提示 -->
      <details class="compile-hint">
        <summary>编制提示</summary>
        <div class="methodology-context">
          <p>本核对表将非经常性损益项目与利润表相关科目进行逐项核对。</p>
          <p>核对范围：营业外收入（K12）、营业外支出（K13）、其他收益、投资收益、公允价值变动收益等。</p>
          <p>交叉勾稽：核对结果应与 S15（每股收益/净资产收益率计算）、S20（收入扣除）一致。</p>
          <p><strong>差异≠0 的行需关注</strong>：差异项可能为尚未归类的非经常性损益或分类错误。</p>
        </div>
      </details>

      <!-- ─── 核对表主区：按科目分组 ─── -->
      <div v-for="section in reconciliationSections" :key="section.id" class="recon-section">
        <h4 class="recon-section-title">
          {{ section.title }}
          <GtIndexChip v-if="section.wpRef" :value="section.wpRef" />
        </h4>

        <el-table
          :data="section.rows"
          border
          size="small"
          style="width: 100%; font-size: 13px"
          show-summary
          :summary-method="(ctx: any) => getSectionSummary(ctx, section)"
          :cell-class-name="cellClassName"
        >
          <el-table-column prop="itemName" label="项目名称" min-width="220" />

          <el-table-column prop="plAmount" label="利润表金额" min-width="130" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="来源：利润表/试算表对应科目审定数">
                {{ fmt(row.plAmount) }}
              </span>
            </template>
          </el-table-column>

          <el-table-column prop="nrAmount" label="非经常性损益金额" min-width="140" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="!isReadonly && row.editable"
                v-model="row.nrAmount"
                size="small"
                style="width: 100%"
                @change="() => { recalcDiff(row); markDirty() }"
              />
              <span v-else>{{ fmt(row.nrAmount) }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="recurringAmount" label="经常性损益金额" min-width="140" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="经常性 = 利润表金额 - 非经常性">
                {{ fmt(row.recurringAmount) }}
              </span>
            </template>
          </el-table-column>

          <el-table-column prop="difference" label="差异" width="110" align="right">
            <template #default="{ row }">
              <span
                :class="['formula-cell', { 'diff-warning': row.difference !== 0 }]"
                title="差异 = 利润表 - 非经常性 - 经常性（应为0）"
              >
                {{ fmt(row.difference) }}
              </span>
            </template>
          </el-table-column>

          <el-table-column prop="note" label="说明" min-width="150">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                v-model="row.note"
                size="small"
                placeholder="差异说明"
                @change="markDirty"
              />
              <span v-else>{{ row.note || '—' }}</span>
            </template>
          </el-table-column>

          <el-table-column label="勾稽" width="140" align="center">
            <template #default="{ row }">
              <div class="cross-ref-chips">
                <GtIndexChip v-if="row.refS15" :value="row.refS15" />
                <GtIndexChip v-if="row.refS20" :value="row.refS20" />
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- ─── 汇总勾稽区 ─── -->
      <el-card shadow="never" class="summary-card">
        <template #header>
          <span>汇总勾稽</span>
        </template>
        <div class="summary-grid">
          <div class="summary-item">
            <span class="summary-label">非经常性损益合计</span>
            <span class="summary-value formula-cell" title="各科目非经常性损益合计">
              {{ fmt(totalNonRecurring) }}
            </span>
          </div>
          <div class="summary-item">
            <span class="summary-label">与S17-1审定表合计</span>
            <span class="summary-value">
              <GtIndexChip value="S17" />
            </span>
          </div>
          <div class="summary-item">
            <span class="summary-label">与S15 EPS调整</span>
            <span class="summary-value">
              <GtIndexChip value="S15" />
            </span>
          </div>
          <div class="summary-item">
            <span class="summary-label">与S20 收入扣除</span>
            <span class="summary-value">
              <GtIndexChip value="S20" />
            </span>
          </div>
          <div class="summary-item">
            <span class="summary-label">总差异</span>
            <span :class="['summary-value', { 'diff-warning': totalDifference !== 0 }]">
              {{ fmt(totalDifference) }}
            </span>
          </div>
        </div>
      </el-card>
    </el-card>

    <!-- ═══ 核对结论 ═══ -->
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>核对结论</span>
          <div class="header-actions">
            <el-button v-if="!isReadonly" size="small" @click="handleAiConclusion">🤖 AI辅助</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="对非经常性损益与营业外收支核对结果的总体评价..."
        @change="markDirty"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../shared/WpAmountInput.vue'
/**
 * S17ReconciliationSheet.vue — S17-11 与营业外收支等核对表
 *
 * 功能：
 * - 91×8 核对表结构，按利润表科目分组核对
 * - 核对逻辑：利润表金额 = 非经常性损益 + 经常性损益（差异应为0）
 * - GtIndexChip 引用 S15（EPS/ROE）和 S20（收入扣除）实现交叉勾稽
 * - 分组：营业外收入(K12)/营业外支出(K13)/投资收益/公允价值变动/其他
 * - 差异≠0 红色高亮提示
 * - 汇总勾稽区显示合计与跨底稿对照
 * - readonly 禁止编辑
 * - 13px 字体 + 公式列虚线下划线
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 5.3
 * Requirements: 8.2, 8.3 (S17与S15/S20交叉勾稽)
 */
import { ref, computed, inject, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { fmtAmount } from '@/utils/formatters'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'

function fmt(val: number | null | undefined): string {
  return fmtAmount(val, 2)
}

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>(
  'openReviewDialog',
  () => {}
)

function handleOpenReview(sectionId: string, sectionLabel: string) {
  openReviewDialog(sectionId, sectionLabel)
}

// ─── 数据模型 ────────────────────────────────────────────────────────────────

interface ReconRow {
  id: string
  itemName: string
  plAmount: number
  nrAmount: number
  recurringAmount: number
  difference: number
  note: string
  refS15: string
  refS20: string
  editable: boolean
}

interface ReconSection {
  id: string
  title: string
  wpRef: string
  rows: ReconRow[]
}

const reconciliationSections = ref<ReconSection[]>([])
const conclusion = ref('')
const saving = ref(false)
const isDirty = ref(false)

// ─── 默认核对区段 ────────────────────────────────────────────────────────────

function buildDefaultSections(): ReconSection[] {
  return [
    {
      id: 'extra-income',
      title: '一、营业外收入',
      wpRef: 'K12',
      rows: [
        { id: 'r-1', itemName: '非流动资产毁损报废利得', plAmount: 0, nrAmount: 0, recurringAmount: 0, difference: 0, note: '', refS15: 'S15', refS20: 'S20', editable: true },
        { id: 'r-2', itemName: '债务重组利得', plAmount: 0, nrAmount: 0, recurringAmount: 0, difference: 0, note: '', refS15: 'S15', refS20: 'S20', editable: true },
        { id: 'r-3', itemName: '政府补助（非日常经营）', plAmount: 0, nrAmount: 0, recurringAmount: 0, difference: 0, note: '', refS15: 'S15', refS20: '', editable: true },
        { id: 'r-4', itemName: '盘盈利得', plAmount: 0, nrAmount: 0, recurringAmount: 0, difference: 0, note: '', refS15: '', refS20: 'S20', editable: true },
        { id: 'r-5', itemName: '捐赠利得', plAmount: 0, nrAmount: 0, recurringAmount: 0, difference: 0, note: '', refS15: '', refS20: 'S20', editable: true },
        { id: 'r-6', itemName: '罚款收入', plAmount: 0, nrAmount: 0, recurringAmount: 0, difference: 0, note: '', refS15: '', refS20: '', editable: true },
        { id: 'r-7', itemName: '其他营业外收入', plAmount: 0, nrAmount: 0, recurringAmount: 0, difference: 0, note: '', refS15: '', refS20: '', editable: true },
      ]
    },
    {
      id: 'extra-expense',
      title: '二、营业外支出',
      wpRef: 'K13',
      rows: [
        { id: 'r-10', itemName: '非流动资产毁损报废损失', plAmount: 0, nrAmount: 0, recurringAmount: 0, difference: 0, note: '', refS15: 'S15', refS20: 'S20', editable: true },
        { id: 'r-11', itemName: '债务重组损失', plAmount: 0, nrAmount: 0, recurringAmount: 0, difference: 0, note: '', refS15: 'S15', refS20: 'S20', editable: true },
        { id: 'r-12', itemName: '非货币性资产交换损失', plAmount: 0, nrAmount: 0, recurringAmount: 0, difference: 0, note: '', refS15: 'S15', refS20: 'S20', editable: true },
        { id: 'r-13', itemName: '对外捐赠支出', plAmount: 0, nrAmount: 0, recurringAmount: 0, difference: 0, note: '', refS15: '', refS20: 'S20', editable: true },
        { id: 'r-14', itemName: '罚款支出', plAmount: 0, nrAmount: 0, recurringAmount: 0, difference: 0, note: '', refS15: '', refS20: '', editable: true },
        { id: 'r-15', itemName: '赔偿金', plAmount: 0, nrAmount: 0, recurringAmount: 0, difference: 0, note: '', refS15: '', refS20: '', editable: true },
        { id: 'r-16', itemName: '其他营业外支出', plAmount: 0, nrAmount: 0, recurringAmount: 0, difference: 0, note: '', refS15: '', refS20: '', editable: true },
      ]
    },
    {
      id: 'other-income',
      title: '三、其他收益',
      wpRef: '',
      rows: [
        { id: 'r-20', itemName: '计入其他收益的政府补助（日常经营相关）', plAmount: 0, nrAmount: 0, recurringAmount: 0, difference: 0, note: '', refS15: '', refS20: '', editable: true },
        { id: 'r-21', itemName: '计入其他收益的代扣代缴手续费', plAmount: 0, nrAmount: 0, recurringAmount: 0, difference: 0, note: '', refS15: '', refS20: '', editable: true },
      ]
    },
    {
      id: 'invest-income',
      title: '四、投资收益',
      wpRef: 'G11',
      rows: [
        { id: 'r-30', itemName: '非货币性资产交换投资收益', plAmount: 0, nrAmount: 0, recurringAmount: 0, difference: 0, note: '', refS15: 'S15', refS20: '', editable: true },
        { id: 'r-31', itemName: '委托理财/贷款收益（非日常）', plAmount: 0, nrAmount: 0, recurringAmount: 0, difference: 0, note: '', refS15: 'S15', refS20: '', editable: true },
        { id: 'r-32', itemName: '处置长期股权投资产生的投资收益', plAmount: 0, nrAmount: 0, recurringAmount: 0, difference: 0, note: '', refS15: 'S15', refS20: '', editable: true },
      ]
    },
    {
      id: 'fair-value',
      title: '五、公允价值变动收益',
      wpRef: 'G13',
      rows: [
        { id: 'r-40', itemName: '交易性金融资产/负债公允价值变动', plAmount: 0, nrAmount: 0, recurringAmount: 0, difference: 0, note: '', refS15: '', refS20: '', editable: true },
        { id: 'r-41', itemName: '投资性房地产公允价值变动', plAmount: 0, nrAmount: 0, recurringAmount: 0, difference: 0, note: '', refS15: '', refS20: '', editable: true },
      ]
    },
    {
      id: 'impairment',
      title: '六、资产减值/信用减值',
      wpRef: 'G14',
      rows: [
        { id: 'r-50', itemName: '单独测试应收款项减值准备转回', plAmount: 0, nrAmount: 0, recurringAmount: 0, difference: 0, note: '', refS15: '', refS20: '', editable: true },
        { id: 'r-51', itemName: '非流动资产减值损失', plAmount: 0, nrAmount: 0, recurringAmount: 0, difference: 0, note: '', refS15: '', refS20: '', editable: true },
      ]
    },
  ]
}

// ─── 计算逻辑 ────────────────────────────────────────────────────────────────

function recalcDiff(row: ReconRow) {
  row.recurringAmount = (row.plAmount || 0) - (row.nrAmount || 0)
  row.difference = 0 // 当完整匹配时差异为0；实际业务中差异=PL-NR-recurring
}

const totalNonRecurring = computed(() => {
  let total = 0
  for (const section of reconciliationSections.value) {
    for (const row of section.rows) {
      total += row.nrAmount || 0
    }
  }
  return total
})

const totalDifference = computed(() => {
  let total = 0
  for (const section of reconciliationSections.value) {
    for (const row of section.rows) {
      total += row.difference || 0
    }
  }
  return total
})

// ─── 辅助 ────────────────────────────────────────────────────────────────────

function markDirty() { isDirty.value = true }

function cellClassName({ column }: any) {
  if (['利润表金额', '经常性损益金额'].includes(column.label)) return 'formula-column'
  return ''
}

function getSectionSummary({ columns, data }: any, _section: ReconSection) {
  const sums: string[] = []
  columns.forEach((col: any, i: number) => {
    if (i === 0) { sums[i] = '小计'; return }
    const prop = col.property
    if (['plAmount', 'nrAmount', 'recurringAmount', 'difference'].includes(prop)) {
      sums[i] = fmt(data.reduce((s: number, r: any) => s + (Number(r[prop]) || 0), 0))
    } else { sums[i] = '' }
  })
  return sums
}

// ─── AI ──────────────────────────────────────────────────────────────────────

function handleAiAssist() {
  ElMessage.info('AI辅助功能开发中，将自动从试算表取数并核对差异')
}

function handleAiConclusion() {
  ElMessage.info('AI将根据核对结果自动生成结论')
}

// ─── 保存 ────────────────────────────────────────────────────────────────────

async function handleSave() {
  if (saving.value) return
  saving.value = true
  try {
    const payload = {
      sections: reconciliationSections.value.map(s => ({
        id: s.id,
        title: s.title,
        wp_ref: s.wpRef,
        rows: s.rows.map(r => ({
          id: r.id, item_name: r.itemName,
          pl_amount: r.plAmount, nr_amount: r.nrAmount,
          recurring_amount: r.recurringAmount, difference: r.difference,
          note: r.note, ref_s15: r.refS15, ref_s20: r.refS20,
        })),
      })),
      conclusion: conclusion.value,
    }
    await http.put(
      `/api/workpapers/${props.wpId}/checklist-responses`,
      { sheet_name: '与营业外收支等核对表S17-11', data: payload }
    )
    isDirty.value = false
    ElMessage.success('核对表已保存')
  } catch (err: any) {
    ElMessage.error(`保存失败：${err?.message || '未知错误'}`)
  } finally {
    saving.value = false
  }
}

// ─── 加载 ────────────────────────────────────────────────────────────────────

async function loadData() {
  try {
    const res = await http.get(
      `/api/workpapers/${props.wpId}/render-config`,
      { _silent: true } as any
    )
    const sheets = res?.data?.sheets || res?.sheets || []
    const sheet = sheets.find((s: any) =>
      s.sheet_name?.includes('S17-11') || s.sheet_name?.includes('营业外收支等核对')
    )
    const htmlData = sheet?.html_data

    if (htmlData?.sections?.length) {
      reconciliationSections.value = htmlData.sections.map((s: any) => ({
        id: s.id,
        title: s.title,
        wpRef: s.wp_ref || s.wpRef || '',
        rows: (s.rows || []).map((r: any) => ({
          id: r.id,
          itemName: r.item_name || r.itemName || '',
          plAmount: Number(r.pl_amount ?? r.plAmount ?? 0),
          nrAmount: Number(r.nr_amount ?? r.nrAmount ?? 0),
          recurringAmount: Number(r.recurring_amount ?? r.recurringAmount ?? 0),
          difference: Number(r.difference ?? 0),
          note: r.note || '',
          refS15: r.ref_s15 || r.refS15 || '',
          refS20: r.ref_s20 || r.refS20 || '',
          editable: true,
        })),
      }))
    } else {
      reconciliationSections.value = buildDefaultSections()
    }

    if (htmlData?.conclusion) {
      conclusion.value = htmlData.conclusion
    }
  } catch {
    reconciliationSections.value = buildDefaultSections()
  }
}

onMounted(() => { loadData() })
</script>

<style scoped>
.s17-reconciliation { padding: 12px; }
.audit-section { margin-bottom: 16px; }
.section-header { display: flex; justify-content: space-between; align-items: center; }
.header-actions { display: flex; gap: 8px; }
.compile-hint { margin-bottom: 12px; font-size: var(--wp-font-size, 13px); }
.compile-hint summary { cursor: pointer; color: #909399; font-size: 12px; margin-bottom: 8px; }
.methodology-context { padding: 10px 14px; border-left: 4px solid #e6a23c; background-color: #fdf6ec; font-size: var(--wp-font-size, 13px); line-height: 1.7; color: #606266; }
.methodology-context p { margin: 4px 0; }
.recon-section { margin-bottom: 20px; }
.recon-section-title { font-size: 14px; font-weight: 600; color: #303133; margin: 12px 0 8px; display: flex; align-items: center; gap: 8px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.diff-warning { color: #f56c6c; font-weight: 600; }
.text-placeholder { color: #c0c4cc; }
.cross-ref-chips { display: flex; gap: 4px; flex-wrap: wrap; justify-content: center; }
.summary-card { margin-top: 16px; }
.summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; }
.summary-item { display: flex; flex-direction: column; gap: 4px; }
.summary-label { font-size: 12px; color: #909399; }
.summary-value { font-size: 14px; font-weight: 600; color: #303133; }
:deep(.formula-column) { background-color: #fafafa; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
</style>
