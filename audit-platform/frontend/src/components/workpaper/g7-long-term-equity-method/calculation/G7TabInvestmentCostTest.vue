<!--
  G7TabInvestmentCostTest.vue — G7-13 投资成本测试（68行×17列→2区段Tab+虚拟滚动）

  2区段Tab切换（el-segmented）：
  - Tab1: 初始计量(9列): 被投资单位|投资日期|合并/非合并(下拉)|支付对价|直接相关费用|初始投资成本(公式)|净资产FV|享有份额(公式)|差额(公式)
  - Tab2: 商誉计算+调整(8列): 被投资单位|差额性质(自动判断:正=商誉绿色/负=营业外蓝色)|会计处理|FV调整明细(textarea)|调整后净资产|调整后享有份额|审计结论(下拉)|索引

  方法论上下文区域（琥珀色左边线+浅黄背景：CAS2投资成本判断规则）
  68行虚拟滚动 + 行同步 + 动态行增删
  底部审计结论textarea(AI辅助 cost-test-conclusion) + details编制提示折叠
  公式列：虚线下划线 + cursor:help + tooltip显示公式来源

  Spec: .kiro/specs/g7-long-term-equity-method/ Task 6.1
  Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 7.4, 7.5
-->
<template>
  <div class="g7-tab-investment-cost-test">
    <!-- 方法论上下文区域（琥珀色左边线+浅黄背景） -->
    <div class="methodology-context">
      <p class="methodology-title">CAS2 投资成本判断规则：</p>
      <ul class="methodology-list">
        <li>初始投资成本 &gt; 享有可辨认净资产FV份额 → 差额确认为<strong>商誉</strong>（不调整）</li>
        <li>初始投资成本 &lt; 享有可辨认净资产FV份额 → 差额计入<strong>营业外收入</strong>（调整初始成本）</li>
        <li>被投资方净资产公允价值需逐项辨认、调整（资产评估/审计确认）</li>
      </ul>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实长期股权投资初始投资成本的计量，验证商誉或营业外收入的确认是否符合 CAS2。"
      class="objective-alert"
    />

    <!-- 顶部工具栏 -->
    <div class="section-head">
      <h3 class="sheet-title">G7-13 合营联营企业投资成本测试表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
          + 被投资单位
        </el-button>
        <el-dropdown trigger="click" size="small" @command="handleDropdownCommand">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export">导出数据</el-dropdown-item>
              <el-dropdown-item command="import">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="openReviewDialog('G7-13-cost-test')">💬复核</el-button>
      </div>
    </div>

    <!-- 工具栏：索引 chip + 行数 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G7-13" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <!-- 2区段Tab切换 -->
    <el-segmented v-model="activeTab" :options="segmentOptions" size="small" class="segment-bar" />

    <!-- 表格（单一实例，列按Tab切换，68行虚拟滚动） -->
    <el-table
      :data="rows"
      border
      size="small"
      max-height="580"
      highlight-current-row
      row-key="id"
      class="cost-test-table"
      @current-change="onCurrentChange"
    >
      <!-- 序号列（始终显示） -->
      <el-table-column label="序号" width="55" align="center" fixed>
        <template #default="{ row }">{{ row.seq }}</template>
      </el-table-column>

      <!-- 被投资单位列（始终显示作为锚定列） -->
      <el-table-column label="被投资单位" width="150" fixed>
        <template #default="{ row }">
          <span class="investee-name">{{ row.investeeName }}</span>
        </template>
      </el-table-column>

      <!-- ═══ Tab1: 初始计量(9列，含序号+被投资单位共9列显示) ═══ -->
      <template v-if="activeTab === 'tab1'">
        <el-table-column label="投资日期" min-width="130">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" :model-value="row.investDate" size="small"
              type="date" value-format="YYYY-MM-DD" style="width:100%"
              @update:model-value="(v: string) => updateField(row.id, 'investDate', v)" />
            <span v-else>{{ row.investDate }}</span>
          </template>
        </el-table-column>

        <el-table-column label="合并/非合并" min-width="110">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.mergeType" size="small" style="width:100%"
              @change="(v: string) => updateField(row.id, 'mergeType', v)">
              <el-option value="合并" label="合并" />
              <el-option value="非合并" label="非合并" />
            </el-select>
            <span v-else>{{ row.mergeType }}</span>
          </template>
        </el-table-column>

        <el-table-column label="支付对价" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.consideration" size="small"
              :controls="false" :precision="2" class="compact-num"
              @change="(v: number) => updateFieldWithRecalc(row.id, 'consideration', v)" />
            <span v-else>{{ fmtNum(row.consideration) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="直接相关费用" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.directCosts" size="small"
              :controls="false" :precision="2" class="compact-num"
              @change="(v: number) => updateFieldWithRecalc(row.id, 'directCosts', v)" />
            <span v-else>{{ fmtNum(row.directCosts) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="初始投资成本" min-width="130" align="right">
          <template #default="{ row }">
            <el-tooltip content="初始投资成本 = 支付对价 + 直接相关费用" placement="top">
              <span class="formula-cell">{{ fmtNum(row.initialCost) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column label="净资产公允价值" min-width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.netAssetFairValue" size="small"
              :controls="false" :precision="2" class="compact-num"
              @change="(v: number) => updateFieldWithRecalc(row.id, 'netAssetFairValue', v)" />
            <span v-else>{{ fmtNum(row.netAssetFairValue) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="享有份额" min-width="120" align="right">
          <template #default="{ row }">
            <el-tooltip content="享有份额 = 净资产公允价值 × 持股比例" placement="top">
              <span class="formula-cell">{{ fmtNum(row.shareOfNetAssets) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column label="差额" min-width="120" align="right">
          <template #default="{ row }">
            <el-tooltip content="差额 = 初始投资成本 - 享有份额（正=商誉,负=营业外收入）" placement="top">
              <span class="formula-cell" :class="differenceClass(row.difference)">
                {{ fmtNum(row.difference) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ Tab2: 商誉计算+调整(8列，含被投资单位共8) ═══ -->
      <template v-if="activeTab === 'tab2'">
        <el-table-column label="差额性质" min-width="120" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.difference > 0" type="success" size="small">商誉</el-tag>
            <el-tag v-else-if="row.difference < 0" type="primary" size="small">营业外收入</el-tag>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>

        <el-table-column label="会计处理" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.accountingTreatment" size="small"
              @change="(v: string) => updateField(row.id, 'accountingTreatment', v)" />
            <span v-else>{{ row.accountingTreatment }}</span>
          </template>
        </el-table-column>

        <el-table-column label="FV调整明细" min-width="200">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" type="textarea" :model-value="row.fvAdjustmentDetail"
              :autosize="{ minRows: 1, maxRows: 3 }" size="small"
              @change="(v: string) => updateField(row.id, 'fvAdjustmentDetail', v)" />
            <span v-else class="multiline-cell">{{ row.fvAdjustmentDetail }}</span>
          </template>
        </el-table-column>

        <el-table-column label="调整后净资产" min-width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.adjustedNetAssets" size="small"
              :controls="false" :precision="2" class="compact-num"
              @change="(v: number) => updateField(row.id, 'adjustedNetAssets', v)" />
            <span v-else>{{ fmtNum(row.adjustedNetAssets) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="调整后享有份额" min-width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.adjustedShareOfNetAssets" size="small"
              :controls="false" :precision="2" class="compact-num"
              @change="(v: number) => updateField(row.id, 'adjustedShareOfNetAssets', v)" />
            <span v-else>{{ fmtNum(row.adjustedShareOfNetAssets) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="审计结论" min-width="150">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.auditConclusion" size="small" style="width:100%"
              @change="(v: string) => updateField(row.id, 'auditConclusion', v)">
              <el-option value="无差异" label="无差异" />
              <el-option value="存在差异-可接受" label="存在差异-可接受" />
              <el-option value="存在差异-需调整" label="存在差异-需调整" />
            </el-select>
            <span v-else>{{ row.auditConclusion }}</span>
          </template>
        </el-table-column>

        <el-table-column label="索引" width="90" align="center">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.indexRef" size="small"
              @change="(v: string) => updateField(row.id, 'indexRef', v)" />
            <span v-else>{{ row.indexRef }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- 操作列（删除） -->
      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-popconfirm :title="`确认删除「${row.investeeName}」?`" @confirm="removeRow(row.id)">
            <template #reference>
              <el-button type="danger" link size="small">✕</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计说明 -->
    <el-card class="conclusion-card" shadow="never">
      <template #header>
        <div class="conclusion-header">
          <span>审计说明</span>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：可概述所执行程序、测试情况及结果，拟调整/未调整事项及其影响。"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 底部：审计结论 el-card + AI辅助按钮 -->
    <el-card class="conclusion-card" shadow="never">
      <template #header>
        <div class="conclusion-header">
          <span>审计结论</span>
          <el-button size="small" :disabled="isReadonly" @click="handleAiConclusion">
            🤖 AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="对投资成本测试结果的综合评价（商誉/营业外收入确认是否合理）..."
        @change="persistRows"
      />
    </el-card>

    <!-- 编制提示 details 折叠 -->
    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>初始投资成本 = 支付对价 + 直接相关费用（审计/律师/评估等）</li>
        <li>享有份额 = 被投资方可辨认净资产公允价值 × 投资方持股比例</li>
        <li>差额为正（初始成本 > 享有份额）：差额确认为商誉，不调整初始投资成本</li>
        <li>差额为负（初始成本 < 享有份额）：差额计入营业外收入，同时调增初始投资成本</li>
        <li>合并取得的长期股权投资，初始投资成本按合并对价确定</li>
        <li>非合并取得的长期股权投资，支付的对价+直接费用均计入初始成本</li>
        <li>被投资方净资产公允价值需参照评估报告逐项辨认调整</li>
        <li>持股比例从G7-4被投资单位基本信息自动带入</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G7TabInvestmentCostTest — G7-13 投资成本测试
 *
 * Spec: .kiro/specs/g7-long-term-equity-method/
 * Task: 6.1
 *
 * 68行×17列→2区段Tab：
 * - Tab1 初始计量(9列)：calcInvestmentCost / calcShareOfNetAssets / calcGoodwill
 * - Tab2 商誉计算+调整(8列)：差额性质自动判断（正=商誉绿色/负=营业外蓝色）
 * - 方法论上下文（琥珀色左边线+浅黄背景）
 * - 68行虚拟滚动 max-height
 * - 行同步：Tab切换保持行索引
 * - 动态行增删：ElMessageBox.prompt
 * - 底部审计结论textarea(AI辅助) + details编制提示
 *
 * Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 7.4, 7.5
 */
import { ref, reactive, inject, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  calcInvestmentCost,
  calcShareOfNetAssets,
  calcGoodwill,
} from '../../composables/useG7EquityMethodFormulaEngine'
import { G7_13_ROWS_KEY } from '../../composables/g7EquityMethodCrossSheet'
import GtIndexChip from '../../GtIndexChip.vue'
import { useG7EquityMethodFormData } from '../../composables/useG7EquityMethodFormData'
import type { InvestmentCostTestRow } from '../../composables/useG7EquityMethodFormData'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const isReadonly = computed(() => props.readonly ?? false)

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// ─── 2区段Tab ────────────────────────────────────────────────────────────────

type TabKey = 'tab1' | 'tab2'
const activeTab = ref<TabKey>('tab1')

const segmentOptions = [
  { label: '初始计量(9)', value: 'tab1' },
  { label: '商誉计算+调整(8)', value: 'tab2' },
]

// ─── 行同步: selectedRowIndex ────────────────────────────────────────────────

const selectedRowIndex = ref<number>(-1)

function onCurrentChange(row: InvestmentCostTestRow | null) {
  if (row) {
    const idx = rows.findIndex(r => r.id === row.id)
    selectedRowIndex.value = idx
  }
}

// ─── 持股比例映射（从G7-4 BasicInfo数据获取） ────────────────────────────────

const ratioMap = reactive<Record<string, number>>({})

// ─── 行数据 ──────────────────────────────────────────────────────────────────

const rows = reactive<InvestmentCostTestRow[]>([])
const conclusion = ref<string>('')

// ─── 审计说明持久化（checklist_responses，conclusion:null） ────────────────────

const auditFormData = useG7EquityMethodFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
const AUDIT_NOTE_KEY = 'G7-13-audit-note'
const auditNote = ref('')

function saveAuditNote(val: string): void {
  if (isReadonly.value) return
  auditNote.value = val
  auditFormData.debouncedSave(AUDIT_NOTE_KEY, { remark: val, conclusion: null })
}

function persistRows(): void {
  if (isReadonly.value) return
  auditFormData.debouncedSave(G7_13_ROWS_KEY, {
    conclusion: JSON.stringify({ rows: [...rows], conclusion: conclusion.value }),
    remark: null,
  })
}

function loadRowsFromChecklist(): boolean {
  const saved = auditFormData.data.value.get(G7_13_ROWS_KEY)
  const parsed = (() => {
    try {
      return saved?.conclusion ? JSON.parse(String(saved.conclusion)) : null
    } catch {
      return null
    }
  })()
  const rawRows = Array.isArray(parsed?.rows) ? parsed.rows : Array.isArray(parsed) ? parsed : null
  if (!rawRows?.length) return false
  rows.length = 0
  for (let i = 0; i < rawRows.length; i++) {
    const raw = rawRows[i]
    const row: InvestmentCostTestRow = {
      ...createEmptyRow(i + 1, raw.investeeName || ''),
      ...raw,
      seq: i + 1,
      id: raw.id || crypto.randomUUID(),
    }
    rows.push(row)
    recalcRow(row)
  }
  if (typeof parsed?.conclusion === 'string') conclusion.value = parsed.conclusion
  return true
}

function createEmptyRow(seq: number, investeeName: string): InvestmentCostTestRow {
  return {
    id: crypto.randomUUID(),
    seq,
    investeeName,
    investDate: '',
    mergeType: '非合并',
    consideration: 0,
    directCosts: 0,
    initialCost: 0,
    netAssetFairValue: 0,
    shareOfNetAssets: 0,
    difference: 0,
    differenceNature: '商誉',
    accountingTreatment: '',
    fvAdjustmentDetail: '',
    adjustedNetAssets: 0,
    adjustedShareOfNetAssets: 0,
    auditConclusion: '无差异',
    indexRef: '',
  }
}

// ─── 公式重算（核心） ────────────────────────────────────────────────────────

function recalcRow(row: InvestmentCostTestRow): void {
  // 获取该被投资单位的持股比例
  const ratio = ratioMap[row.investeeName] ?? 0

  // P1: 初始投资成本 = 支付对价 + 直接相关费用
  row.initialCost = calcInvestmentCost(row.consideration, row.directCosts)

  // P2: 享有份额 = 净资产FV × 持股比例
  row.shareOfNetAssets = calcShareOfNetAssets(row.netAssetFairValue, ratio)

  // P3: 差额 = 初始成本 - 享有份额（正=商誉，负=营业外收入）
  row.difference = calcGoodwill(row.initialCost, row.shareOfNetAssets)

  // 差额性质自动判断
  row.differenceNature = row.difference >= 0 ? '商誉' : '营业外收入'
}

// ─── 字段更新 ────────────────────────────────────────────────────────────────

function updateField(id: string, field: keyof InvestmentCostTestRow, value: any) {
  const row = rows.find(r => r.id === id)
  if (row) {
    ;(row as any)[field] = value
    persistRows()
  }
}

function updateFieldWithRecalc(id: string, field: keyof InvestmentCostTestRow, value: any) {
  const row = rows.find(r => r.id === id)
  if (row) {
    ;(row as any)[field] = value ?? 0
    recalcRow(row)
    persistRows()
  }
}

// ─── 动态行增删（ElMessageBox.prompt + 名称唯一性校验） ──────────────────────

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入被投资单位名称', '新增被投资单位', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '被投资单位名称不能为空',
      inputValidator: (val: string) => {
        if (!val?.trim()) return '被投资单位名称不能为空'
        const exists = rows.some(r => r.investeeName === val.trim())
        if (exists) return `「${val.trim()}」已存在，请勿重复添加`
        return true
      },
    })
    if (value?.trim()) {
      const newRow = createEmptyRow(rows.length + 1, value.trim())
      rows.push(newRow)
      persistRows()
      ElMessage.success(`已添加「${value.trim()}」`)
    }
  } catch {
    // 用户取消
  }
}

function removeRow(id: string) {
  const idx = rows.findIndex(r => r.id === id)
  if (idx >= 0) {
    rows.splice(idx, 1)
    rows.forEach((r, i) => { r.seq = i + 1 })
    persistRows()
  }
}

// ─── AI生成审计结论 ──────────────────────────────────────────────────────────

function handleAiConclusion() {
  ElMessage.info('AI生成投资成本测试结论(cost-test-conclusion)将在AI模块完成后启用')
}

// ─── 导入导出 ────────────────────────────────────────────────────────────────

async function handleDropdownCommand(command: string) {
  if (command === 'template') {
    ElMessage.info('导出模板功能将在后续集成')
  } else if (command === 'export') {
    ElMessage.info('导出数据功能将在后续集成')
  } else if (command === 'import') {
    ElMessage.info('导入数据功能将在后续集成')
  }
}

// ─── 差额颜色样式 ───────────────────────────────────────────────────────────

function differenceClass(diff: number): string {
  if (diff > 0) return 'diff-goodwill'
  if (diff < 0) return 'diff-bargain'
  return ''
}

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function fmtNum(v: unknown): string {
  if (v === 0) return '0.00'
  if (typeof v === 'number') {
    return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return String(v ?? '')
}

// ─── 数据加载 ────────────────────────────────────────────────────────────────

function loadFromHtmlData(data: Record<string, any> | null): void {
  if (!data) return
  rows.length = 0

  const costTestData = data.investmentCostTest || data
  const rawRows = costTestData?.rows || []
  conclusion.value = costTestData?.conclusion || ''

  // 加载持股比例映射（从basicInfo或传入数据）
  const basicInfo = data.basicInfo || {}
  if (basicInfo.rows && Array.isArray(basicInfo.rows)) {
    for (const bi of basicInfo.rows) {
      if (bi.investeeName && typeof bi.investmentRatio === 'number') {
        ratioMap[bi.investeeName] = bi.investmentRatio
      }
    }
  }

  // 加载行数据
  if (Array.isArray(rawRows) && rawRows.length > 0) {
    for (let i = 0; i < rawRows.length; i++) {
      const raw = rawRows[i]
      const row: InvestmentCostTestRow = {
        ...createEmptyRow(i + 1, raw.investeeName || ''),
        ...raw,
        seq: i + 1,
        id: raw.id || crypto.randomUUID(),
      }
      rows.push(row)
      // 重算公式确保数据一致性
      recalcRow(row)
    }
  }
}

/**
 * 更新持股比例（供父组件跨sheet联动时调用）
 */
function updateRatioMap(investeeName: string, ratio: number): void {
  ratioMap[investeeName] = ratio
  // 重算所有同名行
  rows.filter(r => r.investeeName === investeeName).forEach(recalcRow)
}

/**
 * 导出当前数据（供父组件保存调用）
 */
function getData(): { rows: InvestmentCostTestRow[]; conclusion: string } {
  return { rows: [...rows], conclusion: conclusion.value }
}

defineExpose({ getData, loadFromHtmlData, updateRatioMap })

onMounted(async () => {
  await auditFormData.load()
  const n = auditFormData.data.value.get(AUDIT_NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  if (!loadRowsFromChecklist()) {
    const snapshot = props.htmlData?.responses_snapshot?.[G7_13_ROWS_KEY]
    const snapParsed = (() => {
      try {
        return snapshot?.conclusion ? JSON.parse(String(snapshot.conclusion)) : null
      } catch {
        return null
      }
    })()
    if (Array.isArray(snapParsed?.rows) && snapParsed.rows.length) {
      rows.length = 0
      for (let i = 0; i < snapParsed.rows.length; i++) {
        const raw = snapParsed.rows[i]
        const row: InvestmentCostTestRow = {
          ...createEmptyRow(i + 1, raw.investeeName || ''),
          ...raw,
          seq: i + 1,
          id: raw.id || crypto.randomUUID(),
        }
        rows.push(row)
        recalcRow(row)
      }
      if (typeof snapParsed.conclusion === 'string') conclusion.value = snapParsed.conclusion
    } else {
      loadFromHtmlData(props.htmlData)
    }
  }
})
</script>

<style scoped>
.g7-tab-investment-cost-test { padding: 12px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.tab-toolbar .toolbar-right { display: flex; gap: 6px; align-items: center; }
.tab-toolbar .chip-wrap { display: inline-flex; align-items: center; }

/* 方法论上下文（琥珀色左边线+浅黄背景） */
.methodology-context {
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #fffbeb;
  border-left: 4px solid #f59e0b;
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
  line-height: 1.7;
}
.methodology-title { margin: 0 0 6px; font-weight: 600; color: #92400e; }
.methodology-list { margin: 0; padding-left: 18px; color: #78350f; }
.methodology-list li { margin-bottom: 2px; }

/* 顶部工具栏 */
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; align-items: center; }

/* 区段Tab */
.segment-bar { margin-bottom: 12px; }

/* 表格 */
.cost-test-table { font-size: var(--wp-font-size, 13px); }
.compact-num { width: 100%; }
.investee-name { font-weight: 500; color: #303133; }
.multiline-cell { white-space: pre-wrap; word-break: break-all; font-size: 12px; line-height: 1.4; }
.text-muted { color: #c0c4cc; }

/* 公式列：虚线下划线 + cursor:help */
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 1px;
}

/* 差额颜色 */
.diff-goodwill { color: #67c23a; font-weight: 500; }
.diff-bargain { color: #409eff; font-weight: 500; }

/* 审计结论卡片 */
.conclusion-card { margin-top: 16px; }
.conclusion-header { display: flex; justify-content: space-between; align-items: center; }

/* 编制提示 */
.prep-hint { margin-top: 16px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; font-weight: 500; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; line-height: 1.8; }
</style>
