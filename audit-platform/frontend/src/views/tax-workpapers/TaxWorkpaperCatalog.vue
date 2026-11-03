<template>
  <nav class="tw-catalog" aria-label="底稿目录">
    <div class="tw-catalog__caption">底稿目录</div>

    <!-- 索引置顶：它是全部底稿的总览，不属于任何分类 -->
    <button
      type="button"
      class="tw-catalog__sheet tw-catalog__sheet--index"
      :class="{ 'tw-catalog__sheet--active': activeCode === indexCode }"
      @click="emit('open', indexCode)"
    >
      <span class="tw-catalog__sheet-code">索引</span>税务底稿索引
    </button>

    <div v-for="group in visibleGroups" :key="group.title">
      <button
        type="button"
        class="tw-catalog__group"
        :class="{ 'tw-catalog__group--open': openGroups.has(group.title) }"
        :aria-expanded="openGroups.has(group.title)"
        @click="toggleGroup(group.title)"
      >
        <span class="tw-catalog__caret">{{ openGroups.has(group.title) ? '▾' : '▸' }}</span>
        <span class="tw-catalog__group-name">{{ group.title }}</span>
        <span class="tw-catalog__count">{{ group.sheets.length }}</span>
      </button>

      <template v-if="openGroups.has(group.title)">
        <button
          v-for="sheet in group.sheets"
          :key="sheet.code"
          type="button"
          class="tw-catalog__sheet"
          :class="{ 'tw-catalog__sheet--active': activeCode === sheet.code }"
          @click="emit('open', sheet.code)"
        >
          <span class="tw-catalog__sheet-code">{{ sheet.code }}</span>{{ sheet.name }}
        </button>
      </template>
    </div>
  </nav>
</template>

<script setup lang="ts">
/**
 * 税务底稿二级目录栏（移植自 CITAR ProjectShell 的 shell-subnav）。
 * 分组默认全部收起；当前打开的表所在分组自动展开，否则从索引点进来后目录里看不到高亮项。
 */
import { computed, ref, watch } from 'vue'
import { TAX_WORKPAPER_INDEX, findTaxWorkpaperGroup } from './taxWorkpaperIndex'

const props = defineProps<{
  /** 当前打开的表编号；索引页传 indexCode */
  activeCode: string
  /** 索引页的编号（不是真实底稿） */
  indexCode: string
  /** 标记为「无」且开了隐藏的表 */
  hiddenCodes: ReadonlySet<string>
}>()

const emit = defineEmits<{ (e: 'open', code: string): void }>()

const openGroups = ref<Set<string>>(new Set())

function toggleGroup(title: string) {
  const next = new Set(openGroups.value)
  if (next.has(title)) next.delete(title)
  else next.add(title)
  openGroups.value = next
}

watch(
  () => props.activeCode,
  (code) => {
    const group = findTaxWorkpaperGroup(code)
    if (group && !openGroups.value.has(group.title)) {
      openGroups.value = new Set(openGroups.value).add(group.title)
    }
  },
  { immediate: true },
)

/** 当前表即使被标为「无」也留在目录里：它正开着，消失会让人以为点错了 */
const visibleGroups = computed(() =>
  TAX_WORKPAPER_INDEX.map(group => ({
    title: group.title,
    sheets: group.sheets.filter(s => s.code === props.activeCode || !props.hiddenCodes.has(s.code)),
  })),
)
</script>

<style scoped src="./taxWorkpaperCatalog.css"></style>
