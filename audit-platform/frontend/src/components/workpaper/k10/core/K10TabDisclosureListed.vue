<template>
  <div class="k10-tab-disclosure-listed">
    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>按补助来源披露本期其他收益金额（上市公司版）。数据来源K10-1审定表+K10-2明细表，subscribe 'substantive:adjudicated' 事件自动刷新。上市公司版38行×17列，含各补助类型本期/上期金额及比较。</p>
    </div>

    <!-- ═══ 主表：其他收益按补助来源分类披露 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">其他收益附注披露（上市公司）</span>
          <div class="section-actions">
            <el-button size="small" type="primary" link @click="applyAutoFill">
              <el-icon><Refresh /></el-icon>从审定表取数
            </el-button>
            <el-button size="small" type="primary" link @click="generateAI('disclosure-listed')">
              <el-icon><MagicStick /></el-icon>AI辅助
            </el-button>
            <el-button size="small" type="success" :disabled="isReadonly" @click="syncToDisclosureNotes">同步到附注</el-button>
            <GtReviewTrigger section-id="K10-disclosure-listed" label="💬 复核" />
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
        <el-table-column prop="category" label="项目（补助来源分类）" min-width="180" />
        <el-table-column prop="grantType" label="补助类型" width="120">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.grantType"
              size="small"
              style="width: 100%"
              placeholder="类型"
              @change="handleRowChange(row)"
            >
              <el-option label="与收益相关" value="与收益相关" />
              <el-option label="与资产相关" value="与资产相关" />
            </el-select>
            <span v-else>{{ row.grantType || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="recognitionMethod" label="确认方式" width="120">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.recognitionMethod"
              size="small"
              style="width: 100%"
              placeholder="方式"
              @change="handleRowChange(row)"
            >
              <el-option label="直接计入" value="直接计入" />
              <el-option label="递延分摊" value="递延分摊" />
            </el-select>
            <span v-else>{{ row.recognitionMethod || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="currentAmount" label="本期发生额" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.currentAmount"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="handleRowChange(row)"
            />
            <span v-else :class="{ 'amount-zero': !row.currentAmount }">{{ fmtAmt(row.currentAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="priorAmount" label="上期发生额" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.priorAmount"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="handleRowChange(row)"
            />
            <span v-else>{{ fmtAmt(row.priorAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="同比变动" min-width="100" align="right">
          <template #default="{ row }">
            <span :class="{ 'abnormal-rate': isAbnormal(row) }">{{ formatRate(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="proportion" label="占比" min-width="80" align="right">
          <template #default="{ row }">
            {{ formatProportion(row) }}
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="说明" min-width="180">
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

    <!-- ═══ 审计说明（AI辅助文本区域） ═══ -->
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
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="输入其他收益附注披露说明（含政府补助类型/确认方式/补助条件达成情况等）..."
        @change="handleNarrativeSave"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-tips">
      <summary>编制提示</summary>
      <ul>
        <li>数据优先从K10-1审定表自动拉取（按来源分类行），点击「从审定表取数」</li>
        <li>订阅 'substantive:adjudicated' 事件自动刷新</li>
        <li>上市公司需按《企业会计准则第16号——政府补助》分类披露</li>
        <li>披露要点：补助类型(与收益/资产相关) + 确认方式(直接计入/递延分摊) + 金额</li>
        <li>与日常活动相关的政府补助纳入其他收益（6117），非营业外收入</li>
        <li>variant='listed'（上市公司版，38行×17列结构）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K10TabDisclosureListed.vue — K10 附注披露信息（上市公司）
 *
 * Spec: .kiro/specs/k10-other-income/
 * Task: 4.6
 * Requirements: 7.1
 *
 * 功能：
 * - 38行×17列上市公司版附注披露
 * - 自动从K10-1/K10-2审定表+明细表取数（formula references）
 * - Subscribe 'substantive:adjudicated' EventBus刷新
 * - variant='listed'
 * - AI辅助按钮per section
 * - 补助来源分类+补助类型+确认方式+本期/上期/同比/占比
 */
import { ref, computed, onMounted, onUnmounted, onBeforeUnmount, inject } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, MagicStick } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'
import { api } from '@/services/apiProxy'
import http from '@/utils/http'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
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
  const payload = buildK10SyncPayload('listed', props.wpId || '', disclosureRows.value, narrativeText.value)
  try {
    await http.post(`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`, payload)
    eventBus.emit('disclosure:note-text-updated' as any, {
      wpCode: 'K10', variant: 'listed', accountCode: '6117',
      projectId: props.projectId, sectionIds: ['五、68'],
    })
    ElMessage.success('已同步到附注')
  } catch { /* silent */ }
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ABNORMAL_THRESHOLD = 0.5

/** 其他收益标准来源分类（与K10-1审定表行对应） */
const CATEGORIES = [
  '政府补助-即征即退',
  '政府补助-财政贴息',
  '政府补助-研发补助',
  '政府补助-稳岗补贴',
  '政府补助-资源税返还',
  '政府补助-产业扶持',
  '政府补助-其他',
  '其他收益-个税手续费返还',
  '其他收益-其他',
]

// ─── Types ───────────────────────────────────────────────────────────────────

interface DisclosureRow {
  category: string
  grantType: string
  recognitionMethod: string
  currentAmount: number
  priorAmount: number
  remark: string
}

// ─── State ───────────────────────────────────────────────────────────────────

const disclosureRows = ref<DisclosureRow[]>(
  CATEGORIES.map(c => ({
    category: c,
    grantType: c.startsWith('政府补助') ? '与收益相关' : '',
    recognitionMethod: '',
    currentAmount: 0,
    priorAmount: 0,
    remark: '',
  }))
)
const narrativeText = ref('')

// ─── Load saved data ─────────────────────────────────────────────────────────

function loadSavedData(): void {
  for (let i = 0; i < CATEGORIES.length; i++) {
    const key = `K10-disc-listed-row-${i}`
    const saved = props.allResponses.get(key)
    if (saved) {
      try {
        const parsed = typeof saved.remark === 'string' ? JSON.parse(saved.remark) : saved.remark
        if (parsed) {
          disclosureRows.value[i] = {
            category: CATEGORIES[i],
            grantType: parsed.grantType || disclosureRows.value[i].grantType,
            recognitionMethod: parsed.recognitionMethod || '',
            currentAmount: Number(parsed.currentAmount || 0),
            priorAmount: Number(parsed.priorAmount || 0),
            remark: parsed.remark || '',
          }
        }
      } catch { /* ignore */ }
    }
  }
  // 动态行（来自 K10-1 的非标准来源名，name-keyed 持久化）
  loadDynamicRows()
  const narrativeSaved = props.allResponses.get('K10-disclosure-listed-narrative')
  if (narrativeSaved) {
    narrativeText.value = narrativeSaved.remark || narrativeSaved.conclusion || ''
  }
}

const DYN_PREFIX = 'K10-disc-listed-dyn-'

/** 加载动态追加行（K10-1 中不在固定 CATEGORIES 的来源） */
function loadDynamicRows(): void {
  // 先移除已有动态行（避免重复），保留固定 CATEGORIES 行
  disclosureRows.value = disclosureRows.value.slice(0, CATEGORIES.length)
  for (const [key, saved] of props.allResponses) {
    if (!key.startsWith(DYN_PREFIX)) continue
    try {
      const parsed = typeof saved.remark === 'string' ? JSON.parse(saved.remark) : saved.remark
      if (parsed && parsed.category) {
        disclosureRows.value.push({
          category: parsed.category,
          grantType: parsed.grantType || '',
          recognitionMethod: parsed.recognitionMethod || '',
          currentAmount: Number(parsed.currentAmount || 0),
          priorAmount: Number(parsed.priorAmount || 0),
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
    // 精确名称匹配，回退子串匹配（如"政府补助-即征即退" ↔ "即征即退"）
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
  // 追加：K10-1 中未匹配任何固定分类的来源（如源模板动态项目名）→ 动态披露行
  loadDynamicRows()
  for (const [name, amt] of adjMap) {
    if (matchedNames.has(name) || amt === 0) continue
    const already = disclosureRows.value.some(r => r.category === name)
    if (already) {
      const r = disclosureRows.value.find(rr => rr.category === name)!
      r.currentAmount = amt
      persistDynamicRow(r)
    } else {
      const row: DisclosureRow = { category: name, grantType: '', recognitionMethod: '', currentAmount: amt, priorAmount: 0, remark: '' }
      disclosureRows.value.push(row)
      persistDynamicRow(row)
    }
    matched++
  }
  ElMessage.success(matched > 0 ? `已从审定表取数（匹配 ${matched} 项）` : '审定表暂无可匹配来源金额')
}

/** 持久化动态追加行（name-keyed，去除非法字符） */
function persistDynamicRow(row: DisclosureRow): void {
  const safeKey = DYN_PREFIX + row.category.replace(/[^\w\u4e00-\u9fa5]/g, '_')
  emit('save', safeKey, {
    category: row.category,
    grantType: row.grantType,
    recognitionMethod: row.recognitionMethod,
    currentAmount: row.currentAmount,
    priorAmount: row.priorAmount,
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
    // 动态追加行 → name-keyed 持久化
    persistDynamicRow(row)
    autoSync.scheduleAutoSync(syncToDisclosureNotes)
    return
  }
  emit('save', `K10-disc-listed-row-${idx}`, {
    grantType: row.grantType,
    recognitionMethod: row.recognitionMethod,
    currentAmount: row.currentAmount,
    priorAmount: row.priorAmount,
    remark: row.remark,
  })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function handleNarrativeSave(): void {
  emit('save', 'K10-disclosure-listed-narrative', { remark: narrativeText.value })
  eventBus.emit('disclosure:note-text-updated' as any, {
    noteId: 'other_income',
    wpCode: 'K10',
    variant: 'listed',
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
      prompt: `为K10其他收益底稿生成上市公司附注披露文本。来源分类：${CATEGORIES.join('/')}。`,
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
  openReviewDialog?.('K10-disclosure-listed', '其他收益附注披露（上市）')
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

function formatProportion(row: DisclosureRow): string {
  const total = totalCurrentAmount.value
  if (!total || total === 0 || !row.currentAmount) return '—'
  return ((row.currentAmount / total) * 100).toFixed(1) + '%'
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
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
.k10-tab-disclosure-listed {
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
