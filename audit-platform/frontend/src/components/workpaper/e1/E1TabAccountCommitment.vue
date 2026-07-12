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
import GtIndexChip from '../GtIndexChip.vue'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

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

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

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
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 取得管理层关于银行账户完整性的书面承诺，作为账户完整性认定的支持证据。</p>
        <p>2. 承诺书应由法定代表人或经授权的负责人签字并加盖公章确认。</p>
        <p>3. 管理层承诺不能替代实质性审计程序，仍须执行账户核对（E1-10）与征信查询（E1-18）。</p>
        <p>4. 承诺内容应与银行账户清单、征信报告相互印证，关注是否存在账外账户。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：取得管理层对银行账户完整性的书面承诺，支持货币资金完整性认定。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-tag size="small" type="success">银行账户情况承诺书 (E1-11)</el-tag>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:E1-1" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:E1-10" :context-project-id="projectId" /></span>
      </div>
    </div>

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

/* 编制提示 */
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p {
  margin: 2px 0;
}
.objective-alert {
  margin-bottom: 12px;
}

/* 工具栏 */
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.chip-wrap { display: inline-flex; align-items: center; }

.commit-card {
  max-width: 800px;
}
.card-title {
  font-weight: 600;
  font-size: 15px;
}
</style>
