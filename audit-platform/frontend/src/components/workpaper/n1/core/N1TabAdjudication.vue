<template>
  <div class="n1-tab-adjudication">
    <!-- ═══ 双模式切换 ═══ -->
    <div class="n1-mode-bar">
      <el-segmented v-model="dualMode.mode.value" :options="dualMode.modeOptions.value" @change="dualMode.switchMode" />
    </div>

    <!-- ═══ OnlyOffice 降级模式 ═══ -->
    <template v-if="dualMode.isOnlyOffice.value">
      <GtOnlyOfficeSheet :wp-id="wpId" :project-id="projectId" sheet-name="审定表N1-1" style="height: 100%; min-height: 600px" />
    </template>

    <!-- ═══ 结构化 / 矩阵视图 ═══ -->
    <template v-else>
      <!-- ═══ 蓝色渐变引导区（多步骤引导） ═══ -->
      <div class="n1-guidance-banner">
        <div class="guidance-grid">
          <div class="guidance-step">
            <span class="step-num">①</span>
            <span class="step-text">录入各暂时性差异项目期初/期末金额</span>
          </div>
          <div class="guidance-step">
            <span class="step-num">②</span>
            <span class="step-text">填入AJE/RJE调整，公式自动计算审定数</span>
          </div>
          <div class="guidance-step">
            <span class="step-num">③</span>
            <span class="step-text">核验N1-2/N1-4交叉验证一致</span>
          </div>
          <div class="guidance-step">
            <span class="step-num">④</span>
            <span class="step-text">确认后回写试算表(1811期末余额)</span>
          </div>
        </div>
      </div>

      <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
      <div class="n1-methodology-ctx">
        <p><strong>递延所得税资产(1811)</strong>：可抵扣暂时性差异×适用税率。资产账面价值＜计税基础，或负债账面价值＞计税基础时产生可抵扣暂时性差异，确认递延所得税资产。</p>
        <p>确认前提：预期未来有足够应纳税所得额用以利用可抵扣暂时性差异/可弥补亏损。</p>
      </div>

      <!-- ═══ 资产类科目公式提示 ═══ -->
      <div class="n1-asset-formula-badge">
        <el-icon><WarningFilled /></el-icon>
        <span>⚠️ 资产类借方科目1811：期末余额 = 期初余额 + 本期借方（确认）− 本期贷方（转回）</span>
      </div>

      <!-- ═══ 审定表 section ═══ -->
      <el-card shadow="never" class="n1-section-card">
        <template #header>
          <div class="section-header">
            <div class="section-title-group">
              <span class="section-title">递延所得税资产审定表 N1-1</span>
              <el-tag type="success" size="small" class="asset-tag">资产类·借方</el-tag>
            </div>
            <div class="section-actions">
              <el-button size="small" @click="handleAI('adjudication')">
                <el-icon><MagicStick /></el-icon> AI辅助
              </el-button>
              <el-button size="small" @click="openReview?.('N1-1-审定表')">
                <el-icon><ChatDotSquare /></el-icon> 复核
              </el-button>
            </div>
          </div>
        </template>

        <el-table
          :data="adjudication.rows.value"
          border
          size="small"
          show-summary
          :summary-method="getSummaries"
          style="width: 100%"
          :row-class-name="getRowClassName"
          highlight-current-row
          class="adjudication-table"
        >
          <el-table-column prop="category" label="暂时性差异项目" min-width="140" fixed>
            <template #default="{ row }">
              <span class="category-cell">{{ row.category }}</span>
            </template>
          </el-table-column>

          <!-- 期初部分 -->
          <el-table-column label="期初" align="center">
            <el-table-column prop="beginUnadjusted" label="未审数" min-width="100" align="right">
              <template #default="{ row, $index }">
                <el-input-number v-if="!isReadonly" :model-value="row.beginUnadjusted" size="small" :controls="false" :precision="2" class="cell-input" @change="(v: number) => adjudication.updateRow($index, 'beginUnadjusted', v ?? 0)" />
                <span v-else :class="['cell-value', { negative: row.beginUnadjusted < 0 }]">{{ fmtAmt(row.beginUnadjusted) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="beginAje" label="AJE" min-width="90" align="right">
              <template #default="{ row, $index }">
                <el-input-number v-if="!isReadonly" :model-value="row.beginAje" size="small" :controls="false" :precision="2" class="cell-input" @change="(v: number) => adjudication.updateRow($index, 'beginAje', v ?? 0)" />
                <span v-else :class="['cell-value', { negative: row.beginAje < 0 }]">{{ fmtAmt(row.beginAje) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="beginRje" label="RJE" min-width="90" align="right">
              <template #default="{ row, $index }">
                <el-input-number v-if="!isReadonly" :model-value="row.beginRje" size="small" :controls="false" :precision="2" class="cell-input" @change="(v: number) => adjudication.updateRow($index, 'beginRje', v ?? 0)" />
                <span v-else :class="['cell-value', { negative: row.beginRje < 0 }]">{{ fmtAmt(row.beginRje) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="beginAudited" label="审定数" min-width="110" align="right">
              <template #header>
                <el-tooltip content="审定数 = 未审数 + AJE + RJE" placement="top">
                  <span class="formula-col">审定数</span>
                </el-tooltip>
              </template>
              <template #default="{ row }">
                <el-tooltip content="期初审定数 = 期初未审 + 期初AJE + 期初RJE" placement="top">
                  <span class="formula-value">{{ fmtAmt(row.beginAudited) }}</span>
                </el-tooltip>
              </template>
            </el-table-column>
          </el-table-column>

          <!-- 期末部分 -->
          <el-table-column label="期末" align="center">
            <el-table-column prop="endUnadjusted" label="未审数" min-width="100" align="right">
              <template #default="{ row, $index }">
                <el-input-number v-if="!isReadonly" :model-value="row.endUnadjusted" size="small" :controls="false" :precision="2" class="cell-input" @change="(v: number) => adjudication.updateRow($index, 'endUnadjusted', v ?? 0)" />
                <span v-else :class="['cell-value', { negative: row.endUnadjusted < 0 }]">{{ fmtAmt(row.endUnadjusted) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="endAje" label="AJE" min-width="90" align="right">
              <template #default="{ row, $index }">
                <el-input-number v-if="!isReadonly" :model-value="row.endAje" size="small" :controls="false" :precision="2" class="cell-input" @change="(v: number) => adjudication.updateRow($index, 'endAje', v ?? 0)" />
                <span v-else :class="['cell-value', { negative: row.endAje < 0 }]">{{ fmtAmt(row.endAje) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="endRje" label="RJE" min-width="90" align="right">
              <template #default="{ row, $index }">
                <el-input-number v-if="!isReadonly" :model-value="row.endRje" size="small" :controls="false" :precision="2" class="cell-input" @change="(v: number) => adjudication.updateRow($index, 'endRje', v ?? 0)" />
                <span v-else :class="['cell-value', { negative: row.endRje < 0 }]">{{ fmtAmt(row.endRje) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="endAudited" label="审定数" min-width="110" align="right">
              <template #header>
                <el-tooltip content="审定数 = 未审数 + AJE + RJE" placement="top">
                  <span class="formula-col">审定数</span>
                </el-tooltip>
              </template>
              <template #default="{ row }">
                <el-tooltip content="期末审定数 = 期末未审 + 期末AJE + 期末RJE" placement="top">
                  <span class="formula-value">{{ fmtAmt(row.endAudited) }}</span>
                </el-tooltip>
              </template>
            </el-table-column>
          </el-table-column>

          <!-- 比较部分 -->
          <el-table-column label="比较" align="center">
            <el-table-column prop="changeAudited" label="变动额" min-width="110" align="right">
              <template #header>
                <el-tooltip content="变动额 = 期末审定数 − 期初审定数" placement="top">
                  <span class="formula-col">变动额</span>
                </el-tooltip>
              </template>
              <template #default="{ row }">
                <el-tooltip content="变动额 = 期末审定数 − 期初审定数" placement="top">
                  <span :class="['formula-value', { negative: row.changeAudited < 0 }]">{{ fmtAmt(row.changeAudited) }}</span>
                </el-tooltip>
              </template>
            </el-table-column>
            <el-table-column prop="changeRateAudited" label="变动率" min-width="80" align="right">
              <template #header>
                <el-tooltip content="变动率 = 变动额 ÷ 期初审定数" placement="top">
                  <span class="formula-col">变动率</span>
                </el-tooltip>
              </template>
              <template #default="{ row }">
                <el-tooltip content="变动率 = 变动额 ÷ 期初审定数" placement="top">
                  <span :class="['formula-value', { negative: row.changeRateAudited < 0 }]">{{ fmtPercent(row.changeRateAudited) }}</span>
                </el-tooltip>
              </template>
            </el-table-column>
          </el-table-column>

          <!-- 原因分析 -->
          <el-table-column prop="reason" label="原因分析" min-width="160">
            <template #header>
              <div class="reason-header">
                <span>原因分析</span>
                <el-button size="small" link type="primary" @click="handleAI('reason')">
                  <el-icon><MagicStick /></el-icon>
                </el-button>
              </div>
            </template>
            <template #default="{ row, $index }">
              <el-input v-if="!isReadonly" v-model="row.reason" size="small" placeholder="变动原因..." @change="adjudication.updateRow($index, 'reason', row.reason)" />
              <span v-else class="cell-value">{{ row.reason || '—' }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- ═══ 交叉验证区 ═══ -->
      <div class="n1-cross-validation">
        <div class="cv-title">交叉验证</div>
        <div class="cv-indicators">
          <!-- N1-1 vs N1-2明细 -->
          <div class="cv-item" :class="crossSheet.adjudicationVsDetail.value.isMatch ? 'cv-match' : 'cv-diff'">
            <span class="cv-label">N1-1审定表 vs N1-2明细表</span>
            <span v-if="crossSheet.adjudicationVsDetail.value.isMatch" class="cv-badge cv-badge-ok">✓ 一致</span>
            <span v-else class="cv-badge cv-badge-err">⚠ 差异 {{ fmtAmt(crossSheet.adjudicationVsDetail.value.diff) }}</span>
            <GtIndexChip value="N1-2" :context-project-id="projectId" />
          </div>
          <!-- N1-1 vs N1-4测算 -->
          <div class="cv-item" :class="crossSheet.adjudicationVsCalcTable.value.isMatch ? 'cv-match' : 'cv-diff'">
            <span class="cv-label">N1-1审定确认额 vs N1-4测算结果</span>
            <span v-if="crossSheet.adjudicationVsCalcTable.value.isMatch" class="cv-badge cv-badge-ok">✓ 一致</span>
            <span v-else class="cv-badge cv-badge-err">⚠ 差异 {{ fmtAmt(crossSheet.adjudicationVsCalcTable.value.diff) }}</span>
            <GtIndexChip value="N1-4" :context-project-id="projectId" />
          </div>
        </div>
      </div>

      <!-- ═══ N3对应关系提示（同源差异分列展示） ═══ -->
      <div class="n3-correspondence-section">
        <div class="n3-title">
          <span>N1递延所得税资产 ↔ N3递延所得税负债 对应关系</span>
          <GtIndexChip value="N1-4" :context-project-id="projectId" />
          <GtIndexChip value="N3-1" :context-project-id="projectId" />
          <GtIndexChip value="N3-2" :context-project-id="projectId" />
        </div>
        <div class="n3-details">
          <div class="n3-item">
            <span class="n3-label">N1递延税资产（可抵扣暂时性差异×税率）：</span>
            <span class="n3-value">{{ fmtAmt(crossSheet.n1ToN3Correspondence.value.assetPart) }}</span>
          </div>
          <div class="n3-item">
            <span class="n3-label">N3递延税负债（应纳税暂时性差异×税率）：</span>
            <span class="n3-value">{{ fmtAmt(crossSheet.n1ToN3Correspondence.value.liabilityPart) }}</span>
          </div>
          <div class="n3-item">
            <span class="n3-label">本期变动额（供N5核对递延所得税费用）：</span>
            <span :class="['n3-value', { negative: crossSheet.deferredTaxChange.value.change < 0 }]">
              {{ fmtAmt(crossSheet.deferredTaxChange.value.change) }}
            </span>
            <GtIndexChip value="N5-8" :context-project-id="projectId" />
          </div>
        </div>
      </div>

      <!-- ═══ TB回写 + N5联动状态 ═══ -->
      <div class="n1-action-bar">
        <el-button
          type="primary"
          size="small"
          :disabled="isReadonly"
          :loading="writebackLoading"
          @click="handleWritebackTB"
        >
          回写审定数 → TB(1811期末余额)
        </el-button>
        <div class="n5-linkage-indicator">
          <span class="n5-label">N5递延税费用联动：</span>
          <span v-if="crossSheet.deferredTaxChange.value.change !== 0" class="n5-badge n5-badge-ok">
            ✓ 变动 {{ fmtAmt(crossSheet.deferredTaxChange.value.change) }}
          </span>
          <span v-else class="n5-badge n5-badge-na">— 无变动</span>
          <GtIndexChip value="N5-8" :context-project-id="projectId" />
        </div>
      </div>

      <!-- ═══ 审计说明+结论 ═══ -->
      <el-card shadow="never" class="n1-section-card">
        <template #header>
          <div class="section-header">
            <span class="section-title">审计说明与结论</span>
            <div class="section-actions">
              <el-button size="small" @click="handleAI('conclusion')">
                <el-icon><MagicStick /></el-icon> AI辅助
              </el-button>
              <el-button size="small" @click="openReview?.('N1-1-结论')">
                <el-icon><ChatDotSquare /></el-icon> 复核
              </el-button>
            </div>
          </div>
        </template>
        <div class="n1-conclusion-area">
          <div class="field-group">
            <label class="field-label">审计说明</label>
            <el-input
              v-model="adjudication.auditNotes.value"
              type="textarea"
              :autosize="{ minRows: 3, maxRows: 8 }"
              :disabled="isReadonly"
              placeholder="说明递延所得税资产各暂时性差异项目变动原因及审计关注要点..."
              @change="handleNotesSave"
            />
          </div>
          <div class="field-group">
            <label class="field-label">审计结论</label>
            <el-input
              v-model="adjudication.auditConclusion.value"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 5 }"
              :disabled="isReadonly"
              placeholder="经审计，递延所得税资产各暂时性差异项目确认合理..."
              @change="handleConclusionSave"
            />
          </div>
        </div>
      </el-card>

      <!-- ═══ 编制提示（折叠底部） ═══ -->
      <details class="n1-details-tip">
        <summary>编制提示</summary>
        <ul>
          <li>递延所得税资产（1811）为<strong>资产类借方科目</strong>：期末 = 期初 + 借方（确认）− 贷方（转回）</li>
          <li>审定数 = 未审数 + AJE调整 + RJE重分类</li>
          <li>可抵扣暂时性差异 = 计税基础 − 账面价值（资产项：账面＜计税基础）</li>
          <li>递延所得税资产 = 可抵扣暂时性差异 × 适用税率</li>
          <li>确认前提：预期未来有足够应纳税所得额利用可抵扣差异/可弥补亏损</li>
          <li>N1-2明细表各项目期末递延税资产合计应与本表审定合计一致</li>
          <li>N1-4测算表递延税资产合计应与本表审定确认额一致</li>
          <li>本期变动额（期末−期初）供N5递延所得税费用核对</li>
          <li>"回写审定数"将合计审定数回写至试算表（科目1811期末余额）</li>
          <li>N1-4测算表同源产出递延税资产（归N1）和递延税负债（归N3），不能抵销的分列</li>
        </ul>
      </details>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * N1TabAdjudication — N1-1 递延所得税资产审定表
 *
 * Spec: .kiro/specs/n1-deferred-tax-assets/
 * Task: 4.2
 * Requirements: 2.1-2.9
 *
 * 核心职责：
 * - 9大类暂时性差异项目行 + 合计行，78公式覆盖
 * - 资产类期末余额 = 期初 + 借方 − 贷方（1811借方科目）
 * - 审定数 = 未审 + AJE + RJE（虚线下划线 + cursor:help + tooltip来源）
 * - 与N1-2明细表交叉验证
 * - 与N1-4测算表结果交叉验证（审定确认额=测算额）
 * - N3递延所得税负债对应关系提示（GtIndexChip跳转N1-4/N3-2）
 * - TB回写(1811期末余额) + 发布'substantive:adjudicated'
 * - N5递延税费用联动（本期变动额）
 * - 审计说明+结论+复核入口
 *
 * 科目：1811 递延所得税资产（**借方/资产类**！期末余额=期初+借-贷）
 */
import { ref, inject, onMounted, toRef } from 'vue'
import { ElMessage } from 'element-plus'
import { WarningFilled, MagicStick, ChatDotSquare } from '@element-plus/icons-vue'
// @ts-ignore
import GtIndexChip from '../../GtIndexChip.vue'
// @ts-ignore
import GtOnlyOfficeSheet from '../../GtOnlyOfficeSheet.vue'
import { useN1FormData } from '../../composables/useN1FormData'
import { useN1Adjudication } from '../../composables/useN1Adjudication'
import { useN1CrossSheet } from '../../composables/useN1CrossSheet'
import { useN1DualMode } from '../../composables/useN1DualMode'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

// ─── Inject 复核对话 ─────────────────────────────────────────────────────────

const openReview = inject<(section: string) => void>('openReviewDialog', undefined)

// ─── Composables ─────────────────────────────────────────────────────────────

const wpIdRef = toRef(props, 'wpId')
const projectIdRef = toRef(props, 'projectId')

const dualMode = useN1DualMode({ wpId: wpIdRef })

const formData = useN1FormData({ wpId: wpIdRef, projectId: projectIdRef })

const crossSheet = useN1CrossSheet(formData.allResponses)

const adjudication = useN1Adjudication({
  wpId: wpIdRef,
  projectId: projectIdRef,
  allResponses: formData.allResponses,
  formData,
  crossSheet,
})

// ─── State ───────────────────────────────────────────────────────────────────

const writebackLoading = ref(false)

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => formData.loadData())

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmtAmt(val: number | undefined): string {
  if (val == null || isNaN(val) || val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(val: number | undefined): string {
  if (val == null || isNaN(val) || val === 0) return '—'
  return (val * 100).toFixed(2) + '%'
}

function getRowClassName({ row }: { row: any }): string {
  if (row.category === '其他') return 'other-row'
  return ''
}

// ─── 合计行 ──────────────────────────────────────────────────────────────────

function getSummaries({ columns }: any) {
  const sums: string[] = []
  const t = adjudication.totals.value
  columns.forEach((col: any, i: number) => {
    if (i === 0) { sums[i] = '合计'; return }
    const map: Record<string, number> = {
      beginUnadjusted: t.beginUnadjusted,
      beginAje: t.beginAje,
      beginRje: t.beginRje,
      beginAudited: t.beginAudited,
      endUnadjusted: t.endUnadjusted,
      endAje: t.endAje,
      endRje: t.endRje,
      endAudited: t.endAudited,
      changeAudited: t.changeAudited,
    }
    const prop = col.property
    sums[i] = prop && map[prop] !== undefined ? fmtAmt(map[prop]) : ''
  })
  return sums
}

// ─── TB回写 ──────────────────────────────────────────────────────────────────

async function handleWritebackTB() {
  writebackLoading.value = true
  try {
    const auditedEndTotal = adjudication.totals.value.endAudited
    await formData.writebackTB(auditedEndTotal)
    ElMessage.success('审定数已回写试算表（科目1811期末余额）')
  } catch (err: any) {
    ElMessage.error(`回写失败：${err?.message || '未知错误'}`)
  } finally {
    writebackLoading.value = false
  }
}

// ─── 审计说明/结论保存 ───────────────────────────────────────────────────────

function handleNotesSave() {
  formData.setField('1', 'audit-notes', adjudication.auditNotes.value)
}

function handleConclusionSave() {
  formData.setField('1', 'audit-conclusion', adjudication.auditConclusion.value)
}

// ─── AI辅助 ──────────────────────────────────────────────────────────────────

function handleAI(section: string) {
  ElMessage.info(`AI辅助分析递延所得税资产${section}数据...`)
}
</script>

<style scoped>
.n1-tab-adjudication {
  padding: 12px;
  font-size: 13px;
}

/* ─── 双模式切换 ─── */
.n1-mode-bar {
  margin-bottom: 12px;
}

/* ─── 蓝色渐变引导区 ─── */
.n1-guidance-banner {
  padding: 14px 20px;
  margin-bottom: 16px;
  background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);
  border: 1px solid #90caf9;
  border-radius: 8px;
}

.guidance-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 24px;
}

.guidance-step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #1565c0;
}

.step-num {
  font-weight: 700;
  font-size: 14px;
  color: #0d47a1;
}

.step-text {
  color: #1565c0;
}

/* ─── 方法论上下文（琥珀色左边线+浅黄背景） ─── */
.n1-methodology-ctx {
  padding: 12px 16px;
  margin-bottom: 16px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-left: 4px solid #d97706;
  border-radius: 6px;
  font-size: 13px;
  color: #92400e;
  line-height: 1.7;
}

.n1-methodology-ctx p {
  margin: 0 0 4px;
}

.n1-methodology-ctx p:last-child {
  margin-bottom: 0;
}

/* ─── 资产类科目公式提示 ─── */
.n1-asset-formula-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  margin-bottom: 16px;
  background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%);
  border: 1px solid #81c784;
  border-left: 4px solid #43a047;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  color: #1b5e20;
}

.n1-asset-formula-badge .el-icon {
  font-size: 16px;
  color: #43a047;
  flex-shrink: 0;
}

/* ─── Section Header ─── */
.n1-section-card {
  margin-bottom: 16px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.section-title-group {
  display: flex;
  align-items: center;
  gap: 10px;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.asset-tag {
  font-size: 11px;
}

.section-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ─── 表格样式 ─── */
.adjudication-table {
  margin-bottom: 0;
}

:deep(.adjudication-table .el-table) {
  font-size: 13px;
}

.category-cell {
  font-weight: 500;
  color: #303133;
}

.cell-input {
  width: 100%;
}

:deep(.cell-input .el-input__inner) {
  text-align: right;
  font-size: 13px;
}

.cell-value {
  font-size: 13px;
  color: #606266;
}

.negative {
  color: #f56c6c !important;
}

/* ─── 公式列样式（虚线下划线+cursor:help） ─── */
.formula-col {
  border-bottom: 1px dashed #409eff;
  cursor: help;
  color: #409eff;
  font-weight: 600;
}

.formula-value {
  border-bottom: 1px dashed #909399;
  cursor: help;
  font-weight: 500;
  color: #303133;
  padding-bottom: 1px;
}

/* ─── 原因分析列header ─── */
.reason-header {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* ─── 行样式 ─── */
:deep(.other-row) {
  background-color: #fafafa !important;
}

:deep(.el-table) {
  font-size: 13px;
}

:deep(.el-input-number) {
  width: 100%;
}

:deep(.el-input-number .el-input__inner) {
  text-align: right;
}

/* ─── 交叉验证区 ─── */
.n1-cross-validation {
  margin-bottom: 16px;
  padding: 14px 16px;
  background: #fafbfc;
  border: 1px solid #ebeef5;
  border-radius: 8px;
}

.cv-title {
  font-size: 13px;
  font-weight: 500;
  color: #303133;
  margin-bottom: 10px;
}

.cv-indicators {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.cv-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 12px;
}

.cv-match {
  background: #e8f5e9;
  border: 1px solid #a5d6a7;
}

.cv-diff {
  background: #fef0f0;
  border: 1px solid #fab6b6;
}

.cv-label {
  color: #606266;
  font-size: 12px;
}

.cv-badge {
  font-weight: 600;
  font-size: 12px;
}

.cv-badge-ok {
  color: #43a047;
}

.cv-badge-err {
  color: #f56c6c;
}

/* ─── N3对应关系区 ─── */
.n3-correspondence-section {
  margin-bottom: 16px;
  padding: 14px 16px;
  background: #f0f9ff;
  border: 1px solid #bae6fd;
  border-radius: 8px;
}

.n3-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 500;
  color: #0369a1;
  margin-bottom: 10px;
}

.n3-details {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.n3-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.n3-label {
  color: #64748b;
}

.n3-value {
  font-weight: 500;
  color: #303133;
}

/* ─── 操作栏（TB回写+N5联动） ─── */
.n1-action-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
  padding: 10px 16px;
  background: #f5f7fa;
  border-radius: 6px;
}

.n5-linkage-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.n5-label {
  color: #606266;
}

.n5-badge {
  font-weight: 500;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
}

.n5-badge-ok {
  background: #e8f5e9;
  color: #43a047;
  border: 1px solid #a5d6a7;
}

.n5-badge-na {
  background: #f5f5f5;
  color: #9e9e9e;
  border: 1px solid #e0e0e0;
}

/* ─── 审计说明卡片 ─── */
.n1-conclusion-area {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.field-group {
  margin-bottom: 0;
}

.field-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: #606266;
  margin-bottom: 6px;
}

/* ─── 编制提示折叠 ─── */
.n1-details-tip {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 13px;
  color: #606266;
}

.n1-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.n1-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
