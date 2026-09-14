<template>
  <div class="cycle-dir-card" data-testid="cycle-directory-card">
    <div class="index-header">
      <h3 class="title">{{ wpCode }} 底稿目录</h3>
      <GtReviewTrigger :section-id="`${wpCode}-index-directory`" />
      <div v-if="HandbookDialog" class="handbook-btns">
        <el-button size="small" type="primary" plain @click="openHandbook('preparation')">📖 编制手册</el-button>
        <el-button size="small" @click="openHandbook('usage')">使用手册</el-button>
      </div>
      <div class="progress-wrap">
        <span>编制进度 {{ completedCount }}/{{ conclusionSheets.length }}</span>
        <el-progress :percentage="progressPct" :stroke-width="10" />
      </div>
    </div>

    <component :is="HandbookDialog" v-if="HandbookDialog" v-model="handbookVisible" :initial-tab="handbookTab" />

    <!-- 跨表结论口径看板 -->
    <div class="conclusion-board" data-testid="cycle-conclusion-board">
      <div class="board-head">
        <strong>跨表结论口径</strong>
        <el-tag size="small" :type="worstTagType">{{ worstLabel }}</el-tag>
        <span class="board-meta">已填 {{ filledCount }}/{{ conclusionSheets.length }}</span>
      </div>
      <div class="board-tags">
        <el-tag
          v-for="c in conclusionSheets"
          :key="c.code"
          size="small"
          class="concl-tag clickable"
          :type="c.filled ? 'success' : 'info'"
          effect="plain"
          @click="goSheet(c)"
        >
          {{ c.code }} {{ c.filled ? '已填' : '未填' }}
        </el-tag>
      </div>
      <p v-if="hasUnfilled" class="board-hint">存在未填审计结论，请点击标签跳转补全审计说明与结论。</p>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * GtCycleDirectoryCard.vue — 通用「底稿目录」卡片（E1TabDirectory 的泛化版）
 *
 * 由 GtBIndex 在「底稿架构」上方渲染，覆盖 E1 + D~N 全部叶子科目目录页：
 * - 目录卡（标题「{wpCode} 底稿目录」+ 复核 + 编制/使用手册按钮[注册表有才显示] + 进度条）
 * - 跨表结论口径看板（从 navigation_rows 派生审定/明细/检查表，各表结论已填/未填 + 跳转）
 * 自行拉取本底稿 checklist-responses（GtBIndex 不持有 allResponses）。
 * 结论判定用鲁棒 key.includes(`${code}-`)+/conclusion|audit-note|note/（不依赖各科目精确键）。
 * 跳转经 emit('navigate', sheetName)（GtBIndex handleNavigate → jump-to-section 转发）。
 */
import { computed, onMounted, ref, defineAsyncComponent, type Component } from 'vue'
import http from '@/utils/http'
import GtReviewTrigger from './GtReviewTrigger.vue'
import { getCycleHandbookLoader } from '@/services/cycleHandbookRegistry'

const props = defineProps<{
  wpId?: string
  wpCode: string
  /** sheet 全名列表（b-index navigation_rows），供结论看板派生 + jumpToSection 精确匹配 */
  availableSheets?: Array<{ sheet_name?: string; content?: string; index_ref?: string; component_type?: string }>
}>()

const emit = defineEmits<{ (e: 'navigate', sheetName: string): void }>()

// ═══ 手册弹窗（注册表有才加载） ═══
const handbookLoader = getCycleHandbookLoader(props.wpCode)
const HandbookDialog: Component | null = handbookLoader ? defineAsyncComponent(handbookLoader as any) : null
const handbookVisible = ref(false)
const handbookTab = ref<'preparation' | 'usage'>('preparation')
function openHandbook(tab: 'preparation' | 'usage') {
  handbookTab.value = tab
  handbookVisible.value = true
}

// ═══ 响应数据：自行拉取 ═══
const fetchedResponses = ref<Map<string, any>>(new Map())
onMounted(async () => {
  if (!props.wpId) return
  try {
    const res: any = await http.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const list = res?.data?.items ?? res?.items ?? res?.data ?? res
    const map = new Map<string, any>()
    if (Array.isArray(list)) {
      for (const it of list) {
        if (it?.item_id) map.set(it.item_id, it)
      }
    }
    fetchedResponses.value = map
  } catch {
    /* silent：拉取失败则看板全显未填 */
  }
})

// ═══ 从 navigation_rows 派生审定/明细/检查表（排除程序表/附注/调整分录/目录） ═══
interface ConclusionSheet { code: string; sheetLabel: string; filled: boolean }

/** 仅匹配本科目子表（如 D2 → ^D2-\d+$），排除同目录内的 D0-* 函证等其它科目 sheet。 */
const subSheetRe = computed(() => {
  const esc = (props.wpCode || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return new RegExp(`^${esc}-\\d+$`)
})

const derivedSheets = computed(() => {
  const rows = props.availableSheets ?? []
  const out: Array<{ code: string; sheetLabel: string }> = []
  const seen = new Set<string>()
  for (const r of rows) {
    const code = String(r.index_ref || '').trim()
    const label = String(r.sheet_name || r.content || '').trim()
    if (!code || !subSheetRe.value.test(code)) continue
    if (r.component_type === 'a-program-console') continue
    if (/调整分录|附注|底稿目录/.test(label) || /调整分录|附注|底稿目录/.test(code)) continue
    if (seen.has(code)) continue
    seen.add(code)
    out.push({ code, sheetLabel: label || code })
  }
  return out
})

// ═══ 鲁棒结论/说明判定 ═══
function isConclusionFilled(code: string): boolean {
  const map = fetchedResponses.value
  if (!map?.size) return false
  const token = `${code}-`
  for (const [key, val] of map.entries()) {
    if (!key.includes(token)) continue
    if (!/conclusion|audit-note|note/i.test(key)) continue
    const text = (val?.remark ?? val?.conclusion ?? '') as string
    if (typeof text === 'string' && text.trim().length > 0) return true
  }
  return false
}

const conclusionSheets = computed<ConclusionSheet[]>(() =>
  derivedSheets.value.map(s => ({ code: s.code, sheetLabel: s.sheetLabel, filled: isConclusionFilled(s.code) })),
)

const filledCount = computed(() => conclusionSheets.value.filter(c => c.filled).length)
const completedCount = filledCount
const hasUnfilled = computed(() => conclusionSheets.value.some(c => !c.filled))
const progressPct = computed(() => {
  const total = conclusionSheets.value.length
  return total > 0 ? Math.round((filledCount.value / total) * 100) : 0
})

const worstLabel = computed(() => {
  if (conclusionSheets.value.length === 0) return '暂无可核对结论'
  if (filledCount.value === 0) return '结论未填'
  if (hasUnfilled.value) return `结论未齐 ${conclusionSheets.value.length - filledCount.value} 项`
  return '总体已齐'
})
const worstTagType = computed<'success' | 'warning' | 'info'>(() => {
  if (filledCount.value === 0) return 'info'
  if (hasUnfilled.value) return 'warning'
  return 'success'
})

function goSheet(c: ConclusionSheet) {
  emit('navigate', c.sheetLabel || c.code)
}
</script>

<style scoped>
.cycle-dir-card { font-size: var(--wp-font-size, 13px); margin-bottom: 20px; }
.index-header { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; flex-wrap: wrap; }
.title { margin: 0; font-size: 16px; font-weight: 600; color: #303133; }
.handbook-btns { display: flex; gap: 6px; }
.progress-wrap { flex: 1; min-width: 200px; }
.conclusion-board {
  margin-bottom: 12px;
  padding: 10px 12px;
  background: #f5f7fa;
  border-radius: 6px;
  border-left: 3px solid #409eff;
}
.board-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.board-meta { font-size: 12px; color: #909399; }
.board-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.concl-tag.clickable { cursor: pointer; }
.board-hint { margin: 8px 0 0; font-size: 12px; color: #e6a23c; }
</style>
