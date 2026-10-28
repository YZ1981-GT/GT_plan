<script setup lang="ts">
/**
 * 凭证检查行的「对方科目」单元格（spec voucher-identity-writeback-and-audit-phase 需求 4.8，design §4）
 *
 * 配上的行照常显示对方科目；配不上（多借多贷金额对不出唯一对应）的行写「多科目」，点开看整张凭证分录。
 * 分录不存进底稿行，点开时按行上的凭证键现取（穿透接口，凭证键定位单张凭证）；
 * 超过配对上限的大凭证（分录过多）不在此展开，给出到序时账查看的入口。
 */
import { computed, ref } from 'vue'
import { fetchVoucherLines } from '../composables/useAttachedVouchers'
import { metaOf, MULTI_ACCOUNT } from '../composables/shared/voucherCheckFill'
import { voucherKeyAmbiguityOf, voucherLabel } from '@/utils/voucherIdentity'
import { yearQuery } from '@/utils/resolveAuditYear'
import GtAmountCell from '@/components/common/GtAmountCell.vue'

const props = defineProps<{
  row: unknown
  /** 对方科目（宿主行上的字段值） */
  account?: string | null
  accountName?: string | null
  projectId: string
  /** 审计年度兜底（凭证键带年度时以键为准）；项目没填审计年度为 null */
  year?: number | null
  /** 本行科目：大凭证跳转序时账时定位到该科目 */
  accountCode?: string | null
}>()

interface Line {
  account_code: string
  account_name: string
  debit_amount: string | null
  credit_amount: string | null
  summary: string
  line_fp?: string | null
}

const meta = computed(() => metaOf(props.row))
const label = computed(() =>
  [props.account, props.accountName && props.accountName !== props.account ? props.accountName : '']
    .filter(Boolean).join(' '))
const isMulti = computed(() =>
  props.account === MULTI_ACCOUNT || meta.value?.pr === 'multi' || meta.value?.pr === 'large')
const isLarge = computed(() => meta.value?.pr === 'large')
const parts = computed<string[] | null>(() => {
  try {
    const p = meta.value?.vk ? JSON.parse(meta.value.vk) : null
    return Array.isArray(p) && p.length === 5 ? p.map(String) : null
  } catch {
    return null
  }
})
const title = computed(() => (parts.value ? `${parts.value[2]} ${voucherLabel(parts.value[3], parts.value[4])} 整张凭证` : '整张凭证'))
const lines = ref<Line[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const loaded = ref(false)

async function load(): Promise<void> {
  if (loaded.value || loading.value || isLarge.value) return
  if (!parts.value) {
    error.value = '这一行没有凭证键（旧行或手工行），请到序时账按凭证号查看'
    return
  }
  const [keyYear, company, date, type, no] = parts.value
  const year = Number(keyYear) || props.year
  if (!year) {
    error.value = '这一行的凭证键没有年度，请到序时账按凭证号查看'
    return
  }
  loading.value = true
  error.value = null
  try {
    // 凭证键整组带上（含主体）：一套账两个主体同日同号同凭证字时只按日期 + 凭证字 + 号会命中两张
    lines.value = (await fetchVoucherLines(props.projectId, year, no, date, type, company)) as Line[]
    loaded.value = true
  } catch (e) {
    error.value = voucherKeyAmbiguityOf(e)
      ? '当前账套里这个凭证键对应多张凭证（多个主体编码），请到序时账核对'
      : '凭证分录读取失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

// 年度优先取凭证键上的（宿主没有审计年度时传的兜底值不可靠）
const ledgerRoute = computed(() => ({
  name: 'LedgerPenetration',
  params: { projectId: props.projectId },
  query: {
    ...yearQuery(Number(parts.value?.[0]) || props.year),
    ...(props.accountCode ? { account: props.accountCode } : {}),
  },
}))
</script>

<template>
  <span v-if="!isMulti" class="gt-pairing-cell">{{ label }}</span>
  <el-popover v-else trigger="click" placement="bottom-start" :width="620">
    <template #reference>
      <el-button link type="primary" size="small" data-testid="voucher-pairing-multi" @click="load">{{ MULTI_ACCOUNT }}</el-button>
    </template>
    <div class="gt-pairing-pop" data-testid="voucher-pairing-pop">
      <div class="gt-pairing-pop__title">{{ title }}</div>
      <template v-if="isLarge">
        <p>这张凭证分录过多（超过配对上限），不在这里展开。</p>
        <router-link :to="ledgerRoute" target="_blank">到序时账查看</router-link>
      </template>
      <el-alert v-else-if="error" :title="error" type="warning" :closable="false" show-icon />
      <el-table v-else v-loading="loading" :data="lines" size="small" border max-height="320">
        <el-table-column prop="account_code" label="科目" min-width="110" show-overflow-tooltip />
        <el-table-column prop="account_name" label="科目名称" min-width="140" show-overflow-tooltip />
        <el-table-column label="借方" min-width="100" align="right">
          <template #default="{ row: line }"><GtAmountCell :value="line.debit_amount" /></template>
        </el-table-column>
        <el-table-column label="贷方" min-width="100" align="right">
          <template #default="{ row: line }"><GtAmountCell :value="line.credit_amount" /></template>
        </el-table-column>
        <el-table-column prop="summary" label="摘要" min-width="140" show-overflow-tooltip />
      </el-table>
      <p class="gt-pairing-pop__hint">金额对不出唯一的对方科目（多借多贷），按整张凭证核对。</p>
    </div>
  </el-popover>
</template>

<style scoped>
.gt-pairing-pop__title {
  font-weight: 600;
  margin-bottom: 8px;
}
.gt-pairing-pop__hint {
  margin: 8px 0 0;
  color: var(--gt-color-text-secondary);
  font-size: var(--gt-font-size-xs);
}
</style>
