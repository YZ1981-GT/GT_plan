<script setup lang="ts">
/**
 * D3TabIndex — 统一底稿目录（比照 D4TabIndex / D1TabIndex）
 */
import { computed, inject, ref, onMounted, defineAsyncComponent } from 'vue'
import { useRouter } from 'vue-router'
import GtIndexChip from '../GtIndexChip.vue'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import { D3_INDEX_ROWS, resolveD3SheetLabel } from '../composables/d3SheetLabels'
import { loadCycleWorkpaperCards, type CycleWpCard } from '@/services/cycleDirectory'

const D3PreparationHandbookDialog = defineAsyncComponent(() => import('./D3PreparationHandbookDialog.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  availableSheets?: Array<{ sheet_name?: string }>
  applicableStandards?: string
}>()

const indexRows = computed(() => {
  const std = (props.applicableStandards || '').toLowerCase()
  return D3_INDEX_ROWS.map(row => {
    let applicable = row.applicable
    if (row.code === '附注上市') {
      applicable = std.includes('listed') || !std
    }
    if (row.code === '附注国企') {
      applicable = std.includes('soe') || !std
    }
    return {
      ...row,
      applicable,
      sheetLabel: resolveD3SheetLabel(row.code, props.availableSheets),
    }
  })
})

function hasJsonRows(m: Map<string, any>, key: string): boolean {
  const raw = m.get(key)?.remark
  if (!raw) return false
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) && parsed.length > 0
  } catch {
    return false
  }
}

function hasText(m: Map<string, any>, key: string): boolean {
  const v = m.get(key)?.remark
  return typeof v === 'string' && v.trim().length > 0
}

function isSheetComplete(code: string, m: Map<string, any>): boolean {
  switch (code) {
    case 'D3A':
      return [...m.keys()].some(k => k.startsWith('D3-proc-'))
    case 'D3-1':
      return [...m.keys()].some(k => k.startsWith('D3-adj-'))
    case 'D3-2':
      return hasJsonRows(m, 'D3-det-rows')
    case 'D3-3':
      return hasJsonRows(m, 'D3-aje-rows')
    case 'D3-4':
      return hasJsonRows(m, 'D3-ana-debit-rows') || hasJsonRows(m, 'D3-ana-credit-rows') || hasText(m, 'D3-ana-note')
    case 'D3-5':
      return hasJsonRows(m, 'D3-lt-rows')
    case 'D3-6':
      return hasJsonRows(m, 'D3-rp-rows')
    case 'D3-7':
      return hasJsonRows(m, 'D3-vc-current-rows') || hasJsonRows(m, 'D3-vc-post-rows')
    case '附注上市':
    case '附注国企':
      return [...m.keys()].some(k => k.startsWith('D3-disc-'))
    default:
      return false
  }
}

const applicableRows = computed(() => indexRows.value.filter(r => r.applicable))

const completedCount = computed(() =>
  applicableRows.value.filter(r => isSheetComplete(r.code, props.allResponses)).length,
)

const progressPct = computed(() => {
  const total = applicableRows.value.length
  return total > 0 ? Math.round((completedCount.value / total) * 100) : 0
})

const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

// ─── 编制/使用手册弹窗 ─────────────────────────────────────────────────
const handbookVisible = ref(false)
const handbookTab = ref<'preparation' | 'usage'>('preparation')
function openHandbook(tab: 'preparation' | 'usage') {
  handbookTab.value = tab
  handbookVisible.value = true
}

// ─── 跨表结论口径看板（审定/明细/检查类，排除程序表/附注/调整分录）───
function isConclusionFilled(code: string): boolean {
  const map = props.allResponses instanceof Map ? props.allResponses : (props.allResponses as any)?.value ?? new Map()
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
const CONCLUSION_RE = /^D3-\d+$/
const conclusionSheets = computed(() =>
  indexRows.value
    .filter(r => CONCLUSION_RE.test(r.code) && !/调整分录/.test(r.name))
    .map(r => ({ code: r.code, sheetKey: r.sheetLabel, filled: isConclusionFilled(r.code) })),
)
const conclusionFilledCount = computed(() => conclusionSheets.value.filter(c => c.filled).length)
const conclusionHasUnfilled = computed(() => conclusionSheets.value.some(c => !c.filled))
const conclusionWorstLabel = computed(() => {
  if (conclusionFilledCount.value === 0) return '结论未填'
  if (conclusionHasUnfilled.value) return `结论未齐 ${conclusionSheets.value.length - conclusionFilledCount.value} 项`
  return '总体已齐'
})
const conclusionWorstType = computed<'success' | 'warning' | 'info'>(() => {
  if (conclusionFilledCount.value === 0) return 'info'
  if (conclusionHasUnfilled.value) return 'warning'
  return 'success'
})
function jumpConclusion(sheetKey: string) {
  if (jumpToSection && sheetKey) jumpToSection(sheetKey)
}

// ─── 本循环底稿目录（D 循环其他科目，跨底稿跳转）───────────────────────
const router = useRouter()
const cycleWorkpapers = ref<CycleWpCard[]>([])
async function loadCycleWorkpapers(): Promise<void> {
  cycleWorkpapers.value = await loadCycleWorkpaperCards(props.projectId, 'D', props.wpId)
}
function onCycleCardClick(wp: CycleWpCard): void {
  if (!wp.wp_id || wp.is_current || !props.projectId) return
  router.push({ name: 'WorkpaperEditor', params: { projectId: props.projectId, wpId: wp.wp_id } })
}
onMounted(loadCycleWorkpapers)
</script>

<template>
  <div class="d3-tab-index">
    <div class="index-header">
      <h3>D3 底稿目录</h3>
      <GtReviewTrigger section-id="D3-index-directory" />
      <div class="handbook-btns">
        <el-button size="small" type="primary" plain @click="openHandbook('preparation')">📖 编制手册</el-button>
        <el-button size="small" @click="openHandbook('usage')">使用手册</el-button>
      </div>
      <div class="progress-wrap">
        <span class="progress-label">编制进度 {{ completedCount }}/{{ applicableRows.length }}</span>
        <el-progress :percentage="progressPct" :stroke-width="10" />
      </div>
    </div>

    <D3PreparationHandbookDialog v-model="handbookVisible" :initial-tab="handbookTab" />

    <!-- 跨表结论口径看板 -->
    <div class="conclusion-board">
      <div class="board-head">
        <strong>跨表结论口径</strong>
        <el-tag size="small" :type="conclusionWorstType">{{ conclusionWorstLabel }}</el-tag>
        <span class="board-meta">已填 {{ conclusionFilledCount }}/{{ conclusionSheets.length }}</span>
      </div>
      <div class="board-tags">
        <el-tag
          v-for="c in conclusionSheets"
          :key="c.code"
          size="small"
          class="concl-tag clickable"
          :type="c.filled ? 'success' : 'info'"
          effect="plain"
          @click="jumpConclusion(c.sheetKey)"
        >
          {{ c.code }} {{ c.filled ? '已填' : '未填' }}
        </el-tag>
      </div>
      <p v-if="conclusionHasUnfilled" class="board-hint">存在未填审计结论，请点击标签跳转补全审计说明与结论。</p>
    </div>

    <el-table :data="indexRows" size="small" border stripe>
      <el-table-column prop="seq" label="序号" width="60" align="center" />
      <el-table-column prop="group" label="分组" width="80" />
      <el-table-column prop="code" label="索引号" width="90" />
      <el-table-column label="底稿名称" min-width="260">
        <template #default="{ row }">
          <span :class="{ 'na-row': !row.applicable }">{{ row.name }}</span>
          <GtIndexChip
            v-if="row.applicable && jumpToSection"
            :label="row.code"
            class="index-chip"
            @click="jumpToSection(row.sheetLabel)"
          />
          <el-tag
            v-if="row.applicable && isSheetComplete(row.code, allResponses)"
            type="success"
            size="small"
            class="done-tag"
          >已编制</el-tag>
          <GtReviewDot v-if="row.applicable" :section-id="`D3-index-${row.code}`" class="index-review-dot" />
        </template>
      </el-table-column>
      <el-table-column label="适用" width="70" align="center">
        <template #default="{ row }">
          <el-tag :type="row.applicable ? 'success' : 'info'" size="small">
            {{ row.applicable ? '适用' : 'N/A' }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>

    <details class="methodology-hint">
      <summary>编制提示</summary>
      <p>推荐工作流：D3A 程序表 → D3-1 审定表 → D3-2 明细 → D3-4 分析 → D3-3 调整分录。检查程序 D3-5~D3-7 可与 D3-2 明细交叉核对。</p>
    </details>

    <!-- 本循环底稿目录（D 循环其他科目，可跳转） -->
    <div v-if="cycleWorkpapers.length" class="cycle-section">
      <div class="cycle-header">
        <h4 class="cycle-title">本循环底稿目录</h4>
        <span class="cycle-hint">点击可跳转至同循环其他底稿（灰色表示尚未生成）</span>
      </div>
      <div class="cycle-grid">
        <div
          v-for="wp in cycleWorkpapers"
          :key="wp.wp_code"
          class="cycle-card"
          :class="{ 'is-current': wp.is_current, 'is-disabled': !wp.wp_id }"
          @click="onCycleCardClick(wp)"
        >
          <div class="cycle-card-top">
            <span class="cycle-code">{{ wp.wp_code }}</span>
            <el-tag v-if="wp.is_current" size="small" effect="plain" class="cycle-current-tag">当前</el-tag>
          </div>
          <span class="cycle-name" :title="wp.wp_name">{{ wp.wp_name }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.d3-tab-index { padding: 4px 0; }
.index-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.index-header h3 { margin: 0; font-size: 16px; color: #303133; }
.progress-wrap { min-width: 220px; }
.progress-label { font-size: 12px; color: #606266; display: block; margin-bottom: 4px; }
.index-chip { margin-left: 8px; }
.done-tag { margin-left: 6px; }
.index-review-dot { margin-left: 4px; }
.na-row { color: #909399; }
.methodology-hint {
  margin-top: 16px;
  padding: 10px 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 0 4px 4px 0;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}
.methodology-hint summary { cursor: pointer; font-weight: 500; color: #409eff; }
.handbook-btns { display: flex; gap: 6px; }
.conclusion-board { margin: 0 0 12px; padding: 10px 12px; background: #f5f7fa; border-radius: 6px; border-left: 3px solid #409eff; }
.board-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.board-head strong { font-size: 13px; color: #303133; }
.board-meta { font-size: 12px; color: #909399; }
.board-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.concl-tag.clickable { cursor: pointer; }
.board-hint { margin: 8px 0 0; font-size: 12px; color: #e6a23c; }
.cycle-section { margin-top: 24px; }
.cycle-header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px; }
.cycle-title { margin: 0; font-size: 16px; font-weight: 600; color: #303133; }
.cycle-hint { font-size: 12px; color: #909399; }
.cycle-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; }
.cycle-card { display: flex; flex-direction: column; gap: 6px; padding: 10px 12px; border: 1px solid var(--gt-color-border-purple, #e8e4f0); border-radius: 8px; background: #fff; cursor: pointer; transition: all 0.2s; }
.cycle-card:hover { border-color: var(--gt-color-primary, #4b2d77); box-shadow: 0 2px 8px rgba(75, 45, 119, 0.12); transform: translateY(-2px); }
.cycle-card.is-current { border-color: var(--gt-color-primary, #4b2d77); background: var(--gt-color-primary-bg, #f4f0fa); box-shadow: 0 0 0 1px var(--gt-color-primary, #4b2d77); cursor: default; }
.cycle-card.is-disabled { opacity: 0.5; cursor: not-allowed; }
.cycle-card.is-disabled:hover { border-color: var(--gt-color-border-purple, #e8e4f0); box-shadow: none; transform: none; }
.cycle-card-top { display: flex; align-items: center; gap: 6px; }
.cycle-code { font-size: var(--wp-font-size, 13px); font-weight: 700; color: var(--gt-color-primary, #4b2d77); }
.cycle-current-tag { margin-left: auto; }
.cycle-name { font-size: var(--wp-font-size, 13px); line-height: 1.4; color: #303133; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
</style>
