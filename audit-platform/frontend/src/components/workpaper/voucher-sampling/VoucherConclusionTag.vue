<script setup lang="ts">
/**
 * 凭证检查行的他稿结论（spec voucher-workflow-linkage-lineage-closure R6，design §9）
 *
 * 放在「来源」列（VoucherRowMetaCell 内）：同一凭证在其他可见底稿也有检查行时显示「他稿 n」；其中有判为异常的
 * 显示「他稿异常」。点开逐底稿列编码、结论（异常 / 正常 / 未判定）与行数，可打开该底稿（带返回当前页的地址）。
 * 查询失败显示「他稿结论加载失败」可重试，不显示成「无」。只做提示，不阻断保存。
 */
import { computed, hasInjectionContext, inject } from 'vue'
import { routeLocationKey } from 'vue-router'
import { rowVoucherKey } from '@/components/attachment/rowEvidence'
import { voucherKeyLabel, voucherKeyYear } from '@/components/attachment/workpaperEvidence'
import { useVoucherConclusionIndex } from '@/composables/useVoucherConclusionIndex'
import { VOUCHER_VERDICT_LABEL, type VoucherVerdict } from '@/utils/voucherVerdict'
import { workpaperRouteFromLedger } from '@/utils/voucherLedgerRoute'
import { WorkpaperRuntimeContextKey } from '../composables/useWorkpaperScaffold'

const props = defineProps<{ row: unknown; projectId: string }>()

const runtime = hasInjectionContext() ? inject(WorkpaperRuntimeContextKey, null) : null
const route = hasInjectionContext() ? inject(routeLocationKey, null) : null
const wpId = computed(() => runtime?.wpId.value ?? '')
const voucherKey = computed(() => rowVoucherKey(props.row))
/** 年度取凭证键自带的（同 VoucherEvidenceTag：不少宿主给「来源」列缺省年度 0） */
const year = computed(() => voucherKeyYear(voucherKey.value))
const label = computed(() => voucherKeyLabel(voucherKey.value) || '本凭证')

const index = useVoucherConclusionIndex(() => props.projectId, () => year.value, () => voucherKey.value)
const others = computed(() => index.entries.value.filter((e) => e.working_paper_id !== wpId.value))
const abnormal = computed(() => others.value.some((e) => e.verdict === 'abnormal'))
const failed = computed(() => index.status.value === 'error' || index.status.value === 'forbidden')

const VERDICT_TYPE: Record<VoucherVerdict, 'danger' | 'success' | 'info'> = {
  abnormal: 'danger', normal: 'success', unknown: 'info',
}

function routeOf(workpaperId: string) {
  return workpaperRouteFromLedger(props.projectId, workpaperId, { returnTo: route?.fullPath ?? null })
}
</script>

<template>
  <el-button
    v-if="voucherKey && failed"
    class="gt-voucher-conclusion__ref"
    link
    size="small"
    type="danger"
    data-testid="voucher-conclusion-error"
    :title="index.status.value === 'forbidden' ? '无权查看其他底稿的检查结论，点击重试' : '点击重试'"
    @click.stop="index.retry()"
  >
    他稿结论加载失败
  </el-button>
  <!-- persistent=false：点开才渲染（凭证检查表可能有上千行） -->
  <el-popover v-else-if="voucherKey && others.length" placement="bottom-start" trigger="click" :width="340" :persistent="false">
    <template #reference>
      <el-button
        class="gt-voucher-conclusion__ref"
        link
        size="small"
        :type="abnormal ? 'danger' : 'info'"
        data-testid="voucher-conclusion-tag"
        :aria-label="`凭证 ${label} 在其他 ${others.length} 张底稿有检查行${abnormal ? '，其中有判为异常的' : ''}`"
        @click.stop
      >
        {{ abnormal ? '他稿异常' : `他稿 ${others.length}` }}
      </el-button>
    </template>
    <div class="gt-voucher-conclusion" data-testid="voucher-conclusion-panel">
      <div class="gt-voucher-conclusion__title">凭证 {{ label }} 在其他底稿的检查结论</div>
      <ul class="gt-voucher-conclusion__list">
        <li v-for="e in others" :key="e.working_paper_id" class="gt-voucher-conclusion__item">
          <span class="gt-voucher-conclusion__wp" :title="e.wp_name">{{ e.wp_code || '其他底稿' }} {{ e.wp_name }}</span>
          <el-tag size="small" :type="VERDICT_TYPE[e.verdict]" effect="plain">{{ VOUCHER_VERDICT_LABEL[e.verdict] }}</el-tag>
          <span class="gt-voucher-conclusion__hint">{{ e.rows }} 行</span>
          <router-link :to="routeOf(e.working_paper_id)" class="gt-voucher-conclusion__open">打开底稿</router-link>
          <div v-if="e.legacy" class="gt-voucher-conclusion__hint gt-voucher-conclusion__note">旧行按凭证号和日期认出</div>
        </li>
      </ul>
      <div v-if="index.partial.value" class="gt-voucher-conclusion__hint">检查表内容过多，结果可能不全</div>
      <div class="gt-voucher-conclusion__hint">只做提示，结论以各底稿为准</div>
    </div>
  </el-popover>
</template>

<style scoped>
.el-button.gt-voucher-conclusion__ref {
  padding: 0 2px;
  min-height: auto;
  margin-left: 0;
}
.gt-voucher-conclusion__title {
  margin: 4px 0;
  font-weight: 600;
  font-size: var(--gt-font-size-xs, 12px);
}
.gt-voucher-conclusion__list {
  list-style: none;
  margin: 0 0 6px;
  padding: 0;
  max-height: 240px;
  overflow-y: auto;
}
.gt-voucher-conclusion__item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 3px 0;
  font-size: var(--gt-font-size-xs, 12px);
}
.gt-voucher-conclusion__wp {
  flex: 1;
  min-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.gt-voucher-conclusion__open {
  color: var(--gt-color-primary, #4b2d77);
}
.gt-voucher-conclusion__note {
  flex-basis: 100%;
}
.gt-voucher-conclusion__hint {
  color: var(--gt-color-text-tertiary, #909399);
  font-size: var(--gt-font-size-xs, 12px);
}
</style>
