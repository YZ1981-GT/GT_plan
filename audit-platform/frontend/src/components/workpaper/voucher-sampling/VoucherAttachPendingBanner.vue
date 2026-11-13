<template>
  <el-alert
    v-if="visible && status"
    type="info"
    :closable="false"
    show-icon
    class="vapb"
    data-testid="voucher-attach-pending-banner"
  >
    <template #title>
      <div class="vapb-main">
        <strong>有 {{ status.pending_count }} 张凭证已从序时账挂到本底稿，尚未导入凭证检查表</strong>
        <span class="vapb-actions">
          <el-button size="small" link type="primary" data-testid="voucher-attach-pending-toggle" @click="expanded = !expanded">
            {{ expanded ? '收起' : '查看' }}
          </el-button>
          <el-button size="small" link @click="load">刷新</el-button>
          <el-button size="small" link data-testid="voucher-attach-pending-dismiss" @click="dismiss">本次不再提示</el-button>
        </span>
      </div>
      <div v-if="expanded" class="vapb-detail" data-testid="voucher-attach-pending-detail">
        <p>在凭证检查表点「📎 从序时账挂入导入」把它们带入检查行。导入时每张凭证只取本底稿科目的分录；没有本底稿科目分录的凭证，导入时会提示挂错底稿。</p>
        <ul class="vapb-list">
          <li v-for="p in shown" :key="p.id">
            <el-button
              v-if="ledgerLink(p)"
              link
              type="primary"
              size="small"
              data-testid="voucher-attach-pending-ledger"
              :title="`在序时账打开凭证 ${p.label}`"
              @click="router.push(ledgerLink(p)!)"
            >{{ p.label }}</el-button>
            <span v-else>{{ p.label }}</span>
            <span v-if="p.account_code" class="vapb-account">挂凭科目 {{ p.account_code }}</span>
          </li>
        </ul>
        <p v-if="status.pending_count > shown.length" class="vapb-more">另有 {{ status.pending_count - shown.length }} 张未列出</p>
        <p v-if="status.undetermined" class="vapb-more">另有 {{ status.undetermined }} 张旧挂凭没记凭证日期，判断不了是否已导入</p>
      </div>
    </template>
  </el-alert>
</template>

<script setup lang="ts">
/**
 * 底稿顶部「待导入」提示（spec voucher-workflow-linkage-lineage-closure R3.6，design §5.6）。
 *
 * 挂在 GtWpRenderer（VoucherSurvivalBanner 旁）：本底稿有从序时账手工挂入、但凭证检查表里按凭证身份找不到的凭证时
 * 显示张数、前 5 张（可在序时账打开）与操作说明。只提示、不导入（ADR-VWL-06：导入的科目范围与行映射在各宿主）。
 * 从挂凭结果「打开底稿」进来（`from=voucher-attach`）时默认展开；「本次不再提示」记在 sessionStorage（按底稿）。
 * 宿主读入 / 导入后会 bump 存续核对注册表的版本号（voucherCheckFill），这里据此防抖重查。
 * 读取失败或后端说判断不了（judged=false）时不显示：这是提示，不能挡住底稿，也不能把「不知道」说成「没导入」。
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import http from '@/utils/http'
import { ledger as P_ledger } from '@/services/apiPaths'
import { FROM_VOUCHER_ATTACH, ledgerRouteOfVoucherKey } from '@/utils/voucherLedgerRoute'
import { voucherSurvivalRegistryRevision } from '../composables/shared/voucherSurvivalRegistry'

interface PendingVoucher {
  id: string
  voucher_key: string | null
  label: string
  voucher_no: string
  voucher_date: string
  account_code: string | null
}
interface PendingStatus {
  attached: number
  pending: PendingVoucher[]
  pending_count: number
  undetermined: number
  judged: boolean
}

const props = defineProps<{ projectId: string; workpaperId: string; year: number | null }>()
const route = useRoute()
const router = useRouter()

const SHOWN = 5
const RELOAD_DEBOUNCE_MS = 800
const status = ref<PendingStatus | null>(null)
const expanded = ref(route.query.from === FROM_VOUCHER_ATTACH)
const dismissed = ref(false)
const shown = computed(() => (status.value?.pending ?? []).slice(0, SHOWN))
const visible = computed(() => !dismissed.value && !!status.value?.judged && status.value.pending_count > 0)

const storageKey = () => `gt:voucher-attach-pending-dismissed:${props.workpaperId}`
function readDismissed(): boolean {
  try {
    return sessionStorage.getItem(storageKey()) === '1'
  } catch {
    return false
  }
}
function dismiss(): void {
  dismissed.value = true
  try {
    sessionStorage.setItem(storageKey(), '1')
  } catch { /* 隐私模式等：只在本页内关闭 */ }
}

function ledgerLink(p: PendingVoucher) {
  return ledgerRouteOfVoucherKey(props.projectId, p.voucher_key, { accountCode: p.account_code })
}

let seq = 0
async function load(): Promise<void> {
  const { projectId, workpaperId, year } = props
  const mine = ++seq
  if (!projectId || !workpaperId || year == null) {
    status.value = null
    return
  }
  try {
    const res: any = await http.get(P_ledger.attachedVoucherStatus(projectId, workpaperId), {
      params: { year }, _silent: true, _dedupe: false,
    } as any)
    if (mine !== seq) return
    const body = res?.data?.data ?? res?.data ?? res
    status.value = body && typeof body === 'object' && Array.isArray(body.pending) ? body as PendingStatus : null
  } catch {
    if (mine === seq) status.value = null
  }
}

let timer: ReturnType<typeof setTimeout> | null = null
function scheduleReload(): void {
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => {
    timer = null
    void load()
  }, RELOAD_DEBOUNCE_MS)
}

watch(() => [props.projectId, props.workpaperId, props.year], () => {
  dismissed.value = readDismissed()
  void load()
}, { immediate: true })
watch(voucherSurvivalRegistryRevision, scheduleReload)
onBeforeUnmount(() => {
  if (timer) clearTimeout(timer)
  seq += 1
})
</script>

<style scoped>
.vapb {
  margin-bottom: var(--gt-space-2);
}
.vapb-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--gt-space-3);
  width: 100%;
}
.vapb-actions {
  display: inline-flex;
  align-items: center;
  gap: var(--gt-space-1);
}
.vapb-detail {
  margin-top: var(--gt-space-1);
  font-weight: 400;
  color: var(--gt-color-text-secondary);
}
.vapb-detail p {
  margin: 2px 0;
}
.vapb-list {
  margin: 2px 0;
  padding-left: 18px;
}
.vapb-account {
  margin-left: var(--gt-space-2);
  color: var(--gt-color-text-tertiary);
}
.vapb-more {
  color: var(--gt-color-text-tertiary);
}
</style>
