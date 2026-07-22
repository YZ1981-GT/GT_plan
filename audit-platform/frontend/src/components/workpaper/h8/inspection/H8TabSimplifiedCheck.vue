<template>
  <div class="h8-tab-simplified-check">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="objective-alert"
      title="审计目标：①核实短期租赁(≤12月)及低价值资产租赁(全新价值≤4万)简化处理适用性（CAS21第32条）；②按直线法重算本期租金费用并与账面、相关科目勾稽；③不符合条件的租赁应确认使用权资产与租赁负债。" />

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>CAS21第32条：短期租赁或低价值资产租赁可选择不确认使用权资产和租赁负债，租赁付款额按直线法（或其他系统合理方法）计入相关资产成本或当期损益。本表双轨检查：资格判断 + 费用重算。</p>
    </div>

    <!-- 索引 + 行数 -->
    <div class="h8-tab-toolbar">
      <GtIndexChip value="wp:H8-13" />
      <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      <el-tag v-if="Math.abs(totalDifference) > 0.005" size="small" type="warning">
        费用差异合计 {{ fmtAmt(totalDifference) }}
      </el-tag>
      <el-tag
        v-if="h85LeaseTermMismatches.length"
        size="small"
        type="warning"
        class="nav-chip"
        @click="emit('navigate-sheet', 'H8-5')"
      >
        与 H8-5 租期不一致 {{ h85LeaseTermMismatches.length }}
      </el-tag>
      <el-tag
        v-if="h85ShortTermMissing.length"
        size="small"
        type="danger"
        class="nav-chip"
        @click="handleSyncH85"
      >
        H8-5 短期未纳入 {{ h85ShortTermMissing.length }}
      </el-tag>
      <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H8-5')">← H8-5</el-tag>
      <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H8-4')">H8-4</el-tag>
      <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H8-2')">H8-2</el-tag>
      <el-dropdown size="small" @command="handleExportCommand">
        <el-button size="small" :loading="ieBusy">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
            <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
            <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
    </div>

    <el-alert
      v-if="h85LeaseTermMismatches.length || h85ShortTermMissing.length"
      type="warning"
      :closable="false"
      show-icon
      class="sync-alert"
      :title="syncAlertTitle"
    >
      <template #default>
        <el-button size="small" type="warning" :disabled="isReadonly" @click="handleSyncH85">
          从 H8-5 同步短期候选
        </el-button>
        <el-button size="small" link type="primary" @click="emit('navigate-sheet', 'H8-5')">打开 H8-5</el-button>
      </template>
    </el-alert>

    <!-- 检查表 -->
    <el-card shadow="never" class="table-card">
      <template #header>
        <div class="section-title">
          <span>简化处理检查（H8-13：资格判断 + 费用重算）</span>
          <div class="title-actions">
            <el-button v-if="!isReadonly" size="small" type="primary" plain @click="handleSyncH85">从 H8-5 带入</el-button>
            <el-button v-if="!isReadonly" size="small" @click="handleAddRow">+ 新增行</el-button>
            <el-button size="small" type="primary" plain @click="$emit('open-ai', 'simplified')">AI 辅助</el-button>
            <el-button size="small" @click="$emit('open-review', 'simplified')">复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="rows" border size="small" class="formula-table"
        :row-class-name="getRowClassName" show-summary :summary-method="getSummary">
        <el-table-column prop="contractNo" label="合同号" min-width="110" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.contractNo" size="small"
              @change="updateCell(row.rowId, 'contractNo', row.contractNo)" />
            <span v-else>{{ row.contractNo }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="assetCategory" label="资产类别" width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.assetCategory" size="small" clearable
              @change="updateCell(row.rowId, 'assetCategory', row.assetCategory)">
              <el-option v-for="c in assetCategories" :key="c" :label="c" :value="c" />
            </el-select>
            <span v-else>{{ row.assetCategory }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="assetName" label="承租资产" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetName" size="small"
              @change="updateCell(row.rowId, 'assetName', row.assetName)" />
            <span v-else>{{ row.assetName }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="lessor" label="出租方" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.lessor" size="small"
              @change="updateCell(row.rowId, 'lessor', row.lessor)" />
            <span v-else>{{ row.lessor }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="leaseTermMonths" label="租赁期(月)" width="95" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.leaseTermMonths" :controls="false"
              size="small" :min="0"
              @change="(v: number | undefined) => updateCell(row.rowId, 'leaseTermMonths', v)" />
            <span v-else>{{ row.leaseTermMonths }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="newAssetValue" label="全新价值" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.newAssetValue" :controls="false" size="small"
              @change="(v: number | undefined) => updateCell(row.rowId, 'newAssetValue', v)" />
            <span v-else>{{ fmtAmt(row.newAssetValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="短期(≤12月)" width="100" align="center" class-name="formula-col">
          <template #default="{ row }">
            <el-tag :type="row.isShortTerm ? 'success' : 'info'" size="small">
              {{ row.isShortTerm ? '是' : '否' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="低价值(≤4万)" width="110" align="center" class-name="formula-col">
          <template #default="{ row }">
            <el-tag :type="row.isLowValue ? 'success' : 'info'" size="small">
              {{ row.isLowValue ? '是' : '否' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="简化类型" width="110" align="center" class-name="formula-col">
          <template #default="{ row }">
            <el-tag v-if="row.simplifiedType === '不符合'" type="danger" size="small">不符合</el-tag>
            <el-tag v-else-if="row.simplifiedType" type="success" size="small">{{ row.simplifiedType }}</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="monthlyRent" label="月租金" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.monthlyRent" :controls="false" size="small"
              @change="(v: number | undefined) => updateCell(row.rowId, 'monthlyRent', v)" />
            <span v-else>{{ fmtAmt(row.monthlyRent) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="accrualMonths" label="应计月数" width="90" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.accrualMonths" :controls="false"
              size="small" :min="0" :max="12" :precision="1"
              @change="(v: number | undefined) => updateCell(row.rowId, 'accrualMonths', v)" />
            <span v-else>{{ row.accrualMonths }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期应计租金" width="120" align="right" class-name="formula-col">
          <template #default="{ row }">{{ fmtAmt(row.expectedExpense) }}</template>
        </el-table-column>
        <el-table-column prop="bookExpense" label="账面本期租金" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.bookExpense" :controls="false" size="small"
              @change="(v: number | undefined) => updateCell(row.rowId, 'bookExpense', v)" />
            <span v-else>{{ fmtAmt(row.bookExpense) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异" width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span :class="{ 'diff-warn': Math.abs(row.difference) > 0.005 }">{{ fmtAmt(row.difference) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="reconciled" label="勾稽一致" width="100" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.reconciled" size="small" clearable
              @change="updateCell(row.rowId, 'reconciled', row.reconciled)">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="待核实" value="待核实" />
            </el-select>
            <span v-else>{{ row.reconciled }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="expenseAccount" label="费用科目" width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.expenseAccount" size="small"
              @change="updateCell(row.rowId, 'expenseAccount', row.expenseAccount)" />
            <span v-else>{{ row.expenseAccount }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="conclusion" label="核查结论" min-width="140">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.conclusion" size="small"
              @change="updateCell(row.rowId, 'conclusion', row.conclusion)">
              <el-option label="符合简化条件" value="符合简化条件" />
              <el-option label="不符合，应确认ROU" value="不符合，应确认ROU" />
              <el-option label="待核实" value="待核实" />
            </el-select>
            <span v-else>{{ row.conclusion }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="deleteRow(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 底部统计卡片 -->
    <div class="stats-row">
      <el-card shadow="never" class="stat-card">
        <div class="stat-label">简化处理笔数</div>
        <div class="stat-value ok">{{ simplifiedCount }}</div>
      </el-card>
      <el-card shadow="never" class="stat-card">
        <div class="stat-label">应转为使用权资产</div>
        <div class="stat-value" :class="mustRecognizeCount > 0 ? 'warn' : 'ok'">{{ mustRecognizeCount }}</div>
      </el-card>
      <el-card shadow="never" class="stat-card">
        <div class="stat-label">本期应计租金合计</div>
        <div class="stat-value">{{ fmtAmt(totalExpectedExpense) }} 元</div>
      </el-card>
      <el-card shadow="never" class="stat-card">
        <div class="stat-label">账面本期租金合计</div>
        <div class="stat-value">{{ fmtAmt(totalBookExpense) }} 元</div>
      </el-card>
      <el-card shadow="never" class="stat-card">
        <div class="stat-label">费用差异合计</div>
        <div class="stat-value" :class="Math.abs(totalDifference) > 0.005 ? 'warn' : 'ok'">
          {{ fmtAmt(totalDifference) }} 元
        </div>
      </el-card>
      <el-card shadow="never" class="stat-card">
        <div class="stat-label">简化处理年租金</div>
        <div class="stat-value">{{ fmtAmt(totalAnnualRental) }} 元</div>
      </el-card>
    </div>

    <!-- 不合规提示 -->
    <el-alert v-if="mustRecognizeCount > 0" type="error" :closable="false" show-icon class="noncompliant-alert">
      <template #title>
        {{ mustRecognizeCount }}笔租赁不符合简化条件，应确认使用权资产和租赁负债（转入 H8-2 / H9）
      </template>
    </el-alert>
    <el-alert v-if="Math.abs(totalDifference) > 0.005" type="warning" :closable="false" show-icon class="noncompliant-alert">
      <template #title>
        本期应计与账面租金差异合计 {{ fmtAmt(totalDifference) }} 元，请追查重大差异并考虑调整
      </template>
    </el-alert>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><span class="card-title">审计说明</span></template>
      <el-input type="textarea" :model-value="auditNote" :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="说明抽查范围、简化处理政策一贯性、免租期/递进租金处理、与费用科目勾稽结果，以及「不符合」笔数是否已转入 H8-2/H9…"
        @change="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-conclusion-card">
      <template #header><span class="card-title">审计结论</span></template>
      <el-input type="textarea" :model-value="auditConclusion" :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="经检查，本期简化处理的租赁□符合 / □基本符合 / □不符合 CAS21第32条；租金费用计提□准确 / □存在差异已调整 / □待进一步核实。"
        @change="saveAuditConclusion" />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>短期租赁：租赁期开始日确定的租赁期不超过12个月；含购买选择权的不属于短期租赁</li>
        <li>低价值：标的资产全新状态下价值≤40,000元（绝对金额，与承租人规模无关）；预期转租不适用</li>
        <li>转租中的转租人不得对原租赁选用短期简化</li>
        <li>优先从 H8-5「推送短期候选 / 从 H8-5 带入」按合同号同步租赁期；含购买选择权的合同不会被推送</li>
        <li>费用重算：本期应计租金＝月租金×本期应计月数；免租期/递进租金须先按系统合理方法分摊</li>
        <li>「不符合」红色高亮，应转入 H8-2/H9 按完整租赁模型确认</li>
        <li>本表索引号为 H8-13，勿与 H8-12（减少/终止检查表）混淆</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H8TabSimplifiedCheck.vue — H8-13 简化处理的租赁检查表
 * 资格判断（短期/低价值）+ 费用重算（应计 vs 账面），不合规/差异高亮
 * Spec: Task 4.9 | Requirements: 8.1-8.4
 */
import { ref, computed, toRef, watch, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useH8SimplifiedCheck } from '../../composables/useH8SimplifiedCheck'
import { useH8ImportExport } from '../../composables/useH8ImportExport'
import GtIndexChip from '../../GtIndexChip.vue'

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
  (e: 'navigate-sheet', sheetName: string): void
}>()

const assetCategories = ['房屋建筑物', '机器设备', '运输工具', '办公设备', '其他']

const {
  rows, simplifiedCount, mustRecognizeCount, totalAnnualRental,
  totalExpectedExpense, totalBookExpense, totalDifference,
  h85LeaseTermMismatches, h85ShortTermMissing,
  addRow, deleteRow, updateCell, syncFromH85, load,
} = useH8SimplifiedCheck({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses'),
  onSave: (itemId, value) => emit('save', itemId, value),
})

const wpIdRef = toRef(props, 'wpId')
const projectIdRef = toRef(props, 'projectId')
const h8ReloadAll = inject<() => Promise<void>>('h8ReloadAll', async () => {})
const { isExporting, isImporting, exportTemplate, exportData, importData } = useH8ImportExport({
  wpId: wpIdRef,
  projectId: projectIdRef,
  sheetCode: 'H8-13',
  onImported: async () => {
    await h8ReloadAll()
    load()
  },
})
const ieBusy = computed(() => isExporting.value || isImporting.value)
const fileInputRef = ref<HTMLInputElement | null>(null)

async function handleExportCommand(cmd: string) {
  if (cmd === 'export-template') await exportTemplate(['H8-13'])
  else if (cmd === 'export-data') await exportData(['H8-13'])
  else if (cmd === 'import-data') fileInputRef.value?.click()
}
async function onFileSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) await importData(file, ['H8-13'])
  ;(e.target as HTMLInputElement).value = ''
}

const syncAlertTitle = computed(() => {
  const parts: string[] = []
  if (h85LeaseTermMismatches.value.length) {
    const m = h85LeaseTermMismatches.value[0]
    parts.push(`${h85LeaseTermMismatches.value.length} 行租期不一致（例 ${m.contractNo} ${m.h813Months}≠${m.h85Months}月）`)
  }
  if (h85ShortTermMissing.value.length) {
    parts.push(`H8-5 有 ${h85ShortTermMissing.value.length} 份短期候选未纳入本表`)
  }
  return parts.join('；') || '与 H8-5 存在差异'
})

// ── 审计说明 / 审计结论（持久化 checklist_responses，conclusion:null）──
const AUDIT_NOTE_KEY = 'H8-simplified-audit-note'
const AUDIT_CONCLUSION_KEY = 'H8-simplified-audit-conclusion'
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

function fmtAmt(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function handleAddRow() {
  const { value } = await ElMessageBox.prompt('请输入合同号', '新增检查行', {
    confirmButtonText: '确认', cancelButtonText: '取消', inputPlaceholder: '如：LEASE-2024-001',
  })
  if (value) addRow(value)
}

function handleSyncH85() {
  if (props.isReadonly) return
  const r = syncFromH85({ addMissing: true, onlyShortTerm: true })
  if (!r.ok && r.updated + r.added === 0) {
    ElMessage.warning(r.reason || '同步失败')
    return
  }
  const parts: string[] = []
  if (r.added) parts.push(`新增 ${r.added}`)
  if (r.updated) parts.push(`更新 ${r.updated}`)
  ElMessage.success(parts.length ? `已从 H8-5 同步：${parts.join('，')}` : (r.reason || '已一致'))
}

function getRowClassName({ row }: { row: any }) {
  if (row.simplifiedType === '不符合') return 'noncompliant-row'
  if (Math.abs(row.difference) > 0.005) return 'diff-row'
  return ''
}

function getSummary({ columns }: { columns: any[] }) {
  const labels: Record<string, string> = {}
  return columns.map((col: any, idx: number) => {
    if (idx === 0) return `合计 ${rows.value.length} 笔`
    const prop = col.property
    if (prop === 'monthlyRent') return ''
    if (col.label === '本期应计租金') return fmtAmt(totalExpectedExpense.value)
    if (prop === 'bookExpense') return fmtAmt(totalBookExpense.value)
    if (col.label === '差异') return fmtAmt(totalDifference.value)
    if (prop === 'annualRental') return fmtAmt(totalAnnualRental.value)
    return labels[prop] ?? ''
  })
}
</script>

<style scoped>
.h8-tab-simplified-check { padding: 16px; font-size: var(--wp-font-size, 13px); }

.objective-alert { margin-bottom: 12px; }
.audit-note-card, .audit-conclusion-card { margin-bottom: 16px; }
.card-title { font-weight: 600; }

.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  border-radius: 0 6px 6px 0; margin-bottom: 16px; font-size: 12px; color: #92400e;
}

.h8-tab-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.nav-chip { cursor: pointer; }
.nav-chip:hover { opacity: 0.85; }
.sync-alert { margin-bottom: 12px; }

.section-title { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
.title-actions { display: flex; gap: 6px; }

.table-card { margin-bottom: 16px; }
.formula-table { font-size: var(--wp-font-size, 13px); }
.formula-table :deep(.formula-col) { background: #f0fdf4; }
.formula-table :deep(.noncompliant-row) { background: #fef2f2 !important; }
.formula-table :deep(.diff-row) { background: #fffbeb !important; }
.diff-warn { color: #dc2626; font-weight: 600; }

.stats-row { display: flex; gap: 12px; margin: 16px 0; flex-wrap: wrap; }
.stat-card { flex: 1; min-width: 140px; text-align: center; }
.stat-label { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px; }
.stat-value { font-size: 18px; font-weight: 700; color: var(--el-color-primary); }
.stat-value.ok { color: #16a34a; }
.stat-value.warn { color: #dc2626; }

.noncompliant-alert { margin: 12px 0; }

.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
