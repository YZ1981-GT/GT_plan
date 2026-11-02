<!--
  TaxWorkpaperPage — 税审底稿内容区。
  目录在布局层的二级栏（TaxWorkpaperSubnav），本页只按 `?sheet=` 渲染：
  - 无 sheet：提示从左侧选表
  - `__index__`：索引总览（分组 + 编号 + 表名，点行打开）
  - 有效编号：表头（编号 / 表名 / 所属分组）+ 表样待录入占位
  - 无效编号：明确报「编号不存在」，不显示空白
  🔴 单张底稿的表样与取数规则尚未录入 ⇒ 本页不发请求、不读写数据。
-->
<template>
  <div class="gt-twp-page">
    <div v-if="!sheetCode" class="gt-twp-page__home" data-testid="tax-wp-home">
      <p class="gt-twp-page__home-title">请从左侧选择一张底稿</p>
      <p class="gt-twp-page__home-hint">共 {{ ALL_TAX_WORKPAPER_SHEETS.length }} 张表，按 {{ TAX_WORKPAPER_INDEX.length }} 个分类归集。</p>
    </div>

    <template v-else-if="sheetCode === TAX_WORKPAPER_INDEX_CODE">
      <h2 class="gt-twp-page__title">税审底稿索引</h2>
      <table class="gt-twp-page__index" data-testid="tax-wp-index">
        <thead>
          <tr><th class="gt-twp-page__col-code">索引号</th><th>底稿名称</th></tr>
        </thead>
        <tbody v-for="group in TAX_WORKPAPER_INDEX" :key="group.title">
          <tr class="gt-twp-page__group-row"><td colspan="2">{{ group.title }}</td></tr>
          <tr
            v-for="sheet in group.sheets"
            :key="sheet.code"
            class="gt-twp-page__sheet-row"
            @click="openSheet(sheet.code)"
          >
            <td class="gt-twp-page__col-code">{{ sheet.code }}</td>
            <td>{{ sheet.name }}</td>
          </tr>
        </tbody>
      </table>
    </template>

    <!-- 单张底稿：版式照 CITAR WorkpaperScreen（渐变表头 → 同组页签 → 工具栏 → 白色面板） -->
    <div v-else-if="sheet" class="gt-twp-sheet">
      <header class="gt-twp-sheet__header">
        <span class="gt-twp-sheet__code">{{ sheet.code }}</span>
        <h1 class="gt-twp-sheet__title">{{ sheet.name }}</h1>
        <span v-if="group" class="gt-twp-sheet__group">{{ group.title }}</span>
      </header>

      <!-- 同组横向切换：只显示编号（组内表名过长、一组最多 30 余张），表名放 title 悬停可见 -->
      <nav v-if="group && group.sheets.length > 1" class="gt-twp-sheet__tabs" :aria-label="`${group.title} 表清单`">
        <button
          v-for="item in group.sheets"
          :key="item.code"
          type="button"
          class="gt-twp-sheet__tab"
          :class="{ 'gt-twp-sheet__tab--active': item.code === sheet.code }"
          :title="item.name"
          :aria-current="item.code === sheet.code ? 'page' : undefined"
          @click="item.code !== sheet.code && openSheet(item.code)"
        >{{ item.code }}</button>
      </nav>

      <!-- 三个按钮在表样录入前保持禁用：没有表样就没有可导入 / 导出 / 保存的内容 -->
      <div class="gt-twp-sheet__toolbar">
        <button v-for="label in TOOLBAR" :key="label" type="button" class="gt-twp-sheet__btn" disabled title="本期暂未开放">{{ label }}</button>
      </div>

      <!-- 电子表格（照 CITAR WorkpaperGrid）：已上传样表的按样表加载，其余为空白表；可编辑、不存盘 -->
      <section class="gt-twp-sheet__panel gt-twp-sheet__panel--grid">
        <TaxWorkpaperGrid :code="sheet.code" :name="sheet.name" />
      </section>
    </div>

    <div v-else class="gt-twp-page__home" data-testid="tax-wp-unknown">
      <p class="gt-twp-page__home-title">底稿编号不存在</p>
      <p class="gt-twp-page__home-hint">编号「{{ sheetCode }}」不在税审底稿索引中，请从左侧目录重新选择。</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import TaxWorkpaperGrid from '@/components/workpaper/TaxWorkpaperGrid.vue'
import { useRoute, useRouter } from 'vue-router'
import {
  TAX_WORKPAPER_INDEX, ALL_TAX_WORKPAPER_SHEETS, TAX_WORKPAPER_INDEX_CODE,
  findTaxWorkpaperSheet, findTaxWorkpaperGroup,
} from '@/constants/taxWorkpaperIndex'

defineOptions({ name: 'TaxWorkpaperPage' })

const route = useRoute()
const router = useRouter()

const sheetCode = computed(() => (typeof route.query.sheet === 'string' ? route.query.sheet : ''))
const sheet = computed(() => (sheetCode.value ? findTaxWorkpaperSheet(sheetCode.value) : undefined))
const group = computed(() => (sheetCode.value ? findTaxWorkpaperGroup(sheetCode.value) : undefined))

const TOOLBAR = ['导入', '导出', '保存'] as const

function openSheet(code: string) {
  router.push({ name: 'TaxWorkpapers', params: route.params, query: { ...route.query, sheet: code } })
}
</script>

<style scoped>
.gt-twp-page { padding: 20px 24px; }
.gt-twp-page__home {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  text-align: center;
}
.gt-twp-page__home-title {
  margin: 0 0 10px;
  font-size: 17px;
  color: #4a4a55;
}
.gt-twp-page__home-hint {
  margin: 0;
  font-size: 13px;
  line-height: 1.8;
  color: #9a9aa4;
}
.gt-twp-page__title {
  margin: 0 0 14px;
  font-size: 16px;
  font-weight: 700;
  color: var(--gt-color-primary, #4b2d77);
}
.gt-twp-page__index {
  width: 100%;
  max-width: 900px;
  border-collapse: collapse;
  font-size: 13px;
}
.gt-twp-page__index th,
.gt-twp-page__index td {
  padding: 7px 12px;
  border: 1px solid #e8e8ec;
  text-align: left;
}
.gt-twp-page__index th {
  background: #f3edfa;
  color: var(--gt-color-primary, #4b2d77);
  font-weight: 700;
}
.gt-twp-page__col-code {
  width: 130px;
  font-variant-numeric: tabular-nums;
}
.gt-twp-page__group-row td {
  background: #fbf9fe;
  font-weight: 700;
  color: #5c5c68;
}
.gt-twp-page__sheet-row { cursor: pointer; }
.gt-twp-page__sheet-row:hover td {
  background: #faf6ff;
  color: var(--gt-color-primary, #4b2d77);
}
/* ── 单张底稿：取值照 CITAR workpaper-screen.css ── */
.gt-twp-sheet { max-width: 1180px; }
.gt-twp-sheet__header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 14px 20px;
  border-radius: 10px;
  background: linear-gradient(90deg, #5b1a8c 0%, #8b3fd0 100%);
}
.gt-twp-sheet__code {
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  color: rgba(255, 255, 255, 0.78);
}
.gt-twp-sheet__title {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  color: #fff;
}
.gt-twp-sheet__group {
  margin-left: auto;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.78);
}
/* 页签一行横向滚动而非换行：纵向空间留给宽表 */
.gt-twp-sheet__tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  overflow-x: auto;
  overflow-y: hidden;
  border-bottom: 1px solid #e4d8f3;
  scrollbar-width: thin;
}
.gt-twp-sheet__tabs::-webkit-scrollbar { height: 6px; }
.gt-twp-sheet__tabs::-webkit-scrollbar-thumb {
  background: #d9c4ee;
  border-radius: 3px;
}
.gt-twp-sheet__tab {
  flex: 0 0 auto;
  padding: 9px 14px;
  border: none;
  border-bottom: 2px solid transparent;
  background: none;
  font: inherit;
  font-size: 13px;
  color: #6b6b76;
  cursor: pointer;
  white-space: nowrap;
}
.gt-twp-sheet__tab:hover { color: #6e0ba6; }
.gt-twp-sheet__tab:focus-visible {
  outline: 2px solid #6e0ba6;
  outline-offset: -2px;
}
.gt-twp-sheet__tab--active {
  border-bottom-color: #6e0ba6;
  color: #6e0ba6;
  font-weight: 700;
}
.gt-twp-sheet__toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
}
.gt-twp-sheet__btn {
  height: 32px;
  padding: 0 14px;
  border: 1px solid #d9d9e0;
  border-radius: 6px;
  background: #fff;
  font-size: 13px;
  color: #4a4a55;
  cursor: pointer;
}
.gt-twp-sheet__btn:hover:not(:disabled) {
  border-color: #6e0ba6;
  color: #6e0ba6;
}
.gt-twp-sheet__btn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}
.gt-twp-sheet__panel {
  margin-top: 14px;
  padding: 18px 20px 22px;
  background: #fff;
  border: 1px solid #e8e8ec;
  border-radius: 10px;
}
/* 表格面板去掉内边距，让控件贴满面板 */
.gt-twp-sheet__panel--grid {
  padding: 0;
  overflow: hidden;
}
</style>
