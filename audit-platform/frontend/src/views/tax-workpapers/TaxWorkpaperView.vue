<template>
  <div class="tw-view">
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
import { computed, inject, nextTick, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import { CITAR_SUBNAV_OPEN_KEY } from '@/citar/citarRoutes'
import { useCitarProject } from '@/citar/useCitarProject'
import TaxWorkpaperCatalog from './TaxWorkpaperCatalog.vue'
import TaxWorkpaperIndexPanel from './TaxWorkpaperIndexPanel.vue'
import TaxWorkpaperParamsPanel from './TaxWorkpaperParamsPanel.vue'
import TaxWorkpaperSheetPanel from './TaxWorkpaperSheetPanel.vue'
import { TAX_INDEX_CODE, findTaxWorkpaperSheet } from './taxWorkpaperIndex'
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

const ACTIVE_PREFIX = 'gt.tax-workpaper-active.'

// 年度：路由 ?year= 优先，否则项目审核年度（读完之前不渲染取数页，避免误报「未设置年度」）
const { projectId, year, yearLoading } = useCitarProject()
const sheetPanelRef = ref<{ dirty: boolean } | null>(null)

const marks = ref<TaxWorkpaperMarkMap>({})
const hideAbsent = ref(false)
const activeCode = ref<string>(TAX_INDEX_CODE)
const contentRef = ref<HTMLElement | null>(null)

/** 目录栏开合：CITAR 框架点「税务底稿」时切换；不在该框架下（inject 不到）时常开 */
const catalogOpen = inject(CITAR_SUBNAV_OPEN_KEY, ref(true))

function loadActiveCode(pid: string): string {
  try {
    const saved = sessionStorage.getItem(ACTIVE_PREFIX + pid)
    if (saved && (saved === TAX_INDEX_CODE || findTaxWorkpaperSheet(saved))) return saved
  } catch {
    // sessionStorage 不可用时回到索引页
  }
  return TAX_INDEX_CODE
}

// 切项目时重读该项目的标记与上次打开的表
watch(
  projectId,
  (pid) => {
    marks.value = loadMarks(pid)
    hideAbsent.value = loadHideAbsent(pid)
    activeCode.value = loadActiveCode(pid)
  },
  { immediate: true },
)

/** 标为「无」且开了隐藏的表：不进目录栏与页签（索引页照常列出） */
const hiddenCodes = computed<ReadonlySet<string>>(() => {
  if (!hideAbsent.value) return new Set()
  return new Set(Object.keys(marks.value).filter(code => marks.value[code] === 'absent'))
})

async function openSheet(code: string) {
  if (code === activeCode.value) return
  // 切表（目录栏、页签、索引页都走这里）：单表页有未保存修改时先确认
  if (sheetPanelRef.value?.dirty) {
    try {
      await ElMessageBox.confirm('本表有未保存的修改，离开后修改会丢失。', '提示', {
        confirmButtonText: '离开', cancelButtonText: '留下', type: 'warning',
      })
    } catch {
      return
    }
  }
  activeCode.value = code
  try {
    sessionStorage.setItem(ACTIVE_PREFIX + projectId.value, code)
  } catch {
    // 记不住上次的表不影响使用
  }
  await nextTick()
  // 整页滚动由外层容器负责，换表后回到内容区顶部
  contentRef.value?.scrollIntoView({ block: 'start' })
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

<style scoped>
/*
 * 配色照 CITAR 白紫（#6e0ba6 一系）。stylelint 禁止 color/background 直接写十六进制，
 * 统一在根上定义 --tw-* 变量，子组件只用 var()（自定义属性会继承进子组件）。
 */
.tw-view {
  --tw-accent: #6e0ba6;
  --tw-accent-light: #8b3fd0;
  --tw-accent-deep: #4c1273;
  --tw-accent-soft: #f3edfa;
  --tw-accent-hover: #f7f1fe;
  --tw-on-accent: #ffffff;
  --tw-header-gradient: linear-gradient(90deg, #5b1a8c 0%, #8b3fd0 100%);
  --tw-subnav-bg: #fbf9fe;
  --tw-th-bg: #f1e7fb;
  --tw-page-bg: #f5f6fa;
  --tw-surface: #ffffff;
  --tw-input-bg: #fdfcff;
  --tw-line: #e8e8ec;
  --tw-line-soft: #f0eaf8;
  --tw-line-strong: #d9d9e0;
  --tw-line-accent: #e4d8f3;
  --tw-line-accent-strong: #d9c4ee;
  --tw-text: #3c3c48;
  --tw-text-muted: #6b6b76;
  --tw-text-faint: #a79bb5;
  --tw-text-hint: #8a6aa8;
  --tw-mark-present: #1a7f37;
  --tw-mark-absent: #c0392b;
  /* 单元格来源：公式 / 按规则取数 / 待确认 / 需人工填写 / 手工修改 / 取不到 */
  --tw-formula-bg: #f7f7fa;
  --tw-rule-auto-bg: #eef6ff;
  --tw-rule-confirm-bg: #fff4e0;
  --tw-rule-manual-bg: #f2f2f2;
  --tw-manual-bg: #fbf3ff;
  --tw-issue-mark: #e6a23c;

  /* 在 CITAR 框架内容区里铺满（内容区为 flex 容器，见 CitarLayout .citar-content--flush） */
  display: flex;
  flex: 1 1 auto;
  min-width: 0;
  background: var(--tw-page-bg);
  font-family: "Microsoft YaHei", "PingFang SC", system-ui, sans-serif;
}

.tw-view__content {
  flex: 1 1 auto;
  min-width: 0;
  padding: 20px 24px;
}

.tw-view__params {
  max-width: 1180px;
}
</style>
