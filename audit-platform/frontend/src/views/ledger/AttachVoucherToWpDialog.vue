<script setup lang="ts">
/**
 * AttachVoucherToWpDialog.vue — 序时账「挂凭到底稿」弹窗
 *
 * 审计师在账簿查询里手工挑到关注/异常凭证 → 挂到底稿（如 E1 货币资金、J1 职工薪酬）的凭证检查表。
 * 记录到 sampled_vouchers 的手工侧（凭证按当前账套定位成一张，阶段取项目当前阶段），底稿凭证检查表
 * 通过「从序时账挂入导入」拉取（useAttachedVouchers.pullSamplesForWorkpaper，只取本底稿科目的分录）。
 *
 * ## 2026-10-14 改造
 * - 科目推荐：从 wp_account_mapping.json 权威映射消费，覆盖 D~N 全 72 个 primary
 * - 多对多凭证：传入凭证所有分录科目，推荐所有涉及的底稿（⭐ 推荐组置顶）
 *
 * ## 任务 14（spec voucher-identity-writeback-and-audit-phase，需求 5.1）
 * - 一张凭证挂多张底稿：底稿改多选，推荐底稿默认勾选；每张底稿只列一次（推荐的列在 ⭐ 组，不在循环组重复）
 * - 一次提交走批量接口，逐条返回新挂 / 已挂 / 失败原因；有失败时弹窗不关，列出哪张凭证挂哪张底稿没成、为什么
 */
import { ref, computed, watch, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listWorkpapersAll } from '@/services/workpaperApi'
import {
  ATTACH_BATCH_MAX_PAIRS, ATTACH_STATUS, attachFailureReason, attachVouchersBatch, type AttachBatchResult,
} from '@/components/workpaper/composables/useAttachedVouchers'
import { voucherLabel } from '@/utils/voucherIdentity'
import { MISSING_AUDIT_YEAR_MESSAGE } from '@/composables/useProjectAuditYear'
import { findAllRecommendedWpCodes } from './accountToWpMapping'

interface VoucherTarget {
  voucherNo: string
  /** 凭证日期 YYYY-MM-DD。🔴 凭证号跨日重复，无日期时可能对应多张凭证（后端逐条报「对应多张」）。 */
  voucherDate?: string | null
  /** 凭证字（'' = 凭证字为空）；同日同号可能有多种凭证字，null = 不知道（后端命中多张时这一条失败并列候选） */
  voucherType?: string | null
  /** 主体编码（一套账两个主体时区分同日同号凭证）；不知道传 null */
  companyCode?: string | null
  accountCode?: string | null
}

const props = defineProps<{
  modelValue: boolean
  projectId: string
  /** 审计年度；项目没填为 null ⇒ 挂入提示去填年度、不发请求 */
  year: number | null
  /** 待挂入的凭证清单（去重后） */
  vouchers: VoucherTarget[]
  /**
   * 凭证涉及的所有科目编码（去重）。
   * 用于推荐相关底稿——多对多凭证（如借方 1002 贷方 2201）会推荐 E1 和 F3。
   * 为空时退化为从 vouchers[].accountCode 提取。
   */
  allAccountCodes?: string[]
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  /** 至少一条挂上（新挂或之前已挂）：宿主据 voucherKeys 刷新已挂标识 */
  (e: 'attached', payload: {
    count: number; existed: number; workpaperId: string; workpaperIds: string[]; voucherKeys: string[]
  }): void
  /** 用户选择跳转到目标底稿（只选了一张底稿时询问） */
  (e: 'navigateToWp', payload: { workpaperId: string; wpCode: string; wpName: string }): void
}>()

const CYCLE_NAMES: Record<string, string> = {
  A: 'A 完成阶段', B: 'B 风险评估', C: 'C 控制测试', D: 'D 销售循环',
  E: 'E 货币资金', F: 'F 存货', G: 'G 投资', H: 'H 固定资产',
  I: 'I 无形资产', J: 'J 薪酬', K: 'K 费用', L: 'L 负债',
  M: 'M 权益', N: 'N 税项', S: 'S 特定项目',
}

// ── 审计循环排序优先级（B~S 实质性底稿在前，A 完成阶段排后面）──
const CYCLE_ORDER = 'D E F G H I J K L M N S B C A'.split(' ')
function cycleSortKey(c: string): number {
  const i = CYCLE_ORDER.indexOf(c)
  return i >= 0 ? i : 99
}

interface WpOption {
  /** 真实 `working_paper.id`。🔴 绝不可用 `wp_index_id` 兜底 —— 见 loadWorkpapers 注释。 */
  wp_id: string
  wp_code: string
  wp_name: string
  cycle: string
  /** 底稿是否已生成。false 的项不进选项（挂上去拉不回来）。 */
  wpGenerated: boolean
}

interface OptionGroup {
  key: string
  label: string
  recommended: boolean
  items: WpOption[]
}

const loading = ref(false)
const submitting = ref(false)
const wpOptions = ref<WpOption[]>([])
const selectedWpIds = ref<string[]>([])
const note = ref('')
/** 上次提交没挂上的条目（弹窗内列出）与汇总 */
const failures = ref<AttachBatchResult[]>([])
const lastSummary = ref<{ created: number; existed: number; failed: number } | null>(null)

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const voucherCount = computed(() => props.vouchers.filter(v => v.voucherNo).length)
const pairCount = computed(() => voucherCount.value * selectedWpIds.value.length)

/** 收集所有凭证涉及的科目编码 */
const allCodes = computed<string[]>(() => {
  if (props.allAccountCodes?.length) return props.allAccountCodes
  // 退化：从 vouchers[].accountCode 提取
  const set = new Set<string>()
  for (const v of props.vouchers) {
    const code = String(v.accountCode || '').trim()
    if (code) set.add(code)
  }
  return [...set]
})

/** 推荐的底稿 wp_code 集合 */
const recommendedWpCodes = computed(() => {
  return new Set(findAllRecommendedWpCodes(allCodes.value))
})

const byCode = (a: WpOption, b: WpOption) => a.wp_code.localeCompare(b.wp_code, undefined, { numeric: true })

/** 选项分组：⭐ 推荐组置顶，其余按循环分组；每张底稿只出现一次 */
const optionGroups = computed<OptionGroup[]>(() => {
  const recommended = recommendedWpCodes.value
  const groups: OptionGroup[] = []
  const recItems = wpOptions.value.filter(w => recommended.has(w.wp_code)).sort(byCode)
  if (recItems.length > 0) {
    groups.push({ key: '__recommend__', label: `⭐ 推荐底稿（${recItems.length}）`, recommended: true, items: recItems })
  }
  const byCycle = new Map<string, WpOption[]>()
  for (const w of wpOptions.value) {
    if (recommended.has(w.wp_code)) continue
    const arr = byCycle.get(w.cycle) ?? []
    arr.push(w)
    byCycle.set(w.cycle, arr)
  }
  for (const [cycle, items] of [...byCycle.entries()].sort((a, b) => cycleSortKey(a[0]) - cycleSortKey(b[0]))) {
    groups.push({ key: `cycle_${cycle}`, label: CYCLE_NAMES[cycle] || `${cycle} 循环`, recommended: false, items: items.sort(byCode) })
  }
  return groups
})

const loadError = ref('')
/** 被过滤掉的未生成底稿提示（如实告知，避免用户找不到目标底稿而困惑） */
const ungeneratedHint = ref('')

async function loadWorkpapers(): Promise<void> {
  loading.value = true
  loadError.value = ''
  ungeneratedHint.value = ''
  try {
    if (!props.projectId) {
      loadError.value = '项目ID缺失，请从项目内页面打开'
      wpOptions.value = []
      return
    }
    // 一次取完全部可见底稿（原先 100 条一页串行拉，spec platform-perf-hotspots R5）
    const collected = await listWorkpapersAll(props.projectId)
    const opts: WpOption[] = []
    let ungeneratedCount = 0
    for (const it of collected) {
      const code = String(it?.wp_code || '')
      if (!code) continue
      // 🔴 只认真实 `working_paper.id`，绝不用 `wp_index_id` 兜底。
      const wpId = String(it?.wp_id ?? '')
      const generated = it?.wp_generated === true || (!!wpId && it?.wp_generated == null)
      if (!wpId || !generated) {
        ungeneratedCount += 1
        continue
      }
      if (opts.some(o => o.wp_id === wpId)) continue
      opts.push({
        wp_id: wpId,
        wp_code: code,
        wp_name: String(it?.wp_name ?? code),
        cycle: code[0] || '?',
        wpGenerated: true,
      })
    }
    wpOptions.value = opts

    if (opts.length === 0) {
      loadError.value = ungeneratedCount > 0
        ? `该项目 ${ungeneratedCount} 张底稿均未生成，无法挂凭。请先在底稿管理中生成底稿`
        : '该项目暂无底稿，请先在底稿管理中生成底稿'
    } else if (ungeneratedCount > 0) {
      ungeneratedHint.value = `${ungeneratedCount} 张未生成的底稿已隐藏（生成后才能挂凭）`
    }

    // 推荐底稿默认勾选（需求 5.1）：一张多科目凭证一次挂进它涉及的每张底稿
    await nextTick()
    if (selectedWpIds.value.length === 0) {
      const recommended = recommendedWpCodes.value
      selectedWpIds.value = opts.filter(o => recommended.has(o.wp_code)).sort(byCode).map(o => o.wp_id)
    }
  } catch (err: any) {
    wpOptions.value = []
    const status = err?.response?.status
    if (status === 401 || status === 403) {
      loadError.value = '权限不足，无法获取底稿列表'
    } else if (status === 404) {
      loadError.value = '项目不存在或无法访问'
    } else {
      loadError.value = '获取底稿列表失败，请检查网络后重试'
    }
  } finally {
    loading.value = false
  }
}

watch(visible, (v) => {
  if (v) {
    selectedWpIds.value = []
    note.value = ''
    failures.value = []
    lastSummary.value = null
    void loadWorkpapers()
  }
})

function wpById(id: string): WpOption | undefined {
  return wpOptions.value.find(o => o.wp_id === id)
}

async function confirm(): Promise<void> {
  if (selectedWpIds.value.length === 0) {
    ElMessage.warning('请选择目标底稿')
    return
  }
  if (voucherCount.value === 0) {
    ElMessage.warning('无可挂入的凭证')
    return
  }
  const year = props.year
  if (year == null) {
    ElMessage.warning(MISSING_AUDIT_YEAR_MESSAGE)
    return
  }
  if (pairCount.value > ATTACH_BATCH_MAX_PAIRS) {
    ElMessage.warning(`一次最多挂 ${ATTACH_BATCH_MAX_PAIRS} 个「凭证 × 底稿」组合，当前 ${voucherCount.value} 张凭证 × `
      + `${selectedWpIds.value.length} 张底稿 = ${pairCount.value} 个，请减少后分批挂入`)
    return
  }
  submitting.value = true
  const wpIds = [...selectedWpIds.value]
  try {
    const res = await attachVouchersBatch(props.projectId, {
      year,
      vouchers: props.vouchers.filter(v => v.voucherNo).map(v => ({
        voucherNo: v.voucherNo,
        voucherDate: v.voucherDate ?? null,
        voucherType: v.voucherType ?? null,
        companyCode: v.companyCode ?? null,
        accountCode: v.accountCode ?? null,
      })),
      workpaperIds: wpIds,
      note: note.value || '序时账挂入',
      source: 'ledger',
    })
    failures.value = res.results.filter(r => r.status === ATTACH_STATUS.FAILED)
    lastSummary.value = { created: res.created, existed: res.existed, failed: res.failed }
    const ok = res.created + res.existed
    if (ok > 0) {
      const voucherKeys = [...new Set(res.results.filter(r => r.status !== ATTACH_STATUS.FAILED && r.voucher_key)
        .map(r => r.voucher_key as string))]
      emit('attached', { count: res.created, existed: res.existed, workpaperId: wpIds[0], workpaperIds: wpIds, voucherKeys })
    }
    if (failures.value.length > 0) {
      // 有没挂上的：弹窗不关，下方列出明细（可改选底稿后再提交，已挂上的再提交只算「已挂」）
      ElMessage.warning({ message: `${failures.value.length} 条没挂上，原因见弹窗下方`, duration: 5000, showClose: true })
      return
    }
    visible.value = false
    const existedText = res.existed > 0 ? `（其中 ${res.existed} 条之前已挂，未重复登记）` : ''
    if (wpIds.length > 1) {
      ElMessage.success(`已挂入 ${voucherCount.value} 张凭证 × ${wpIds.length} 张底稿${existedText}`)
      return
    }
    const wp = wpById(wpIds[0])
    const wpName = wp?.wp_name || wp?.wp_code || '底稿'
    const wpCode = wp?.wp_code || ''
    try {
      await ElMessageBox.confirm(
        `已挂入 ${voucherCount.value} 张凭证到「${wpCode} ${wpName}」${existedText}。\n是否立即跳转到该底稿查看？`,
        '挂凭成功',
        { confirmButtonText: '跳转到底稿', cancelButtonText: '留在当前页', type: 'success' },
      )
      emit('navigateToWp', { workpaperId: wpIds[0], wpCode, wpName })
    } catch {
      // 用户点了「留在当前页」或关闭，什么都不做
    }
  } catch (e) {
    // 整单失败（无编辑权限、组合超限、网络）：一条都没写
    ElMessage.error(`挂凭失败：${attachFailureReason(e)}`)
  } finally {
    submitting.value = false
  }
}

/** 凭证称呼：「2025-01-07 FY-0003」（凭证字未知时只写号） */
function voucherName(v: { voucherDate?: string | null; voucherType?: string | null; voucherNo: string }): string {
  return `${v.voucherDate ? `${v.voucherDate} ` : ''}${voucherLabel(v.voucherType, v.voucherNo)}`
}

function failureTarget(f: AttachBatchResult): string {
  if (f.wp_code) return f.wp_code
  return wpById(f.working_paper_id)?.wp_code ?? '（底稿不在本项目）'
}
</script>

<template>
  <el-dialog
    v-model="visible"
    title="挂凭到底稿"
    width="600px"
    append-to-body
    destroy-on-close
  >
    <div class="attach-body">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="将选中凭证挂入底稿的凭证检查表（可同时挂多张底稿）"
        description="挂入后，可在目标底稿的凭证检查表点击「从序时账挂入导入」把这些凭证带入检查行；每张底稿只导入本科目的分录。"
      />

      <div class="attach-field">
        <span class="attach-label">待挂凭证</span>
        <div class="voucher-chips">
          <el-tag
            v-for="(v, i) in vouchers"
            :key="i"
            size="small"
            type="warning"
            effect="plain"
          >{{ voucherName(v) }}</el-tag>
          <span v-if="voucherCount === 0" class="empty-hint">（无凭证，请在凭证/明细层选择带凭证号的行）</span>
        </div>
      </div>

      <!-- 涉及科目提示（多对多凭证时显示所有科目） -->
      <div v-if="allCodes.length > 0" class="attach-field">
        <span class="attach-label">涉及科目</span>
        <div class="voucher-chips">
          <el-tag
            v-for="code in allCodes"
            :key="code"
            size="small"
            type="info"
            effect="plain"
          >{{ code }}</el-tag>
        </div>
      </div>

      <div class="attach-field">
        <span class="attach-label">目标底稿（可多选） <span class="req">*</span></span>
        <el-select
          v-model="selectedWpIds"
          multiple
          filterable
          clearable
          collapse-tags
          collapse-tags-tooltip
          :max-collapse-tags="4"
          :loading="loading"
          placeholder="选择要挂入的底稿（⭐ 推荐底稿已按凭证科目默认勾选）"
          style="width: 100%"
          data-testid="attach-wp-select"
        >
          <el-option-group v-for="g in optionGroups" :key="g.key" :label="g.label">
            <el-option
              v-for="w in g.items"
              :key="w.wp_id"
              :label="`${w.wp_code} ${w.wp_name}`"
              :value="w.wp_id"
            >
              <span :class="{ 'recommended-node': g.recommended }">
                <span v-if="g.recommended" class="rec-dot">⭐</span>{{ w.wp_code }} {{ w.wp_name }}
              </span>
            </el-option>
          </el-option-group>
        </el-select>
        <div v-if="ungeneratedHint" class="hint-text">💡 {{ ungeneratedHint }}</div>
        <div v-if="loadError" class="error-hint">⚠️ {{ loadError }}</div>
        <div v-if="recommendedWpCodes.size > 0 && optionGroups[0]?.recommended" class="hint-text">
          💡 按凭证涉及的科目推荐了 {{ optionGroups[0].items.length }} 张底稿，已默认勾选；不需要的可取消
        </div>
        <div v-if="pairCount > ATTACH_BATCH_MAX_PAIRS" class="error-hint">
          ⚠️ 一次最多挂 {{ ATTACH_BATCH_MAX_PAIRS }} 个「凭证 × 底稿」组合（当前 {{ pairCount }} 个），请减少后分批挂入
        </div>
      </div>

      <div class="attach-field">
        <span class="attach-label">挂凭说明</span>
        <el-input
          v-model="note"
          type="textarea"
          :rows="2"
          maxlength="200"
          show-word-limit
          placeholder="可填：为何挂入（如大额、异常整数收支、疑似关联方往来等），供底稿检查时参考"
        />
      </div>

      <div v-if="failures.length > 0 && lastSummary" class="attach-field" data-testid="attach-failures">
        <el-alert
          type="warning"
          :closable="false"
          show-icon
          :title="`${failures.length} 条没挂上（新挂 ${lastSummary.created} 条、之前已挂 ${lastSummary.existed} 条已处理）`"
        />
        <ul class="failure-list">
          <li v-for="(f, i) in failures" :key="i">
            <span class="failure-voucher">{{ voucherName({ voucherDate: f.voucher_date, voucherType: f.voucher_type, voucherNo: f.voucher_no }) }}</span>
            → {{ failureTarget(f) }}：{{ f.reason || '挂凭失败' }}
          </li>
        </ul>
      </div>
    </div>

    <template #footer>
      <el-button @click="visible = false">{{ failures.length > 0 ? '关闭' : '取消' }}</el-button>
      <el-button
        type="primary"
        :loading="submitting"
        :disabled="selectedWpIds.length === 0 || voucherCount === 0 || pairCount > ATTACH_BATCH_MAX_PAIRS"
        @click="confirm"
      >挂入底稿（{{ voucherCount }} 张 × {{ selectedWpIds.length }} 张底稿）</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.attach-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
  font-size: var(--gt-font-size-sm);
}
.attach-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.attach-label {
  font-weight: 600;
  color: var(--gt-color-text-primary);
}
.attach-label .req {
  color: var(--el-color-danger);
}
.voucher-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  max-height: 120px;
  overflow-y: auto;
}
.empty-hint {
  color: var(--gt-color-text-tertiary);
  font-size: var(--gt-font-size-xs);
}
.error-hint {
  color: var(--el-color-warning);
  font-size: var(--gt-font-size-xs);
  margin-top: 4px;
}
.hint-text {
  color: var(--gt-color-text-tertiary);
  font-size: var(--gt-font-size-xs);
  margin-top: 2px;
}
/* 推荐底稿选项高亮 */
.recommended-node {
  color: var(--el-color-warning-dark-2);
  font-weight: 600;
}
.rec-dot {
  margin-right: 2px;
}
.failure-list {
  margin: 0;
  padding-left: 18px;
  max-height: 160px;
  overflow-y: auto;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-regular);
}
.failure-voucher {
  font-weight: 600;
}
</style>
