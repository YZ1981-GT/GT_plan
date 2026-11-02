<!--
  TaxWorkpaperSubnav — 税审底稿的二级侧边栏（底稿目录）。
  版式照 CITAR ProjectShell：与一级环节栏并排（不嵌套），
  顶部「底稿目录」标题 → 置顶「索引」→ 11 个分组（默认全部收起，点标题展开）。
  当前表由路由 `?sheet=` 决定：点表只改 query，不自管选中态，
  刷新 / 前进后退时高亮跟着路由走。
  🔴 本组件挂在布局层（ThreeColumnLayout）而非页面内：页面在 router-view 里
     按 fullPath 重挂载，放在页面里每点一张表分组展开状态就会被重置。
-->
<template>
  <nav class="gt-twp-subnav" data-testid="tax-wp-subnav">
    <div class="gt-twp-subnav__caption">底稿目录</div>
    <button
      type="button"
      class="gt-twp-subnav__sheet"
      :class="{ 'gt-twp-subnav__sheet--active': activeSheet === TAX_WORKPAPER_INDEX_CODE }"
      @click="openSheet(TAX_WORKPAPER_INDEX_CODE)"
    >
      <span class="gt-twp-subnav__code">索引</span>税审底稿索引
    </button>
    <div v-for="group in TAX_WORKPAPER_INDEX" :key="group.title">
      <button
        type="button"
        class="gt-twp-subnav__group"
        :class="{ 'gt-twp-subnav__group--open': openGroups.has(group.title) }"
        @click="toggleGroup(group.title)"
      >
        <span class="gt-twp-subnav__caret">{{ openGroups.has(group.title) ? '▾' : '▸' }}</span>
        <span class="gt-twp-subnav__group-name">{{ group.title }}</span>
        <span class="gt-twp-subnav__count">{{ group.sheets.length }}</span>
      </button>
      <template v-if="openGroups.has(group.title)">
        <button
          v-for="sheet in group.sheets"
          :key="sheet.code"
          type="button"
          class="gt-twp-subnav__sheet gt-twp-subnav__sheet--child"
          :class="{ 'gt-twp-subnav__sheet--active': activeSheet === sheet.code }"
          @click="openSheet(sheet.code)"
        >
          <span class="gt-twp-subnav__code">{{ sheet.code }}</span>{{ sheet.name }}
        </button>
      </template>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  TAX_WORKPAPER_INDEX, TAX_WORKPAPER_INDEX_CODE, findTaxWorkpaperGroup,
} from '@/constants/taxWorkpaperIndex'

const route = useRoute()
const router = useRouter()

/** 底稿页路由名（与 router/domains/workpapers.ts 一致） */
const PAGE_ROUTE = 'TaxWorkpapers'

const activeSheet = computed(() =>
  route.name === PAGE_ROUTE && typeof route.query.sheet === 'string' ? route.query.sheet : '',
)

/** 展开的分组。默认全部收起；reactive(Set) 让 has() 可被追踪 */
const openGroups = reactive(new Set<string>())

function toggleGroup(title: string) {
  if (openGroups.has(title)) openGroups.delete(title)
  else openGroups.add(title)
}

// 从地址栏直接打开某张表（刷新 / 分享链接）时，展开它所在的分组，
// 否则高亮项藏在收起的分组里，看着像没选中。只展开、不收起用户已展开的。
watch(activeSheet, code => {
  const g = code ? findTaxWorkpaperGroup(code) : undefined
  if (g) openGroups.add(g.title)
}, { immediate: true })

function openSheet(code: string) {
  const pid = (route.params.projectId as string) || ''
  if (!pid) return
  const year = route.query.year ? String(route.query.year) : undefined
  router.push({
    name: PAGE_ROUTE,
    params: { projectId: pid },
    query: { ...(year ? { year } : {}), sheet: code },
  })
}
</script>

<style scoped>
/* 配色与 CITAR project-shell.css 的二级栏一致（白紫）。
   ⚠ 注释内禁写花括号：CSS 注释不能嵌套，会吞掉后一条规则。 */
.gt-twp-subnav {
  display: flex;
  flex-direction: column;
  flex: 0 0 270px;
  width: 270px;
  min-height: 0;
  overflow-y: auto;
  background: #fbf9fe;
  border-right: 1px solid #e8e8ec;
}
.gt-twp-subnav__caption {
  flex: 0 0 auto;
  padding: 10px 14px;
  border-bottom: 1px solid #e8e8ec;
  background: #f3edfa;
  font-size: 12px;
  font-weight: 700;
  color: var(--gt-color-primary, #4b2d77);
}
.gt-twp-subnav__group {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 9px 12px;
  border: none;
  border-bottom: 1px solid #f0eaf8;
  background: none;
  font: inherit;
  font-size: 12px;
  color: #5c5c68;
  text-align: left;
  cursor: pointer;
}
.gt-twp-subnav__group:hover {
  color: var(--gt-color-primary, #4b2d77);
  background: #f7f1fe;
}
.gt-twp-subnav__group--open {
  color: var(--gt-color-primary, #4b2d77);
  font-weight: 700;
  background: #f7f1fe;
}
.gt-twp-subnav__caret {
  flex: 0 0 auto;
  width: 10px;
  font-size: 9px;
  color: #a79bb5;
}
.gt-twp-subnav__group-name {
  min-width: 0;
  overflow-wrap: anywhere;
}
.gt-twp-subnav__count {
  margin-left: auto;
  flex: 0 0 auto;
  font-size: 11px;
  color: #a79bb5;
}
.gt-twp-subnav__sheet {
  display: block;
  width: 100%;
  padding: 7px 14px;
  border: none;
  border-left: 3px solid transparent;
  background: #fff;
  font: inherit;
  font-size: 12px;
  line-height: 1.5;
  color: #6b6b76;
  text-align: left;
  cursor: pointer;
  overflow-wrap: anywhere;
}
.gt-twp-subnav__sheet--child { padding-left: 28px; }
.gt-twp-subnav__sheet:hover {
  background: #faf6ff;
  color: var(--gt-color-primary, #4b2d77);
}
.gt-twp-subnav__sheet--active {
  border-left-color: var(--gt-color-primary, #4b2d77);
  background: #f3edfa;
  color: var(--gt-color-primary, #4b2d77);
  font-weight: 700;
}
.gt-twp-subnav__code {
  margin-right: 6px;
  font-variant-numeric: tabular-nums;
  color: #a79bb5;
}
.gt-twp-subnav__sheet--active .gt-twp-subnav__code { color: #8b3fd0; }
</style>
