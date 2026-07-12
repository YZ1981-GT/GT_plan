<!--
  G7TabUnrecognizedLoss.vue — G7-16 未确认投资损失测试表（40行×17列→2区段Tab）

  2区段Tab切换（el-segmented）：
  - Tab1: 长期权益分析(9列): 被投资单位|投资账面|长应收|其他权益|预计负债|合计(公式)|累计亏损|超额亏损(公式)|分配顺序
  - Tab2: 超额亏损分配(8列): 被投资单位|冲减投资|冲减长应收|冲减其他|确认预计负债|未确认损失(公式)|本期变动|审计结论(下拉)

  方法论上下文区域（琥珀色左边线+浅黄背景：CAS2第44条超额亏损抵减顺序）
  超额亏损为0时Tab2全部禁用
  行同步 + 动态行增删
  底部审计结论textarea(AI辅助) + details编制提示折叠

  Spec: .kiro/specs/g7-long-term-equity-method/ Task 8.1
  Requirements: 6.4, 6.7
-->
<template>
  <div class="g7-tab-unrecognized-loss">
    <!-- 方法论上下文区域（琥珀色左边线+浅黄背景） -->
    <div class="methodology-context">
      <p class="methodology-title">超额亏损抵减顺序（CAS2第44条）：</p>
      <ul class="methodology-list">
        <li>① 先冲减<strong>长期股权投资</strong>账面价值</li>
        <li>② 再冲减<strong>长期应收款</strong>等其他实质长期权益</li>
        <li>③ 最后确认<strong>预计负债</strong>（如有额外义务）</li>
        <li>超出①②③的部分为<strong>未确认投资损失</strong>（备查簿登记）</li>
      </ul>
    </div>

    <!-- 顶部工具栏 -->
    <div class="section-head">
      <h3 class="sheet-title">G7-16 未确认投资损失测试表</h3>
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
        <el-button size="small" @click="openReviewDialog('G7-16-unrecognized-loss')">💬复核</el-button>
      </div>
    </div>

    <!-- 2区段Tab切换 -->
    <el-segmented v-model="activeTab" :options="segmentOptions" size="small" class="segment-bar" />

    <!-- 超额亏损为0时Tab2禁用提示 -->
    <el-alert
      v-if="activeTab === 'tab2' && allExcessLossZero"
      type="info"
      :closable="false"
      show-icon
      class="tab2-disabled-alert"
    >
      所有被投资单位超额亏损均为0，无需分配超额亏损。Tab2数据已禁用。
    </el-alert>

    <!-- 表格 -->
    <el-table
      :data="rows"
      border
      size="small"
      max-height="520"
      highlight-current-row
      row-key="id"
      class="loss-table"
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

      <!-- ═══ Tab1: 长期权益分析(9列，含序号+被投资单位共9列显示) ═══ -->
      <template v-if="activeTab === 'tab1'">
        <el-table-column label="投资账面" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.investmentBookValue" size="small"
              :controls="false" :precision="2" class="compact-num"
              @change="(v: number) => updateFieldWithRecalc(row.id, 'investmentBookValue', v)" />
            <span v-else>{{ fmtNum(row.investmentBookValue) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="长期应收款" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.longTermReceivable" size="small"
              :controls="false" :precision="2" class="compact-num"
              @change="(v: number) => updateFieldWithRecalc(row.id, 'longTermReceivable', v)" />
            <span v-else>{{ fmtNum(row.longTermReceivable) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="其他实质长期权益" min-width="140" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.otherLongTermEquity" size="small"
              :controls="false" :precision="2" class="compact-num"
              @change="(v: number) => updateFieldWithRecalc(row.id, 'otherLongTermEquity', v)" />
            <span v-else>{{ fmtNum(row.otherLongTermEquity) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="预计负债" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.estimatedLiability" size="small"
              :controls="false" :precision="2" class="compact-num"
              @change="(v: number) => updateFieldWithRecalc(row.id, 'estimatedLiability', v)" />
            <span v-else>{{ fmtNum(row.estimatedLiability) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="合计长期权益" min-width="130" align="right">
          <template #default="{ row }">
            <el-tooltip content="合计 = 投资账面 + 长应收 + 其他权益 + 预计负债" placement="top">
              <span class="formula-cell">{{ fmtNum(row.totalLongTermEquity) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column label="累计亏损" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.cumulativeLoss" size="small"
              :controls="false" :precision="2" class="compact-num"
              @change="(v: number) => updateFieldWithRecalc(row.id, 'cumulativeLoss', v)" />
            <span v-else>{{ fmtNum(row.cumulativeLoss) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="超额亏损" min-width="120" align="right">
          <template #default="{ row }">
            <el-tooltip content="超额亏损 = MAX(0, 累计亏损 - 合计长期权益)" placement="top">
              <span class="formula-cell" :class="{ 'excess-highlight': row.excessLoss > 0 }">
                {{ fmtNum(row.excessLoss) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column label="分配顺序说明" min-width="180">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.allocationOrder" size="small"
              @change="(v: string) => updateField(row.id, 'allocationOrder', v)" />
            <span v-else>{{ row.allocationOrder }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ Tab2: 超额亏损分配(8列，含被投资单位共8列) ═══ -->
      <template v-if="activeTab === 'tab2'">
        <el-table-column label="冲减投资" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !isTab2Disabled(row)" :model-value="row.reduceInvestment" size="small"
              :controls="false" :precision="2" class="compact-num"
              @change="(v: number) => updateFieldWithRecalc(row.id, 'reduceInvestment', v)" />
            <span v-else :class="{ 'text-disabled': isTab2Disabled(row) }">{{ fmtNum(row.reduceInvestment) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="冲减长应收" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !isTab2Disabled(row)" :model-value="row.reduceLongTermReceivable" size="small"
              :controls="false" :precision="2" class="compact-num"
              @change="(v: number) => updateFieldWithRecalc(row.id, 'reduceLongTermReceivable', v)" />
            <span v-else :class="{ 'text-disabled': isTab2Disabled(row) }">{{ fmtNum(row.reduceLongTermReceivable) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="冲减其他权益" min-width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !isTab2Disabled(row)" :model-value="row.reduceOtherEquity" size="small"
              :controls="false" :precision="2" class="compact-num"
              @change="(v: number) => updateFieldWithRecalc(row.id, 'reduceOtherEquity', v)" />
            <span v-else :class="{ 'text-disabled': isTab2Disabled(row) }">{{ fmtNum(row.reduceOtherEquity) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="确认预计负债" min-width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !isTab2Disabled(row)" :model-value="row.recognizeEstimatedLiability" size="small"
              :controls="false" :precision="2" class="compact-num"
              @change="(v: number) => updateFieldWithRecalc(row.id, 'recognizeEstimatedLiability', v)" />
            <span v-else :class="{ 'text-disabled': isTab2Disabled(row) }">{{ fmtNum(row.recognizeEstimatedLiability) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="未确认损失" min-width="130" align="right">
          <template #default="{ row }">
            <el-tooltip content="未确认损失 = 超额亏损 - 冲减投资 - 冲减长应收 - 冲减其他 - 确认预计负债" placement="top">
              <span class="formula-cell" :class="{ 'text-disabled': isTab2Disabled(row) }">
                {{ fmtNum(row.unrecognizedLoss) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column label="本期变动" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !isTab2Disabled(row)" :model-value="row.currentChange" size="small"
              :controls="false" :precision="2" class="compact-num"
              @change="(v: number) => updateField(row.id, 'currentChange', v)" />
            <span v-else :class="{ 'text-disabled': isTab2Disabled(row) }">{{ fmtNum(row.currentChange) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="审计结论" min-width="130">
          <template #default="{ row }">
            <el-select v-if="!isReadonly && !isTab2Disabled(row)" :model-value="row.auditConclusion" size="small" style="width:100%"
              @change="(v: string) => updateField(row.id, 'auditConclusion', v)">
              <el-option value="合理" label="合理" />
              <el-option value="基本合理" label="基本合理" />
              <el-option value="不合理" label="不合理" />
            </el-select>
            <span v-else :class="{ 'text-disabled': isTab2Disabled(row) }">{{ row.auditConclusion }}</span>
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
        placeholder="对未确认投资损失测试结果的综合评价（超额亏损分配是否合理）..."
      />
    </el-card>

    <!-- 编制提示 details 折叠 -->
    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>超额亏损 = MAX(0, 累计亏损 - 合计长期权益)，即亏损超过可承受范围的部分</li>
        <li>合计长期权益 = 投资账面 + 长期应收款 + 其他实质长期权益 + 预计负债</li>
        <li>抵减顺序：先冲投资账面→再冲长应收→最后确认预计负债</li>
        <li>超过上述各项可抵减部分 = 未确认投资损失（账外备查簿登记）</li>
        <li>被投资方实现净利润时，按相反顺序恢复（先恢复预计负债→恢复长应收→恢复投资）</li>
        <li>超额亏损为0时，无需进行Tab2分配（系统自动禁用Tab2输入）</li>
        <li>对于合营/联营企业，按CAS2第44条处理超额亏损</li>
        <li>长期应收款需为"实质上构成对被投资单位净投资"的部分</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G7TabUnrecognizedLoss — G7-16 未确认投资损失测试表
 *
 * Spec: .kiro/specs/g7-long-term-equity-method/
 * Task: 8.1
 *
 * 40行×17列→2区段Tab：
 * - Tab1 长期权益分析(9列)：合计(公式)=各项之和 / 超额亏损(公式)=MAX(0,累计亏损-合计)
 * - Tab2 超额亏损分配(8列)：未确认损失(公式)=超额-各项冲减
 * - 方法论上下文（琥珀色：CAS2第44条超额亏损抵减顺序）
 * - 超额亏损为0时Tab2全部禁用
 * - 行同步 + 动态行增删
 *
 * Requirements: 6.4, 6.7
 */
import { ref, reactive, inject, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { parseNum } from '../../composables/useG7EquityMethodFormulaEngine'
import type { UnrecognizedLossRow } from '../../composables/useG7EquityMethodFormData'

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
  { label: '长期权益分析(9)', value: 'tab1' },
  { label: '超额亏损分配(8)', value: 'tab2' },
]

// ─── 行同步: selectedRowIndex ────────────────────────────────────────────────

const selectedRowIndex = ref<number>(-1)

function onCurrentChange(row: UnrecognizedLossRow | null) {
  if (row) {
    const idx = rows.findIndex(r => r.id === row.id)
    selectedRowIndex.value = idx
  }
}

// ─── 行数据 ──────────────────────────────────────────────────────────────────

const rows = reactive<UnrecognizedLossRow[]>([])
const conclusion = ref<string>('')

// ─── 超额亏损为0时Tab2禁用判断 ──────────────────────────────────────────────

/** 全局：所有行超额亏损都为0 → Tab2全局禁用提示 */
const allExcessLossZero = computed(() => rows.every(r => r.excessLoss === 0))

/** 单行：该行超额亏损为0时Tab2字段禁用 */
function isTab2Disabled(row: UnrecognizedLossRow): boolean {
  return row.excessLoss === 0
}

// ─── 公式重算（核心） ────────────────────────────────────────────────────────

function recalcRow(row: UnrecognizedLossRow): void {
  // Tab1公式：合计长期权益 = 投资账面 + 长应收 + 其他权益 + 预计负债
  row.totalLongTermEquity = Math.round((
    parseNum(row.investmentBookValue)
    + parseNum(row.longTermReceivable)
    + parseNum(row.otherLongTermEquity)
    + parseNum(row.estimatedLiability)
  ) * 100) / 100

  // Tab1公式：超额亏损 = MAX(0, 累计亏损 - 合计长期权益)
  const diff = parseNum(row.cumulativeLoss) - row.totalLongTermEquity
  row.excessLoss = Math.round(Math.max(0, diff) * 100) / 100

  // Tab2公式：未确认损失 = 超额亏损 - 冲减投资 - 冲减长应收 - 冲减其他 - 确认预计负债
  row.unrecognizedLoss = Math.round((
    row.excessLoss
    - parseNum(row.reduceInvestment)
    - parseNum(row.reduceLongTermReceivable)
    - parseNum(row.reduceOtherEquity)
    - parseNum(row.recognizeEstimatedLiability)
  ) * 100) / 100
}

// ─── 空行创建 ────────────────────────────────────────────────────────────────

function createEmptyRow(seq: number, investeeName: string): UnrecognizedLossRow {
  return {
    id: crypto.randomUUID(),
    seq,
    investeeName,
    investmentBookValue: 0,
    longTermReceivable: 0,
    otherLongTermEquity: 0,
    estimatedLiability: 0,
    totalLongTermEquity: 0,
    cumulativeLoss: 0,
    excessLoss: 0,
    allocationOrder: '①冲投资→②冲长应收→③确认预计负债',
    reduceInvestment: 0,
    reduceLongTermReceivable: 0,
    reduceOtherEquity: 0,
    recognizeEstimatedLiability: 0,
    unrecognizedLoss: 0,
    currentChange: 0,
    auditConclusion: '合理',
  }
}

// ─── 字段更新 ────────────────────────────────────────────────────────────────

function updateField(id: string, field: keyof UnrecognizedLossRow, value: any) {
  const row = rows.find(r => r.id === id)
  if (row) {
    ;(row as any)[field] = value
  }
}

function updateFieldWithRecalc(id: string, field: keyof UnrecognizedLossRow, value: any) {
  const row = rows.find(r => r.id === id)
  if (row) {
    ;(row as any)[field] = value ?? 0
    recalcRow(row)
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
    // 重新排序
    rows.forEach((r, i) => { r.seq = i + 1 })
  }
}

// ─── AI生成审计结论 ──────────────────────────────────────────────────────────

function handleAiConclusion() {
  ElMessage.info('AI生成未确认损失结论(impairment-conclusion)将在AI模块完成后启用')
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

  const lossData = data.unrecognizedLoss || data
  const rawRows = lossData?.rows || []
  conclusion.value = lossData?.conclusion || ''

  // 加载行数据
  if (Array.isArray(rawRows) && rawRows.length > 0) {
    for (let i = 0; i < rawRows.length; i++) {
      const raw = rawRows[i]
      const row: UnrecognizedLossRow = {
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
 * 导出当前数据（供父组件保存调用）
 */
function getData(): { rows: UnrecognizedLossRow[]; conclusion: string } {
  return { rows: [...rows], conclusion: conclusion.value }
}

defineExpose({ getData, loadFromHtmlData })

onMounted(() => {
  loadFromHtmlData(props.htmlData)
})
</script>

<style scoped>
.g7-tab-unrecognized-loss { padding: 12px; font-size: var(--wp-font-size, 13px); }

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

/* Tab2全局禁用提示 */
.tab2-disabled-alert { margin-bottom: 12px; }

/* 表格 */
.loss-table { font-size: var(--wp-font-size, 13px); }
.compact-num { width: 100%; }
.investee-name { font-weight: 500; color: #303133; }

/* 公式列：虚线下划线 + cursor:help */
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 1px;
}

/* 超额亏损高亮 */
.excess-highlight { color: #f56c6c; font-weight: 600; }

/* 禁用状态（超额亏损为0时） */
.text-disabled { color: #c0c4cc; }

/* 审计结论卡片 */
.conclusion-card { margin-top: 16px; }
.conclusion-header { display: flex; justify-content: space-between; align-items: center; }

/* 编制提示 */
.prep-hint { margin-top: 16px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; font-weight: 500; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; line-height: 1.8; }
</style>
