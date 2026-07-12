<template>
  <div class="n1-tab-loss-check">
    <!-- ═══ 双模式切换 ═══ -->
    <div class="n1-mode-bar">
      <el-segmented v-model="dualMode.mode.value" :options="dualMode.modeOptions.value" @change="dualMode.switchMode" />
    </div>

    <!-- ═══ OnlyOffice 降级模式 ═══ -->
    <template v-if="dualMode.isOnlyOffice.value">
      <GtOnlyOfficeSheet :wp-id="wpId" :project-id="projectId" sheet-name="亏损检查N1-5" style="height: 100%; min-height: 600px" />
    </template>

    <!-- ═══ 结构化视图 ═══ -->
    <template v-else>
      <!-- ═══ 蓝色渐变引导区（多步骤引导） ═══ -->
      <div class="n1-guidance-banner">
        <div class="guidance-grid">
          <div class="guidance-step">
            <span class="step-num">①</span>
            <span class="step-text">录入各年度亏损金额及已弥补情况</span>
          </div>
          <div class="guidance-step">
            <span class="step-num">②</span>
            <span class="step-text">系统自动计算未弥补金额、判断弥补期限</span>
          </div>
          <div class="guidance-step">
            <span class="step-num">③</span>
            <span class="step-text">录入预计未来应纳税所得额，系统测算可确认递延税资产</span>
          </div>
          <div class="guidance-step">
            <span class="step-num">④</span>
            <span class="step-text">合计可确认额回填N1-4/N1-1的可弥补亏损项</span>
          </div>
        </div>
      </div>

      <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
      <div class="n1-methodology-ctx">
        <p><strong>可弥补亏损确认逻辑（CAS 18 第15条·谨慎性原则）</strong></p>
        <p>企业对于能够结转以后年度的可抵扣亏损和税款抵减，应当以很可能获得用来抵扣的未来应纳税所得额为限，确认相应的递延所得税资产。</p>
        <p>可确认递延税资产 = min(未弥补亏损, 预计未来应纳税所得额) × 适用税率。弥补期限：一般企业5年 / 高新技术企业·科技型中小企业10年。</p>
      </div>

      <!-- ═══ 警告区域 ═══ -->
      <div v-if="lossCheck.expiredWarnings.value.length > 0 || lossCheck.insufficientWarnings.value.length > 0" class="n1-warnings-area">
        <!-- 届满标红警告 -->
        <div v-for="w in lossCheck.expiredWarnings.value" :key="'exp-' + w.rowIndex" class="warn-item warn-expired">
          <el-icon><WarningFilled /></el-icon>
          <span>{{ w.message }}</span>
        </div>
        <!-- 不足标黄警告 -->
        <div v-for="w in lossCheck.insufficientWarnings.value" :key="'ins-' + w.rowIndex" class="warn-item warn-insufficient">
          <el-icon><Warning /></el-icon>
          <span>{{ w.message }}</span>
        </div>
      </div>

      <!-- ═══ 亏损检查主 Section ═══ -->
      <el-card shadow="never" class="n1-section-card">
        <template #header>
          <div class="section-header">
            <div class="section-title-group">
              <span class="section-title">可用以后年度税前利润弥补的亏损检查表 N1-5</span>
              <el-tag type="info" size="small">30×13</el-tag>
            </div>
            <div class="section-actions">
              <el-dropdown trigger="click" @command="handleImportExportCmd">
                <el-button size="small">导入导出 ▾</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
                    <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
                    <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <el-button size="small" @click="handleAI('loss-check')">
                <el-icon><MagicStick /></el-icon> AI辅助
              </el-button>
              <el-button size="small" @click="openReview?.('N1-5-亏损检查')">
                <el-icon><ChatDotSquare /></el-icon> 复核
              </el-button>
            </div>
          </div>
        </template>

        <!-- 动态行新增 -->
        <div v-if="!isReadonly" class="n1-row-actions">
          <el-button type="primary" size="small" @click="handleAddLossYear">+ 新增亏损年度</el-button>
          <span class="row-count">共 {{ lossCheck.rows.value.length }} 个年度</span>
        </div>

        <!-- ═══ 亏损检查表格（30行×13列） ═══ -->
        <el-table
          :data="lossCheck.rows.value"
          border
          size="small"
          style="width: 100%"
          class="loss-check-table"
          :row-class-name="getRowClassName"
          show-summary
          :summary-method="getSummaries"
        >
          <el-table-column prop="lossYear" label="亏损年度" min-width="80" align="center" fixed>
            <template #default="{ row }">
              <span class="year-cell" :class="{ 'year-expired': row.isExpired }">{{ row.lossYear }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="lossAmount" label="亏损金额" min-width="110" align="right">
            <template #default="{ row, $index }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.lossAmount"
                size="small"
                :controls="false"
                :precision="2"
                class="cell-input"
                @change="(v: number) => lossCheck.updateRow($index, 'lossAmount', v ?? 0)"
              />
              <span v-else class="cell-value">{{ fmtAmt(row.lossAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="expiryYear" label="弥补截止年度" min-width="100" align="center">
            <template #header>
              <el-tooltip content="弥补截止年度 = 亏损年度 + 最长弥补年限" placement="top">
                <span class="formula-col">弥补截止年度</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span :class="['formula-value', { 'text-danger-bold': row.isExpired }]">{{ row.expiryYear }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="maxYears" label="弥补年限" min-width="80" align="center">
            <template #default="{ row, $index }">
              <el-select
                v-if="!isReadonly"
                :model-value="row.maxYears"
                size="small"
                style="width: 70px"
                @change="(v: number) => lossCheck.updateRow($index, 'maxYears', v)"
              >
                <el-option :value="5" label="5年" />
                <el-option :value="10" label="10年" />
              </el-select>
              <span v-else>{{ row.maxYears }}年</span>
            </template>
          </el-table-column>
          <el-table-column prop="recoveredBegin" label="期初已弥补" min-width="110" align="right">
            <template #default="{ row, $index }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.recoveredBegin"
                size="small"
                :controls="false"
                :precision="2"
                class="cell-input"
                @change="(v: number) => lossCheck.updateRow($index, 'recoveredBegin', v ?? 0)"
              />
              <span v-else class="cell-value">{{ fmtAmt(row.recoveredBegin) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="currentRecovery" label="本期弥补" min-width="100" align="right">
            <template #default="{ row, $index }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.currentRecovery"
                size="small"
                :controls="false"
                :precision="2"
                class="cell-input"
                @change="(v: number) => lossCheck.updateRow($index, 'currentRecovery', v ?? 0)"
              />
              <span v-else class="cell-value">{{ fmtAmt(row.currentRecovery) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="totalRecovered" label="已弥补金额" min-width="110" align="right">
            <template #header>
              <el-tooltip content="已弥补金额 = 期初已弥补 + 本期弥补" placement="top">
                <span class="formula-col">已弥补金额</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <el-tooltip content="期初已弥补 + 本期弥补" placement="top">
                <span class="formula-value">{{ fmtAmt(row.totalRecovered) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column prop="unrecoveredLoss" label="未弥补金额" min-width="110" align="right">
            <template #header>
              <el-tooltip content="未弥补金额 = 亏损金额 − 已弥补金额" placement="top">
                <span class="formula-col">未弥补金额</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <el-tooltip content="亏损金额 − 已弥补金额" placement="top">
                <span :class="['formula-value', { 'text-danger': row.unrecoveredLoss > 0 && row.isExpired }]">
                  {{ fmtAmt(row.unrecoveredLoss) }}
                </span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column prop="futureTaxableIncome" label="预计未来应纳税所得额" min-width="150" align="right">
            <template #default="{ row, $index }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.futureTaxableIncome"
                size="small"
                :controls="false"
                :precision="2"
                class="cell-input"
                :class="{ 'insufficient-input': row.isInsufficient }"
                @change="(v: number) => lossCheck.updateRow($index, 'futureTaxableIncome', v ?? 0)"
              />
              <span v-else :class="['cell-value', { 'text-warning': row.isInsufficient }]">
                {{ fmtAmt(row.futureTaxableIncome) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="taxRate" label="适用税率" min-width="80" align="center">
            <template #default="{ row, $index }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.taxRate * 100"
                size="small"
                :controls="false"
                :precision="0"
                :min="0"
                :max="100"
                class="cell-input rate-input"
                @change="(v: number) => lossCheck.updateRow($index, 'taxRate', (v ?? 25) / 100)"
              />
              <span v-else>{{ fmtPercent(row.taxRate) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="recognizableAsset" label="可确认递延税资产" min-width="140" align="right">
            <template #header>
              <el-tooltip content="可确认递延税资产 = min(未弥补金额, 预计未来应纳税所得额) × 适用税率" placement="top">
                <span class="formula-col">可确认递延税资产</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <el-tooltip :content="`min(${fmtAmt(row.unrecoveredLoss)}, ${fmtAmt(row.futureTaxableIncome)}) × ${fmtPercent(row.taxRate)}`" placement="top">
                <span :class="['formula-value', 'asset-value', { 'text-muted': row.isExpired || row.recognizableAsset === 0 }]">
                  {{ row.isExpired ? '—（已届满）' : fmtAmt(row.recognizableAsset) }}
                </span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column prop="recognitionBasis" label="确认依据" min-width="160">
            <template #default="{ row, $index }">
              <el-input
                v-if="!isReadonly"
                :model-value="row.recognitionBasis"
                size="small"
                placeholder="如：盈利预测/合同..."
                @change="(v: string) => lossCheck.updateRow($index, 'recognitionBasis', v ?? '')"
              />
              <span v-else class="basis-text">{{ row.recognitionBasis || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" min-width="80" align="center" fixed="right">
            <template #default="{ row }">
              <el-tag v-if="row.isExpired" type="danger" size="small">已届满</el-tag>
              <el-tag v-else-if="row.isInsufficient" type="warning" size="small">不足</el-tag>
              <el-tag v-else-if="row.recognizableAsset > 0" type="success" size="small">可确认</el-tag>
              <el-tag v-else type="info" size="small">—</el-tag>
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="" width="60" align="center" fixed="right">
            <template #default="{ $index }">
              <el-button type="danger" size="small" link @click="lossCheck.removeRow($index)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- ═══ 合计 + 回填操作区 ═══ -->
      <div class="n1-loss-totals">
        <div class="total-section total-recognizable">
          <div class="total-info">
            <span class="total-label">可确认递延税资产合计（可弥补亏损项）</span>
            <span class="total-value asset-value">{{ fmtAmt(lossCheck.totals.value.recognizableAsset) }}</span>
          </div>
          <div class="total-actions">
            <el-button
              type="success"
              size="small"
              :disabled="isReadonly"
              :loading="writebackLoading"
              @click="handleWritebackToN4"
            >
              回填 → N1-4/N1-1
            </el-button>
            <GtIndexChip value="N1-4" :context-project-id="projectId" />
            <GtIndexChip value="N1-1" :context-project-id="projectId" />
          </div>
        </div>
        <div class="total-section total-unrecovered">
          <div class="total-info">
            <span class="total-label">未弥补亏损合计</span>
            <span class="total-value text-danger">{{ fmtAmt(lossCheck.totals.value.unrecoveredLoss) }}</span>
          </div>
          <div class="total-meta">
            <span class="meta-item">亏损合计: {{ fmtAmt(lossCheck.totals.value.lossAmount) }}</span>
            <span class="meta-item">已弥补合计: {{ fmtAmt(lossCheck.totals.value.totalRecovered) }}</span>
          </div>
        </div>
      </div>

      <!-- ═══ 剩余年限可视化 ═══ -->
      <div v-if="lossCheck.rows.value.length > 0" class="n1-remaining-years">
        <div class="ry-title">各年度亏损剩余弥补年限</div>
        <div class="ry-bars">
          <div v-for="row in lossCheck.rows.value" :key="row.id" class="ry-bar-item">
            <span class="ry-year">{{ row.lossYear }}</span>
            <div class="ry-bar-track">
              <div
                class="ry-bar-fill"
                :class="{ 'ry-expired': row.isExpired, 'ry-warning': row.remainingYears <= 1 && !row.isExpired }"
                :style="{ width: `${Math.min(100, (row.remainingYears / row.maxYears) * 100)}%` }"
              ></div>
            </div>
            <span class="ry-label" :class="{ 'text-danger': row.isExpired }">
              {{ row.isExpired ? '已届满' : `${row.remainingYears}年` }}
            </span>
          </div>
        </div>
      </div>

      <!-- ═══ 确认判断依据 + 复核入口（底部说明） ═══ -->
      <el-card shadow="never" class="n1-section-card">
        <template #header>
          <div class="section-header">
            <span class="section-title">确认判断依据</span>
            <div class="section-actions">
              <el-button size="small" @click="handleAI('basis')">
                <el-icon><MagicStick /></el-icon> AI辅助
              </el-button>
              <el-button size="small" @click="openReview?.('N1-5-确认依据')">
                <el-icon><ChatDotSquare /></el-icon> 复核
              </el-button>
            </div>
          </div>
        </template>
        <div class="n1-basis-area">
          <div class="field-group">
            <label class="field-label">确认递延税资产的判断依据</label>
            <el-input
              v-model="basisNotes"
              type="textarea"
              :autosize="{ minRows: 3, maxRows: 8 }"
              :disabled="isReadonly"
              placeholder="说明确认可弥补亏损对应递延税资产的判断依据，如：被审计单位近年盈利能力分析、管理层利润预测可靠性评估、税务筹划方案可行性..."
              @change="handleBasisSave"
            />
          </div>
          <div class="field-group">
            <label class="field-label">审计结论</label>
            <el-input
              v-model="auditConclusion"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 5 }"
              :disabled="isReadonly"
              placeholder="经检查，可弥补亏损对应的递延所得税资产确认金额合理/不合理..."
              @change="handleConclusionSave"
            />
          </div>
        </div>
      </el-card>

      <!-- ═══ 编制提示（折叠底部） ═══ -->
      <details class="n1-details-tip">
        <summary>编制提示</summary>
        <ul>
          <li>可弥补亏损 = 经税务机关确认的各年度税前亏损金额</li>
          <li>弥补期限：一般企业5年（《企业所得税法》第18条），高新技术企业/科技型中小企业10年（财税[2018]76号/45号）</li>
          <li>未弥补金额 = 亏损金额 − 已弥补金额（含期初+本期）</li>
          <li>可确认递延税资产 = min(未弥补亏损, 预计未来应纳税所得额) × 适用税率</li>
          <li>预计未来应纳税所得额不足以弥补的部分，不确认递延所得税资产（谨慎性原则）</li>
          <li>弥补期限届满的亏损，不再确认递延税资产（标红提示）</li>
          <li>确认依据应说明管理层利润预测的可靠性、历史盈利趋势、行业环境等</li>
          <li>"回填→N1-4/N1-1"将合计可确认额写入测算表和审定表的可弥补亏损项</li>
        </ul>
      </details>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * N1TabLossCheck — N1-5 可用以后年度税前利润弥补的亏损检查表
 *
 * Spec: .kiro/specs/n1-deferred-tax-assets/
 * Task: 4.5
 * Requirements: 5.1-5.6
 *
 * 核心职责：
 * - 30×13 亏损检查表
 * - 未弥补/可确认测算（useN1LossCompensationEngine 纯函数）
 * - 弥补期限判断（一般5年，高新/科技型中小企业10年）
 * - 届满标红 + 不足标黄（谨慎性警告）
 * - 合计可确认额回填 N1-4/N1-1 的可弥补亏损项
 * - 底部确认判断依据 + 复核入口
 * - 蓝色渐变引导区 + 方法论琥珀块 + 公式虚线 + tooltip
 * - 双模式 + 导入导出 + AI辅助 + 动态行新增
 *
 * 科目：1811 递延所得税资产（**借方/资产类**！期末余额=期初+借-贷）
 */
import { ref, inject, onMounted, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { WarningFilled, Warning, MagicStick, ChatDotSquare } from '@element-plus/icons-vue'
// @ts-ignore
import GtIndexChip from '../../GtIndexChip.vue'
// @ts-ignore
import GtOnlyOfficeSheet from '../../GtOnlyOfficeSheet.vue'
import { useN1FormData } from '../../composables/useN1FormData'
import { useN1LossCheck } from '../../composables/useN1LossCheck'
import { useN1CrossSheet } from '../../composables/useN1CrossSheet'
import { useN1DualMode } from '../../composables/useN1DualMode'
import { useN1ImportExport } from '../../composables/useN1ImportExport'
import { eventBus } from '@/utils/eventBus'

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
const importExport = useN1ImportExport({ wpId: wpIdRef, projectId: projectIdRef })

const lossCheck = useN1LossCheck({
  wpId: wpIdRef,
  projectId: projectIdRef,
  allResponses: formData.allResponses,
  formData,
})

// ─── State ───────────────────────────────────────────────────────────────────

const writebackLoading = ref(false)
const basisNotes = ref('')
const auditConclusion = ref('')

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  // 恢复审计说明/结论
  const basis = formData.getField('5', 'recognition-basis')
  if (basis) basisNotes.value = String(basis)
  const conclusion = formData.getField('5', 'audit-conclusion')
  if (conclusion) auditConclusion.value = String(conclusion)
})

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmtAmt(val: number | undefined): string {
  if (val == null || isNaN(val) || val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(val: number | undefined): string {
  if (val == null || isNaN(val) || val === 0) return '—'
  return (val * 100).toFixed(0) + '%'
}

/**
 * 行样式：届满标红行、不足标黄行
 */
function getRowClassName({ row }: { row: any }): string {
  if (row.isExpired) return 'row-expired'
  if (row.isInsufficient) return 'row-insufficient'
  return ''
}

// ─── 合计行方法 ──────────────────────────────────────────────────────────────

function getSummaries({ columns }: any) {
  const sums: string[] = []
  const rows = lossCheck.rows.value
  columns.forEach((col: any, i: number) => {
    if (i === 0) { sums[i] = '合计'; return }
    const prop = col.property
    if (!prop) { sums[i] = ''; return }
    const numericProps = ['lossAmount', 'totalRecovered', 'unrecoveredLoss', 'futureTaxableIncome', 'recognizableAsset', 'recoveredBegin', 'currentRecovery']
    if (numericProps.includes(prop)) {
      const total = rows.reduce((sum, r) => sum + ((r as any)[prop] || 0), 0)
      sums[i] = fmtAmt(total)
    } else {
      sums[i] = ''
    }
  })
  return sums
}

// ─── 动态行新增（ElMessageBox.prompt） ───────────────────────────────────────

async function handleAddLossYear() {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入亏损发生年度（如2020）',
      '新增亏损年度',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /^\d{4}$/,
        inputErrorMessage: '请输入4位数字年份',
        inputPlaceholder: '如：2020',
      },
    )
    if (value) {
      const year = parseInt(value, 10)
      // 二次确认弥补年限
      const { value: yearsStr } = await ElMessageBox.prompt(
        '请选择弥补年限（一般企业5年，高新/科技型中小企业10年）',
        '弥补年限',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消（默认5年）',
          inputValue: '5',
          inputPattern: /^(5|10)$/,
          inputErrorMessage: '请输入5或10',
        },
      ).catch(() => ({ value: '5' }))
      const maxYears = parseInt(yearsStr || '5', 10)
      lossCheck.addRow(year, maxYears)
      ElMessage.success(`已添加 ${year} 年度亏损（弥补年限 ${maxYears} 年）`)
    }
  } catch { /* cancelled */ }
}

// ─── 回填N1-4/N1-1（可确认递延税资产合计） ──────────────────────────────────

async function handleWritebackToN4() {
  writebackLoading.value = true
  try {
    const total = lossCheck.totals.value.recognizableAsset
    // 保存到 allResponses 供 crossSheet 读取 → N1-4可弥补亏损行
    await formData.saveField('N1-5-total-recognizable', {
      remark: String(total),
    })
    // 发布事件通知 N1-4 和 N1-1 刷新可弥补亏损项
    eventBus.emit('loss-check:recognizable-updated', {
      recognizableTotal: total,
      wpCode: 'N1',
      source: 'N1-5',
      timestamp: Date.now(),
    })
    ElMessage.success(`可确认递延税资产合计 ${fmtAmt(total)} 已回填N1-4/N1-1`)
  } catch (err: any) {
    ElMessage.error(`回填失败：${err?.message || '未知错误'}`)
  } finally {
    writebackLoading.value = false
  }
}

// ─── 导入导出命令 ────────────────────────────────────────────────────────────

async function handleImportExportCmd(cmd: string) {
  switch (cmd) {
    case 'export-template':
      await importExport.exportTemplate()
      break
    case 'export-data':
      await importExport.exportData()
      break
    case 'import-data': {
      const input = document.createElement('input')
      input.type = 'file'
      input.accept = '.xlsx,.xls'
      input.onchange = async (e: Event) => {
        const file = (e.target as HTMLInputElement).files?.[0]
        if (file) {
          await importExport.importData(file)
          await formData.loadData()
        }
      }
      input.click()
      break
    }
  }
}

// ─── 审计说明/结论保存 ───────────────────────────────────────────────────────

function handleBasisSave() {
  formData.setField('5', 'recognition-basis', basisNotes.value)
}

function handleConclusionSave() {
  formData.setField('5', 'audit-conclusion', auditConclusion.value)
}

// ─── AI辅助 ──────────────────────────────────────────────────────────────────

function handleAI(section: string) {
  ElMessage.info(`AI辅助分析可弥补亏损${section}数据...`)
}
</script>

<style scoped>
.n1-tab-loss-check {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
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
  font-size: var(--wp-font-size, 13px);
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
  font-size: var(--wp-font-size, 13px);
  color: #92400e;
  line-height: 1.7;
}

.n1-methodology-ctx p {
  margin: 0 0 4px;
}

.n1-methodology-ctx p:last-child {
  margin-bottom: 0;
}

/* ─── 警告区域 ─── */
.n1-warnings-area {
  margin-bottom: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.warn-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
}

.warn-expired {
  background: #fef2f2;
  border: 1px solid #fca5a5;
  border-left: 4px solid #dc2626;
  color: #991b1b;
}

.warn-insufficient {
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-left: 4px solid #d97706;
  color: #92400e;
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

.section-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ─── 动态行操作 ─── */
.n1-row-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}

.row-count {
  font-size: 12px;
  color: #909399;
}

/* ─── 表格通用 ─── */
.loss-check-table {
  margin-bottom: 0;
}

:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}

:deep(.el-input-number) {
  width: 100%;
}

:deep(.el-input-number .el-input__inner) {
  text-align: right;
  font-size: var(--wp-font-size, 13px);
}

.cell-input {
  width: 100%;
}

.rate-input {
  width: 60px !important;
}

.cell-value {
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.year-cell {
  font-weight: 600;
  color: #303133;
}

.year-expired {
  color: #dc2626 !important;
  text-decoration: line-through;
}

.basis-text {
  font-size: 12px;
  color: #606266;
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

.asset-value {
  color: #2e7d32 !important;
  font-weight: 700;
}

.text-danger {
  color: #f56c6c !important;
}

.text-danger-bold {
  color: #dc2626 !important;
  font-weight: 700;
}

.text-warning {
  color: #e65100 !important;
}

.text-muted {
  color: #c0c4cc;
}

/* ─── 行高亮（届满标红、不足标黄） ─── */
:deep(.row-expired td) {
  background-color: #fef2f2 !important;
}

:deep(.row-insufficient td) {
  background-color: #fffbeb !important;
}

/* ─── 不足输入框黄色边框 ─── */
.insufficient-input :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px #d97706 inset;
}

/* ─── 合计 + 回填操作区 ─── */
.n1-loss-totals {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 16px;
  padding: 12px;
}

.total-section {
  padding: 12px 16px;
  border-radius: 8px;
}

.total-recognizable {
  background: #e8f5e9;
  border: 1px solid #a5d6a7;
}

.total-unrecovered {
  background: #fef2f2;
  border: 1px solid #fca5a5;
}

.total-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 8px;
}

.total-label {
  font-size: 12px;
  color: #606266;
  font-weight: 500;
}

.total-value {
  font-size: 18px;
  font-weight: 700;
  color: #303133;
}

.total-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.total-meta {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: #909399;
}

.meta-item {
  white-space: nowrap;
}

/* ─── 剩余年限可视化 ─── */
.n1-remaining-years {
  margin-bottom: 16px;
  padding: 14px 16px;
  background: #fafbfc;
  border: 1px solid #ebeef5;
  border-radius: 8px;
}

.ry-title {
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #303133;
  margin-bottom: 10px;
}

.ry-bars {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ry-bar-item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.ry-year {
  width: 40px;
  font-size: 12px;
  font-weight: 600;
  color: #606266;
  text-align: right;
}

.ry-bar-track {
  flex: 1;
  height: 8px;
  background: #f0f2f5;
  border-radius: 4px;
  overflow: hidden;
}

.ry-bar-fill {
  height: 100%;
  background: #67c23a;
  border-radius: 4px;
  transition: width 0.3s ease;
}

.ry-bar-fill.ry-expired {
  background: #f56c6c;
  width: 100% !important;
}

.ry-bar-fill.ry-warning {
  background: #e6a23c;
}

.ry-label {
  width: 50px;
  font-size: 12px;
  color: #606266;
}

/* ─── 确认判断依据卡片 ─── */
.n1-basis-area {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.field-group {
  margin-bottom: 0;
}

.field-label {
  display: block;
  font-size: var(--wp-font-size, 13px);
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
  font-size: var(--wp-font-size, 13px);
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
