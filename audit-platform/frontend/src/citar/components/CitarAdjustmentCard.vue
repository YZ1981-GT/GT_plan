<template>
  <section class="adj-entry" :class="{ 'citar-adj--editing': editing }">
    <div class="adj-entry__head">
      <span class="adj-entry__seq">{{ entry.no || '新分录' }}</span>
      <select v-if="editing && !entry.groupId" v-model="entry.type" class="citar-adj__type">
        <option value="aje">审计调整（AJE）</option>
        <option value="rje">重分类调整（RJE）</option>
      </select>
      <span v-else class="citar-tag citar-tag--type">{{ entry.type === 'rje' ? '重分类调整' : '审计调整' }}</span>
      <span class="citar-tag" :class="`citar-tag--${entry.status}`">{{ statusLabel }}</span>

      <span class="citar-adj__actions">
        <template v-if="editing">
          <button class="citar-btn" type="button" :disabled="busy" @click="emit('cancel')">取消</button>
          <button class="citar-btn citar-btn--primary" type="button" :disabled="busy" @click="onSave">保存</button>
        </template>
        <template v-else>
          <button v-if="editable" class="citar-btn" type="button" :disabled="busy" @click="emit('edit')">编辑</button>
          <button v-if="editable" class="citar-btn citar-btn--danger" type="button" :disabled="busy" @click="emit('remove')">删除</button>
          <button v-if="entry.status === S.DRAFT" class="citar-btn" type="button" :disabled="busy" @click="emit('review', S.PENDING_REVIEW)">提交复核</button>
          <!-- 复核三个动作需要 adjustment:review（经理 / 合伙人），没有权限不显示 -->
          <template v-if="canReview && (entry.status === S.DRAFT || entry.status === S.PENDING_REVIEW)">
            <button class="citar-btn" type="button" :disabled="busy" @click="emit('review', S.REJECTED)">驳回</button>
            <button class="citar-btn citar-btn--primary" type="button" :disabled="busy" @click="emit('review', S.APPROVED)">复核通过</button>
          </template>
          <button v-if="canReview && entry.status === S.APPROVED" class="citar-btn" type="button" :disabled="busy" @click="emit('revoke')">撤回复核</button>
        </template>
      </span>
    </div>

    <p v-if="entry.status === S.REJECTED && entry.rejectionReason && !editing" class="citar-adj__reason">
      驳回原因：{{ entry.rejectionReason }}
    </p>

    <input
      v-if="editing"
      v-model="entry.description"
      class="adj-input citar-adj__desc"
      type="text"
      placeholder="摘要（调整原因）"
    />
    <p v-else-if="entry.description" class="citar-adj__desc-text">{{ entry.description }}</p>

    <div class="adj-grid adj-grid--head">
      <span>调整方向</span><span>科目编号</span><span>科目名称</span><span>金额</span><span />
    </div>

    <div v-for="line in entry.lines" :key="line.key" class="adj-grid">
      <span class="adj-side" :class="`adj-side--${line.side}`">{{ line.side === 'debit' ? '借方' : '贷方' }}</span>
      <template v-if="editing">
        <input
          v-model="line.code"
          class="adj-input"
          type="text"
          :list="datalistId"
          placeholder="科目编号"
          @change="onCodeChange(line)"
        />
        <input v-model="line.name" class="adj-input" type="text" placeholder="科目名称（选编号自动带出）" />
        <input
          v-model="line.amount"
          class="adj-input adj-input--amount"
          type="text"
          inputmode="decimal"
          placeholder="0.00"
          @blur="line.amount = formatAmountInput(line.amount)"
        />
        <!-- 该侧只剩一行时不允许删，否则分录缺一边 -->
        <button
          class="adj-row-remove"
          type="button"
          title="删除此行"
          :disabled="sideCount(line.side) <= 1"
          @click="removeLine(line.key)"
        >×</button>
      </template>
      <template v-else>
        <span class="citar-adj__cell">{{ line.code }}</span>
        <span class="citar-adj__cell">{{ line.name }}</span>
        <span class="citar-adj__cell citar-adj__cell--amount">{{ line.amount }}</span>
        <span />
      </template>
    </div>

    <div v-if="editing" class="adj-entry__actions">
      <button class="adj-add-row" type="button" @click="entry.lines.push(emptyLine('debit'))">+ 借方行</button>
      <button class="adj-add-row" type="button" @click="entry.lines.push(emptyLine('credit'))">+ 贷方行</button>
      <span class="citar-adj__balance" :class="{ 'is-off': !balanced }">
        借方合计 {{ formatAmountInput(totals.debit) }} ／ 贷方合计 {{ formatAmountInput(totals.credit) }}
      </span>
    </div>
    <p v-if="editing && saveError" class="citar-adj__error">{{ saveError }}</p>
  </section>
</template>

<script setup lang="ts">
/** 一条调整分录：查看态显示分录与复核操作，编辑态按 CITAR 录入网格（科目编号可选、带出名称）。 */
import { computed, ref } from 'vue'
import { ADJUSTMENT_STATUS as S, ADJUSTMENT_STATUS_LABELS } from '@/constants/statusEnum'
import {
  emptyLine, formatAmountInput, lineTotals, validateEntry, type AdjEntry, type AdjLine, type ReviewTarget, type Side,
} from '../useCitarAdjustments'

const props = defineProps<{
  entry: AdjEntry
  editing: boolean
  busy: boolean
  datalistId: string
  /** 科目编号 → 名称（选编号后带出名称） */
  accountNames: Map<string, string>
  canReview: boolean
}>()

const emit = defineEmits<{
  edit: []
  cancel: []
  save: []
  remove: []
  review: [status: ReviewTarget]
  revoke: []
}>()

const saveError = ref('')

const statusLabel = computed(() => ADJUSTMENT_STATUS_LABELS[props.entry.status]?.label || props.entry.status)
/** 平台规则：只有草稿与驳回的分录能改、能删 */
const editable = computed(() => props.entry.status === S.DRAFT || props.entry.status === S.REJECTED)

const totals = computed(() => lineTotals(props.entry))
const balanced = computed(() => totals.value.debit === totals.value.credit)

function sideCount(side: Side) {
  return props.entry.lines.filter(l => l.side === side).length
}

function removeLine(key: string) {
  const lines = props.entry.lines
  const i = lines.findIndex(l => l.key === key)
  if (i >= 0) lines.splice(i, 1)
}

function onCodeChange(line: AdjLine) {
  const name = props.accountNames.get(line.code.trim())
  if (name) line.name = name
}

function onSave() {
  // 只填了编号没填名称的行（手输编号、没从下拉里选）：按编号补上标准科目名
  for (const l of props.entry.lines) {
    if (!l.name.trim()) onCodeChange(l)
  }
  saveError.value = validateEntry(props.entry)
  if (!saveError.value) emit('save')
}
</script>

<style scoped src="../styles/adjustment.css"></style>
<style scoped src="../styles/citar-data.css"></style>

<style scoped>
.citar-adj--editing {
  border-color: #c9b3e0;
}

.adj-entry__head {
  gap: 8px;
}

.citar-adj__actions {
  display: flex;
  gap: 6px;
  margin-left: auto;
}

.citar-adj__type {
  height: 28px;
  padding: 0 6px;
  border: 1px solid #d8cfe6;
  border-radius: 6px;
  font: inherit;
  font-size: var(--citar-fs-12);
  color: var(--citar-c-4c1273);
  background: var(--citar-c-ffffff);
}

.citar-adj__desc {
  margin-bottom: 10px;
}

.citar-adj__desc-text {
  margin: 0 0 10px;
  font-size: var(--citar-fs-13);
  color: var(--citar-c-3f3f4a);
}

.citar-adj__reason {
  margin: 0 0 8px;
  font-size: var(--citar-fs-12);
  color: var(--citar-c-a3262a);
}

.citar-adj__cell {
  display: flex;
  align-items: center;
  min-height: 32px;
  padding: 0 10px;
  border-radius: 6px;
  background: var(--citar-c-f7f7fa);
  font-size: var(--citar-fs-13);
  color: var(--citar-c-1f1f1f);
}

.citar-adj__cell--amount {
  justify-content: flex-end;
  font-variant-numeric: tabular-nums;
}

.citar-adj__balance {
  margin-left: auto;
  font-size: var(--citar-fs-12);
  color: var(--citar-c-0b6e4f);
}

.citar-adj__balance.is-off {
  color: var(--citar-c-a3262a);
}

.citar-adj__error {
  margin: 8px 0 0;
  font-size: var(--citar-fs-12);
  color: var(--citar-c-a3262a);
}
</style>
