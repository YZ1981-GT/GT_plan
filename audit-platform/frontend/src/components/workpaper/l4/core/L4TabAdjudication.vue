<template>
  <div class="l4-tab-adjudication">
    <!-- ═══ 标题 + 带入/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">L4-1 应付债券审定表</h3>
      </div>
      <div class="section-header-right">
        <el-button size="small" type="primary" plain :loading="adjPull.loading.value" @click="openBringInAdjustment">
          <el-icon><Download /></el-icon>带入调整
        </el-button>
        <el-button v-if="!isReadonly" size="small" type="warning" plain @click="handleImportFromDetail">从 L4-2 明细带入</el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title>审计目标（认定）</template>
      <ol class="ao-list">
        <li><b>完整性：</b>所有应付债券均已记录（负债完整性重点在前）；</li>
        <li><b>存在：</b>记录的应付债券在资产负债表日确实存在；</li>
        <li><b>义务：</b>应付债券确为被审计单位的义务；</li>
        <li><b>计价与分摊：</b>应付债券以恰当金额（摊余成本）列示；</li>
        <li><b>列报与披露：</b>应付债券已恰当列报和充分披露（一年内到期部分重分类至流动负债）。</li>
      </ol>
    </el-alert>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>双期审定结构（负债类贷方 2502）：</strong>
        期初数、期末数各按「未审数 → 账项调整 → 重分类调整 → 审定数」列示，审定数 = 未审 + 账项调整 + 重分类调整；
        最终审定数 = 审定数 − 一年内到期的应付债券（重分类至流动负债）。各品种（普通/可转换）下分 成本/利息调整/应计利息 + 品种小计。
        变动率超 30% 需在原因分析栏说明。
      </div>
    </div>

    <!-- ═══ 审定表主体（双期结构，分组表头） ═══ -->
    <el-table
      :data="displayRows"
      border
      size="small"
      style="width: 100%"
      :row-class-name="getRowClassName"
    >
      <el-table-column prop="label" label="项目" min-width="150" fixed>
        <template #default="{ row }">
          <span :class="{ 'row-bold': row.isSubtotal }">{{ row.label }}</span>
        </template>
      </el-table-column>

      <!-- 期初数 -->
      <el-table-column label="期初数" align="center">
        <el-table-column label="未审数" width="105" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" :model-value="row.beginUnadjusted" :controls="false" size="small" style="width:100%" @change="(v:number|undefined)=>onCell(row.rowKey,'beginUnadjusted',v??0)" />
            <span v-else>{{ fmt(row.beginUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账项调整" width="95" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" :model-value="row.beginAje" :controls="false" size="small" style="width:100%" @change="(v:number|undefined)=>onCell(row.rowKey,'beginAje',v??0)" />
            <span v-else>{{ fmt(row.beginAje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="重分类调整" width="95" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" :model-value="row.beginRje" :controls="false" size="small" style="width:100%" @change="(v:number|undefined)=>onCell(row.rowKey,'beginRje',v??0)" />
            <span v-else>{{ fmt(row.beginRje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="105" align="right">
          <template #header><el-tooltip content="期初审定数 = 未审 + 账项调整 + 重分类调整" placement="top"><span class="formula-col-header">审定数</span></el-tooltip></template>
          <template #default="{ row }"><span class="formula-value">{{ fmt(row.beginAudited) }}</span></template>
        </el-table-column>
        <el-table-column label="减一年内到期" width="105" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" :model-value="row.beginCurrent" :controls="false" size="small" style="width:100%" @change="(v:number|undefined)=>onCell(row.rowKey,'beginCurrent',v??0)" />
            <span v-else>{{ fmt(row.beginCurrent) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="最终审定数" width="105" align="right">
          <template #header><el-tooltip content="最终审定数 = 审定数 − 一年内到期" placement="top"><span class="formula-col-header">最终审定数</span></el-tooltip></template>
          <template #default="{ row }"><span class="formula-value">{{ fmt(row.beginDisclosed) }}</span></template>
        </el-table-column>
      </el-table-column>

      <!-- 期末数 -->
      <el-table-column label="期末数" align="center">
        <el-table-column label="未审数" width="105" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" :model-value="row.endUnadjusted" :controls="false" size="small" style="width:100%" @change="(v:number|undefined)=>onCell(row.rowKey,'endUnadjusted',v??0)" />
            <span v-else>{{ fmt(row.endUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账项调整" width="95" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" :model-value="row.endAje" :controls="false" size="small" style="width:100%" @change="(v:number|undefined)=>onCell(row.rowKey,'endAje',v??0)" />
            <span v-else>{{ fmt(row.endAje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="重分类调整" width="95" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" :model-value="row.endRje" :controls="false" size="small" style="width:100%" @change="(v:number|undefined)=>onCell(row.rowKey,'endRje',v??0)" />
            <span v-else>{{ fmt(row.endRje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="105" align="right">
          <template #header><el-tooltip content="期末审定数 = 未审 + 账项调整 + 重分类调整（回写 TB 2502）" placement="top"><span class="formula-col-header">审定数</span></el-tooltip></template>
          <template #default="{ row }"><span class="formula-value">{{ fmt(row.endAudited) }}</span></template>
        </el-table-column>
        <el-table-column label="减一年内到期" width="105" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" :model-value="row.endCurrent" :controls="false" size="small" style="width:100%" @change="(v:number|undefined)=>onCell(row.rowKey,'endCurrent',v??0)" />
            <span v-else>{{ fmt(row.endCurrent) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="最终审定数" width="105" align="right">
          <template #header><el-tooltip content="最终审定数 = 审定数 − 一年内到期" placement="top"><span class="formula-col-header">最终审定数</span></el-tooltip></template>
          <template #default="{ row }"><span class="formula-value">{{ fmt(row.endDisclosed) }}</span></template>
        </el-table-column>
      </el-table-column>

      <!-- 本期未审较期初 -->
      <el-table-column label="本期未审较期初" align="center">
        <el-table-column label="变动额" width="105" align="right">
          <template #default="{ row }"><span class="formula-value" :class="chg(row.unadjChange)">{{ fmt(row.unadjChange) }}</span></template>
        </el-table-column>
        <el-table-column label="变动率" width="85" align="right">
          <template #default="{ row }"><span class="formula-value" :class="{ 'text-warning': Math.abs(row.unadjRate) > 0.3 }">{{ fmtRate(row.unadjRate) }}</span></template>
        </el-table-column>
      </el-table-column>

      <!-- 本期审定较期初 -->
      <el-table-column label="本期审定较期初" align="center">
        <el-table-column label="变动额" width="105" align="right">
          <template #default="{ row }"><span class="formula-value" :class="chg(row.auditedChange)">{{ fmt(row.auditedChange) }}</span></template>
        </el-table-column>
        <el-table-column label="变动率" width="85" align="right">
          <template #default="{ row }"><span class="formula-value" :class="{ 'text-warning': Math.abs(row.auditedRate) > 0.3 }">{{ fmtRate(row.auditedRate) }}</span></template>
        </el-table-column>
      </el-table-column>

      <!-- 原因分析 -->
      <el-table-column label="原因分析" min-width="150">
        <template #default="{ row }">
          <el-input v-if="row.isEditable && !isReadonly" :model-value="row.reason" size="small" placeholder="变动率超30%需说明" @input="(v:string)=>onCell(row.rowKey,'reason',v)" />
          <span v-else>{{ row.reason || '-' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 合计行 -->
    <el-table :data="[totalRow]" border size="small" style="width:100%;margin-top:-1px" :show-header="false" class="total-table">
      <el-table-column prop="label" min-width="150" fixed><template #default="{ row }"><b>{{ row.label }}</b></template></el-table-column>
      <el-table-column width="105" align="right"><template #default="{ row }"><b>{{ fmt(row.beginUnadjusted) }}</b></template></el-table-column>
      <el-table-column width="95" align="right"><template #default="{ row }"><b>{{ fmt(row.beginAje) }}</b></template></el-table-column>
      <el-table-column width="95" align="right"><template #default="{ row }"><b>{{ fmt(row.beginRje) }}</b></template></el-table-column>
      <el-table-column width="105" align="right"><template #default="{ row }"><b>{{ fmt(row.beginAudited) }}</b></template></el-table-column>
      <el-table-column width="105" align="right"><template #default="{ row }"><b>{{ fmt(row.beginCurrent) }}</b></template></el-table-column>
      <el-table-column width="105" align="right"><template #default="{ row }"><b>{{ fmt(row.beginDisclosed) }}</b></template></el-table-column>
      <el-table-column width="105" align="right"><template #default="{ row }"><b>{{ fmt(row.endUnadjusted) }}</b></template></el-table-column>
      <el-table-column width="95" align="right"><template #default="{ row }"><b>{{ fmt(row.endAje) }}</b></template></el-table-column>
      <el-table-column width="95" align="right"><template #default="{ row }"><b>{{ fmt(row.endRje) }}</b></template></el-table-column>
      <el-table-column width="105" align="right"><template #default="{ row }"><b>{{ fmt(row.endAudited) }}</b></template></el-table-column>
      <el-table-column width="105" align="right"><template #default="{ row }"><b>{{ fmt(row.endCurrent) }}</b></template></el-table-column>
      <el-table-column width="105" align="right"><template #default="{ row }"><b>{{ fmt(row.endDisclosed) }}</b></template></el-table-column>
      <el-table-column width="105" align="right"><template #default="{ row }"><b>{{ fmt(row.unadjChange) }}</b></template></el-table-column>
      <el-table-column width="85" align="right"><template #default="{ row }"><b>{{ fmtRate(row.unadjRate) }}</b></template></el-table-column>
      <el-table-column width="105" align="right"><template #default="{ row }"><b>{{ fmt(row.auditedChange) }}</b></template></el-table-column>
      <el-table-column width="85" align="right"><template #default="{ row }"><b>{{ fmtRate(row.auditedRate) }}</b></template></el-table-column>
      <el-table-column min-width="150" />
    </el-table>

    <!-- ═══ 交叉验证区 ═══ -->
    <div class="cross-check-section">
      <span class="cross-check-label">L4-1 期末审定合计 vs L4-2 明细期末摊余成本合计：</span>
      <el-tag :type="crossCheck.isMatch ? 'success' : 'danger'" size="small">
        {{ crossCheck.isMatch ? '✓ 一致' : '✗ 差异 ' + fmt(crossCheck.diff) + ' 元' }}
      </el-tag>
    </div>

    <!-- ═══ 审计说明 ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">审计说明</span>
          <el-button size="small" :loading="aiLoading" :disabled="isReadonly" @click="handleAiNote">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 4, maxRows: 10 }"
        :placeholder="NOTE_PLACEHOLDER" :disabled="isReadonly" @input="(v:string)=>updateText('note', v)" />
    </el-card>

    <!-- ═══ 审计结论 ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="section-header"><span class="card-title">审计结论</span></div></template>
      <el-input :model-value="conclusion" type="textarea" :autosize="{ minRows: 3 }"
        placeholder="参考：A.未见异常。 B.除上述重大不符事项应作为调整事项予以调整外，其余未见异常。 C.由于存在重大未调整事项，不可确认。"
        :disabled="isReadonly" @input="(v:string)=>updateText('conclusion', v)" />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l4-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>双期结构：期初数/期末数各含未审、账项调整、重分类调整、审定数、减一年内到期、最终审定数</li>
        <li>各品种（普通/可转换）下分 成本（面值）/ 利息调整（溢折价摊销余额）/ 应计利息 + 品种小计</li>
        <li>可从明细表 L4-2 按品种×子项聚合带入期初/期末未审摊余成本</li>
        <li>最终审定数 = 审定数 − 一年内到期（重分类至流动负债，供披露）</li>
        <li>期末审定合计自动回写 TB（科目2502）并通知附注组件</li>
        <li>带入调整：可从集中登记按科目 2502 拉取调整分录，逐笔分配到各品种×子项叶子行的期末账项/重分类调整，带入后审定数自动更新并联动附注</li>
      </ul>
    </details>

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="2502 应付债券"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * L4TabAdjudication — L4-1 应付债券审定表（双期结构，2026-07 复盘重建）
 *
 * 对齐致同源模板：期初数/期末数各(未审/账项调整/重分类/审定/减一年内到期/最终审定)
 * + 本期未审较期初(变动额/率) + 本期审定较期初(变动额/率) + 原因分析。
 * 品种×子项：普通/可转换 × 成本/利息调整/应计利息 + 品种小计 + 合计。
 * - 自 formData.allResponses hydrate（修旧版本地 reactive 归零+不持久化的数据丢失）
 * - 从 L4-2 明细带入 + 与 L4-2 期末摊余成本交叉验证
 * - 期末审定合计回写 TB 2502 + EventBus 'substantive:adjudicated'
 */
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, Check, Download } from '@element-plus/icons-vue'
import { inject } from 'vue'
import http from '@/utils/http'
import { useL4FormData } from '../../composables/useL4FormData'
import { useL4Adjudication } from '../../composables/useL4Adjudication'
import { useL4CrossSheet } from '../../composables/useL4CrossSheet'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import { useAuditContext } from '@/composables/useAuditContext'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<() => void>('openReviewDialog', () => {})

// ─── FormData + composables ──────────────────────────────────────────────────

const formData = useL4FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const {
  displayRows, totalRow, totalAuditedAmount,
  auditNote, conclusion, updateText, updateCell, importFromDetail, submitAdjudication,
} = useL4Adjudication(formData)

const { adjudicationVsDetail } = useL4CrossSheet(formData.allResponses)
const crossCheck = computed(() => adjudicationVsDetail.value)

// ─── 从集中登记带入调整（2502 应付债券，负债贷方；双列 endAje/endRje，仅叶子行不含小计） ───
const bringInRows = computed(() =>
  displayRows.value
    .filter((r) => r.isEditable && !r.isSubtotal)
    .map((r) => ({ rowKey: r.rowKey, name: r.label, aje: r.endAje ?? 0, rje: r.endRje ?? 0 })),
)
const {
  adjPull,
  visible: bringInVisible,
  rowOptions: bringInRowOptions,
  open: openBringInAdjustment,
  apply: onBringInApply,
} = useAdjudicationBringIn({
  projectId: computed(() => props.projectId) as any,
  year: useAuditContext().year as any,
  subjectPrefix: '2502',
  direction: 'credit',
  subjectCode: '2502',
  wpCode: 'L4',
  subjectLabel: '应付债券(2502)',
  rows: bringInRows,
  updateCell: (rowKey: string, field: any, value: number) =>
    updateCell(rowKey, field === 'rje' ? 'endRje' : 'endAje', value),
  totalAudited: () => totalRow.value.endAudited,
})

// ─── 编辑 ────────────────────────────────────────────────────────────────────

function onCell(rowKey: string, field: string, value: number | string): void {
  updateCell(rowKey, field as any, value)
}

// ─── 从明细带入 ──────────────────────────────────────────────────────────────

async function handleImportFromDetail() {
  try {
    await ElMessageBox.confirm(
      '将按品种×子项从明细表 L4-2 聚合期初/期末未审摊余成本带入审定表，覆盖对应行未审数（账项调整/重分类调整保留）。是否继续？',
      '从 L4-2 明细带入',
      { confirmButtonText: '带入', cancelButtonText: '取消', type: 'warning' },
    )
    const count = importFromDetail()
    if (count > 0) ElMessage.success(`已带入 ${count} 行`)
    else ElMessage.info('明细表暂无数据可带入')
  } catch { /* 取消 */ }
}

// ─── 审计说明 AI ─────────────────────────────────────────────────────────────

const NOTE_PLACEHOLDER =
  '（1）应付债券期末余额较期初增减及主要原因（比例超30%需说明）。\n' +
  '（2）各品种债券的发行、计息、兑付情况；一年内到期的应付债券重分类至流动负债的情况。\n' +
  '（3）利息调整（溢折价）摊销与实际利率法测算核对情况。\n' +
  '（4）可转换债券负债/权益成分拆分及后续计量情况。'

const aiLoading = ref(false)

async function handleAiNote() {
  if (props.isReadonly) return
  aiLoading.value = true
  try {
    const t = totalRow.value
    const context: Record<string, string> = {
      期末审定合计: String(t.endAudited),
      期初审定合计: String(t.beginAudited),
      变动额: String(t.auditedChange),
      变动率百分比: (t.auditedRate * 100).toFixed(2),
      一年内到期合计: String(t.endCurrent),
    }
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'L4-1-note',
      prompt: '请基于应付债券审定表数据撰写审计说明，覆盖：①期末较期初增减及原因②各品种发行/计息/兑付及一年内到期重分类③利息调整摊销④可转换债券负债/权益拆分。',
      existingContent: auditNote.value,
      context,
    })
    const content = (res.data?.data ?? res.data)?.content
    if (content) updateText('note', content)
    else ElMessage.info('AI 未返回内容，请手动撰写')
  } catch {
    ElMessage.info('AI 辅助暂不可用，请手动撰写')
  } finally {
    aiLoading.value = false
  }
}

function handleReview() {
  openReviewDialog?.()
}

// ─── TB 回写（期末审定合计变化 → 自动回写） ─────────────────────────────────

watch(totalAuditedAmount, async (newVal, oldVal) => {
  if (props.isReadonly) return
  if (oldVal !== undefined && newVal !== oldVal) {
    await submitAdjudication()
  }
})

// ─── 行样式 ──────────────────────────────────────────────────────────────────

function getRowClassName({ row }: { row: { isSubtotal: boolean } }): string {
  return row.isSubtotal ? 'subtotal-row' : ''
}

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function fmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRate(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return `${(val * 100).toFixed(2)}%`
}

function chg(val: number): Record<string, boolean> {
  return { 'text-danger': val < 0, 'text-success': val > 0 }
}

// ─── 加载 ────────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
})
</script>

<style scoped>
.l4-tab-adjudication {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }

.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }

.methodology-context {
  border-left: 4px solid #f59e0b;
  background: #fffbeb;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
}

.methodology-text { font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }
.methodology-text strong { color: #b45309; }

.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.row-bold { font-weight: 600; }

:deep(.subtotal-row) { background-color: #f5f7fa !important; font-weight: 600; }
.total-table :deep(.el-table__row) { background-color: #f0f9eb !important; }

:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.el-table th .cell) { font-size: var(--wp-font-size, 13px); font-weight: 600; }

.cross-check-section {
  margin: 12px 0;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--wp-font-size, 13px);
}
.cross-check-label { color: #606266; }

.text-danger { color: #f56c6c; }
.text-success { color: #67c23a; }
.text-warning { color: #e6a23c; font-weight: 600; }

.audit-note-card { margin-top: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }
.audit-note-card :deep(.el-textarea__inner) { font-size: var(--wp-font-size, 13px); }

.l4-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}
.l4-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l4-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }

.audit-objective { margin-bottom: 12px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.55; font-size: 12px; }
</style>
