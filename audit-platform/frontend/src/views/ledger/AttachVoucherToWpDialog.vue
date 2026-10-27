<script setup lang="ts">
/**
 * AttachVoucherToWpDialog.vue — 序时账「挂凭到底稿」弹窗
 *
 * 审计师在账簿查询里手工挑到关注/异常凭证 → 挂到某张底稿（如 E1 货币资金、
 * D2 应收账款）的凭证检查表。记录到 sampled_vouchers（working_paper_id + source='ledger'），
 * 底稿凭证检查表通过「从序时账挂入导入」拉取（useAttachedVouchers）。
 *
 * ## 2026-10-14 改造
 * - el-select → el-tree-select 树形折叠选择器（循环→底稿两级）
 * - 科目推荐：从 wp_account_mapping.json 权威映射消费，覆盖 D~N 全 72 个 primary
 * - 多对多凭证：传入凭证所有分录科目，推荐所有涉及的底稿（⭐ 推荐组置顶展开）
 */
import { ref, computed, watch, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listWorkpapersPaged } from '@/services/workpaperApi'
import { attachFailureReason, attachVoucher } from '@/components/workpaper/composables/useAttachedVouchers'
import { voucherLabel } from '@/utils/voucherIdentity'
import { findAllRecommendedWpCodes } from './accountToWpMapping'

interface VoucherTarget {
  voucherNo: string
  /** 凭证日期 YYYY-MM-DD。🔴 凭证号跨日重复，无日期时底稿回拉可能命中同号别张凭证。 */
  voucherDate?: string | null
  /** 凭证字（'' = 凭证字为空）；同日同号可能有多种凭证字，null = 不知道（后端命中多张时拒绝并列候选） */
  voucherType?: string | null
  accountCode?: string | null
}

const props = defineProps<{
  modelValue: boolean
  projectId: string
  year: number
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
  (e: 'attached', payload: { count: number; workpaperId: string }): void
  /** 用户选择跳转到目标底稿 */
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

// ── el-tree-select 节点结构 ──
interface TreeNode {
  id: string
  label: string
  /** 叶子节点才有值：真实 wp_id */
  wpId?: string
  /** 是否禁用（循环组节点禁选） */
  disabled?: boolean
  children?: TreeNode[]
  /** 是否推荐底稿（用于样式高亮） */
  isRecommended?: boolean
}

const loading = ref(false)
const submitting = ref(false)
const wpOptions = ref<WpOption[]>([])
const selectedWpId = ref<string>('')
const note = ref('')
const treeSelectRef = ref<any>(null)

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const voucherCount = computed(() => props.vouchers.length)

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

/** 树形数据：推荐组置顶 + 按循环分组折叠 */
const treeData = computed<TreeNode[]>(() => {
  const opts = wpOptions.value
  if (opts.length === 0) return []

  const recommended = recommendedWpCodes.value
  const nodes: TreeNode[] = []

  // ── ⭐ 推荐底稿组（仅有推荐时才出现） ──
  const recItems = opts
    .filter((w) => recommended.has(w.wp_code))
    .sort((a, b) => a.wp_code.localeCompare(b.wp_code, undefined, { numeric: true }))
  if (recItems.length > 0) {
    nodes.push({
      id: '__recommend__',
      label: `⭐ 推荐底稿（${recItems.length}）`,
      disabled: true,
      children: recItems.map((w) => ({
        id: w.wp_id,
        label: `${w.wp_code} ${w.wp_name}`,
        wpId: w.wp_id,
        isRecommended: true,
      })),
    })
  }

  // ── 按循环分组 ──
  const byCycle = new Map<string, WpOption[]>()
  for (const w of opts) {
    const arr = byCycle.get(w.cycle) ?? []
    arr.push(w)
    byCycle.set(w.cycle, arr)
  }

  const sortedCycles = [...byCycle.entries()]
    .sort((a, b) => cycleSortKey(a[0]) - cycleSortKey(b[0]))

  for (const [cycle, items] of sortedCycles) {
    const hasRec = items.some((w) => recommended.has(w.wp_code))
    const sorted = items.sort((a, b) =>
      a.wp_code.localeCompare(b.wp_code, undefined, { numeric: true }),
    )
    nodes.push({
      id: `cycle_${cycle}`,
      label: CYCLE_NAMES[cycle] || `${cycle} 循环`,
      disabled: true,
      children: sorted.map((w) => ({
        id: w.wp_id,
        label: `${w.wp_code} ${w.wp_name}`,
        wpId: w.wp_id,
        isRecommended: recommended.has(w.wp_code),
      })),
    })
  }

  return nodes
})

/** el-tree-select 默认展开的节点：推荐组 + 有推荐底稿的循环组 */
const defaultExpandedKeys = computed<string[]>(() => {
  const keys: string[] = []
  const recommended = recommendedWpCodes.value
  if (recommended.size > 0) {
    keys.push('__recommend__')
    // 也展开有推荐底稿的循环组
    for (const w of wpOptions.value) {
      if (recommended.has(w.wp_code)) {
        const cycleKey = `cycle_${w.cycle}`
        if (!keys.includes(cycleKey)) keys.push(cycleKey)
      }
    }
  }
  return keys
})

/** 过滤方法：搜索时按 wp_code 和 wp_name 匹配 */
function filterNode(value: string, data: TreeNode): boolean {
  if (!value) return true
  const keyword = value.toLowerCase()
  return data.label.toLowerCase().includes(keyword)
}

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
    const collected: any[] = []
    let page = 1
    for (;;) {
      const env: any = await listWorkpapersPaged(props.projectId, { page, page_size: 100 })
      const items: any[] = Array.isArray(env?.items) ? env.items : []
      collected.push(...items)
      const total = Number.isFinite(env?.total) ? Number(env.total) : collected.length
      if (items.length === 0 || collected.length >= total || page > 20) break
      page += 1
    }
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

    // 智能默认：有推荐底稿时预选第一个
    await nextTick()
    if (!selectedWpId.value) {
      const recommended = recommendedWpCodes.value
      if (recommended.size > 0) {
        const first = opts.find((o) => recommended.has(o.wp_code))
        if (first) selectedWpId.value = first.wp_id
      }
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
    selectedWpId.value = ''
    note.value = ''
    void loadWorkpapers()
  }
})

async function confirm(): Promise<void> {
  if (!selectedWpId.value) {
    ElMessage.warning('请选择目标底稿')
    return
  }
  if (voucherCount.value === 0) {
    ElMessage.warning('无可挂入的凭证')
    return
  }
  submitting.value = true
  try {
    let ok = 0
    const failures: string[] = []
    for (const v of props.vouchers) {
      if (!v.voucherNo) continue
      try {
        await attachVoucher(props.projectId, {
          year: props.year,
          voucherNo: v.voucherNo,
          voucherDate: v.voucherDate ?? null,
          voucherType: v.voucherType ?? null,
          accountCode: v.accountCode ?? null,
          workpaperId: selectedWpId.value,
          source: 'ledger',
          note: note.value || `序时账挂入${v.accountCode ? ' · ' + v.accountCode : ''}`,
        })
        ok += 1
      } catch (e) {
        // 单张失败不阻断其余，原因汇总给用户（多张凭证 / 账套里没有 / 无权限）
        failures.push(`${voucherName(v)}：${attachFailureReason(e)}`)
      }
    }
    if (failures.length > 0) {
      ElMessage.warning({
        message: `${failures.length} 张凭证没挂上：${failures.slice(0, 3).join('；')}${failures.length > 3 ? ' 等' : ''}`,
        duration: 8000,
        showClose: true,
      })
    }
    if (ok > 0) {
      const wp = wpOptions.value.find((o) => o.wp_id === selectedWpId.value)
      const wpName = wp?.wp_name || wp?.wp_code || '底稿'
      const wpCode = wp?.wp_code || ''
      emit('attached', { count: ok, workpaperId: selectedWpId.value })
      visible.value = false

      // 挂凭成功后询问是否跳转到目标底稿
      try {
        await ElMessageBox.confirm(
          `已挂入 ${ok} 张凭证到「${wpCode} ${wpName}」。\n是否立即跳转到该底稿查看？`,
          '挂凭成功',
          {
            confirmButtonText: '跳转到底稿',
            cancelButtonText: '留在当前页',
            type: 'success',
          },
        )
        // 用户点了「跳转到底稿」
        emit('navigateToWp', {
          workpaperId: selectedWpId.value,
          wpCode,
          wpName,
        })
      } catch {
        // 用户点了「留在当前页」或关闭，什么都不做
      }
    } else if (failures.length === 0) {
      ElMessage.error('挂凭失败，请稍后重试')
    }
  } finally {
    submitting.value = false
  }
}

/** 凭证称呼：「2025-01-07 FY-0003」（凭证字未知时只写号） */
function voucherName(v: VoucherTarget): string {
  return `${v.voucherDate ? `${v.voucherDate} ` : ''}${voucherLabel(v.voucherType, v.voucherNo)}`
}
</script>

<template>
  <el-dialog
    v-model="visible"
    title="挂凭到底稿"
    width="560px"
    append-to-body
    destroy-on-close
  >
    <div class="attach-body">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="将选中凭证挂入某张底稿的凭证检查表"
        description="挂入后，可在目标底稿的凭证检查表点击「从序时账挂入导入」把这些凭证带入检查行。"
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
        <span class="attach-label">目标底稿 <span class="req">*</span></span>
        <el-tree-select
          ref="treeSelectRef"
          v-model="selectedWpId"
          :data="treeData"
          :props="{ children: 'children', label: 'label', disabled: 'disabled' }"
          :default-expanded-keys="defaultExpandedKeys"
          node-key="id"
          filterable
          :filter-node-method="filterNode"
          clearable
          check-strictly
          :render-after-expand="false"
          placeholder="选择要挂入的底稿（⭐ 推荐底稿已根据科目自动匹配）"
          style="width: 100%"
        >
          <template #default="{ data }">
            <span :class="{ 'recommended-node': data.isRecommended }">
              <span v-if="data.isRecommended" class="rec-dot">⭐</span>
              {{ data.label }}
            </span>
          </template>
        </el-tree-select>
        <div v-if="ungeneratedHint" class="hint-text">💡 {{ ungeneratedHint }}</div>
        <div v-if="loadError" class="error-hint">⚠️ {{ loadError }}</div>
        <div v-if="recommendedWpCodes.size > 0 && !selectedWpId" class="hint-text">
          💡 根据凭证科目自动推荐了 {{ recommendedWpCodes.size }} 个底稿，已在⭐推荐组中展开
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
    </div>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button
        type="primary"
        :loading="submitting"
        :disabled="!selectedWpId || voucherCount === 0"
        @click="confirm"
      >挂入底稿（{{ voucherCount }} 张）</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.attach-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
  font-size: 13px;
}
.attach-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.attach-label {
  font-weight: 600;
  color: #303133;
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
  color: #909399;
  font-size: 12px;
}
.error-hint {
  color: var(--el-color-warning);
  font-size: 12px;
  margin-top: 4px;
}
.hint-text {
  color: #909399;
  font-size: 12px;
  margin-top: 2px;
}
/* 推荐底稿节点高亮 */
.recommended-node {
  color: var(--el-color-warning-dark-2);
  font-weight: 600;
}
.rec-dot {
  margin-right: 2px;
}
/* tree-select 下拉面板：紧凑字号 + 限高 */
:deep(.el-tree-select__popper .el-scrollbar) {
  max-height: 360px;
}
:deep(.el-tree-node__content) {
  height: 26px;
  font-size: 12px;
}
:deep(.el-tree-node__label) {
  font-size: 12px;
}
/* 循环组节点样式：稍加粗 */
:deep(.el-tree-node__content .is-disabled > .el-tree-node__label) {
  font-weight: 600;
  color: #606266;
  font-size: 12px;
}
</style>
