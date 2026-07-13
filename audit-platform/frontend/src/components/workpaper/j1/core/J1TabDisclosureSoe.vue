<template>
  <div class="j1-tab-disclosure-soe">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        审计目标：验证应付职工薪酬附注披露（国有企业口径）各项目期初余额、本期增减、期末余额的完整性与准确性，确保与审定表、明细表勾稽一致。
      </template>
    </el-alert>

    <!-- （1）应付职工薪酬列示 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="group-header">
          <span class="section-title">（1）应付职工薪酬列示</span>
          <el-button size="small" type="primary" plain :disabled="isReadonly" @click="addSummaryRow()">+ 新增行</el-button>
        </div>
      </template>
      <el-table :data="summaryRows" border size="small"
        :row-class-name="({ row }) => row.isSubtotal ? 'subtotal-row' : ''">
        <el-table-column label="项 目" min-width="240">
          <template #default="{ row }">
            <template v-if="row.isSubtotal"><span class="subtotal-label">{{ row.label }}</span></template>
            <el-input v-else v-model="row.label" size="small" :disabled="isReadonly" placeholder="输入项目名称" />
          </template>
        </el-table-column>
        <el-table-column label="期初余额" align="right">
          <template #default="{ row }">
            <template v-if="row.isSubtotal">{{ fmtN(row.beginBalance) }}</template>
            <el-input-number v-else v-model="row.beginBalance" :controls="false" :precision="2" size="small" :disabled="isReadonly" @change="recalcRow(row)" />
          </template>
        </el-table-column>
        <el-table-column label="本期增加" align="right">
          <template #default="{ row }">
            <template v-if="row.isSubtotal">{{ fmtN(row.increase) }}</template>
            <el-input-number v-else v-model="row.increase" :controls="false" :precision="2" size="small" :disabled="isReadonly" @change="recalcRow(row)" />
          </template>
        </el-table-column>
        <el-table-column label="本期减少" align="right">
          <template #default="{ row }">
            <template v-if="row.isSubtotal">{{ fmtN(row.decrease) }}</template>
            <el-input-number v-else v-model="row.decrease" :controls="false" :precision="2" size="small" :disabled="isReadonly" @change="recalcRow(row)" />
          </template>
        </el-table-column>
        <el-table-column label="期末余额" align="right" class-name="auto-calc-col">
          <template #default="{ row }"><span class="formula-cell" title="期末=期初+增加-减少">{{ fmtN(row.endBalance) }}</span></template>
        </el-table-column>
        <el-table-column label="" width="36" align="center">
          <template #default="{ row }">
            <el-button v-if="!row.isSubtotal" type="danger" link size="small" :disabled="isReadonly" @click="removeSummaryRow(row.id)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- （2）短期薪酬列示 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="group-header">
          <span class="section-title">（2）短期薪酬列示</span>
          <el-button size="small" type="primary" plain :disabled="isReadonly" @click="addRow('short_term')">+ 新增行</el-button>
        </div>
      </template>
      <el-table :data="[...shortTermRows, shortTermSubtotal]" border size="small"
        highlight-current-row @current-change="(r) => selectedRow = r"
        :row-class-name="({ row }) => row.isSubtotal ? 'subtotal-row' : (row.indent ? 'indent-row' : '')">
        <el-table-column label="项 目" min-width="240">
          <template #default="{ row }">
            <template v-if="row.isSubtotal"><span class="subtotal-label">{{ row.label }}</span></template>
            <template v-else-if="row.indent">
              <el-input v-model="row.label" size="small" :disabled="isReadonly" style="padding-left:16px" placeholder="输入子项名称" />
            </template>
            <template v-else><span>{{ row.label }}</span></template>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" align="right">
          <template #default="{ row }">
            <template v-if="row.isSubtotal">{{ fmtN(row.beginBalance) }}</template>
            <el-input-number v-else v-model="row.beginBalance" :controls="false" :precision="2" size="small" :disabled="isReadonly" @change="recalcRow(row)" />
          </template>
        </el-table-column>
        <el-table-column label="本期增加" align="right">
          <template #default="{ row }">
            <template v-if="row.isSubtotal">{{ fmtN(row.increase) }}</template>
            <el-input-number v-else v-model="row.increase" :controls="false" :precision="2" size="small" :disabled="isReadonly" @change="recalcRow(row)" />
          </template>
        </el-table-column>
        <el-table-column label="本期减少" align="right">
          <template #default="{ row }">
            <template v-if="row.isSubtotal">{{ fmtN(row.decrease) }}</template>
            <el-input-number v-else v-model="row.decrease" :controls="false" :precision="2" size="small" :disabled="isReadonly" @change="recalcRow(row)" />
          </template>
        </el-table-column>
        <el-table-column label="期末余额" align="right" class-name="auto-calc-col">
          <template #default="{ row }"><span class="formula-cell" title="期末=期初+增加-减少">{{ fmtN(row.endBalance) }}</span></template>
        </el-table-column>
        <el-table-column label="" width="36" align="center">
          <template #default="{ row }">
            <el-button v-if="!row.isSubtotal && row.indent" type="danger" link size="small" :disabled="isReadonly" @click="removeRow(row.id, 'short_term')">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- （3）设定提存计划列示 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="group-header">
          <span class="section-title">（3）设定提存计划列示</span>
          <el-button size="small" type="primary" plain :disabled="isReadonly" @click="addRow('post_employment')">+ 新增行</el-button>
        </div>
      </template>
      <el-table :data="[...postEmploymentRows, postEmploymentSubtotal]" border size="small"
        highlight-current-row @current-change="(r) => selectedRow = r"
        :row-class-name="({ row }) => row.isSubtotal ? 'subtotal-row' : (row.indent ? 'indent-row' : '')">
        <el-table-column label="项 目" min-width="240">
          <template #default="{ row }">
            <template v-if="row.isSubtotal"><span class="subtotal-label">{{ row.label }}</span></template>
            <template v-else-if="row.indent">
              <el-input v-model="row.label" size="small" :disabled="isReadonly" style="padding-left:16px" placeholder="输入子项名称" />
            </template>
            <template v-else><span>{{ row.label }}</span></template>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" align="right">
          <template #default="{ row }">
            <template v-if="row.isSubtotal">{{ fmtN(row.beginBalance) }}</template>
            <el-input-number v-else v-model="row.beginBalance" :controls="false" :precision="2" size="small" :disabled="isReadonly" @change="recalcRow(row)" />
          </template>
        </el-table-column>
        <el-table-column label="本期增加" align="right">
          <template #default="{ row }">
            <template v-if="row.isSubtotal">{{ fmtN(row.increase) }}</template>
            <el-input-number v-else v-model="row.increase" :controls="false" :precision="2" size="small" :disabled="isReadonly" @change="recalcRow(row)" />
          </template>
        </el-table-column>
        <el-table-column label="本期减少" align="right">
          <template #default="{ row }">
            <template v-if="row.isSubtotal">{{ fmtN(row.decrease) }}</template>
            <el-input-number v-else v-model="row.decrease" :controls="false" :precision="2" size="small" :disabled="isReadonly" @change="recalcRow(row)" />
          </template>
        </el-table-column>
        <el-table-column label="期末余额" align="right" class-name="auto-calc-col">
          <template #default="{ row }"><span class="formula-cell" title="期末=期初+增加-减少">{{ fmtN(row.endBalance) }}</span></template>
        </el-table-column>
        <el-table-column label="" width="36" align="center">
          <template #default="{ row }">
            <el-button v-if="!row.isSubtotal && row.indent" type="danger" link size="small" :disabled="isReadonly" @click="removeRow(row.id, 'post_employment')">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 说明 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="note-header">
          <span class="section-title">说明</span>
          <el-button size="small" type="primary" plain @click="aiGenerate('soe-note')" :disabled="isReadonly">🤖 AI辅助</el-button>
        </div>
      </template>
      <el-input type="textarea" v-model="soeNote" :disabled="isReadonly"
        :autosize="{ minRows: 3, maxRows: 6 }" size="small"
        placeholder="1.企业本期为职工提供的各项非货币性福利的形式、金额及其计算依据。&#10;2.企业应说明设立或参与的设定提存计划的性质、计算缴费金额的公式或依据。&#10;3.存在设定受益计划的企业，应说明设定受益计划的特征及与之相关的风险、在财务报表中确认的金额。" />
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 依据 CAS 9 及国有企业财务披露要求，按项目列示期初余额、本期增加（计提）、本期减少（发放）、期末余额。</p>
        <p>2. 灰色底纹"期末余额"列为自动计算列（期初+增加-减少），不可手动编辑。</p>
        <p>3. 附注披露金额应与审定表（J1-1）期末审定数、明细表（J1-2）勾稽一致。</p>
        <p>4. 国企版简化格式，不含占比列。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
  isReadonly?: boolean
}>()
const isReadonly = props.isReadonly ?? false

interface DRow {
  id: string; label: string; category: string; indent?: number
  beginBalance: number; increase: number; decrease: number; endBalance: number
  isSubtotal?: boolean
}
const selectedRow = ref<DRow | null>(null)
const soeNote = ref('')

// （1）应付职工薪酬汇总
const summaryRows = ref<DRow[]>([
  { id: 's-1', label: '短期薪酬', category: 'summary', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 's-2', label: '离职后福利-设定提存计划', category: 'summary', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 's-3', label: '辞退福利', category: 'summary', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 's-4', label: '一年内到期的其他福利', category: 'summary', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 's-5', label: '其他', category: 'summary', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 's-total', label: '合 计', category: 'summary', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0, isSubtotal: true },
])

// （2）短期薪酬
const shortTermData = ref<DRow[]>([
  { id: 'st-1', label: '工资、奖金、津贴和补贴', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'st-2', label: '职工福利费', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'st-3', label: '社会保险费', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'st-4', label: '其中：医疗保险费', category: 'short_term', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'st-5', label: '工伤保险费', category: 'short_term', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'st-6', label: '生育保险费', category: 'short_term', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'st-7', label: '其他', category: 'short_term', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'st-8', label: '住房公积金', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'st-9', label: '工会经费和职工教育经费', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'st-10', label: '短期带薪缺勤', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'st-11', label: '短期利润分享计划', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'st-12', label: '其他短期薪酬', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
])
const shortTermRows = computed(() => shortTermData.value)
const shortTermSubtotal = computed<DRow>(() => {
  const top = shortTermData.value.filter(r => !r.indent)
  return { id: 'st-total', label: '合 计', category: 'short_term', isSubtotal: true,
    beginBalance: top.reduce((s, r) => s + r.beginBalance, 0),
    increase: top.reduce((s, r) => s + r.increase, 0),
    decrease: top.reduce((s, r) => s + r.decrease, 0),
    endBalance: top.reduce((s, r) => s + r.endBalance, 0) }
})

// （3）设定提存计划
const postEmploymentData = ref<DRow[]>([
  { id: 'pe-1', label: '离职后福利', category: 'post_employment', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'pe-2', label: '其中：基本养老保险费', category: 'post_employment', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'pe-3', label: '失业保险费', category: 'post_employment', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'pe-4', label: '企业年金缴费', category: 'post_employment', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'pe-5', label: '其他', category: 'post_employment', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'pe-6', label: '其他长期职工福利（不适用的删除）', category: 'post_employment', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'pe-7', label: '其中：xxx', category: 'post_employment', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { id: 'pe-8', label: '其他', category: 'post_employment', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
])
const postEmploymentRows = computed(() => postEmploymentData.value)
const postEmploymentSubtotal = computed<DRow>(() => {
  const top = postEmploymentData.value.filter(r => !r.indent)
  return { id: 'pe-total', label: '合 计', category: 'post_employment', isSubtotal: true,
    beginBalance: top.reduce((s, r) => s + r.beginBalance, 0),
    increase: top.reduce((s, r) => s + r.increase, 0),
    decrease: top.reduce((s, r) => s + r.decrease, 0),
    endBalance: top.reduce((s, r) => s + r.endBalance, 0) }
})

function recalcRow(row: DRow) { row.endBalance = (row.beginBalance || 0) + (row.increase || 0) - (row.decrease || 0) }

function addSummaryRow() {
  const newRow: DRow = { id: `s-${Date.now()}`, label: '', category: 'summary', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 }
  const totalIdx = summaryRows.value.findIndex(r => r.isSubtotal)
  if (totalIdx >= 0) summaryRows.value.splice(totalIdx, 0, newRow)
  else summaryRows.value.push(newRow)
}
function removeSummaryRow(id: string) {
  const idx = summaryRows.value.findIndex(r => r.id === id)
  if (idx >= 0) summaryRows.value.splice(idx, 1)
}

function addRow(category: string) {
  const arr = category === 'short_term' ? shortTermData : postEmploymentData
  const newRow: DRow = { id: `${category}-${Date.now()}`, label: '', category, indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 }
  const sel = selectedRow.value
  if (sel && !sel.isSubtotal && sel.category === category) {
    const idx = arr.value.findIndex(r => r.id === sel.id)
    if (idx >= 0) { arr.value.splice(idx + 1, 0, newRow); return }
  }
  arr.value.push(newRow)
}
function removeRow(id: string, category: string) {
  const arr = category === 'short_term' ? shortTermData : postEmploymentData
  const idx = arr.value.findIndex(r => r.id === id)
  if (idx >= 0) arr.value.splice(idx, 1)
}

function fmtN(v: number | null | undefined): string {
  if (!v) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function aiGenerate(section: string) {
  try {
    const { data } = await (await import('@/utils/http')).default.post(
      `/api/workpapers/${props.wpId}/ai/generate-text`,
      { section: `j1-disclosure-soe-${section}`, context: {} }
    )
    const text = data?.data?.content || data?.content || ''
    if (text) soeNote.value = text
  } catch { /* AI不可用时静默 */ }
}

onMounted(() => { /* 从 htmlData 恢复 */ })
</script>

<style scoped>
.j1-tab-disclosure-soe { padding: 16px; }
.audit-objective { margin-bottom: 14px; }
.section-card { margin-bottom: 16px; }
.section-card :deep(.el-card__header) { padding: 8px 16px; }
.section-card :deep(.el-card__body) { padding: 12px 16px; }
.section-card :deep(.el-table) { font-size: 13px !important; }
.section-card :deep(.el-table th), .section-card :deep(.el-table td) { font-size: 13px !important; padding: 4px 6px !important; }
.section-card :deep(.el-input-number) { width: 100%; }
.section-card :deep(.el-input-number .el-input__inner) { text-align: right; font-size: 13px; }
.section-card :deep(.el-input__inner) { font-size: 13px; }
.section-title { font-weight: 600; font-size: 14px; }
.group-header { display: flex; justify-content: space-between; align-items: center; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
:deep(.subtotal-row) { background-color: #f5f7fa !important; font-weight: 600; }
:deep(.indent-row) { color: #606266; }
.subtotal-label { font-weight: 600; }
.section-note-area { padding: 8px 0; }
.note-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.note-label { font-size: 13px; font-weight: 500; color: #606266; }
.section-note-area :deep(.el-textarea__inner) { font-size: 13px; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
</style>
