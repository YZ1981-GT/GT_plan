<template>
  <div class="e0-lower-zone" v-if="isE0">
    <!-- 一、函证情况（品种矩阵由父组件通过 slot 注入） -->
    <section class="e0-lower-zone__block">
      <h4 class="e0-lower-zone__title">一、函证情况</h4>
      <slot name="matrix" />
    </section>

    <!-- 二、样本选择 -->
    <section class="e0-lower-zone__block">
      <h4 class="e0-lower-zone__title">二、样本选择</h4>
      <div
        v-for="item in sampleSelectionTexts"
        :key="item.key"
        class="e0-lower-zone__method-hint"
      >
        <p>{{ item.text }}</p>
      </div>
      <div class="e0-lower-zone__input-area">
        <label>未函证账户的理由：</label>
        <el-input
          v-model="unfundedReason"
          type="textarea"
          :autosize="{ minRows: 3 }"
          :disabled="readonly"
          placeholder="如果存在未函证的银行账户，请记录不执行函证程序的理由"
          @change="handleSave(E0_UNFUNDED_REASON_KEY, unfundedReason)"
        />
      </div>
    </section>

    <!-- 三、审计说明 -->
    <section class="e0-lower-zone__block">
      <h4 class="e0-lower-zone__title">三、审计说明</h4>
      <div
        v-for="item in auditNoteTexts"
        :key="item.key"
        class="e0-lower-zone__note-section"
      >
        <div class="e0-lower-zone__note-label">{{ item.text }}</div>
        <div class="e0-lower-zone__note-input">
          <el-input
            v-model="auditNotes[item.key]"
            type="textarea"
            :autosize="{ minRows: 3 }"
            :disabled="readonly"
            :placeholder="`请填写${item.text.replace(/^\d+\./, '').trim()}的内容`"
            @change="handleSave(E0_AUDIT_NOTE_KEY_PREFIX + item.key, auditNotes[item.key])"
          />
          <div class="e0-lower-zone__ai-bar">
            <el-button size="small" :disabled="readonly" @click="$emit('ai-generate', item.key)">
              🤖 AI 辅助
            </el-button>
            <el-button size="small" :disabled="readonly" @click="$emit('review', item.key)">
              💬 复核
            </el-button>
          </div>
        </div>
      </div>
    </section>

    <!-- 四、审计结论 -->
    <section class="e0-lower-zone__block">
      <h4 class="e0-lower-zone__title">四、审计结论</h4>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="readonly"
        placeholder="请填写审计结论"
        @change="handleSave(E0_CONCLUSION_KEY, conclusion)"
      />
      <div class="e0-lower-zone__ai-bar">
        <el-button size="small" :disabled="readonly" @click="$emit('ai-generate', 'conclusion')">
          🤖 AI 辅助
        </el-button>
        <el-button size="small" :disabled="readonly" @click="$emit('review', 'conclusion')">
          💬 复核
        </el-button>
      </div>
    </section>

    <!-- 提示 -->
    <section class="e0-lower-zone__block e0-lower-zone__tips">
      <div class="e0-lower-zone__method-hint e0-lower-zone__method-hint--amber">
        <p><strong>{{ tipsTitle }}</strong></p>
        <p v-for="(line, idx) in tipsLines" :key="idx">{{ line }}</p>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  E0_LOWER_ZONE_TEXTS,
  E0_UNFUNDED_REASON_KEY,
  E0_AUDIT_NOTE_KEY_PREFIX,
  E0_CONCLUSION_KEY,
  getTextsForBlock,
} from './e0SummaryLowerZone'

const props = defineProps<{
  /** 是否为 E0 循环 */
  isE0: boolean
  /** 只读模式 */
  readonly: boolean
  /** 已持久化的 checklist responses（key → value） */
  responses?: Record<string, string>
}>()

const emit = defineEmits<{
  (e: 'save', key: string, value: string): void
  (e: 'ai-generate', section: string): void
  (e: 'review', section: string): void
}>()

// 文字分组
const sampleSelectionTexts = computed(() => getTextsForBlock('sample_selection'))
const auditNoteTexts = computed(() => getTextsForBlock('audit_note'))
const tipsTexts = computed(() => getTextsForBlock('tips'))
const tipsTitle = computed(() => tipsTexts.value.find(t => t.key === 'tips_title')?.text ?? '')
const tipsLines = computed(() => {
  const body = tipsTexts.value.find(t => t.key === 'tips_body')?.text ?? ''
  return body.split('\n').filter(Boolean)
})

// 录入数据
const unfundedReason = ref('')
const auditNotes = ref<Record<string, string>>({})
const conclusion = ref('')

onMounted(() => {
  const r = props.responses ?? {}
  unfundedReason.value = r[E0_UNFUNDED_REASON_KEY] ?? ''
  conclusion.value = r[E0_CONCLUSION_KEY] ?? ''
  for (const item of auditNoteTexts.value) {
    auditNotes.value[item.key] = r[E0_AUDIT_NOTE_KEY_PREFIX + item.key] ?? ''
  }
})

function handleSave(key: string, value: string) {
  emit('save', key, value)
}
</script>

<style scoped>
.e0-lower-zone {
  margin-top: 24px;
  border-top: 1px solid var(--el-border-color-light);
  padding-top: 16px;
}
.e0-lower-zone__block {
  margin-bottom: 20px;
}
.e0-lower-zone__title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--el-text-color-primary);
}
.e0-lower-zone__method-hint {
  border-left: 3px solid var(--el-color-warning-light-3);
  background: var(--el-color-warning-light-9);
  padding: 8px 12px;
  margin-bottom: 8px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
}
.e0-lower-zone__method-hint--amber {
  border-left-color: #e6a23c;
  background: #fdf6ec;
}
.e0-lower-zone__input-area {
  margin-top: 12px;
}
.e0-lower-zone__input-area label {
  display: block;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}
.e0-lower-zone__note-section {
  margin-bottom: 16px;
}
.e0-lower-zone__note-label {
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 4px;
  color: var(--el-text-color-primary);
}
.e0-lower-zone__note-input {
  position: relative;
}
.e0-lower-zone__ai-bar {
  display: flex;
  gap: 8px;
  margin-top: 6px;
  justify-content: flex-end;
}
.e0-lower-zone__tips {
  margin-top: 16px;
}
</style>
