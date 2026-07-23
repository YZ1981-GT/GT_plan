<template>
  <div class="m1-tab-fx-rate">
    <!-- ═══ 标题 + 操作栏 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M1-4 外币汇率测算表</h3>
        <el-tag type="warning" size="small">13公式·动态行</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
          <el-icon><Plus /></el-icon> 新增外币股东
        </el-button>
        <el-dropdown :disabled="isReadonly" @command="handleImportExport" trigger="click">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item command="exportData">导出数据</el-dropdown-item>
              <el-dropdown-item command="importData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="handleAI('general')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 审计目标 ═══ -->
    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title>审计目标（认定）</template>
      <ol class="ao-list">
        <li><b>计价：</b>外币应付股利按期末即期汇率折算准确；</li>
        <li><b>准确性：</b>汇兑差异计算正确并恰当计入财务费用。</li>
      </ol>
    </el-alert>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>外币应付股利折算规则：</strong>
        对境外股东以外币计价的应付股利，期末按即期汇率折算为本位币。
        折算本位币 = 原币金额 × 期末汇率；汇兑差异 = 折算本位币 − 账面本位币。
        汇兑差异计入财务费用（L8联动）。|差异| > {{ fxThreshold.toLocaleString() }} 元时红色高亮。
      </div>
    </div>

    <!-- ═══ 主表 ═══ -->
    <el-table :data="computedRows" border size="small" style="width: 100%" highlight-current-row>
      <el-table-column type="index" label="#" width="50" align="center" fixed />

      <!-- 股东名称 -->
      <el-table-column prop="shareholderName" label="股东" min-width="160" fixed>
        <template #default="{ row }">
          <span>{{ row.shareholderName || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 原币金额（用户输入） -->
      <el-table-column label="原币金额" width="140" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.amount"
            :controls="false"
            size="small"
            style="width: 100%"
            @change="(val: number | undefined) => handleUpdate($index, 'amount', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.amount) }}</span>
        </template>
      </el-table-column>

      <!-- 币种（用户输入） -->
      <el-table-column label="币种" width="100" align="center">
        <template #default="{ row, $index }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.currency"
            size="small"
            style="width: 100%"
            @change="(val: string) => handleUpdate($index, 'currency', val)"
          >
            <el-option v-for="c in currencyOptions" :key="c" :label="c" :value="c" />
          </el-select>
          <span v-else>{{ row.currency || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 期末汇率（用户输入） -->
      <el-table-column label="期末汇率" width="120" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.rate"
            :controls="false"
            :precision="6"
            size="small"
            style="width: 100%"
            @change="(val: number | undefined) => handleUpdate($index, 'rate', val ?? 0)"
          />
          <span v-else>{{ row.rate ? row.rate.toFixed(6) : '—' }}</span>
        </template>
      </el-table-column>

      <!-- 折算本位币（公式计算） -->
      <el-table-column label="折算本位币" width="140" align="right">
        <template #header>
          <el-tooltip content="公式: 原币金额 × 期末汇率" placement="top">
            <span class="formula-col-header">折算本位币</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-value">{{ fmtAmount(row.converted) }}</span>
        </template>
      </el-table-column>

      <!-- 账面本位币（用户输入） -->
      <el-table-column label="账面本位币" width="140" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.booked"
            :controls="false"
            size="small"
            style="width: 100%"
            @change="(val: number | undefined) => handleUpdate($index, 'booked', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.booked) }}</span>
        </template>
      </el-table-column>

      <!-- 汇兑差异（公式计算） -->
      <el-table-column label="汇兑差异" width="140" align="right">
        <template #header>
          <el-tooltip content="公式: 折算本位币 − 账面本位币" placement="top">
            <span class="formula-col-header">汇兑差异</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span
            class="formula-value"
            :class="{ 'fx-diff-alert': Math.abs(row.fxDiff) > fxThreshold }"
          >
            {{ fmtAmount(row.fxDiff) }}
          </span>
          <el-icon v-if="Math.abs(row.fxDiff) > fxThreshold" class="fx-warning-icon"><Warning /></el-icon>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column v-if="!isReadonly" label="操作" width="70" align="center" fixed="right">
        <template #default="{ $index }">
          <el-popconfirm title="确认删除该外币股东？" @confirm="handleRemoveRow($index)">
            <template #reference>
              <el-button type="danger" text size="small">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 汇总行 ═══ -->
    <div class="summary-bar">
      <span>折算本位币合计：<strong class="formula-value--primary">{{ fmtAmount(totalConverted) }}</strong></span>
      <span>账面本位币合计：<strong>{{ fmtAmount(totalBooked) }}</strong></span>
      <span>汇兑差异合计：<strong :class="{ 'fx-diff-alert': Math.abs(totalFxDiff) > fxThreshold }">{{ fmtAmount(totalFxDiff) }}</strong></span>
      <span>共 <strong>{{ rows.length }}</strong> 个外币股东</span>
    </div>

    <!-- ═══ 跨底稿联动 ═══ -->
    <div class="cross-wp-links">
      <span class="cross-wp-label">cross_wp_ref：</span>
      <GtIndexChip value="M1-2" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">明细表（外币股东来源）</span>
      <GtIndexChip value="L8" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">财务费用（汇兑差异去向）</span>
    </div>

    <!-- ═══ 审计说明 ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">审计说明</span>
          <el-button size="small" @click="handleAI('auditNote')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="请填写外币汇率测算审计说明..." :disabled="isReadonly" @change="saveAuditNote" />
    </el-card>

    <!-- ═══ 审计结论（源模板四、审计结论） ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">审计结论</span>
        </div>
      </template>
      <el-select v-model="conclusionOption" :disabled="isReadonly" size="small" class="concl-select" placeholder="选择结论模板" @change="onConclusionOption">
        <el-option label="A、未见异常，可以确认" value="A" />
        <el-option label="B、经审计调整后可确认" value="B" />
        <el-option label="C、由于存在重大未调整事项（或审计范围受限），不可确认" value="C" />
      </el-select>
      <el-input v-model="conclusionText" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="基于上述汇率测算核对情况，对外币应付股利折算的准确性发表结论..." @change="saveConclusion" />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m1-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>外币股东数据来源于M1-2明细表中币种≠CNY的股东</li>
        <li>期末汇率使用资产负债表日即期汇率（央行中间价）</li>
        <li>折算本位币 = 原币金额 × 期末汇率（13公式前端实时计算）</li>
        <li>汇兑差异 = 折算本位币 − 账面本位币（正值=汇率上升负债增加）</li>
        <li>汇兑差异超阈值（{{ fxThreshold.toLocaleString() }}元）红色高亮，需考虑调整</li>
        <li>汇兑差异最终计入财务费用（L8联动）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M1TabFxRate — M1-4 外币汇率测算表
 *
 * Requirements: 4.1-4.5
 * - 25×7 table: 股东 | 原币金额 | 币种 | 期末汇率 | 折算本位币(calc) | 账面本位币 | 汇兑差异(calc)
 * - 13 formulas all computed real-time in frontend
 * - Red highlight when |汇兑差异| > threshold
 * - Uses calcFxConverted, calcFxDiff from useM1FxEngine
 * - Dynamic rows (按外币股东)
 * - 导入导出 button
 */
import { computed, inject, onMounted, ref } from 'vue'
import { Plus, MagicStick, Check, Warning } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import { useM1FormData } from '../../composables/useM1FormData'
import { useM1ImportExport } from '../../composables/useM1ImportExport'
import { calcFxConverted, calcFxDiff } from '../../composables/useM1FxEngine'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── Types ───────────────────────────────────────────────────────────────────

interface FxRow {
  key: string
  shareholderName: string
  amount: number
  currency: string
  rate: number
  booked: number
}

interface ComputedFxRow extends FxRow {
  converted: number
  fxDiff: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const FX_THRESHOLD_DEFAULT = 10000 // |汇兑差异| > 10000 元红色高亮
const currencyOptions = ['USD', 'EUR', 'GBP', 'JPY', 'HKD', 'SGD', 'AUD', 'CAD', 'CHF', 'KRW']

// ─── State ───────────────────────────────────────────────────────────────────

const fxThreshold = ref(FX_THRESHOLD_DEFAULT)

const rows = ref<FxRow[]>([])

const auditNote = ref('')
// ─── Composables ─────────────────────────────────────────────────────────────

const formData = useM1FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const { exportTemplate, exportData, importData } = useM1ImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── Computed（13 formulas real-time） ────────────────────────────────────────

const computedRows = computed<ComputedFxRow[]>(() => {
  return rows.value.map(row => {
    const converted = calcFxConverted(row.amount, row.rate)
    const fxDiff = calcFxDiff(converted, row.booked)
    return { ...row, converted, fxDiff }
  })
})

const totalConverted = computed(() => computedRows.value.reduce((sum, r) => sum + r.converted, 0))
const totalBooked = computed(() => computedRows.value.reduce((sum, r) => sum + r.booked, 0))
const totalFxDiff = computed(() => computedRows.value.reduce((sum, r) => sum + r.fxDiff, 0))

// ─── Persistence ─────────────────────────────────────────────────────────────

function _persistRows(): void {
  formData.debouncedSave('M1-M1-4-fx-rows', {
    remark: JSON.stringify(rows.value),
  })
}

function _restoreRows(): void {
  const saved = formData.allResponses.value.get('M1-M1-4-fx-rows')
  if (saved?.remark) {
    try {
      const parsed = JSON.parse(saved.remark)
      if (Array.isArray(parsed) && parsed.length > 0) {
        rows.value = parsed
      }
    } catch { /* use empty */ }
  }
  if (rows.value.length === 0) rows.value = []

  // 恢复审计说明
  const savedNote = formData.allResponses.value.get('M1-4-auditNote')
  if (savedNote?.remark) {
    auditNote.value = savedNote.remark
  }

  // 恢复结论
  const savedConclusion = formData.allResponses.value.get('M1-4-conclusion')
  if (savedConclusion?.remark) {
    try {
      const c = JSON.parse(savedConclusion.remark)
      conclusionOption.value = c.option || ''
      conclusionText.value = c.text || ''
    } catch { /* ignore */ }
  }
}

// ─── Handlers ────────────────────────────────────────────────────────────────

async function handleAddRow(): Promise<void> {
  try {
    const { value: name } = await ElMessageBox.prompt(
      '请输入外币股东名称',
      '新增外币股东',
      { confirmButtonText: '确定', cancelButtonText: '取消', inputPlaceholder: '如：ABC Corp' },
    )
    if (!name?.trim()) return
    rows.value.push({
      key: `fx-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      shareholderName: name.trim(),
      amount: 0,
      currency: 'USD',
      rate: 0,
      booked: 0,
    })
    _persistRows()
  } catch {
    // 用户取消
  }
}

function handleRemoveRow(index: number): void {
  rows.value.splice(index, 1)
  _persistRows()
}

function handleUpdate(index: number, field: keyof FxRow, value: any): void {
  if (index < 0 || index >= rows.value.length) return
  ;(rows.value[index] as any)[field] = value
  _persistRows()
}

function handleImportExport(command: string): void {
  switch (command) {
    case 'exportTemplate':
      exportTemplate('M1-4')
      break
    case 'exportData':
      exportData('M1-4')
      break
    case 'importData': {
      const input = document.createElement('input')
      input.type = 'file'
      input.accept = '.xlsx,.xls'
      input.onchange = async (e: Event) => {
        const file = (e.target as HTMLInputElement).files?.[0]
        if (file) {
          const result = await importData(file, 'M1-4')
          if (result) {
            await formData.loadData()
            _restoreRows()
            ElMessage.success(`导入完成，共 ${result.rowCount} 行`)
          }
        }
      }
      input.click()
      break
    }
  }
}

function handleAI(section: string = 'general'): void {
  import('@/utils/http').then(async ({ default: h }) => {
    try {
      const res = await h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
        section: `m1-fx-rate-${section}`,
        prompt: '请基于外币汇率测算表数据，分析汇兑差异及影响，给出审计建议',
        context: {
          section: String(section),
          wpId: String(props.wpId),
          totalConverted: String(totalConverted.value),
          totalBooked: String(totalBooked.value),
          totalFxDiff: String(totalFxDiff.value),
          rowCount: String(rows.value.length),
        },
      })
      const content = res?.data?.content || res?.content || ''
      if (content && !auditNote.value) {
        auditNote.value = content
        saveAuditNote()
      }
    } catch {
      // AI生成失败静默
    }
  })
}
function handleReview(): void { openReviewDialog?.('M1-4-fx-rate', '外币汇率测算表') }

function saveAuditNote() {
  formData.debouncedSave('M1-4-auditNote', { remark: auditNote.value || null })
}

// ─── 审计结论 ────────────────────────────────────────────────────────────────

const conclusionOption = ref('')
const conclusionText = ref('')

function onConclusionOption(val: string) {
  const map: Record<string, string> = {
    A: '未见异常，可以确认。',
    B: '经审计调整后可确认。',
    C: '由于存在上述重大未调整事项（或审计范围受到限制无法获取充分、适当证据），不可确认。',
  }
  if (map[val] && !conclusionText.value) conclusionText.value = map[val]
  saveConclusion()
}

function saveConclusion() {
  formData.debouncedSave('M1-4-conclusion', {
    remark: JSON.stringify({ option: conclusionOption.value, text: conclusionText.value }),
  })
}

// ─── Format ──────────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  _restoreRows()
})
</script>

<style scoped>
.m1-tab-fx-rate { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.audit-objective { margin-bottom: 12px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.55; font-size: 12px; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }
.audit-note-card { margin-top: 16px; }
.conclusion-card { margin-top: 12px; }
.concl-select { width: 100%; margin-bottom: 8px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.formula-value--primary { color: #67c23a; font-weight: 600; }
.fx-diff-alert { color: #f56c6c !important; font-weight: 700; }
.fx-warning-icon { color: #f56c6c; margin-left: 4px; vertical-align: middle; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.summary-bar { display: flex; gap: 24px; padding: 10px 16px; margin-top: 12px; background: #f5f7fa; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; flex-wrap: wrap; }
.cross-wp-links { display: flex; align-items: center; gap: 8px; margin-top: 16px; padding: 10px 14px; background: #f0f9ff; border: 1px solid #d9ecff; border-radius: 6px; flex-wrap: wrap; }
.cross-wp-label { font-size: 12px; color: #409eff; font-weight: 500; }
.cross-wp-desc { font-size: 12px; color: #909399; }
.m1-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.m1-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.m1-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
