<template>
  <div class="g6-disclosure-soe" data-testid="g6-disclosure-soe">
    <div class="section-head first">
      <div>
        <h3 class="sheet-title">G6 其他债权投资附注披露（国企）</h3>
        <div class="cross-index">Excel 95 行 × 6 列 · Note:{{ noteSection }}</div>
      </div>
      <div class="head-actions">
        <el-button size="small" :disabled="isReadonly" @click="refreshFromSources(true)">
          从 G6-1/G6-2/G6-3 更新
        </el-button>
        <el-button
          size="small"
          type="primary"
          :loading="isSyncing"
          :disabled="isReadonly || !projectId"
          @click="syncToDisclosureNotes"
        >
          同步至附注
        </el-button>
        <GtReviewTrigger section-id="G6-disclosure-soe" />
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="国企口径按“公允价值余额→重要投资→期末三阶段减值→减值准备滚动”编制。其他债权投资按公允价值列示，ECL 不冲减资产负债表列示金额。"
      class="objective-alert"
    />

    <section>
      <div class="section-head">
        <h4>（1）其他债权投资情况</h4>
        <el-tag :type="balanceTieOut.matched ? 'success' : 'danger'" size="small">
          {{ balanceTieOut.matched ? '与 G6-1 相符' : `与 G6-1 差异 ${fmt(balanceTieOut.diff)}` }}
        </el-tag>
      </div>
      <el-table :data="balanceRows" border size="small">
        <el-table-column label="项目" min-width="180">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.item"
              size="small"
              @change="persistStructured"
            />
            <span v-else>{{ row.item }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="150" align="right">
          <template #default="{ row }">{{ fmt(row.endingBalance) }}</template>
        </el-table-column>
        <el-table-column label="期初余额" width="150" align="right">
          <template #default="{ row }">{{ fmt(row.openingBalance) }}</template>
        </el-table-column>
      </el-table>
      <div class="table-total">
        合计：期末 {{ fmt(balanceTotals.ending) }} ／ 期初 {{ fmt(balanceTotals.opening) }}
      </div>
    </section>

    <section>
      <div class="section-head">
        <h4>（2）期末重要的其他债权投资</h4>
        <span class="hint">前四项从 G6-2 更新；减值准备按项目补充分拆</span>
      </div>
      <el-table :data="importantRows" border size="small">
        <el-table-column prop="item" label="其他债权投资项目" min-width="160" />
        <el-table-column label="面值" width="120" align="right">
          <template #default="{ row }">{{ fmt(row.faceValue) }}</template>
        </el-table-column>
        <el-table-column label="摊余成本" width="120" align="right">
          <template #default="{ row }">{{ fmt(row.amortizedCost) }}</template>
        </el-table-column>
        <el-table-column label="公允价值" width="120" align="right">
          <template #default="{ row }">{{ fmt(row.fairValue) }}</template>
        </el-table-column>
        <el-table-column label="累计计入 OCI 的公允价值变动" width="180" align="right">
          <template #default="{ row }">{{ fmt(row.ociCumulative) }}</template>
        </el-table-column>
        <el-table-column label="减值准备" width="130" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.impairment"
              size="small"
              :controls="false"
              class="amt-input"
              @change="persistStructured"
            />
            <span v-else>{{ fmt(row.impairment) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <div class="table-total">
        合计：面值 {{ fmt(importantTotals.faceValue) }} ／ 摊余成本
        {{ fmt(importantTotals.amortizedCost) }} ／ 公允价值
        {{ fmt(importantTotals.fairValue) }} ／ 减值准备
        {{ fmt(importantTotals.impairment) }}
      </div>
    </section>

    <section>
      <div class="section-head">
        <h4>（3）减值准备计提情况（期末三阶段）</h4>
        <el-tag :type="stageTieOut.matched ? 'success' : 'danger'" size="small">
          {{ stageTieOut.matched ? '与 G6-3 相符' : `待分拆/差异 ${fmt(stageTieOut.diff)}` }}
        </el-tag>
      </div>
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="“其中”支持动态增删；第一阶段按未来12个月 ECL，第二、三阶段按整个存续期 ECL。账面价值仅为减值分析口径。"
        class="stage-tip"
      />

      <el-card v-for="block in stageBlocks" :key="block.id" shadow="never" class="stage-card">
        <template #header>
          <strong>{{ block.title }}</strong>
        </template>
        <div v-for="method in stageMethods" :key="method" class="method-block">
          <div class="method-head">
            <span>{{ method === 'individual' ? '按单项计提减值准备' : '按组合计提减值准备' }}</span>
            <el-button
              type="primary"
              link
              size="small"
              :disabled="isReadonly"
              @click="addStageRow(block.id, method)"
            >
              + 添加其中行
            </el-button>
          </div>
          <el-table :data="methodRows(block, method)" border size="small">
            <el-table-column label="类别" min-width="150">
              <template #default="{ row }">
                <el-input
                  v-if="row.kind === 'detail' && !isReadonly"
                  :model-value="row.name"
                  size="small"
                  @change="(v: string) => patchStageRow(block.id, method, row.id, { name: v })"
                />
                <strong v-else-if="row.kind === 'parent'">{{ row.name }}</strong>
                <span v-else>{{ row.name }}</span>
              </template>
            </el-table-column>
            <el-table-column label="账面余额" width="125" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="row.kind === 'detail' && !isReadonly"
                  :model-value="row.bookBalance"
                  size="small"
                  :controls="false"
                  class="amt-input"
                  @change="(v: number) => patchStageRow(block.id, method, row.id, { bookBalance: v || 0 })"
                />
                <span v-else>{{ fmt(row.bookBalance) }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="block.rateLabel" width="170" align="right">
              <template #default="{ row }">{{ fmtRate(row.ratePct) }}</template>
            </el-table-column>
            <el-table-column label="减值准备" width="125" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="row.kind === 'detail' && !isReadonly"
                  :model-value="row.impairment"
                  size="small"
                  :controls="false"
                  class="amt-input"
                  @change="(v: number) => patchStageRow(block.id, method, row.id, { impairment: v || 0 })"
                />
                <span v-else>{{ fmt(row.impairment) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="账面价值（分析口径）" width="150" align="right">
              <template #default="{ row }">{{ fmt(row.bookValue) }}</template>
            </el-table-column>
            <el-table-column label="理由" min-width="140">
              <template #default="{ row }">
                <el-input
                  v-if="row.kind === 'detail' && !isReadonly"
                  :model-value="row.reason"
                  size="small"
                  @change="(v: string) => patchStageRow(block.id, method, row.id, { reason: v })"
                />
                <span v-else>{{ row.reason }}</span>
              </template>
            </el-table-column>
            <el-table-column v-if="!isReadonly" width="50">
              <template #default="{ row }">
                <el-button
                  v-if="row.kind === 'detail'"
                  type="danger"
                  link
                  @click="removeStageRow(block.id, method, row.id)"
                >
                  删
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
        <div class="table-total">
          阶段合计：账面余额 {{ fmt(stageTotal(block).bookBalance) }} ／ 减值准备
          {{ fmt(stageTotal(block).impairment) }} ／ 账面价值
          {{ fmt(stageTotal(block).bookValue) }}
        </div>
      </el-card>
    </section>

    <section>
      <div class="section-head">
        <h4>本期计提、收回或转回的减值准备情况</h4>
        <el-tag :type="movementTieOut.matched ? 'success' : 'danger'" size="small">
          {{ movementTieOut.matched ? '期末与 G6-3 相符' : `期末差异 ${fmt(movementTieOut.diff)}` }}
        </el-tag>
      </div>
      <el-table :data="movementRows" border size="small">
        <el-table-column prop="item" label="减值准备" min-width="160" />
        <el-table-column v-for="stage in movementStages" :key="stage.key" :label="stage.label" width="150" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly"
              v-model="row[stage.key]"
              size="small"
              :controls="false"
              class="amt-input"
              @change="persistStructured"
            />
            <span v-else>{{ fmt(row[stage.key]) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="合计" width="130" align="right">
          <template #default="{ row }">{{ fmt(movementTotal(row)) }}</template>
        </el-table-column>
      </el-table>
    </section>

    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-head note-head">
          <strong>附注说明文字</strong>
          <el-button
            type="primary"
            link
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="fillAiDraft"
          >
            🤖 AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="noteText"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 14 }"
        :disabled="isReadonly"
        placeholder="说明 FVOCI 分类、公允价值计量、OCI 变动、ECL 三阶段及重大项目情况……"
        @change="persistNote"
      />
    </el-card>

    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>Excel 与平台结构一致：余额（8–12）→重要投资（14–20）→三阶段（22–74）→减值滚动（75–89）。</li>
        <li>余额从 G6-1、重要投资从 G6-2、减值合计从 G6-3 更新；三阶段明细按 G6-11/G6-12 填列。</li>
        <li>“同步至附注”单向写入国企附注“其他债权投资”，不反向覆盖底稿。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import { useG6MainAiGenerate } from '../../composables/useG6MainAiGenerate'
import {
  addStageDetail,
  bookValue,
  buildDefaultSoeStageBlocks,
  eclRatePct,
  methodTotals,
  parseStageBlocks,
  patchStageDetail,
  removeStageDetail,
  serializeStageBlocks,
  stageTotals,
  type G4StageBlock,
  type G4StageDetailRow,
  type G4StageMethod,
} from '../../composables/g4ListedStageDisclosure'
import type { ChecklistResponse } from '../../composables/useF1FormData'

interface BalanceRow {
  item: string
  endingBalance: number
  openingBalance: number
}

interface ImportantRow {
  item: string
  faceValue: number
  amortizedCost: number
  fairValue: number
  ociCumulative: number
  impairment: number
}

type MovementAmountKey = 'stage1' | 'stage2' | 'stage3'

interface MovementRow {
  key: string
  item: string
  stage1: number
  stage2: number
  stage3: number
  editable: boolean
}

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses?: Map<string, ChecklistResponse>
}>()

const ACCOUNT_CODE = '1503'
const STRUCTURED_KEY = 'G6-disclosure-soe-rows'
const STAGES_KEY = 'G6-disclosure-soe-stages'
const TEXT_KEY = 'G6-disclosure-soe-text'

const isReadonly = computed(() => props.isReadonly)
const wpIdRef = computed(() => props.wpId)
const { generateAndConfirm, aiAvailable, loading: aiLoading } = useG6MainAiGenerate(wpIdRef)
const isSyncing = ref(false)
const sourceFvEnd = ref(0)
const sourceFvOpening = ref(0)
const sourceProvisionEnd = ref(0)

const balanceRows = ref<BalanceRow[]>(
  Array.from({ length: 4 }, (_, i) => ({
    item: `项目${i + 1}（可改名）`,
    endingBalance: 0,
    openingBalance: 0,
  })),
)
const importantRows = ref<ImportantRow[]>(
  Array.from({ length: 4 }, (_, i) => ({
    item: `重要项目${i + 1}`,
    faceValue: 0,
    amortizedCost: 0,
    fairValue: 0,
    ociCumulative: 0,
    impairment: 0,
  })),
)

const movementRows = ref<MovementRow[]>([
  { key: 'opening', item: '期初余额', stage1: 0, stage2: 0, stage3: 0, editable: true },
  { key: 'transfer-2', item: '—转入第二阶段', stage1: 0, stage2: 0, stage3: 0, editable: true },
  { key: 'transfer-3', item: '—转入第三阶段', stage1: 0, stage2: 0, stage3: 0, editable: true },
  { key: 'return-2', item: '—转回第二阶段', stage1: 0, stage2: 0, stage3: 0, editable: true },
  { key: 'return-1', item: '—转回第一阶段', stage1: 0, stage2: 0, stage3: 0, editable: true },
  { key: 'provision', item: '本期计提', stage1: 0, stage2: 0, stage3: 0, editable: true },
  { key: 'reversal', item: '本期转回', stage1: 0, stage2: 0, stage3: 0, editable: true },
  { key: 'transfer-out', item: '本期转销', stage1: 0, stage2: 0, stage3: 0, editable: true },
  { key: 'write-off', item: '本期核销', stage1: 0, stage2: 0, stage3: 0, editable: true },
  { key: 'other', item: '其他变动', stage1: 0, stage2: 0, stage3: 0, editable: true },
])

function g6StageDefaults(): G4StageBlock[] {
  return buildDefaultSoeStageBlocks().map(block => ({
    ...block,
    title: block.title.replace('债权投资', '其他债权投资'),
  }))
}

const stageBlocks = ref<G4StageBlock[]>(g6StageDefaults())
const noteText = ref('')
const stageMethods: G4StageMethod[] = ['individual', 'portfolio']
const movementStages: Array<{ key: MovementAmountKey; label: string }> = [
  { key: 'stage1', label: '第一阶段' },
  { key: 'stage2', label: '第二阶段' },
  { key: 'stage3', label: '第三阶段' },
]

const standards = computed<string[]>(() => {
  const raw =
    props.htmlData?.applicable_standards
    ?? props.htmlData?.render_config?.applicable_standards
    ?? []
  return Array.isArray(raw) ? raw.map(String) : []
})
const currentStandard = computed(() =>
  standards.value.find(s => s === 'soe_standalone' || s === 'soe_consolidated')
  ?? 'soe_standalone',
)
const noteSection = computed(() =>
  currentStandard.value === 'soe_consolidated' ? '五、17' : '八、16',
)

function n(value: unknown): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function fmt(value: unknown): string {
  const amount = n(value)
  return amount === 0
    ? '-'
    : amount.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRate(value: number | null | undefined): string {
  return value == null || Number.isNaN(value) ? '—' : `${value.toFixed(2)}%`
}

function readResponse(key: string): string {
  const direct = props.allResponses?.get(key)
  if (direct?.remark || direct?.conclusion) return direct.remark || direct.conclusion || ''
  const map = props.htmlData?.checklist_responses
  if (map?.[key]) {
    const item = map[key]
    return typeof item === 'object' ? item.remark || item.conclusion || '' : String(item)
  }
  const list = props.htmlData?.responses
  if (Array.isArray(list)) {
    const item = list.find((entry: any) => entry?.item_id === key)
    return item?.remark || item?.conclusion || ''
  }
  return ''
}

function saveResponse(key: string, remark: string): void {
  if (props.isReadonly) return
  window.dispatchEvent(new CustomEvent('g6:save-items', {
    detail: { items: [{ item_id: key, conclusion: null, remark }] },
  }))
}

function persistStructured(): void {
  saveResponse(STRUCTURED_KEY, JSON.stringify({
    version: 2,
    balanceRows: balanceRows.value,
    importantRows: importantRows.value,
    movementRows: movementRows.value,
  }))
}

function persistStages(): void {
  saveResponse(STAGES_KEY, serializeStageBlocks(stageBlocks.value))
}

function persistNote(): void {
  saveResponse(TEXT_KEY, noteText.value)
  window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
    detail: {
      wpCode: 'G6',
      accountCode: ACCOUNT_CODE,
      section: 'soe',
      text: noteText.value,
      timestamp: Date.now(),
    },
  }))
}

function loadPersisted(): boolean {
  let found = false
  const structured = readResponse(STRUCTURED_KEY)
  if (structured) {
    try {
      const parsed = JSON.parse(structured)
      if (Array.isArray(parsed.balanceRows)) balanceRows.value = parsed.balanceRows
      if (Array.isArray(parsed.importantRows)) importantRows.value = parsed.importantRows
      if (Array.isArray(parsed.movementRows)) movementRows.value = parsed.movementRows
      found = true
    } catch { /* invalid legacy payload */ }
  }
  const parsedStages = parseStageBlocks(readResponse(STAGES_KEY))
  if (parsedStages) {
    const ids = new Set(g6StageDefaults().map(block => block.id))
    stageBlocks.value = parsedStages
      .filter(block => ids.has(block.id))
      .map(block => ({ ...block, title: block.title.replace('债权投资', '其他债权投资') }))
    found = true
  }
  noteText.value = readResponse(TEXT_KEY)
  return found
}

function parseJson(raw: string): any {
  if (!raw) return null
  try { return JSON.parse(raw) } catch { return null }
}

function refreshFromSources(force = false): void {
  const adjudication = parseJson(readResponse('G6-1-rows')) || {}
  let fvEnd = 0
  let fvOpening = 0
  balanceRows.value = balanceRows.value.map((row, index) => {
    const source = adjudication[`fv-item-${index + 1}`] || {}
    const endingBalance = n(source.closingUnadjusted) + n(source.closingAdjustment)
    const openingBalance = n(source.openingUnadjusted) + n(source.openingAdjustment)
    fvEnd += endingBalance
    fvOpening += openingBalance
    return {
      item: String(source.itemLabel || row.item),
      endingBalance: force || !row.endingBalance ? endingBalance : row.endingBalance,
      openingBalance: force || !row.openingBalance ? openingBalance : row.openingBalance,
    }
  })
  sourceFvEnd.value = fvEnd
  sourceFvOpening.value = fvOpening

  const detail = parseJson(readResponse('G6-2-rows'))
  if (Array.isArray(detail)) {
    const rows = detail.filter((row: any) => row?.investProject || n(row?.closingAudited)).slice(0, 4)
    importantRows.value = importantRows.value.map((current, index) => {
      const row = rows[index]
      if (!row) return current
      return {
        item: String(row.investProject || current.item),
        faceValue: n(row.faceValue),
        amortizedCost: n(row.closingSubtotal),
        fairValue: n(row.closingAudited || row.closingFairValue),
        ociCumulative: n(row.closingCumulativeFvChange),
        impairment: current.impairment,
      }
    })
  }

  const badDebt = parseJson(readResponse('G6-3-rows'))
  if (Array.isArray(badDebt)) {
    sourceProvisionEnd.value = badDebt.reduce((sum: number, row: any) => {
      const closingUnadjusted =
        n(row.openingUnadjusted)
        + n(row.provisionIncrease)
        + n(row.otherIncrease)
        - n(row.reversal)
        - n(row.writeOff)
        - n(row.otherDecrease)
      return sum + closingUnadjusted + n(row.closingAdjustment)
    }, 0)
  }

  persistStructured()
  if (force) ElMessage.success('已从 G6-1/G6-2/G6-3 更新可自动承接的数据')
}

const balanceTotals = computed(() => ({
  ending: balanceRows.value.reduce((sum, row) => sum + n(row.endingBalance), 0),
  opening: balanceRows.value.reduce((sum, row) => sum + n(row.openingBalance), 0),
}))
const importantTotals = computed(() =>
  importantRows.value.reduce(
    (sum, row) => ({
      faceValue: sum.faceValue + n(row.faceValue),
      amortizedCost: sum.amortizedCost + n(row.amortizedCost),
      fairValue: sum.fairValue + n(row.fairValue),
      impairment: sum.impairment + n(row.impairment),
    }),
    { faceValue: 0, amortizedCost: 0, fairValue: 0, impairment: 0 },
  ),
)

function tieOut(actual: number, expected: number) {
  const diff = Math.round((actual - expected) * 100) / 100
  return { diff, matched: Math.abs(diff) < 0.01 }
}

const balanceTieOut = computed(() => tieOut(balanceTotals.value.ending, sourceFvEnd.value))
const stageProvisionTotal = computed(() =>
  stageBlocks.value.reduce((sum, block) => sum + stageTotals(block).impairment, 0),
)
const stageTieOut = computed(() => tieOut(stageProvisionTotal.value, sourceProvisionEnd.value))

function movementTotal(row: MovementRow): number {
  return n(row.stage1) + n(row.stage2) + n(row.stage3)
}

function closingByStage(key: MovementAmountKey): number {
  const get = (rowKey: string) => n(movementRows.value.find(row => row.key === rowKey)?.[key])
  return (
    get('opening')
    + get('transfer-2')
    + get('transfer-3')
    + get('return-2')
    + get('return-1')
    + get('provision')
    - get('reversal')
    - get('transfer-out')
    - get('write-off')
    + get('other')
  )
}

const movementClosing = computed(() =>
  closingByStage('stage1') + closingByStage('stage2') + closingByStage('stage3'),
)
const movementTieOut = computed(() => tieOut(movementClosing.value, sourceProvisionEnd.value))

interface DisplayStageRow {
  id: string
  kind: 'parent' | 'detail'
  name: string
  bookBalance: number
  impairment: number
  bookValue: number
  ratePct: number | null
  reason: string
}

function methodRows(block: G4StageBlock, method: G4StageMethod): DisplayStageRow[] {
  const source = method === 'individual' ? block.individual : block.portfolio
  const total = methodTotals(source)
  return [
    {
      id: `${block.id}-${method}-parent`,
      kind: 'parent',
      name: method === 'individual' ? '按单项计提减值准备' : '按组合计提减值准备',
      ...total,
      reason: '',
    },
    ...source.details.map(detail => ({
      id: detail.id,
      kind: 'detail' as const,
      name: detail.name,
      bookBalance: detail.bookBalance,
      impairment: detail.impairment,
      bookValue: bookValue(detail.bookBalance, detail.impairment),
      ratePct: eclRatePct(detail.impairment, detail.bookBalance),
      reason: detail.reason,
    })),
  ]
}

function stageTotal(block: G4StageBlock) {
  return stageTotals(block)
}

function addStageRow(blockId: string, method: G4StageMethod): void {
  stageBlocks.value = addStageDetail(stageBlocks.value, blockId, method)
  persistStages()
}

function removeStageRow(blockId: string, method: G4StageMethod, detailId: string): void {
  stageBlocks.value = removeStageDetail(stageBlocks.value, blockId, method, detailId)
  persistStages()
}

function patchStageRow(
  blockId: string,
  method: G4StageMethod,
  detailId: string,
  patch: Partial<Pick<G4StageDetailRow, 'name' | 'bookBalance' | 'impairment' | 'reason'>>,
): void {
  stageBlocks.value = patchStageDetail(stageBlocks.value, blockId, method, detailId, patch)
  persistStages()
}

function buildSyncData(): Record<string, Record<string, unknown>[]> {
  return {
    其他债权投资情况: [
      ...balanceRows.value.map(row => ({
        label: row.item,
        end_balance: n(row.endingBalance),
        prior_balance: n(row.openingBalance),
        row_type: 'data',
      })),
      {
        label: '合计',
        end_balance: balanceTotals.value.ending,
        prior_balance: balanceTotals.value.opening,
        row_type: 'subtotal',
        is_total: true,
      },
    ],
    期末重要的其他债权投资: importantRows.value.map(row => ({
      label: row.item,
      face_value: n(row.faceValue),
      amortized_cost: n(row.amortizedCost),
      fair_value: n(row.fairValue),
      oci_cumulative: n(row.ociCumulative),
      impairment: n(row.impairment),
      row_type: 'data',
    })),
    减值准备计提情况: stageBlocks.value.flatMap(block =>
      stageMethods.flatMap(method =>
        (method === 'individual' ? block.individual : block.portfolio).details.map(row => ({
          stage: block.stage,
          method,
          label: row.name,
          book_balance: n(row.bookBalance),
          impairment: n(row.impairment),
          book_value: bookValue(row.bookBalance, row.impairment),
          reason: row.reason,
          row_type: 'data',
        })),
      ),
    ),
    减值准备变动: [
      ...movementRows.value.map(row => ({
        label: row.item,
        stage1: n(row.stage1),
        stage2: n(row.stage2),
        stage3: n(row.stage3),
        total: movementTotal(row),
        row_type: 'data',
      })),
      {
        label: '期末余额',
        stage1: closingByStage('stage1'),
        stage2: closingByStage('stage2'),
        stage3: closingByStage('stage3'),
        total: movementClosing.value,
        row_type: 'subtotal',
        is_total: true,
      },
    ],
    _note_texts: [{ section: 'soe-audit-note', text: noteText.value }],
  }
}

async function syncToDisclosureNotes(): Promise<void> {
  if (isSyncing.value || !props.projectId || props.isReadonly) return
  isSyncing.value = true
  try {
    const result: any = await api.post(
      `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
      {
        wp_id: props.wpId,
        sheet_name: '附注披露信息（国企）',
        section_id: noteSection.value,
        current_standard: currentStandard.value,
        sub_table_data: buildSyncData(),
      },
    )
    const data = result?.data ?? result
    ElMessage.success(`已同步 ${Number(data?.rows_synced ?? 0)} 行到附注模块“${noteSection.value} 其他债权投资”`)
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}

async function fillAiDraft(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'disclosure-soe-note',
    noteText.value,
    {
      期末公允价值: balanceTotals.value.ending,
      期末减值准备: sourceProvisionEnd.value,
      三阶段减值合计: stageProvisionTotal.value,
    },
    'AI 国企附注披露',
  )
  if (text) {
    noteText.value = text
    persistNote()
  }
}

function handleAdjudicated(event: Event): void {
  const detail = (event as CustomEvent<{ accountCode: string }>).detail
  if (detail?.accountCode === ACCOUNT_CODE) refreshFromSources(false)
}

onMounted(() => {
  const hadPersisted = loadPersisted()
  refreshFromSources(!hadPersisted)
  window.addEventListener('substantive:adjudicated', handleAdjudicated)
})
onBeforeUnmount(() => {
  window.removeEventListener('substantive:adjudicated', handleAdjudicated)
})
</script>

<style scoped>
.g6-disclosure-soe { padding: 12px; font-size: var(--wp-font-size, 13px); }
.sheet-title { margin: 0; font-size: 16px; }
.cross-index { margin-top: 4px; color: #909399; font-size: 12px; }
.objective-alert { margin-bottom: 12px; }
.section-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin: 18px 0 8px; }
.section-head.first { margin-top: 0; }
.section-head h4 { margin: 0; font-size: 14px; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.hint { color: #909399; font-size: 12px; }
.table-total { padding: 7px 10px; text-align: right; background: #f5f7fa; color: #606266; font-size: 12px; }
.stage-tip { margin-bottom: 10px; }
.stage-card { margin-bottom: 12px; }
.method-block { margin-bottom: 10px; }
.method-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; color: #c00; font-weight: 600; }
.amt-input { width: 112px; }
.note-card { margin-top: 16px; }
.note-head { margin: 0; }
.prep-hint { margin-top: 16px; color: #909399; font-size: 12px; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
</style>
