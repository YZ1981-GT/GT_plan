<script setup lang="ts">
/**
 * D4IpoFindingWriteback — D4-29/31/32 IPO/舞弊组「风险发现 → 人工认定 → A13/D4-1」共享回写件
 *
 * 边界（spec d4-ipo-fraud-writeback-formula-io Requirement 3）：
 *   - 发现（findings）先落库留痕（item_id: {wpCode}-findings），不自动造错报。
 *   - 描述型 amount=0 / reason / 「否」非空都不能单独判异常自动进 A13。
 *   - 只有审计人员在弹窗内人工确认「方向 + 金额(>0) + 描述 + 证据索引」后，
 *     该发现才可勾选推送；未确认项禁用推送。
 *   - 推送经共享 useD4InspectionWriteback.pushToA13（eventBus 白名单 a13:push-misstatement
 *     → useA13MisstatementBridge durable ack + draftHash 去重 + D4-1 说明独立落库）。
 *   - 只读态禁止一切写入。
 */
import { ref, computed, watch, toRef } from 'vue'
import { ElMessage } from 'element-plus'
import { useD4InspectionWriteback, type D4MisstatementItem } from '../../composables/useD4InspectionWriteback'

/** 候选发现（由各底稿从其数据派生；纯描述、无金额方向） */
export interface D4IpoFinding {
  /** 稳定 key（source identity 的一部分，用于去重/留痕） */
  key: string
  /** 发现摘要（如「关联方客户：XX」「访谈红旗：存在其他资金往来」「异常资金流水：XX」） */
  label: string
  /** 建议索引（溯源到本底稿行/期间），可空 */
  indexRef?: string
}

/** 人工认定态（审计人员填写，认定完成才可推送） */
interface Confirmation {
  selected: boolean
  amount: number | ''
  description: string
  evidence: string   // 证据索引/说明（非空才算已取得证据）
}

const props = defineProps<{
  wpCode: string
  accountCode?: string
  accountName?: string
  allResponses: Map<string, any>
  isReadonly: boolean
  /** 候选发现列表（由父组件派生传入） */
  findings: D4IpoFinding[]
}>()

const emit = defineEmits<{ (e: 'pushed', count: number): void }>()

const { pushToA13 } = useD4InspectionWriteback({
  wpCode: props.wpCode,
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const dialogVisible = ref(false)
// 人工认定态：key → Confirmation
const confirmations = ref<Record<string, Confirmation>>({})

const findingsItemId = computed(() => `${props.wpCode}-findings`)

function loadFindings() {
  // 恢复既有留痕的认定态（若有）
  try {
    const raw = props.allResponses.get(findingsItemId.value)?.remark
    if (raw) {
      const parsed = JSON.parse(raw)
      if (parsed && typeof parsed === 'object' && parsed.confirmations) {
        confirmations.value = parsed.confirmations
      }
    }
  } catch { /* ignore */ }
}
watch(() => props.allResponses.get(`${props.wpCode}-findings`)?.remark, loadFindings, { immediate: true })

function ensureConfirmation(key: string): Confirmation {
  if (!confirmations.value[key]) {
    confirmations.value[key] = { selected: false, amount: '', description: '', evidence: '' }
  }
  return confirmations.value[key]
}

/** 某发现是否已完成人工认定（金额>0 + 描述非空 + 证据非空） */
function isConfirmed(key: string): boolean {
  const c = confirmations.value[key]
  if (!c) return false
  const amt = typeof c.amount === 'number' ? c.amount : Number(c.amount)
  return isFinite(amt) && amt > 0 && !!c.description.trim() && !!c.evidence.trim()
}

/** 可推送项 = 已勾选 且 已完成认定 */
const pushableCount = computed(() =>
  props.findings.filter(f => confirmations.value[f.key]?.selected && isConfirmed(f.key)).length,
)

/** 发现留痕落库（先保存发现，不推 A13）——独立于 A13，随时可存 */
function persistFindings() {
  if (props.isReadonly) return
  const remark = JSON.stringify({
    findings: props.findings.map(f => ({ key: f.key, label: f.label, indexRef: f.indexRef || '' })),
    confirmations: confirmations.value,
    savedAt: Date.now(),
  })
  props.allResponses.set(findingsItemId.value, { item_id: findingsItemId.value, conclusion: null, remark })
  try {
    window.dispatchEvent(new CustomEvent('d4:save-items', {
      detail: { items: [props.allResponses.get(findingsItemId.value)].filter(Boolean) },
    }))
  } catch { /* SSR */ }
}

function openDialog() {
  if (!props.findings.length) {
    ElMessage.info('暂无风险发现，无需认定')
    return
  }
  for (const f of props.findings) ensureConfirmation(f.key)
  dialogVisible.value = true
}

function handleSaveFindings() {
  persistFindings()
  ElMessage.success('风险发现已留痕保存')
}

/** 人工确认后推送：仅推送已勾选且已认定的项 */
function handlePush() {
  if (props.isReadonly) return
  // 先留痕再推（先保存发现，不自动造错报）
  persistFindings()
  const items: D4MisstatementItem[] = props.findings
    .filter(f => confirmations.value[f.key]?.selected && isConfirmed(f.key))
    .map(f => {
      const c = confirmations.value[f.key]
      return {
        amount: typeof c.amount === 'number' ? c.amount : Number(c.amount),
        description: `${c.description.trim()}（证据：${c.evidence.trim()}）`,
        indexRef: f.indexRef || props.wpCode,
      }
    })
  if (!items.length) {
    ElMessage.warning('无已完成人工认定的发现（需勾选并填写方向/金额/证据）')
    return
  }
  const ok = pushToA13(items, props.accountCode || '6001', props.accountName || '营业收入')
  if (ok) {
    dialogVisible.value = false
    emit('pushed', items.length)
  }
}

// 暴露内部方法/态供守卫测试驱动人工门（Requirement 3 行为级验证）
defineExpose({ openDialog, handlePush, handleSaveFindings, confirmations, isConfirmed, pushableCount })
</script>

<template>
<span class="d4-ipo-finding-writeback">
  <el-badge :value="findings.length" :hidden="!findings.length" type="warning">
    <el-button size="small" type="warning" plain :disabled="isReadonly" @click="openDialog">
      风险发现认定 → A13
    </el-button>
  </el-badge>

  <el-dialog v-model="dialogVisible" title="风险发现人工认定（确认方向/金额/证据后方可推送 A13）" width="820px" top="6vh" destroy-on-close>
    <div class="fw-intro">
      <el-alert type="info" :closable="false" show-icon>
        以下为本底稿识别出的风险发现。发现本身不构成错报；须由审计人员逐项人工确认<strong>错报方向、金额（&gt;0）与证据索引</strong>后，
        方可勾选并推送至 A13 未更正错报汇总（同步至 D4-1 审计说明）。描述型/金额为 0 的发现不会进入 A13。
      </el-alert>
    </div>
    <el-table :data="findings" border size="small" class="fw-table" max-height="440">
      <el-table-column label="推送" width="56" align="center">
        <template #default="{ row }">
          <el-checkbox
            v-model="ensureConfirmation(row.key).selected"
            :disabled="isReadonly || !isConfirmed(row.key)"
          />
        </template>
      </el-table-column>
      <el-table-column label="风险发现" min-width="180">
        <template #default="{ row }">
          <div class="fw-label">{{ row.label }}</div>
          <div v-if="row.indexRef" class="fw-idx">索引：{{ row.indexRef }}</div>
        </template>
      </el-table-column>
      <el-table-column label="错报金额" width="130" align="right">
        <template #default="{ row }">
          <el-input
            v-model.number="ensureConfirmation(row.key).amount"
            size="small" type="number" placeholder="金额>0"
            :disabled="isReadonly" @input="ensureConfirmation(row.key).selected = false"
          />
        </template>
      </el-table-column>
      <el-table-column label="方向/描述" min-width="170">
        <template #default="{ row }">
          <el-input
            v-model="ensureConfirmation(row.key).description"
            size="small" placeholder="错报方向及说明"
            :disabled="isReadonly" @input="ensureConfirmation(row.key).selected = false"
          />
        </template>
      </el-table-column>
      <el-table-column label="证据索引" min-width="140">
        <template #default="{ row }">
          <el-input
            v-model="ensureConfirmation(row.key).evidence"
            size="small" placeholder="证据来源/索引"
            :disabled="isReadonly" @input="ensureConfirmation(row.key).selected = false"
          />
        </template>
      </el-table-column>
      <el-table-column label="认定" width="64" align="center">
        <template #default="{ row }">
          <el-tag :type="isConfirmed(row.key) ? 'success' : 'info'" size="small" effect="plain">
            {{ isConfirmed(row.key) ? '已认定' : '待认定' }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>
    <template #footer>
      <div class="fw-footer">
        <span class="fw-count">可推送：{{ pushableCount }} 项</span>
        <span class="fw-actions">
          <el-button size="small" :disabled="isReadonly" @click="handleSaveFindings">仅保存发现留痕</el-button>
          <el-button size="small" @click="dialogVisible = false">取消</el-button>
          <el-button size="small" type="warning" :disabled="isReadonly || pushableCount === 0" @click="handlePush">
            推送 {{ pushableCount }} 项至 A13
          </el-button>
        </span>
      </div>
    </template>
  </el-dialog>
</span>
</template>

<style scoped>
.d4-ipo-finding-writeback { display: inline-flex; }
.fw-intro { margin-bottom: 12px; }
.fw-intro :deep(.el-alert__content) { line-height: 1.7; font-size: 12px; }
.fw-table { font-size: 12px; }
.fw-table :deep(.el-table__cell) { padding: 4px 6px; }
.fw-label { font-size: 12px; color: #303133; }
.fw-idx { font-size: 11px; color: #909399; margin-top: 2px; }
.fw-footer { display: flex; align-items: center; justify-content: space-between; }
.fw-count { font-size: 12px; color: #e6a23c; font-weight: 600; }
.fw-actions { display: flex; gap: 8px; }
</style>
