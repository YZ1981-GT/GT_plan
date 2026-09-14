<template>
  <el-dialog
    :model-value="visible"
    :title="`政府补助核对 — ${form.projectName || '新增项目'}`"
    width="880px"
    :close-on-click-modal="false"
    destroy-on-close
    @update:model-value="(v: boolean) => emit('update:visible', v)"
  >
    <div class="k10-grant-dialog">
      <!-- 左：分组卡片录入 -->
      <div class="dialog-form">
        <!-- ① 基本信息 -->
        <el-card shadow="never" class="group-card">
          <template #header><span class="group-title">① 基本信息</span></template>
          <el-form label-width="96px" size="small">
            <el-form-item label="补助项目">
              <el-input v-model="form.projectName" :disabled="readonly" placeholder="如：研发费用补贴" />
            </el-form-item>
            <el-form-item label="补助期间">
              <el-input v-model="form.period" :disabled="readonly" placeholder="如 2025" />
            </el-form-item>
          </el-form>
          <div class="group-hint">与日常活动相关的政府补助计入其他收益(6117)；与日常活动无关计入营业外收入(6301/K12)。</div>
        </el-card>

        <!-- ② 直接计入（收到当期即确认） -->
        <el-card shadow="never" class="group-card">
          <template #header><span class="group-title">② 直接计入（当期确认）</span></template>
          <el-form label-width="130px" size="small">
            <el-form-item label="直接冲减成本">
              <el-input-number v-model="form.directReduceCost" :controls="false" :disabled="readonly" style="width:100%" />
            </el-form-item>
            <el-form-item label="直接计入其他收益">
              <el-input-number v-model="form.directToOtherIncome" :controls="false" :disabled="readonly" style="width:100%" />
            </el-form-item>
            <el-form-item label="直接计入营业外">
              <el-input-number v-model="form.directToNonOpIncome" :controls="false" :disabled="readonly" style="width:100%" />
            </el-form-item>
          </el-form>
        </el-card>

        <!-- ③ 递延收益变动 -->
        <el-card shadow="never" class="group-card">
          <template #header><span class="group-title">③ 递延收益变动（CAS16）</span></template>
          <el-form label-width="130px" size="small">
            <el-form-item label="期初递延余额">
              <el-input-number v-model="form.openingDeferred" :controls="false" :disabled="readonly" style="width:100%" />
            </el-form-item>
            <el-form-item label="新增递延">
              <el-input-number v-model="form.newDeferred" :controls="false" :disabled="readonly" style="width:100%" />
            </el-form-item>
            <el-form-item label="摊销冲减成本">
              <el-input-number v-model="form.amortReduceCost" :controls="false" :disabled="readonly" style="width:100%" />
            </el-form-item>
            <el-form-item label="摊销转其他收益">
              <el-input-number v-model="form.amortToOtherIncome" :controls="false" :disabled="readonly" style="width:100%" />
            </el-form-item>
            <el-form-item label="摊销转营业外">
              <el-input-number v-model="form.amortToNonOpIncome" :controls="false" :disabled="readonly" style="width:100%" />
            </el-form-item>
            <el-form-item label="返还">
              <el-input-number v-model="form.refund" :controls="false" :disabled="readonly" style="width:100%" />
            </el-form-item>
            <el-form-item label="其他转出">
              <el-input-number v-model="form.otherTransferOut" :controls="false" :disabled="readonly" style="width:100%" />
            </el-form-item>
          </el-form>
        </el-card>
      </div>

      <!-- 右：实时结果与提示 -->
      <div class="dialog-panel">
        <div class="panel-title">实时核对</div>
        <div class="panel-item">
          <span class="panel-label">期末递延余额</span>
          <span class="panel-value">{{ fmt(closingDeferred) }}</span>
        </div>
        <div class="panel-formula">= 期初 + 新增 − 摊销(成本+其他收益+营业外) − 返还 − 其他转出</div>
        <el-divider style="margin:10px 0" />
        <div class="panel-item highlight">
          <span class="panel-label">本行计入其他收益合计</span>
          <span class="panel-value strong">{{ fmt(recognizedOtherIncome) }}</span>
        </div>
        <div class="panel-formula">= 直接计入其他收益 + 摊销转其他收益</div>
        <el-alert
          v-if="closingDeferred < 0"
          type="warning"
          :closable="false"
          show-icon
          style="margin-top:10px"
          title="期末递延余额为负，请检查摊销/返还金额是否超过可摊销余额"
        />
        <el-alert
          v-if="form.directToNonOpIncome > 0 || form.amortToNonOpIncome > 0"
          type="info"
          :closable="false"
          show-icon
          style="margin-top:10px"
          title="存在计入营业外收入的金额，应属与日常活动无关的补助，请确认归类至 6301(K12)"
        />
        <div class="panel-tip">递延分摊转其他收益应与 K7 递延收益(2401)本期分摊一致。</div>
      </div>
    </div>

    <template #footer>
      <el-button size="small" @click="emit('update:visible', false)">取消</el-button>
      <el-button size="small" type="primary" :disabled="readonly" @click="handleSave">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * K10GrantReconcileDialog — K10-4 政府补助核对引导式录入弹窗（分组卡片 + 实时核对面板）
 *
 * 宽表(13列)逐笔录入改引导式弹窗（J3PlanDialog/D2DerecognitionWizard 范式）：
 * - 左侧 3 分组卡片（基本信息/直接计入/递延变动）点点点录入
 * - 右侧实时面板（期末递延余额公式 + 本行计入其他收益 + 负余额/营业外/K7 提示）
 * - 保存 emit patch → 父组件按字段写回 reconcile
 */
import { reactive, computed, watch } from 'vue'

interface GrantForm {
  rowKey: string
  projectName: string
  period: string
  directReduceCost: number
  directToOtherIncome: number
  directToNonOpIncome: number
  newDeferred: number
  openingDeferred: number
  amortReduceCost: number
  amortToOtherIncome: number
  amortToNonOpIncome: number
  refund: number
  otherTransferOut: number
}

const props = defineProps<{
  visible: boolean
  row: Record<string, any> | null
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'save', patch: GrantForm): void
}>()

const readonly = computed(() => !!props.readonly)

function blank(): GrantForm {
  return {
    rowKey: '', projectName: '', period: '',
    directReduceCost: 0, directToOtherIncome: 0, directToNonOpIncome: 0,
    newDeferred: 0, openingDeferred: 0,
    amortReduceCost: 0, amortToOtherIncome: 0, amortToNonOpIncome: 0,
    refund: 0, otherTransferOut: 0,
  }
}

const form = reactive<GrantForm>(blank())

function hydrate(): void {
  const r = props.row
  const b = blank()
  if (r) {
    b.rowKey = r.rowKey ?? ''
    b.projectName = r.projectName ?? ''
    b.period = r.period ?? ''
    for (const k of ['directReduceCost','directToOtherIncome','directToNonOpIncome','newDeferred','openingDeferred','amortReduceCost','amortToOtherIncome','amortToNonOpIncome','refund','otherTransferOut'] as const) {
      ;(b as any)[k] = Number(r[k] ?? 0)
    }
  }
  Object.assign(form, b)
}

watch(() => props.visible, (v) => { if (v) hydrate() }, { immediate: true })

const closingDeferred = computed(() =>
  form.openingDeferred + form.newDeferred - form.amortReduceCost - form.amortToOtherIncome - form.amortToNonOpIncome - form.refund - form.otherTransferOut,
)
const recognizedOtherIncome = computed(() => form.directToOtherIncome + form.amortToOtherIncome)

function fmt(v: number): string {
  if (!v) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function handleSave(): void {
  emit('save', { ...form })
  emit('update:visible', false)
}
</script>

<style scoped>
.k10-grant-dialog { display: flex; gap: 16px; }
.dialog-form { flex: 1 1 auto; display: flex; flex-direction: column; gap: 12px; max-height: 60vh; overflow-y: auto; }
.dialog-panel {
  flex: 0 0 260px; align-self: flex-start;
  background: #f5f7fa; border-radius: 8px; padding: 14px; font-size: 13px;
  position: sticky; top: 0;
}
.group-card :deep(.el-card__header) { padding: 8px 12px; }
.group-card :deep(.el-card__body) { padding: 12px; }
.group-title { font-weight: 600; font-size: 13px; }
.group-hint { margin-top: 6px; font-size: 12px; color: #8b6914; background: #fffbe6; border-left: 3px solid #e6a23c; padding: 6px 10px; border-radius: 0 4px 4px 0; }

.panel-title { font-weight: 600; margin-bottom: 10px; color: #303133; }
.panel-item { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.panel-item.highlight { background: #fff; border-radius: 6px; padding: 6px 8px; }
.panel-label { color: #606266; }
.panel-value { font-weight: 600; color: #303133; }
.panel-value.strong { color: #e6a23c; font-size: 15px; }
.panel-formula { font-size: 11px; color: #909399; margin-bottom: 6px; }
.panel-tip { margin-top: 12px; font-size: 12px; color: #909399; line-height: 1.5; }
</style>
