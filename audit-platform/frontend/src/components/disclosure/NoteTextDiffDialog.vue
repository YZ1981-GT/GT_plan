<script setup lang="ts">
/**
 * NoteTextDiffDialog — 现有 / 拟写入并排对比（Task 49，AC-9.3~9.4 / 10.2）
 *
 * - v-model 为 boolean（R-24：首版绑 string|null，关闭时 Element Plus 写回 false 致类型错乱）；
 * - 已有内容可显式选「替换 / 追加」，追加结果取后端预演的 append_html（apply 逐字比对 hash）；
 * - 变量替换可逐项撤销（撤销后须重新预览）；高风险标记须逐项勾选核对后才能采用。
 */
import { computed, ref, watch } from 'vue'
import { sanitizeHtml } from '@/composables/useSanitize'
import type { ApplyMode, PreviewItem } from '@/composables/useNoteTextBatch'
import { canAppend as appendAllowed, flagLabel, highRiskFlags, targetLabel } from './noteTextBatchLabels'

const props = defineProps<{
  modelValue: boolean
  item: PreviewItem | null
  mode: ApplyMode
  revokedIds: string[]
  stale: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'update:mode': [value: ApplyMode]
  'toggle-revocation': [replacementId: string]
  'confirm': [item: PreviewItem]
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const risks = computed(() => (props.item ? highRiskFlags(props.item) : []))
const acknowledged = ref<Set<string>>(new Set())
watch(() => props.item?.source_id, () => { acknowledged.value = new Set() })

function toggleAck(flag: string, checked: boolean) {
  const next = new Set(acknowledged.value)
  if (checked) next.add(flag)
  else next.delete(flag)
  acknowledged.value = next
}

const allAcknowledged = computed(() => risks.value.every(f => acknowledged.value.has(f)))
/** 已有正文且追加会增加内容才给「替换 / 追加」；来源段落已全在现有正文里时只能替换（第 26 组） */
const canAppend = computed(() => !!props.item && appendAllowed(props.item))
const proposedHtml = computed(() => {
  if (!props.item) return ''
  return props.mode === 'append' && canAppend.value && props.item.append_html !== null
    ? props.item.append_html : props.item.proposed_html
})

function onConfirm() {
  if (!props.item || !allAcknowledged.value) return
  emit('confirm', props.item)
  visible.value = false
}
</script>

<template>
  <el-dialog v-model="visible" :title="item ? `📝 对比：${targetLabel(item)}` : '📝 对比'" width="80%" append-to-body>
    <template v-if="item">
      <div class="gt-ntd-toolbar">
        <span>来源章节：{{ item.source_title }}</span>
        <el-radio-group v-if="canAppend" :model-value="mode" size="small" @update:model-value="(v: any) => emit('update:mode', v)">
          <el-radio-button value="replace">替换现有内容</el-radio-button>
          <el-radio-button value="append">追加到现有内容后</el-radio-button>
        </el-radio-group>
        <span v-else-if="item.append_html !== null" class="gt-ntd-muted">来源段落已全部在现有内容中，追加不会增加内容，只能替换</span>
        <span v-else class="gt-ntd-muted">目标章节当前为空，将直接写入</span>
      </div>
      <el-alert v-if="stale" type="warning" :closable="false" show-icon title="已修改变量替换，拟写入内容需重新预览后才是最终结果" />
      <div class="gt-ntd-columns">
        <section>
          <h4>现有内容</h4>
          <div class="gt-ntd-pane" v-html="sanitizeHtml(item.before_html || '<p>（空）</p>')" />
        </section>
        <section>
          <h4>拟写入内容（{{ mode === 'append' && canAppend ? '追加后' : '替换后' }}）</h4>
          <div class="gt-ntd-pane" v-html="sanitizeHtml(proposedHtml || '<p>（空）</p>')" />
        </section>
      </div>
      <div v-if="item.replacements.length" class="gt-ntd-block">
        <h4>变量替换</h4>
        <div v-for="r in item.replacements" :key="r.replacement_id" class="gt-ntd-row">
          <span><del>{{ r.old_value }}</del> → <strong>{{ r.new_value }}</strong></span>
          <el-button v-if="r.reversible" size="small" link type="primary" @click="emit('toggle-revocation', r.replacement_id)">
            {{ revokedIds.includes(r.replacement_id) ? '恢复替换' : '撤销替换' }}
          </el-button>
        </div>
      </div>
      <div v-if="risks.length" class="gt-ntd-block">
        <h4>风险核对（逐项确认后才能采用）</h4>
        <el-checkbox v-for="flag in risks" :key="flag" :model-value="acknowledged.has(flag)"
          @change="(v: any) => toggleAck(flag, !!v)">已核对：{{ flagLabel(flag) }}</el-checkbox>
      </div>
    </template>
    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button type="primary" :disabled="!item || !allAcknowledged" @click="onConfirm">采用此章</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.gt-ntd-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.gt-ntd-muted { color: var(--el-text-color-secondary); font-size: 13px; }
.gt-ntd-columns { display: flex; gap: 16px; margin-top: 8px; }
.gt-ntd-columns section { flex: 1; min-width: 0; }
.gt-ntd-columns h4, .gt-ntd-block h4 { margin: 0 0 6px; font-size: 13px; }
.gt-ntd-pane { border: 1px solid var(--el-border-color); border-radius: 4px; padding: 12px; min-height: 120px; max-height: 50vh; overflow-y: auto; }
.gt-ntd-block { margin-top: 12px; }
.gt-ntd-row { display: flex; align-items: center; justify-content: space-between; font-size: 13px; }
</style>
