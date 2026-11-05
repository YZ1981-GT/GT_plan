<template>
  <div class="tw-view tw-tokens">
    <TaxWorkpaperCatalog
      v-if="catalogOpen"
      :active-code="activeCode"
      :index-code="TAX_INDEX_CODE"
      :hidden-codes="hiddenCodes"
      @open="openSheet"
    />

    <main ref="contentRef" class="tw-view__content">
      <template v-if="activeCode === TAX_INDEX_CODE">
        <TaxWorkpaperIndexPanel
          :marks="marks"
          :hide-absent="hideAbsent"
          @open="openSheet"
          @toggle-mark="toggleMark"
          @toggle-hide="toggleHide"
          @set-marks="setMarks"
        />
        <TaxWorkpaperParamsPanel v-if="!yearLoading" class="tw-view__params" :project-id="projectId" :year="year" />
      </template>
      <TaxWorkpaperSheetPanel
        v-else-if="!yearLoading"
        ref="sheetPanelRef"
        :code="activeCode"
        :hidden-codes="hiddenCodes"
        :project-id="projectId"
        :year="year"
        :locate="locate"
        @open="openSheet"
      />
    </main>
  </div>
</template>

<script setup lang="ts">
/**
 * 税务底稿页（/projects/:projectId/workpapers）。
 *
 * 版式移植自 CITAR：左为「底稿目录」二级栏（索引 + 11 个分组），右为内容区
 * （紫色横幅 → 同组页签 → 白色卡片）。
 *
 * 当前表编号不进路由 query：DefaultLayout 按 fullPath 给页面加 key，
 * 改 query 会整页重建、目录展开状态丢失。改记 sessionStorage，刷新后回到上次的表。
 */
import { computed, inject, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CITAR_SUBNAV_OPEN_KEY } from '@/citar/citarRoutes'
import { TAX_CELL_LOCATE_EVENT, takePendingTaxLocate, type TaxCellLocate } from '@/citar/cellSource'
import { useCitarProject } from '@/citar/useCitarProject'
import TaxWorkpaperCatalog from './TaxWorkpaperCatalog.vue'
import TaxWorkpaperIndexPanel from './TaxWorkpaperIndexPanel.vue'
import TaxWorkpaperParamsPanel from './TaxWorkpaperParamsPanel.vue'
import TaxWorkpaperSheetPanel from './TaxWorkpaperSheetPanel.vue'
import { TAX_INDEX_CODE, isTaxWorkpaperShown, loadActiveTaxSheet, saveActiveTaxSheet } from './taxWorkpaperIndex'
import {
  loadHideAbsent,
  loadMarks,
  nextMark,
  saveHideAbsent,
  saveMarks,
  type TaxWorkpaperMark,
  type TaxWorkpaperMarkMap,
} from './taxWorkpaperMarks'

defineOptions({ name: 'TaxWorkpaperView' })

// 年度：路由 ?year= 优先，否则项目审核年度（读完之前不渲染取数页，避免误报「未设置年度」）
const { projectId, year, yearLoading } = useCitarProject()
const sheetPanelRef = ref<{ dirty: boolean } | null>(null)

const marks = ref<TaxWorkpaperMarkMap>({})
const hideAbsent = ref(false)
const activeCode = ref<string>(TAX_INDEX_CODE)
const contentRef = ref<HTMLElement | null>(null)

/** 目录栏开合：CITAR 框架点「税务底稿」时切换；不在该框架下（inject 不到）时常开 */
const catalogOpen = inject(CITAR_SUBNAV_OPEN_KEY, ref(true))

/** 来源链接要定位的格子；seq 每次加一，同一格再点也会重新定位（须声明在下方 immediate watch 之前：进页时就会用到） */
const locate = ref<(TaxCellLocate & { seq: number }) | null>(null)
let locateSeq = 0

// 切项目时重读该项目的标记与上次打开的表
watch(
  projectId,
  (pid) => {
    marks.value = loadMarks(pid)
    hideAbsent.value = loadHideAbsent(pid)
    activeCode.value = loadActiveTaxSheet(pid)
    // 从别的页的来源链接跳来：切到目标表，读完值后定位格子（spec citar-cell-source-hover R2）
    const pending = takePendingTaxLocate(pid, 'workpaper')
    if (pending) void goLocate(pending, false)
  },
  { immediate: true },
)

async function goLocate(target: TaxCellLocate, confirm = true) {
  if (!isTaxWorkpaperShown(target.code)) {
    ElMessage.info(`${target.code} 不在底稿目录中显示，只能经取数或手填`)
    return
  }
  if (confirm ? !(await openSheet(target.code)) : !switchTo(target.code)) return
  locate.value = { ...target, seq: ++locateSeq }
}

function onLocateEvent(e: Event) {
  const target = (e as CustomEvent<TaxCellLocate>).detail
  if (target?.domain === 'workpaper') void goLocate(target)
}
window.addEventListener(TAX_CELL_LOCATE_EVENT, onLocateEvent)
onBeforeUnmount(() => window.removeEventListener(TAX_CELL_LOCATE_EVENT, onLocateEvent))

/** 不确认直接切（进页时用） */
function switchTo(code: string): boolean {
  activeCode.value = code
  saveActiveTaxSheet(projectId.value, code)
  return true
}

/** 标为「无」且开了隐藏的表：不进目录栏与页签（索引页照常列出） */
const hiddenCodes = computed<ReadonlySet<string>>(() => {
  if (!hideAbsent.value) return new Set()
  return new Set(Object.keys(marks.value).filter(code => marks.value[code] === 'absent'))
})

/** 切表；返回是否已在该表（用户在未保存确认里选「留下」时 false） */
async function openSheet(code: string): Promise<boolean> {
  if (code === activeCode.value) return true
  // 切表（目录栏、页签、索引页都走这里）：单表页有未保存修改时先确认
  if (sheetPanelRef.value?.dirty) {
    try {
      await ElMessageBox.confirm('本表有未保存的修改，离开后修改会丢失。', '提示', {
        confirmButtonText: '离开', cancelButtonText: '留下', type: 'warning',
      })
    } catch {
      return false
    }
  }
  activeCode.value = code
  saveActiveTaxSheet(projectId.value, code)
  await nextTick()
  // 换表后回到顶部：CITAR 框架里内容区自己滚动（归零 scrollTop）；不在该框架时由外层滚动（scrollIntoView）
  const content = contentRef.value
  if (content) {
    content.scrollTop = 0
    content.scrollIntoView({ block: 'start' })
  }
  return true
}

function commitMarks(next: TaxWorkpaperMarkMap) {
  marks.value = next
  saveMarks(projectId.value, next)
}

function toggleMark(code: string) {
  const next = { ...marks.value }
  const mark = nextMark(next[code])
  if (mark) next[code] = mark
  else delete next[code]
  commitMarks(next)
}

function setMarks(codes: string[], mark: TaxWorkpaperMark | undefined) {
  const next = { ...marks.value }
  for (const code of codes) {
    if (mark) next[code] = mark
    else delete next[code]
  }
  commitMarks(next)
}

function toggleHide() {
  hideAbsent.value = !hideAbsent.value
  saveHideAbsent(projectId.value, hideAbsent.value)
}
</script>

<!-- 配色变量（--tw-*）与汇算申报表页共用 -->
<style scoped src="./taxWorkpaperTokens.css"></style>

<style scoped>
.tw-view {
  /* 在 CITAR 框架内容区里铺满（内容区为 flex 容器，见 CitarLayout .citar-content--flush） */
  display: flex;
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  background: var(--tw-page-bg);
  font-family: "Microsoft YaHei", "PingFang SC", system-ui, sans-serif;
}

/* CITAR 框架定高一屏：目录栏与右侧内容各自滚动，往下翻表时目录留在原处 */
.tw-view__content {
  flex: 1 1 auto;
  min-width: 0;
  padding: 20px 24px;
  overflow-y: auto;
}

.tw-view__params {
  min-width: 0;
}
</style>
