<template>
  <td
    class="is-numeric citar-amount"
    :class="{ 'citar-amount--editable': editable, 'citar-amount--manual': isManual, 'citar-amount--restored': restored }"
    :data-src="srcKey || undefined"
    :data-hint="tip"
    @click="startEdit"
  >
    <span v-if="editing" class="citar-amount__editor">
      <input
        ref="inputRef"
        v-model="text"
        class="citar-amount__input"
        :aria-label="label ? `修改 ${label}` : '修改金额'"
        @keydown.enter.prevent="commit"
        @keydown.esc.prevent="editing = false"
        @blur="commit"
      />
      <!-- mousedown.prevent：不让输入框先失焦提交 -->
      <button
        v-if="isManual"
        type="button"
        class="citar-amount__restore"
        title="去掉手工值，恢复为自动算出的金额"
        @mousedown.prevent
        @click.stop="onRestore"
      >恢复</button>
    </span>
    <template v-else>{{ shown }}</template>
  </td>
</template>

<script setup lang="ts">
/**
 * 报表金额格（审定报表 / 单体财务报表共用，spec citar-table-manual-edit R6 / R7）。
 * 点开改 → edit 事件交回草稿（null = 清空成空白）；有手工值时可「恢复」→ restore 事件。本组件不发请求。
 * 数据来源：`srcKey` 写进 data-src，操作提示写进 data-hint，由页面的悬浮来源卡片读取（spec citar-cell-source-hover；原生 title 已去掉）。
 */
import { computed, nextTick, ref } from 'vue'
import { fmtMoney } from '../useCitarProject'

const props = defineProps<{
  /** 生效值（手工值优先） */
  value: number | string | null | undefined
  /** 已保存的手工值 */
  manual?: boolean
  /** 手工值对应的自动值 */
  auto?: number | string | null
  /** 未保存的修改：undefined = 无草稿；null = 清空 */
  draft?: number | null
  /** 已点「恢复」、未保存 */
  restored?: boolean
  editable?: boolean
  label?: string
  /** 悬浮来源的键（不传不挂） */
  srcKey?: string
}>()

const emit = defineEmits<{ edit: [value: number | null]; restore: [] }>()

const editing = ref(false)
const text = ref('')
const initial = ref('')
const inputRef = ref<HTMLInputElement | null>(null)

const hasDraft = computed(() => props.draft !== undefined)
const isManual = computed(() => hasDraft.value || (Boolean(props.manual) && !props.restored))

const current = computed(() => {
  if (hasDraft.value) return props.draft
  if (props.restored) return props.auto
  return props.value
})

const shown = computed(() => fmtMoney(current.value as any))

const tip = computed(() => {
  if (props.restored) return '已恢复自动值，保存后生效'
  if (isManual.value) {
    const auto = props.manual ? props.auto : props.value
    return `手工修改，自动值：${fmtMoney(auto as any) || '空'}${props.editable ? '（点开可恢复）' : ''}`
  }
  return props.editable ? '点击修改' : undefined
})

function plain(v: unknown): string {
  if (v === null || v === undefined || v === '') return ''
  const n = Number(v)
  return Number.isFinite(n) ? String(n) : String(v)
}

async function startEdit() {
  if (!props.editable || editing.value) return
  editing.value = true
  text.value = plain(current.value)
  initial.value = text.value
  await nextTick()
  inputRef.value?.focus()
  inputRef.value?.select()
}

function commit() {
  if (!editing.value) return
  editing.value = false
  const raw = text.value.trim()
  if (raw === initial.value.trim()) return
  if (raw === '') {
    emit('edit', null)
    return
  }
  const n = Number(raw.replace(/,/g, ''))
  if (!Number.isFinite(n)) return
  emit('edit', n)
}

function onRestore() {
  editing.value = false
  emit('restore')
}
</script>

<style scoped>
.citar-amount--editable {
  cursor: text;
}

.citar-amount--editable:hover {
  outline: 1px solid #c9a8ea;
  outline-offset: -1px;
}

.citar-amount--manual {
  background: #f6efff;
  color: var(--citar-c-6e0ba6);
}

.citar-amount--restored {
  font-style: italic;
}

.citar-amount__editor {
  display: flex;
  align-items: center;
  gap: 4px;
}

.citar-amount__input {
  width: 100%;
  min-width: 100px;
  padding: 2px 4px;
  border: 1px solid var(--citar-c-6e0ba6);
  font: inherit;
  text-align: right;
}

.citar-amount__restore {
  flex: 0 0 auto;
  padding: 1px 6px;
  border: 1px solid #d7c3ee;
  background: #fff;
  font-size: var(--citar-fs-11);
  color: var(--citar-c-6e0ba6);
  cursor: pointer;
  white-space: nowrap;
}
</style>
