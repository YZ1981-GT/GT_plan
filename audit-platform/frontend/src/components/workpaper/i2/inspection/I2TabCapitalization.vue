<template>
  <div class="i2-capitalization">
    <div class="section-header">
      <span class="section-title">I2-6 研发项目资本化时点判断</span>
      <div class="section-actions">
        <el-button size="small" type="default" text @click="handleReview">复核</el-button>
      </div>
    </div>

    <!-- 一、审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>一、审计目标</template>
      <ol class="obj-list">
        <li v-for="(o, i) in CAS6_OBJECTIVES" :key="i">{{ o }}</li>
      </ol>
    </el-alert>

    <div class="methodology-context">
      <p>
        <b>编制逻辑（CAS6 §9）：</b>
        研究阶段支出费用化 → 开发阶段支出仅当<strong>五条件同时满足</strong>方可资本化 →
        记录资本化时点与依据 → 与无形资产明细勾稽 → 回写 I2-2「资本化起点」。
        无法区分研究/开发阶段的支出全部费用化。
      </p>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-right">
        <GtIndexChip value="wp:I2-6" :context-project-id="projectId" />
        <el-tag size="small" type="success">可资本化 {{ summary.metCount }}</el-tag>
        <el-tag v-if="summary.notMetCount" size="small" type="danger">不满足 {{ summary.notMetCount }}</el-tag>
        <el-tag v-if="summary.pendingCount" size="small" type="warning">待评 {{ summary.pendingCount }}</el-tag>
        <el-tag v-if="gateBlocked" size="small" type="danger">闸门阻断</el-tag>
        <el-tag v-if="amountReconciles.length" size="small" type="warning">勾稽差 {{ amountReconciles.length }}</el-tag>
        <el-button size="small" @click="emit('navigate-sheet', 'I2-4')">← I2-4</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'I2-2')">I2-2</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'I2-7')">I2-7 →</el-button>
      </div>
    </div>

    <el-alert
      v-if="gateIssues.length"
      :type="gateBlocked ? 'error' : 'warning'"
      :closable="false"
      show-icon
      class="gate-alert"
    >
      <template #title>资本化闸门（{{ gateIssues.length }}）</template>
      <ul class="issue-list">
        <li v-for="(g, i) in gateIssues" :key="i">【{{ g.projectName }}】{{ g.message }}</li>
      </ul>
    </el-alert>

    <el-alert
      v-if="amountReconciles.length"
      type="warning"
      :closable="false"
      show-icon
      class="gate-alert"
    >
      <template #title>与 I2-2 / I2-7 金额勾稽（{{ amountReconciles.length }}）</template>
      <ul class="issue-list">
        <li v-for="(r, i) in amountReconciles" :key="i">
          【{{ r.projectName }}】{{ r.messages.join('；') }}
        </li>
      </ul>
    </el-alert>

    <!-- CAS6 引导 + 示例 -->
    <el-card shadow="never" class="guide-card">
      <template #header>
        <div class="block-title">
          <span>CAS6 第9条 — 开发阶段资本化五条件（须同时满足）</span>
          <el-button size="small" text type="primary" @click="showExamples = !showExamples">
            {{ showExamples ? '收起示例' : '展开条件示例' }}
          </el-button>
        </div>
      </template>
      <div class="conditions-grid">
        <div v-for="id in ([1, 2, 3, 4, 5] as const)" :key="id" class="condition-item">
          <span class="condition-num">{{ ['①', '②', '③', '④', '⑤'][id - 1] }}</span>
          <div>
            <strong>{{ CAS6_CONDITION_NAMES[id] }}</strong>
            <p class="cond-analysis">{{ CAS6_CONDITION_ANALYSIS[id] }}</p>
            <p v-if="showExamples" class="cond-example">{{ CAS6_CONDITION_EXAMPLES[id] }}</p>
          </div>
        </div>
      </div>
    </el-card>

    <!-- 二、审计过程 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="block-title">
          <span>二、审计过程 — 按项目资本化时点判断</span>
          <div class="title-actions">
            <el-button size="small" :disabled="isReadonly" @click="handleSeed">从 I2-2 带入</el-button>
            <el-button size="small" type="warning" :disabled="isReadonly" @click="handleLinkI22">回写时点→I2-2</el-button>
            <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleAdd">+ 新增项目</el-button>
            <el-button size="small" type="success" :disabled="isReadonly" @click="handleSave">保存</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="rows"
        border
        stripe
        size="small"
        max-height="420"
        highlight-current-row
        :row-class-name="rowClassName"
        @current-change="onCurrentChange"
        show-summary
        :summary-method="getSummary"
      >
        <el-table-column type="index" label="#" width="40" align="center" fixed />
        <el-table-column label="项目编号" width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.projectNo" size="small" @update:model-value="(v: string) => updateField(row.rowId, 'projectNo', v)" />
            <span v-else>{{ row.projectNo || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="研发项目名称" min-width="130" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.projectName" size="small" placeholder="项目名称" @update:model-value="(v: string) => updateField(row.rowId, 'projectName', v)" />
            <span v-else>{{ row.projectName || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="研究阶段" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.researchAmount" size="small" :controls="false" :precision="2" class="amt-input" @change="(v: number | undefined) => updateField(row.rowId, 'researchAmount', v ?? 0)" />
            <span v-else class="amt">{{ fmtNum(row.researchAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="开发阶段" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.developmentAmount" size="small" :controls="false" :precision="2" class="amt-input" @change="(v: number | undefined) => updateField(row.rowId, 'developmentAmount', v ?? 0)" />
            <span v-else class="amt">{{ fmtNum(row.developmentAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="资本化时点" width="128">
          <template #default="{ row }">
            <el-date-picker
              v-if="!isReadonly"
              :model-value="row.capStartDate"
              type="date"
              size="small"
              value-format="YYYY-MM-DD"
              style="width:100%"
              :disabled="!getRowCapResult(row).isMet"
              @update:model-value="(v: string) => updateField(row.rowId, 'capStartDate', v || '')"
            />
            <span v-else>{{ row.capStartDate || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="五条件" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="capTagType(row)" size="small">{{ capTagLabel(row) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="确认无形资产" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.recognizedIaAmount" size="small" :controls="false" :precision="2" class="amt-input" @change="(v: number | undefined) => updateField(row.rowId, 'recognizedIaAmount', v ?? 0)" />
            <span v-else class="amt">{{ fmtNum(row.recognizedIaAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="与明细勾稽" width="100" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.ledgerConsistent" size="small" clearable @change="(v: string) => updateField(row.rowId, 'ledgerConsistent', v || '')">
              <el-option label="一致" value="Y" />
              <el-option label="不一致" value="N" />
            </el-select>
            <span v-else>{{ row.ledgerConsistent === 'Y' ? '一致' : row.ledgerConsistent === 'N' ? '不一致' : '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末进度" min-width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.progress" size="small" @update:model-value="(v: string) => updateField(row.rowId, 'progress', v)" />
            <span v-else>{{ row.progress || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引" width="80">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.indexRef" size="small" @update:model-value="(v: string) => updateField(row.rowId, 'indexRef', v)" />
            <span v-else>{{ row.indexRef || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" text @click="removeRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <p class="table-hint">点击行可展开下方「五条件明细」；资本化时点仅在五条件全部为「是」时可编辑。</p>
    </el-card>

    <!-- 选中行：五条件明细 + 扩展字段 -->
    <el-card v-if="activeRow" shadow="never" class="block-card detail-card">
      <template #header>
        <div class="block-title">
          <span>五条件明细 — {{ activeRow.projectName || '未命名项目' }}</span>
          <div class="title-actions">
            <el-tooltip
              content="基于项目文本关键词匹配的启发式建议（非 LLM/AI 判断），仅供参考，须人工复核证据后确认"
              placement="top"
            >
              <el-button
                v-if="!isReadonly"
                size="small"
                type="primary"
                plain
                @click="handleAiSuggest"
              >
                规则建议条件
              </el-button>
            </el-tooltip>
            <el-tag v-if="activeResult" :type="activeResult.isMet ? 'success' : 'danger'" size="small">
              {{ activeResult.conclusion }}
            </el-tag>
          </div>
        </div>
      </template>

      <el-alert
        v-if="activeTimingIssues.length"
        type="warning"
        :closable="false"
        show-icon
        class="gate-alert"
        :title="activeTimingIssues.join('；')"
      />

      <el-form label-width="110px" size="small" class="meta-form">
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="立项开始日">
              <el-date-picker
                :model-value="activeRow.projectStartDate"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                style="width:100%"
                :disabled="isReadonly"
                @update:model-value="(v: string) => updateField(activeRow!.rowId, 'projectStartDate', v || '')"
              />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="验收日">
              <el-date-picker
                :model-value="activeRow.acceptanceDate"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                style="width:100%"
                :disabled="isReadonly"
                @update:model-value="(v: string) => updateField(activeRow!.rowId, 'acceptanceDate', v || '')"
              />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="转入无形资产日">
              <el-date-picker
                :model-value="activeRow.transferDate"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                style="width:100%"
                :disabled="isReadonly"
                @update:model-value="(v: string) => updateField(activeRow!.rowId, 'transferDate', v || '')"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="项目具体内容">
              <el-input :model-value="activeRow.projectContent" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly" @update:model-value="(v: string) => updateField(activeRow!.rowId, 'projectContent', v)" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="人员构成">
              <el-input :model-value="activeRow.personnelComposition" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly" @update:model-value="(v: string) => updateField(activeRow!.rowId, 'personnelComposition', v)" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="预算-材料">
              <el-input-number :model-value="activeRow.budgetMaterial" :controls="false" :precision="2" :disabled="isReadonly" @change="(v: number | undefined) => updateField(activeRow!.rowId, 'budgetMaterial', v ?? 0)" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="预算-人工">
              <el-input-number :model-value="activeRow.budgetLabor" :controls="false" :precision="2" :disabled="isReadonly" @change="(v: number | undefined) => updateField(activeRow!.rowId, 'budgetLabor', v ?? 0)" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="预算-其他">
              <el-input-number :model-value="activeRow.budgetOther" :controls="false" :precision="2" :disabled="isReadonly" @change="(v: number | undefined) => updateField(activeRow!.rowId, 'budgetOther', v ?? 0)" />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="资本化依据">
              <el-input :model-value="activeRow.capBasis" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly" placeholder="立项/可行性研究/决议等依据摘要…" @update:model-value="(v: string) => updateField(activeRow!.rowId, 'capBasis', v)" />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="支持性证据">
              <el-input :model-value="activeRow.supportingEvidence" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly" placeholder="查验的原始证据清单…" @update:model-value="(v: string) => updateField(activeRow!.rowId, 'supportingEvidence', v)" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>

      <div
        v-for="(cond, idx) in activeRow.conditions"
        :key="cond.id"
        class="condition-card"
      >
        <div class="condition-card-header">
          <span class="condition-card-num">{{ ['①', '②', '③', '④', '⑤'][idx] }}</span>
          <span class="condition-card-title">{{ cond.name }}</span>
          <el-tooltip :content="CAS6_CONDITION_EXAMPLES[cond.id]" placement="top">
            <el-tag size="small" type="info">示例</el-tag>
          </el-tooltip>
        </div>
        <div class="condition-card-body">
          <el-radio-group
            :model-value="cond.result || undefined"
            :disabled="isReadonly"
            size="small"
            @change="(v: string | number | boolean | undefined) => updateCondition(activeRow!.rowId, idx, { result: (v as any) || '' })"
          >
            <el-radio-button value="yes">是</el-radio-button>
            <el-radio-button value="no">否</el-radio-button>
            <el-radio-button value="na">不适用</el-radio-button>
          </el-radio-group>
          <el-input
            :model-value="cond.evidence"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }"
            :disabled="isReadonly"
            :placeholder="`证据描述…（${CAS6_CONDITION_ANALYSIS[cond.id]}）`"
            class="mt-8"
            @change="(v: string) => updateCondition(activeRow!.rowId, idx, { evidence: v })"
          />
          <el-input
            :model-value="(cond.attachments || []).join('；')"
            size="small"
            :disabled="isReadonly"
            placeholder="附件索引（多个用；分隔，如 立项批复.pdf；测试报告.docx）"
            class="mt-8"
            @change="(v: string) => updateCondition(activeRow!.rowId, idx, {
              attachments: v.split(/[；;]/).map((s) => s.trim()).filter(Boolean),
            })"
          />
        </div>
      </div>
    </el-card>

    <el-empty v-else description="请从上方表格选择或新增研发项目，开始五条件判断" :image-size="64" />

    <!-- 三、审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><span>三、审计说明</span></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 4 }"
        placeholder="记录阶段划分、时点依据、证据查验及异常处理…"
        @change="(v: string) => saveNote(v)"
      />
    </el-card>

    <!-- 四、审计结论 -->
    <el-card shadow="never" class="audit-conclusion-card">
      <template #header>
        <div class="conclusion-header">
          <span>四、审计结论</span>
          <el-button v-if="!isReadonly" size="small" text type="primary" @click="handleFillDraft">生成草稿</el-button>
        </div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="资本化时点判断是否恰当；政策是否一贯…"
        @change="(v: string) => saveConclusion(v)"
      />
    </el-card>

    <details class="edit-tips">
      <summary>编制说明（CAS6 / 建议程序）</summary>
      <p>研究阶段支出应费用化；开发阶段支出须五条件<strong>同时</strong>满足方可资本化；无法区分阶段的全部费用化。</p>
      <ol>
        <li v-for="(h, i) in CAS6_PROCEDURE_HINTS" :key="i">{{ h }}</li>
      </ol>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I2TabCapitalization.vue — I2-6 研发项目资本化时点判断
 * 对齐 Excel：项目宽表 + CAS6五条件明细 + 示例/程序指引
 */
import { ref, computed, inject, toRef } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import {
  useI2Capitalization,
  getRowCapResult,
  CAS6_CONDITION_NAMES,
  CAS6_CONDITION_ANALYSIS,
  CAS6_CONDITION_EXAMPLES,
  CAS6_OBJECTIVES,
  CAS6_PROCEDURE_HINTS,
  type I2CapitalizationProjectRow,
} from '../../composables/useI2Capitalization'

const props = defineProps<{
  sheetName: string
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveResponse: (sheetCode: string, data: Record<string, any>) => Promise<void>
  isReadonly?: boolean
}>()

const emit = defineEmits<{ 'save': []; 'navigate-sheet': [sheetName: string] }>()
const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const isReadonly = computed(() => Boolean(props.isReadonly))
const projectId = computed(() => props.projectId)
const showExamples = ref(false)

const {
  rows,
  activeRowId,
  activeRow,
  activeResult,
  summary,
  gateIssues,
  gateBlocked,
  amountReconciles,
  activeTimingIssues,
  auditNote,
  auditConclusion,
  addRow,
  removeRow,
  updateField,
  updateCondition,
  applyAiSuggest,
  seedFromDetail,
  linkCapDateToDetail,
  fillConclusionDraft,
  persistAll,
  saveNote,
  saveConclusion,
} = useI2Capitalization(toRef(props, 'allResponses'), {
  saveResponse: props.saveResponse,
})

function fmtNum(v: number): string {
  return v == null || isNaN(v) ? '—' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function capTagType(row: I2CapitalizationProjectRow) {
  const r = getRowCapResult(row)
  if (r.isMet) return 'success'
  const filled = row.conditions.some((c) => c.result === 'yes' || c.result === 'no')
  return filled ? 'danger' : 'info'
}

function capTagLabel(row: I2CapitalizationProjectRow) {
  const r = getRowCapResult(row)
  if (r.isMet) return '满足'
  const filled = row.conditions.some((c) => c.result === 'yes' || c.result === 'no')
  if (!filled) return '待评'
  return `缺${r.missingConditions.length}`
}

function rowClassName({ row }: { row: I2CapitalizationProjectRow }) {
  const r = getRowCapResult(row)
  if (r.isMet) return 'row-met'
  if (row.conditions.some((c) => c.result === 'no')) return 'row-fail'
  return ''
}

function onCurrentChange(row: I2CapitalizationProjectRow | null) {
  if (row) activeRowId.value = row.rowId
}

function getSummary({ columns }: { columns: any[] }) {
  const s = summary.value
  return columns.map((col, idx) => {
    if (idx === 0) return '合计'
    const label = String(col.label || '')
    if (label.includes('研究')) return fmtNum(s.totalResearch)
    if (label.includes('开发')) return fmtNum(s.totalDevelopment)
    if (label.includes('无形资产')) return fmtNum(s.totalRecognizedIa)
    return ''
  })
}

async function handleAdd() {
  try {
    const { value } = await ElMessageBox.prompt('请输入研发项目名称', '新增项目', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    if (value?.trim()) {
      addRow({ projectName: value.trim() })
      ElMessage.success(`已添加：${value.trim()}`)
    }
  } catch { /* cancelled */ }
}

function handleSeed() {
  const r = seedFromDetail()
  if (r.ok) ElMessage.success(r.message)
  else ElMessage.warning(r.message)
}

function handleLinkI22() {
  const r = linkCapDateToDetail()
  if (r.ok) ElMessage.success(r.message)
  else ElMessage.warning(r.message)
}

function handleAiSuggest() {
  if (!activeRow.value) return
  const r = applyAiSuggest(activeRow.value.rowId)
  if (r.ok) ElMessage.success(r.message)
  else ElMessage.warning(r.message)
}

function handleFillDraft() {
  const r = fillConclusionDraft()
  if (!r.ok) {
    ElMessage.error(r.message)
    return
  }
  void saveConclusion(auditConclusion.value)
  ElMessage.success(r.message)
}

async function handleSave() {
  await persistAll()
  emit('save')
  ElMessage.success('资本化时点判断已保存')
}

function handleReview() {
  openReviewDialog('I2-6-资本化时点判断')
}
</script>

<style scoped>
.i2-capitalization { font-size: var(--wp-font-size, 13px); padding: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { font-size: 15px; font-weight: 600; color: #1f2937; }
.objective-alert { margin-bottom: 12px; }
.obj-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.6; font-size: 12px; }
.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  margin-bottom: 12px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.65;
}
.tab-toolbar { display: flex; justify-content: flex-end; margin-bottom: 10px; }
.toolbar-right, .title-actions { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.gate-alert { margin-bottom: 10px; }
.issue-list { margin: 4px 0 0; padding-left: 18px; font-size: 12px; line-height: 1.55; }
.guide-card, .block-card { margin-bottom: 12px; }
.block-title { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; font-weight: 600; }
.conditions-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.condition-item { display: flex; gap: 8px; font-size: 12px; color: #334155; line-height: 1.5; }
.condition-num { color: #2563eb; font-weight: 700; flex-shrink: 0; }
.cond-analysis { margin: 2px 0 0; color: #64748b; }
.cond-example { margin: 4px 0 0; color: #1d4ed8; background: #eff6ff; padding: 4px 8px; border-radius: 4px; }
.amt { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.table-hint { margin: 8px 0 0; font-size: 12px; color: #9ca3af; }
.detail-card .meta-form { margin-bottom: 12px; }
.condition-card { border: 1px solid #e5e7eb; border-radius: 8px; margin-bottom: 10px; overflow: hidden; }
.condition-card-header {
  display: flex; align-items: center; gap: 8px; padding: 8px 12px;
  background: #f9fafb; border-bottom: 1px solid #e5e7eb; font-weight: 600;
}
.condition-card-num { color: #2563eb; }
.condition-card-body { padding: 12px; display: flex; flex-direction: column; gap: 8px; }
.mt-8 { margin-top: 8px; }
.audit-note-card, .audit-conclusion-card { margin-top: 12px; }
.conclusion-header { display: flex; align-items: center; justify-content: space-between; }
.edit-tips { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ol { padding-left: 18px; margin-top: 8px; line-height: 1.75; }
:deep(.row-met) { background-color: #f0fdf4 !important; }
:deep(.row-fail) { background-color: #fef2f2 !important; }
@media (max-width: 900px) {
  .conditions-grid { grid-template-columns: 1fr; }
}
</style>
