<script setup lang="ts">
/**
 * GtCycleDirExtras — 底稿目录页 E1 标准「加法式增强」通用块（H 循环等专属路径复用）
 *
 * 渲染三块（不含底稿架构/进度，保留各 TabIndex 现有 NAV_ROWS/GtBArchitectureTree/progress 不动）：
 *  1. 目录卡头部：标题「{wpCode} 底稿目录」+ GtReviewTrigger(复核) + 编制/使用手册按钮
 *  2. 跨表结论口径看板：从 sheets 筛数据承载表（index_ref 形如 {wpCode}-数字，排除调整分录）
 *  3. 本循环底稿目录 grid：loadCycleWorkpaperCards(projectId, cycleLetter, wpId)
 *
 * 导航不改各文件现有机制：本组件仅 emit('navigate', navValue)，由宿主 TabIndex 转发到
 * 其现有 inject('jumpToSection') 或 emit('navigate-sheet')。
 */
import { computed, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import GtReviewTrigger from './GtReviewTrigger.vue'
import { loadCycleWorkpaperCards, type CycleWpCard } from '@/services/cycleDirectory'

interface DirSheet {
  /** 底稿编码，如 H1-1（用于结论看板筛选与匹配） */
  code: string
  /** 该文件现有导航机制期望的跳转值（H1/H10=完整sheet名；H5=编码；余=sheetName） */
  navValue: string
  /** 底稿名称（用于排除「调整分录」类） */
  name: string
}

const props = defineProps<{
  wpCode: string
  cycleLetter: string
  wpId?: string
  projectId?: string
  allResponses?: Map<string, any>
  sheets: DirSheet[]
}>()

const emit = defineEmits<{
  (e: 'navigate', navValue: string): void
  (e: 'open-handbook', tab: 'preparation' | 'usage'): void
}>()

// ─── 跨表结论口径看板 ──────────────────────────────────────────────────────
/** includes(`${code}-`) 兼容不同存储前缀深度，尾部连字符保证边界安全。 */
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

const conclusionSheets = computed(() => {
  const re = new RegExp(`^${props.wpCode}-\\d+$`)
  return props.sheets
    .filter((s) => re.test(s.code) && !/调整/.test(s.name))
    .map((s) => ({ code: s.code, navValue: s.navValue, filled: isConclusionFilled(s.code) }))
})
const conclusionFilledCount = computed(() => conclusionSheets.value.filter((c) => c.filled).length)
const conclusionHasUnfilled = computed(() => conclusionSheets.value.some((c) => !c.filled))
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

// ─── 本循环底稿目录 grid ───────────────────────────────────────────────────
const router = useRouter()
const cycleWorkpapers = ref<CycleWpCard[]>([])
async function loadCycleWorkpapers(): Promise<void> {
  if (!props.projectId) return
  cycleWorkpapers.value = await loadCycleWorkpaperCards(props.projectId, props.cycleLetter, props.wpId || '')
}
function onCycleCardClick(wp: CycleWpCard): void {
  if (!wp.wp_id || wp.is_current || !props.projectId) return
  router.push({ name: 'WorkpaperEditor', params: { projectId: props.projectId, wpId: wp.wp_id } })
}
onMounted(loadCycleWorkpapers)
</script>

<template>
  <div class="cdir-extras">
    <!-- ═══ 目录卡头部（标题 + 复核 + 编制/使用手册） ═══ -->
    <div class="cdir-head">
      <h3 class="cdir-title">{{ wpCode }} 底稿目录</h3>
      <GtReviewTrigger :section-id="`${wpCode}-index-directory`" />
      <div class="cdir-handbook-btns">
        <el-button size="small" type="primary" plain @click="emit('open-handbook', 'preparation')">📖 编制手册</el-button>
        <el-button size="small" @click="emit('open-handbook', 'usage')">使用手册</el-button>
      </div>
    </div>

    <!-- ═══ 跨表结论口径看板 ═══ -->
    <div v-if="conclusionSheets.length" class="cdir-board">
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
          @click="emit('navigate', c.navValue)"
        >
          {{ c.code }} {{ c.filled ? '已填' : '未填' }}
        </el-tag>
      </div>
      <p v-if="conclusionHasUnfilled" class="board-hint">存在未填审计结论，点击标签跳转补全审计说明与结论。</p>
    </div>

    <!-- ═══ 本循环底稿目录 grid ═══ -->
    <div v-if="cycleWorkpapers.length" class="cdir-cycle">
      <div class="cycle-header">
        <h4 class="cycle-title">本循环底稿目录</h4>
        <span class="cycle-hint">点击跳转同循环其他底稿（灰色表示尚未生成）</span>
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
.cdir-extras { font-size: var(--wp-font-size, 13px); }

/* ─── 目录卡头部 ─── */
.cdir-head { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.cdir-title { margin: 0; font-size: 16px; font-weight: 600; color: #303133; }
.cdir-handbook-btns { display: flex; gap: 6px; }

/* ─── 结论口径看板 ─── */
.cdir-board {
  margin-bottom: 16px;
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

/* ─── 本循环底稿目录 ─── */
.cdir-cycle { margin-top: 20px; margin-bottom: 8px; }
.cycle-header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px; }
.cycle-title { margin: 0; font-size: 16px; font-weight: 600; color: #303133; }
.cycle-hint { font-size: 12px; color: #909399; }
.cycle-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; }
.cycle-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  border: 1px solid var(--gt-color-border-purple, #e8e4f0);
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  transition: all 0.2s;
}
.cycle-card:hover { border-color: var(--gt-color-primary, #4b2d77); box-shadow: 0 2px 8px rgba(75, 45, 119, 0.12); transform: translateY(-2px); }
.cycle-card.is-current { border-color: var(--gt-color-primary, #4b2d77); background: var(--gt-color-primary-bg, #f4f0fa); box-shadow: 0 0 0 1px var(--gt-color-primary, #4b2d77); cursor: default; }
.cycle-card.is-disabled { opacity: 0.5; cursor: not-allowed; }
.cycle-card.is-disabled:hover { border-color: var(--gt-color-border-purple, #e8e4f0); box-shadow: none; transform: none; }
.cycle-card-top { display: flex; align-items: center; gap: 6px; }
.cycle-code { font-size: var(--wp-font-size, 13px); font-weight: 700; color: var(--gt-color-primary, #4b2d77); }
.cycle-current-tag { margin-left: auto; }
.cycle-name { font-size: var(--wp-font-size, 13px); line-height: 1.4; color: #303133; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
</style>
