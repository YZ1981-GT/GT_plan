<script setup lang="ts">
/**
 * AttachVoucherToWpDialog.vue — 序时账「挂凭到底稿」弹窗
 *
 * 审计师在账簿查询里手工挑到关注/异常凭证 → 挂到某张底稿（如 E1 货币资金、
 * D2 应收账款）的凭证检查表。记录到 sampled_vouchers（working_paper_id + source='ledger'），
 * 底稿凭证检查表通过「从序时账挂入导入」拉取（useAttachedVouchers）。
 */
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { listWorkpapersPaged } from '@/services/workpaperApi'
import { attachVoucher } from '@/components/workpaper/composables/useAttachedVouchers'

interface VoucherTarget {
  voucherNo: string
  accountCode?: string | null
}

const props = defineProps<{
  modelValue: boolean
  projectId: string
  year: number
  /** 待挂入的凭证清单（去重后） */
  vouchers: VoucherTarget[]
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'attached', payload: { count: number; workpaperId: string }): void
}>()

const CYCLE_NAMES: Record<string, string> = {
  A: 'A 完成阶段', B: 'B 风险评估', C: 'C 控制测试', D: 'D 销售循环',
  E: 'E 货币资金', F: 'F 存货', G: 'G 投资', H: 'H 固定资产',
  I: 'I 无形资产', J: 'J 薪酬', K: 'K 费用', L: 'L 负债',
  M: 'M 权益', N: 'N 税项', S: 'S 特定项目',
}

/** 科目编码前缀 → 建议目标底稿主编码（含凭证检查表的常见科目） */
const ACCOUNT_TO_WP: Array<{ prefix: string; wp: string }> = [
  { prefix: '1001', wp: 'E1' }, { prefix: '1002', wp: 'E1' }, { prefix: '1012', wp: 'E1' },
  { prefix: '1121', wp: 'D1' }, { prefix: '1122', wp: 'D2' },
  { prefix: '1221', wp: 'K1' }, { prefix: '1231', wp: 'K2' },
  { prefix: '2241', wp: 'K3' }, { prefix: '2245', wp: 'K4' },
  { prefix: '6001', wp: 'D4' }, { prefix: '6051', wp: 'D4' },
  { prefix: '6601', wp: 'K8' }, { prefix: '6602', wp: 'K9' },
  { prefix: '2211', wp: 'J1' },
]

interface WpOption {
  wp_id: string
  wp_code: string
  wp_name: string
  cycle: string
}

const loading = ref(false)
const submitting = ref(false)
const wpOptions = ref<WpOption[]>([])
const selectedWpId = ref<string>('')
const note = ref('')

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const voucherCount = computed(() => props.vouchers.length)

/** 按循环分组的可选底稿（供 el-select 分组展示） */
const groupedOptions = computed(() => {
  const byCycle = new Map<string, WpOption[]>()
  for (const w of wpOptions.value) {
    const arr = byCycle.get(w.cycle) ?? []
    arr.push(w)
    byCycle.set(w.cycle, arr)
  }
  return Array.from(byCycle.entries())
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([cycle, items]) => ({
      label: CYCLE_NAMES[cycle] || `${cycle} 循环`,
      options: items.sort((a, b) => a.wp_code.localeCompare(b.wp_code, undefined, { numeric: true })),
    }))
})

/** 根据待挂凭证的科目推断建议目标底稿编码 */
function suggestWpCode(): string {
  for (const v of props.vouchers) {
    const code = String(v.accountCode || '')
    const hit = ACCOUNT_TO_WP.find((m) => code.startsWith(m.prefix))
    if (hit) return hit.wp
  }
  return ''
}

const loadError = ref('')

async function loadWorkpapers(): Promise<void> {
  loading.value = true
  loadError.value = ''
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
    for (const it of collected) {
      // wp_id 可为 null（底稿未生成），此时用 wp_index_id 替代作为标识
      // 挂凭目标只需底稿存在（wp_index 有记录），不强制文件已生成
      const wpId = (it?.wp_id ?? it?.wp_index_id ?? it?.id ?? '') as string
      const code = String(it?.wp_code || '')
      if (!wpId || !code) continue
      opts.push({
        wp_id: wpId,
        wp_code: code,
        wp_name: String(it?.wp_name ?? code),
        cycle: code[0] || '?',
      })
    }
    wpOptions.value = opts

    if (opts.length === 0) {
      loadError.value = '该项目暂无底稿，请先在底稿管理中生成底稿'
    }

    // 智能默认：按科目推断的建议底稿若已生成则预选
    const suggested = suggestWpCode()
    if (suggested) {
      const match = opts.find((o) => o.wp_code === suggested)
      if (match) selectedWpId.value = match.wp_id
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
    for (const v of props.vouchers) {
      if (!v.voucherNo) continue
      try {
        await attachVoucher(props.projectId, {
          year: props.year,
          voucherNo: v.voucherNo,
          accountCode: v.accountCode ?? null,
          workpaperId: selectedWpId.value,
          source: 'ledger',
          note: note.value || `序时账挂入${v.accountCode ? ' · ' + v.accountCode : ''}`,
        })
        ok += 1
      } catch {
        /* 单张失败不阻断其余 */
      }
    }
    if (ok > 0) {
      const wp = wpOptions.value.find((o) => o.wp_id === selectedWpId.value)
      ElMessage.success(`已挂入 ${ok} 张凭证到「${wp?.wp_name || wp?.wp_code || '底稿'}」，可在该底稿凭证检查表「从序时账挂入导入」`)
      emit('attached', { count: ok, workpaperId: selectedWpId.value })
      visible.value = false
    } else {
      ElMessage.error('挂凭失败，请稍后重试')
    }
  } finally {
    submitting.value = false
  }
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
          >{{ v.voucherNo }}</el-tag>
          <span v-if="voucherCount === 0" class="empty-hint">（无凭证，请在凭证/明细层选择带凭证号的行）</span>
        </div>
      </div>

      <div class="attach-field">
        <span class="attach-label">目标底稿 <span class="req">*</span></span>
        <el-select
          v-model="selectedWpId"
          filterable
          clearable
          placeholder="选择要挂入的底稿（含凭证检查表的底稿更适用）"
          :loading="loading"
          style="width: 100%"
        >
          <template v-if="loadError" #empty>
            <div style="padding: 10px 20px; color: #909399; font-size: 12px; text-align: center">
              {{ loadError }}
            </div>
          </template>
          <el-option-group
            v-for="grp in groupedOptions"
            :key="grp.label"
            :label="grp.label"
          >
            <el-option
              v-for="o in grp.options"
              :key="o.wp_id"
              :label="`${o.wp_code} ${o.wp_name}`"
              :value="o.wp_id"
            />
          </el-option-group>
        </el-select>
        <div v-if="loadError" class="error-hint">⚠️ {{ loadError }}</div>
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
</style>
