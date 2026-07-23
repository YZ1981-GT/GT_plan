<script setup lang="ts">
/**
 * B50AccountRiskDialog — B50-3 认定层次风险「引导式」科目录入弹窗
 *
 * 一个科目一个弹窗，4 分组卡片（审计范围 / 认定层次风险 / 特别风险 / 应对方案）+
 * 右侧实时联动面板。保存一次性批量应用（emit apply → 父调 applyAccountPatch 单次 saveImmediate）。
 *
 * Spec: .kiro/specs/b50-workpaper-rework/ Task 7
 */
import { ref, computed, watch } from 'vue'
import {
  ASSERTIONS, RISK_COLOR_MAP, CATEGORY_OPTIONS, CYCLE_OPTIONS,
  CONTROL_RELIANCE_OPTIONS, APPROACH_OPTIONS, computeSuggestedApproach,
  type Assertion, type RiskLevel, type ScopeCategory, type ControlReliance,
  type AuditApproach, type AccountRow, type AccountPatch,
} from './composables/useB50RiskMatrix'

const props = defineProps<{
  visible: boolean
  row: AccountRow | null
  readonly?: boolean
}>()
const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'apply', account: string, patch: AccountPatch): void
}>()

const ASSERTION_LABELS: Record<Assertion, string> = {
  existence: '存在', completeness: '完整性', accuracy: '准确性',
  cutoff: '截止', classification: '分类', presentation: '列报',
}
const RISK_OPTS: { value: RiskLevel; label: string }[] = [
  { value: 'H', label: '高' }, { value: 'M', label: '中' }, { value: 'L', label: '低' },
]

// 本地工作副本
interface CellDraft { ir: RiskLevel | null; cr: RiskLevel | null; rmm: RiskLevel | null; special: boolean }
const form = ref<{
  balance: number | null
  category: ScopeCategory
  estimate: string
  cycle: string | null
  reliance: ControlReliance | null
  subonly: string | null
  approach: AuditApproach | null
  cells: Record<Assertion, CellDraft>
}>(blankForm())

function blankForm() {
  const cells = {} as Record<Assertion, CellDraft>
  for (const a of ASSERTIONS) cells[a] = { ir: null, cr: null, rmm: null, special: false }
  return { balance: null, category: '' as ScopeCategory, estimate: '', cycle: null, reliance: null, subonly: null, approach: null, cells }
}

watch(() => props.visible, (v) => {
  if (v && props.row) {
    const r = props.row
    const cells = {} as Record<Assertion, CellDraft>
    for (const a of ASSERTIONS) {
      const c = r.cells[a]
      cells[a] = { ir: c.inherentRisk, cr: c.controlRisk, rmm: c.combinedRisk, special: c.isSpecialRisk }
    }
    form.value = {
      balance: r.balance, category: r.category, estimate: r.isEstimate,
      cycle: r.cycle, reliance: r.plannedReliance, subonly: r.substantiveOnlySufficient,
      approach: r.approach, cells,
    }
  }
})

const accountName = computed(() => props.row?.name || '')
const isMgmtOverride = computed(() => accountName.value === '管理层凌驾控制')

// 实时联动面板
const hasHighCombined = computed(() => ASSERTIONS.some(a => form.value.cells[a].rmm === 'H'))
const hasSpecial = computed(() => ASSERTIONS.some(a => form.value.cells[a].special))
const suggested = computed(() => computeSuggestedApproach(form.value.category, hasHighCombined.value))
const suggestedLabel = computed(() => suggested.value === 'combined' ? '综合性方案' : suggested.value === 'substantive' ? '实质性方案' : '')

const linkageHints = computed(() => {
  const hints: { type: 'warning' | 'info' | 'success'; text: string }[] = []
  if (hasSpecial.value && (accountName.value === '收入确认' || isMgmtOverride.value)) {
    hints.push({ type: 'warning', text: 'CAS 舞弊推定：本科目特别风险须实施针对性细节测试（不得仅含分析程序）。' })
  } else if (hasSpecial.value) {
    hints.push({ type: 'warning', text: '存在特别风险：须实施针对性实质性程序，并在 Tab4 记录应对。' })
  }
  if (form.value.approach === 'combined') {
    hints.push({ type: 'info', text: '综合性方案：须在 C 类实施控制测试（→C）。' })
  }
  if (form.value.cycle && form.value.cycle !== 'pervasive') {
    const label = CYCLE_OPTIONS.find(o => o.value === form.value.cycle)?.label || form.value.cycle
    hints.push({ type: 'success', text: `将路由到「${label}」程序表（→${form.value.cycle}）。` })
  }
  if (suggestedLabel.value && form.value.approach !== suggested.value) {
    hints.push({ type: 'info', text: `按类别与最高综合风险，建议应对方案：${suggestedLabel.value}。` })
  }
  if (form.value.category === 'amount_only' && form.value.subonly !== 'Y') {
    hints.push({ type: 'info', text: '仅金额重大科目通常"仅实质性程序即足够"。' })
  }
  return hints
})

function close() { emit('update:visible', false) }

function save() {
  if (props.readonly || !props.row) { close(); return }
  const cells: AccountPatch['cells'] = {}
  for (const a of ASSERTIONS) {
    const c = form.value.cells[a]
    cells![a] = { ir: c.ir, cr: c.cr, rmm: c.rmm, special: c.special }
  }
  emit('apply', accountName.value, {
    balance: form.value.balance,
    category: form.value.category,
    estimate: form.value.estimate,
    cycle: form.value.cycle,
    reliance: form.value.reliance,
    subonly: form.value.subonly,
    approach: form.value.approach,
    cells,
  })
  close()
}
</script>

<template>
  <el-dialog
    :model-value="visible"
    :title="`引导录入 — ${accountName}`"
    width="880px"
    append-to-body
    @update:model-value="(v: boolean) => emit('update:visible', v)"
  >
    <div class="b50-guide-body">
      <div class="b50-guide-main">
        <!-- ① 审计范围 -->
        <el-card shadow="never" class="guide-card">
          <template #header><span class="gc-title">① 审计范围（源 B50-3）</span></template>
          <div class="gc-grid">
            <div class="gc-field">
              <label>余额/金额</label>
              <el-input-number v-model="form.balance" :disabled="readonly" :controls="false" placeholder="—" style="width: 100%" />
            </div>
            <div class="gc-field">
              <label>类别</label>
              <el-select v-model="form.category" :disabled="readonly" placeholder="选择类别" style="width: 100%">
                <el-option v-for="o in CATEGORY_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
            </div>
            <div class="gc-field">
              <label>是否涉及会计估计</label>
              <el-select v-model="form.estimate" :disabled="readonly" placeholder="是/否" style="width: 100%">
                <el-option label="是" value="Y" /><el-option label="否" value="N" />
              </el-select>
            </div>
          </div>
        </el-card>

        <!-- ② 认定层次风险 -->
        <el-card shadow="never" class="guide-card">
          <template #header><span class="gc-title">② 认定层次风险（IR / CR / 综合 RMM）</span></template>
          <el-table :data="ASSERTIONS" size="small" border>
            <el-table-column label="认定" width="120">
              <template #default="{ row: a }">{{ ASSERTION_LABELS[a as Assertion] }}</template>
            </el-table-column>
            <el-table-column label="固有风险 IR">
              <template #default="{ row: a }">
                <el-select v-model="form.cells[a as Assertion].ir" :disabled="readonly" clearable placeholder="—" size="small" style="width: 100%">
                  <el-option v-for="o in RISK_OPTS" :key="o.value" :label="o.label" :value="o.value" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="控制风险 CR">
              <template #default="{ row: a }">
                <el-select v-model="form.cells[a as Assertion].cr" :disabled="readonly" clearable placeholder="—" size="small" style="width: 100%">
                  <el-option v-for="o in RISK_OPTS" :key="o.value" :label="o.label" :value="o.value" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="综合风险 RMM">
              <template #default="{ row: a }">
                <el-select v-model="form.cells[a as Assertion].rmm" :disabled="readonly" clearable placeholder="—" size="small" style="width: 100%">
                  <el-option v-for="o in RISK_OPTS" :key="o.value" :label="o.label" :value="o.value">
                    <span :style="{ color: RISK_COLOR_MAP[o.value].text }">● {{ o.label }}</span>
                  </el-option>
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="特别风险" width="90" align="center">
              <template #default="{ row: a }">
                <el-checkbox v-model="form.cells[a as Assertion].special" :disabled="readonly || isMgmtOverride" />
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <!-- ④ 应对方案 -->
        <el-card shadow="never" class="guide-card">
          <template #header><span class="gc-title">③ 风险应对</span></template>
          <div class="gc-grid">
            <div class="gc-field">
              <label>相关业务循环</label>
              <el-select v-model="form.cycle" :disabled="readonly || isMgmtOverride" placeholder="选择循环" style="width: 100%">
                <el-option v-for="o in CYCLE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
            </div>
            <div class="gc-field">
              <label>对控制的拟信赖程度</label>
              <el-select v-model="form.reliance" :disabled="readonly" placeholder="选择" style="width: 100%">
                <el-option v-for="o in CONTROL_RELIANCE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
            </div>
            <div class="gc-field">
              <label>仅实质性程序是否足够</label>
              <el-select v-model="form.subonly" :disabled="readonly" placeholder="是/否" style="width: 100%">
                <el-option label="是" value="Y" /><el-option label="否" value="N" />
              </el-select>
            </div>
            <div class="gc-field">
              <label>应对方案</label>
              <el-select v-model="form.approach" :disabled="readonly" placeholder="选择方案" style="width: 100%">
                <el-option v-for="o in APPROACH_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
            </div>
          </div>
        </el-card>
      </div>

      <!-- 右侧实时联动面板 -->
      <div class="b50-guide-side">
        <div class="side-title">实时联动</div>
        <el-alert v-for="(h, i) in linkageHints" :key="i" :type="h.type" :closable="false" show-icon class="side-hint">
          {{ h.text }}
        </el-alert>
        <div v-if="linkageHints.length === 0" class="side-empty">填写后显示风险应对联动提示</div>
      </div>
    </div>

    <template #footer>
      <el-button @click="close">取消</el-button>
      <el-button type="primary" :disabled="readonly" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.b50-guide-body { display: flex; gap: 16px; font-size: 13px; }
.b50-guide-main { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: 12px; }
.b50-guide-side { flex: 0 0 240px; border-left: 1px solid var(--el-border-color-light); padding-left: 12px; }
.guide-card { --el-card-padding: 10px 12px; }
.gc-title { font-weight: 500; color: var(--el-color-primary); font-size: 13px; }
.gc-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px 14px; }
.gc-field label { display: block; font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px; }
.side-title { font-weight: 500; margin-bottom: 8px; font-size: 13px; }
.side-hint { margin-bottom: 8px; }
.side-empty { color: var(--el-text-color-placeholder); font-size: 12px; }
:deep(.el-table) { font-size: 13px; }
</style>
