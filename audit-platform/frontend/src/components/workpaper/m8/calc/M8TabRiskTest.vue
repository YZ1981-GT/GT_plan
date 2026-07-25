<template>
  <div class="m8-tab-risk-test">
    <!-- ═══ 标题 + DualMode + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M8-4 一般风险准备计提测试表</h3>
        <el-tag type="success" effect="dark" size="small" class="equity-badge">
          权益类·贷方余额·4104
        </el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" :loading="aiLoading === 'risk-test'" @click="handleAI('risk-test')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>按风险资产期末余额1.5%计提（财金〔2012〕20号）。</strong>
        金融企业应当于每年年度终了根据承担风险和损失的资产余额计提一般准备，
        一般准备余额原则上不得低于风险资产期末余额的1.5%。
        应计金额G = 风险资产期末余额E × 计提比例F；差异H = 本期计提B − 应计金额G。
        差异为正=超额计提（安全），差异为负=计提不足（风险！红色高亮）。
      </div>
    </div>

    <!-- ═══ 11列计提测试表 ═══ -->
    <el-table
      :data="displayRows"
      border
      size="small"
      style="width: 100%"
      :row-class-name="getRowClassName"
      :header-cell-style="{ fontSize: '13px', background: '#fafafa' }"
    >
      <!-- A列: 项目 -->
      <el-table-column prop="itemName" label="项目" min-width="140" fixed>
        <template #default="{ row, $index }">
          <template v-if="row._rowType === 'total'">
            <span class="total-row-label">{{ row.itemName }}</span>
          </template>
          <template v-else-if="!isReadonly">
            <el-input
              :model-value="row.itemName"
              size="small"
              placeholder="风险资产项目"
              @change="(val: string) => handleUpdate($index, 'itemName', val)"
            />
          </template>
          <template v-else>{{ row.itemName || '—' }}</template>
        </template>
      </el-table-column>

      <!-- B列: 本期增加额-计提 -->
      <el-table-column label="本期增加额-计提" width="120" align="right">
        <template #default="{ row, $index }">
          <template v-if="isDataRow(row) && !isReadonly">
            <el-input-number
              :model-value="row.currentProvision"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => handleUpdate($index, 'currentProvision', val ?? 0)"
            />
          </template>
          <span v-else>{{ fmtAmount(row.currentProvision) }}</span>
        </template>
      </el-table-column>

      <!-- C列: 本期增加额-其它 -->
      <el-table-column label="本期增加额-其它" width="120" align="right">
        <template #default="{ row, $index }">
          <template v-if="isDataRow(row) && !isReadonly">
            <el-input-number
              :model-value="row.other"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => handleUpdate($index, 'other', val ?? 0)"
            />
          </template>
          <span v-else>{{ fmtAmount(row.other) }}</span>
        </template>
      </el-table-column>

      <!-- D列: 提取-标准 -->
      <el-table-column label="提取标准" width="160">
        <template #default="{ row, $index }">
          <template v-if="isDataRow(row) && !isReadonly">
            <el-input
              :model-value="row.standard"
              size="small"
              placeholder="如：不低于风险资产1.5%"
              @change="(val: string) => handleUpdate($index, 'standard', val)"
            />
          </template>
          <template v-else>{{ row.standard || '—' }}</template>
        </template>
      </el-table-column>

      <!-- E列: 提取-基数（风险资产期末余额） -->
      <el-table-column label="风险资产期末余额" width="150" align="right">
        <template #default="{ row, $index }">
          <template v-if="isDataRow(row) && !isReadonly">
            <el-input-number
              :model-value="row.riskAssetBalance"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => handleUpdate($index, 'riskAssetBalance', val ?? 0)"
            />
          </template>
          <span v-else>{{ fmtAmount(row.riskAssetBalance) }}</span>
        </template>
      </el-table-column>

      <!-- F列: 提取-比例（默认1.5%，可编辑） -->
      <el-table-column label="比例(注)" width="90" align="right">
        <template #header>
          <el-tooltip content="计提比例（默认1.5%=0.015），可手动编辑" placement="top">
            <span class="formula-col-header">比例(注)</span>
          </el-tooltip>
        </template>
        <template #default="{ row, $index }">
          <template v-if="isDataRow(row) && !isReadonly">
            <el-input-number
              :model-value="row.rate * 100"
              :controls="false"
              :precision="2"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => handleUpdate($index, 'rate', (val ?? 1.5) / 100)"
            />
          </template>
          <span v-else>{{ (row.rate * 100).toFixed(2) }}%</span>
        </template>
      </el-table-column>

      <!-- G列: 应计金额（公式=E×F） -->
      <el-table-column width="130" align="right">
        <template #header>
          <el-tooltip content="应计金额 G = 风险资产期末余额E × 计提比例F" placement="top">
            <span class="formula-col-header">应计金额</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-value">{{ fmtAmount(row.estimatedAmount) }}</span>
        </template>
      </el-table-column>

      <!-- H列: 差异（公式=B-G） -->
      <el-table-column width="130" align="right">
        <template #header>
          <el-tooltip content="差异 H = 本期计提B − 应计金额G。正=超额(安全)，负=不足(风险!)" placement="top">
            <span class="formula-col-header">差异</span>
          </el-tooltip>
        </template>
        <template #default="{ row, $index }">
          <span :class="getDiffClass(row, $index)">{{ fmtAmount(row.diff) }}</span>
        </template>
      </el-table-column>

      <!-- I列: 差异原因 -->
      <el-table-column label="差异原因" min-width="140">
        <template #default="{ row, $index }">
          <template v-if="isDataRow(row) && !isReadonly">
            <el-input
              :model-value="row.diffReason"
              size="small"
              placeholder="差异说明..."
              @change="(val: string) => handleUpdate($index, 'diffReason', val)"
            />
          </template>
          <template v-else>{{ row.diffReason || '—' }}</template>
        </template>
      </el-table-column>

      <!-- J列: 相关依据索引号 -->
      <el-table-column label="相关依据索引号" width="120">
        <template #default="{ row, $index }">
          <template v-if="isDataRow(row) && !isReadonly">
            <el-input
              :model-value="row.basisIndex"
              size="small"
              placeholder="索引号"
              @change="(val: string) => handleUpdate($index, 'basisIndex', val)"
            />
          </template>
          <template v-else>{{ row.basisIndex || '—' }}</template>
        </template>
      </el-table-column>

      <!-- K列: 相关数据来源索引号 -->
      <el-table-column label="数据来源索引号" width="120">
        <template #default="{ row, $index }">
          <template v-if="isDataRow(row) && !isReadonly">
            <el-input
              :model-value="row.sourceIndex"
              size="small"
              placeholder="来源索引"
              @change="(val: string) => handleUpdate($index, 'sourceIndex', val)"
            />
          </template>
          <template v-else>{{ row.sourceIndex || '—' }}</template>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 计提充足性结论 ═══ -->
    <div class="provision-footer">
      <el-tag type="primary" size="small" effect="dark">
        合计本期计提: {{ fmtAmount(riskTest.totalRow.value.currentProvision) }}
      </el-tag>
      <el-tag type="info" size="small" effect="plain">
        合计应计金额: {{ fmtAmount(riskTest.totalRow.value.estimatedAmount) }}
      </el-tag>
      <el-tag
        :type="riskTest.provisionAdequacy.value.isAdequate ? 'success' : 'danger'"
        size="small"
        :effect="riskTest.provisionAdequacy.value.isAdequate ? 'plain' : 'dark'"
      >
        {{ riskTest.provisionAdequacy.value.isAdequate ? '计提充足 ✓' : '计提不足 ✗' }}
        （差异: {{ fmtAmount(riskTest.totalRow.value.diff) }}）
      </el-tag>
    </div>

    <!-- ═══ 计提不足警告 ═══ -->
    <el-alert
      v-if="riskTest.insufficientRows.value.length > 0"
      type="error"
      :closable="false"
      show-icon
      class="insufficient-alert"
    >
      <template #title>
        计提不足项目（{{ riskTest.insufficientRows.value.length }}项）需关注
      </template>
      <template #default>
        {{ riskTest.provisionAdequacy.value.conclusion }}
      </template>
    </el-alert>

    <!-- ═══ 编制提示（折叠底部） ═══ -->
    <details class="m8-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>法规依据</strong>：《金融企业准备金计提管理办法》（财金〔2012〕20号）第五条</li>
        <li><strong>计提标准</strong>：一般准备余额原则上不得低于风险资产期末余额的1.5%</li>
        <li><strong>应计金额</strong>：G = 风险资产期末余额(E) × 计提比例(F)</li>
        <li><strong>差异</strong>：H = 本期计提(B) − 应计金额(G)</li>
        <li>差异为正 = 实际计提 &gt; 应计提 = <strong>超额计提（安全）</strong></li>
        <li>差异为负 = 实际计提 &lt; 应计提 = <strong class="text-danger">计提不足（风险！红色高亮）</strong></li>
        <li>Row 19 合计行: SUM(B10:B18), SUM(C10:C18), SUM(G10:G18), SUM(H10:H18)</li>
        <li>比例列(F)默认1.5%，可根据监管要求手动调整</li>
        <li>9行数据行（rows 10-18）+ 1行合计行（row 19）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M8TabRiskTest — M8-4 一般风险准备计提测试表（13公式 + 9数据行 + 合计行）
 *
 * Spec: .kiro/specs/m8-general-risk-reserve/
 * Task: 4.4
 * Requirements: 3.3-3.7
 *
 * xlsx结构：30×11 (A:K), 29公式
 * Headers (row 8-9):
 *   A:项目 | B:本期增加额-计提 | C:本期增加额-其它 | D:提取标准
 *   E:基数(风险资产期末余额) | F:比例(注)(默认1.5%) | G:应计金额(=E×F)
 *   H:差异(=B-G) | I:差异原因 | J:相关依据索引号 | K:数据来源索引号
 *
 * 核心公式：
 *   G = E × F（应计金额 = 风险资产期末余额 × 计提比例）
 *   H = B - G（差异 = 本期计提 - 应计金额）
 *   Row 19: SUM(B10:B18), SUM(C10:C18), SUM(G10:G18), SUM(H10:H18)
 *
 * 差异方向：
 *   正=超额计提（安全）, 负=计提不足（风险！红色高亮）
 *
 * Features:
 * - 9 data rows (rows 10-18) + 1 total row (row 19)
 * - el-table with 11 columns
 * - Formula columns G and H with dashed underline + cursor:help + tooltip
 * - |差异(H)|>阈值时红色高亮（Requirement 3.6: 计提不足红色）
 * - 比例列(F)默认填1.5%但可编辑
 * - 方法论上下文 amber block: 财金〔2012〕20号
 * - Section header with AI辅助 + 复核按钮
 * - 编制提示 details折叠
 *
 * 科目：4104 一般风险准备（**贷方/权益类！金融企业专属**）
 */
import { computed, inject, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { useM8FormData } from '../../composables/useM8FormData'
import {
  useM8RiskTest,
  DEFAULT_RISK_RATE,
  M8_RISK_DEFAULT_ITEMS,
  type M8RiskTestRow,
} from '../../composables/useM8RiskTest'
import { useVersionTrail } from '../../composables/useVersionTrail'
import type { GenerateWorkpaperAiText } from '../../composables/useWorkpaperScaffold'

const props = defineProps<{ wpId: string; projectId: string; isReadonly: boolean }>()
const emit = defineEmits<{ (e: 'navigate', sheetName: string): void; (e: 'save'): void }>()

// ─── Inject复核对话 + AI ─────────────────────────────────────────────────────
const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})
const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')
const aiLoading = ref('')

// ─── Composables ─────────────────────────────────────────────────────────────
const formData = useM8FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const testRows = ref<M8RiskTestRow[]>([])
const riskTest = useM8RiskTest(formData, testRows)

// Version trail (autoSnapshot on save)
useVersionTrail({
  projectId: computed(() => props.projectId),
  workpaperId: computed(() => props.wpId),
})

// ─── Display rows: computed rows + 合计行 ────────────────────────────────────
interface DisplayRow extends M8RiskTestRow {
  _rowType?: 'data' | 'total'
}

const displayRows = computed<DisplayRow[]>(() => {
  const rows: DisplayRow[] = riskTest.computedRows.value.map(r => ({
    ...r,
    _rowType: 'data' as const,
  }))
  // 合计行 (Row 19)
  const t = riskTest.totalRow.value
  rows.push({
    key: '__total__',
    itemName: '合 计',
    currentProvision: t.currentProvision,
    other: t.other,
    standard: '',
    riskAssetBalance: 0,
    rate: 0,
    estimatedAmount: t.estimatedAmount,
    diff: t.diff,
    diffReason: '',
    basisIndex: '',
    sourceIndex: '',
    _rowType: 'total',
  })
  return rows
})

// ─── 行类型判断 ──────────────────────────────────────────────────────────────
function isDataRow(row: DisplayRow): boolean { return row._rowType === 'data' }
function getRowClassName({ row }: { row: DisplayRow; rowIndex: number }): string {
  if (row._rowType === 'total') return 'total-row'
  return ''
}

// ─── 差异高亮判断 ─────────────────────────────────────────────────────────────
function getDiffClass(row: DisplayRow, displayIndex: number): string {
  if (row._rowType === 'total') {
    // 合计行差异为负 → 红色
    return row.diff < 0 ? 'formula-value diff-insufficient' : 'formula-value'
  }
  // 数据行：差异为负=计提不足→红色高亮
  const highlight = riskTest.highlightRows.value[displayIndex]
  if (highlight?.isOverThreshold && row.diff < 0) {
    return 'formula-value diff-insufficient'
  }
  if (highlight?.isOverThreshold && row.diff > 0) {
    return 'formula-value diff-surplus'
  }
  return 'formula-value'
}

// ─── 行操作 ──────────────────────────────────────────────────────────────────
function handleUpdate(
  displayIndex: number,
  field: 'itemName' | 'currentProvision' | 'other' | 'standard' | 'riskAssetBalance' | 'rate' | 'diffReason' | 'basisIndex' | 'sourceIndex',
  value: string | number,
): void {
  const row = displayRows.value[displayIndex]
  if (!row || row._rowType !== 'data') return
  const rawIdx = testRows.value.findIndex(r => r.key === row.key)
  if (rawIdx >= 0) {
    riskTest.updateRow(rawIdx, field, value)
  }
}

// ─── 格式化 ──────────────────────────────────────────────────────────────────
function fmtAmount(val: number | undefined | null): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── AI / 复核 ───────────────────────────────────────────────────────────────
async function handleAI(section: string): Promise<void> {
  if (props.isReadonly) return
  aiLoading.value = section
  try {
    const t = riskTest.totalRow.value
    const adequacy = riskTest.provisionAdequacy.value
    const context: Record<string, string> = {
      科目: '4104 一般风险准备（权益类/贷方，金融企业专属）',
      底稿: 'M8-4 一般风险准备计提测试表',
      合计本期计提: fmtAmount(t.currentProvision),
      合计应计金额: fmtAmount(t.estimatedAmount),
      差异: fmtAmount(t.diff),
      计提充足性: adequacy.isAdequate ? '计提充足' : '计提不足',
      计提不足项目数: String(riskTest.insufficientRows.value.length),
    }
    const text = await generateAiText({ section: `m8-risktest-${section}`, context, existingContent: '' })
    if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
    ElMessageBox.alert(text, 'AI 辅助建议', { confirmButtonText: '知道了' }).catch(() => {})
  } catch { ElMessage.warning('AI 生成失败，请稍后重试') } finally { aiLoading.value = '' }
}

function handleReview(): void {
  openReviewDialog?.('M8-4-risk-test', '一般风险准备计提测试')
}

// ─── 从 checklist_responses 恢复行数据 ───────────────────────────────────────
function _restoreRows(): M8RiskTestRow[] {
  const restored: M8RiskTestRow[] = []
  for (const [key, resp] of formData.allResponses.value.entries()) {
    if (key.startsWith('M8-4-row-') && key.endsWith('-data') && resp.remark) {
      try {
        const d = JSON.parse(resp.remark)
        restored.push({
          key: d.key || `m8-risk-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          itemName: d.itemName || '',
          currentProvision: Number(d.currentProvision) || 0,
          other: Number(d.other) || 0,
          standard: d.standard || '',
          riskAssetBalance: Number(d.riskAssetBalance) || 0,
          rate: Number(d.rate) || DEFAULT_RISK_RATE,
          estimatedAmount: 0,
          diff: 0,
          diffReason: d.diffReason || '',
          basisIndex: d.basisIndex || '',
          sourceIndex: d.sourceIndex || '',
        })
      } catch { /* skip corrupt data */ }
    }
  }
  return restored
}

/** 默认9行数据行（对应xlsx rows 10-18） */
function _defaultRows(): M8RiskTestRow[] {
  return M8_RISK_DEFAULT_ITEMS.map((name, i) => ({
    key: `m8-risk-default-${i + 1}`,
    itemName: name,
    currentProvision: 0,
    other: 0,
    standard: '不低于风险资产期末余额的1.5%',
    riskAssetBalance: 0,
    rate: DEFAULT_RISK_RATE,
    estimatedAmount: 0,
    diff: 0,
    diffReason: '',
    basisIndex: '',
    sourceIndex: '',
  }))
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────
onMounted(async () => {
  await formData.loadData()

  // 恢复行数据
  const restored = _restoreRows()
  if (restored.length > 0) {
    testRows.value = restored
  } else {
    testRows.value = _defaultRows()
  }
})
</script>

<style scoped>
.m8-tab-risk-test { padding: 12px; font-size: var(--wp-font-size, 13px); }

/* ─── Header ─── */
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.equity-badge { font-weight: 600; }

/* ─── 方法论上下文（琥珀色） ─── */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 12px 16px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
}
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }

/* ─── 公式列虚线下划线 + cursor:help ─── */
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }

/* ─── 差异高亮 ─── */
.diff-insufficient { color: #f56c6c !important; font-weight: 700; }
.diff-surplus { color: #67c23a !important; font-weight: 600; }

/* ─── 行样式 ─── */
.total-row-label { font-weight: 700; color: #303133; }
.text-danger { color: #f56c6c; }

:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.total-row) { background: #ecf5ff !important; font-weight: 700; }
:deep(.total-row td) { border-top: 2px solid #409eff; }

/* ─── 计提充足性 Footer ─── */
.provision-footer {
  margin-top: 8px;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 12px 16px;
  background: #f5f7fa;
  border-radius: 6px;
}

/* ─── 计提不足告警 ─── */
.insufficient-alert { margin-bottom: 16px; }

/* ─── 编制提示折叠 ─── */
.m8-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}
.m8-details-tip summary { cursor: pointer; font-weight: 600; color: #303133; }
.m8-details-tip ul { margin: 8px 0 0; padding-left: 20px; }
.m8-details-tip li { margin-bottom: 4px; line-height: 1.5; }

/* ─── el-input-number 紧凑 ─── */
:deep(.el-input-number) { width: 100%; }
:deep(.el-input-number .el-input__inner) { text-align: right; }
</style>
