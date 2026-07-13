<template>
  <div class="i6-tab-targeted-check">
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 费用归集完整性：研发费用是否全面归集到6602</div>
        <div class="guide-step"><span class="step-num">②</span> 人员费用分摊合理性：研发人员工时/工资分摊依据</div>
        <div class="guide-step"><span class="step-num">③</span> 与I2划分一致性：费用化(I6)+资本化(I2)划分合规</div>
        <div class="guide-step"><span class="step-num">④</span> 加计扣除测算：可加计研发费用范围与税会差异</div>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：验证研发费用归集完整、人员费用分摊合理、费用化与资本化划分一致，并测算研发费用加计扣除的可加计范围与税会差异，确认列报及税务处理恰当。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:I6-4" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ superDeductionRows.length }} 类费用</el-tag>
      </div>
    </div>

    <!-- Section 1: 费用归集完整性 -->
    <el-card shadow="never" class="check-section">
      <template #header>
        <div class="section-header">
          <span class="section-title">一、费用归集完整性</span>
          <div class="section-actions">
            <el-button size="small" type="default" text @click="handleReview">复核</el-button>
          </div>
        </div>
      </template>
      <div class="methodology-block">
        <p><strong>方法论：</strong>研发费用归集完整性检查要点：</p>
        <p>1. 核实是否所有符合条件的研发支出均已归集到6602科目</p>
        <p>2. 检查是否存在应归入研发费用但计入其他科目的支出</p>
        <p>3. 核查研发项目立项与费用归集的对应关系</p>
      </div>
      <div class="check-items">
        <div class="check-item">
          <span class="check-label">研发项目立项是否完整覆盖实际研发活动：</span>
          <el-radio-group v-model="checkItems.completeProject" :disabled="isReadonly" size="small" @change="onCheckChange('completeProject')">
            <el-radio-button value="正常">正常</el-radio-button><el-radio-button value="异常">异常</el-radio-button><el-radio-button value="不适用">不适用</el-radio-button>
          </el-radio-group>
        </div>
        <div class="check-item">
          <span class="check-label">是否存在应归入研发费用但计入管理费用等的支出：</span>
          <el-radio-group v-model="checkItems.completeMisclass" :disabled="isReadonly" size="small" @change="onCheckChange('completeMisclass')">
            <el-radio-button value="正常">正常</el-radio-button><el-radio-button value="异常">异常</el-radio-button><el-radio-button value="不适用">不适用</el-radio-button>
          </el-radio-group>
        </div>
      </div>
      <div class="section-conclusion">
        <span class="conclusion-label">本节结论：</span>
        <el-input v-model="conclusions.completeness" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="请填写费用归集完整性检查结论..." @blur="onConclusionBlur('completeness')" />
      </div>
    </el-card>

    <!-- Section 2: 人员费用分摊合理性 -->
    <el-card shadow="never" class="check-section">
      <template #header>
        <div class="section-header">
          <span class="section-title">二、人员费用分摊合理性</span>
          <div class="section-actions">
            <el-button size="small" type="default" text @click="handleReview">复核</el-button>
          </div>
        </div>
      </template>
      <div class="methodology-block">
        <p><strong>方法论：</strong>人员费用分摊合理性检查：</p>
        <p>1. 核实研发人员名单与实际参与研发活动的人员是否一致</p>
        <p>2. 工时分摊比例是否有充分依据（工时记录/考勤/项目周报）</p>
        <p>3. 人工费用分摊方法是否合理且前后一致</p>
      </div>
      <div class="check-items">
        <div class="check-item">
          <span class="check-label">研发人员名单与实际参与研发的人员一致：</span>
          <el-radio-group v-model="checkItems.allocStaff" :disabled="isReadonly" size="small" @change="onCheckChange('allocStaff')">
            <el-radio-button value="正常">正常</el-radio-button><el-radio-button value="异常">异常</el-radio-button><el-radio-button value="不适用">不适用</el-radio-button>
          </el-radio-group>
        </div>
        <div class="check-item">
          <span class="check-label">工时分摊有充分支撑依据：</span>
          <el-radio-group v-model="checkItems.allocBasis" :disabled="isReadonly" size="small" @change="onCheckChange('allocBasis')">
            <el-radio-button value="正常">正常</el-radio-button><el-radio-button value="异常">异常</el-radio-button><el-radio-button value="不适用">不适用</el-radio-button>
          </el-radio-group>
        </div>
      </div>
      <div class="section-conclusion">
        <span class="conclusion-label">本节结论：</span>
        <el-input v-model="conclusions.allocation" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="请填写人员费用分摊合理性结论..." @blur="onConclusionBlur('allocation')" />
      </div>
    </el-card>

    <!-- Section 3: 与I2划分一致性 -->
    <el-card shadow="never" class="check-section">
      <template #header>
        <div class="section-header">
          <span class="section-title">三、与I2划分一致性</span>
          <div class="section-actions">
            <el-button size="small" type="default" text @click="handleReview">复核</el-button>
          </div>
        </div>
      </template>
      <div class="methodology-block">
        <p><strong>方法论：</strong>费用化(I6)与资本化(I2)划分一致性：</p>
        <p>1. CAS 6号：研究阶段支出全部费用化，开发阶段满足5条件可资本化</p>
        <p>2. 验证费用化(I6)与资本化(I2)的划分时点、金额是否一致</p>
        <p>3. VR-I6-01：费用化+资本化=研发总额，确认无遗漏/重复</p>
      </div>
      <div class="check-items">
        <div class="check-item">
          <span class="check-label">研究/开发阶段划分时点合理：</span>
          <el-radio-group v-model="checkItems.i2PhaseDiv" :disabled="isReadonly" size="small" @change="onCheckChange('i2PhaseDiv')">
            <el-radio-button value="正常">正常</el-radio-button><el-radio-button value="异常">异常</el-radio-button><el-radio-button value="不适用">不适用</el-radio-button>
          </el-radio-group>
        </div>
        <div class="check-item">
          <span class="check-label">费用化+资本化=研发总额（VR-I6-01）：</span>
          <el-radio-group v-model="checkItems.i2VrBalance" :disabled="isReadonly" size="small" @change="onCheckChange('i2VrBalance')">
            <el-radio-button value="正常">正常</el-radio-button><el-radio-button value="异常">异常</el-radio-button><el-radio-button value="不适用">不适用</el-radio-button>
          </el-radio-group>
        </div>
      </div>
      <div class="section-conclusion">
        <span class="conclusion-label">本节结论：</span>
        <el-input v-model="conclusions.i2consistency" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="请填写与I2划分一致性结论..." @blur="onConclusionBlur('i2consistency')" />
      </div>
    </el-card>

    <!-- Section 4: 研发费用加计扣除测算（研发特点） -->
    <el-card shadow="never" class="check-section">
      <template #header>
        <div class="section-header">
          <span class="section-title">四、研发费用加计扣除测算</span>
          <div class="section-actions">
            <el-button size="small" type="default" text @click="handleReview">复核</el-button>
          </div>
        </div>
      </template>
      <div class="methodology-block">
        <p><strong>方法论：</strong>研发费用加计扣除（财税加计扣除政策 / 财会〔2019〕6号列示 / CAS28 税会差异）：</p>
        <p>1. 按 6 类费用（人工/材料/折旧/无形资产摊销/设计/委外等）确认可加计范围，委外研发费按 80% 计入。</p>
        <p>2. 可加计金额 = 归集金额 × 是否可加计 × 加计扣除比例；税会差异体现为可抵扣暂时性差异。</p>
        <p>3. 加计扣除仅调整应纳税所得额，不改变会计利润（税会差异，联动递延所得税）。</p>
      </div>
      <el-table :data="superDeductionRows" border stripe size="small" class="deduction-table" show-summary :summary-method="getDeductionSummary">
        <el-table-column prop="category" label="费用类别" min-width="130" fixed>
          <template #default="{ row }">
            <span :class="{ 'subtotal-text': row.isTotal }">{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="collectedAmount" label="归集金额" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !row.isTotal" v-model="row.collectedAmount" size="small" :controls="false" :min="0" @change="onDeductionChange" />
            <span v-else>{{ fmtAmt(row.collectedAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="deductible" label="是否可加计" width="110" align="center">
          <template #default="{ row }">
            <el-switch v-if="!isReadonly && !row.isTotal" v-model="row.deductible" @change="onDeductionChange" />
            <el-tag v-else-if="!row.isTotal" :type="row.deductible ? 'success' : 'info'" size="small">{{ row.deductible ? '可加计' : '不可加计' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="ratio" label="加计比例(%)" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !row.isTotal" v-model="row.ratio" size="small" :controls="false" :min="0" :max="200" @change="onDeductionChange" />
            <span v-else-if="!row.isTotal">{{ row.ratio }}%</span>
          </template>
        </el-table-column>
        <el-table-column label="可加计金额" min-width="130" align="right">
          <template #header>
            <el-tooltip content="可加计金额 = 归集金额 × 是否可加计 × 加计比例" placement="top">
              <span class="formula-col-header">可加计金额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip content="= 归集金额 × 是否可加计 × 加计比例" placement="top">
              <span class="formula-value">{{ fmtAmt(deductibleAmount(row)) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="税会差异说明" min-width="150">
          <template #default="{ row }">
            <el-input v-if="!isReadonly && !row.isTotal" v-model="row.remark" size="small" @change="onDeductionChange" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
      <div class="section-conclusion">
        <span class="conclusion-label">加计扣除测算结论：</span>
        <el-input v-model="conclusions.superDeduction" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="请填写加计扣除可加计范围、比例及税会差异结论..." @blur="onConclusionBlur('superDeduction')" />
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="section-header"><span class="section-title">审计说明</span></div></template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly" placeholder="请填写针对性检查的总体审计说明（归集/分摊/划分/加计扣除等执行情况与发现）..." @blur="onAuditNoteBlur" />
    </el-card>

    <!-- 总体结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header><div class="section-header"><span class="section-title">总体审计结论</span></div></template>
      <el-select v-model="overallConclusion" placeholder="请选择" :disabled="isReadonly" class="conclusion-select" @change="onOverallChange">
        <el-option value="针对性检查未发现异常，研发费用归集完整、分摊合理、与I2划分一致" label="针对性检查未发现异常，研发费用归集完整、分摊合理、与I2划分一致" />
        <el-option value="存在需关注事项，但不影响整体列报" label="存在需关注事项，但不影响整体列报" />
        <el-option value="发现需调整事项" label="发现需调整事项" />
      </el-select>
    </el-card>

    <details class="guidance-details compile-hint"><summary>编制提示</summary><ul>
      <li>四维度检查：费用归集完整性/人员分摊合理性/I2划分一致性/加计扣除测算</li>
      <li>CAS 6号五条件是资本化判断依据</li>
      <li>VR-I6-01：费用化(I6)+资本化(I2)=研发总额</li>
      <li>加计扣除：委外研发费按80%计入，可加计金额=归集金额×是否可加计×加计比例</li>
      <li>加计扣除属税会差异（CAS28），仅调整应纳税所得额，不改会计利润</li>
    </ul></details>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch, inject } from 'vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const emit = defineEmits<{ 'save': [itemId: string, value: any] }>()
const openReviewDialog = inject<(section?: string) => void>('openReviewDialog', () => {})

const PREFIX = 'I6-4'
const NOTE_KEY = 'I6-4-audit-note'
const checkItems = reactive({
  completeProject: '', completeMisclass: '',
  allocStaff: '', allocBasis: '',
  i2PhaseDiv: '', i2VrBalance: '',
})
const conclusions = reactive({ completeness: '', allocation: '', i2consistency: '', superDeduction: '' })
const overallConclusion = ref('')
const auditNote = ref('')

// ─── 加计扣除测算（研发特点） ─────────────────────────────────────────────────
interface DeductionRow { rowId: string; category: string; collectedAmount: number; deductible: boolean; ratio: number; remark: string; isTotal?: boolean }
const DEDUCTION_KEY = 'I6-4-super-deduction-rows'
const DEFAULT_DEDUCTION: { category: string; ratio: number }[] = [
  { category: '人工费', ratio: 100 }, { category: '材料费', ratio: 100 },
  { category: '折旧费', ratio: 100 }, { category: '无形资产摊销', ratio: 100 },
  { category: '设计费', ratio: 100 }, { category: '委外研发费', ratio: 80 },
  { category: '其他费用', ratio: 100 },
]
const superDeductionRows = ref<DeductionRow[]>([])

function _makeDeductionRow(category: string, ratio: number): DeductionRow {
  return { rowId: `dr-${Math.random().toString(36).slice(2, 10)}`, category, collectedAmount: 0, deductible: true, ratio, remark: '' }
}
function deductibleAmount(row: DeductionRow): number {
  if (row.isTotal) return superDeductionRows.value.filter((r) => !r.isTotal).reduce((s, r) => s + _deductible(r), 0)
  return _deductible(row)
}
function _deductible(row: DeductionRow): number { return row.deductible ? (row.collectedAmount || 0) * (row.ratio || 0) / 100 : 0 }
function getDeductionSummary({ columns }: { columns: any[] }): string[] {
  return columns.map((col, idx) => {
    if (idx === 0) return '合计'
    if (col.property === 'collectedAmount') return fmtAmt(superDeductionRows.value.reduce((s, r) => s + (r.collectedAmount || 0), 0))
    if (col.label && String(col.label).includes('可加计金额')) return fmtAmt(superDeductionRows.value.reduce((s, r) => s + _deductible(r), 0))
    return ''
  })
}
function onDeductionChange(): void { emit('save', DEDUCTION_KEY, JSON.stringify(superDeductionRows.value)) }

function _load(): void {
  checkItems.completeProject = _str(`${PREFIX}-complete-project`)
  checkItems.completeMisclass = _str(`${PREFIX}-complete-misclass`)
  checkItems.allocStaff = _str(`${PREFIX}-alloc-staff`)
  checkItems.allocBasis = _str(`${PREFIX}-alloc-basis`)
  checkItems.i2PhaseDiv = _str(`${PREFIX}-i2-phase-div`)
  checkItems.i2VrBalance = _str(`${PREFIX}-i2-vr-balance`)
  conclusions.completeness = _str(`${PREFIX}-completeness-conclusion`)
  conclusions.allocation = _str(`${PREFIX}-allocation-conclusion`)
  conclusions.i2consistency = _str(`${PREFIX}-i2consistency-conclusion`)
  conclusions.superDeduction = _str(`${PREFIX}-superDeduction-conclusion`)
  overallConclusion.value = _str(`${PREFIX}-conclusion`)
  auditNote.value = _str(NOTE_KEY)
  const dr = props.allResponses.get(DEDUCTION_KEY)
  const raw = dr?.remark ?? (typeof dr === 'string' ? dr : null)
  if (raw) { try { const p = JSON.parse(raw); if (Array.isArray(p)) { superDeductionRows.value = p; return } } catch { /* */ } }
  superDeductionRows.value = DEFAULT_DEDUCTION.map((d) => _makeDeductionRow(d.category, d.ratio))
}
function _str(id: string): string { const item = props.allResponses.get(id); return (item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : '')) as string }
watch(() => props.allResponses, () => _load(), { immediate: true })

const CHECK_MAP: Record<string, string> = {
  completeProject: `${PREFIX}-complete-project`, completeMisclass: `${PREFIX}-complete-misclass`,
  allocStaff: `${PREFIX}-alloc-staff`, allocBasis: `${PREFIX}-alloc-basis`,
  i2PhaseDiv: `${PREFIX}-i2-phase-div`, i2VrBalance: `${PREFIX}-i2-vr-balance`,
}
function onCheckChange(field: keyof typeof checkItems): void { emit('save', CHECK_MAP[field], checkItems[field]) }
function onConclusionBlur(field: keyof typeof conclusions): void { emit('save', `${PREFIX}-${field}-conclusion`, conclusions[field]) }
function onOverallChange(val: string): void { emit('save', `${PREFIX}-conclusion`, val) }
function onAuditNoteBlur(): void { emit('save', NOTE_KEY, auditNote.value) }
function handleReview(): void { openReviewDialog('I6-4 针对性检查') }
function fmtAmt(v: number | null | undefined): string { if (v == null || Math.abs(v) < 0.005) return '-'; return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.i6-tab-targeted-check { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.deduction-table { font-size: var(--wp-font-size, 13px); margin-bottom: 8px; }
.deduction-table :deep(.el-table__footer td) { font-weight: 600; background: #f0f9ff; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; padding-bottom: 2px; }
.formula-value { border-bottom: 1px dashed #c0c4cc; cursor: help; padding-bottom: 1px; color: #303133; font-weight: 500; }
.subtotal-text { font-weight: 600; }
.audit-note-card { margin-bottom: 16px; }
.audit-note-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; }
.guide-area { background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%); border-radius: 8px; padding: 16px; margin-bottom: 16px; }
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.guide-step { display: flex; align-items: flex-start; gap: 6px; font-size: var(--wp-font-size, 13px); }
.step-num { font-weight: 700; color: var(--el-color-primary); min-width: 20px; }
.check-section { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-title { font-size: 14px; font-weight: 600; }
.section-actions { display: flex; align-items: center; gap: 4px; }
.methodology-block { border-left: 4px solid #d97706; background: #fffbeb; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.7; }
.methodology-block p { margin: 0 0 2px; }
.methodology-block strong { color: #78350f; }
.check-items { margin-bottom: 12px; }
.check-item { display: flex; align-items: center; justify-content: space-between; padding: 8px 0; border-bottom: 1px dashed var(--el-border-color-lighter); }
.check-item:last-child { border-bottom: none; }
.check-label { font-size: var(--wp-font-size, 13px); color: var(--el-text-color-regular); flex: 1; }
.section-conclusion { margin-top: 12px; padding-top: 10px; border-top: 1px dashed var(--el-border-color-lighter); }
.conclusion-label { font-size: 12px; color: var(--el-text-color-regular); display: block; margin-bottom: 6px; }
.conclusion-card { margin-bottom: 16px; }
.conclusion-select { width: 100%; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
