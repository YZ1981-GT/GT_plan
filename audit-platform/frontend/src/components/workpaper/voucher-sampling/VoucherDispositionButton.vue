<script setup lang="ts">
/**
 * 凭证检查异常行的「处置」（spec voucher-workflow-linkage-lineage-closure R7，design §9）
 *
 * 本行按结论取值表判为异常（rowVerdict）、底稿可编辑、不是年审阶段锁定的预审行、取得到底稿编码时才出：
 * - 记入未更正错报：填金额（必填、> 0）与类型（事实 / 判断 / 推断），经 `a13:push-misstatement` 交给底稿页的错报桥落库
 *   （桥按「底稿 + 描述 + 金额 + 科目 + 类型」去重，同一分录同金额同类型只落一笔）；
 * - 去调整分录：打开本项目调整分录页。
 */
import { computed, hasInjectionContext, inject, ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { rowVerdict } from '@/utils/voucherVerdict'
import { voucherKeyLabel } from '@/components/attachment/workpaperEvidence'
import { metaOf } from '../composables/shared/voucherCheckFill'
import { WorkpaperRuntimeContextKey } from '../composables/useWorkpaperScaffold'

type MisstatementKind = 'factual' | 'judgmental' | 'projected'

const props = defineProps<{ row: unknown; projectId: string; locked?: boolean }>()

const runtime = hasInjectionContext() ? inject(WorkpaperRuntimeContextKey, null) : null
const wpCode = computed(() => runtime?.wpCode?.value ?? '')
const meta = computed(() => metaOf(props.row))
const visible = computed(() =>
  rowVerdict(props.row) === 'abnormal' && !runtime?.readonly?.value && !props.locked && !!wpCode.value && !!props.projectId,
)

/** 科目取分录指纹第 6 项（[年度, 主体, 日期, 凭证字, 号, 科目, 借贷, 金额, 序号]） */
const accountCode = computed<string | null>(() => {
  try {
    const parts = meta.value?.lfp ? JSON.parse(meta.value.lfp) : null
    return Array.isArray(parts) && typeof parts[5] === 'string' && parts[5] ? parts[5] : null
  } catch {
    return null
  }
})
const voucherName = computed(() => {
  const label = voucherKeyLabel(meta.value?.vk ?? null)
  if (label) return label
  const r = (props.row ?? {}) as Record<string, unknown>
  return [r.voucherDate ?? r.voucher_date, r.voucherNo ?? r.voucher_no].filter(Boolean).join(' ') || '本行凭证'
})
const description = computed(() => `凭证 ${voucherName.value} 抽查异常`)

const open = ref(false)
const amount = ref<number | undefined>(undefined)
const kind = ref<MisstatementKind>('factual')
const canPush = computed(() => typeof amount.value === 'number' && amount.value > 0)

function pushMisstatement() {
  if (!canPush.value) return
  eventBus.emit('a13:push-misstatement', {
    wpCode: wpCode.value,
    accountCode: accountCode.value,
    amount: amount.value,
    misstatementType: kind.value,
    // 描述里已有凭证称呼，不再传 voucherNo（桥会再追加一次「（凭证:…）」）
    description: description.value,
  })
  open.value = false
  amount.value = undefined
}
</script>

<template>
  <el-popover v-if="visible" v-model:visible="open" placement="bottom-start" trigger="click" :width="300" :persistent="false">
    <template #reference>
      <el-button class="gt-voucher-disposition__ref" link size="small" type="danger" data-testid="voucher-disposition"
        :aria-label="`处置异常凭证 ${voucherName}`" @click.stop>
        处置
      </el-button>
    </template>
    <div class="gt-voucher-disposition" data-testid="voucher-disposition-panel">
      <div class="gt-voucher-disposition__title">{{ description }}</div>
      <div class="gt-voucher-disposition__section">记入未更正错报</div>
      <el-input-number v-model="amount" :min="0" :precision="2" :controls="false" size="small" placeholder="错报金额（必填）"
        class="gt-voucher-disposition__amount" data-testid="voucher-disposition-amount" />
      <el-radio-group v-model="kind" size="small" class="gt-voucher-disposition__kind">
        <el-radio-button value="factual">事实错报</el-radio-button>
        <el-radio-button value="judgmental">判断错报</el-radio-button>
        <el-radio-button value="projected">推断错报</el-radio-button>
      </el-radio-group>
      <div class="gt-voucher-disposition__hint">科目：{{ accountCode || '未识别（记入后可在错报汇总里补）' }}</div>
      <el-button type="primary" size="small" :disabled="!canPush" data-testid="voucher-disposition-push" @click="pushMisstatement">
        记入
      </el-button>
      <div class="gt-voucher-disposition__section">或者</div>
      <router-link :to="{ name: 'Adjustments', params: { projectId } }" class="gt-voucher-disposition__link"
        data-testid="voucher-disposition-adjust">去调整分录</router-link>
    </div>
  </el-popover>
</template>

<style scoped>
.el-button.gt-voucher-disposition__ref {
  padding: 0 2px;
  min-height: auto;
  margin-left: 0;
}
.gt-voucher-disposition {
  display: grid;
  gap: 6px;
  font-size: var(--gt-font-size-xs, 12px);
}
.gt-voucher-disposition__title {
  font-weight: 600;
}
.gt-voucher-disposition__section {
  margin-top: 2px;
  color: var(--gt-color-text-secondary, #606266);
}
.gt-voucher-disposition__amount {
  width: 100%;
}
.gt-voucher-disposition__hint {
  color: var(--gt-color-text-tertiary, #909399);
}
.gt-voucher-disposition__link {
  color: var(--gt-color-primary, #4b2d77);
}
</style>
