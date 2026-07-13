<template>
  <div class="j1-tab-adjudication">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        审计目标：确认应付职工薪酬各分类期初、期末审定数的准确性，分析本期变动率异常项（&gt;30% 标红），形成审定结论并回写试算平衡表（科目 2211）。
      </template>
    </el-alert>

    <!-- 双模式切换 -->
    <div class="mode-bar">
      <el-segmented v-model="mode" :options="['HTML', 'OnlyOffice']" size="small" />
      <span class="chip-wrap"><GtIndexChip value="wp:J1-1" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ groups.length }} 组分类</el-tag>
    </div>

    <template v-if="mode === 'HTML'">
      <!-- 各分类分组 -->
      <el-card v-for="group in groups" :key="group.category" shadow="never" class="group-card">
        <template #header>
          <div class="group-header">
            <span class="group-title">{{ group.label }}</span>
            <el-button size="small" type="primary" plain
              :disabled="isReadonly" @click="addRowToCategory(group.category)">
              + 新增行
            </el-button>
          </div>
        </template>
        <el-table :data="[...group.rows, group.subtotal]" border size="small"
          highlight-current-row @current-change="(row) => onCurrentRowChange(group.category, row)"
          :row-class-name="({ row }) => row.id?.startsWith('subtotal') ? 'subtotal-row' : ''">
          <!-- 项目名称 -->
          <el-table-column label="项目名称" min-width="160" fixed>
            <template #default="{ row }">
              <template v-if="row.id?.startsWith('subtotal')">
                <span class="subtotal-label">{{ row.label }}</span>
              </template>
              <template v-else-if="isDynamicCategory(row.category) || row.indent">
                <el-input v-model="row.label" size="small" :disabled="isReadonly"
                  :style="{ paddingLeft: (row.indent || 0) * 16 + 'px' }"
                  :placeholder="row.indent ? '输入子项名称' : '输入项目名称'" @change="onCellChange(row)" />
              </template>
              <template v-else>
                <span :style="{ paddingLeft: (row.indent || 0) * 16 + 'px' }">{{ row.label }}</span>
              </template>
            </template>
          </el-table-column>
          <!-- 期初数 -->
          <el-table-column label="期初数" align="center">
            <el-table-column label="未审数" width="100" align="right">
              <template #default="{ row }">
                <template v-if="row.id?.startsWith('subtotal')">{{ fmtAmount(row.beginUnadj) }}</template>
                <el-input-number v-else v-model="row.beginUnadj" :disabled="isReadonly"
                  size="small" :controls="false" :precision="2" @change="onCellChange(row)" />
              </template>
            </el-table-column>
            <el-table-column label="调整" width="90" align="right">
              <template #default="{ row }">
                <template v-if="row.id?.startsWith('subtotal')">{{ fmtAmount(row.beginAje) }}</template>
                <el-input-number v-else v-model="row.beginAje" :disabled="isReadonly"
                  size="small" :controls="false" :precision="2" @change="onCellChange(row)" />
              </template>
            </el-table-column>
            <el-table-column label="审定数" width="100" align="right" class-name="auto-calc-col">
              <template #default="{ row }">
                <span class="formula-cell" title="审定=未审+调整">{{ fmtAmount(row.beginAudited) }}</span>
              </template>
            </el-table-column>
          </el-table-column>
          <!-- 期末数 -->
          <el-table-column label="期末数" align="center">
            <el-table-column label="未审数" width="100" align="right">
              <template #default="{ row }">
                <template v-if="row.id?.startsWith('subtotal')">{{ fmtAmount(row.endUnadj) }}</template>
                <el-input-number v-else v-model="row.endUnadj" :disabled="isReadonly"
                  size="small" :controls="false" :precision="2" @change="onCellChange(row)" />
              </template>
            </el-table-column>
            <el-table-column label="调整" width="90" align="right">
              <template #default="{ row }">
                <template v-if="row.id?.startsWith('subtotal')">{{ fmtAmount(row.endAje) }}</template>
                <el-input-number v-else v-model="row.endAje" :disabled="isReadonly"
                  size="small" :controls="false" :precision="2" @change="onCellChange(row)" />
              </template>
            </el-table-column>
            <el-table-column label="审定数" width="100" align="right" class-name="auto-calc-col">
              <template #default="{ row }">
                <span class="formula-cell" title="审定=未审+调整">{{ fmtAmount(row.endAudited) }}</span>
              </template>
            </el-table-column>
          </el-table-column>
          <!-- 本期未审vs上期审定 -->
          <el-table-column label="本期未审数与上期审定数比较" align="center">
            <el-table-column label="变动额" width="100" align="right" class-name="auto-calc-col">
              <template #default="{ row }">{{ fmtAmount(row.unadjVsPriorDiff) }}</template>
            </el-table-column>
            <el-table-column label="变动率" width="80" align="right" class-name="auto-calc-col">
              <template #default="{ row }">
                <span :class="{ 'text-danger': Math.abs(row.unadjVsPriorRate) > 30 }">
                  {{ row.unadjVsPriorRate?.toFixed(1) }}%
                </span>
              </template>
            </el-table-column>
          </el-table-column>
          <!-- 本期审定vs上期审定 -->
          <el-table-column label="本期审定数与上期审定数比较" align="center">
            <el-table-column label="变动额" width="100" align="right" class-name="auto-calc-col">
              <template #default="{ row }">{{ fmtAmount(row.auditedVsPriorDiff) }}</template>
            </el-table-column>
            <el-table-column label="变动率" width="80" align="right" class-name="auto-calc-col">
              <template #default="{ row }">
                <span :class="{ 'text-danger': Math.abs(row.auditedVsPriorRate) > 30 }">
                  {{ row.auditedVsPriorRate?.toFixed(1) }}%
                </span>
              </template>
            </el-table-column>
          </el-table-column>
          <!-- 原因分析 -->
          <el-table-column label="原因分析" min-width="140">
            <template #default="{ row }">
              <template v-if="row.id?.startsWith('subtotal')"></template>
              <el-input v-else v-model="row.analysis" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }"
                :disabled="isReadonly" size="small" placeholder="" @change="onCellChange(row)" />
            </template>
          </el-table-column>
          <!-- 操作列（动态行/子项可删） -->
          <el-table-column label="" width="40" align="center">
            <template #default="{ row }">
              <el-button v-if="!row.id?.startsWith('subtotal') && (isDynamicCategory(row.category) || row.indent)"
                type="danger" link size="small" :disabled="isReadonly" @click="removeRow(row.id)">✕</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- 合计行 -->
      <el-card shadow="never" class="total-card">
        <div class="total-row">
          <span>应付职工薪酬合计</span>
          <span>期初审定: {{ fmtAmount(grandTotal.beginAudited) }}</span>
          <span>期末审定: {{ fmtAmount(grandTotal.endAudited) }}</span>
          <span :class="{ 'text-danger': Math.abs(grandTotal.auditedVsPriorRate) > 30 }">
            审定变动率: {{ grandTotal.auditedVsPriorRate?.toFixed(1) }}%
          </span>
        </div>
      </el-card>

      <!-- 试算平衡表勾稽 -->
      <div class="tb-reconcile">
        <table class="tb-reconcile-table">
          <tr>
            <td class="tb-label">试算平衡表数</td>
            <td class="tb-value">{{ fmtAmount(tbBalance) }}</td>
            <td class="tb-label" style="padding-left: 32px;">期初审定</td>
            <td class="tb-value">{{ fmtAmount(grandTotal.beginAudited) }}</td>
            <td class="tb-label" style="padding-left: 32px;">期末审定</td>
            <td class="tb-value">{{ fmtAmount(grandTotal.endAudited) }}</td>
          </tr>
          <tr>
            <td class="tb-label">差异数</td>
            <td class="tb-value" :class="{ 'text-danger': Math.abs(tbDiff) > 0.01 }">{{ fmtAmount(tbDiff) }}</td>
            <td colspan="4">
              <el-tag v-if="Math.abs(tbDiff) < 0.01" type="success" size="small">✓ 勾稽一致</el-tag>
              <el-tag v-else type="danger" size="small">✕ 存在差异，请核查</el-tag>
            </td>
          </tr>
        </table>
      </div>

      <!-- 1、审计说明 -->
      <el-card shadow="never" class="audit-note-card">
        <template #header>
          <div class="card-header">
            <span>1、审计说明</span>
            <el-button size="small" type="primary" plain @click="aiGenerate('note')" :disabled="isReadonly">🤖 AI辅助</el-button>
          </div>
        </template>
        <el-input type="textarea" v-model="auditNote" :disabled="isReadonly"
          :autosize="{ minRows: 5 }" placeholder="填写审计说明..." @change="saveAuditNote" />
      </el-card>

      <!-- 2、审计结论 -->
      <el-card shadow="never" class="audit-note-card">
        <template #header>
          <div class="card-header">
            <span>2、审计结论</span>
            <el-button size="small" type="primary" plain @click="aiGenerate('conclusion')" :disabled="isReadonly">🤖 AI辅助</el-button>
          </div>
        </template>
        <el-input type="textarea" v-model="auditConclusion" :disabled="isReadonly"
          :autosize="{ minRows: 3 }" placeholder="填写审计结论..." @change="saveAuditConclusion" />
      </el-card>
    </template>

    <!-- OnlyOffice降级 -->
    <div v-else class="oo-placeholder">
      <el-empty description="OnlyOffice 模式（审定表J1-1）" />
    </div>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 依据 CAS 9《职工薪酬》，审定表按短期薪酬/离职后福利/辞退福利分组列示。</p>
        <p>2. 灰色底纹列为自动计算列（审定数=未审数+调整），不可手动编辑。</p>
        <p>3. 本期审定数与上期审定数变动率超过 30% 自动标红，须在原因分析栏说明。</p>
        <p>4. 审定合计应与明细表（J1-2）、试算平衡表科目 2211 期末余额勾稽一致。</p>
        <p>5. 辞退福利为动态行，根据实际辞退计划增减行。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useJ1Adjudication, type AdjudicationRow } from '@/composables/workpaper/j1/useJ1Adjudication'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
  isReadonly?: boolean
}>()

const isReadonly = props.isReadonly ?? false
const mode = ref('HTML')
const htmlDataRef = ref(props.htmlData || {})
const { rows, groups, grandTotal, initFromHtmlData, updateRow } = useJ1Adjudication(htmlDataRef)

/** 试算平衡表勾稽 */
const tbBalance = ref(0)
const tbDiff = computed(() => grandTotal.value.endAudited - tbBalance.value)

/** 审计说明 / 结论 */
const NOTE_KEY = 'J1-adjudication-audit-note'
const CONCLUSION_KEY = 'J1-adjudication-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

/** 动态行分类（辞退福利可增删） */
const DYNAMIC_CATEGORIES = new Set(['severance'])
function isDynamicCategory(cat: string) { return DYNAMIC_CATEGORIES.has(cat) }

/** 当前选中行（按分组追踪） */
const currentRowByCategory = ref<Record<string, AdjudicationRow | null>>({})
function onCurrentRowChange(category: string, row: AdjudicationRow | null) {
  currentRowByCategory.value[category] = row
}

onMounted(() => {
  if (props.htmlData) initFromHtmlData(props.htmlData)
  else initFromHtmlData({})
  // 恢复试算平衡表数
  if (props.htmlData?.tb_data) {
    const tb = props.htmlData.tb_data as Record<string, number>
    tbBalance.value = tb.audited_amount || 0
  }
  // 恢复审计说明/结论
  const responses = props.htmlData?.responses_snapshot as Record<string, { remark?: string }> | undefined
  if (responses) {
    if (responses[NOTE_KEY]?.remark) auditNote.value = responses[NOTE_KEY].remark
    if (responses[CONCLUSION_KEY]?.remark) auditConclusion.value = responses[CONCLUSION_KEY].remark
  }
})

function saveAuditNote(val: string) {
  auditNote.value = val
}
function saveAuditConclusion(val: string) {
  auditConclusion.value = val
}

/** AI辅助生成 */
async function aiGenerate(section: 'note' | 'conclusion') {
  try {
    const { data } = await (await import('@/utils/http')).default.post(
      `/api/workpapers/${props.wpId}/ai/generate-text`,
      { section: `j1-adjudication-${section}`, context: { endAudited: grandTotal.value.endAudited, beginAudited: grandTotal.value.beginAudited } }
    )
    const text = data?.data?.content || data?.content || ''
    if (text) {
      if (section === 'note') auditNote.value = text
      else auditConclusion.value = text
    }
  } catch { /* 降级：AI不可用时静默 */ }
}

function onCellChange(row: AdjudicationRow) {
  updateRow(row.id, 'beginUnadj', row.beginUnadj)
}

function addRowToCategory(category: string) {
  const newRow: AdjudicationRow = {
    id: `row-${category}-${Date.now()}`,
    label: '',
    category: category as AdjudicationRow['category'],
    indent: category === 'severance' ? 0 : 1,
    beginUnadj: 0, beginAje: 0, beginAudited: 0,
    endUnadj: 0, endAje: 0, endAudited: 0,
    unadjVsPriorDiff: 0, unadjVsPriorRate: 0,
    auditedVsPriorDiff: 0, auditedVsPriorRate: 0,
    analysis: '',
  }
  // 插入到选中行的下一行；未选中则追加到该分类末尾
  const selectedRow = currentRowByCategory.value[category]
  if (selectedRow && !selectedRow.id?.startsWith('subtotal')) {
    const idx = rows.value.findIndex(r => r.id === selectedRow.id)
    if (idx >= 0) {
      rows.value.splice(idx + 1, 0, newRow)
      return
    }
  }
  // 追加到该分类最后一行之后
  const lastIdx = rows.value.map((r, i) => r.category === category ? i : -1).filter(i => i >= 0).pop()
  if (lastIdx !== undefined && lastIdx >= 0) {
    rows.value.splice(lastIdx + 1, 0, newRow)
  } else {
    rows.value.push(newRow)
  }
}

function removeRow(id: string) {
  const idx = rows.value.findIndex(r => r.id === id)
  if (idx >= 0) rows.value.splice(idx, 1)
}

function fmtAmount(val: number | null | undefined): string {
  if (val === null || val === undefined) return '-'
  if (val === 0) return '0'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.j1-tab-adjudication { padding: 16px; }
.audit-objective { margin-bottom: 12px; }
.mode-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.chip-wrap { display: inline-flex; align-items: center; }
.group-card { margin-bottom: 16px; }
.group-card :deep(.el-table) { font-size: 13px !important; }
.group-card :deep(.el-table th), .group-card :deep(.el-table td) { font-size: 13px !important; padding: 4px 6px !important; }
.group-card :deep(.el-input-number) { width: 100%; }
.group-card :deep(.el-input-number .el-input__inner) { text-align: right; font-size: 13px; }
.group-card :deep(.el-input__inner) { font-size: 13px; }
.group-card :deep(.el-textarea__inner) { font-size: 13px; }
.group-header { display: flex; justify-content: space-between; align-items: center; }
.group-title { font-weight: 600; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
:deep(.subtotal-row) { background-color: #f5f7fa !important; font-weight: 600; }
.subtotal-label { font-weight: 600; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.total-card { background: #ecf5ff; }
.total-row { display: flex; gap: 24px; align-items: center; font-weight: 600; font-size: 13px; }
.tb-reconcile { margin: 16px 0; padding: 12px 16px; background: #f8f9fa; border: 1px solid #e8e8e8; border-radius: 6px; }
.tb-reconcile-table { width: auto; border-collapse: collapse; font-size: 13px; }
.tb-reconcile-table td { padding: 4px 8px; vertical-align: middle; }
.tb-label { font-weight: 500; color: #606266; white-space: nowrap; }
.tb-value { font-family: 'Courier New', monospace; font-weight: 600; color: #303133; }
.audit-note-card { margin-top: 12px; }
.audit-note-card :deep(.el-card__header) { padding: 8px 16px; font-weight: 600; font-size: 13px; }
.audit-note-card :deep(.el-card__body) { padding: 12px 16px; }
.audit-note-card :deep(.el-textarea__inner) { font-size: 13px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.text-danger { color: #f56c6c; }
</style>
