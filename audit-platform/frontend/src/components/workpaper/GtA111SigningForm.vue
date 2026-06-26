<script setup lang="ts">
/**
 * GtA111SigningForm — A1-11 业务报告签发流转控制表
 *
 * Spec: .kiro/specs/a1-11-signing-control-form/
 * Tasks: 3.1–3.9, 4.1
 *
 * 完整还原 Excel 模板"A1-11 报告签发"sheet 的全部字段和流转逻辑：
 * - 基本信息区（6字段）
 * - 报告信息区（3字段）
 * - 签字流转区（6槽位 + 进度条）
 * - 报告管理区（4字段 + 3签字行）
 * - 已签发报告修改区（Amendment_Section）
 * - 注释区（CAS准则引用）
 * - 只读模式 + 响应式布局 + 打印样式
 */
import { ref, computed, watch } from 'vue'
import { useA111FormData } from './composables/useA111FormData'
import { useA111Signing, SIGN_SLOTS } from './composables/useA111Signing'
import { useAuthStore } from '@/stores/auth'

// ─── Props / Emits (Task 3.1) ────────────────────────────────────────────────

const props = withDefaults(defineProps<{
  wpId: string
  projectId: string
  wpCode: string
  year: number
  readonly?: boolean
}>(), {
  readonly: false,
})

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
}>()

// ─── Auth ────────────────────────────────────────────────────────────────────

const authStore = useAuthStore()

function currentUserName(): string {
  const u = authStore.user
  if (!u) return '审计员'
  return u.full_name || u.username || '审计员'
}

// ─── Form Data Composable ────────────────────────────────────────────────────

const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)

const {
  formData,
  loading,
  updateField,
  setFieldImmediate,
  getField,
} = useA111FormData(wpIdRef, projectIdRef)

// ─── Signing Composable ──────────────────────────────────────────────────────

const businessCategory = computed(() => getField('A1-11-biz-category').conclusion || '')

/** Map formData sign entries into the shape useA111Signing expects (keyed by slot id) */
const signStates = computed(() => {
  const result: Record<string, { conclusion: string | null; remark: string | null; wp_ref: string | null }> = {}
  for (const slot of SIGN_SLOTS) {
    const item = getField(`A1-11-sign-${slot.id}`)
    result[slot.id] = {
      conclusion: item.conclusion,
      remark: item.remark,
      wp_ref: item.wp_ref,
    }
  }
  return result
})

const externalReadonly = computed(() => props.readonly)

const {
  requiredSlots,
  progress,
  isAllSigned,
  isReadonly,
  signAction,
  getSlotState,
} = useA111Signing(businessCategory, signStates, externalReadonly)

// ─── Readonly (Task 3.8) ─────────────────────────────────────────────────────

/** Watch for completion → emit */
watch(isAllSigned, (val) => {
  if (val) emit('completed')
})

// ─── Sign Handler ────────────────────────────────────────────────────────────

function handleSign(slotId: string) {
  const userName = currentUserName()
  signAction(slotId, userName)
  // Persist to formData immediately
  const today = formatDate(new Date())
  setFieldImmediate(`A1-11-sign-${slotId}`, {
    conclusion: 'Y',
    remark: userName,
    wp_ref: today,
  })
  emit('save')
}

// ─── Report Management Sign Handler ─────────────────────────────────────────

function handleMgmtSign(itemId: string) {
  const userName = currentUserName()
  const today = formatDate(new Date())
  setFieldImmediate(itemId, {
    conclusion: 'Y',
    remark: userName,
    wp_ref: today,
  })
  emit('save')
}

// ─── Slot visibility (B/C → qc/eqcr/it/tax show as NA) ─────────────────────

function isSlotNA(slotId: string): boolean {
  const slot = SIGN_SLOTS.find(s => s.id === slotId)
  if (!slot) return false
  const cat = businessCategory.value as 'A' | 'B' | 'C'
  if (!cat) return false
  // Not in requiredFor AND not optional → NA
  if (!slot.requiredFor.includes(cat) && !slot.optional) return true
  // optional slots for B/C: also NA
  if (slot.optional && !slot.requiredFor.includes(cat)) return true
  return false
}

// ─── Amendment (Task 3.6) ────────────────────────────────────────────────────

const showAmendment = ref(false)
const amendmentReason = ref('')
const currentAmendmentIndex = ref(1)

/** Compute existing amendment count from formData */
const amendmentHistory = computed(() => {
  const history: { index: number; reason: string; signs: Record<string, { remark: string | null; wp_ref: string | null }> }[] = []
  for (let i = 1; i <= 20; i++) {
    const reasonItem = getField(`A1-11-amend-${i}-reason`)
    if (reasonItem.remark) {
      const signs: Record<string, { remark: string | null; wp_ref: string | null }> = {}
      for (const role of ['pm', 'partner', 'qc', 'eqcr']) {
        const signItem = getField(`A1-11-amend-${i}-sign-${role}`)
        if (signItem.conclusion === 'Y') {
          signs[role] = { remark: signItem.remark, wp_ref: signItem.wp_ref }
        }
      }
      history.push({ index: i, reason: reasonItem.remark, signs })
    } else {
      break
    }
  }
  currentAmendmentIndex.value = history.length + 1
  return history
})

const canStartAmendment = computed(() => isReadonly.value && !showAmendment.value)

function startAmendment() {
  showAmendment.value = true
  amendmentReason.value = ''
}

const amendmentReasonValid = computed(() => amendmentReason.value.trim().length > 0)

function saveAmendmentReason() {
  if (!amendmentReasonValid.value) return
  const idx = currentAmendmentIndex.value
  updateField(`A1-11-amend-${idx}-reason`, 'remark', amendmentReason.value.trim())
}

function handleAmendmentSign(role: string) {
  const idx = currentAmendmentIndex.value
  const userName = currentUserName()
  const today = formatDate(new Date())
  setFieldImmediate(`A1-11-amend-${idx}-sign-${role}`, {
    conclusion: 'Y',
    remark: userName,
    wp_ref: today,
  })
  emit('save')
}

const AMENDMENT_ROLES = [
  { id: 'pm', label: '项目经理' },
  { id: 'partner', label: '合伙人' },
  { id: 'qc', label: '质控复核' },
  { id: 'eqcr', label: '技术复核' },
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatDate(date: Date): string {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

// ─── Business category options ───────────────────────────────────────────────

const BIZ_CATEGORIES = [
  { value: 'A', label: 'A类' },
  { value: 'B', label: 'B类' },
  { value: 'C', label: 'C类' },
]
</script>

<template>
  <div class="a111-signing-form" v-loading="loading">
    <!-- ═══ 只读横幅 (Task 3.8) ═══ -->
    <el-alert
      v-if="isReadonly && !showAmendment"
      type="success"
      :closable="false"
      show-icon
      class="a111-completed-banner"
    >
      <template #title>已完成签发</template>
    </el-alert>

    <!-- ═══ 基本信息区 (Task 3.2) ═══ -->
    <section class="a111-section">
      <h3 class="a111-section-title">基本信息</h3>
      <div class="a111-grid a111-grid--basic">
        <div class="a111-field">
          <label class="a111-label">委托人名称</label>
          <el-input
            :model-value="getField('A1-11-entity-name').remark || ''"
            :disabled="isReadonly"
            placeholder="委托人名称"
            @input="(val: string) => updateField('A1-11-entity-name', 'remark', val)"
          />
        </div>
        <div class="a111-field">
          <label class="a111-label">业务约定书编号</label>
          <el-input
            :model-value="getField('A1-11-engagement-no').remark || ''"
            :disabled="isReadonly"
            placeholder="约定书编号"
            @input="(val: string) => updateField('A1-11-engagement-no', 'remark', val)"
          />
        </div>
        <div class="a111-field">
          <label class="a111-label">企业性质</label>
          <el-input
            :model-value="getField('A1-11-entity-type').remark || ''"
            :disabled="isReadonly"
            placeholder="企业性质"
            @input="(val: string) => updateField('A1-11-entity-type', 'remark', val)"
          />
        </div>
        <div class="a111-field">
          <label class="a111-label">行业</label>
          <el-input
            :model-value="getField('A1-11-industry').remark || ''"
            :disabled="isReadonly"
            placeholder="行业"
            @input="(val: string) => updateField('A1-11-industry', 'remark', val)"
          />
        </div>
        <div class="a111-field">
          <label class="a111-label">鉴证业务分类</label>
          <el-select
            :model-value="getField('A1-11-biz-category').conclusion || ''"
            :disabled="isReadonly"
            placeholder="请选择"
            @change="(val: string) => updateField('A1-11-biz-category', 'conclusion', val)"
          >
            <el-option
              v-for="opt in BIZ_CATEGORIES"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </div>
        <div class="a111-field">
          <label class="a111-label">首次承接</label>
          <el-radio-group
            :model-value="getField('A1-11-first-engagement').conclusion || ''"
            :disabled="isReadonly"
            @change="(val: string) => updateField('A1-11-first-engagement', 'conclusion', val)"
          >
            <el-radio value="Y">是</el-radio>
            <el-radio value="N">否</el-radio>
          </el-radio-group>
        </div>
      </div>
    </section>

    <!-- ═══ 报告信息区 (Task 3.3) ═══ -->
    <section class="a111-section">
      <h3 class="a111-section-title">报告信息</h3>
      <div class="a111-grid a111-grid--report">
        <div class="a111-field a111-field--full">
          <label class="a111-label">报告标题</label>
          <el-input
            :model-value="getField('A1-11-report-title').remark || ''"
            :disabled="isReadonly"
            placeholder="报告标题"
            @input="(val: string) => updateField('A1-11-report-title', 'remark', val)"
          />
        </div>
        <div class="a111-field">
          <label class="a111-label">收件人全称</label>
          <el-input
            :model-value="getField('A1-11-recipient').remark || ''"
            :disabled="isReadonly"
            placeholder="收件人全称"
            @input="(val: string) => updateField('A1-11-recipient', 'remark', val)"
          />
        </div>
        <div class="a111-field">
          <label class="a111-label">附送说明</label>
          <el-input
            :model-value="getField('A1-11-attachment-note').remark || ''"
            :disabled="isReadonly"
            placeholder="附送说明"
            type="textarea"
            :rows="2"
            @input="(val: string) => updateField('A1-11-attachment-note', 'remark', val)"
          />
        </div>
      </div>
    </section>

    <!-- ═══ 签字流转区 (Task 3.4) ═══ -->
    <section class="a111-section">
      <h3 class="a111-section-title">签字流转</h3>
      <div class="a111-progress-bar">
        <span class="a111-progress-text">已签 {{ progress.signed }}/{{ progress.total }}</span>
        <el-progress
          :percentage="progress.total > 0 ? Math.round((progress.signed / progress.total) * 100) : 0"
          :stroke-width="14"
          :show-text="false"
          class="a111-progress"
        />
      </div>
      <div class="a111-sign-table">
        <div class="a111-sign-header">
          <span class="a111-sign-col a111-sign-col--role">审批角色</span>
          <span class="a111-sign-col a111-sign-col--name">签字人</span>
          <span class="a111-sign-col a111-sign-col--action">操作</span>
          <span class="a111-sign-col a111-sign-col--date">日期</span>
        </div>
        <div
          v-for="slot in SIGN_SLOTS"
          :key="slot.id"
          class="a111-sign-row"
          :class="{ 'a111-sign-row--na': isSlotNA(slot.id) }"
        >
          <span class="a111-sign-col a111-sign-col--role">{{ slot.label }}</span>
          <template v-if="isSlotNA(slot.id)">
            <span class="a111-sign-col a111-sign-col--na" style="grid-column: span 3;">
              <el-tag type="info" size="small">不适用</el-tag>
            </span>
          </template>
          <template v-else>
            <span class="a111-sign-col a111-sign-col--name">
              {{ getSlotState(slot.id).remark || '' }}
            </span>
            <span class="a111-sign-col a111-sign-col--action">
              <el-button
                v-if="getSlotState(slot.id).conclusion !== 'Y'"
                type="primary"
                size="small"
                :disabled="isReadonly"
                @click="handleSign(slot.id)"
              >
                签字
              </el-button>
              <el-tag v-else type="success" size="small">已签</el-tag>
            </span>
            <span class="a111-sign-col a111-sign-col--date">
              {{ getSlotState(slot.id).wp_ref || '' }}
            </span>
          </template>
        </div>
      </div>
    </section>

    <!-- ═══ 报告管理区 (Task 3.5) ═══ -->
    <section class="a111-section">
      <h3 class="a111-section-title">报告管理</h3>
      <div class="a111-grid a111-grid--mgmt">
        <div class="a111-field">
          <label class="a111-label">部门</label>
          <el-input
            :model-value="getField('A1-11-mgmt-dept').remark || ''"
            :disabled="isReadonly"
            placeholder="部门"
            @input="(val: string) => updateField('A1-11-mgmt-dept', 'remark', val)"
          />
        </div>
        <div class="a111-field">
          <label class="a111-label">文号</label>
          <el-input
            :model-value="getField('A1-11-mgmt-doc-no').remark || ''"
            :disabled="isReadonly"
            placeholder="文号"
            @input="(val: string) => updateField('A1-11-mgmt-doc-no', 'remark', val)"
          />
        </div>
        <div class="a111-field">
          <label class="a111-label">中文报告份数</label>
          <el-input
            :model-value="getField('A1-11-mgmt-cn-copies').remark || ''"
            :disabled="isReadonly"
            placeholder="份数"
            @input="(val: string) => updateField('A1-11-mgmt-cn-copies', 'remark', val)"
          />
        </div>
        <div class="a111-field">
          <label class="a111-label">外文报告份数</label>
          <el-input
            :model-value="getField('A1-11-mgmt-en-copies').remark || ''"
            :disabled="isReadonly"
            placeholder="份数"
            @input="(val: string) => updateField('A1-11-mgmt-en-copies', 'remark', val)"
          />
        </div>
      </div>

      <!-- 报告管理签字行 -->
      <div class="a111-sign-table a111-sign-table--mgmt">
        <div class="a111-sign-header">
          <span class="a111-sign-col a111-sign-col--role">事项</span>
          <span class="a111-sign-col a111-sign-col--name">签字人</span>
          <span class="a111-sign-col a111-sign-col--action">操作</span>
          <span class="a111-sign-col a111-sign-col--date">日期</span>
        </div>
        <div class="a111-sign-row" v-for="item in [
          { id: 'A1-11-mgmt-proofread', label: '打字校对' },
          { id: 'A1-11-mgmt-print', label: '打印' },
          { id: 'A1-11-mgmt-seal', label: '印章管理员' },
        ]" :key="item.id">
          <span class="a111-sign-col a111-sign-col--role">{{ item.label }}</span>
          <span class="a111-sign-col a111-sign-col--name">
            {{ getField(item.id).remark || '' }}
          </span>
          <span class="a111-sign-col a111-sign-col--action">
            <el-button
              v-if="getField(item.id).conclusion !== 'Y'"
              type="primary"
              size="small"
              :disabled="isReadonly"
              @click="handleMgmtSign(item.id)"
            >
              签字
            </el-button>
            <el-tag v-else type="success" size="small">已签</el-tag>
          </span>
          <span class="a111-sign-col a111-sign-col--date">
            {{ getField(item.id).wp_ref || '' }}
          </span>
        </div>
      </div>
    </section>

    <!-- ═══ 已签发报告修改区 (Task 3.6) ═══ -->
    <section class="a111-section">
      <h3 class="a111-section-title">已签发报告修改</h3>

      <!-- 修改历史 -->
      <div v-if="amendmentHistory.length > 0" class="a111-amendment-history">
        <div
          v-for="item in amendmentHistory"
          :key="item.index"
          class="a111-amendment-item"
        >
          <div class="a111-amendment-item-header">
            <el-tag size="small">第{{ item.index }}次修改</el-tag>
          </div>
          <div class="a111-amendment-reason">
            <strong>修改原因：</strong>{{ item.reason }}
          </div>
          <div class="a111-amendment-signs">
            <span v-for="role in AMENDMENT_ROLES" :key="role.id" class="a111-amendment-sign-item">
              {{ role.label }}：
              <template v-if="item.signs[role.id]">
                <el-tag type="success" size="small">
                  {{ item.signs[role.id]?.remark }} ({{ item.signs[role.id]?.wp_ref }})
                </el-tag>
              </template>
              <template v-else>
                <el-tag type="info" size="small">未签</el-tag>
              </template>
            </span>
          </div>
        </div>
      </div>

      <!-- 启动修改按钮 -->
      <el-button
        v-if="canStartAmendment"
        type="warning"
        @click="startAmendment"
      >
        启动修改
      </el-button>

      <!-- 当前修改区 -->
      <div v-if="showAmendment" class="a111-amendment-current">
        <div class="a111-field a111-field--full">
          <label class="a111-label">修改原因（必填）</label>
          <el-input
            v-model="amendmentReason"
            type="textarea"
            :rows="3"
            placeholder="请填写修改原因"
            @blur="saveAmendmentReason"
          />
        </div>

        <!-- 修改签字槽位 -->
        <div v-if="amendmentReasonValid" class="a111-sign-table a111-sign-table--amend">
          <div class="a111-sign-header">
            <span class="a111-sign-col a111-sign-col--role">角色</span>
            <span class="a111-sign-col a111-sign-col--name">签字人</span>
            <span class="a111-sign-col a111-sign-col--action">操作</span>
            <span class="a111-sign-col a111-sign-col--date">日期</span>
          </div>
          <div
            v-for="role in AMENDMENT_ROLES"
            :key="role.id"
            class="a111-sign-row"
          >
            <span class="a111-sign-col a111-sign-col--role">{{ role.label }}</span>
            <span class="a111-sign-col a111-sign-col--name">
              {{ getField(`A1-11-amend-${currentAmendmentIndex}-sign-${role.id}`).remark || '' }}
            </span>
            <span class="a111-sign-col a111-sign-col--action">
              <el-button
                v-if="getField(`A1-11-amend-${currentAmendmentIndex}-sign-${role.id}`).conclusion !== 'Y'"
                type="primary"
                size="small"
                @click="handleAmendmentSign(role.id)"
              >
                签字
              </el-button>
              <el-tag v-else type="success" size="small">已签</el-tag>
            </span>
            <span class="a111-sign-col a111-sign-col--date">
              {{ getField(`A1-11-amend-${currentAmendmentIndex}-sign-${role.id}`).wp_ref || '' }}
            </span>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══ 注释区 (Task 3.7) ═══ -->
    <section class="a111-section a111-section--note">
      <h3 class="a111-section-title">注释</h3>
      <div class="a111-note-text">
        <p>
          根据《中国注册会计师审计准则第1501号——对财务报表形成审计意见和出具审计报告》的规定，
          审计报告日期不应早于注册会计师获取充分、适当的审计证据，并在此基础上对财务报表形成审计意见的日期。
        </p>
        <p>
          审计报告日期不应早于管理层和治理层（如适用）签署或批准财务报表的日期（即管理层声明书日期）。
          审计报告日期应当与管理层书面声明的日期一致或在其之后。
        </p>
      </div>
    </section>
  </div>
</template>

<style scoped>
/* ═══ Base Layout (Task 3.9) ═══ */
.a111-signing-form {
  padding: 16px 20px;
  max-width: 1200px;
  margin: 0 auto;
  font-size: 14px;
  color: #303133;
}

.a111-completed-banner {
  margin-bottom: 16px;
}

/* ═══ Section ═══ */
.a111-section {
  margin-bottom: 24px;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 16px;
}

.a111-section--note {
  background: #fafafa;
}

.a111-section-title {
  font-size: 15px;
  font-weight: 600;
  color: #4b2d77;
  margin: 0 0 12px 0;
  padding-bottom: 8px;
  border-bottom: 1px solid #ebeef5;
}

/* ═══ CSS Grid Fields (Task 3.9) ═══ */
.a111-grid {
  display: grid;
  gap: 12px 16px;
}

.a111-grid--basic {
  grid-template-columns: repeat(3, 1fr);
}

.a111-grid--report {
  grid-template-columns: repeat(2, 1fr);
}

.a111-grid--mgmt {
  grid-template-columns: repeat(4, 1fr);
  margin-bottom: 16px;
}

.a111-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.a111-field--full {
  grid-column: 1 / -1;
}

.a111-label {
  font-size: 13px;
  font-weight: 500;
  color: #606266;
  white-space: nowrap;
}

/* ═══ Sign Table (Excel-like grid) ═══ */
.a111-sign-table {
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  overflow: hidden;
}

.a111-sign-header {
  display: grid;
  grid-template-columns: 160px 1fr 100px 120px;
  background: #f5f7fa;
  border-bottom: 1px solid #dcdfe6;
  padding: 8px 12px;
  font-weight: 600;
  font-size: 13px;
  color: #606266;
}

.a111-sign-row {
  display: grid;
  grid-template-columns: 160px 1fr 100px 120px;
  padding: 8px 12px;
  border-bottom: 1px solid #ebeef5;
  align-items: center;
}

.a111-sign-row:last-child {
  border-bottom: none;
}

.a111-sign-row--na {
  background: #fafafa;
  opacity: 0.7;
}

.a111-sign-col--role {
  font-weight: 500;
  color: #4b2d77;
}

.a111-sign-col--name {
  color: #303133;
}

.a111-sign-col--date {
  color: #909399;
  font-size: 13px;
}

/* ═══ Progress Bar ═══ */
.a111-progress-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.a111-progress-text {
  font-size: 13px;
  font-weight: 500;
  color: #606266;
  white-space: nowrap;
}

.a111-progress {
  flex: 1;
}

/* ═══ Amendment Section ═══ */
.a111-amendment-history {
  margin-bottom: 16px;
}

.a111-amendment-item {
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  padding: 12px;
  margin-bottom: 8px;
  background: #fafbfc;
}

.a111-amendment-item-header {
  margin-bottom: 8px;
}

.a111-amendment-reason {
  margin-bottom: 8px;
  font-size: 13px;
}

.a111-amendment-signs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 13px;
}

.a111-amendment-sign-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.a111-amendment-current {
  margin-top: 12px;
}

.a111-sign-table--amend {
  margin-top: 12px;
}

/* ═══ Note Section ═══ */
.a111-note-text {
  font-size: 13px;
  color: #606266;
  line-height: 1.8;
}

.a111-note-text p {
  margin: 0 0 8px 0;
  text-indent: 2em;
}

.a111-note-text p:last-child {
  margin-bottom: 0;
}

/* ═══ Responsive (Task 3.9) ═══ */
@media (max-width: 768px) {
  .a111-signing-form {
    padding: 12px;
  }

  .a111-grid--basic,
  .a111-grid--report,
  .a111-grid--mgmt {
    grid-template-columns: 1fr;
  }

  .a111-sign-header,
  .a111-sign-row {
    grid-template-columns: 1fr;
    gap: 4px;
  }

  .a111-sign-header {
    display: none;
  }

  .a111-sign-row {
    padding: 12px;
    border: 1px solid #ebeef5;
    border-radius: 4px;
    margin-bottom: 8px;
  }

  .a111-sign-col--role::before {
    content: '';
  }

  .a111-sign-col--name::before {
    content: '签字人：';
    color: #909399;
    font-size: 12px;
  }

  .a111-sign-col--date::before {
    content: '日期：';
    color: #909399;
    font-size: 12px;
  }

  .a111-amendment-signs {
    flex-direction: column;
  }
}

@media (min-width: 1200px) {
  .a111-signing-form {
    max-width: 1100px;
  }

  .a111-grid--basic {
    grid-template-columns: repeat(3, 1fr);
  }

  .a111-sign-header,
  .a111-sign-row {
    grid-template-columns: 180px 1fr 110px 140px;
  }
}

/* ═══ Print Styles (Task 4.1) ═══ */
@media print {
  .a111-signing-form {
    padding: 0;
    max-width: 100%;
    font-size: 12px;
  }

  /* A4 portrait */
  @page {
    size: A4 portrait;
    margin: 15mm 12mm;
  }

  /* Hide interactive elements */
  .a111-signing-form :deep(.el-button),
  .a111-signing-form :deep(.el-input__wrapper),
  .a111-signing-form :deep(.el-select .el-input__wrapper),
  .a111-signing-form :deep(.el-textarea__inner),
  .a111-signing-form :deep(.el-radio__input),
  .a111-signing-form .a111-progress-bar,
  .a111-signing-form .a111-completed-banner {
    display: none !important;
  }

  /* Show text values instead of inputs */
  .a111-signing-form :deep(.el-input) {
    border: none !important;
    box-shadow: none !important;
  }

  .a111-signing-form :deep(.el-input__inner) {
    border: none !important;
    padding: 0 !important;
    box-shadow: none !important;
    background: transparent !important;
  }

  .a111-signing-form :deep(.el-textarea__inner) {
    border: none !important;
    padding: 0 !important;
    box-shadow: none !important;
    background: transparent !important;
  }

  /* Keep table borders */
  .a111-section {
    border: 1px solid #333;
    page-break-inside: avoid;
    margin-bottom: 12px;
    padding: 8px;
  }

  .a111-sign-table {
    border: 1px solid #333;
  }

  .a111-sign-header {
    border-bottom: 1px solid #333;
    background: #eee !important;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }

  .a111-sign-row {
    border-bottom: 1px solid #ccc;
  }

  .a111-section-title {
    font-size: 13px;
    border-bottom: 1px solid #333;
  }

  /* Show signing results as text */
  .a111-sign-col--action .el-tag {
    border: none;
    background: transparent !important;
    color: #333 !important;
    padding: 0;
  }

  /* Note section */
  .a111-note-text {
    font-size: 11px;
  }
}
</style>
