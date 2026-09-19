<template>
  <div class="m2-tab-fx-invest">
    <!-- ═══ 标题 + 操作栏 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M2-4 外币投资汇率测算表</h3>
        <el-tag type="warning" size="small">13公式·动态行</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
          <el-icon><Plus /></el-icon> 新增出资人
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
        <el-button size="small" :loading="aiLoading" :disabled="isReadonly" @click="handleAI">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>外币出资折算规则（CAS19/CAS30）：</strong>
        境外出资人以外币出资时，按实际收到出资当日即期汇率折算为本位币（人民币）。
        折算本位币 = 原币出资 × 出资日汇率；折算差异 = 折算本位币 − 账面本位币。
        折算差异计入资本公积——资本（股本）溢价（M4联动）。|差异| > {{ fxThreshold.toLocaleString() }} 元时红色高亮。
      </div>
    </div>

    <!-- ═══ 审计目标 ═══ -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective-alert">
      <template #title>一、审计目标</template>
      <div class="ao-text">
        实收资本以恰当的金额包括在财务报表中，与之相关的<strong>计价或分摊调整已恰当记录</strong>，相关披露已得到恰当计量和描述。
      </div>
    </el-alert>

    <!-- ═══ 主表（20×7，13公式） ═══ -->
    <el-table :data="computedRows" border size="small" style="width: 100%" highlight-current-row>
      <el-table-column type="index" label="#" width="50" align="center" fixed />

      <!-- 出资人 -->
      <el-table-column prop="investorName" label="出资人" min-width="160" fixed>
        <template #default="{ row }">
          <span>{{ row.investorName || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 原币出资（用户输入） -->
      <el-table-column label="原币出资" width="140" align="right">
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

      <!-- 出资日汇率（用户输入） -->
      <el-table-column label="出资日汇率" width="130" align="right">
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

      <!-- 折算本位币（公式列） -->
      <el-table-column label="折算本位币" width="140" align="right">
        <template #header>
          <el-tooltip content="公式: 原币出资 × 出资日汇率" placement="top">
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

      <!-- 折算差异（公式列） -->
      <el-table-column label="折算差异" width="140" align="right">
        <template #header>
          <el-tooltip content="公式: 折算本位币 − 账面本位币（差异计入M4资本公积）" placement="top">
            <span class="formula-col-header">折算差异</span>
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
          <el-popconfirm title="确认删除该出资人？" @confirm="handleRemoveRow($index)">
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
      <span>折算差异合计：<strong :class="{ 'fx-diff-alert': Math.abs(totalFxDiff) > fxThreshold }">{{ fmtAmount(totalFxDiff) }}</strong></span>
      <span>共 <strong>{{ rows.length }}</strong> 个外币出资人</span>
    </div>

    <!-- ═══ 差异>阈值提示区 ═══ -->
    <el-alert
      v-if="Math.abs(totalFxDiff) > fxThreshold"
      title="折算差异超阈值"
      type="warning"
      :closable="false"
      show-icon
      class="fx-alert"
    >
      <template #default>
        折算差异合计 <strong>{{ fmtAmount(totalFxDiff) }}</strong> 超过阈值（{{ fxThreshold.toLocaleString() }}元），
        该差异应计入<strong>M4 资本公积——资本（股本）溢价</strong>。请确认已在M4中正确反映。
      </template>
    </el-alert>

    <!-- ═══ 跨底稿联动 ═══ -->
    <div class="cross-wp-links">
      <span class="cross-wp-label">cross_wp_ref：</span>
      <GtIndexChip value="M2-2" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">明细表（外币出资人来源）</span>
      <GtIndexChip value="M4" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">资本公积（折算差异去向）</span>
    </div>

    <!-- ═══ 三、审计说明 ═══ -->
    <el-card shadow="never" class="opinion-card">
      <template #header>
        <div class="opinion-header">
          <span class="card-title">三、审计说明</span>
          <el-button size="small" :loading="aiLoading" :disabled="isReadonly" @click="handleAI">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        :placeholder="auditNotePlaceholder"
        @change="persistNote"
      />
    </el-card>

    <!-- ═══ 四、审计结论 ═══ -->
    <el-card shadow="never" class="opinion-card">
      <template #header>
        <div class="opinion-header">
          <span class="card-title">四、审计结论</span>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="基于上述折算测试情况，形成审计结论..."
        @change="persistNote"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>外币出资人数据来源于M2-2明细表中币种≠CNY的出资人</li>
        <li>出资日汇率使用实际收到出资当日即期汇率（央行中间价）</li>
        <li>折算本位币 = 原币出资 × 出资日汇率（13公式前端实时计算）</li>
        <li>折算差异 = 折算本位币 − 账面本位币（正值=折算>账面=多记资本公积贷方）</li>
        <li>折算差异超阈值（{{ fxThreshold.toLocaleString() }}元）红色高亮，差异计入M4资本公积</li>
        <li>依据：CAS19外币折算 + CAS30财务报表列报</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M2TabFxInvest — M2-4 外币投资汇率测算表（20×7，13公式）
 *
 * Spec: .kiro/specs/m2-paid-in-capital/
 * Task: 4.4
 * Requirements: 4.1-4.5
 *
 * 功能：
 * - 列：出资人 | 原币出资 | 币种 | 出资日汇率 | 折算本位币[公式] | 账面本位币 | 折算差异[公式]
 * - 13 formulas all computed real-time: calcFxConverted, calcFxDiff
 * - Red highlight when |折算差异| > threshold
 * - 提示差异计入M4资本公积
 * - Dynamic rows (按出资人列表)
 * - Import/Export dropdown for M2-4
 * - GtIndexChip → M4 (跨底稿联动)
 * - Uses useM2FxEngine + useM2FormData + useM2ImportExport
 */
import { computed, inject, onMounted, ref, watch } from 'vue'
import { Plus, MagicStick, Check, Warning } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import type { GenerateWorkpaperAiText } from '../../composables/useWorkpaperScaffold'
import { useM2FormData } from '../../composables/useM2FormData'
import { useM2ImportExport } from '../../composables/useM2ImportExport'
import { calcFxConverted, calcFxDiff } from '../../composables/useM2FxEngine'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})
const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')
const aiLoading = ref(false)

// ─── Types ───────────────────────────────────────────────────────────────────

interface FxRow {
  key: string
  investorName: string
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

const FX_THRESHOLD_DEFAULT = 10000 // |折算差异| > 10000 元红色高亮
const currencyOptions = ['USD', 'EUR', 'GBP', 'JPY', 'HKD', 'SGD', 'AUD', 'CAD', 'CHF', 'KRW']

// ─── State ───────────────────────────────────────────────────────────────────

const fxThreshold = ref(FX_THRESHOLD_DEFAULT)
const rows = ref<FxRow[]>([])
const auditNote = ref('')
const auditConclusion = ref('')

// ─── 审计说明预填提示 ──────────────────────────────────────────────────────────

const auditNotePlaceholder = computed(() => {
  if (rows.value.length === 0) return '填写外币出资折算测试情况及结果...'
  const diffTotal = totalFxDiff.value
  if (Math.abs(diffTotal) > fxThreshold.value) {
    return `折算差异合计${fmtAmount(diffTotal)}元，超过阈值，差异应计入资本公积——资本（股本）溢价（M4）...`
  }
  return '折算差异在合理范围内，未见异常...'
})

// ─── Composables ─────────────────────────────────────────────────────────────

const formData = useM2FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const { exportTemplate, exportData, importData } = useM2ImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── Computed（13公式实时计算） ───────────────────────────────────────────────

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
  formData.debouncedSave('M2-M2-4-fx-rows', {
    remark: JSON.stringify(rows.value),
  })
}

function _restoreRows(): void {
  const saved = formData.allResponses.value.get('M2-M2-4-fx-rows')
  if (saved?.remark) {
    try {
      const parsed = JSON.parse(saved.remark)
      if (Array.isArray(parsed) && parsed.length > 0) {
        rows.value = parsed
        return
      }
    } catch { /* use empty */ }
  }
  rows.value = []
  // 恢复审计说明和结论
  const noteResp = formData.allResponses.value.get('M2-M2-4-auditNote')
  if (noteResp?.remark) auditNote.value = noteResp.remark
  const conclusionResp = formData.allResponses.value.get('M2-M2-4-conclusion')
  if (conclusionResp?.remark) auditConclusion.value = conclusionResp.remark
}

function persistNote(): void {
  formData.debouncedSave('M2-M2-4-auditNote', { remark: auditNote.value || null })
  formData.debouncedSave('M2-M2-4-conclusion', { remark: auditConclusion.value || null })
}

// ─── Handlers ────────────────────────────────────────────────────────────────

async function handleAddRow(): Promise<void> {
  try {
    const { value: name } = await ElMessageBox.prompt(
      '请输入外币出资人名称',
      '新增外币出资人',
      { confirmButtonText: '确定', cancelButtonText: '取消', inputPlaceholder: '如：ABC International Ltd.' },
    )
    if (!name?.trim()) return
    rows.value.push({
      key: `fx-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      investorName: name.trim(),
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
      exportTemplate('M2-4')
      break
    case 'exportData':
      exportData('M2-4')
      break
    case 'importData': {
      const input = document.createElement('input')
      input.type = 'file'
      input.accept = '.xlsx,.xls'
      input.onchange = async (e: Event) => {
        const file = (e.target as HTMLInputElement).files?.[0]
        if (file) {
          const result = await importData(file, 'M2-4')
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

async function handleAI(): Promise<void> {
  if (props.isReadonly) return
  aiLoading.value = true
  try {
    const context: Record<string, string> = {
      科目: '4001 实收资本/股本（外币出资折算）',
      外币出资人数: String(rows.value.length),
      折算本位币合计: fmtAmount(totalConverted.value),
      账面本位币合计: fmtAmount(totalBooked.value),
      折算差异合计: fmtAmount(totalFxDiff.value),
      差异阈值: String(fxThreshold.value),
      是否超阈值: Math.abs(totalFxDiff.value) > fxThreshold.value ? '是' : '否',
    }
    const text = await generateAiText({ section: 'm2-4-fx-note', context, existingContent: auditNote.value })
    if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
    auditNote.value = text
    persistNote()
  } catch {
    ElMessage.warning('AI 生成失败，请稍后重试')
  } finally {
    aiLoading.value = false
  }
}
function handleReview(): void { openReviewDialog?.('M2-4-fx-invest', '外币投资汇率测算表') }

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

watch(rows, _persistRows, { deep: true })
</script>

<style scoped>
.m2-tab-fx-invest { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.formula-value--primary { color: #67c23a; font-weight: 600; }
.fx-diff-alert { color: #f56c6c !important; font-weight: 700; }
.fx-warning-icon { color: #f56c6c; margin-left: 4px; vertical-align: middle; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.summary-bar { display: flex; gap: 24px; padding: 10px 16px; margin-top: 12px; background: #f5f7fa; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; flex-wrap: wrap; }
.fx-alert { margin-top: 12px; }
.audit-objective-alert { margin-bottom: 14px; }
.ao-text { font-size: var(--wp-font-size, 13px); line-height: 1.6; }
.opinion-card { margin-top: 14px; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.card-title { font-size: 13px; font-weight: 600; color: #303133; }
.cross-wp-links { display: flex; align-items: center; gap: 8px; margin-top: 16px; padding: 10px 14px; background: #f0f9ff; border: 1px solid #d9ecff; border-radius: 6px; flex-wrap: wrap; }
.cross-wp-label { font-size: 12px; color: #409eff; font-weight: 500; }
.cross-wp-desc { font-size: 12px; color: #909399; }
.m2-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.m2-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.m2-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
