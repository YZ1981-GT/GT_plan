<template>
  <div v-if="sources.length" class="fs-sources">
    <p class="fs-sources__head">数据源头</p>
    <ul class="fs-sources__list">
      <li v-for="(s, i) in sources" :key="`${s.kind}|${i}`" class="fs-sources__item">
        <div class="fs-sources__title">
          <span>{{ s.title }}</span>
          <span v-if="s.amount" class="fs-sources__amount">影响 {{ fmtMoney(numberOf(s.amount)) }}</span>
          <button
            v-if="!s.rows.length && canOpen(s.page)"
            type="button"
            class="fs-sources__link"
            @click="emit('open', { page: s.page!, code: '' })"
          >去{{ pageLabel(s.page) }}</button>
        </div>
        <ul v-if="s.rows.length" class="fs-sources__rows">
          <li v-for="(r, j) in s.rows" :key="`${r.code}|${r.statement ?? ''}|${r.r ?? ''}|${j}`" class="fs-sources__row">
            <button
              v-if="canOpen(s.page, r)"
              type="button"
              class="fs-sources__link"
              :title="`去${pageLabel(s.page)}定位到这一行`"
              @click="emit('open', { page: s.page!, code: r.code, row: r })"
            >{{ rowText(s.page, r) }}</button>
            <span v-else>{{ rowText(s.page, r) }}</span>
            <span class="fs-sources__amount">{{ fmtMoney(numberOf(r.amount)) }}</span>
            <span class="fs-sources__note">{{ r.note }}</span>
            <button
              v-if="r.journal && r.code"
              type="button"
              class="fs-sources__link fs-sources__link--minor"
              @click="emit('open', { page: 'journal', code: r.code })"
            >看序时账</button>
          </li>
          <li v-if="s.more" class="fs-sources__more">另有 {{ s.more }} 行未列出</li>
        </ul>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
/**
 * 「其他问题」里一条问题的数据源头（spec citar-fs-issue-source-locate）：每类原因带金额，下列源头行；
 * 点行 → open 事件交给页面跳转（本页格子 page = statement 由页面就地定位）。本组件不发请求、不跳路由。
 */
import { SOURCE_PAGE_LABELS, sourceLink } from '../fsIssueSources'
import { numberOf, type FsSource, type FsSourcePage, type FsSourceRow } from '../taxAssuranceApi'
import { fmtMoney } from '../useCitarProject'

export interface FsSourceOpen {
  page: FsSourcePage
  code: string
  row?: FsSourceRow
}

defineProps<{ sources: FsSource[] }>()
const emit = defineEmits<{ open: [payload: FsSourceOpen] }>()

function pageLabel(page: FsSourcePage | null): string {
  if (!page || page === 'statement') return '本页'
  return SOURCE_PAGE_LABELS[page]
}

function canOpen(page: FsSourcePage | null, row?: FsSourceRow): boolean {
  if (page === 'statement') return Boolean(row?.statement)
  return Boolean(sourceLink(page, row?.code ?? ''))
}

function rowText(page: FsSourcePage | null, r: FsSourceRow): string {
  if (page === 'statement') return `本页「${r.name}」`
  const who = [r.code, r.name].filter(Boolean).join(' ')
  return `${pageLabel(page)} ${who}`.trim()
}
</script>

<style scoped>
.fs-sources {
  flex: 1 0 100%;
  margin-top: 6px;
  padding: 8px 10px;
  border-top: 1px dashed #f0d9b5;
  font-size: var(--citar-fs-12);
  color: var(--citar-c-5c5c68);
}

.fs-sources__head {
  margin: 0 0 4px;
  font-weight: 600;
  color: var(--citar-c-8a5300);
}

.fs-sources__list,
.fs-sources__rows {
  margin: 0;
  padding: 0;
  list-style: none;
}

.fs-sources__item + .fs-sources__item {
  margin-top: 6px;
}

.fs-sources__title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  color: var(--citar-c-1f1f1f);
}

.fs-sources__rows {
  margin-top: 2px;
  padding-left: 14px;
}

.fs-sources__row {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 8px;
  line-height: 1.8;
}

.fs-sources__amount {
  font-variant-numeric: tabular-nums;
  color: var(--citar-c-8a5300);
}

.fs-sources__note {
  color: var(--citar-c-8c8c96);
}

.fs-sources__more {
  color: var(--citar-c-8c8c96);
}

.fs-sources__link {
  padding: 0;
  border: 0;
  background: none;
  font: inherit;
  color: var(--citar-c-6e0ba6);
  text-decoration: underline;
  text-underline-offset: 2px;
  cursor: pointer;
}

.fs-sources__link--minor {
  color: var(--citar-c-8c8c96);
}

.fs-sources__link:hover,
.fs-sources__link:focus-visible {
  color: var(--citar-c-4c1273);
}
</style>
