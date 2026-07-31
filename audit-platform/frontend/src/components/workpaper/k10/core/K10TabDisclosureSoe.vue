<template>
  <div class="k10-tab-disclosure-soe">
    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>按补助来源简要披露其他收益金额（国企版）。数据来源K10-1审定表，subscribe 'substantive:adjudicated' 事件自动刷新。国企版17行×6列，相比上市版结构更简洁。</p>
    </div>

    <!-- ═══ 主表：其他收益披露（国企） ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">其他收益附注披露（国企）</span>
          <div class="section-actions">
            <el-button size="small" type="primary" link @click="applyAutoFill">
              <el-icon><Refresh /></el-icon>从审定表取数
            </el-button>
            <el-button size="small" type="primary" link @click="generateAI('disclosure-soe')">
              <el-icon><MagicStick /></el-icon>AI辅助
            </el-button>
            <el-button size="small" type="success" :disabled="isReadonly" @click="syncToDisclosureNotes">同步到附注</el-button>
            <GtReviewTrigger section-id="K10-disclosure-soe" label="💬 复核" />
          </div>
        </div>
      </template>

      <el-table
        :data="disclosureRows"
        border
        size="small"
        show-summary
        :summary-method="summaryMethod"
        class="disclosure-table"
      >
        <el-table-column prop="category" label="项目" min-width="180" />
        <el-table-column prop="currentAmount" label="本期发生额" min-width="130" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              v-model="row.currentAmount"
              @change="handleRowChange(row)"
            />
            <span v-else :class="{ 'amount-zero': !row.currentAmount }">{{ fmtAmt(row.currentAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="priorAmount" label="上期发生额" min-width="130" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              v-model="row.priorAmount"
              @change="handleRowChange(row)"
            />
            <span v-else>{{ fmtAmt(row.priorAmount) }}</span>
          </template>
        </el-table-column>
        <!-- 源模板国企侧第 4 列（附注 §八、69 headers[3]），交互点选 -->
        <el-table-column prop="isGovGrant" label="是否为政府补助" width="140">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.isGovGrant"
              size="small"
              style="width: 100%"
              placeholder="请选择"
              @change="handleRowChange(row)"
            >
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
            <span v-else>{{ row.isGovGrant || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="同比变动" min-width="100" align="right">
          <template #default="{ row }">
            <span :class="{ 'abnormal-rate': isAbnormal(row) }">{{ formatRate(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="说明" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.remark"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              placeholder="披露说明"
              @change="handleRowChange(row)"
            />
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 审计说明（AI辅助） ═══ -->
    <el-card shadow="never" class="narrative-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">附注披露说明</span>
          <el-button size="small" type="primary" link @click="generateAI('narrative')">
            <el-icon><MagicStick /></el-icon>AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="narrativeText"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 6 }"
        :readonly="isReadonly"
        placeholder="输入其他收益附注披露说明（国企版简要格式）..."
        @change="handleNarrativeSave"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-tips">
      <summary>编制提示</summary>
      <ul>
        <li>国企版附注披露结构较简洁（17行×6列），重点在金额披露</li>
        <li>数据从K10-1审定表自动取数，点击「从审定表取数」</li>
        <li>订阅 'substantive:adjudicated' 事件自动刷新</li>
        <li>variant='soe'（国企版）</li>
        <li>与上市版区别：无需按补助类型/确认方式细分，按来源汇总即可</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K10TabDisclosureSoe.vue — K10 附注披露信息（国企）
 *
 * Spec: .kiro/specs/k10-other-income/
 * Task: 4.6
 * Requirements: 7.1
 *
 * 功能：
 * - 17行×6列国企版附注披露
 * - 同K10TabDisclosureListed模式但更简洁
 * - Subscribe 'substantive:adjudicated' EventBus刷新
 * - variant='soe'
 * - AI辅助按钮
 */
import { ref, computed, onMounted, onUnmounted, onBeforeUnmount } from 'vue'
import { fmtAmount } from '@/utils/formatters'
import { ElMessage } from 'element-plus'
import { Refresh, MagicStick } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'
import http from '@/utils/http'
import { api } from '@/services/apiProxy'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { buildK10SyncPayload } from '../../composables/k10NoteSectionMap'

// ─── Props & Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────
const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── Auto-sync to disclosure notes ──────────────────────────────────────────
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })

onBeforeUnmount(() => autoSync.cancelPending())

async function syncToDisclosureNotes(): Promise<void> {
  if (!props.projectId || props.isReadonly) return
  // 🔴 行模型字段是 `category`，旧载荷读 `project` → 曾把标签推成空串；
  // 第 4 列「是否为政府补助」与合计后的「其中：政府补助」结构行按源模板行序推送
  const detail = disclosureRows.value.map(r => ({
    project: r.category,
    currentAmount: r.currentAmount,
    priorAmount: r.priorAmount,
    isGovGrant: r.isGovGrant,
  }))
  const govGrantRow = disclosureRows.value
    .filter(r => r.isGovGrant === '是')
    .reduce(
      (acc, r) => ({
        currentAmount: acc.currentAmount + (Number(r.currentAmount) || 0),
        priorAmount: acc.priorAmount + (Number(r.priorAmount) || 0),
      }),
      { currentAmount: 0, priorAmount: 0 },
    )
  const payload = buildK10SyncPayload(
    'soe',
    props.wpId || '',
    detail,
    narrativeText.value,
    govGrantRow,
  )
  try {
    await http.post(`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`, payload)
    eventBus.emit('disclosure:note-text-updated' as any, {
      wpCode: 'K10', variant: 'soe', accountCode: '6117',
      projectId: props.projectId, sectionIds: ['八、69'],
    })
    ElMessage.success('已同步到附注')
  } catch { /* silent */ }
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ABNORMAL_THRESHOLD = 0.5

/** 国企版来源分类（简洁版） */
const CATEGORIES = [
  '政府补助',
  '即征即退',
  '财政贴息',
  '研发补助',
  '稳岗补贴',
  '其他补贴收入',
  '个税手续费返还',
]

// ─── Types ───────────────────────────────────────────────────────────────────

interface DisclosureRow {
  category: string
  currentAmount: number
  priorAmount: number
  /** 附注 §八、69 第 4 列「是否为政府补助」（源模板国企侧独有） */
  isGovGrant: string
  remark: string
}

// ─── State ───────────────────────────────────────────────────────────────────

/** 固定分类中语义上即政府补助的项目，作为第 4 列默认值（可人工改选） */
const GOV_GRANT_DEFAULT = new Set(['政府补助', '即征即退', '财政贴息', '研发补助', '稳岗补贴'])

const disclosureRows = ref<DisclosureRow[]>(
  CATEGORIES.map(c => ({
    category: c,
    currentAmount: 0,
    priorAmount: 0,
    isGovGrant: GOV_GRANT_DEFAULT.has(c) ? '是' : '否',
    remark: '',
  }))
)
const narrativeText = ref('')

// ─── Load saved data ─────────────────────────────────────────────────────────

function loadSavedData(): void {
  for (let i = 0; i < CATEGORIES.length; i++) {
    const key = `K10-disc-soe-row-${i}`
    const saved = props.allResponses.get(key)
    if (saved) {
      try {
        const parsed = typeof saved.remark === 'string' ? JSON.parse(saved.remark) : saved.remark
        if (parsed) {
          disclosureRows.value[i] = {
            category: CATEGORIES[i],
            currentAmount: Number(parsed.currentAmount || 0),
            priorAmount: Number(parsed.priorAmount || 0),
            isGovGrant: parsed.isGovGrant
              || (GOV_GRANT_DEFAULT.has(CATEGORIES[i]) ? '是' : '否'),
            remark: parsed.remark || '',
          }
        }
      } catch { /* ignore */ }
    }
  }
  loadDynamicRows()
  const narrativeSaved = props.allResponses.get('K10-disclosure-soe-narrative')
  if (narrativeSaved) {
    narrativeText.value = narrativeSaved.remark || narrativeSaved.conclusion || ''
  }
}

const DYN_PREFIX = 'K10-disc-soe-dyn-'

/** 加载动态追加行（K10-1 中不在固定 CATEGORIES 的来源） */
function loadDynamicRows(): void {
  disclosureRows.value = disclosureRows.value.slice(0, CATEGORIES.length)
  for (const [key, saved] of props.allResponses) {
    if (!key.startsWith(DYN_PREFIX)) continue
    try {
      const parsed = typeof saved.remark === 'string' ? JSON.parse(saved.remark) : saved.remark
      if (parsed && parsed.category) {
        disclosureRows.value.push({
          category: parsed.category,
          currentAmount: Number(parsed.currentAmount || 0),
          priorAmount: Number(parsed.priorAmount || 0),
          isGovGrant: parsed.isGovGrant || '否',
          remark: parsed.remark || '',
        })
      }
    } catch { /* ignore */ }
  }
}

// ─── Auto-fill from K10-1（读 K10-1-rows JSON，按来源名称匹配） ───────────────

/** 从审定表 K10-1-rows 构建 名称→审定数 映射 */
function buildAdjAuditedMap(): Map<string, number> {
  const map = new Map<string, number>()
  const raw = props.allResponses.get('K10-1-rows')
  if (!raw) return map
  try {
    const parsed = typeof raw.remark === 'string' ? JSON.parse(raw.remark) : raw.remark
    if (Array.isArray(parsed)) {
      for (const r of parsed) {
        const name = String(r?.name ?? '').trim()
        if (!name) continue
        const audited = Number(r?.audited ?? 0)
          || (Number(r?.unadjusted ?? 0) + Number(r?.aje ?? 0) + Number(r?.rje ?? 0))
        map.set(name, audited)
      }
    }
  } catch { /* ignore */ }
  return map
}

function applyAutoFill(): void {
  const adjMap = buildAdjAuditedMap()
  if (adjMap.size === 0) {
    ElMessage.warning('未找到 K10-1 审定表数据，请先编制审定表')
    return
  }
  const matchedNames = new Set<string>()
  let matched = 0
  for (let i = 0; i < CATEGORIES.length; i++) {
    let val = adjMap.get(CATEGORIES[i])
    let hitName = CATEGORIES[i]
    if (val == null) {
      for (const [name, amt] of adjMap) {
        if (CATEGORIES[i].includes(name) || name.includes(CATEGORIES[i])) { val = amt; hitName = name; break }
      }
    }
    if (val != null && val !== 0) {
      disclosureRows.value[i].currentAmount = val
      handleRowChange(disclosureRows.value[i])
      matchedNames.add(hitName)
      matched++
    }
  }
  // 追加：K10-1 中未匹配任何固定分类的来源 → 动态披露行
  loadDynamicRows()
  for (const [name, amt] of adjMap) {
    if (matchedNames.has(name) || amt === 0) continue
    const existing = disclosureRows.value.find(r => r.category === name)
    if (existing) {
      existing.currentAmount = amt
      persistDynamicRow(existing)
    } else {
      const row: DisclosureRow = {
        category: name,
        currentAmount: amt,
        priorAmount: 0,
        isGovGrant: '否',
        remark: '',
      }
      disclosureRows.value.push(row)
      persistDynamicRow(row)
    }
    matched++
  }
  ElMessage.success(matched > 0 ? `已从审定表取数（匹配 ${matched} 项）` : '审定表暂无可匹配来源金额')
}

/** 持久化动态追加行（name-keyed） */
function persistDynamicRow(row: DisclosureRow): void {
  const safeKey = DYN_PREFIX + row.category.replace(/[^\w\u4e00-\u9fa5]/g, '_')
  emit('save', safeKey, {
    category: row.category,
    currentAmount: row.currentAmount,
    priorAmount: row.priorAmount,
    isGovGrant: row.isGovGrant,
    remark: row.remark,
  })
}

// ─── EventBus subscribe ──────────────────────────────────────────────────────

function handleAdjudicated(payload: any): void {
  if (!payload) return
  if (payload.accountCode === '6117' || payload.wpCode === 'K10') {
    applyAutoFill()
  }
}

// ─── Save handlers ───────────────────────────────────────────────────────────

function handleRowChange(row: DisclosureRow): void {
  const idx = disclosureRows.value.indexOf(row)
  if (idx < 0) return
  if (idx >= CATEGORIES.length) {
    persistDynamicRow(row)
    autoSync.scheduleAutoSync(syncToDisclosureNotes)
    return
  }
  emit('save', `K10-disc-soe-row-${idx}`, {
    currentAmount: row.currentAmount,
    priorAmount: row.priorAmount,
    isGovGrant: row.isGovGrant,
    remark: row.remark,
  })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function handleNarrativeSave(): void {
  emit('save', 'K10-disclosure-soe-narrative', { remark: narrativeText.value })
  eventBus.emit('disclosure:note-text-updated' as any, {
    noteId: 'other_income',
    wpCode: 'K10',
    variant: 'soe',
    text: narrativeText.value,
  })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

// ─── AI generation ───────────────────────────────────────────────────────────

async function generateAI(section: string): Promise<void> {
  if (!props.wpId) return
  try {
    const res = await api.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section,
      prompt: `为K10其他收益底稿生成国企附注披露文本。来源分类：${CATEGORIES.join('/')}。口径以致同 2025 修订版底稿源模板与附注模版为准；只能使用已提供的项目名称与金额，不得虚构项目、金额或业务背景，无把握的内容留空由审计师补充。`,
      context: {
        来源分类: CATEGORIES.join('/'),
        本期合计: String(totalCurrentAmount.value),
        明细: disclosureRows.value.map(r => `${r.category}:本期${r.currentAmount}`).join('；'),
      },
    })
    const content = res?.data?.content || res?.content || ''
    if (content && section === 'narrative') {
      narrativeText.value = content
      handleNarrativeSave()
    }
    ElMessage.success('AI生成完成')
  } catch {
    ElMessage.warning('AI生成失败，请手动填写')
  }
}

function handleReview(): void {
  openReviewDialog?.('K10-disclosure-soe', '其他收益附注披露（国企）')
}

// ─── Table helpers ───────────────────────────────────────────────────────────

const totalCurrentAmount = computed(() =>
  disclosureRows.value.reduce((s, r) => s + (r.currentAmount || 0), 0)
)

function summaryMethod({ columns }: { columns: any[]; data: DisclosureRow[] }): string[] {
  return columns.map((col: any, idx: number) => {
    if (idx === 0) return '合计'
    if (col.property === 'currentAmount') return fmtAmt(totalCurrentAmount.value)
    if (col.property === 'priorAmount') {
      return fmtAmt(disclosureRows.value.reduce((s, r) => s + (r.priorAmount || 0), 0))
    }
    return ''
  })
}

function isAbnormal(row: DisclosureRow): boolean {
  if (!row.priorAmount || row.priorAmount === 0) return false
  return Math.abs((row.currentAmount - row.priorAmount) / row.priorAmount) > ABNORMAL_THRESHOLD
}

function formatRate(row: DisclosureRow): string {
  if (!row.priorAmount || row.priorAmount === 0) return '—'
  return (((row.currentAmount - row.priorAmount) / row.priorAmount) * 100).toFixed(1) + '%'
}

/** 只读金额展示：委托平台金额格式单一真源，保留底稿「0 显示 -」语义 */
function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return fmtAmount(val)
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  loadSavedData()
  eventBus.on('substantive:adjudicated' as any, handleAdjudicated)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated' as any, handleAdjudicated)
})
</script>

<style scoped>
.k10-tab-disclosure-soe {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 12px 16px;
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
  color: #6b5900;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.section-title {
  font-weight: 600;
  font-size: 14px;
}

.section-actions {
  display: flex;
  gap: 8px;
}

.disclosure-card,
.narrative-card {
  margin: 0;
}

.disclosure-table {
  font-size: var(--wp-font-size, 13px);
}

.amount-zero {
  color: var(--el-text-color-placeholder);
}

.abnormal-rate {
  color: var(--el-color-danger);
  font-weight: 600;
}

.compile-tips {
  margin-top: 8px;
  padding: 8px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.compile-tips summary {
  cursor: pointer;
  font-weight: 500;
}

.compile-tips ul {
  margin: 8px 0 0;
  padding-left: 20px;
}
</style>
