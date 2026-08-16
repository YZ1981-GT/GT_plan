<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * G5ReversalWriteoffDialog — G5-11 转回/核销逐笔录入与合理性分析弹窗
 */
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  emptyReversalRow,
  emptyWriteoffRow,
  inferApprovalComplete,
  summarizeChecks,
  type ReasonablenessItem,
  type ReversalRow,
  type WriteoffRow,
} from '../../composables/useG5ReversalWriteoff'
import { isReversalValid } from '@/composables/useG5FormulaEngine'

const props = defineProps<{
  modelValue: boolean
  mode: 'reversal' | 'writeoff'
  row: ReversalRow | WriteoffRow | null
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'save', payload: { mode: 'reversal' | 'writeoff'; row: ReversalRow | WriteoffRow }): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const activeTab = ref('basic')
const RESULT_OPTIONS = ['是', '否', '不适用'] as const

const rev = reactive(emptyReversalRow())
const wo = reactive(emptyWriteoffRow())

const title = computed(() => {
  const name = props.mode === 'reversal' ? (rev.debtor || '未命名') : (wo.debtor || '未命名')
  return props.mode === 'reversal'
    ? `转回/收回检查 · ${name}`
    : `核销检查 · ${name}`
})

const checks = computed(() => (props.mode === 'reversal' ? rev.checks : wo.checks))
const amountWarning = computed(() =>
  props.mode === 'reversal' && !isReversalValid(rev.reversalAmount, rev.accumulatedProvision),
)

function hydrate(): void {
  activeTab.value = 'basic'
  if (props.mode === 'reversal') {
    const src = (props.row as ReversalRow | null) || emptyReversalRow()
    const next = emptyReversalRow({ ...src })
    Object.assign(rev, next)
    rev.checks = next.checks
  } else {
    const src = (props.row as WriteoffRow | null) || emptyWriteoffRow()
    const next = emptyWriteoffRow({ ...src })
    Object.assign(wo, next)
    wo.checks = next.checks
  }
}

watch(() => [props.modelValue, props.mode, props.row?.id], ([open]) => {
  if (open) hydrate()
})

function onCheckChange(): void {
  if (props.mode === 'writeoff') {
    wo.approvalComplete = inferApprovalComplete(wo)
  }
}

function fillReasonablenessFromChecks(): void {
  if (props.mode === 'reversal') {
    const text = summarizeChecks(rev.checks)
    if (text) rev.reasonableness = text
  } else {
    const text = summarizeChecks(wo.checks)
    if (text) wo.reasonableness = text
  }
}

function onSave(): void {
  if (props.mode === 'reversal') {
    if (!rev.debtor?.trim()) {
      ElMessage.warning('请填写单位名称')
      activeTab.value = 'basic'
      return
    }
    rev.isValid = isReversalValid(rev.reversalAmount, rev.accumulatedProvision)
    if (!rev.reasonableness) rev.reasonableness = summarizeChecks(rev.checks)
    emit('save', {
      mode: 'reversal',
      row: {
        ...rev,
        checks: rev.checks.map(c => ({ ...c })),
      },
    })
  } else {
    if (!wo.debtor?.trim()) {
      ElMessage.warning('请填写单位名称')
      activeTab.value = 'basic'
      return
    }
    wo.approvalComplete = inferApprovalComplete(wo)
    if (!wo.approvalStatus && wo.procedures) wo.approvalStatus = wo.procedures
    if (!wo.reasonableness) wo.reasonableness = summarizeChecks(wo.checks)
    emit('save', {
      mode: 'writeoff',
      row: {
        ...wo,
        checks: wo.checks.map(c => ({ ...c })),
      },
    })
  }
  visible.value = false
}

function resultTag(r: ReasonablenessItem['result']): string {
  if (r === '是') return 'success'
  if (r === '否') return 'danger'
  if (r === '不适用') return 'info'
  return 'info'
}
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="title"
    width="860px"
    top="5vh"
    append-to-body
    destroy-on-close
  >
    <el-alert
      v-if="amountWarning"
      type="error"
      :closable="false"
      show-icon
      class="mb"
      title="转回/收回金额超过累计已计提减值准备 — 不符合 CAS 22，请复核金额或调整会计处理。"
    />

    <el-tabs v-model="activeTab">
      <el-tab-pane label="① 业务信息" name="basic">
        <!-- 转回 -->
        <el-form v-if="mode === 'reversal'" label-width="140px" size="small">
          <el-row :gutter="12">
            <el-col :span="12">
              <el-form-item label="单位名称" required>
                <el-input v-model="rev.debtor" :disabled="readonly" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="关联交易">
                <el-switch v-model="rev.isRelatedParty" :disabled="readonly" active-text="是" inactive-text="否" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="收回/转回金额">
                <WpAmountInput v-model="rev.reversalAmount" :disabled="readonly" style="width:100%" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="转回前累计计提">
                <WpAmountInput v-model="rev.accumulatedProvision" :disabled="readonly" style="width:100%" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="收回方式">
                <el-input v-model="rev.recoveryMethod" :disabled="readonly" placeholder="现金收回/抵债/债务重组等" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="索引号">
                <el-input v-model="rev.indexRef" :disabled="readonly" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="转回原因">
            <el-input v-model="rev.reason" type="textarea" :rows="2" :disabled="readonly" />
          </el-form-item>
          <el-form-item label="原减值依据">
            <el-input v-model="rev.originalBasis" type="textarea" :rows="2" :disabled="readonly" placeholder="原确定减值准备的依据" />
          </el-form-item>
        </el-form>

        <!-- 核销 -->
        <el-form v-else label-width="140px" size="small">
          <el-row :gutter="12">
            <el-col :span="12">
              <el-form-item label="单位名称" required>
                <el-input v-model="wo.debtor" :disabled="readonly" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="关联交易产生">
                <el-switch v-model="wo.isRelatedParty" :disabled="readonly" active-text="是" inactive-text="否" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="核销金额">
                <WpAmountInput v-model="wo.writeoffAmount" :disabled="readonly" style="width:100%" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="应收款性质">
                <el-input v-model="wo.nature" :disabled="readonly" placeholder="融资租赁/分期收款等" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="索引号">
                <el-input v-model="wo.indexRef" :disabled="readonly" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="审批完整">
                <el-tag :type="wo.approvalComplete ? 'success' : 'danger'" size="small">
                  {{ wo.approvalComplete ? '是' : '否/待确认' }}
                </el-tag>
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="核销原因">
            <el-input v-model="wo.reason" type="textarea" :rows="2" :disabled="readonly" />
          </el-form-item>
          <el-form-item label="履行的核销程序">
            <el-input v-model="wo.procedures" type="textarea" :rows="2" :disabled="readonly" placeholder="董事会/管理层审批、法务意见、备查登记等" @change="onCheckChange" />
          </el-form-item>
        </el-form>
      </el-tab-pane>

      <el-tab-pane label="② 合理性分析" name="judge">
        <p class="hint">逐项判断后可一键汇总为「合理性分析」结论文字；人工结论优先。</p>
        <div v-for="c in checks" :key="c.id" class="check-item">
          <div class="check-head">
            <span class="check-label">{{ c.label }}</span>
            <el-tag v-if="c.result" :type="resultTag(c.result)" size="small">{{ c.result }}</el-tag>
          </div>
          <el-radio-group v-model="c.result" size="small" :disabled="readonly" @change="onCheckChange">
            <el-radio-button v-for="o in RESULT_OPTIONS" :key="o" :value="o">{{ o }}</el-radio-button>
          </el-radio-group>
          <el-input
            v-model="c.note"
            size="small"
            :disabled="readonly"
            placeholder="简要说明 / 证据摘录"
            style="margin-top:6px"
          />
        </div>
        <div class="sum-actions">
          <el-button size="small" type="primary" plain :disabled="readonly" @click="fillReasonablenessFromChecks">
            汇总检查项 → 合理性分析
          </el-button>
        </div>
        <el-input
          v-if="mode === 'reversal'"
          v-model="rev.reasonableness"
          type="textarea"
          :rows="3"
          :disabled="readonly"
          placeholder="合理性分析结论"
        />
        <el-input
          v-else
          v-model="wo.reasonableness"
          type="textarea"
          :rows="3"
          :disabled="readonly"
          placeholder="合理性分析结论"
        />
      </el-tab-pane>
    </el-tabs>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :disabled="readonly" @click="onSave">保存并回填底稿</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.mb { margin-bottom: 12px; }
.hint { margin: 0 0 10px; font-size: 12px; color: #909399; }
.check-item {
  border: 1px solid #ebeef5; border-radius: 6px; padding: 10px 12px; margin-bottom: 10px; background: #fafafa;
}
.check-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 6px; }
.check-label { font-size: 13px; font-weight: 500; color: #303133; line-height: 1.4; }
.sum-actions { margin: 8px 0 10px; }
</style>
