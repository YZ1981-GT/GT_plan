<script setup lang="ts">
/**
 * G12/G13/G14 底稿目录 Tab — 保留 GtBIndex 底稿架构 + 本循环跨底稿网格（D4 式清单下方）
 */
import { computed, inject, ref, watch, onMounted, defineAsyncComponent, type Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import GtBArchitectureTree from '../GtBArchitectureTree.vue'
import { getCycleHandbookLoader } from '@/services/cycleHandbookRegistry'
import { loadCycleWorkpaperCards, type CycleWpCard } from '@/services/cycleDirectory'
import {
  buildCycleArchitectureHtmlData,
  type CycleArchitectureSheet,
} from '../composables/gCycleIndexRouting'

interface CycleWorkpaper {
  wp_code: string
  wp_name: string
  wp_id: string | null
  status: string
  is_current: boolean
}

const props = defineProps<{
  wpId: string
  projectId: string
  sheetName?: string
  wpCode?: string
  htmlData?: Record<string, unknown>
  availableSheets?: CycleArchitectureSheet[]
  showArchitecture?: boolean
  /** 传入则渲染 E1 式「跨表结论口径看板」（各科目子表结论已填/未填），未传则不渲染（优雅降级） */
  allResponses?: Map<string, any>
}>()

const showArchitecture = computed(() => props.showArchitecture !== false)
const route = useRoute()
const router = useRouter()
const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

const projectId = computed(() => props.projectId || (route.params.projectId as string) || '')

const architectureHtmlData = computed(() =>
  buildCycleArchitectureHtmlData(props.htmlData, props.availableSheets, props.wpCode),
)

// 后端 render-config 提供的 cycle_workpapers（GtBIndex 路径有；G 循环专属 render 不提供 → 走自拉取兜底）
const propCycleWorkpapers = computed<CycleWorkpaper[]>(() => {
  const list = props.htmlData?.cycle_workpapers
  return Array.isArray(list) ? (list as CycleWorkpaper[]) : []
})

// ═══ 编制/使用手册（wp_code 优先 props，回退 cycle_workpapers 中 is_current 项；注册表有才显示） ═══
const resolvedWpCode = computed<string>(() => {
  if (props.wpCode) return props.wpCode
  const cur = propCycleWorkpapers.value.find(w => w.is_current)
  return cur?.wp_code || ''
})

// 循环字母（G4→G / H10→H），用于自拉取本循环底稿目录
const cycleLetter = computed<string>(() => {
  const m = resolvedWpCode.value.match(/^[A-Za-z]+/)
  return m ? m[0] : ''
})

// G 循环专属 render 不返回 cycle_workpapers → 从源模板清单自拉取（单一真源，同 E1/K 目录卡）
const fetchedCards = ref<CycleWpCard[]>([])
async function loadCycleGrid() {
  const pid = projectId.value
  const letter = cycleLetter.value
  if (!pid || !letter) return
  try {
    fetchedCards.value = await loadCycleWorkpaperCards(pid, letter, props.wpId)
  } catch {
    fetchedCards.value = []
  }
}
onMounted(loadCycleGrid)
watch([projectId, cycleLetter, () => props.wpId], loadCycleGrid)

// 本循环底稿目录：后端提供优先（GtBIndex 路径），否则用自拉取结果（G 循环路径）
const cycleWorkpapers = computed<CycleWorkpaper[]>(() => {
  if (propCycleWorkpapers.value.length > 0) return propCycleWorkpapers.value
  return fetchedCards.value as unknown as CycleWorkpaper[]
})
const handbookLoader = computed(() => getCycleHandbookLoader(resolvedWpCode.value))
const HandbookDialog = computed<Component | null>(() =>
  handbookLoader.value ? defineAsyncComponent(handbookLoader.value as any) : null,
)
const handbookVisible = ref(false)
const handbookTab = ref<'preparation' | 'usage'>('preparation')
function openHandbook(tab: 'preparation' | 'usage') {
  handbookTab.value = tab
  handbookVisible.value = true
}

// ═══ 跨表结论口径看板（E1 标准，从架构 navigation_rows 派生数据承载科目表） ═══
/** includes(`${code}-`) 兼容不同存储前缀深度，尾部连字符保证边界安全。 */
function isConclusionFilled(code: string): boolean {
  const map = props.allResponses instanceof Map ? props.allResponses : ((props.allResponses as any)?.value ?? null)
  if (!map || !map.size) return false
  const token = `${code}-`
  for (const [key, val] of map.entries()) {
    if (!key.includes(token)) continue
    if (!/conclusion|audit-note|note/i.test(key)) continue
    const text = (val?.remark ?? val?.conclusion ?? '') as string
    if (typeof text === 'string' && text.trim().length > 0) return true
  }
  return false
}

const conclusionSheets = computed(() => {
  const rows = (architectureHtmlData.value?.navigation_rows as any[]) || []
  const code = resolvedWpCode.value
  if (!code) return []
  const re = new RegExp(`^${code}-\\d+$`)
  const seen = new Set<string>()
  const out: { code: string; navValue: string; filled: boolean }[] = []
  for (const r of rows) {
    const ref = String(r.index_ref || '')
    const name = String(r.sheet_name || r.content || '')
    if (!re.test(ref) || /调整/.test(name) || seen.has(ref)) continue
    seen.add(ref)
    out.push({ code: ref, navValue: name, filled: isConclusionFilled(ref) })
  }
  return out
})
const conclusionFilledCount = computed(() => conclusionSheets.value.filter(c => c.filled).length)
const conclusionHasUnfilled = computed(() => conclusionSheets.value.some(c => !c.filled))
const conclusionWorstLabel = computed(() => {
  if (conclusionSheets.value.length === 0) return '无数据承载表'
  if (conclusionFilledCount.value === 0) return '结论未填'
  if (conclusionHasUnfilled.value) return `结论未齐 ${conclusionSheets.value.length - conclusionFilledCount.value} 项`
  return '总体已齐'
})
const conclusionWorstType = computed<'success' | 'warning' | 'info'>(() => {
  if (conclusionFilledCount.value === 0) return 'info'
  if (conclusionHasUnfilled.value) return 'warning'
  return 'success'
})

function handleNavigate(sheetName: string) {
  if (jumpToSection) {
    jumpToSection(sheetName)
  }
}

function onCycleCardClick(wp: CycleWorkpaper) {
  if (!wp.wp_id || wp.is_current) return
  const pid = projectId.value
  if (!pid) return
  router.push({
    name: 'WorkpaperEditor',
    params: { projectId: pid, wpId: wp.wp_id },
  })
}
</script>

<template>
  <div class="g-cycle-b-index-extras" data-testid="g-cycle-b-index-extras">
    <div v-if="HandbookDialog" class="g-cycle-b-index-extras__handbook">
      <el-button size="small" type="primary" plain @click="openHandbook('preparation')">📖 编制手册</el-button>
      <el-button size="small" @click="openHandbook('usage')">使用手册</el-button>
    </div>
    <component :is="HandbookDialog" v-if="HandbookDialog" v-model="handbookVisible" :initial-tab="handbookTab" />

    <!-- ═══ 跨表结论口径看板（E1 标准） ═══ -->
    <div v-if="allResponses && conclusionSheets.length" class="g-cycle-b-index-extras__board">
      <div class="g-cycle-b-index-extras__board-head">
        <strong>跨表结论口径</strong>
        <el-tag size="small" :type="conclusionWorstType">{{ conclusionWorstLabel }}</el-tag>
        <span class="g-cycle-b-index-extras__board-meta">已填 {{ conclusionFilledCount }}/{{ conclusionSheets.length }}</span>
      </div>
      <div class="g-cycle-b-index-extras__board-tags">
        <el-tag
          v-for="c in conclusionSheets"
          :key="c.code"
          size="small"
          class="g-cycle-b-index-extras__concl-tag"
          :type="c.filled ? 'success' : 'info'"
          effect="plain"
          @click="handleNavigate(c.navValue)"
        >
          {{ c.code }} {{ c.filled ? '已填' : '未填' }}
        </el-tag>
      </div>
      <p v-if="conclusionHasUnfilled" class="g-cycle-b-index-extras__board-hint">存在未填审计结论，点击标签跳转补全审计说明与结论。</p>
    </div>

    <div v-if="showArchitecture" class="g-cycle-b-index-extras__navigation">
      <div class="g-cycle-b-index-extras__navigation-header">
        <h4 class="g-cycle-b-index-extras__navigation-title">底稿架构</h4>
        <span class="g-cycle-b-index-extras__navigation-hint">点击程序卡片可跳转至对应底稿</span>
      </div>
      <GtBArchitectureTree
        :wp-id="wpId"
        :project-id="projectId"
        :active-sheet="sheetName"
        :html-data="architectureHtmlData"
        @navigate="handleNavigate"
      />
    </div>

    <div v-if="cycleWorkpapers.length > 0" class="g-cycle-b-index-extras__cycle">
      <div class="g-cycle-b-index-extras__cycle-header">
        <h4 class="g-cycle-b-index-extras__cycle-title">本循环底稿目录</h4>
        <span class="g-cycle-b-index-extras__cycle-hint">点击可跳转至同循环其他底稿（灰色表示尚未生成）</span>
      </div>
      <div class="g-cycle-b-index-extras__cycle-grid">
        <div
          v-for="wp in cycleWorkpapers"
          :key="wp.wp_code"
          class="g-cycle-b-index-extras__cycle-card"
          :class="{
            'is-current': wp.is_current,
            'is-disabled': !wp.wp_id,
          }"
          @click="onCycleCardClick(wp)"
        >
          <div class="g-cycle-b-index-extras__cycle-card-top">
            <span class="g-cycle-b-index-extras__cycle-code">{{ wp.wp_code }}</span>
            <el-tag
              v-if="wp.is_current"
              size="small"
              effect="plain"
              class="g-cycle-b-index-extras__cycle-current-tag"
            >当前</el-tag>
          </div>
          <span class="g-cycle-b-index-extras__cycle-name" :title="wp.wp_name">{{ wp.wp_name }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.g-cycle-b-index-extras {
  padding: 0 12px 16px;
  font-size: var(--wp-font-size, 13px);
}

.g-cycle-b-index-extras__handbook {
  display: flex;
  gap: 6px;
  margin: 4px 0 12px;
}

.g-cycle-b-index-extras__board {
  margin-bottom: 16px;
  padding: 10px 12px;
  background: #f5f7fa;
  border-radius: 6px;
  border-left: 3px solid #409eff;
}
.g-cycle-b-index-extras__board-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.g-cycle-b-index-extras__board-meta { font-size: 12px; color: #909399; }
.g-cycle-b-index-extras__board-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.g-cycle-b-index-extras__concl-tag { cursor: pointer; }
.g-cycle-b-index-extras__board-hint { margin: 8px 0 0; font-size: 12px; color: #e6a23c; }

.g-cycle-b-index-extras__navigation {
  margin-top: 8px;
  padding-top: 20px;
  border-top: 1px solid var(--gt-color-border-purple-light, #e8e4f0);
}

.g-cycle-b-index-extras__navigation-header,
.g-cycle-b-index-extras__cycle-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
}

.g-cycle-b-index-extras__navigation-title,
.g-cycle-b-index-extras__cycle-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--gt-color-text-primary, #303133);
}

.g-cycle-b-index-extras__navigation-hint,
.g-cycle-b-index-extras__cycle-hint {
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
}

.g-cycle-b-index-extras__cycle {
  margin-top: 28px;
}

.g-cycle-b-index-extras__cycle-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
}

.g-cycle-b-index-extras__cycle-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  border: 1px solid var(--gt-color-border-purple, #e8e4f0);
  border-radius: 8px;
  background: var(--gt-color-bg-white, #fff);
  cursor: pointer;
  transition: all 0.2s;
}

.g-cycle-b-index-extras__cycle-card:hover {
  border-color: var(--gt-color-primary, #4b2d77);
  box-shadow: 0 2px 8px rgba(75, 45, 119, 0.12);
  transform: translateY(-2px);
}

.g-cycle-b-index-extras__cycle-card.is-current {
  border-color: var(--gt-color-primary, #4b2d77);
  background: var(--gt-color-primary-bg, #f4f0fa);
  box-shadow: 0 0 0 1px var(--gt-color-primary, #4b2d77);
  cursor: default;
}

.g-cycle-b-index-extras__cycle-card.is-disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.g-cycle-b-index-extras__cycle-card.is-disabled:hover {
  border-color: var(--gt-color-border-purple, #e8e4f0);
  box-shadow: none;
  transform: none;
}

.g-cycle-b-index-extras__cycle-card-top {
  display: flex;
  align-items: center;
  gap: 6px;
}

.g-cycle-b-index-extras__cycle-code {
  font-size: var(--wp-font-size, 13px);
  font-weight: 700;
  color: var(--gt-color-primary, #4b2d77);
}

.g-cycle-b-index-extras__cycle-current-tag {
  margin-left: auto;
}

.g-cycle-b-index-extras__cycle-name {
  font-size: var(--wp-font-size, 13px);
  line-height: 1.4;
  color: var(--gt-color-text-primary, #303133);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
