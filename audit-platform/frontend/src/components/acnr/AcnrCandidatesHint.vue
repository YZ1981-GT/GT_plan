<!--
  AcnrCandidatesHint.vue — 地址解析失败时的可解释提示（T31 / design §12.2~§12.5）

  后端 full_resolve 判不出唯一地址时会返回三样东西：中文 reason、需要补的
  required_context、以及中文 next_step；多义时还带 candidates。本组件把它们按同一
  顺序显示，并允许点选候选 —— 选中后把 addr_id 交给调用方按规范地址重解析，
  避免用户再用会歧义的写法试一遍。

  用于：选址器（FormulaRefPicker）、地址树、GtIndexChip 的详情区。
  文案一律取后端给的中文，组件内不编造原因，也不显示英文错误码。
-->
<template>
  <div v-if="hasAnything" class="gt-acnr-hint">
    <!-- 原因 -->
    <p v-if="reasonText" class="gt-acnr-hint__reason">{{ reasonText }}</p>

    <!-- 需要补的上下文 -->
    <p v-if="requiredContextText" class="gt-acnr-hint__ctx">
      需补充：{{ requiredContextText }}
    </p>

    <!-- 停用条目的替代地址 -->
    <p v-if="result?.deprecated && result?.replaced_by" class="gt-acnr-hint__ctx">
      替代地址：{{ result.replaced_by }}
    </p>

    <!-- 候选 -->
    <template v-if="candidates.length">
      <p class="gt-acnr-hint__label">可选地址（{{ candidates.length }}）：</p>
      <ul class="gt-acnr-hint__list">
        <li v-for="c in candidates" :key="c.addr_id">
          <el-button
            link
            type="primary"
            size="small"
            class="gt-acnr-hint__pick"
            @click="pick(c)"
          >
            {{ c.display_label || c.addr_id }}
          </el-button>
        </li>
      </ul>
    </template>

    <!-- 下一步 -->
    <p v-if="nextStepText" class="gt-acnr-hint__next">{{ nextStepText }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AcnrResolveResult } from '@/services/acnr'

type Candidate = NonNullable<AcnrResolveResult['candidates']>[number]

const props = defineProps<{
  /** 后端 resolve 结果；found=true 时本组件不显示 */
  result?: AcnrResolveResult | null
}>()

const emit = defineEmits<{
  /** 用户点选候选 → 交调用方按 addr_id 重解析 */
  pick: [addrId: string, candidate: Candidate]
}>()

/** 上下文字段名 → 中文说明（后端给的是字段名，界面不能直接甩给用户看） */
const CONTEXT_LABELS: Record<string, string> = {
  parent_wp_code: '所属底稿编码',
  cell_address: '单元格坐标（形如 C10）',
  sheet_code: '表编码',
  project_id: '所属项目',
  year: '审计年度',
}

const candidates = computed<Candidate[]>(() => {
  if (props.result?.found) return []
  return props.result?.candidates ?? []
})

const reasonText = computed(() => (props.result?.found ? '' : props.result?.reason || ''))
const nextStepText = computed(() => (props.result?.found ? '' : props.result?.next_step || ''))

const requiredContextText = computed(() => {
  if (props.result?.found) return ''
  const ctx = props.result?.required_context ?? []
  if (!ctx.length) return ''
  // 未登记的字段名照原样显示，不编中文，便于发现漏登记
  return ctx.map(k => CONTEXT_LABELS[k] || k).join('、')
})

const hasAnything = computed(() =>
  Boolean(reasonText.value || nextStepText.value || requiredContextText.value || candidates.value.length),
)

function pick(c: Candidate) {
  if (!c?.addr_id) return
  emit('pick', c.addr_id, c)
}
</script>

<style scoped>
.gt-acnr-hint {
  font-size: var(--gt-font-size-xs);
  line-height: 1.6;
  color: var(--gt-color-text-secondary);
}

.gt-acnr-hint__reason {
  margin: 0;
  color: var(--gt-color-text-primary);
}

.gt-acnr-hint__ctx,
.gt-acnr-hint__next,
.gt-acnr-hint__label {
  margin: 2px 0 0;
}

.gt-acnr-hint__list {
  margin: 2px 0 0;
  padding-left: 16px;
}

.gt-acnr-hint__pick {
  padding: 0;
  height: auto;
}
</style>
