<template>
  <div class="s20-revenue-deduction">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <!-- ─── 工具栏：双模式 + 导入导出 + 版本历史 ─── -->
      <div class="s20-toolbar">
        <el-segmented
          v-model="dualMode"
          :options="modeOptions"
          size="small"
          @change="handleModeChange"
        />
        <el-dropdown trigger="click" @command="handleImportExport">
          <el-button size="small">
            导入导出 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item command="exportData">导出数据</el-dropdown-item>
              <el-dropdown-item v-if="!isReadonly" command="importData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="openVersionHistory">版本历史</el-button>
      </div>

      <!-- 双模式：切换到 OnlyOffice -->
      <GtOnlyOfficeSheet
        v-if="dualMode === 'OnlyOffice'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || '营业收入扣除情况核查'"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- HTML 模式：单页多区段渲染 -->
      <div v-else class="s20-content">
        <!-- 审计目标 -->
        <el-alert type="info" :closable="false" show-icon class="audit-objective">
          <template #title>审计目标</template>
          <div class="audit-objective-text">
            核查营业收入扣除情况：逐项识别与主营业务无关的业务收入和不具备商业实质的收入，计算扣除后营业收入金额，判断是否触及退市风险警示（利润总额/净利润/扣非净利润孰低为负值且扣除后营业收入低于人民币 3 亿元）。
          </div>
        </el-alert>

        <!-- ─── 顶部引导区（蓝色渐变 2列grid） ─── -->
        <div class="s20-guide-banner">
          <div class="guide-grid">
            <div class="guide-step">
              <span class="step-num">①</span>
              <span class="step-text">确认适用情形（利润总额/净利润/扣非净利润孰低为负值）</span>
            </div>
            <div class="guide-step">
              <span class="step-num">②</span>
              <span class="step-text">逐项核查营业收入扣除项目并计算扣除后金额</span>
            </div>
            <div class="guide-step">
              <span class="step-num">③</span>
              <span class="step-text">填列与主营业务无关的业务收入明细</span>
            </div>
            <div class="guide-step">
              <span class="step-num">④</span>
              <span class="step-text">填列不具备商业实质的收入明细</span>
            </div>
          </div>
        </div>

        <!-- ═══════════════════════════════════════════════════ -->
        <!-- 区段1: 核查目标 — 方法论上下文（适用情形提示 Req 4.5） -->
        <!-- ═══════════════════════════════════════════════════ -->
        <div class="s20-segment segment-methodology">
          <div class="methodology-context">
            <p class="methodology-title">适用情形</p>
            <p class="methodology-text">
              根据《上市公司重大违法强制退市实施办法》，上市公司最近一个会计年度经审计的<strong>利润总额</strong>、<strong>净利润</strong>或<strong>扣除非经常性损益后净利润</strong>孰低者为负值，且最近一个会计年度经审计的<strong>营业收入</strong>低于人民币<strong>3亿元</strong>（扣除与主营业务无关的业务收入和不具备商业实质的收入后），将被实施退市风险警示。
            </p>
            <p class="methodology-note">
              本底稿适用于：利润总额、净利润、扣除非经常性损益后净利润，三者孰低为负值时，须对营业收入扣除情况进行核查。
            </p>
          </div>
        </div>

        <!-- ═══════════════════════════════════════════════════ -->
        <!-- 区段2: 扣非净利润 — 判断适用条件 -->
        <!-- ═══════════════════════════════════════════════════ -->
        <div class="s20-segment">
          <div class="segment-header">
            <h3 class="segment-title">一、适用条件判断</h3>
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              @click="handleAiAssist('applicability')"
            >AI辅助</el-button>
            <el-button
              size="small"
              @click="handleOpenReview('s20-applicability', '适用条件判断')"
            >复核</el-button>
          </div>
          <el-table :data="applicabilityRows" border class="s20-table" size="small">
            <el-table-column label="项目" prop="label" min-width="200" />
            <el-table-column label="本年度审定数（C列）" min-width="160" align="right">
              <template #default="{ row }">
                <span class="formula-cell" :title="row.tooltip || '取自审定表'">
                  {{ fmtAmount(row.currentYear) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="判断" min-width="80" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.currentYear !== null && row.currentYear < 0" type="danger" size="small">为负</el-tag>
                <el-tag v-else-if="row.currentYear !== null" type="success" size="small">非负</el-tag>
                <span v-else>-</span>
              </template>
            </el-table-column>
          </el-table>
          <div class="applicability-conclusion">
            <el-tag :type="isApplicable ? 'warning' : 'info'" size="default">
              {{ isApplicable ? '⚠ 适用：三者孰低为负值，须进行营业收入扣除核查' : '✓ 不适用：三者孰低非负值' }}
            </el-tag>
          </div>
        </div>

        <!-- ═══════════════════════════════════════════════════ -->
        <!-- 区段3: 营收扣除汇总 — 核心公式区（uses useS20FormulaEngine） -->
        <!-- ═══════════════════════════════════════════════════ -->
        <div class="s20-segment">
          <div class="segment-header">
            <h3 class="segment-title">二、营业收入扣除情况汇总</h3>
            <div class="segment-actions">
              <span class="data-source-hint">数据来源：</span>
              <GtIndexChip value="D4" />
              <el-button
                size="small"
                @click="handleOpenReview('s20-summary', '营收扣除汇总')"
              >复核</el-button>
            </div>
          </div>
          <el-table :data="summaryTableData" border class="s20-table" size="small">
            <el-table-column label="项目" prop="label" min-width="240" />
            <el-table-column label="本年度审定数（C列）" min-width="160" align="right">
              <template #default="{ row }">
                <template v-if="row.isFormula">
                  <span class="formula-cell" :title="row.formulaTooltip">
                    {{ row.unable ? '不可计算' : fmtAmount(row.currentYear) }}
                  </span>
                </template>
                <template v-else-if="row.isInput && !isReadonly">
                  <WpAmountInput
                    v-model="row.currentYear"
                    size="small"
                    class="amount-input"
                    @change="onInputChange"
                  />
                </template>
                <template v-else>
                  <span>{{ fmtAmount(row.currentYear) }}</span>
                </template>
              </template>
            </el-table-column>
            <el-table-column label="上年度追溯调整后审定数（D列）" min-width="180" align="right">
              <template #default="{ row }">
                <template v-if="row.isFormula">
                  <span class="formula-cell" :title="row.formulaTooltipPrior">
                    {{ row.unablePrior ? '不可计算' : fmtAmount(row.priorYear) }}
                  </span>
                </template>
                <template v-else-if="row.isInput && !isReadonly">
                  <WpAmountInput
                    v-model="row.priorYear"
                    size="small"
                    class="amount-input"
                    @change="onInputChange"
                  />
                </template>
                <template v-else>
                  <span>{{ fmtAmount(row.priorYear) }}</span>
                </template>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <!-- ═══════════════════════════════════════════════════ -->
        <!-- 区段4: 与主营无关收入明细 — 动态明细行表格 -->
        <!-- ═══════════════════════════════════════════════════ -->
        <div class="s20-segment">
          <div class="segment-header">
            <h3 class="segment-title">三、与主营业务无关的业务收入明细</h3>
            <div class="segment-actions">
              <el-button
                v-if="!isReadonly"
                size="small"
                type="primary"
                @click="addUnrelatedRow"
              >+ 新增行</el-button>
              <el-button
                v-if="!isReadonly"
                size="small"
                :icon="MagicStick"
                @click="handleAiAssist('unrelated')"
              >AI辅助</el-button>
              <el-button
                size="small"
                @click="handleOpenReview('s20-unrelated', '与主营无关收入明细')"
              >复核</el-button>
            </div>
          </div>
          <el-table :data="unrelatedRows" border class="s20-table" size="small">
            <el-table-column type="index" label="序号" width="60" />
            <el-table-column label="收入项目名称" min-width="200">
              <template #default="{ row, $index }">
                <el-input
                  v-if="!isReadonly"
                  v-model="row.name"
                  size="small"
                  placeholder="收入项目名称"
                  @change="onInputChange"
                />
                <span v-else>{{ row.name || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="本年度审定数" min-width="140" align="right">
              <template #default="{ row }">
                <WpAmountInput
                  v-if="!isReadonly"
                  v-model="row.currentYear"
                  size="small"
                  class="amount-input"
                  @change="onInputChange"
                />
                <span v-else>{{ fmtAmount(row.currentYear) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="上年度审定数" min-width="140" align="right">
              <template #default="{ row }">
                <WpAmountInput
                  v-if="!isReadonly"
                  v-model="row.priorYear"
                  size="small"
                  class="amount-input"
                  @change="onInputChange"
                />
                <span v-else>{{ fmtAmount(row.priorYear) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="扣除理由" min-width="200">
              <template #default="{ row }">
                <el-input
                  v-if="!isReadonly"
                  v-model="row.reason"
                  size="small"
                  type="textarea"
                  :autosize="{ minRows: 1, maxRows: 3 }"
                  placeholder="扣除理由"
                  @change="onInputChange"
                />
                <span v-else>{{ row.reason || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column v-if="!isReadonly" label="操作" width="70" align="center">
              <template #default="{ $index }">
                <el-button type="danger" link size="small" @click="removeUnrelatedRow($index)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div class="subtotal-row">
            <span class="subtotal-label">合计</span>
            <span class="formula-cell subtotal-value" title="=SUM(与主营无关明细)">
              {{ fmtAmount(unrelatedTotalCurrent) }}
            </span>
            <span class="formula-cell subtotal-value" title="=SUM(与主营无关明细-上年)">
              {{ fmtAmount(unrelatedTotalPrior) }}
            </span>
          </div>
        </div>

        <!-- ═══════════════════════════════════════════════════ -->
        <!-- 区段5: 不具备商业实质收入明细 — 动态明细行表格 -->
        <!-- ═══════════════════════════════════════════════════ -->
        <div class="s20-segment">
          <div class="segment-header">
            <h3 class="segment-title">四、不具备商业实质的收入明细</h3>
            <div class="segment-actions">
              <el-button
                v-if="!isReadonly"
                size="small"
                type="primary"
                @click="addNoSubstanceRow"
              >+ 新增行</el-button>
              <el-button
                v-if="!isReadonly"
                size="small"
                :icon="MagicStick"
                @click="handleAiAssist('noSubstance')"
              >AI辅助</el-button>
              <el-button
                size="small"
                @click="handleOpenReview('s20-no-substance', '不具备商业实质收入明细')"
              >复核</el-button>
            </div>
          </div>
          <el-table :data="noSubstanceRows" border class="s20-table" size="small">
            <el-table-column type="index" label="序号" width="60" />
            <el-table-column label="收入项目名称" min-width="200">
              <template #default="{ row }">
                <el-input
                  v-if="!isReadonly"
                  v-model="row.name"
                  size="small"
                  placeholder="收入项目名称"
                  @change="onInputChange"
                />
                <span v-else>{{ row.name || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="本年度审定数" min-width="140" align="right">
              <template #default="{ row }">
                <WpAmountInput
                  v-if="!isReadonly"
                  v-model="row.currentYear"
                  size="small"
                  class="amount-input"
                  @change="onInputChange"
                />
                <span v-else>{{ fmtAmount(row.currentYear) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="上年度审定数" min-width="140" align="right">
              <template #default="{ row }">
                <WpAmountInput
                  v-if="!isReadonly"
                  v-model="row.priorYear"
                  size="small"
                  class="amount-input"
                  @change="onInputChange"
                />
                <span v-else>{{ fmtAmount(row.priorYear) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="扣除理由" min-width="200">
              <template #default="{ row }">
                <el-input
                  v-if="!isReadonly"
                  v-model="row.reason"
                  size="small"
                  type="textarea"
                  :autosize="{ minRows: 1, maxRows: 3 }"
                  placeholder="扣除理由"
                  @change="onInputChange"
                />
                <span v-else>{{ row.reason || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column v-if="!isReadonly" label="操作" width="70" align="center">
              <template #default="{ $index }">
                <el-button type="danger" link size="small" @click="removeNoSubstanceRow($index)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div class="subtotal-row">
            <span class="subtotal-label">合计</span>
            <span class="formula-cell subtotal-value" title="=SUM(不具备商业实质明细)">
              {{ fmtAmount(noSubstanceTotalCurrent) }}
            </span>
            <span class="formula-cell subtotal-value" title="=SUM(不具备商业实质明细-上年)">
              {{ fmtAmount(noSubstanceTotalPrior) }}
            </span>
          </div>
        </div>

        <!-- ═══════════════════════════════════════════════════ -->
        <!-- 区段6: 其他核查事项 — 附加说明 -->
        <!-- ═══════════════════════════════════════════════════ -->
        <div class="s20-segment">
          <div class="segment-header">
            <h3 class="segment-title">五、其他核查事项及结论</h3>
            <div class="segment-actions">
              <el-button
                v-if="!isReadonly"
                size="small"
                :icon="MagicStick"
                @click="handleAiAssist('conclusion')"
              >AI辅助</el-button>
              <el-button
                size="small"
                @click="handleOpenReview('s20-conclusion', '其他核查事项')"
              >复核</el-button>
            </div>
          </div>
          <el-card shadow="never" class="conclusion-card">
            <el-input
              v-if="!isReadonly"
              v-model="otherMatters"
              type="textarea"
              :autosize="{ minRows: 3, maxRows: 8 }"
              placeholder="请填写其他需要说明的核查事项..."
              @change="onInputChange"
            />
            <div v-else class="conclusion-text">{{ otherMatters || '（无）' }}</div>
          </el-card>
          <el-card shadow="never" class="conclusion-card" style="margin-top: 8px">
            <template #header>
              <span style="font-weight: 600">审计结论</span>
            </template>
            <el-input
              v-if="!isReadonly"
              v-model="auditConclusion"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 6 }"
              placeholder="经核查，我们认为..."
              @change="onInputChange"
            />
            <div v-else class="conclusion-text">{{ auditConclusion || '（无）' }}</div>
          </el-card>
          <details class="edit-hint">
            <summary>编制提示</summary>
            <p>1. 核查范围：逐项判断是否存在与主营业务无关的业务收入和不具备商业实质的收入。</p>
            <p>2. 商业实质判断：关注关联方交易、异常大额交易、期末突击交易等。</p>
            <p>3. 双列比对：注意本年与上年的变动异常，说明变动原因。</p>
          </details>
        </div>
      </div>
    </template>

    <!-- 复核对话组件 -->
    <GtReviewDialog
      v-if="reviewDialogVisible"
      :wp-id="props.wpId"
      :section-id="reviewDialogSectionId"
      :section-label="reviewDialogSectionLabel"
      :current-user="currentUser"
      :related-data="{ wpCode: 'S20', projectId: props.projectId }"
    />

    <!-- 版本历史抽屉 -->
    <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../shared/WpAmountInput.vue'
/**
 * GtS20RevenueDeduction.vue — S20 营业收入扣除情况核查底稿主入口
 *
 * 由外层 GtWpRenderer 的 componentType 's20-revenue-deduction' 路由到此组件。
 * S20 为单 sheet 多区段组件（无内部 sheetName 分发），一页呈现 6 个功能区段。
 *
 * 区段结构（Phase0 验证）：
 *   区段1: 核查目标    → 方法论上下文（amber left border block - 适用情形提示）
 *   区段2: 扣非净利润  → 判断适用条件（利润总额/净利润/扣非净利润孰低为负值时适用）
 *   区段3: 营收扣除汇总 → 核心公式区（uses useS20FormulaEngine）
 *   区段4: 与主营无关收入明细 → 动态明细行表格
 *   区段5: 不具备商业实质收入明细 → 动态明细行表格
 *   区段6: 其他核查事项 → 附加说明
 *
 * 核心特性：
 * - 单 sheet 组件 — 无 v-if sheetName 分发，直接单页渲染
 * - Req 4.4: 取本年度审定数与上年度追溯调整后审定数两列并行呈现
 * - Req 4.5: 顶部方法论上下文区块展示适用情形提示
 * - selfLoad: htmlData 为 null 时自行调 render-config 加载数据
 * - 使用 useS20FormulaEngine composable 进行 reactive 计算
 * - 公式单元格只读（虚线下划线 + cursor:help + tooltip）
 * - 动态明细行增删（区段4 & 5）
 * - el-segmented 双模式（HTML/OnlyOffice）
 * - provide openReviewDialog
 * - EventBus 订阅 substantive:adjudicated
 *
 * Spec: .kiro/specs/s-estimate-calculation-workpapers/ Task 4.3
 * Requirements: 1.5, 4.4, 4.5
 */
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch, nextTick, provide, defineAsyncComponent } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick, ArrowDown } from '@element-plus/icons-vue'
import http from '@/utils/http'
import { parseResponseValue } from '../composables/useSExpertPersist'
import { useAuthStore } from '@/stores/auth'
import { fmtAmount } from '@/utils/formatters'
import {
  calcRevenueDeduction,
  parseNum,
  type RevenueDeductionInput,
  type RevenueDeductionResult,
} from '../composables/useS20FormulaEngine'
import { useSEstimateImportExport } from '../composables/useSEstimateImportExport'

// ─── Lazy-loaded shared components ───────────────────────────────────────────

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('../GtOnlyOfficeSheet.vue'))
const GtReviewDialog = defineAsyncComponent(() => import('@/components/collaboration/GtReviewDialog.vue'))
const GtWpVersionTrail = defineAsyncComponent(() => import('../version-trail/GtWpVersionTrail.vue'))
const GtIndexChip = defineAsyncComponent(() => import('../GtIndexChip.vue'))

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  year?: number
  htmlData?: any
  readonly?: boolean
}>()

const parentEmit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
}>()

// ─── State ───────────────────────────────────────────────────────────────────

const isLoading = ref(true)
const isReadonly = computed(() => !!props.readonly)

/** 持久化数据快照（item_id → {conclusion, remark}）；由 selfLoad 合并 responses_snapshot 填充 */
const allResponses = ref<Map<string, any>>(new Map())

// ─── Auth ────────────────────────────────────────────────────────────────────

const authStore = useAuthStore()
const currentUser = computed(() => ({
  id: authStore.userId || '',
  name: authStore.user?.full_name || authStore.username || '',
  role: (authStore.user?.role || '审计助理') as any,
}))

// ─── 双模式（HTML/OnlyOffice） ───────────────────────────────────────────────

const dualMode = ref<'HTML' | 'OnlyOffice'>('HTML')
const modeOptions = [
  { label: 'HTML', value: 'HTML' },
  { label: 'OnlyOffice', value: 'OnlyOffice' },
]

function handleModeChange(val: any) {
  dualMode.value = val
}

// ─── 导入导出（Req 10.1, 10.2） ─────────────────────────────────────────────

const importExport = useSEstimateImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

/** 导入导出 el-dropdown command handler */
function handleImportExport(command: string): void {
  // S20 两个动态行明细分 sheet 导出
  const sheets = ['S20-unrelated', 'S20-noSubstance']
  switch (command) {
    case 'exportTemplate':
      // 多区块分 sheet — 不传 sheet 则全导出（Req 10.3）
      importExport.exportTemplate('S20-unrelated')
      break
    case 'exportData':
      importExport.exportData('S20-unrelated')
      break
    case 'importData':
      _triggerFileUpload()
      break
  }
}

function _triggerFileUpload(): void {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls'
  input.onchange = async (e: Event) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return
    // 默认导入与主营无关收入明细，用户也可用 sheet 参数区分
    const result = await importExport.importData('S20-unrelated', file)
    if (result?.success) {
      // 重新加载数据
      await selfLoad()
    }
  }
  input.click()
}

// ─── 区段2: 适用条件判断数据 ─────────────────────────────────────────────────

interface ApplicabilityRow {
  label: string
  currentYear: number | null
  tooltip?: string
}

const applicabilityRows = reactive<ApplicabilityRow[]>([
  { label: '利润总额', currentYear: null, tooltip: '取自审定表/利润表' },
  { label: '净利润', currentYear: null, tooltip: '取自审定表/利润表' },
  { label: '扣除非经常性损益后净利润', currentYear: null, tooltip: '取自非经常性损益明细' },
])

/** 三者孰低为负值 → 适用 */
const isApplicable = computed(() => {
  const vals = applicabilityRows.map(r => r.currentYear).filter(v => v !== null) as number[]
  if (vals.length === 0) return false
  return Math.min(...vals) < 0
})

// ─── 区段3: 营收扣除汇总数据 ─────────────────────────────────────────────────

/** 主营业务收入明细（本年C列） */
const mainBusinessCurrent = reactive<number[]>([0, 0, 0, 0])
/** 主营业务收入明细（上年D列） */
const mainBusinessPrior = reactive<number[]>([0, 0, 0, 0])
/** 其他业务收入明细（本年） */
const otherBusinessCurrent = reactive<number[]>([0, 0, 0, 0])
/** 其他业务收入明细（上年） */
const otherBusinessPrior = reactive<number[]>([0, 0, 0, 0])

// ─── 区段4: 与主营无关收入明细（动态行） ─────────────────────────────────────

interface DetailRow {
  name: string
  currentYear: number
  priorYear: number
  reason: string
}

const unrelatedRows = reactive<DetailRow[]>([])
const noSubstanceRows = reactive<DetailRow[]>([])

/** 与主营无关合计（本年） */
const unrelatedTotalCurrent = computed(() =>
  unrelatedRows.reduce((sum, r) => sum + parseNum(r.currentYear), 0)
)
/** 与主营无关合计（上年） */
const unrelatedTotalPrior = computed(() =>
  unrelatedRows.reduce((sum, r) => sum + parseNum(r.priorYear), 0)
)
/** 不具备商业实质合计（本年） */
const noSubstanceTotalCurrent = computed(() =>
  noSubstanceRows.reduce((sum, r) => sum + parseNum(r.currentYear), 0)
)
/** 不具备商业实质合计（上年） */
const noSubstanceTotalPrior = computed(() =>
  noSubstanceRows.reduce((sum, r) => sum + parseNum(r.priorYear), 0)
)

// ─── 公式引擎（reactive） ────────────────────────────────────────────────────

/** 本年度输入 */
const currentInput = computed<RevenueDeductionInput>(() => ({
  mainBusiness: [...mainBusinessCurrent],
  otherBusiness: [...otherBusinessCurrent],
  unrelatedRevenue: unrelatedTotalCurrent.value,
  noSubstanceRevenue: noSubstanceTotalCurrent.value,
}))

/** 上年度输入 */
const priorInput = computed<RevenueDeductionInput>(() => ({
  mainBusiness: [...mainBusinessPrior],
  otherBusiness: [...otherBusinessPrior],
  unrelatedRevenue: unrelatedTotalPrior.value,
  noSubstanceRevenue: noSubstanceTotalPrior.value,
}))

/** 本年度计算结果 */
const currentResult = computed<RevenueDeductionResult>(() => calcRevenueDeduction(currentInput.value))
/** 上年度计算结果 */
const priorResult = computed<RevenueDeductionResult>(() => calcRevenueDeduction(priorInput.value))

// ─── 区段3: 汇总表数据 ──────────────────────────────────────────────────────

interface SummaryRow {
  label: string
  currentYear: number | null
  priorYear: number | null
  isFormula: boolean
  isInput: boolean
  formulaTooltip?: string
  formulaTooltipPrior?: string
  unable?: boolean
  unablePrior?: boolean
}

const summaryTableData = computed<SummaryRow[]>(() => {
  const cr = currentResult.value
  const pr = priorResult.value
  return [
    {
      label: '营业收入',
      currentYear: cr.revenue,
      priorYear: pr.revenue,
      isFormula: true,
      isInput: false,
      formulaTooltip: '=主营业务收入+其他业务收入',
      formulaTooltipPrior: '=主营业务收入(上年)+其他业务收入(上年)',
    },
    {
      label: '  其中：主营业务收入',
      currentYear: cr.mainBusinessTotal,
      priorYear: pr.mainBusinessTotal,
      isFormula: true,
      isInput: false,
      formulaTooltip: '=SUM(主营明细)',
      formulaTooltipPrior: '=SUM(主营明细-上年)',
    },
    {
      label: '  其中：其他业务收入',
      currentYear: cr.otherBusinessTotal,
      priorYear: pr.otherBusinessTotal,
      isFormula: true,
      isInput: false,
      formulaTooltip: '=SUM(其他明细)',
      formulaTooltipPrior: '=SUM(其他明细-上年)',
    },
    {
      label: '营业收入扣除项目合计',
      currentYear: cr.deductionTotal,
      priorYear: pr.deductionTotal,
      isFormula: true,
      isInput: false,
      formulaTooltip: '=与主营无关收入+不具备商业实质收入',
      formulaTooltipPrior: '=与主营无关收入(上年)+不具备商业实质收入(上年)',
    },
    {
      label: '  其中：与主营业务无关的业务收入',
      currentYear: unrelatedTotalCurrent.value,
      priorYear: unrelatedTotalPrior.value,
      isFormula: true,
      isInput: false,
      formulaTooltip: '=SUM(区段4明细)',
      formulaTooltipPrior: '=SUM(区段4明细-上年)',
    },
    {
      label: '  其中：不具备商业实质的收入',
      currentYear: noSubstanceTotalCurrent.value,
      priorYear: noSubstanceTotalPrior.value,
      isFormula: true,
      isInput: false,
      formulaTooltip: '=SUM(区段5明细)',
      formulaTooltipPrior: '=SUM(区段5明细-上年)',
    },
    {
      label: '扣除项目占营业收入比重',
      currentYear: cr.unable ? null : cr.deductionRatio,
      priorYear: pr.unable ? null : pr.deductionRatio,
      isFormula: true,
      isInput: false,
      formulaTooltip: '=扣除合计÷营业收入',
      formulaTooltipPrior: '=扣除合计(上年)÷营业收入(上年)',
      unable: cr.unable,
      unablePrior: pr.unable,
    },
    {
      label: '扣除后营业收入金额',
      currentYear: cr.revenueAfterDeduction,
      priorYear: pr.revenueAfterDeduction,
      isFormula: true,
      isInput: false,
      formulaTooltip: '=营业收入-扣除合计',
      formulaTooltipPrior: '=营业收入(上年)-扣除合计(上年)',
    },
  ]
})

// ─── 区段6: 其他核查事项 ─────────────────────────────────────────────────────

const otherMatters = ref('')
const auditConclusion = ref('')

// Watch 披露文本 → 发布 disclosure:note-text-updated（Req 8.2）+ 持久化
watch(auditConclusion, (val) => {
  if (val) onDisclosureTextChange(val, 'S20-conclusion')
  if (!hydrating) persistResponse(CONCLUSION_ID, auditConclusion.value)
})
watch(otherMatters, (val) => {
  if (val) onDisclosureTextChange(val, 'S20-other-matters')
  if (!hydrating) persistResponse(OTHER_MATTERS_ID, otherMatters.value)
})

// ─── 动态行操作 ──────────────────────────────────────────────────────────────

async function addUnrelatedRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入收入项目名称', '新增与主营无关收入', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：房屋租赁收入',
    })
    if (value) {
      unrelatedRows.push({ name: value, currentYear: 0, priorYear: 0, reason: '' })
    }
  } catch {
    // cancelled
  }
}

function removeUnrelatedRow(index: number) {
  unrelatedRows.splice(index, 1)
}

async function addNoSubstanceRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入收入项目名称', '新增不具备商业实质收入', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：关联方无商业实质交易',
    })
    if (value) {
      noSubstanceRows.push({ name: value, currentYear: 0, priorYear: 0, reason: '' })
    }
  } catch {
    // cancelled
  }
}

function removeNoSubstanceRow(index: number) {
  noSubstanceRows.splice(index, 1)
}

// ─── AI辅助（Req 8.1 — AI 辅助生成披露文本） ────────────────────────────────

async function handleAiAssist(section: string) {
  await generateDisclosureWithAi(section, {
    revenue: currentResult.value.revenue,
    deductionTotal: currentResult.value.deductionTotal,
    deductionRatio: currentResult.value.deductionRatio,
    revenueAfterDeduction: currentResult.value.revenueAfterDeduction,
    isApplicable: isApplicable.value,
  })
}

// ─── 输入变更 → 自动重算（公式引擎是 computed，自动） ─────────────────────────

function onInputChange() {
  // 披露内容联动 — 当扣除数据变更时同步发布事件
  publishDisclosureNoteUpdated('deduction-summary', JSON.stringify({
    revenue: currentResult.value.revenue,
    deductionTotal: currentResult.value.deductionTotal,
    revenueAfterDeduction: currentResult.value.revenueAfterDeduction,
  }))
  // computed 属性自动 reactive，此处可用于触发保存
}

// ─── 复核对话 ────────────────────────────────────────────────────────────────

const reviewDialogVisible = ref(false)
const reviewDialogSectionId = ref('')
const reviewDialogSectionLabel = ref('')

function openReviewDialog(sectionId: string, sectionLabel?: string): void {
  reviewDialogSectionId.value = sectionId
  reviewDialogSectionLabel.value = sectionLabel || sectionId
  reviewDialogVisible.value = true
}

function handleOpenReview(sectionId: string, sectionLabel: string) {
  openReviewDialog(sectionId, sectionLabel)
}

provide('openReviewDialog', openReviewDialog)

// ─── 版本追踪 ────────────────────────────────────────────────────────────────

const versionTrailRef = ref<any>(null)

function openVersionHistory() {
  versionTrailRef.value?.open?.()
}

function scheduleAutoSnapshot() {
  // 自动快照逻辑（保存后触发）
}

provide('scheduleAutoSnapshot', scheduleAutoSnapshot)
provide('openVersionHistory', openVersionHistory)

// ─── selfLoad ────────────────────────────────────────────────────────────────

/** 合并一个 responses 对象（{item_id: {...}}）到目标 Map */
function _mergeResponses(map: Map<string, any>, src: any): void {
  if (!src || typeof src !== 'object') return
  // 注入权威 item_id：dict 值缺 item_id 时以键补齐（否则保存 items 缺 item_id 触发 422）；v 自带 item_id 则以其为准
  for (const [k, v] of Object.entries(src)) map.set(k, (v && typeof v === 'object' && !Array.isArray(v)) ? { item_id: k, ...v } : { item_id: k, remark: v })
}

/** 用 allResponses 中的存储值恢复本页可编辑状态（明细行/说明/结论） */
function _hydrateFromResponses(): void {
  hydrating = true
  const unrelated = parseResponseValue(allResponses.value, UNRELATED_ID)
  if (Array.isArray(unrelated)) unrelatedRows.splice(0, unrelatedRows.length, ...unrelated)
  const noSub = parseResponseValue(allResponses.value, NO_SUBSTANCE_ID)
  if (Array.isArray(noSub)) noSubstanceRows.splice(0, noSubstanceRows.length, ...noSub)
  const om = parseResponseValue(allResponses.value, OTHER_MATTERS_ID)
  if (typeof om === 'string') otherMatters.value = om
  const conc = parseResponseValue(allResponses.value, CONCLUSION_ID)
  if (typeof conc === 'string') auditConclusion.value = conc
  nextTick(() => { hydrating = false })
}

/**
 * 当 htmlData 为 null（bundle 内嵌场景），自行调 render-config 加载数据。
 * 合并 render 策略输出的 responses_snapshot（S20 render 实际输出键）到 allResponses，
 * 恢复本页可编辑状态（此前丢弃 → 刷新丢失，本次修复）。
 */
async function selfLoad() {
  try {
    if (props.htmlData) {
      const map = new Map<string, any>()
      _mergeResponses(map, props.htmlData.responses_snapshot)
      _mergeResponses(map, props.htmlData.allResponses)
      _mergeResponses(map, props.htmlData.checklist_responses)
      if (map.size > 0) allResponses.value = map
    } else {
      const res = await http.get(`/api/workpapers/${props.wpId}/render-config`, { _silent: true } as any)
      const data = res.data?.data || res.data
      if (data?.sheets && Array.isArray(data.sheets)) {
        const map = new Map<string, any>()
        for (const sheet of data.sheets) {
          _mergeResponses(map, sheet.html_data?.responses_snapshot)
          _mergeResponses(map, sheet.html_data?.allResponses)
          _mergeResponses(map, sheet.html_data?.checklist_responses)
        }
        if (map.size > 0) allResponses.value = map
      }
    }
    if (allResponses.value.size > 0) _hydrateFromResponses()
  } catch (err) {
    console.warn('[GtS20RevenueDeduction] selfLoad failed:', err)
  }

  isLoading.value = false
}

provide('reloadWorkpaperData', selfLoad)

// ─── 持久化（防抖 800ms 批量 PUT；乐观更新 Map；只读跳过） ────────────────────

const UNRELATED_ID = 'S20-unrelated-rows'
const NO_SUBSTANCE_ID = 'S20-no-substance-rows'
const OTHER_MATTERS_ID = 'S20-other-matters'
const CONCLUSION_ID = 'S20-conclusion'

/** hydrating 期间抑制 watch 回写，避免 seed 触发无谓 PUT */
let hydrating = false

const _saveTimers = new Map<string, ReturnType<typeof setTimeout>>()
function persistResponse(itemId: string, value: any): void {
  if (!itemId || !props.wpId) return
  const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
  const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
  const updated = { ...existing, item_id: itemId, remark: strVal }
  allResponses.value.set(itemId, updated)
  if (isReadonly.value) return
  const prev = _saveTimers.get(itemId)
  if (prev) clearTimeout(prev)
  _saveTimers.set(itemId, setTimeout(() => {
    _saveTimers.delete(itemId)
    http.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId,
      items: [{ item_id: itemId, conclusion: updated.conclusion ?? null, remark: updated.remark ?? null }],
    }).catch((err: unknown) => console.warn('[GtS20RevenueDeduction] persistResponse failed:', itemId, err))
  }, 800))
}

provide('saveResponse', persistResponse)
provide('allResponses', allResponses)

// 明细行 / 说明 / 结论变更 → 持久化（hydrating 期间跳过）
watch(unrelatedRows, () => { if (!hydrating) persistResponse(UNRELATED_ID, [...unrelatedRows]) }, { deep: true })
watch(noSubstanceRows, () => { if (!hydrating) persistResponse(NO_SUBSTANCE_ID, [...noSubstanceRows]) }, { deep: true })

onBeforeUnmount(() => {
  for (const t of _saveTimers.values()) clearTimeout(t)
  _saveTimers.clear()
})

// ─── EventBus + 披露联动（Task 5.2: Req 7.3, 8.1, 8.2, 8.3） ───────────────

import { useSEstimateDisclosureEventBus } from '../composables/useSEstimateDisclosureEventBus'

const {
  disclosureText: s20DisclosureText,
  aiLoading: s20AiLoading,
  saveAndPublish,
  publishDisclosureNoteUpdated,
  onDisclosureTextChange,
  generateDisclosureWithAi,
} = useSEstimateDisclosureEventBus({
  wpCode: 'S20',
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  onRefresh: () => selfLoad(),
  isReadonly,
})

// provide 给子组件用
provide('sEstimateDisclosure', {
  disclosureText: s20DisclosureText,
  aiLoading: s20AiLoading,
  saveAndPublish,
  publishDisclosureNoteUpdated,
  onDisclosureTextChange,
  generateDisclosureWithAi,
})

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  selfLoad()
})
</script>

<style scoped>
.s20-revenue-deduction {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.loading-container {
  padding: 24px;
}

.s20-toolbar {
  margin-bottom: 8px;
  display: flex;
  gap: 8px;
  align-items: center;
}

.s20-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.audit-objective-text {
  font-size: var(--wp-font-size, 13px);
  line-height: 1.6;
}

/* ─── 顶部蓝色渐变引导区 ─── */
.s20-guide-banner {
  background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%);
  border: 1px solid #b3d8f0;
  border-radius: 8px;
  padding: 12px 16px;
}

.guide-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 24px;
}

.guide-step {
  display: flex;
  align-items: flex-start;
  gap: 6px;
}

.step-num {
  font-weight: 700;
  color: #1890ff;
  font-size: 14px;
  flex-shrink: 0;
}

.step-text {
  color: #333;
  line-height: 1.4;
}

/* ─── 方法论上下文（琥珀色左边线） ─── */
.segment-methodology {
  margin-bottom: 0;
}

.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 12px 16px;
  border-radius: 0 6px 6px 0;
}

.methodology-title {
  font-weight: 700;
  color: #b88230;
  margin: 0 0 8px 0;
  font-size: 14px;
}

.methodology-text {
  color: #664d03;
  margin: 0 0 8px 0;
  line-height: 1.6;
}

.methodology-note {
  color: #856404;
  margin: 0;
  font-size: 12px;
  font-style: italic;
}

/* ─── 区段通用 ─── */
.s20-segment {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 12px 16px;
  background: #fff;
}

.segment-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.segment-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin: 0;
  flex: 1;
}

.segment-actions {
  display: flex;
  gap: 4px;
  align-items: center;
}

.data-source-hint {
  font-size: 12px;
  color: #909399;
  white-space: nowrap;
}

/* ─── 表格 ─── */
.s20-table {
  font-size: var(--wp-font-size, 13px);
}

.s20-table :deep(.el-table__cell) {
  font-size: var(--wp-font-size, 13px);
  padding: 6px 8px;
}

/* ─── 公式单元格 ─── */
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  color: #303133;
  padding-bottom: 1px;
}

/* ─── 金额输入 ─── */
.amount-input {
  width: 100%;
}

.amount-input :deep(.el-input__inner) {
  text-align: right;
}

/* ─── 合计行 ─── */
.subtotal-row {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  margin-top: 8px;
  gap: 16px;
}

.subtotal-label {
  font-weight: 600;
  min-width: 60px;
}

.subtotal-value {
  min-width: 120px;
  text-align: right;
}

/* ─── 适用结论 ─── */
.applicability-conclusion {
  margin-top: 12px;
  text-align: center;
}

/* ─── 结论区 ─── */
.conclusion-card {
  border-color: #dcdfe6;
}

.conclusion-card :deep(.el-card__header) {
  padding: 10px 16px;
  background: #f5f7fa;
}

.conclusion-text {
  white-space: pre-wrap;
  color: #606266;
  line-height: 1.6;
}

/* ─── 编制提示 ─── */
.edit-hint {
  margin-top: 12px;
  font-size: 12px;
  color: #909399;
}

.edit-hint summary {
  cursor: pointer;
  color: #606266;
  font-weight: 500;
}

.edit-hint p {
  margin: 4px 0;
  padding-left: 16px;
}
</style>
