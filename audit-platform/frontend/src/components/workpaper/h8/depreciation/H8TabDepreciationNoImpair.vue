<template>
  <div class="h8-tab-depreciation-no-impair">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="objective-alert"
      title="审计目标：核实未发生减值迹象的使用权资产折旧计提（直线法）的准确性，确认折旧期=min(租赁期,使用寿命)且本期折旧与 H8-1 累计折旧计提一致（CAS21第21条）。" />

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>CAS21第21条：使用权资产应当自租赁期开始日起按直线法计提折旧。折旧期=min(租赁期, 使用寿命)。不含减值版本适用于未发生减值迹象的使用权资产。</p>
    </div>

    <!-- 公式说明Banner -->
    <div class="formula-banner">
      <div class="formula-icon">📐</div>
      <div class="formula-content">
        <div class="formula-title">折旧计算公式（不含减值）</div>
        <div class="formula-text">折旧期 = min(租赁期, 使用寿命) ｜ 月折旧额 = 入账值 / 折旧期月数 ｜ 本期折旧 = 月折旧 × 当期月数</div>
      </div>
    </div>

    <!-- 索引 + 行数 -->
    <div class="h8-tab-toolbar">
      <GtIndexChip value="wp:H8-8" />
      <el-tag size="small" type="info">共 {{ depRows.length }} 行</el-tag>
    </div>

    <!-- 折旧参数摘要 -->
    <el-card shadow="never" class="params-card">
      <template #header>
        <div class="section-title">
          <span>折旧测算参数（51行25列62公式）</span>
          <div class="title-actions">
            <el-button v-if="!isReadonly" size="small" @click="handleAddRow">+ 新增行</el-button>
            <el-button size="small" type="primary" plain @click="$emit('open-ai', 'dep-no-impair')">AI 辅助</el-button>
            <el-button size="small" @click="$emit('open-review', 'dep-no-impair')">复核</el-button>
          </div>
        </div>
      </template>
      <el-table :data="depRows" border size="small" class="formula-table" show-summary :summary-method="getDepSummary">
        <el-table-column prop="contractNo" label="合同号" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.contractNo" size="small"
              @change="updateDepCell(row.rowId, 'contractNo', row.contractNo)" />
            <span v-else>{{ row.contractNo }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="assetName" label="资产名称" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetName" size="small"
              @change="updateDepCell(row.rowId, 'assetName', row.assetName)" />
            <span v-else>{{ row.assetName }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="rouAmount" label="入账值" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.rouAmount" :controls="false" size="small"
              @change="(v: number | undefined) => updateDepCell(row.rowId, 'rouAmount', v)" />
            <span v-else>{{ fmtAmt(row.rouAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="leaseTermMonths" label="租赁期(月)" width="95" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.leaseTermMonths" :controls="false" size="small" :min="0"
              @change="(v: number | undefined) => updateDepCell(row.rowId, 'leaseTermMonths', v)" />
            <span v-else>{{ row.leaseTermMonths }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="usefulLifeMonths" label="使用寿命(月)" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.usefulLifeMonths" :controls="false" size="small" :min="0"
              @change="(v: number | undefined) => updateDepCell(row.rowId, 'usefulLifeMonths', v)" />
            <span v-else>{{ row.usefulLifeMonths }}</span>
          </template>
        </el-table-column>
        <el-table-column label="折旧期(月)" width="95" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="公式：min(租赁期, 使用寿命)">{{ row.depPeriodMonths }}</span>
          </template>
        </el-table-column>
        <el-table-column label="月折旧额" width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="公式：入账值 / 折旧期月数">{{ fmtAmt(row.monthlyDep) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="monthsInPeriod" label="当期月数" width="85" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.monthsInPeriod" :controls="false" size="small" :min="0" :max="12"
              @change="(v: number | undefined) => updateDepCell(row.rowId, 'monthsInPeriod', v)" />
            <span v-else>{{ row.monthsInPeriod }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期折旧" width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="公式：月折旧 × 当期月数">{{ fmtAmt(row.currentPeriodDep) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="accumulatedDep" label="累计折旧" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.accumulatedDep" :controls="false" size="small"
              @change="(v: number | undefined) => updateDepCell(row.rowId, 'accumulatedDep', v)" />
            <span v-else>{{ fmtAmt(row.accumulatedDep) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="50" align="center">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="deleteDepRow(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- OO渲染区域 -->
    <el-card shadow="never" class="oo-card">
      <template #header>
        <div class="section-title">
          <span>OO明细渲染（51行25列62公式）</span>
          <el-tag type="info" size="small">OnlyOffice 渲染</el-tag>
        </div>
      </template>
      <div class="oo-placeholder">
        <GtOnlyOfficeSheet
          v-if="wpId && showOO"
          :wp-id="wpId"
          :sheet-name="'折旧测算表（不含减值）H8-8'"
          :project-id="projectId"
          :readonly="isReadonly"
        />
        <div v-else class="oo-fallback">
          <el-empty description="OnlyOffice未加载，显示参数区计算结果">
            <template #image><span style="font-size:40px">📊</span></template>
          </el-empty>
        </div>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><span class="card-title">审计说明</span></template>
      <el-input type="textarea" :model-value="auditNote" :disabled="isReadonly"
        :autosize="{ minRows: 5 }" placeholder="请输入审计说明..." @change="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-conclusion-card">
      <template #header><span class="card-title">审计结论</span></template>
      <el-input type="textarea" :model-value="auditConclusion" :disabled="isReadonly"
        :autosize="{ minRows: 3 }" placeholder="请输入审计结论..." @change="saveAuditConclusion" />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>折旧期取较短者：min(租赁期, 使用寿命)</li>
        <li>如合理确定能取得所有权 → 折旧期=使用寿命</li>
        <li>月折旧额=入账值/折旧期月数（直线法）</li>
        <li>不含减值版本：无需考虑减值对折旧基数的影响</li>
        <li>折旧合计应与H8-1累计折旧本期计提交叉验证</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H8TabDepreciationNoImpair.vue — H8-8(A) 折旧测算表（不含减值）
 * 51行25列62公式，OO渲染+参数摘要
 * Spec: Task 4.6 | Requirements: 6.1-6.6
 */
import { ref, toRef, watch, defineAsyncComponent } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useH8Depreciation } from '../../composables/useH8Depreciation'
import GtIndexChip from '../../GtIndexChip.vue'

const GtOnlyOfficeSheet = defineAsyncComponent(() =>
  import('../../GtOnlyOfficeSheet.vue').catch(() => ({ template: '<div>OO不可用</div>' })),
)

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'open-ai', section: string): void
  (e: 'open-review', section: string): void
}>()

const showOO = ref(true)

// ── 审计说明 / 审计结论（持久化 checklist_responses，conclusion:null）──
const AUDIT_NOTE_KEY = 'H8-dep-no-impair-audit-note'
const AUDIT_CONCLUSION_KEY = 'H8-dep-no-impair-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
function _hydrateAudit() {
  const n = props.allResponses.get(AUDIT_NOTE_KEY)
  if (n?.remark != null) auditNote.value = n.remark
  const c = props.allResponses.get(AUDIT_CONCLUSION_KEY)
  if (c?.remark != null) auditConclusion.value = c.remark
}
_hydrateAudit()
watch(() => props.allResponses, _hydrateAudit)
function saveAuditNote(val: string) {
  if (props.isReadonly) return
  auditNote.value = val
  emit('save', AUDIT_NOTE_KEY, val)
}
function saveAuditConclusion(val: string) {
  if (props.isReadonly) return
  auditConclusion.value = val
  emit('save', AUDIT_CONCLUSION_KEY, val)
}

const {
  depRows, depTotal, accDepTotal,
  addDepRow, deleteDepRow, updateDepCell,
} = useH8Depreciation({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses'),
  onSave: (itemId, value) => emit('save', itemId, value),
})

function fmtAmt(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function handleAddRow() {
  const { value } = await ElMessageBox.prompt('请输入合同号', '新增折旧行', {
    confirmButtonText: '确认', cancelButtonText: '取消', inputPlaceholder: '如：LEASE-2024-001',
  })
  if (value) addDepRow(value)
}

function getDepSummary({ columns }: { columns: any[] }) {
  return columns.map((_: any, idx: number) => {
    if (idx === 0) return '合计'
    if (idx === 8) return fmtAmt(depTotal.value)
    if (idx === 9) return fmtAmt(accDepTotal.value)
    return ''
  })
}
</script>

<style scoped>
.h8-tab-depreciation-no-impair { padding: 16px; font-size: var(--wp-font-size, 13px); }

.objective-alert { margin-bottom: 12px; }
.audit-note-card, .audit-conclusion-card { margin-bottom: 16px; }
.card-title { font-weight: 600; }

.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  border-radius: 0 6px 6px 0; margin-bottom: 16px; font-size: 12px; color: #92400e;
}

.formula-banner {
  display: flex; gap: 12px; align-items: flex-start;
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  border: 1px solid #93c5fd; border-radius: 8px; padding: 14px 16px; margin-bottom: 16px;
}
.formula-icon { font-size: 28px; }
.formula-content { flex: 1; }
.formula-title { font-weight: 700; font-size: 14px; color: #1e40af; margin-bottom: 4px; }
.formula-text { font-size: var(--wp-font-size, 13px); color: #1d4ed8; }

.h8-tab-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }

.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 6px; }

.params-card { margin-bottom: 16px; }
.formula-table { font-size: var(--wp-font-size, 13px); }
.formula-table :deep(.formula-col) { background: #f0f9ff; }
.formula-value { border-bottom: 1px dashed #409eff; cursor: help; color: #409eff; }

.oo-card { margin-bottom: 16px; }
.oo-placeholder { min-height: 400px; }
.oo-fallback { padding: 40px 0; }

.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
