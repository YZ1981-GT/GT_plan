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
import { ref, inject, toRef, onBeforeUnmount, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtIndexChip from '../GtIndexChip.vue'
import {
  E1_ACCOUNT_COMMIT_SNAPSHOT_KEY,
  E1_ACCOUNT_LIST_STORAGE_KEY,
  type AccountCommitSnapshotRow,
} from '../composables/useE1AccountList'
import { useE1AiGenerate } from '../composables/useE1AiGenerate'
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
const NOTE_KEY = 'E1-commit-audit-note'
const CONCLUSION_KEY = 'E1-commit-audit-conclusion'
const CHECK_SUMMARY_KEY = 'E1-account-commit-check-summary'
const DEFAULT_CONTENT = `致：致同会计师事务所

我们确认，截至____年____月____日，我公司已向贵所提供了所有银行账户的完整信息，包括但不限于：
1. 所有已开立的银行账户清单
2. 所有银行账户的对账单
3. 所有银行账户的余额调节表
4. 所有银行账户的函证回函
5. 所有银行账户的质押、冻结等限制情况

我们承诺：
1. 上述信息真实、完整、准确；
2. 不存在未向贵所披露的银行账户；
3. 不存在隐瞒银行账户信息的情况；
4. 如有违反上述承诺，我们愿意承担相应的法律责任。`

// ─── State ───────────────────────────────────────────────────────────────────

const commitUnit = ref('')
const commitLegalRep = ref('')
const commitFinanceHead = ref('')
const commitDate = ref('')
const commitContent = ref(DEFAULT_CONTENT)
const signConfirm = ref<'Y' | 'N' | ''>('')

// 审计说明 / 审计结论 / AI核对摘要
const auditNote = ref('')
const auditConclusion = ref('')
const checkSummary = ref('')
const snapshotRows = ref<AccountCommitSnapshotRow[]>([])
const snapshotGeneratedAt = ref('')
const { generateText, isGenerating } = useE1AiGenerate(toRef(props, 'wpId') as Ref<string>)

// ─── Load from allResponses ──────────────────────────────────────────────────

function loadFromResponses(): void {
  const responses = props.allResponses
  commitUnit.value = responses.get(`${ITEM_PREFIX}-unit`)?.remark || ''
  // 兼容旧字段 -person（承诺人）→ 法定代表人
  commitLegalRep.value = responses.get(`${ITEM_PREFIX}-legalrep`)?.remark
    || responses.get(`${ITEM_PREFIX}-person`)?.remark || ''
  commitFinanceHead.value = responses.get(`${ITEM_PREFIX}-finance`)?.remark || ''
  commitDate.value = responses.get(`${ITEM_PREFIX}-date`)?.remark || ''
  commitContent.value = responses.get(`${ITEM_PREFIX}-content`)?.remark || DEFAULT_CONTENT
  signConfirm.value = (responses.get(`${ITEM_PREFIX}-sign`)?.conclusion || '') as 'Y' | 'N' | ''
  auditNote.value = responses.get(NOTE_KEY)?.remark || ''
  auditConclusion.value = responses.get(CONCLUSION_KEY)?.remark || ''
  checkSummary.value = responses.get(CHECK_SUMMARY_KEY)?.remark || ''
  const snapshotRaw = responses.get(E1_ACCOUNT_COMMIT_SNAPSHOT_KEY)?.remark
  if (snapshotRaw) {
    try {
      const parsed = JSON.parse(snapshotRaw)
      snapshotRows.value = Array.isArray(parsed) ? parsed : Array.isArray(parsed?.rows) ? parsed.rows : []
      snapshotGeneratedAt.value = Array.isArray(parsed) ? '' : String(parsed?.generatedAt || '')
    } catch {
      snapshotRows.value = []
      snapshotGeneratedAt.value = ''
    }
  }
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
    { item_id: `${ITEM_PREFIX}-unit`, conclusion: null, remark: commitUnit.value },
    { item_id: `${ITEM_PREFIX}-legalrep`, conclusion: null, remark: commitLegalRep.value },
    { item_id: `${ITEM_PREFIX}-finance`, conclusion: null, remark: commitFinanceHead.value },
    { item_id: `${ITEM_PREFIX}-date`, conclusion: null, remark: commitDate.value },
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

function onUnitChange(val: string): void {
  if (props.isReadonly) return
  commitUnit.value = val
  scheduleSave()
}

function onLegalRepChange(val: string): void {
  if (props.isReadonly) return
  commitLegalRep.value = val
  scheduleSave()
}

function onFinanceChange(val: string): void {
  if (props.isReadonly) return
  commitFinanceHead.value = val
  scheduleSave()
}

function onDateChange(val: string): void {
  if (props.isReadonly) return
  commitDate.value = val || ''
  scheduleSave()
}

function restoreStandardContent(): void {
  if (props.isReadonly) return
  commitContent.value = DEFAULT_CONTENT
  scheduleSave()
  ElMessage.success('已恢复标准承诺正文')
}

async function generateSnapshot(): Promise<void> {
  if (props.isReadonly) return
  const raw = props.allResponses.get(E1_ACCOUNT_LIST_STORAGE_KEY)?.remark
  let sourceRows: Record<string, unknown>[] = []
  try {
    const parsed = raw ? JSON.parse(raw) : []
    sourceRows = Array.isArray(parsed) ? parsed : []
  } catch {
    ElMessage.warning('E1-10 账户清单数据格式异常，无法生成快照')
    return
  }
  const rows = sourceRows
    .filter(row => String(row.bank || '').trim() || String(row.accountNo || '').trim())
    .map(row => ({
      bank: String(row.bank || ''),
      accountNo: String(row.accountNo || ''),
      accountType: String(row.accountType || ''),
      openDate: String(row.openDate || ''),
      closeDate: String(row.closeDate || ''),
      accountStatus: String(row.accountStatus || (row.isClosedThisPeriod === 'Y' ? '已注销' : '正常')),
      restrictionStatus: String(row.restrictionStatus || '无'),
    }))
  if (!rows.length) {
    ElMessage.warning('E1-10 尚无可用于签署的账户数据')
    return
  }
  if (snapshotRows.value.length) {
    try {
      await ElMessageBox.confirm('重新生成将覆盖当前签署快照；已保存快照不会随 E1-10 自动变化。', '覆盖签署快照', {
        confirmButtonText: '确认覆盖',
        cancelButtonText: '取消',
        type: 'warning',
      })
    } catch {
      return
    }
  }
  const generatedAt = new Date().toISOString()
  const item = {
    item_id: E1_ACCOUNT_COMMIT_SNAPSHOT_KEY,
    conclusion: null,
    remark: JSON.stringify({ generatedAt, rows }),
  }
  snapshotRows.value = rows
  snapshotGeneratedAt.value = generatedAt
  props.allResponses.set(E1_ACCOUNT_COMMIT_SNAPSHOT_KEY, item)
  await props.saveImmediate([item])
  ElMessage.success(`已生成 ${rows.length} 个账户的签署快照`)
}

function aiContext(): Record<string, unknown> {
  return {
    snapshotGeneratedAt: snapshotGeneratedAt.value,
    snapshotRows: snapshotRows.value,
    signConfirm: signConfirm.value,
    commitDate: commitDate.value,
  }
}

async function generateAiText(target: 'summary' | 'note' | 'conclusion'): Promise<void> {
  if (props.isReadonly) return
  const config = {
    summary: {
      section: 'account-commitment-check-summary',
      prompt: '请根据签署账户快照生成账户核对摘要，说明账户数量、账户状态、销户及冻结、抵押或质押情况。不要修改或引用固定承诺正文，不要虚构未提供事实。',
      existingContent: checkSummary.value,
      confirmTitle: 'AI 生成账户核对摘要',
    },
    note: {
      section: 'account-commitment-audit-note',
      prompt: '请根据签署账户快照、签署状态和声明日期生成审计说明，说明承诺函取得过程及与账户清单、征信报告的印证情况。不要修改或引用固定承诺正文，不要虚构未提供事实。',
      existingContent: auditNote.value,
      confirmTitle: 'AI 生成审计说明',
    },
    conclusion: {
      section: 'account-commitment-audit-conclusion',
      prompt: '请根据签署账户快照、签署状态和核对结果生成审计结论，明确是否已取得完整性书面承诺及账户完整性认定是否满足。不要修改或引用固定承诺正文，不要虚构未提供事实。',
      existingContent: auditConclusion.value,
      confirmTitle: 'AI 生成审计结论',
    },
  } as const
  const current = config[target]
  const text = await generateText({
    section: current.section,
    prompt: current.prompt,
    context: aiContext(),
    existingContent: current.existingContent,
    confirmTitle: current.confirmTitle,
  })
  if (!text) return
  if (target === 'summary') saveCheckSummary(text)
  else if (target === 'note') saveAuditNote(text)
  else saveAuditConclusion(text)
}

function onSignChange(val: string): void {
  if (props.isReadonly) return
  signConfirm.value = val as 'Y' | 'N'
  scheduleSave()
}

// AI 核对摘要 / 审计说明 / 审计结论 — 即时保存
function saveCheckSummary(val: string): void {
  if (props.isReadonly) return
  checkSummary.value = val
  const item = { item_id: CHECK_SUMMARY_KEY, conclusion: null, remark: val }
  props.allResponses.set(CHECK_SUMMARY_KEY, item)
  props.saveImmediate([item]).catch(() => { /* silent */ })
}

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  const item = { item_id: NOTE_KEY, conclusion: null, remark: val }
  props.allResponses.set(NOTE_KEY, item)
  props.saveImmediate([item]).catch(() => { /* silent */ })
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  const item = { item_id: CONCLUSION_KEY, conclusion: null, remark: val }
  props.allResponses.set(CONCLUSION_KEY, item)
  props.saveImmediate([item]).catch(() => { /* silent */ })
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
      title="审计目标：获取管理层关于已向本所提供全部银行账户信息（含账户清单、对账单、余额调节表、函证回函及受限情况）的书面声明，支持货币资金完整性认定。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-tag size="small" type="success">银行账户情况承诺书 (E1-11)</el-tag>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="generateSnapshot">一键从 E1-10 生成签署快照</el-button>
        <el-tag v-if="snapshotRows.length" size="small" type="info">快照 {{ snapshotRows.length }} 个账户</el-tag>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:E1-1" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:E1-10" :context-project-id="projectId" /></span>
      </div>
    </div>

    <el-card shadow="never" class="commit-card">
      <template #header>
        <span class="card-title">银行账户情况承诺书（被审计单位声明）</span>
      </template>

      <!-- 承诺书正文 -->
      <el-form label-width="100px" size="default">
        <el-form-item label="被审计单位">
          <el-input
            :model-value="commitUnit"
            :disabled="isReadonly"
            placeholder="填写被审计单位全称"
            style="width: 320px"
            @change="onUnitChange"
          />
        </el-form-item>

        <el-form-item label="声明内容">
          <div class="content-toolbar">
            <el-tag size="small" type="info">固定标准正文 · 只读</el-tag>
            <el-button size="small" :disabled="isReadonly || commitContent === DEFAULT_CONTENT" @click="restoreStandardContent">恢复标准正文</el-button>
          </div>
          <el-input
            :model-value="commitContent"
            readonly
            type="textarea"
            :autosize="{ minRows: 10, maxRows: 20 }"
          />
          <div class="field-hint">
            承诺正文禁止 AI 生成和自由修改；历史自定义正文仅只读展示，可恢复为标准正文。
          </div>
        </el-form-item>
      </el-form>

      <div class="snapshot-section">
        <div class="section-title-row">
          <div>
            <span class="section-title">签署账户快照（只读）</span>
            <span v-if="snapshotGeneratedAt" class="snapshot-time">生成于 {{ new Date(snapshotGeneratedAt).toLocaleString() }}</span>
          </div>
          <el-tag size="small" type="warning">保存后不随 E1-10 自动变化</el-tag>
        </div>
        <el-empty v-if="!snapshotRows.length" description="尚未生成签署快照" :image-size="70" />
        <el-table v-else :data="snapshotRows" border size="small" max-height="360" style="width: 100%">
          <el-table-column type="index" label="序号" width="55" align="center" />
          <el-table-column prop="bank" label="开户银行/账户名称" min-width="170" show-overflow-tooltip />
          <el-table-column prop="accountNo" label="账号" min-width="160" show-overflow-tooltip />
          <el-table-column prop="accountType" label="账户性质" min-width="120" />
          <el-table-column prop="openDate" label="开户日期" width="110" />
          <el-table-column prop="closeDate" label="销户日期" width="110" />
          <el-table-column prop="accountStatus" label="账户状态" width="100" />
          <el-table-column prop="restrictionStatus" label="冻结/抵押/质押说明" min-width="180" show-overflow-tooltip />
        </el-table>
      </div>

      <!-- 签署栏 -->
      <div class="sign-block">
        <div class="sign-block-title">签署栏</div>
        <el-form label-width="100px" size="default">
          <el-form-item label="被审计单位">
            <span class="seal-hint">（加盖公章）</span>
          </el-form-item>
          <el-form-item label="法定代表人">
            <el-input
              :model-value="commitLegalRep"
              :disabled="isReadonly"
              placeholder="法定代表人签字"
              style="width: 220px"
              @change="onLegalRepChange"
            />
            <span class="seal-hint">（签字）</span>
          </el-form-item>
          <el-form-item label="财务负责人">
            <el-input
              :model-value="commitFinanceHead"
              :disabled="isReadonly"
              placeholder="财务负责人签字"
              style="width: 220px"
              @change="onFinanceChange"
            />
            <span class="seal-hint">（签字）</span>
          </el-form-item>
          <el-form-item label="声明日期">
            <el-date-picker
              :model-value="commitDate"
              :disabled="isReadonly"
              type="date"
              value-format="YYYY-MM-DD"
              placeholder="选择声明日期"
              style="width: 220px"
              @update:model-value="onDateChange"
            />
          </el-form-item>
          <el-form-item label="签署盖章确认">
            <el-radio-group
              :model-value="signConfirm"
              :disabled="isReadonly"
              @change="onSignChange"
            >
              <el-radio value="Y">已签字盖章确认</el-radio>
              <el-radio value="N">未签署</el-radio>
            </el-radio-group>
          </el-form-item>
        </el-form>
      </div>
    </el-card>

    <!-- AI 核对摘要（不修改固定承诺正文） -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>账户核对摘要</span>
          <el-button size="small" type="primary" plain :loading="isGenerating('account-commitment-check-summary')" :disabled="isReadonly || !snapshotRows.length" @click="generateAiText('summary')">🤖 AI核对</el-button>
        </div>
      </template>
      <el-input
        type="textarea"
        :model-value="checkSummary"
        :disabled="isReadonly"
        :autosize="{ minRows: 4 }"
        placeholder="基于签署快照核对账户数量、状态、销户及冻结/抵押/质押情况；AI 仅辅助生成摘要。"
        @change="(val: string) => saveCheckSummary(val)"
      />
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>审计说明</span>
          <el-button size="small" type="primary" plain :loading="isGenerating('account-commitment-audit-note')" :disabled="isReadonly" @click="generateAiText('note')">🤖 AI辅助</el-button>
        </div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明（如承诺函取得过程、与账户清单/征信报告的印证情况等）..."
        @change="(val: string) => saveAuditNote(val)"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>审计结论</span>
          <el-button size="small" type="primary" plain :loading="isGenerating('account-commitment-audit-conclusion')" :disabled="isReadonly" @click="generateAiText('conclusion')">🤖 AI辅助</el-button>
        </div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="填写审计结论（如是否已取得管理层完整性书面承诺、账户完整性认定是否满足等）..."
        @change="(val: string) => saveAuditConclusion(val)"
      />
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
  max-width: 1100px;
}
.content-toolbar {
  width: 100%;
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.snapshot-section {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px dashed #dcdfe6;
}
.section-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}
.section-title {
  font-weight: 600;
  color: #303133;
}
.snapshot-time {
  margin-left: 10px;
  color: #909399;
  font-size: 12px;
}
.snapshot-section :deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}
.card-title {
  font-weight: 600;
  font-size: 15px;
}
.field-hint {
  margin-top: 6px;
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
}

/* 签署栏 */
.sign-block {
  margin-top: 12px;
  padding: 12px 16px;
  border-top: 1px dashed #dcdfe6;
  background: #fafafa;
  border-radius: 4px;
}
.sign-block-title {
  font-weight: 600;
  color: #606266;
  margin-bottom: 12px;
  font-size: var(--wp-font-size, 13px);
}
.seal-hint {
  margin-left: 8px;
  color: #c0392b;
  font-size: 12px;
}

/* 审计说明 / 审计结论 */
.audit-note-card {
  margin-top: 16px;
  max-width: 800px;
}
.audit-note-card .card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
}
</style>
