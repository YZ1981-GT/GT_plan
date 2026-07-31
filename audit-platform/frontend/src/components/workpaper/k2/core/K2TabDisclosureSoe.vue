<template>
  <div class="k2-disclosure-soe">
    <!-- 方法论上下文（源模板原文，禁改写） -->
    <div class="methodology-block">
      <div class="methodology-title">源模板要求（附注披露信息（国企））</div>
      <div class="methodology-content">
        其他流动资产（根据性质选择披露方式）<br />
        <span class="methodology-sub">
          附注 §八、14 为单表列示：项目 / 期末余额 / 期初余额，8 个固定行取自附注模版。
          数据来源：审定表 K2-1 / 明细表 K2-2。
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

    <!-- 其他流动资产明细列示 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-title-row">
          <span class="section-title">其他流动资产</span>
          <div class="title-actions">
            <el-button size="small" :disabled="isReadonly" @click="addMainRow">新增明细行</el-button>
            <el-button size="small" type="default" link @click="handleReview('K2-disc-soe-main')">💬</el-button>
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
        <el-table-column label="期初余额" width="180" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="row.priorAmount"
              :aria-label="`期初余额 ${row.label}`"
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

    <!-- 文本说明区 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-title-row">
          <span class="section-title">其他流动资产说明</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link :disabled="isReadonly" @click="handleAiGenerate">
              <el-icon><MagicStick /></el-icon> AI辅助
            </el-button>
            <el-button size="small" type="default" link @click="handleReview('K2-disc-soe-text')">💬</el-button>
          </div>
        </div>
      </template>
      <div class="seg-requirement">{{ SOE_REQUIREMENT }}</div>
      <el-input
        v-model="noteText"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="按性质说明其他流动资产的构成、内容与重分类依据"
        @change="onTextChange"
      />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>列结构对齐附注 §八、14：项目 / 期末余额 / 期初余额，合计行自动汇总。</li>
        <li>8 个固定行名取自附注模版；项目实际存在其他项目时用「新增明细行」补充。</li>
        <li>源模板要求根据性质选择披露方式；重分类事项属于其他非流动资产的应在该科目列示。</li>
        <li>录入后 800ms 自动同步到附注；也可点「同步到附注」立即推送。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K2TabDisclosureSoe.vue — 附注披露信息（国企）
 *
 * 结构对齐 note_template_soe.json §八、14（交付物权威）：
 * 单表「其他流动资产」，3 列（项目 / 期末余额 / 期初余额）+ 8 固定行 + 合计。
 *
 * 历史版本是自造的 6 列变动矩阵（期末/期初/增加/减少/变动原因），与附注不符，已废止。
 *
 * spec: .kiro/specs/k2-other-current-assets-disclosure-alignment/ R1 R3
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
  K2_NOTE_SECTION,
  K2_SOE_MAIN_ROWS,
  K2_TOTAL_ROW_LABEL,
  buildK2SyncPayload,
} from '../../composables/k2NoteSectionMap'
import { checkK2Consistency, k2ConsistencySummary } from '../../composables/useK2DisclosureEngine'
import { K2_ACCOUNT_NAME, K2_GROSS_FALLBACK_STANDARD } from '../../composables/k2AccountScope'

/**
 * 科目口径取单一真源（报表行 `BS-014` → 实证 `TB('1901')`）。
 * 🔴 历史写死 `1231` = 应收款项坏账准备，与其他流动资产无关。
 */
const K2_ACCOUNT_CODE = K2_GROSS_FALLBACK_STANDARD

/** 逐字取自 note_template_soe.json §八、14 text_sections[0] */
const SOE_REQUIREMENT =
  '（根据性质选择披露方式）【提示：待抵扣进项税额，根据应交税费-应交增值税科目借方余额分析填列；'
  + '预缴税金中的增值税额，根据应交税费-未交增值税科目以及应交税费-预交增值税科目借方余额分析填列；'
  + '上述重分类事项，如属于其他非流动资产的，应在其他非流动资产科目列示。】'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{ save: [itemId: string, value: any] }>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })

interface MainRow {
  label: string
  endAmount: number
  priorAmount: number
  fixed: boolean
}

const mainRows = reactive<MainRow[]>(
  K2_SOE_MAIN_ROWS.map(label => ({ label, endAmount: 0, priorAmount: 0, fixed: true })),
)

const noteText = ref('')
const checkExpanded = ref(false)

const mainTotalRow = computed(() => ({
  label: K2_TOTAL_ROW_LABEL,
  endAmount: mainRows.reduce((s, r) => s + (Number(r.endAmount) || 0), 0),
  priorAmount: mainRows.reduce((s, r) => s + (Number(r.priorAmount) || 0), 0),
}))

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
    variant: 'soe',
    mainRows,
    auditedEnd: responseNumber('K2-1-audited-total'),
    auditedPrior: responseNumber('K2-1-begin-total'),
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

function onTextChange(): void {
  persistText()
}

// ═══ 持久化 ═══
function persist(itemId: string, payload: unknown): void {
  emit('save', itemId, JSON.stringify(payload))
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function persistMain(): void {
  persist('K2-disc-soe-main', mainRows.map(r => ({ ...r })))
}

function persistText(): void {
  persist('K2-disc-soe-text', { text: noteText.value })
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
  const savedMain = parseSaved('K2-disc-soe-main')
  if (Array.isArray(savedMain) && savedMain.length) {
    mainRows.splice(0, mainRows.length, ...savedMain.map((r: any) => ({
      label: String(r?.label ?? ''),
      endAmount: Number(r?.endAmount) || 0,
      priorAmount: Number(r?.priorAmount) || 0,
      fixed: K2_SOE_MAIN_ROWS.includes(String(r?.label ?? '')),
    })))
  }
  const savedText = parseSaved('K2-disc-soe-text')
  if (savedText && typeof savedText === 'object') noteText.value = String(savedText.text ?? '')
}

// ═══ 同步到附注 ═══
async function syncToDisclosureNotes(): Promise<void> {
  if (!props.projectId || props.isReadonly) return
  const payload = buildK2SyncPayload('soe', props.wpId || '', {
    mainRows: mainRows.map(r => ({
      label: r.label,
      endAmount: r.endAmount,
      priorAmount: r.priorAmount,
    })),
    texts: noteText.value.trim()
      ? [{ section: 'k2-soe-note', title: '其他流动资产说明', text: noteText.value }]
      : [],
  })
  try {
    await http.post(`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`, payload)
    eventBus.emit('disclosure:note-text-updated' as any, {
      wpCode: 'K2',
      variant: 'soe',
      accountCode: K2_ACCOUNT_CODE,
      projectId: props.projectId,
      sectionIds: [K2_NOTE_SECTION.soe],
    })
  } catch {
    /* 静默：自动同步失败不打断录入 */
  }
}

// ═══ AI 辅助 ═══
const AI_PROMPT =
  '请依据致同 2025 修订版底稿 K2 源模板与国有企业财务报表附注格式要求，'
  + '就其他流动资产按性质撰写附注披露文字，说明其构成内容、性质以及待抵扣进项税额、'
  + '预缴税金等重分类事项的填列依据。只能使用已提供的项目名称与金额，'
  + '不得虚构项目、金额或业务背景；无把握的内容留空由审计师补充。'

async function handleAiGenerate(): Promise<void> {
  try {
    // 🔴 `context` 必须是 `dict[str,str]` —— 传字符串会 422 且被 catch 静默吞掉
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      prompt: AI_PROMPT,
      context: {
        accountCode: K2_ACCOUNT_CODE,
        accountName: K2_ACCOUNT_NAME,
        noteSection: K2_NOTE_SECTION.soe,
        variant: '国有企业',
        requirement: SOE_REQUIREMENT,
      },
      existingContent: noteText.value || '',
      section: 'k2-soe-note',
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
    noteText.value = noteText.value ? `${noteText.value}\n${generated}` : generated
    persistText()
    ElMessage.success('已填入 AI 生成内容')
  } catch {
    /* 取消或失败 */
  }
}

function handleReview(id: string): void {
  openReviewDialog(id)
}

onMounted(() => {
  loadSavedData()
})

onBeforeUnmount(() => {
  autoSync.cancelPending()
})
</script>

<style scoped>
.k2-disclosure-soe {
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
