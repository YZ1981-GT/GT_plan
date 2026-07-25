<template>
  <div class="l2-tab-adjudication">
    <!-- ═══ 标题行 + 复核按钮 ═══ -->
    <div class="adj-header">
      <h3 class="adj-title">L2-1 应付利息审定表</h3>
      <div class="adj-header-actions">
        <el-button
          size="small"
          type="primary"
          plain
          :loading="adjPull.loading.value"
          @click="openBringInAdjustment"
        >
          <el-icon><Download /></el-icon>带入调整
        </el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          plain
          @click="handleImportFromDetail"
        >
          从L2-2明细带入
        </el-button>
        <GtReviewTrigger section-id="L2-1-adjudication" label="复核" />
      </div>
    </div>

    <!-- ═══ 审计目标（认定对应） ═══ -->
    <el-alert type="info" :closable="false" class="audit-objective" show-icon>
      <template #title>审计目标与认定</template>
      <ul class="ao-list">
        <li>A. 资产负债表中记录的应付利息是<strong>存在</strong>的，且已记录于恰当的账户（存在）</li>
        <li>B. 所有应记录的应付利息均已记录，相关披露均已包括（<strong>完整性</strong>）</li>
        <li>C. 记录的应付利息是被审计单位应当履行的偿还义务（<strong>权利和义务</strong>）</li>
        <li>D. 应付利息以恰当金额列示，计价或分摊调整已恰当记录（<strong>准确性、计价和分摊</strong>）</li>
        <li>E. 应付利息已被恰当汇总或分解且表述清楚（<strong>列报</strong>）</li>
      </ul>
    </el-alert>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>负债类贷方科目方向铁律：</strong>
        审定数 = 未审数 + 账项调整 + 重分类调整。应付利息汇聚 L1 短期借款、L3 长期借款、L4 应付债券的利息计提。
        本表按利息来源分类列示<strong>期初/期末双期</strong>，与上期审定数比较分析变动，变动率超 30% 须在原因分析说明。
      </div>
    </div>

    <!-- ═══ 勾稽校验指示器 ═══ -->
    <div class="cross-check-indicator">
      <span class="cross-check-label">审定表期末合计 vs 明细表(L2-2)：</span>
      <span :class="crossCheckClass">
        <template v-if="adjudicationVsDetail.isMatch">✓ 匹配</template>
        <template v-else>✗ 差额 {{ fmtAmount(adjudicationVsDetail.diff) }}</template>
      </span>
    </div>

    <!-- ═══ 审定表主体（期初/期末双期 + 变动分析） ═══ -->
    <el-card shadow="never" class="adj-table-card">
      <el-table
        :data="tableData"
        border
        size="small"
        style="width: 100%"
        :row-class-name="getRowClassName"
      >
        <el-table-column prop="label" label="项目" min-width="200" fixed>
          <template #default="{ row }">
            <span :class="{ 'row-bold': row.rowKey === '__total__', 'row-indent': row.isSub }">
              {{ row.label }}
            </span>
          </template>
        </el-table-column>

        <!-- 期初数 -->
        <el-table-column label="期初数" align="center">
          <el-table-column label="未审数" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="canEdit(row)"
                :model-value="row.beginUnadjusted"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(v: number | undefined) => onCell(row, 'beginUnadjusted', v)"
              />
              <span v-else>{{ fmtAmount(row.beginUnadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账项调整" min-width="105" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="canEdit(row)"
                :model-value="row.beginAje"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(v: number | undefined) => onCell(row, 'beginAje', v)"
              />
              <span v-else>{{ fmtAmount(row.beginAje) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="重分类调整" min-width="105" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="canEdit(row)"
                :model-value="row.beginRje"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(v: number | undefined) => onCell(row, 'beginRje', v)"
              />
              <span v-else>{{ fmtAmount(row.beginRje) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定数" min-width="115" align="right">
            <template #header>
              <el-tooltip content="期初审定 = 期初未审 + 账项调整 + 重分类调整" placement="top">
                <span class="formula-col-header">审定数</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span class="formula-cell">{{ fmtAmount(row.beginAudited) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 期末数 -->
        <el-table-column label="期末数" align="center">
          <el-table-column label="未审数" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="canEdit(row)"
                :model-value="row.endUnadjusted"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(v: number | undefined) => onCell(row, 'endUnadjusted', v)"
              />
              <span v-else>{{ fmtAmount(row.endUnadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账项调整" min-width="105" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="canEdit(row)"
                :model-value="row.endAje"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(v: number | undefined) => onCell(row, 'endAje', v)"
              />
              <span v-else>{{ fmtAmount(row.endAje) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="重分类调整" min-width="105" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="canEdit(row)"
                :model-value="row.endRje"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(v: number | undefined) => onCell(row, 'endRje', v)"
              />
              <span v-else>{{ fmtAmount(row.endRje) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定数" min-width="115" align="right">
            <template #header>
              <el-tooltip content="期末审定 = 期末未审 + 账项调整 + 重分类调整" placement="top">
                <span class="formula-col-header">审定数</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span class="formula-cell">{{ fmtAmount(row.endAudited) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 变动分析 -->
        <el-table-column label="本期审定数与期初审定数比较" align="center">
          <el-table-column label="变动额" min-width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" :class="{ 'warn-change': isBigChange(row) }">
                {{ fmtAmount(row.auditedChange) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="变动率" min-width="90" align="right">
            <template #default="{ row }">
              <span :class="{ 'warn-change': isBigChange(row) }">{{ fmtRate(row.auditedRate) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 原因分析 -->
        <el-table-column label="原因分析" min-width="180">
          <template #default="{ row }">
            <el-input
              v-if="canEdit(row)"
              :model-value="row.reason"
              size="small"
              placeholder="变动率超30%须说明"
              @input="(v: string) => onCell(row, 'reason', v)"
            />
            <span v-else>{{ row.reason || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ TB回写按钮 ═══ -->
    <div class="adj-footer">
      <el-button
        type="primary"
        :disabled="isReadonly || isSubmitting"
        :loading="isSubmitting"
        @click="handleSubmit"
      >
        TB回写
      </el-button>
      <span class="footer-hint">回写期末审定合计至试算平衡表（科目 2231 应付利息）</span>
    </div>

    <!-- ═══ 审计说明 ═══ -->
    <el-card shadow="never" class="note-card">
      <template #header><span class="note-card-title">1、审计说明</span></template>
      <div class="note-field">
        <div class="note-label">
          <span>（1）应付利息本期较期初增减主要原因（比例超过30%的）：</span>
          <el-button v-if="!isReadonly" size="small" type="warning" plain :loading="aiLoading === 'change'" @click="handleAi('change')">🤖 AI辅助</el-button>
        </div>
        <el-input
          :model-value="noteChange"
          type="textarea"
          :autosize="{ minRows: 3 }"
          :readonly="isReadonly"
          placeholder="说明本期应付利息余额较期初变动的主要原因..."
          @input="(v: string) => updateNote('note-change', v)"
        />
      </div>
      <div class="note-field">
        <div class="note-label">
          <span>（2）欠付利息的原因说明：</span>
          <el-button v-if="!isReadonly" size="small" type="warning" plain :loading="aiLoading === 'overdue'" @click="handleAi('overdue')">🤖 AI辅助</el-button>
        </div>
        <el-input
          :model-value="noteOverdue"
          type="textarea"
          :autosize="{ minRows: 3 }"
          :readonly="isReadonly"
          placeholder="如存在逾期/欠付利息，说明原因及可收回性评估..."
          @input="(v: string) => updateNote('note-overdue', v)"
        />
      </div>
    </el-card>

    <!-- ═══ 与经审计的财务报表核对 ═══ -->
    <el-card shadow="never" class="recon-card">
      <template #header><span class="note-card-title">（3）与经审计的财务报表核对</span></template>
      <el-table :data="reconRows" border size="small" style="width: 100%" :row-class-name="reconRowClass">
        <el-table-column prop="label" label="项目" min-width="180" />
        <el-table-column label="期末数" min-width="150" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly"
              :model-value="row.end"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="(v: number | undefined) => updateRecon(row.key, 'end', v ?? 0)"
            />
            <span v-else :class="{ 'formula-cell': row.computed }">{{ fmtAmount(row.end) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初数" min-width="150" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly"
              :model-value="row.begin"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="(v: number | undefined) => updateRecon(row.key, 'begin', v ?? 0)"
            />
            <span v-else :class="{ 'formula-cell': row.computed }">{{ fmtAmount(row.begin) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <div class="recon-hint">
        差异应为 0；若不为 0 需核对应付利息/应付股利/其他应付款审定数与报表列报口径。
      </div>
    </el-card>

    <!-- ═══ 审计结论 ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="conclusion-header">
          <span class="note-card-title">2、审计结论</span>
          <el-button v-if="!isReadonly" size="small" type="warning" plain :loading="aiLoading === 'conclusion'" @click="handleAi('conclusion')">🤖 AI辅助</el-button>
        </div>
      </template>
      <el-input
        :model-value="conclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :readonly="isReadonly"
        placeholder="A、未见异常。 B、除上述重大不符事项应作为调整事项外，其余未见异常。 C、由于存在重大未调整事项（或审计范围受限），不可确认。"
        @input="(v: string) => updateNote('conclusion', v)"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>科目方向</strong>：应付利息为负债类贷方科目，审定数 = 未审数 + 账项调整 + 重分类调整</li>
        <li><strong>分类</strong>：分期付息长期借款利息 / 企业债券利息 / 短期借款应付利息 / 优先股永续债利息（工具1/工具2）/ 其他</li>
        <li><strong>双期结构</strong>：期初数、期末数各分「未审/账项调整/重分类/审定」四列，便于变动分析</li>
        <li><strong>变动分析</strong>：本期审定 vs 期初审定，变动率超 30% 须在「原因分析」逐行说明</li>
        <li><strong>数据带入</strong>：点「从L2-2明细带入」按类别聚合明细行的期初/期末余额及调整</li>
        <li><strong>TB回写</strong>：期末审定合计点回写按钮写入试算平衡表科目 2231</li>
        <li><strong>财报核对</strong>：应付利息+应付股利+其他应付款审定合计应与报表「其他应付款」列报数一致</li>
        <li><strong>带入调整</strong>：可从集中登记按科目 2231 拉取调整分录，逐笔分配到各利息来源行的期末账项/重分类调整，带入后审定数自动更新并联动附注</li>
      </ul>
    </details>

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="2231 应付利息"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * L2TabAdjudication — L2-1 应付利息审定表（源模板重建：期初/期末双期变动分析）
 *
 * - 分类行（分期付息长借利息/企业债券/短借/优先股永续债[工具1/2]/其他）+ 合计
 * - 期初数(未审/账项调整/重分类/审定) + 期末数(同) + 变动分析 + 原因分析
 * - 审计说明（增减原因/欠付利息原因）+ 审计结论 + 与经审计财报核对区
 * - 从 L2-2 明细带入（SUMIF 等价）+ TB回写(2231) + 复核圆点
 *
 * 科目：2231 应付利息（贷方/负债类）
 */
import { computed, ref, toRef, provide } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import { useL2FormData } from '../../composables/useL2FormData'
import { useL2Adjudication, type AdjudicationRow } from '../../composables/useL2Adjudication'
import { useL2CrossSheet } from '../../composables/useL2CrossSheet'
import { useWorkpaperReviewThreads } from '../../composables/useWorkpaperReviewThreads'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import { useAuditContext } from '@/composables/useAuditContext'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

// ─── 复核圆点 provide ────────────────────────────────────────────────────────
// GtReviewTrigger 依赖 provide('getThreadDot'/'getRowDot')；openReviewDialog 由 GtWpRenderer 运行时边界提供
const wpIdRef = toRef(props, 'wpId')
const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(wpIdRef)
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

// ─── FormData ────────────────────────────────────────────────────────────────
const { allResponses, loadData, saveField, debouncedSave, writebackTB } = useL2FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})
loadData()

// ─── Adjudication ────────────────────────────────────────────────────────────
const {
  rows,
  totalRow,
  totalAuditedAmount,
  noteChange,
  noteOverdue,
  conclusion,
  updateNote,
  reconRows,
  updateRecon,
  updateCell,
  importFromDetail,
  submitAdjudication,
} = useL2Adjudication({
  allResponses,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  saveField,
  debouncedSave,
  writebackTB,
})

const { adjudicationVsDetail } = useL2CrossSheet(allResponses)

// ─── 从集中登记带入调整（2231 应付利息，负债贷方；双列 endAje/endRje，排除优先股汇总/合计行） ───
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
  subjectPrefix: '2231',
  direction: 'credit',
  subjectCode: '2231',
  wpCode: 'L2',
  subjectLabel: '应付利息(2231)',
  rows: bringInRows,
  updateCell: (rowKey: string, field: any, value: number) =>
    updateCell(rowKey, field === 'rje' ? 'endRje' : 'endAje', value),
  totalAudited: () => totalRow.value.endAudited,
})

// ─── Table data（数据行 + 合计行） ────────────────────────────────────────────
const tableData = computed<AdjudicationRow[]>(() => [...rows.value, totalRow.value])

const crossCheckClass = computed(() => ({
  'cross-check-match': adjudicationVsDetail.value.isMatch,
  'cross-check-diff': !adjudicationVsDetail.value.isMatch,
}))

function canEdit(row: AdjudicationRow): boolean {
  return row.isEditable && row.rowKey !== '__total__' && !props.isReadonly
}

function getRowClassName({ row }: { row: AdjudicationRow }): string {
  if (row.rowKey === '__total__') return 'total-row'
  if (row.rowKey === 'preferred-perpetual') return 'agg-row'
  return ''
}

function isBigChange(row: AdjudicationRow): boolean {
  return Math.abs(row.auditedRate) > 0.3 && row.rowKey !== '__total__'
}

function onCell(row: AdjudicationRow, field: string, value: number | string | undefined): void {
  if (!canEdit(row)) return
  updateCell(row.rowKey, field, typeof value === 'number' ? value : (value ?? 0))
}

// ─── 从明细带入 ──────────────────────────────────────────────────────────────
async function handleImportFromDetail(): Promise<void> {
  try {
    await ElMessageBox.confirm(
      '将按类别聚合 L2-2 明细行的期初/期末余额及调整带入审定表，覆盖当前分类行的对应数值。是否继续？',
      '从明细带入',
      { confirmButtonText: '带入', cancelButtonText: '取消', type: 'warning' },
    )
    const count = importFromDetail()
    if (count > 0) ElMessage.success(`已从明细带入 ${count} 个分类`)
    else ElMessage.info('明细表暂无数据')
  } catch {
    /* 取消 */
  }
}

// ─── TB回写 ──────────────────────────────────────────────────────────────────
const isSubmitting = ref(false)
async function handleSubmit(): Promise<void> {
  isSubmitting.value = true
  try {
    await submitAdjudication()
    ElMessage.success('期末审定数已回写至试算平衡表（科目 2231）')
  } catch {
    ElMessage.error('回写失败，请稍后重试')
  } finally {
    isSubmitting.value = false
  }
}

// ─── AI辅助 ──────────────────────────────────────────────────────────────────
const aiLoading = ref<string>('')
async function handleAi(field: 'change' | 'overdue' | 'conclusion'): Promise<void> {
  aiLoading.value = field
  try {
    const http = (await import('@/utils/http')).default
    const sectionMap: Record<string, string> = {
      change: 'l2-adjudication-change-note',
      overdue: 'l2-adjudication-overdue-note',
      conclusion: 'l2-adjudication-conclusion',
    }
    const promptMap: Record<string, string> = {
      change: '请根据应付利息期初/期末审定数及变动情况，撰写本期增减主要原因说明',
      overdue: '请根据逾期/欠付利息情况，撰写欠付利息原因及可收回性评估说明',
      conclusion: '请根据应付利息审定情况，撰写审计结论',
    }
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: sectionMap[field],
      prompt: promptMap[field],
      context: {
        期末审定合计: String(totalRow.value.endAudited),
        期初审定合计: String(totalRow.value.beginAudited),
        本期变动额: String(totalRow.value.auditedChange),
        本期变动率: String((totalRow.value.auditedRate * 100).toFixed(2)) + '%',
      },
    })
    const content = res.data?.data?.content || res.data?.content
    if (content) {
      const noteKey = field === 'change' ? 'note-change' : field === 'overdue' ? 'note-overdue' : 'conclusion'
      updateNote(noteKey, content)
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

// ─── 格式化 ──────────────────────────────────────────────────────────────────
function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRate(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return `${(val * 100).toFixed(2)}%`
}

function reconRowClass({ row }: { row: { computed: boolean } }): string {
  return row.computed ? 'total-row' : ''
}
</script>

<style scoped>
.l2-tab-adjudication {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.adj-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.adj-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

.adj-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.audit-objective {
  margin-bottom: 14px;
}

.audit-objective :deep(.el-alert__content) {
  padding: 2px 0;
}

.ao-list {
  padding-left: 18px;
  line-height: 1.55;
  font-size: 12px;
  margin: 4px 0 0;
}

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

.methodology-text strong {
  color: #b45309;
}

.cross-check-indicator {
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

.cross-check-label {
  color: #606266;
}

.cross-check-match {
  color: #67c23a;
  font-weight: 600;
}

.cross-check-diff {
  color: #f56c6c;
  font-weight: 600;
}

.adj-table-card {
  margin-bottom: 16px;
}

.formula-col-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 1px;
}

.formula-cell {
  border-bottom: 1px dashed #909399;
  padding-bottom: 1px;
  display: inline-block;
  color: #606266;
}

.warn-change {
  color: #e6a23c;
  font-weight: 600;
}

.row-bold {
  font-weight: 700;
}

.row-indent {
  padding-left: 20px;
  color: #909399;
}

:deep(.total-row) {
  background-color: #f0f9eb !important;
  font-weight: 700;
}

:deep(.agg-row) {
  background-color: #fafafa !important;
  font-weight: 600;
}

:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}

:deep(.el-table th .cell) {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}

.adj-footer {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 16px 0;
}

.footer-hint {
  font-size: 12px;
  color: #909399;
}

.note-card,
.recon-card,
.conclusion-card {
  margin-bottom: 16px;
}

.note-card-title {
  font-weight: 600;
  font-size: 14px;
  color: #303133;
}

.note-field {
  margin-bottom: 14px;
}

.note-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
  color: #606266;
}

.conclusion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.recon-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
}

.l2-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.l2-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.l2-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
