<script setup lang="ts">
/**
 * D4TabAdjudication — D4-1 审定表
 *
 * 双区块el-table（主营+其他）+ 合计行不可编辑 + 跨sheet浅蓝背景
 * 变动率>30%红色 + 差异≠0红色 + 交叉验证el-alert
 * 审计说明/结论textarea + AI按钮(disabled) + 💬复核 + GtIndexChip→D4-6/D4-7/D4-2
 *
 * Requirements: 2.1-2.10, 19.1, 21.1
 */
import { computed, ref, inject, toRef, type Ref } from 'vue'
import { useD4Adjudication, type AdjudicationRow, type AdjudicationSection } from '../../composables/useD4Adjudication'
import { isChangeRateExceeding } from '../../composables/useD4FormulaEngine'
import { useD4ImportExport } from '../../composables/useD4ImportExport'
import GtIndexChip from '../../GtIndexChip.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

// ─── 复核对话注入 ─────────────────────────────────────────────────────
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)
const reloadWorkpaperData = inject<(() => Promise<void> | void) | null>('reloadWorkpaperData', null)

const wpIdRef = computed(() => props.wpId) as unknown as Ref<string>
const projectIdRef = computed(() => props.projectId) as unknown as Ref<string>
const { exportTemplate, exportData, importData, importing } = useD4ImportExport({
  wpId: wpIdRef,
  projectId: projectIdRef,
})

async function onExportTemplate(): Promise<void> {
  await exportTemplate('D4-1')
}

async function onExportData(): Promise<void> {
  await exportData('D4-1')
}

async function onImportFile(file: File): Promise<boolean> {
  const result = await importData('D4-1', file)
  if (result && reloadWorkpaperData) await reloadWorkpaperData()
  return false
}

// ─── 金额格式化 ───────────────────────────────────────────────────────
function fmtAmount(v: number): string {
  if (v === 0) return '-'
  if (v < 0) return `(${Math.abs(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRate(rate: number | '' | 'N/A'): string {
  if (rate === '' || rate === 'N/A') return rate === '' ? '-' : 'N/A'
  return (rate * 100).toFixed(1) + '%'
}

// ─── Composable ───────────────────────────────────────────────────────
const {
  sections,
  grandTotalRow,
  trialBalanceRow,
  differenceRow,
  mainCrossValidation,
  otherCrossValidation,
  auditNote,
  auditConclusion,
  updateCell,
  addProductRow,
  removeProductRow,
  publishAdjudicated,
} = useD4Adjudication({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

// ─── 变动率计算（基于审定数） ───────────────────────────────────────────
function getChangeRate(row: AdjudicationRow): number | '' | 'N/A' {
  const prior = row.priorAudited
  const current = row.currentAudited
  if (prior === 0 && current === 0) return ''
  if (prior === 0) return 'N/A'
  return (current - prior) / prior
}

// ─── 样式判断 ─────────────────────────────────────────────────────────
function getCellClass(row: AdjudicationRow, field: string): string {
  const classes: string[] = []
  if (row.isFromCrossSheet) classes.push('cross-sheet-cell')
  if (field === 'changeRate') {
    const rate = getChangeRate(row)
    if (isChangeRateExceeding(rate, 0.3)) classes.push('rate-warning')
  }
  return classes.join(' ')
}

function getRowClassName({ row }: { row: AdjudicationRow }): string {
  if (row.rowKey.includes('subtotal') || row.rowKey === 'grand-total') return 'subtotal-row-bg'
  return ''
}

// ─── 差异状态 ─────────────────────────────────────────────────────────
const hasDifference = computed(() => Math.abs(differenceRow.value) > 0.005)

// ─── 合并展示数据（按区块拼接） ────────────────────────────────────────
const tableData = computed(() => {
  const result: (AdjudicationRow & { _sectionLabel?: string })[] = []
  for (const section of sections.value) {
    for (const row of section.rows) {
      result.push(row)
    }
    result.push(section.subtotalRow)
  }
  result.push(grandTotalRow.value)
  return result
})

// ─── AI辅助（真实接入） ──────────────────────────────────────────────
const aiAvailable = ref(false)
const aiLoadingKey = ref<string | null>(null)
async function checkAiHealth() {
  try {
    const res = await http.get('/api/ai/health', { _silent: true } as any)
    const s = res.data?.data?.status ?? res.data?.status
    aiAvailable.value = s === 'healthy' || s === 'degraded'
  } catch { aiAvailable.value = false }
}
checkAiHealth()

async function generateAuditNote() {
  if (props.isReadonly || !aiAvailable.value) return
  aiLoadingKey.value = 'note'
  try {
    const ctx = sections.value.map(sec => {
      const sub = sec.subtotalRow
      return `${sec.sectionLabel}: 本期审定=${fmtAmount(sub.currentAudited)}, 上期审定=${fmtAmount(sub.priorAudited)}, 变动率=${fmtRate(getChangeRate(sub))}`
    }).join('\n')
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, {
      section: 'adj-note', existingContent: ctx, relatedContext: {},
    }, { _silent: true } as any)
    const text = res.data?.data?.content ?? res.data?.content ?? ''
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text.length > 300 ? text.slice(0, 300) + '…' : text, 'AI 生成 · 审计说明', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' })
    auditNote.value = text
  } catch (e: any) { if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败') }
  finally { aiLoadingKey.value = null }
}

async function generateAuditConclusion() {
  if (props.isReadonly || !aiAvailable.value) return
  aiLoadingKey.value = 'conclusion'
  try {
    const ctx = `审计说明：${auditNote.value || '（未填写）'}\n差异：${hasDifference.value ? fmtAmount(differenceRow.value) : '核对一致'}`
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, {
      section: 'adj-conclusion', existingContent: ctx, relatedContext: {},
    }, { _silent: true } as any)
    const text = res.data?.data?.content ?? res.data?.content ?? ''
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text.length > 300 ? text.slice(0, 300) + '…' : text, 'AI 生成 · 审计结论', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' })
    auditConclusion.value = text
  } catch (e: any) { if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败') }
  finally { aiLoadingKey.value = null }
}

const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')
</script>

<template>
  <div class="d4-tab-adjudication">
    <div class="import-export-bar">
      <el-button-group size="small">
        <el-button @click="onExportTemplate">导出模板</el-button>
        <el-button @click="onExportData">导出数据</el-button>
        <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile">
          <el-button :disabled="isReadonly || importing">导入数据</el-button>
        </el-upload>
      </el-button-group>
    </div>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表反映被审计单位营业收入（科目6001+6051）审定过程。</p>
        <p>2. "未审数"列取自试算平衡表，"AJE/RJE"列取自D4-4调整分录。</p>
        <p>3. 浅蓝背景单元格为跨sheet自动取数（D4-2/D4-3），不可手工编辑。</p>
        <p>4. 变动率超过30%的项目请在审计说明中解释原因。</p>
        <p>5. 审定完成后请点击"确认审定"回写试算表。</p>
      </div>
    </details>

    <!-- 交叉验证警告 -->
    <el-alert
      v-if="mainCrossValidation"
      type="warning"
      :closable="false"
      class="cross-alert"
    >
      {{ mainCrossValidation }}
    </el-alert>
    <el-alert
      v-if="otherCrossValidation"
      type="warning"
      :closable="false"
      class="cross-alert"
    >
      {{ otherCrossValidation }}
    </el-alert>

    <!-- 差异警告 -->
    <el-alert
      v-if="hasDifference"
      type="error"
      :closable="false"
      class="cross-alert"
    >
      审定合计与试算平衡表差异：{{ fmtAmount(differenceRow) }}元
    </el-alert>

    <!-- 区块标题 + 操作 -->
    <div class="section-toolbar">
      <div class="toolbar-left">
        <el-tooltip placement="top" :show-after="300">
        <template #content>
          本表项目列数据从 D4-2(主营明细) 和 D4-3(其他明细) 自动取数填充。<br/>
          添加行前，建议先完成 D4-2/D4-3 底稿编制。
        </template>
        <el-button size="small" :disabled="isReadonly" @click="addProductRow">+ 添加产品行</el-button>
      </el-tooltip>
      </div>
      <div class="toolbar-right">
        <GtIndexChip value="wp:D4-2" :context-project-id="projectId" />
        <GtIndexChip value="wp:D4-6" :context-project-id="projectId" />
        <GtIndexChip value="wp:D4-7" :context-project-id="projectId" />
      </div>
    </div>

    <!-- 一、主营业务收入 -->
    <template v-for="(section, sIdx) in sections" :key="section.sectionKey">
      <h4 class="section-title">{{ section.sectionLabel }}</h4>
      <el-table
        :data="[...section.rows, section.subtotalRow]"
        border
        size="small"
        :row-class-name="getRowClassName"
        style="width: 100%; margin-bottom: 16px"
        @cell-contextmenu="(row: any, col: any, e: MouseEvent) => {
          if (!openReviewDialog) return
          e.preventDefault()
          openReviewDialog(`D4-1-adj-${section.sectionKey}-${row.rowKey}`)
        }"
      >
        <el-table-column prop="label" label="项目" min-width="160" fixed>
          <template #default="{ row }">
            <el-input
              v-if="row.isEditable && !row.isFixed && !isReadonly"
              :model-value="row.label || ''"
              size="small"
              placeholder="产品名称"
              @change="(val: string) => updateCell(row.rowKey, 'label', val)"
            />
            <span v-else :class="{ 'font-bold': row.rowKey.includes('subtotal') }">{{ row.label || '(未命名)' }}</span>
          </template>
        </el-table-column>

        <!-- 本期 -->
        <el-table-column label="本期" align="center">
          <el-table-column label="未审数" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.isEditable && !row.isFixed && !isReadonly && !row.isFromCrossSheet"
                :model-value="row.currentUnadjusted"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number) => updateCell(row.rowKey, 'currentUnadjusted', val ?? 0)"
              />
              <span v-else :class="getCellClass(row, 'currentUnadjusted')">{{ fmtAmount(row.currentUnadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账项调整" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.isEditable && !row.isFixed && !isReadonly && !row.isFromCrossSheet"
                :model-value="row.currentAje"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number) => updateCell(row.rowKey, 'currentAje', val ?? 0)"
              />
              <span v-else :class="getCellClass(row, 'currentAje')">{{ fmtAmount(row.currentAje) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="重分类调整" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.isEditable && !row.isFixed && !isReadonly && !row.isFromCrossSheet"
                :model-value="row.currentRje"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number) => updateCell(row.rowKey, 'currentRje', val ?? 0)"
              />
              <span v-else :class="getCellClass(row, 'currentRje')">{{ fmtAmount(row.currentRje) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定数" min-width="110" align="right">
            <template #default="{ row }">
              <span class="audited-cell">{{ fmtAmount(row.currentAudited) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 上期 -->
        <el-table-column label="上期" align="center">
          <el-table-column label="未审数" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.isEditable && !row.isFixed && !isReadonly"
                :model-value="row.priorUnadjusted"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number) => updateCell(row.rowKey, 'priorUnadjusted', val ?? 0)"
              />
              <span v-else>{{ fmtAmount(row.priorUnadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账项调整" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.isEditable && !row.isFixed && !isReadonly"
                :model-value="row.priorAje"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number) => updateCell(row.rowKey, 'priorAje', val ?? 0)"
              />
              <span v-else>{{ fmtAmount(row.priorAje) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="重分类调整" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.isEditable && !row.isFixed && !isReadonly"
                :model-value="row.priorRje"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number) => updateCell(row.rowKey, 'priorRje', val ?? 0)"
              />
              <span v-else>{{ fmtAmount(row.priorRje) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定数" min-width="110" align="right">
            <template #default="{ row }">
              <span class="audited-cell">{{ fmtAmount(row.priorAudited) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 变动 -->
        <el-table-column label="变动率" min-width="90" align="right">
          <template #default="{ row }">
            <span :class="getCellClass(row, 'changeRate')">{{ fmtRate(getChangeRate(row)) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- 营业收入合计 -->
    <el-table
      :data="[grandTotalRow]"
      border
      size="small"
      :show-header="false"
      style="width: 100%; margin-bottom: 16px"
    >
      <el-table-column min-width="160" fixed>
        <template #default>
          <span class="font-bold">营业收入合计</span>
        </template>
      </el-table-column>
      <el-table-column min-width="100" align="right">
        <template #default="{ row }"><span>{{ fmtAmount(row.currentUnadjusted) }}</span></template>
      </el-table-column>
      <el-table-column min-width="100" align="right">
        <template #default="{ row }"><span>{{ fmtAmount(row.currentAje) }}</span></template>
      </el-table-column>
      <el-table-column min-width="100" align="right">
        <template #default="{ row }"><span>{{ fmtAmount(row.currentRje) }}</span></template>
      </el-table-column>
      <el-table-column min-width="110" align="right">
        <template #default="{ row }"><span class="audited-cell">{{ fmtAmount(row.currentAudited) }}</span></template>
      </el-table-column>
      <el-table-column min-width="100" align="right">
        <template #default="{ row }"><span>{{ fmtAmount(row.priorUnadjusted) }}</span></template>
      </el-table-column>
      <el-table-column min-width="100" align="right">
        <template #default="{ row }"><span>{{ fmtAmount(row.priorAje) }}</span></template>
      </el-table-column>
      <el-table-column min-width="100" align="right">
        <template #default="{ row }"><span>{{ fmtAmount(row.priorRje) }}</span></template>
      </el-table-column>
      <el-table-column min-width="110" align="right">
        <template #default="{ row }"><span class="audited-cell">{{ fmtAmount(row.priorAudited) }}</span></template>
      </el-table-column>
      <el-table-column min-width="90" align="right">
        <template #default="{ row }"><span :class="{ 'rate-warning': isChangeRateExceeding(getChangeRate(row), 0.3) }">{{ fmtRate(getChangeRate(row)) }}</span></template>
      </el-table-column>
    </el-table>

    <!-- TB核对行 -->
    <div class="tb-check-row">
      <span class="tb-label">试算平衡表数（6001+6051）：</span>
      <span>{{ fmtAmount(trialBalanceRow.total) }}</span>
      <el-tag v-if="hasDifference" type="danger" size="small" class="diff-tag">
        差异 {{ fmtAmount(differenceRow) }}
      </el-tag>
      <el-tag v-else type="success" size="small" class="diff-tag">核对一致</el-tag>
    </div>

    <!-- 确认审定按钮 -->
    <div class="action-row">
      <el-button type="primary" size="small" :disabled="isReadonly" @click="publishAdjudicated">
        确认审定（回写TB）
      </el-button>
    </div>

    <!-- ─── 审计意见区（卡片式，紧贴表格下方） ───── -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明与结论</span>
          <div class="opinion-chips">
            <GtIndexChip value="wp:D4-6" :context-project-id="projectId" />
            <GtIndexChip value="wp:D4-7" :context-project-id="projectId" />
          </div>
        </div>
      </template>

      <!-- 1. 审计说明 -->
      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">1. 审计说明</span>
          <div class="opinion-actions">
            <el-tooltip :content="aiTip" placement="top">
              <el-button size="small" type="primary" plain :loading="aiLoadingKey === 'note'"
                :disabled="isReadonly || !aiAvailable" @click="generateAuditNote">🤖 AI辅助</el-button>
            </el-tooltip>
            <el-button size="small" @click="openReviewDialog?.('D4-1-adj-note')">💬</el-button>
          </div>
        </div>
        <el-input
          v-model="auditNote"
          type="textarea"
          :autosize="{ minRows: 4, maxRows: 10 }"
          :placeholder="`(1) 营业收入本期较上期增加（负数为减少）：____元，变动率____%\n主要原因（比例超过30%的）：\n(2) 公司前五名客户营业收入总额为____元，占公司全部主营业务收入的比例为____%。\n(3) 实际执行的审计程序和完成的底稿概述`"
          :disabled="isReadonly"
        />
      </div>

      <!-- 2. 审计结论 -->
      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">2. 审计结论</span>
          <el-tooltip :content="aiTip" placement="top">
            <el-button size="small" type="primary" plain :loading="aiLoadingKey === 'conclusion'"
              :disabled="isReadonly || !aiAvailable" @click="generateAuditConclusion">🤖 AI辅助</el-button>
          </el-tooltip>
        </div>
        <el-input
          v-model="auditConclusion"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 5 }"
          placeholder="请输入审计结论..."
          :disabled="isReadonly"
        />
      </div>
    </el-card>

    <!-- 上市规则提示（底部折叠，不突兀） -->
    <details class="guidance-details guidance-bottom">
      <summary>📋 上市规则提示</summary>
      <div class="guidance-content guidance-red">
        <p>提示1: 根据2024年沪深北交易所修订的《上市规则》，公司最近一个会计年度经审计的扣除非经常性损益后的净利润和或者扣除非经常性损益前后较低者为负值的，公司应当在年度报告或者更正公告中披露营业收入扣除情况及扣除后的营业收入金额。</p>
        <p>提示2: 针对被近一个会计年度经审计营业收入低于3亿元（沪深主板）/1亿元（科创板、创业板）和净利润及扣除非经常性损益后的净利润均为正值的公司，会计师事务所应当对其日常经营性营业收入扣除情况出具专项核查意见。项目组需完成营业收入扣除情况及相关信息核查表（查看模板）。</p>
      </div>
    </details>
  </div>
</template>

<style scoped>
.d4-tab-adjudication {
  padding: 12px;
}
.import-export-bar { display: flex; justify-content: flex-end; margin-bottom: 12px; }
.d4-tab-adjudication :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.d4-tab-adjudication :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p {
  margin: 2px 0;
}
.cross-alert {
  margin-bottom: 8px;
}
.section-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
}
.toolbar-right {
  display: flex;
  gap: 6px;
}
.gt-index-chip {
  display: inline-block;
  padding: 2px 8px;
  font-size: 12px;
  background: #e6f7ff;
  border: 1px solid #91d5ff;
  border-radius: 4px;
  color: #1890ff;
  cursor: pointer;
}
.gt-index-chip:hover {
  background: #bae7ff;
}
.section-title {
  margin: 12px 0 8px;
  font-size: 14px;
  color: #303133;
}
.cross-sheet-cell {
  background-color: #e6f7ff;
  padding: 2px 4px;
  border-radius: 2px;
}
.rate-warning {
  color: #f56c6c;
  font-weight: 600;
}
.audited-cell {
  font-weight: 600;
}
.font-bold {
  font-weight: 600;
}
:deep(.subtotal-row-bg) {
  background-color: #fafafa !important;
  font-weight: 600;
  font-size: var(--wp-font-size, 13px);
}
.tb-check-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  margin-bottom: 12px;
  font-size: var(--wp-font-size, 13px);
}
.tb-label {
  color: #909399;
}
.diff-tag {
  margin-left: 8px;
}
.action-row {
  margin-bottom: 16px;
}
.note-actions {
  display: flex;
  gap: 6px;
}
.opinion-card {
  margin-top: 16px;
  border-radius: 8px;
}
.opinion-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.opinion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.opinion-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.opinion-chips {
  display: flex;
  gap: 6px;
}
.opinion-section {
  margin-bottom: 16px;
}
.opinion-section:last-child {
  margin-bottom: 0;
}
.opinion-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.opinion-section-label {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}
.opinion-actions {
  display: flex;
  gap: 6px;
}
.note-structure {
  margin-bottom: 8px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
}
.note-prompt {
  margin: 4px 0;
  color: #606266;
  line-height: 1.6;
}
.guidance-bottom {
  margin-top: 16px;
  border-left-color: #f56c6c;
  background: #fef0f0;
}
.guidance-bottom summary {
  color: #f56c6c;
}
.guidance-red p {
  color: #c45656;
  font-size: 12px;
}
</style>
