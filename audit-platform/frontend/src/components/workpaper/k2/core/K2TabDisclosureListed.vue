<template>
  <div class="k2-disclosure-listed">
    <!-- 方法论上下文（源模板原文，禁改写） -->
    <div class="methodology-block">
      <div class="methodology-title">源模板要求（附注披露信息（上市公司））</div>
      <div class="methodology-content">
        其他流动资产（注：根据实际情况列示；不存在的项目请删除）。<br />
        （金额较大的其他流动资产，应说明其内容、性质）<br />
        <span class="methodology-sub">
          附注 §五、13 共三张表：①明细列示表（必备）②合同取得成本变动（有则披露）
          ③碳排放配额变动（有则披露）。数据来源：审定表 K2-1 / 明细表 K2-2 /
          合同取得成本明细 K2-4 / 摊销测算 K2-5。
        </span>
      </div>
    </div>

    <!-- 勾稽校验 bar -->
    <div class="check-bar" :class="`check-${checkSummary.level}`">
      <span class="check-icon">{{ checkSummary.level === 'ok' ? '✓' : '!' }}</span>
      <span class="check-text">
        披露勾稽 {{ checkSummary.total - checkSummary.failed }}/{{ checkSummary.total }} 通过
        <template v-if="checkSummary.failed > 0">（{{ checkSummary.failed }} 项存在差异）</template>
      </span>
      <el-button size="small" link type="primary" @click="checkExpanded = !checkExpanded">
        {{ checkExpanded ? '收起明细' : '查看明细' }}
      </el-button>
      <span class="check-spacer" />
      <el-button size="small" type="success" :disabled="isReadonly" @click="syncToDisclosureNotes">
        同步到附注
      </el-button>
    </div>
    <el-table v-if="checkExpanded" :data="checkItems" size="small" class="check-table">
      <el-table-column label="校验项" min-width="200">
        <template #default="{ row }">
          <el-tooltip :content="row.rule" placement="top">
            <span class="rule-cell">{{ row.label }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="本表" width="140" align="right">
        <template #default="{ row }">{{ fmtAmount(row.left) }}</template>
      </el-table-column>
      <el-table-column label="对方" width="140" align="right">
        <template #default="{ row }">{{ fmtAmount(row.right) }}</template>
      </el-table-column>
      <el-table-column label="差异" width="140" align="right">
        <template #default="{ row }">{{ fmtAmount(row.diff) }}</template>
      </el-table-column>
      <el-table-column label="结果" width="90">
        <template #default="{ row }">
          <el-tag :type="row.level === 'ok' ? 'success' : row.level === 'warn' ? 'warning' : 'danger'" size="small">
            {{ row.level === 'ok' ? '通过' : row.level === 'warn' ? '关注' : '不平' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="说明" min-width="180">
        <template #default="{ row }">{{ row.detail || '-' }}</template>
      </el-table-column>
    </el-table>

    <!-- ① 其他流动资产明细列示 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-title-row">
          <span class="section-title">① 其他流动资产</span>
          <div class="title-actions">
            <el-button size="small" :disabled="isReadonly" @click="addMainRow">新增明细行</el-button>
            <el-button size="small" type="default" link @click="handleReview('K2-disc-listed-main')">💬</el-button>
          </div>
        </div>
      </template>
      <el-table :data="mainRows" size="small" class="disclosure-table">
        <el-table-column prop="label" label="项目" min-width="200">
          <template #default="{ row, $index }">
            <span v-if="row.fixed">{{ row.label }}</span>
            <el-input
              v-else
              :model-value="row.label"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => onMainLabelChange($index, v)"
            />
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="180" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="row.endAmount"
              :aria-label="`期末余额 ${row.label}`"
              @change="(v: number) => onMainCellChange($index, 'endAmount', v)"
            />
            <span v-else>{{ fmtAmount(row.endAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上年年末余额" width="180" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="row.priorAmount"
              :aria-label="`上年年末余额 ${row.label}`"
              @change="(v: number) => onMainCellChange($index, 'priorAmount', v)"
            />
            <span v-else>{{ fmtAmount(row.priorAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row, $index }">
            <el-button
              v-if="!row.fixed"
              size="small"
              link
              type="danger"
              :disabled="isReadonly"
              @click="removeMainRow($index)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-table :data="[mainTotalRow]" size="small" class="disclosure-table total-table" :show-header="false">
        <el-table-column prop="label" min-width="200" />
        <el-table-column width="180" align="right">
          <template #default="{ row }">
            <el-tooltip content="合计 = 各明细行之和（F13-2）" placement="top">
              <span class="formula-cell">{{ fmtAmount(row.endAmount) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column width="180" align="right">
          <template #default="{ row }">
            <el-tooltip content="合计 = 各明细行之和（F13-2）" placement="top">
              <span class="formula-cell">{{ fmtAmount(row.priorAmount) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column width="80" />
      </el-table>
    </el-card>

    <!-- ② 合同取得成本 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-title-row">
          <span class="section-title">② 合同取得成本</span>
          <div class="title-actions">
            <el-switch
              :model-value="contractCost.enabled"
              size="small"
              active-text="本项目适用"
              inactive-text="不适用"
              :disabled="isReadonly"
              @change="(v: any) => onToggleContractCost(!!v)"
            />
            <el-button
              v-if="contractCost.enabled"
              size="small"
              :disabled="isReadonly"
              @click="addContractCostCategory"
            >
              新增类别列
            </el-button>
            <el-button size="small" type="default" link @click="handleReview('K2-disc-listed-contract-cost')">💬</el-button>
          </div>
        </div>
      </template>
      <div v-if="!contractCost.enabled" class="disabled-hint">
        已标记不适用 —— 同步时不推送该表，并清理附注中的残留表（源模板：不存在的项目请删除）。
      </div>
      <template v-else>
        <el-table :data="contractCostRows" size="small" class="disclosure-table">
          <el-table-column prop="label" label="项目" min-width="180" />
          <el-table-column
            v-for="(cat, catIdx) in contractCost.categories"
            :key="`cat-${catIdx}`"
            :label="cat"
            width="180"
            align="right"
          >
            <template #header>
              <div class="cat-header">
                <span>{{ cat }}</span>
                <el-button
                  size="small"
                  link
                  :disabled="isReadonly"
                  @click="renameContractCostCategory(catIdx)"
                >
                  改名
                </el-button>
                <el-button
                  v-if="contractCost.categories.length > 1"
                  size="small"
                  link
                  type="danger"
                  :disabled="isReadonly"
                  @click="removeContractCostCategory(catIdx)"
                >
                  删除
                </el-button>
              </div>
            </template>
            <template #default="{ row }">
              <el-tooltip
                v-if="row.isFormula"
                content="期末余额 = 期初余额 + 本年增加 − 本年摊销 − 本年计提减值损失"
                placement="top"
              >
                <span class="formula-cell">{{ fmtAmount(row.values[catIdx]) }}</span>
              </el-tooltip>
              <WpAmountInput
                v-else-if="!isReadonly"
                :model-value="row.values[catIdx]"
                :aria-label="`${cat} ${row.label}`"
                @change="(v: number) => onContractCostChange(row.rowIdx, catIdx, v)"
              />
              <span v-else>{{ fmtAmount(row.values[catIdx]) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="合计" width="180" align="right">
            <template #default="{ row }">
              <el-tooltip content="合计 = 各类别列之和" placement="top">
                <span class="formula-cell">{{ fmtAmount(row.total) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
        </el-table>
        <div class="table-hint">
          本年摊销、本年计提减值损失按正数录入，期末余额行自动按减项计算。
          源模板以［佣金支出］为示例类别，请按该资产主要类别改名或增列。
        </div>
      </template>
    </el-card>

    <!-- ③ 碳排放配额变动情况 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-title-row">
          <span class="section-title">③ 碳排放配额变动情况</span>
          <div class="title-actions">
            <el-switch
              :model-value="carbon.enabled"
              size="small"
              active-text="本项目适用"
              inactive-text="不适用"
              :disabled="isReadonly"
              @change="(v: any) => onToggleCarbon(!!v)"
            />
            <el-button size="small" type="default" link @click="handleReview('K2-disc-listed-carbon')">💬</el-button>
          </div>
        </div>
      </template>
      <div v-if="!carbon.enabled" class="disabled-hint">
        已标记不适用 —— 同步时不推送该表，并清理附注中的残留表。
      </div>
      <el-table v-else :data="carbon.rows" size="small" class="disclosure-table">
        <el-table-column prop="label" label="项目" min-width="240" />
        <el-table-column label="本期发生额" width="180" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="row.currentAmount"
              :aria-label="`本期发生额 ${row.label}`"
              @change="(v: number) => onCarbonChange($index, 'currentAmount', v)"
            />
            <span v-else>{{ fmtAmount(row.currentAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上期发生额" width="180" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="row.priorAmount"
              :aria-label="`上期发生额 ${row.label}`"
              @change="(v: number) => onCarbonChange($index, 'priorAmount', v)"
            />
            <span v-else>{{ fmtAmount(row.priorAmount) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 文本说明区（三段，取自附注模版 text_sections） -->
    <el-card v-for="seg in textSegments" :key="seg.key" shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-title-row">
          <span class="section-title">{{ seg.title }}</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link :disabled="isReadonly" @click="handleAiGenerate(seg.key)">
              <el-icon><MagicStick /></el-icon> AI辅助
            </el-button>
            <el-button size="small" type="default" link @click="handleReview(`K2-disc-listed-text-${seg.key}`)">💬</el-button>
          </div>
        </div>
      </template>
      <div class="seg-requirement">{{ seg.requirement }}</div>
      <el-input
        :model-value="texts[seg.key]"
        type="textarea"
        :autosize="{ minRows: 4 }"
        :disabled="isReadonly"
        :placeholder="seg.placeholder"
        @update:model-value="(v: string) => (texts[seg.key] = v)"
        @change="onTextChange"
      />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>①表列结构对齐附注 §五、13：项目 / 期末余额 / 上年年末余额，合计行自动汇总。</li>
        <li>13 个固定行名取自附注模版；项目实际存在其他项目时用「新增明细行」补充（可命名可删除）。</li>
        <li>②表是转置结构：行为变动项目，列为资产主要类别；合计列与期末余额行均为公式。</li>
        <li>③表 10 个固定行名取自附注模版，逐字不改。</li>
        <li>②③两表不适用时关闭开关，同步会清理附注中的残留表。</li>
        <li>录入后 800ms 自动同步到附注；也可点「同步到附注」立即推送。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K2TabDisclosureListed.vue — 附注披露信息（上市公司）
 *
 * 结构对齐 note_template_listed.json §五、13（交付物权威）：
 * ①其他流动资产（3 列 13 固定行 + 合计）
 * ②合同取得成本（转置：行=变动项目，列=资产主要类别 + 合计）
 * ③碳排放配额变动情况（3 列 10 固定行）
 * 文本三段取自模板 text_sections。
 *
 * 历史版本是自造的 7 列变动矩阵（期初/增加/减少/期末/占比/备注），与附注不符，已废止。
 *
 * spec: .kiro/specs/k2-other-current-assets-disclosure-alignment/ R1 R2 R3
 */
import { computed, inject, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { fmtAmount } from '@/utils/formatters'
import { eventBus } from '@/utils/eventBus'
import http from '@/utils/http'
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import {
  K2_CARBON_ROWS,
  K2_CONTRACT_COST_FORMULA_ROW,
  K2_CONTRACT_COST_ROWS,
  K2_DEFAULT_CONTRACT_COST_CATEGORIES,
  K2_LISTED_MAIN_ROWS,
  K2_NOTE_SECTION,
  K2_TOTAL_ROW_LABEL,
  buildK2SyncPayload,
  type K2DisclosureSnapshot,
} from '../../composables/k2NoteSectionMap'
import {
  checkK2Consistency,
  contractCostRowTotal,
  k2ConsistencySummary,
  recalcContractCost,
} from '../../composables/useK2DisclosureEngine'

const K2_ACCOUNT_CODE = '1231'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{ save: [itemId: string, value: any] }>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })

// ═══ 数据模型 ═══
interface MainRow {
  label: string
  endAmount: number
  priorAmount: number
  /** 模板固定行（行名不可改、不可删） */
  fixed: boolean
}

type TextKey = 'significant' | 'contractCost' | 'carbon'

const mainRows = reactive<MainRow[]>(
  K2_LISTED_MAIN_ROWS.map(label => ({ label, endAmount: 0, priorAmount: 0, fixed: true })),
)

const contractCost = reactive({
  enabled: false,
  categories: [...K2_DEFAULT_CONTRACT_COST_CATEGORIES] as string[],
  cells: recalcContractCost([], K2_DEFAULT_CONTRACT_COST_CATEGORIES.length),
})

const carbon = reactive({
  enabled: false,
  rows: K2_CARBON_ROWS.map(label => ({ label, currentAmount: 0, priorAmount: 0 })),
})

const texts = reactive<Record<TextKey, string>>({
  significant: '',
  contractCost: '',
  carbon: '',
})

const checkExpanded = ref(false)

/** 文本段定义 —— requirement 逐字取自 note_template_listed.json §五、13 text_sections */
const textSegments: Array<{ key: TextKey; title: string; requirement: string; placeholder: string }> = [
  {
    key: 'significant',
    title: '金额较大的其他流动资产说明',
    requirement:
      '（金额较大的其他流动资产，应说明其内容、性质）【提示：进项税额，根据应交税费-应交增值税科目借方余额分析填列；'
      + '多交或预缴的增值税额，根据应交税费-未交增值税科目以及应交税费-预交增值税科目借方余额分析填列。'
      + '上述重分类事项，如属于其他非流动资产的，应在其他非流动资产科目列示。】',
    placeholder: '按①表金额较大的项目，逐项说明其内容与性质',
  },
  {
    key: 'contractCost',
    title: '合同取得成本判断与摊销方法说明',
    requirement:
      '披露与合同取得成本有关的资产相关的信息，包括确定该资产金额所做的判断、该资产的摊销方法、'
      + '按该资产主要类别披露的期末账面价值以及本期确认的摊销及减值损失金额等。'
      + '摊销期限未超过一年的合同取得成本于其发生时计入当期损益。',
    placeholder: '说明资本化判断依据、摊销方法与摊销期间，以及本期摊销及减值损失金额',
  },
  {
    key: 'carbon',
    title: '碳排放权相关信息说明',
    requirement:
      '披露与碳排放权相关的信息，包括：①与碳排放权交易相关的信息（参与减排机制的特征、碳排放战略、节能减排措施等）；'
      + '②碳排放配额的具体来源（配额取得方式、取得年度、用途、结转原因等）；'
      + '③节能减排或超额排放情况（免费分配取得的碳排放配额与同期实际排放量有关数据的对比情况、原因等）；'
      + '④碳排放配额变动情况按③表格式披露。',
    placeholder: '按①②③四项要求分别说明',
  },
]

// ═══ 派生 ═══
const mainTotalRow = computed(() => ({
  label: K2_TOTAL_ROW_LABEL,
  endAmount: mainRows.reduce((s, r) => s + (Number(r.endAmount) || 0), 0),
  priorAmount: mainRows.reduce((s, r) => s + (Number(r.priorAmount) || 0), 0),
}))

const contractCostRows = computed(() =>
  K2_CONTRACT_COST_ROWS.map((label, rowIdx) => ({
    rowIdx,
    label,
    isFormula: label === K2_CONTRACT_COST_FORMULA_ROW,
    values: contractCost.categories.map((_c, catIdx) => contractCost.cells[rowIdx]?.[catIdx] ?? 0),
    total: contractCostRowTotal(contractCost.cells, rowIdx, contractCost.categories.length),
  })),
)

function responseNumber(key: string): number | null {
  const item = props.allResponses.get(key)
  if (!item) return null
  const raw = item.remark ?? item.value ?? null
  if (raw == null || raw === '') return null
  const n = Number(raw)
  return Number.isFinite(n) ? n : null
}

const checkItems = computed(() =>
  checkK2Consistency({
    variant: 'listed',
    mainRows,
    auditedEnd: responseNumber('K2-1-audited-total'),
    auditedPrior: responseNumber('K2-1-begin-total'),
    contractCost,
  }),
)

const checkSummary = computed(() => k2ConsistencySummary(checkItems.value))

// ═══ 编辑 ═══
function onMainCellChange(index: number, field: 'endAmount' | 'priorAmount', value: number): void {
  const row = mainRows[index]
  if (!row) return
  row[field] = Number(value) || 0
  persistMain()
}

function onMainLabelChange(index: number, value: string): void {
  const row = mainRows[index]
  if (!row || row.fixed) return
  row.label = String(value ?? '').trim()
  persistMain()
}

async function addMainRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入其他流动资产明细项目名称', '新增明细行', {
      confirmButtonText: '新增',
      cancelButtonText: '取消',
      inputPattern: /\S/,
      inputErrorMessage: '名称不能为空',
    })
    const label = String(value ?? '').trim()
    if (mainRows.some(r => r.label === label)) {
      ElMessage.warning('该项目已存在')
      return
    }
    mainRows.push({ label, endAmount: 0, priorAmount: 0, fixed: false })
    persistMain()
  } catch {
    /* 取消 */
  }
}

function removeMainRow(index: number): void {
  const row = mainRows[index]
  if (!row || row.fixed) return
  mainRows.splice(index, 1)
  persistMain()
}

function onToggleContractCost(enabled: boolean): void {
  contractCost.enabled = enabled
  persistContractCost()
}

function onContractCostChange(rowIdx: number, catIdx: number, value: number): void {
  if (!contractCost.cells[rowIdx]) contractCost.cells[rowIdx] = []
  contractCost.cells[rowIdx][catIdx] = Number(value) || 0
  contractCost.cells = recalcContractCost(contractCost.cells, contractCost.categories.length)
  persistContractCost()
}

async function addContractCostCategory(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入合同取得成本的资产类别名称', '新增类别列', {
      confirmButtonText: '新增',
      cancelButtonText: '取消',
      inputPattern: /\S/,
      inputErrorMessage: '名称不能为空',
    })
    const name = String(value ?? '').trim()
    if (contractCost.categories.includes(name)) {
      ElMessage.warning('该类别已存在')
      return
    }
    contractCost.categories.push(name)
    contractCost.cells = recalcContractCost(contractCost.cells, contractCost.categories.length)
    persistContractCost()
  } catch {
    /* 取消 */
  }
}

async function renameContractCostCategory(catIdx: number): Promise<void> {
  const current = contractCost.categories[catIdx]
  if (current == null) return
  try {
    const { value } = await ElMessageBox.prompt('请输入新的类别名称', '类别改名', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputValue: current,
      inputPattern: /\S/,
      inputErrorMessage: '名称不能为空',
    })
    const name = String(value ?? '').trim()
    if (name === current) return
    if (contractCost.categories.includes(name)) {
      ElMessage.warning('该类别已存在')
      return
    }
    contractCost.categories[catIdx] = name
    persistContractCost()
  } catch {
    /* 取消 */
  }
}

function removeContractCostCategory(catIdx: number): void {
  if (contractCost.categories.length <= 1) return
  contractCost.categories.splice(catIdx, 1)
  for (const row of contractCost.cells) row.splice(catIdx, 1)
  contractCost.cells = recalcContractCost(contractCost.cells, contractCost.categories.length)
  persistContractCost()
}

function onToggleCarbon(enabled: boolean): void {
  carbon.enabled = enabled
  persistCarbon()
}

function onCarbonChange(index: number, field: 'currentAmount' | 'priorAmount', value: number): void {
  const row = carbon.rows[index]
  if (!row) return
  row[field] = Number(value) || 0
  persistCarbon()
}

function onTextChange(): void {
  persistTexts()
}

// ═══ 持久化 ═══
function persist(itemId: string, payload: unknown): void {
  emit('save', itemId, JSON.stringify(payload))
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function persistMain(): void {
  persist('K2-disc-listed-main', mainRows.map(r => ({ ...r })))
}

function persistContractCost(): void {
  persist('K2-disc-listed-contract-cost', {
    enabled: contractCost.enabled,
    categories: [...contractCost.categories],
    cells: contractCost.cells.map(r => [...r]),
  })
}

function persistCarbon(): void {
  persist('K2-disc-listed-carbon', {
    enabled: carbon.enabled,
    rows: carbon.rows.map(r => ({ ...r })),
  })
}

function persistTexts(): void {
  persist('K2-disc-listed-texts', { ...texts })
}

function parseSaved(itemId: string): any {
  const saved = props.allResponses.get(itemId)
  const raw = saved?.remark ?? saved?.value ?? null
  if (!raw) return null
  if (typeof raw !== 'string') return raw
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

function loadSavedData(): void {
  const savedMain = parseSaved('K2-disc-listed-main')
  if (Array.isArray(savedMain) && savedMain.length) {
    mainRows.splice(0, mainRows.length, ...savedMain.map((r: any) => ({
      label: String(r?.label ?? ''),
      endAmount: Number(r?.endAmount) || 0,
      priorAmount: Number(r?.priorAmount) || 0,
      fixed: K2_LISTED_MAIN_ROWS.includes(String(r?.label ?? '')),
    })))
  }

  const savedCc = parseSaved('K2-disc-listed-contract-cost')
  if (savedCc && typeof savedCc === 'object') {
    contractCost.enabled = !!savedCc.enabled
    const cats = Array.isArray(savedCc.categories)
      ? savedCc.categories.map((c: any) => String(c ?? '').trim()).filter(Boolean)
      : []
    contractCost.categories = cats.length ? cats : [...K2_DEFAULT_CONTRACT_COST_CATEGORIES]
    contractCost.cells = recalcContractCost(
      Array.isArray(savedCc.cells) ? savedCc.cells : [],
      contractCost.categories.length,
    )
  }

  const savedCarbon = parseSaved('K2-disc-listed-carbon')
  if (savedCarbon && typeof savedCarbon === 'object') {
    carbon.enabled = !!savedCarbon.enabled
    const byLabel = new Map(
      (Array.isArray(savedCarbon.rows) ? savedCarbon.rows : []).map((r: any) => [String(r?.label ?? ''), r]),
    )
    carbon.rows = K2_CARBON_ROWS.map(label => {
      const hit: any = byLabel.get(label)
      return {
        label,
        currentAmount: Number(hit?.currentAmount) || 0,
        priorAmount: Number(hit?.priorAmount) || 0,
      }
    })
  }

  const savedTexts = parseSaved('K2-disc-listed-texts')
  if (savedTexts && typeof savedTexts === 'object') {
    for (const key of ['significant', 'contractCost', 'carbon'] as TextKey[]) {
      texts[key] = String(savedTexts[key] ?? '')
    }
  }
}

// ═══ 同步到附注 ═══
function buildSnapshot(): K2DisclosureSnapshot {
  return {
    mainRows: mainRows.map(r => ({
      label: r.label,
      endAmount: r.endAmount,
      priorAmount: r.priorAmount,
    })),
    contractCost: {
      enabled: contractCost.enabled,
      categories: [...contractCost.categories],
      cells: contractCost.cells.map(r => [...r]),
    },
    carbon: {
      enabled: carbon.enabled,
      rows: carbon.rows.map(r => ({ ...r })),
    },
    texts: textSegments
      .filter(seg => texts[seg.key].trim())
      .map(seg => ({ section: `k2-${seg.key}`, title: seg.title, text: texts[seg.key] })),
  }
}

async function syncToDisclosureNotes(): Promise<void> {
  if (!props.projectId || props.isReadonly) return
  const payload = buildK2SyncPayload('listed', props.wpId || '', buildSnapshot())
  try {
    await http.post(`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`, payload)
    eventBus.emit('disclosure:note-text-updated' as any, {
      wpCode: 'K2',
      variant: 'listed',
      accountCode: K2_ACCOUNT_CODE,
      projectId: props.projectId,
      sectionIds: [K2_NOTE_SECTION.listed],
    })
  } catch {
    /* 静默：自动同步失败不打断录入 */
  }
}

// ═══ AI 辅助 ═══
const AI_PROMPTS: Record<TextKey, string> = {
  significant:
    '请依据致同 2025 修订版底稿 K2 源模板与企业会计准则 15 号文口径，'
    + '就其他流动资产中金额较大的项目撰写附注披露文字，逐项说明其内容与性质。'
    + '只能使用已提供的项目名称与金额，不得虚构项目、金额或业务背景；无把握的内容留空由审计师补充。',
  contractCost:
    '请依据致同 2025 修订版底稿 K2 源模板与收入准则关于合同取得成本的披露要求，'
    + '撰写附注披露文字：说明将增量成本资本化确认为合同取得成本所做的判断、该资产的摊销方法与摊销期间、'
    + '按主要类别的期末账面价值以及本期确认的摊销及减值损失金额。'
    + '只能使用已提供的类别与金额，不得虚构合同、客户或金额。',
  carbon:
    '请依据致同 2025 修订版底稿 K2 源模板关于碳排放权的披露要求，撰写附注披露文字，'
    + '分别说明：与碳排放权交易相关的信息（参与减排机制的特征、碳排放战略、节能减排措施）、'
    + '碳排放配额的具体来源（取得方式、取得年度、用途、结转原因）、节能减排或超额排放情况及原因。'
    + '只能使用已提供的配额变动数据，不得虚构减排项目、政策或数量。',
}

async function handleAiGenerate(key: TextKey): Promise<void> {
  const seg = textSegments.find(s => s.key === key)
  if (!seg) return
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      prompt: AI_PROMPTS[key],
      context: `科目：其他流动资产(1231)；附注章节：${K2_NOTE_SECTION.listed}；变体：上市公司；`
        + `源模板要求：${seg.requirement}`,
      existingContent: texts[key] || '',
      section: `k2-${key}`,
    })
    const generated = res.data?.data?.content || res.data?.content || ''
    if (!generated) {
      ElMessage.warning('AI 未生成内容')
      return
    }
    await ElMessageBox.confirm(
      `AI 生成内容预览：\n\n${generated.slice(0, 300)}${generated.length > 300 ? '…' : ''}`,
      'AI 生成确认',
      { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' },
    )
    texts[key] = texts[key] ? `${texts[key]}\n${generated}` : generated
    persistTexts()
    ElMessage.success('已填入 AI 生成内容')
  } catch {
    /* 取消或失败 */
  }
}

// ═══ 复核 ═══
function handleReview(id: string): void {
  openReviewDialog(id)
}

// ═══ 生命周期 ═══
onMounted(() => {
  loadSavedData()
})

onBeforeUnmount(() => {
  autoSync.cancelPending()
})
</script>

<style scoped>
.k2-disclosure-listed {
  padding: 16px;
  font-size: var(--wp-font-size, 13px);
}

.methodology-block {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  border-radius: 4px;
  padding: 12px 16px;
  margin-bottom: 12px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.8;
}
.methodology-title {
  font-weight: 600;
  color: #78350f;
  margin-bottom: 4px;
}
.methodology-sub {
  color: #a16207;
}

.check-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 12px;
  border-radius: 4px;
  margin-bottom: 12px;
  font-size: 12px;
}
.check-ok {
  background: var(--el-color-success-light-9);
  color: var(--el-color-success);
}
.check-warn {
  background: var(--el-color-warning-light-9);
  color: var(--el-color-warning);
}
.check-error {
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
}
.check-icon {
  font-weight: 700;
}
.check-spacer {
  flex: 1;
}
.check-table {
  margin-bottom: 12px;
  font-size: 12px;
}
.rule-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
}

.disclosure-card {
  margin-bottom: 12px;
}
.section-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.section-title {
  font-weight: 600;
  font-size: 14px;
}
.title-actions {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-left: auto;
}

.disclosure-table {
  font-size: var(--wp-font-size, 13px);
}
.total-table :deep(.el-table__row) {
  font-weight: 600;
}
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}
.cat-header {
  display: flex;
  align-items: center;
  gap: 4px;
  justify-content: flex-end;
}
.disabled-hint,
.table-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  padding: 6px 0;
  line-height: 1.7;
}
.seg-requirement {
  border-left: 3px solid #d97706;
  background: #fffbeb;
  color: #92400e;
  font-size: 12px;
  line-height: 1.7;
  padding: 8px 12px;
  margin-bottom: 8px;
  border-radius: 3px;
}

.compile-hint {
  margin-top: 16px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.compile-hint summary {
  cursor: pointer;
  font-weight: 500;
}
.compile-hint ul {
  padding-left: 20px;
  margin-top: 8px;
  line-height: 1.8;
}
</style>
