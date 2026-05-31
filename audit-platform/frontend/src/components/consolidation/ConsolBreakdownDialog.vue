<template>
  <!--
    ConsolBreakdownDialog — 统一合并穿透弹窗（report + note 一个组件，ADR-CONSOL-301）
    props.source 仅决定调哪个端点，渲染契约统一（T1：列/占比/抵销/合并数/跳转一致）。
    - source=note   → Phase 3 端点 notes/{section}/consol-breakdown
    - source=report → Phase 2 端点 report/{account_code}/consol-breakdown（前瞻，未就绪时友好降级）
    所有文本中文；金额统一走 GtAmountCell；行点击跳转纳入 Backspace 返回栈（T3）。
  -->
  <el-dialog
    :model-value="modelValue"
    title="查看合并明细"
    width="720px"
    append-to-body
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
    @open="handleOpen"
  >
    <div v-loading="loading">
      <!-- 空态：无 breakdown / 未跑 V2 / 报表端点未就绪 -->
      <el-empty v-if="!loading && rows.length === 0" :description="emptyMessage" />

      <template v-else>
        <el-table :data="rows" border size="small" class="consol-breakdown-table">
          <el-table-column label="子公司名称" min-width="180">
            <template #default="{ row }">
              {{ row.company_name || row.company_code }}
            </template>
          </el-table-column>
          <el-table-column label="金额" min-width="140" align="right">
            <template #default="{ row }">
              <GtAmountCell :value="row.amount" clickable @click="handleJump(row)" />
            </template>
          </el-table-column>
          <el-table-column label="占比" min-width="100" align="right">
            <template #default="{ row }">
              {{ formatPercentRow(row) }}
            </template>
          </el-table-column>
          <el-table-column label="抵销额" min-width="140" align="right">
            <template #default="{ row }">
              <GtAmountCell
                v-if="row.elimination_amount !== undefined && row.elimination_amount !== null"
                :value="row.elimination_amount"
              />
              <span v-else>-</span>
            </template>
          </el-table-column>
        </el-table>

        <!-- 底部合并数 -->
        <div class="consol-breakdown-footer">
          <span class="consol-breakdown-footer__label">合并数</span>
          <GtAmountCell :value="footerAmount" />
        </div>
      </template>
    </div>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import Decimal from 'decimal.js'
import { api } from '@/services/apiProxy'
import { consolidation as P_consol } from '@/services/apiPaths'
import { useNavigationStack, type NavigationEntry } from '@/composables/useNavigationStack'
import { useProjectStore } from '@/stores/project'
import GtAmountCell from '@/components/common/GtAmountCell.vue'

interface BreakdownRow {
  company_code: string
  company_name?: string
  section_title?: string
  amount: number | string | null
  /** 抵销额（后端若提供则展示，否则 '-'） */
  elimination_amount?: number | string | null
  /** 来源单体项目标识（后端若提供才能跨项目跳转，缺失则不跳） */
  source_project_id?: string
}

interface BreakdownResponse {
  section_id?: string
  section_title?: string
  by_company?: BreakdownRow[]
  computed_at?: string
  has_breakdown?: boolean
  message?: string
}

const props = defineProps<{
  modelValue: boolean
  source: 'report' | 'note'
  projectId: string
  year: number
  /** source=report 用 */
  accountCode?: string
  /** source=note 用 */
  sectionId?: string
  /** 合并数（父传入用于底部显示，可选；不传则用 Σamount） */
  consolAmount?: number | string | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  jump: [payload: { source_project_id: string; source: 'report' | 'note'; row: BreakdownRow }]
}>()

const router = useRouter()
const route = useRoute()
const { push: navPush } = useNavigationStack()
const projectStore = useProjectStore()

const loading = ref(false)
const rows = ref<BreakdownRow[]>([])
const respMessage = ref('')
const hasBreakdown = ref(true)

/** 端点：source 决定调哪个；渲染契约统一不受 source 影响 */
const endpoint = computed(() =>
  props.source === 'note'
    ? P_consol.notes.consolBreakdown(props.projectId, props.year, props.sectionId ?? '')
    : P_consol.reports.consolBreakdown(props.projectId, props.year, props.accountCode ?? ''),
)

/** Σamount（Decimal 累加避免浮点误差） */
const totalAmount = computed<Decimal>(() => {
  let sum = new Decimal(0)
  for (const r of rows.value) {
    const v = safeDecimal(r.amount)
    if (v) sum = sum.plus(v)
  }
  return sum
})

/** 底部合并数：父传入优先，否则 Σamount */
const footerAmount = computed<number | string | null>(() => {
  if (props.consolAmount !== undefined && props.consolAmount !== null) return props.consolAmount
  return totalAmount.value.toString()
})

/** 空态文案（中文）：优先用后端 message，其次默认提示 */
const emptyMessage = computed(() => {
  if (respMessage.value) return respMessage.value
  if (props.source === 'note') return '该章节暂无合并明细，请先用 V2 生成合并附注'
  return '该报表行暂无合并明细'
})

function safeDecimal(v: unknown): Decimal | null {
  if (v === null || v === undefined) return null
  if (typeof v === 'string' && v.trim() === '') return null
  try {
    return new Decimal(v as Decimal.Value)
  } catch {
    return null
  }
}

/** 占比：amount / Σamount * 100，格式 xx.x%；Σ=0 → '-' */
function formatPercentRow(row: BreakdownRow): string {
  const total = totalAmount.value
  if (total.isZero()) return '-'
  const v = safeDecimal(row.amount)
  if (!v) return '-'
  const pct = v.dividedBy(total).times(100)
  return `${pct.toFixed(1)}%`
}

async function handleOpen() {
  await fetchBreakdown()
}

// 打开弹窗即拉取（watch modelValue=true 与 @open 双触发兜底）
watch(
  () => props.modelValue,
  (open) => {
    if (open) fetchBreakdown()
  },
  { immediate: true },
)

async function fetchBreakdown() {
  loading.value = true
  rows.value = []
  respMessage.value = ''
  hasBreakdown.value = true
  try {
    const data = await api.get<BreakdownResponse>(endpoint.value)
    hasBreakdown.value = data?.has_breakdown !== false
    respMessage.value = data?.message ?? ''
    if (hasBreakdown.value && Array.isArray(data?.by_company)) {
      rows.value = data.by_company
    }
  } catch (e) {
    // 报表级穿透依赖 Phase 2 端点：未就绪时（404 等）降级为友好空态，不崩溃
    rows.value = []
    if (props.source === 'report') {
      respMessage.value = '报表合并明细端点尚未就绪（依赖 Phase 2）'
    } else {
      respMessage.value = '该章节暂无合并明细，请先用 V2 生成合并附注'
    }
  } finally {
    loading.value = false
  }
}

/**
 * 行点击 → 跳转子公司单体报表/附注，并纳入 Backspace 返回栈（T3）。
 * EH2（2.4）：跳转前做项目访问权限预检——子公司单体项目必须在当前用户可见的项目列表
 *   （后端 /api/projects 已按 require_project_access 过滤）内才允许跳转；无权则 ElMessage 提示不跳。
 *   projectStore.loadProjectOptions() 拉取的 projectOptions 即用户有权访问的项目集合，
 *   作为客户端预检数据源（无专用 canAccessProject helper，避免臆造不存在的 API）。
 */
async function handleJump(row: BreakdownRow) {
  // Task 1 by_company 行当前携带 company_code/company_name/amount，未必有 source_project_id。
  const targetProjectId = row.source_project_id
  emit('jump', {
    source_project_id: targetProjectId ?? row.company_code,
    source: props.source,
    row,
  })

  if (!targetProjectId) {
    // 缺来源项目标识 → 无法定位子公司单体项目，仅 emit 不跳转
    // （附注 by_company 行的 source_project_id 溯源字段属后端 provenance 后续补全项，缺失时降级）
    ElMessage.info('无法定位子公司项目（缺来源项目标识）')
    return
  }

  // EH2 权限预检：目标子公司项目须在当前用户可访问项目列表内
  const canAccess = await checkProjectAccess(targetProjectId)
  if (!canAccess) {
    ElMessage.warning('无权访问该子公司项目')
    return
  }

  // 跳转前 push 当前路由到返回栈（镜像 usePenetrate._pushCurrentRoute，支持 Backspace 返回）
  const entry: NavigationEntry = {
    source_view: route.fullPath,
    label: `合并明细 → ${row.company_name || row.company_code}`,
    direction: 'down',
    scroll_position: window.scrollY,
  }
  navPush(entry)

  const path =
    props.source === 'report'
      ? `/projects/${targetProjectId}/reports`
      : `/projects/${targetProjectId}/disclosure-notes`
  router.push({ path, query: { year: String(props.year) } })

  // 跳转后关闭弹窗
  emit('update:modelValue', false)
}

/**
 * EH2 客户端权限预检：目标项目是否在当前用户可访问项目列表内。
 * - 先确保 projectOptions 已加载（loadProjectOptions 幂等，已加载则直接返回）
 * - 命中列表 → 有权；列表为空（加载失败/未就绪）时不误拦，交由后端路由层 require_project_access 兜底
 */
async function checkProjectAccess(targetProjectId: string): Promise<boolean> {
  try {
    await projectStore.loadProjectOptions()
  } catch {
    // 项目列表拉取失败：不做前端硬拦截，放行交后端权限兜底（避免误伤）
    return true
  }
  const options = projectStore.projectOptions
  if (!Array.isArray(options) || options.length === 0) return true
  return options.some((p) => p.id === targetProjectId)
}
</script>

<style scoped>
.consol-breakdown-table {
  width: 100%;
}

.consol-breakdown-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--gt-color-border, #ebeef5);
  font-weight: 600;
}

.consol-breakdown-footer__label {
  color: var(--gt-color-text-regular, #606266);
}
</style>
