<template>
  <div class="m6-tab-detail">
    <!-- ═══ 蓝色渐变引导区（利润分配流程步骤） ═══ -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step">
          <span class="step-num">①</span>
          <span class="step-text">确认期初未分配利润（含前期差错/政策变更调整）</span>
        </div>
        <div class="guide-step">
          <span class="step-num">②</span>
          <span class="step-text">确认本年净利润（利润表结转）</span>
        </div>
        <div class="guide-step">
          <span class="step-num">③</span>
          <span class="step-text">计算可供分配利润 = 调整后期初 + 本年净利润</span>
        </div>
        <div class="guide-step">
          <span class="step-num">④</span>
          <span class="step-text">扣减提取盈余公积（→M5联动核对）</span>
        </div>
        <div class="guide-step">
          <span class="step-num">⑤</span>
          <span class="step-text">扣减应付股利（→M1联动核对）</span>
        </div>
        <div class="guide-step">
          <span class="step-num">⑥</span>
          <span class="step-text">得出期末未分配利润 → 与M6-1审定表交叉验证</span>
        </div>
      </div>
    </div>

    <!-- ═══ 标题 + 导入导出 + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M6-2 利润分配结转明细表</h3>
        <el-tag type="success" effect="dark" size="small" class="equity-badge">
          权益类·利润分配结转核心
        </el-tag>
      </div>
      <div class="section-header-right">
        <el-dropdown trigger="click" @command="handleImportExport">
          <el-button size="small">
            导入导出 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item command="exportData">导出数据</el-dropdown-item>
              <el-dropdown-item command="importData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" :loading="aiLoading === 'detail'" :disabled="isReadonly" @click="handleAI('detail')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
        <el-button type="primary" size="small" :loading="isSaving" @click="handleSave">
          保存
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>利润分配结转公式链（4104，权益类贷方科目）：</strong>
        期末未分配利润 = 期初未分配利润 + 本年净利润 − 提取法定盈余公积 − 提取任意盈余公积 − 应付现金股利 − 转作股本的股利 − 其他分配。
        明细表32行×19列（含本期+上期双时段），13公式实时计算并逐行勾稽。
        与M5盈余公积计提、M1应付股利联动核对，差异红色高亮。
      </div>
    </div>

    <!-- ═══ M5/M1联动差异警告 ═══ -->
    <el-alert
      v-if="!surplusLinkageDiff.isConsistent"
      type="error"
      :closable="false"
      show-icon
      class="linkage-alert"
    >
      <template #title>
        盈余公积联动差异：M6记录 {{ fmtAmount(distributionSummary.totalSurplus) }} ≠ M5实际计提 {{ fmtAmount(surplusLinkageRef) }}（差额 {{ fmtAmount(surplusLinkageDiff.diff) }}）
      </template>
    </el-alert>
    <el-alert
      v-if="!dividendLinkageDiff.isConsistent"
      type="error"
      :closable="false"
      show-icon
      class="linkage-alert"
    >
      <template #title>
        股利联动差异：M6记录 {{ fmtAmount(distributionSummary.totalDividend) }} ≠ M1实际宣告 {{ fmtAmount(dividendLinkageRef) }}（差额 {{ fmtAmount(dividendLinkageDiff.diff) }}）
      </template>
    </el-alert>

    <!-- ═══ 区段切换（本期/上期） ═══ -->
    <el-segmented v-model="activePeriod" :options="periodOptions" size="default" class="period-switcher" />

    <!-- ═══ 动态行新增按钮 ═══ -->
    <div class="action-bar">
      <el-button v-if="!isReadonly" size="small" type="primary" plain @click="handleAddRow()">
        + 新增明细行
      </el-button>
    </div>

    <!-- ═══ 利润分配结转明细表主体 ═══ -->
    <el-table
      :data="tableRows"
      border
      size="small"
      style="width: 100%"
      :row-class-name="getRowClassName"
      class="detail-table"
    >
      <!-- 项目列 -->
      <el-table-column prop="itemName" label="项目" min-width="200" fixed>
        <template #default="{ row, $index }">
          <template v-if="row.isFormula">
            <span class="formula-row-label">{{ row.itemName }}</span>
          </template>
          <template v-else-if="!isReadonly && row.category === 'adjustment'">
            <el-input :model-value="row.itemName" size="small" placeholder="调整项目" @change="(val: string) => handleUpdate($index, 'itemName', val)" />
          </template>
          <template v-else>
            <span :class="{ 'category-label': isCategoryHeader(row) }">{{ row.itemName }}</span>
          </template>
        </template>
      </el-table-column>

      <!-- 本期列组 -->
      <template v-if="activePeriod === 'current'">
        <el-table-column label="未审-本期" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="row.isFormula">
              <el-tooltip :content="getFormulaTooltip(row)" placement="top">
                <span class="formula-value">{{ fmtAmount(row.unadjustedAmount) }}</span>
              </el-tooltip>
            </template>
            <template v-else-if="!isReadonly">
              <el-input-number :model-value="row.unadjustedAmount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'unadjustedAmount', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.unadjustedAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE-本期" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="row.isFormula"><span class="formula-value">{{ fmtAmount(row.ajeAmount) }}</span></template>
            <template v-else-if="!isReadonly">
              <el-input-number :model-value="row.ajeAmount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'ajeAmount', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.ajeAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RJE-本期" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="row.isFormula"><span class="formula-value">{{ fmtAmount(row.rjeAmount) }}</span></template>
            <template v-else-if="!isReadonly">
              <el-input-number :model-value="row.rjeAmount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'rjeAmount', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.rjeAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column width="130" align="right">
          <template #header>
            <el-tooltip content="审定=未审+AJE+RJE（公式行由结转计算）" placement="top">
              <span class="formula-col-header">审定-本期</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip :content="getFormulaTooltip(row)" placement="top" :disabled="!row.isFormula">
              <span class="formula-value">{{ fmtAmount(row.auditedAmount) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </template>

      <!-- 上期列组 -->
      <template v-if="activePeriod === 'prior'">
        <el-table-column label="未审-上期" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="row.isFormula">
              <span class="formula-value">{{ fmtAmount(row.priorUnadjusted) }}</span>
            </template>
            <template v-else-if="!isReadonly">
              <el-input-number :model-value="row.priorUnadjusted" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'priorUnadjusted', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.priorUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE-上期" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="row.isFormula"><span class="formula-value">{{ fmtAmount(row.priorAje) }}</span></template>
            <template v-else-if="!isReadonly">
              <el-input-number :model-value="row.priorAje" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'priorAje', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.priorAje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RJE-上期" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="row.isFormula"><span class="formula-value">{{ fmtAmount(row.priorRje) }}</span></template>
            <template v-else-if="!isReadonly">
              <el-input-number :model-value="row.priorRje" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'priorRje', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.priorRje) }}</span>
          </template>
        </el-table-column>
        <el-table-column width="130" align="right">
          <template #header>
            <el-tooltip content="上期审定=未审+AJE+RJE" placement="top">
              <span class="formula-col-header">审定-上期</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.priorAudited) }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- 索引号+备注（两个时段共用） -->
      <el-table-column label="索引号" width="100" align="center">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly && !row.isFormula">
            <el-input :model-value="row.refIndex" size="small" placeholder="" @change="(val: string) => handleUpdate($index, 'refIndex', val)" />
          </template>
          <span v-else>{{ row.refIndex || '' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="140">
        <template #default="{ row, $index }">
          <template v-if="!isReadonly && !row.isFormula">
            <el-input :model-value="row.remark" size="small" placeholder="" @change="(val: string) => handleUpdate($index, 'remark', val)" />
          </template>
          <span v-else>{{ row.remark || '' }}</span>
        </template>
      </el-table-column>

      <!-- 操作列（删除动态行） -->
      <el-table-column v-if="!isReadonly" label="" width="60" align="center" fixed="right">
        <template #default="{ row, $index }">
          <el-button v-if="row.category === 'adjustment'" type="danger" size="small" link @click="handleRemoveRow($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 结转汇总 + 交叉验证状态 ═══ -->
    <div class="detail-footer">
      <el-tag type="primary" size="small" effect="dark">
        期末未分配利润: {{ fmtAmount(distributionSummary.retainedEnd) }}
      </el-tag>
      <el-tag type="info" size="small" effect="plain">
        可供分配: {{ fmtAmount(distributionSummary.distributable) }}
      </el-tag>
      <el-tag type="warning" size="small" effect="plain">
        盈余公积计提: {{ fmtAmount(distributionSummary.totalSurplus) }}
      </el-tag>
      <el-tag type="warning" size="small" effect="plain">
        股利分配: {{ fmtAmount(distributionSummary.totalDividend) }}
      </el-tag>
      <el-tag :type="crossValidation.isMatch ? 'success' : 'danger'" size="small" effect="plain">
        与M6-1交叉验证: {{ crossValidation.isMatch ? '一致 ✓' : `差异 ${fmtAmount(crossValidation.diff)}` }}
      </el-tag>
    </div>

    <!-- ═══ 跨底稿联动（cross_wp_ref GtIndexChip） ═══ -->
    <div class="cross-wp-links">
      <span class="cross-wp-label">cross_wp_ref 关联底稿：</span>
      <GtIndexChip value="wp:M5" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">盈余公积计提（M6净利润→M5计提基数）</span>
      <GtIndexChip value="wp:M1" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">应付股利（M6分配股利→M1宣告）</span>
      <GtIndexChip value="wp:M6-1" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">审定表（期末交叉验证）</span>
      <GtIndexChip value="wp:A" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">本年利润（利润表结转来源）</span>
    </div>

    <!-- ═══ 审计说明（el-card包裹） ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">明细表审计说明</span>
          <el-button size="small" :loading="aiLoading === 'detailNote'" :disabled="isReadonly" @click="handleAI('detailNote')"><el-icon><MagicStick /></el-icon> AI辅助</el-button>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="请填写利润分配结转明细表审计说明..." :disabled="isReadonly" @change="saveAuditNote" />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="m6-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>未分配利润（4104）为<strong>权益类贷方科目</strong>：期末 = 期初 + 本年净利润(贷方增加) − 提取盈余公积(借方减少) − 分配股利(借方减少)</li>
        <li><strong>核心公式链</strong>：期末未分配利润 = 期初 + 净利润 − 法定盈余公积 − 任意盈余公积 − 现金股利 − 转增股本 − 其他分配</li>
        <li>前期差错更正和会计政策变更调整年初（调整后期初 = 原始期初 + 差错更正 + 政策变更）</li>
        <li>提取盈余公积须与M5实际计提一致（联动核对，差异红色高亮）</li>
        <li>分配股利须与M1实际宣告一致（联动核对，差异红色高亮）</li>
        <li>期末未分配利润须与M6-1审定表交叉验证</li>
        <li>13公式实时计算：公式行虚线下划线 + 蓝色字体 + tooltip显示公式来源</li>
        <li>支持动态行新增（先输入项目名称确认后创建）和导入导出</li>
      </ul>
    </details>

    <!-- ═══ 隐藏文件上传input ═══ -->
    <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="handleFileSelected" />
  </div>
</template>

<script setup lang="ts">
/**
 * M6TabDetail — M6-2 利润分配结转明细表（核心！）
 * Requirements: 3.1-3.6
 *
 * 32×19 结构，13公式（63 formula cells）
 * 行结构: 一、上年年末余额 | 加：会计政策变更 | 前期差错更正 | 二、本年年初余额(公式)
 *         | 三、盈余公积补亏 | 四、本期净利润 | 五、利润分配(公式合计)
 *         | 1.提取法定盈余公积 | 2.提取任意盈余公积 | 3.应付现金股利
 *         | 4.转作股本的股利 | 5.其他 | 六、所有者权益内部结转(合计) | 七、本年年末余额(公式)
 * 列结构: 项目 | 未审-本期 | AJE-本期 | RJE-本期 | 审定-本期 | 未审-上期 | AJE-上期
 *         | RJE-上期 | 审定-上期 | 索引号 | 备注
 * 公式: 利润分配结转核心公式链 13公式
 * 联动: M5盈余公积计提 + M1股利分配 + M6-1审定表交叉验证
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, Check, ArrowDown } from '@element-plus/icons-vue'
import { useM6FormData } from '../../composables/useM6FormData'
import { useM6ImportExport } from '../../composables/useM6ImportExport'
import { useM6Detail, type M6DetailRow, type M6DetailCategory } from '../../composables/useM6Detail'
import { eventBus } from '@/utils/eventBus'
import type { GenerateWorkpaperAiText } from '../../composables/useWorkpaperScaffold'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{ wpId: string; projectId: string; isReadonly: boolean }>()
const emit = defineEmits<{ (e: 'navigate', sheetName: string): void; (e: 'save'): void }>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})
const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')
const aiLoading = ref('')

// ─── Composables ─────────────────────────────────────────────────────────────
const formData = useM6FormData({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })
const importExport = useM6ImportExport({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })

const detailRows = ref<M6DetailRow[]>([])

const {
  computedRows,
  distributionSummary,
  surplusLinkageDiff,
  dividendLinkageDiff,
  setSurplusLinkage,
  setDividendLinkage,
  addRow,
  removeRow,
  updateRow,
  crossValidateWithAdjudication,
} = useM6Detail(formData, detailRows)

// ─── UI State ────────────────────────────────────────────────────────────────
const isSaving = ref(false)
const auditNote = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)
const activePeriod = ref<'current' | 'prior'>('current')

const periodOptions = [
  { label: '本期', value: 'current' },
  { label: '上期', value: 'prior' },
]

// M5/M1 联动参考值（由EventBus注入）
const surplusLinkageRef = ref(0)
const dividendLinkageRef = ref(0)

// ─── 默认行初始化（32行利润分配结转结构） ────────────────────────────────────
interface ExtendedRow extends M6DetailRow {
  priorUnadjusted: number
  priorAje: number
  priorRje: number
  priorAudited: number
}

const DEFAULT_ROWS: Array<{ itemName: string; category: M6DetailCategory; isFormula: boolean }> = [
  { itemName: '一、上年年末余额', category: 'retained-beginning', isFormula: false },
  { itemName: '加：会计政策变更', category: 'policy-change', isFormula: false },
  { itemName: '    前期差错更正', category: 'prior-error', isFormula: false },
  { itemName: '二、本年年初余额', category: 'distributable', isFormula: true },
  { itemName: '三、盈余公积补亏', category: 'adjustment', isFormula: false },
  { itemName: '四、本期净利润', category: 'net-profit', isFormula: false },
  { itemName: '五、利润分配', category: 'distributable', isFormula: true },
  { itemName: '  1.提取法定盈余公积', category: 'statutory-surplus', isFormula: false },
  { itemName: '  2.提取任意盈余公积', category: 'discretionary-surplus', isFormula: false },
  { itemName: '  3.应付现金股利', category: 'ordinary-dividend', isFormula: false },
  { itemName: '  4.转作股本的股利', category: 'preferred-dividend', isFormula: false },
  { itemName: '  5.其他', category: 'other-distribution', isFormula: false },
  { itemName: '六、所有者权益内部结转', category: 'adjustment', isFormula: true },
  { itemName: '七、本年年末余额', category: 'retained-end', isFormula: true },
]

function initDefaultRows(): M6DetailRow[] {
  return DEFAULT_ROWS.map((def, i) => ({
    key: `m6-det-default-${i}`,
    itemName: def.itemName,
    category: def.category,
    isFormula: def.isFormula,
    unadjustedAmount: 0,
    ajeAmount: 0,
    rjeAmount: 0,
    auditedAmount: 0,
    remark: '',
    refIndex: '',
    source: '',
  }))
}

// ─── 表格展示行（含上期列+公式计算） ─────────────────────────────────────────
const priorData = ref<Map<string, { unadj: number; aje: number; rje: number }>>(new Map())

const tableRows = computed<ExtendedRow[]>(() => {
  return computedRows.value.map(row => {
    const prior = priorData.value.get(row.key) || { unadj: 0, aje: 0, rje: 0 }
    const priorAudited = prior.unadj + prior.aje + prior.rje

    // 公式行审定金额由 distributionSummary 赋值
    let auditedAmount = row.auditedAmount
    if (row.isFormula) {
      auditedAmount = _getFormulaValue(row)
    }

    return {
      ...row,
      auditedAmount,
      priorUnadjusted: prior.unadj,
      priorAje: prior.aje,
      priorRje: prior.rje,
      priorAudited,
    }
  })
})

/** 公式行根据分类返回计算值 */
function _getFormulaValue(row: M6DetailRow): number {
  const s = distributionSummary.value
  switch (row.category) {
    case 'distributable':
      // 二、本年年初余额 = 上年末余额 + 会计政策变更 + 前期差错更正
      // 五、利润分配 = 盈余公积合计 + 股利合计
      if (row.itemName.includes('年初余额')) return s.retainedBeginning
      if (row.itemName.includes('利润分配')) return s.totalSurplus + s.totalDividend
      return s.distributable
    case 'retained-end':
      return s.retainedEnd
    default:
      return 0
  }
}

// ─── 行操作 ──────────────────────────────────────────────────────────────────
function handleUpdate(index: number, field: string, value: string | number): void {
  updateRow(index, field as keyof M6DetailRow, value)
}

function handleRemoveRow(index: number): void {
  removeRow(index)
}

async function handleAddRow(): Promise<void> {
  await addRow('adjustment')
}

// ─── 行分类辅助 ──────────────────────────────────────────────────────────────
function isCategoryHeader(row: M6DetailRow): boolean {
  return row.itemName.startsWith('一、') || row.itemName.startsWith('二、') ||
         row.itemName.startsWith('三、') || row.itemName.startsWith('四、') ||
         row.itemName.startsWith('五、') || row.itemName.startsWith('六、') ||
         row.itemName.startsWith('七、')
}

function getRowClassName({ row }: { row: ExtendedRow; rowIndex: number }): string {
  if (row.isFormula) return 'formula-row'
  if (isCategoryHeader(row)) return 'category-row'
  return ''
}

function getFormulaTooltip(row: M6DetailRow): string {
  if (row.itemName.includes('年初余额')) return '公式: 上年年末余额 + 会计政策变更 + 前期差错更正'
  if (row.itemName.includes('利润分配') && row.isFormula) return '公式: 提取盈余公积合计 + 股利分配合计'
  if (row.category === 'retained-end') return '公式: 期初 + 净利润 − 盈余公积 − 股利'
  if (row.itemName.includes('内部结转')) return '公式: 所有者权益内部结转合计'
  return '公式行（自动计算）'
}

// ─── 交叉验证 ────────────────────────────────────────────────────────────────
const crossValidation = computed(() => {
  const adjEndResp = formData.allResponses.value.get('M6-1-audited-end-balance')
  const adjEndBalance = Number(adjEndResp?.remark) || 0
  return crossValidateWithAdjudication(adjEndBalance)
})

// ─── 格式化 ──────────────────────────────────────────────────────────────────
function fmtAmount(val: number | undefined | null): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 保存 ────────────────────────────────────────────────────────────────────
async function handleSave() {
  isSaving.value = true
  try {
    // 保存所有行数据
    for (let i = 0; i < detailRows.value.length; i++) {
      const row = detailRows.value[i]
      formData.debouncedSave(`M6-2-row-${i + 1}-data`, {
        remark: JSON.stringify({
          key: row.key,
          itemName: row.itemName,
          category: row.category,
          isFormula: row.isFormula,
          unadjustedAmount: row.unadjustedAmount,
          ajeAmount: row.ajeAmount,
          rjeAmount: row.rjeAmount,
          remark: row.remark,
          refIndex: row.refIndex,
          source: row.source,
        }),
      })
    }
    // 保存上期数据
    for (const [key, prior] of priorData.value.entries()) {
      formData.debouncedSave(`M6-2-prior-${key}`, {
        remark: JSON.stringify(prior),
      })
    }
    // 保存结转汇总（供M6-1交叉验证读取）
    formData.debouncedSave('M6-M6-2-retained-end', {
      remark: String(distributionSummary.value.retainedEnd),
    })
    ElMessage.success('明细表已保存')
    emit('save')
  } finally { isSaving.value = false }
}

function saveAuditNote() {
  formData.debouncedSave('M6-2-auditNote', { remark: auditNote.value || null })
}

// ─── AI + 复核 ───────────────────────────────────────────────────────────────
async function handleAI(section: string) {
  if (props.isReadonly) return
  aiLoading.value = section
  try {
    const s = distributionSummary.value
    const context: Record<string, string> = {
      科目: '4104 利润分配-未分配利润 / 明细表（M6-2 利润分配结转公式链）',
      期初未分配利润: fmtAmount(s.retainedBeginning),
      可供分配利润: fmtAmount(s.distributable),
      提取盈余公积: fmtAmount(s.totalSurplus),
      股利分配: fmtAmount(s.totalDividend),
      期末未分配利润: fmtAmount(s.retainedEnd),
      'M5盈余公积联动一致': surplusLinkageDiff.value.isConsistent ? '一致' : `差异${fmtAmount(surplusLinkageDiff.value.diff)}`,
      'M1股利联动一致': dividendLinkageDiff.value.isConsistent ? '一致' : `差异${fmtAmount(dividendLinkageDiff.value.diff)}`,
      '与M6-1交叉验证': crossValidation.value.isMatch ? '一致' : `差异${fmtAmount(crossValidation.value.diff)}`,
    }
    const text = await generateAiText({ section: `m6-detail-${section}`, context, existingContent: auditNote.value })
    if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
    auditNote.value = text
    saveAuditNote()
  } catch { ElMessage.warning('AI 生成失败，请稍后重试') } finally { aiLoading.value = '' }
}
function handleReview() { openReviewDialog?.('M6-2-detail', '利润分配结转明细表') }

// ─── 导入导出 ────────────────────────────────────────────────────────────────
function handleImportExport(command: string) {
  switch (command) {
    case 'exportTemplate': importExport.exportTemplate('M6-2'); break
    case 'exportData': importExport.exportData('M6-2'); break
    case 'importData': fileInputRef.value?.click(); break
  }
}

async function handleFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const result = await importExport.importData('M6-2', file)
  if (result?.success) {
    await formData.loadData()
    _restoreRows()
  }
  input.value = ''
}

// ─── selfLoad + 数据恢复 ─────────────────────────────────────────────────────
function _restoreRows(): void {
  const restored: M6DetailRow[] = []
  for (const [key, resp] of formData.allResponses.value.entries()) {
    if (key.startsWith('M6-2-row-') && key.endsWith('-data') && resp.remark) {
      try {
        const d = JSON.parse(resp.remark)
        restored.push({
          key: d.key || `m6-det-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          itemName: d.itemName || '',
          category: d.category || 'adjustment',
          isFormula: Boolean(d.isFormula),
          unadjustedAmount: Number(d.unadjustedAmount) || 0,
          ajeAmount: Number(d.ajeAmount) || 0,
          rjeAmount: Number(d.rjeAmount) || 0,
          auditedAmount: 0,
          remark: d.remark || '',
          refIndex: d.refIndex || '',
          source: d.source || '',
        })
      } catch { /* skip malformed */ }
    }
  }
  // 恢复上期数据
  for (const [key, resp] of formData.allResponses.value.entries()) {
    if (key.startsWith('M6-2-prior-') && resp.remark) {
      try {
        const rowKey = key.replace('M6-2-prior-', '')
        priorData.value.set(rowKey, JSON.parse(resp.remark))
      } catch { /* skip */ }
    }
  }
  detailRows.value = restored.length > 0 ? restored : initDefaultRows()
}

// ─── EventBus（M5/M1联动） ───────────────────────────────────────────────────
function handleM5AccrualConfirmed(payload: {
  totalAccrual?: number
  statutoryAccrual?: number
  discretionaryAccrual?: number
  amount?: number
}) {
  const amount = Number(
    payload?.totalAccrual
    ?? ((payload?.statutoryAccrual ?? 0) + (payload?.discretionaryAccrual ?? 0) || undefined)
    ?? payload?.amount,
  ) || 0
  surplusLinkageRef.value = amount
  setSurplusLinkage(amount)
}

function handleM1DeclaredConfirmed(payload: {
  declaredAmount?: number
  amount?: number
}) {
  const amount = Number(payload?.declaredAmount ?? payload?.amount) || 0
  dividendLinkageRef.value = amount
  setDividendLinkage(amount)
}

function handleAdjustmentCreated() { formData.loadData() }

onMounted(async () => {
  await formData.loadData()
  _restoreRows()
  // 恢复审计说明
  const noteResp = formData.allResponses.value.get('M6-2-auditNote')
  if (noteResp?.remark) auditNote.value = noteResp.remark
  // 订阅M5/M1联动
  eventBus.on('m5:surplus-accrual', handleM5AccrualConfirmed)
  eventBus.on('m1:declared-confirmed', handleM1DeclaredConfirmed)
  eventBus.on('adjustment:created', handleAdjustmentCreated)
})

onUnmounted(() => {
  eventBus.off('m5:surplus-accrual', handleM5AccrualConfirmed)
  eventBus.off('m1:declared-confirmed', handleM1DeclaredConfirmed)
  eventBus.off('adjustment:created', handleAdjustmentCreated)
})
</script>

<style scoped>
.m6-tab-detail { padding: 12px; font-size: var(--wp-font-size, 13px); }

/* 蓝色渐变引导区 */
.guide-area {
  background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 50%, #c0e4f9 100%);
  border-radius: 8px;
  padding: 16px 20px;
  margin-bottom: 16px;
  border: 1px solid #b3d8f0;
}
.guide-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 24px;
}
.guide-step {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #1a5276;
  line-height: 1.5;
}
.step-num {
  font-weight: 700;
  color: #2980b9;
  font-size: 14px;
  flex-shrink: 0;
}
.step-text { color: #2c3e50; }

/* 标题栏 */
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.equity-badge { font-weight: 600; }

/* 方法论上下文 */
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }

/* 联动警告 */
.linkage-alert { margin-bottom: 12px; }

/* 区段切换 */
.period-switcher { margin-bottom: 12px; }

/* 操作栏 */
.action-bar { margin-bottom: 8px; }

/* 表格 */
.detail-table { font-size: var(--wp-font-size, 13px); }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.formula-row) { background: #f0f9ff !important; }
:deep(.formula-row td) { border-bottom: 1px dashed #409eff; }
:deep(.category-row) { background: #fafafa !important; font-weight: 600; }

/* 公式列 */
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; border-bottom: 1px dashed #409eff; cursor: help; }
.formula-row-label { font-weight: 700; color: #303133; }
.category-label { font-weight: 600; color: #303133; }

/* 底部汇总 */
.detail-footer {
  margin-top: 12px; margin-bottom: 16px;
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  padding: 12px 16px; background: #f5f7fa; border-radius: 6px;
}

/* 审计说明 */
.audit-note-card { margin-top: 16px; }

/* 跨底稿联动 */
.cross-wp-links {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 10px 16px;
  background: #f0f9eb;
  border: 1px solid #e1f3d8;
  border-radius: 6px;
  margin-top: 16px;
  margin-bottom: 4px;
  font-size: var(--wp-font-size, 13px);
}
.cross-wp-label {
  font-weight: 600;
  color: #303133;
  flex-shrink: 0;
}
.cross-wp-desc {
  color: #606266;
  font-size: 12px;
  margin-right: 8px;
}
.card-title { font-size: 14px; font-weight: 600; color: #303133; }

/* 编制提示 */
.m6-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.m6-details-tip summary { cursor: pointer; font-weight: 600; color: #303133; }
.m6-details-tip ul { margin: 8px 0 0; padding-left: 20px; }
.m6-details-tip li { margin-bottom: 4px; line-height: 1.5; }
</style>
