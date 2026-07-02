<script setup lang="ts">
/**
 * E1TabAccountCommitment.vue — E1-11 承诺书 (段落式极简)
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.10
 *
 * - No composable — directly uses allResponses for simple fields
 * - Paragraph form: 承诺日期 | 承诺人 | 承诺内容(textarea) | 签字确认(Y/N)
 * - item_id prefix: 'E1-account-commit-*'
 * - debounce 2s save
 *
 * Requirements: 8.3
 */
import { ref, inject, toRef, watch, onBeforeUnmount, type Ref } from 'vue'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveImmediate: (items: any[]) => Promise<void>
  debouncedSave: (items: any[]) => Promise<void>
  isReadonly: boolean
  sheetName?: string
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const displayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) =>
    v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'E1-account-commit'
const DEFAULT_CONTENT = `本公司承诺：截至资产负债表日，本公司已在贵所提供的银行账户清单中完整列示了所有银行账户信息，不存在未列示的银行账户。

上述银行账户信息完整、真实，如有遗漏或虚假，本公司愿承担由此造成的一切后果。`

// ─── State ───────────────────────────────────────────────────────────────────

const commitDate = ref('')
const commitPerson = ref('')
const commitContent = ref(DEFAULT_CONTENT)
const signConfirm = ref<'Y' | 'N' | ''>('')

// ─── Load from allResponses ──────────────────────────────────────────────────

function loadFromResponses(): void {
  const responses = props.allResponses
  commitDate.value = responses.get(`${ITEM_PREFIX}-date`)?.remark || ''
  commitPerson.value = responses.get(`${ITEM_PREFIX}-person`)?.remark || ''
  commitContent.value = responses.get(`${ITEM_PREFIX}-content`)?.remark || DEFAULT_CONTENT
  signConfirm.value = (responses.get(`${ITEM_PREFIX}-sign`)?.conclusion || '') as 'Y' | 'N' | ''
}

loadFromResponses()

// ─── Debounce Save ───────────────────────────────────────────────────────────

let saveTimer: ReturnType<typeof setTimeout> | null = null

function scheduleSave(): void {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    saveTimer = null
    persistAll()
  }, 2000)
}

function persistAll(): void {
  const items = [
    { item_id: `${ITEM_PREFIX}-date`, conclusion: null, remark: commitDate.value },
    { item_id: `${ITEM_PREFIX}-person`, conclusion: null, remark: commitPerson.value },
    { item_id: `${ITEM_PREFIX}-content`, conclusion: null, remark: commitContent.value },
    { item_id: `${ITEM_PREFIX}-sign`, conclusion: signConfirm.value || null, remark: null },
  ]
  const responses = props.allResponses
  for (const item of items) {
    responses.set(item.item_id, item)
  }
  props.saveImmediate(items).catch(() => { /* silent */ })
}

// ─── Handlers ────────────────────────────────────────────────────────────────

function onDateChange(val: string): void {
  if (props.isReadonly) return
  commitDate.value = val || ''
  scheduleSave()
}

function onPersonChange(val: string): void {
  if (props.isReadonly) return
  commitPerson.value = val
  scheduleSave()
}

function onContentChange(val: string): void {
  if (props.isReadonly) return
  commitContent.value = val
  scheduleSave()
}

function onSignChange(val: string): void {
  if (props.isReadonly) return
  signConfirm.value = val as 'Y' | 'N'
  scheduleSave()
}

// ─── Cleanup ─────────────────────────────────────────────────────────────────

onBeforeUnmount(() => {
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
    persistAll()
  }
})
</script>

<template>
  <div class="e1-tab-account-commitment">
    <el-card shadow="never" class="commit-card">
      <template #header>
        <span class="card-title">银行账户情况承诺书</span>
      </template>

      <el-form label-width="100px" size="default">
        <el-form-item label="承诺日期">
          <el-date-picker
            :model-value="commitDate"
            :disabled="isReadonly"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="选择日期"
            style="width: 220px"
            @update:model-value="onDateChange"
          />
        </el-form-item>

        <el-form-item label="承诺人">
          <el-input
            :model-value="commitPerson"
            :disabled="isReadonly"
            placeholder="填写承诺人姓名"
            style="width: 220px"
            @change="onPersonChange"
          />
        </el-form-item>

        <el-form-item label="承诺内容">
          <el-input
            :model-value="commitContent"
            :disabled="isReadonly"
            type="textarea"
            :autosize="{ minRows: 4, maxRows: 12 }"
            placeholder="填写承诺内容"
            @change="onContentChange"
          />
        </el-form-item>

        <el-form-item label="签字确认">
          <el-radio-group
            :model-value="signConfirm"
            :disabled="isReadonly"
            @change="onSignChange"
          >
            <el-radio value="Y">已确认签字</el-radio>
            <el-radio value="N">未签字</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.e1-tab-account-commitment {
  padding: 12px 0;
}
.commit-card {
  max-width: 800px;
}
.card-title {
  font-weight: 600;
  font-size: 15px;
}
</style>
