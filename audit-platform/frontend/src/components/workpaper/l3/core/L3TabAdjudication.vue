<template>
  <div class="l3-tab-adjudication">
    <!-- ═══ 返回目录 + 标题 + 操作 ═══ -->
    <div class="adj-header">
      <div class="adj-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="adj-title">L3-1 长期借款审定表</h3>
      </div>
      <div class="adj-header-right">
        <el-button size="small" type="primary" plain :loading="adjPull.loading.value" @click="openBringInAdjustment">
          <el-icon><Download /></el-icon>带入调整
        </el-button>
        <el-button v-if="!isReadonly" size="small" type="primary" plain @click="handleImportFromDetail">从L3-2明细带入</el-button>
        <el-button size="small" @click="handleReview"><el-icon><Check /></el-icon> 复核</el-button>
      </div>
    </div>

    <!-- ═══ 审计目标 ═══ -->
    <el-alert type="info" :closable="false" class="audit-objective" show-icon>
      <template #title>审计目标与认定</template>
      <ul class="ao-list">
        <li>A. 资产负债表中记录的长期借款是<strong>存在</strong>的，且已记录于恰当账户（存在）</li>
        <li>B. 所有应记录的长期借款均已记录，相关披露均已包括（<strong>完整性</strong>）</li>
        <li>C. 记录的长期借款是被审计单位应履行的偿还义务（<strong>权利和义务</strong>）</li>
        <li>D. 长期借款以恰当金额列示，计价或分摊调整已恰当记录（<strong>准确性、计价和分摊</strong>）</li>
        <li>E. 长期借款已恰当汇总/分解且表述清楚（<strong>列报</strong>）</li>
      </ul>
    </el-alert>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>长期借款为负债类贷方科目（2501）：</strong>
        审定数 = 未审 + 账项调整 + 重分类调整；<strong>披露审定数 = 审定数 − 减：一年内到期的长期借款</strong>
        （一年内到期部分重分类至流动负债 2801）。按担保方式分类列示期初/期末双期，变动率超 30% 须在原因分析说明。
      </div>
    </div>

    <!-- ═══ 勾稽指示器 ═══ -->
    <div class="cross-check-section">
      <span class="cross-check-label">审定表期末审定合计 vs L3-2明细表合计：</span>
      <span :class="crossCheckClass">
        <template v-if="crossCheckResult.isMatch">✓ 匹配</template>
        <template v-else>✗ 差额 {{ fmtAmount(crossCheckResult.diff) }}</template>
      </span>
    </div>

    <!-- ═══ 审定表主体（期初/期末双期 + 减一年内到期→披露审定 + 变动分析） ═══ -->
    <el-card shadow="never" class="adj-table-card">
      <el-table :data="tableData" border size="small" style="width: 100%" :row-class-name="getRowClassName">
        <el-table-column prop="label" label="项目" min-width="120" fixed>
          <template #default="{ row }">
            <span :class="{ 'row-bold': row.rowKey === '__total__' }">{{ row.label }}</span>
          </template>
        </el-table-column>

        <!-- 期初数 -->
        <el-table-column label="期初数" align="center">
          <el-table-column label="未审数" min-width="105" align="right">
            <template #default="{ row }">
              <el-input-number v-if="canEdit(row)" :model-value="row.beginUnadjusted" :controls="false" size="small" style="width: 100%" @change="(v: number | undefined) => onCell(row, 'beginUnadjusted', v)" />
              <span v-else>{{ fmtAmount(row.beginUnadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账项调整" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="canEdit(row)" :model-value="row.beginAje" :controls="false" size="small" style="width: 100%" @change="(v: number | undefined) => onCell(row, 'beginAje', v)" />
              <span v-else>{{ fmtAmount(row.beginAje) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="重分类调整" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="canEdit(row)" :model-value="row.beginRje" :controls="false" size="small" style="width: 100%" @change="(v: number | undefined) => onCell(row, 'beginRje', v)" />
              <span v-else>{{ fmtAmount(row.beginRje) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定数" min-width="110" align="right">
            <template #header><el-tooltip content="期初审定 = 未审 + 账项调整 + 重分类调整" placement="top"><span class="formula-col-header">审定数</span></el-tooltip></template>
            <template #default="{ row }"><span class="formula-cell">{{ fmtAmount(row.beginAudited) }}</span></template>
          </el-table-column>
          <el-table-column label="减一年内到期" min-width="105" align="right" class-name="current-portion-col">
            <template #default="{ row }">
              <el-input-number v-if="canEdit(row)" :model-value="row.beginCurrent" :controls="false" size="small" style="width: 100%" @change="(v: number | undefined) => onCell(row, 'beginCurrent', v)" />
              <span v-else>{{ fmtAmount(row.beginCurrent) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="披露审定数" min-width="110" align="right">
            <template #header><el-tooltip content="披露审定 = 审定数 − 减一年内到期" placement="top"><span class="formula-col-header">披露审定数</span></el-tooltip></template>
            <template #default="{ row }"><span class="formula-cell">{{ fmtAmount(row.beginDisclosed) }}</span></template>
          </el-table-column>
        </el-table-column>

        <!-- 期末数 -->
        <el-table-column label="期末数" align="center">
          <el-table-column label="未审数" min-width="105" align="right">
            <template #default="{ row }">
              <el-input-number v-if="canEdit(row)" :model-value="row.endUnadjusted" :controls="false" size="small" style="width: 100%" @change="(v: number | undefined) => onCell(row, 'endUnadjusted', v)" />
              <span v-else>{{ fmtAmount(row.endUnadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账项调整" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="canEdit(row)" :model-value="row.endAje" :controls="false" size="small" style="width: 100%" @change="(v: number | undefined) => onCell(row, 'endAje', v)" />
              <span v-else>{{ fmtAmount(row.endAje) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="重分类调整" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="canEdit(row)" :model-value="row.endRje" :controls="false" size="small" style="width: 100%" @change="(v: number | undefined) => onCell(row, 'endRje', v)" />
              <span v-else>{{ fmtAmount(row.endRje) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定数" min-width="110" align="right">
            <template #header><el-tooltip content="期末审定 = 未审 + 账项调整 + 重分类调整" placement="top"><span class="formula-col-header">审定数</span></el-tooltip></template>
            <template #default="{ row }"><span class="formula-cell">{{ fmtAmount(row.endAudited) }}</span></template>
          </el-table-column>
          <el-table-column label="减一年内到期" min-width="105" align="right" class-name="current-portion-col">
            <template #default="{ row }">
              <el-input-number v-if="canEdit(row)" :model-value="row.endCurrent" :controls="false" size="small" style="width: 100%" @change="(v: number | undefined) => onCell(row, 'endCurrent', v)" />
              <span v-else>{{ fmtAmount(row.endCurrent) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="披露审定数" min-width="110" align="right">
            <template #header><el-tooltip content="披露审定 = 审定数 − 减一年内到期（非流动长期借款报表数）" placement="top"><span class="formula-col-header">披露审定数</span></el-tooltip></template>
            <template #default="{ row }"><span class="formula-cell">{{ fmtAmount(row.endDisclosed) }}</span></template>
          </el-table-column>
        </el-table-column>

        <!-- 变动分析 -->
        <el-table-column label="本期审定数与期初审定数比较" align="center">
          <el-table-column label="变动额" min-width="105" align="right">
            <template #default="{ row }"><span class="formula-cell" :class="{ 'warn-change': isBigChange(row) }">{{ fmtAmount(row.auditedChange) }}</span></template>
          </el-table-column>
          <el-table-column label="变动率" min-width="85" align="right">
            <template #default="{ row }"><span :class="{ 'warn-change': isBigChange(row) }">{{ fmtRate(row.auditedRate) }}</span></template>
          </el-table-column>
        </el-table-column>

        <!-- 原因分析 -->
        <el-table-column label="原因分析" min-width="160">
          <template #default="{ row }">
            <el-input v-if="canEdit(row)" :model-value="row.reason" size="small" placeholder="变动率超30%须说明" @input="(v: string) => onCell(row, 'reason', v)" />
            <span v-else>{{ row.reason || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ TB回写 ═══ -->
    <div class="adj-footer">
      <el-button type="primary" :disabled="isReadonly || isSubmitting" :loading="isSubmitting" @click="handleSubmit">TB回写</el-button>
      <span class="footer-hint">回写期末审定合计至试算平衡表（科目 2501 长期借款）；一年内到期部分应经 L3-3 重分类至 2801</span>
    </div>

    <!-- ═══ 审计说明 ═══ -->
    <el-card shadow="never" class="note-card">
      <template #header><span class="note-card-title">1、审计说明</span></template>
      <div class="note-field">
        <div class="note-label"><span>（1）长期借款期末余额较期初增加比例超过30%的主要原因：</span>
          <el-button v-if="!isReadonly" size="small" type="warning" plain :loading="aiLoading === 'change'" @click="handleAi('change')">🤖 AI辅助</el-button></div>
        <el-input :model-value="noteChange" type="textarea" :autosize="{ minRows: 2 }" :readonly="isReadonly" placeholder="说明本期长期借款余额较期初变动的主要原因..." @input="(v: string) => updateNote('note-change', v)" />
      </div>
      <div class="note-field">
        <div class="note-label"><span>（2）已到期未偿还的长期借款情况说明（贷款单位/金额/利率/用途/未按期偿还原因及预计还款期，期后是否已偿还；如展期说明条件及新到期日）：</span></div>
        <el-input :model-value="noteOverdue" type="textarea" :autosize="{ minRows: 2 }" :readonly="isReadonly" placeholder="如有已到期未偿还/展期借款，逐项说明..." @input="(v: string) => updateNote('note-overdue', v)" />
      </div>
      <div class="note-field">
        <div class="note-label"><span>（3）公司用于抵押、质押的财产情况说明：</span></div>
        <el-input :model-value="notePledge" type="textarea" :autosize="{ minRows: 2 }" :readonly="isReadonly" placeholder="说明用于抵押/质押的财产情况（可关联 L3-8）..." @input="(v: string) => updateNote('note-pledge', v)" />
      </div>
      <div class="note-field">
        <div class="note-label"><span>（4）关联方保证、抵押或质押情况说明：</span></div>
        <el-input :model-value="noteGuarantee" type="textarea" :autosize="{ minRows: 2 }" :readonly="isReadonly" placeholder="说明关联方保证/抵押/质押情况..." @input="(v: string) => updateNote('note-guarantee', v)" />
      </div>
    </el-card>

    <!-- ═══ 审计结论 ═══ -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="conclusion-header">
          <span class="note-card-title">2、审计结论</span>
          <el-button v-if="!isReadonly" size="small" type="warning" plain :loading="aiLoading === 'conclusion'" @click="handleAi('conclusion')">🤖 AI辅助</el-button>
        </div>
      </template>
      <el-input :model-value="conclusion" type="textarea" :autosize="{ minRows: 3 }" :readonly="isReadonly" placeholder="A、未见异常。 B、除上述重大不符事项应作调整外，其余未见异常。 C、存在重大未调整事项（或审计范围受限），不可确认。" @input="(v: string) => updateNote('conclusion', v)" />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l3-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>科目方向</strong>：长期借款为负债类贷方科目（2501），审定 = 未审 + 账项调整 + 重分类调整</li>
        <li><strong>分类</strong>：质押借款 / 抵押借款 / 保证借款 / 信用借款（对齐源模板担保方式分类）</li>
        <li><strong>双期结构</strong>：期初/期末各分「未审/账项调整/重分类/审定/减一年内到期/披露审定」</li>
        <li><strong>披露审定数</strong>：= 审定数 − 一年内到期，代表非流动长期借款报表列报数；一年内到期部分经 L3-3 重分类至流动负债 2801</li>
        <li><strong>数据带入</strong>：点「从L3-2明细带入」按借款类型聚合明细期初/期末余额及一年内到期</li>
        <li><strong>TB回写</strong>：期末审定合计回写试算平衡表科目 2501</li>
        <li><strong>借款种类</strong>：担保贷款含保证/抵押/质押；信用贷款系以借款人信誉发放的贷款</li>
        <li><strong>带入调整</strong>：可从集中登记按科目 2501 拉取调整分录，逐笔分配到各担保方式行的期末账项/重分类调整，带入后审定数自动更新并联动附注</li>
      </ul>
    </details>

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="2501 长期借款"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * L3TabAdjudication — L3-1 长期借款审定表（源模板重建：期初/期末双期 + 减一年内到期→披露审定）
 *
 * - 分类行（质押/抵押/保证/信用借款）+ 合计
 * - 期初数/期末数 各（未审/账项调整/重分类/审定/减一年内到期/披露审定）+ 变动分析 + 原因分析
 * - 审计说明（增减原因/已到期未偿还/抵押质押/关联方保证）+ 审计结论
 * - 从 L3-2 明细带入 + TB回写(2501) + AI辅助
 *
 * 科目：2501 长期借款（贷方/负债类）
 */
import { computed, inject, ref, toRef, type Ref } from 'vue'
import { Check, Download } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { useL3FormData } from '@/components/workpaper/composables/useL3FormData'
import { useL3Adjudication, type L3AdjRow } from '@/composables/useL3Adjudication'
import type { AdjudicationVsDetailResult } from '@/components/workpaper/composables/useL3CrossSheet'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import { useAuditContext } from '@/composables/useAuditContext'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

defineEmits<{ (e: 'navigate', sheetName: string): void }>()

// ─── inject formData（由 GtL3 provide） ──────────────────────────────────────
const formData = inject<ReturnType<typeof useL3FormData>>('l3FormData')!
const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})
const adjudicationVsDetail = inject<Ref<AdjudicationVsDetailResult>>(
  'adjudicationVsDetail',
  computed(() => ({ diff: 0, isMatch: true })) as unknown as Ref<AdjudicationVsDetailResult>,
)

const {
  rows,
  totalRow,
  totalAuditedAmount,
  noteChange,
  noteOverdue,
  notePledge,
  noteGuarantee,
  conclusion,
  updateNote,
  updateCell,
  importFromDetail,
  submitAdjudication,
} = useL3Adjudication(formData)

// ─── 从集中登记带入调整（2501 长期借款，负债贷方；双列 endAje/endRje） ───
const bringInRows = computed(() =>
  rows.value
    .filter((r) => r.isEditable && r.rowKey !== '__total__')
    .map((r) => ({ rowKey: r.rowKey, name: r.label, aje: r.endAje ?? 0, rje: r.endRje ?? 0 })),
)
const {
  adjPull,
  visible: bringInVisible,
  rowOptions: bringInRowOptions,
  open: openBringInAdjustment,
  apply: onBringInApply,
} = useAdjudicationBringIn({
  projectId: toRef(props, 'projectId') as any,
  year: useAuditContext().year as any,
  subjectPrefix: '2501',
  direction: 'credit',
  subjectCode: '2501',
  wpCode: 'L3',
  subjectLabel: '长期借款(2501)',
  rows: bringInRows,
  updateCell: (rowKey: string, field: any, value: number) =>
    updateCell(rowKey, field === 'rje' ? 'endRje' : 'endAje', value),
  totalAudited: () => totalRow.value.endAudited,
})

const tableData = computed<L3AdjRow[]>(() => [...rows.value, totalRow.value])

const crossCheckResult = computed<AdjudicationVsDetailResult>(() => adjudicationVsDetail.value)
const crossCheckClass = computed(() => ({
  'cross-check-match': crossCheckResult.value.isMatch,
  'cross-check-diff': !crossCheckResult.value.isMatch,
}))

function canEdit(row: L3AdjRow): boolean {
  return row.isEditable && row.rowKey !== '__total__' && !props.isReadonly
}
function getRowClassName({ row }: { row: L3AdjRow }): string {
  return row.rowKey === '__total__' ? 'total-row' : ''
}
function isBigChange(row: L3AdjRow): boolean {
  return Math.abs(row.auditedRate) > 0.3 && row.rowKey !== '__total__'
}
function onCell(row: L3AdjRow, field: string, value: number | string | undefined): void {
  if (!canEdit(row)) return
  updateCell(row.rowKey, field, typeof value === 'number' ? value : (value ?? 0))
}

async function handleImportFromDetail(): Promise<void> {
  try {
    await ElMessageBox.confirm(
      '将按借款类型聚合 L3-2 明细行的期初/期末余额及一年内到期带入审定表，覆盖对应分类行数值。是否继续？',
      '从明细带入',
      { confirmButtonText: '带入', cancelButtonText: '取消', type: 'warning' },
    )
    const count = importFromDetail()
    if (count > 0) ElMessage.success(`已从明细带入 ${count} 个分类`)
    else ElMessage.info('明细表暂无数据')
  } catch { /* 取消 */ }
}

const isSubmitting = ref(false)
async function handleSubmit(): Promise<void> {
  isSubmitting.value = true
  try {
    await submitAdjudication()
    ElMessage.success('期末审定数已回写至试算平衡表（科目 2501）')
  } catch {
    ElMessage.error('回写失败，请稍后重试')
  } finally {
    isSubmitting.value = false
  }
}

const aiLoading = ref<string>('')
async function handleAi(field: 'change' | 'conclusion'): Promise<void> {
  aiLoading.value = field
  try {
    const httpMod = (await import('@/utils/http')).default
    const sectionMap: Record<string, string> = {
      change: 'l3-adjudication-change-note',
      conclusion: 'l3-adjudication-conclusion',
    }
    const promptMap: Record<string, string> = {
      change: '请根据长期借款期初/期末审定数及变动情况，撰写本期增减主要原因说明',
      conclusion: '请根据长期借款审定情况，撰写审计结论',
    }
    const res = await httpMod.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: sectionMap[field],
      prompt: promptMap[field],
      context: {
        期末审定合计: String(totalRow.value.endAudited),
        期初审定合计: String(totalRow.value.beginAudited),
        本期变动额: String(totalRow.value.auditedChange),
        本期变动率: `${(totalRow.value.auditedRate * 100).toFixed(2)}%`,
        期末披露审定合计: String(totalRow.value.endDisclosed),
      },
    })
    const content = res.data?.data?.content || res.data?.content
    if (content) {
      updateNote(field === 'change' ? 'note-change' : 'conclusion', content)
      ElMessage.success('AI建议已生成')
    } else {
      ElMessage.info('AI辅助暂不可用')
    }
  } catch {
    ElMessage.info('AI辅助暂不可用')
  } finally {
    aiLoading.value = ''
  }
}

function handleReview(): void {
  openReviewDialog('L3-1 长期借款审定表')
}

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtRate(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return `${(val * 100).toFixed(2)}%`
}
</script>

<style scoped>
.l3-tab-adjudication {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.adj-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.adj-header-left { display: flex; align-items: center; gap: 12px; }
.adj-header-right { display: flex; align-items: center; gap: 8px; }

.adj-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

.audit-objective { margin-bottom: 14px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-list { padding-left: 18px; line-height: 1.55; font-size: 12px; margin: 4px 0 0; }

.methodology-context {
  border-left: 4px solid #f59e0b;
  background: #fffbeb;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 14px;
  font-size: var(--wp-font-size, 13px);
  color: #78350f;
  line-height: 1.6;
}
.methodology-text strong { color: #b45309; }

.cross-check-section {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
  padding: 8px 12px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
}
.cross-check-label { color: #606266; }
.cross-check-match { color: #67c23a; font-weight: 600; }
.cross-check-diff { color: #f56c6c; font-weight: 600; }

.adj-table-card { margin-bottom: 16px; }

.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; padding-bottom: 1px; }
.formula-cell { border-bottom: 1px dashed #909399; padding-bottom: 1px; display: inline-block; color: #606266; }
.warn-change { color: #e6a23c; font-weight: 600; }
.row-bold { font-weight: 700; }

:deep(.total-row) { background-color: #f0f9eb !important; font-weight: 700; }
:deep(.current-portion-col) { background-color: #ecf5ff !important; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.el-table th .cell) { font-size: var(--wp-font-size, 13px); font-weight: 600; }

.adj-footer { display: flex; align-items: center; gap: 12px; margin: 16px 0; }
.footer-hint { font-size: 12px; color: #909399; }

.note-card { margin-bottom: 16px; }
.note-card-title { font-weight: 600; font-size: 14px; color: #303133; }
.note-field { margin-bottom: 14px; }
.note-label { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 6px; color: #606266; line-height: 1.5; }
.conclusion-header { display: flex; align-items: center; justify-content: space-between; }

.l3-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}
.l3-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; margin-bottom: 8px; }
.l3-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
