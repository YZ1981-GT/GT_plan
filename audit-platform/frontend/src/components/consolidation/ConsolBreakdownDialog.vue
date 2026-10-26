<template>
  <!--
    ConsolBreakdownDialog — 报表页右键「查看合并明细」（spec consol-autotree-linkage-closure R8.2）
    报表行次走读时计算（与合并报表差额表同一求值）：列 下级节点 / 来源 / 金额 / 占比，底部合并数取后端合计，
    不在前端求和；纯数字科目码沿用已落库的穿透明细。差额户（本级抵销与调整）高亮；单体项目与下级合并项目可进入。
    所有文本中文；金额统一走 GtAmountCell；进入项目纳入 Backspace 返回栈。
  -->
  <el-dialog
    :model-value="modelValue"
    :title="title"
    width="760px"
    append-to-body
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
    <div v-loading="loading">
      <div v-if="data?.node_label" class="cbd-meta" data-testid="cbd-node">汇总节点：{{ data.node_label }}</div>
      <el-alert v-if="!loading && rows.length && data?.message" type="info" :closable="false" show-icon
        class="cbd-note" data-testid="cbd-message" :title="data.message" />

      <!-- 空态：无明细 / 留空 / 读取失败 -->
      <el-empty v-if="!loading && rows.length === 0" :description="emptyMessage" />

      <template v-else-if="rows.length">
        <el-table :data="rows" border size="small" class="consol-breakdown-table" :row-class-name="rowClass">
          <el-table-column label="下级节点" min-width="200">
            <template #default="{ row }">
              <a v-if="jumpTarget(row)" class="cbd-link" data-testid="cbd-enter" @click="handleJump(row)">{{ rowLabel(row) }}</a>
              <span v-else>{{ rowLabel(row) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="来源" width="110">
            <template #default="{ row }">{{ row.source || '—' }}</template>
          </el-table-column>
          <el-table-column label="金额" min-width="150" align="right">
            <template #default="{ row }">
              <span v-if="isBlank(row.amount)" class="cbd-blank" :title="row.reason || ''">留空</span>
              <GtAmountCell v-else :value="row.amount" :clickable="!!jumpTarget(row)" @click="handleJump(row)" />
            </template>
          </el-table-column>
          <el-table-column label="占比" width="100" align="right">
            <template #default="{ row }">{{ pctText(row) }}</template>
          </el-table-column>
        </el-table>

        <!-- 底部：合并数 = 后端合计（含本级抵销与调整） -->
        <div class="consol-breakdown-footer" data-testid="cbd-footer">
          <span v-if="!isBlank(data?.elimination)" class="cbd-elim">
            其中本级抵销与调整 <GtAmountCell :value="data?.elimination ?? null" />
          </span>
          <span class="consol-breakdown-footer__label">合并数</span>
          <span v-if="isBlank(data?.consolidated)" class="cbd-blank">留空</span>
          <GtAmountCell v-else :value="data?.consolidated ?? null" />
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
import { getConsolRowBreakdown, type ConsolRowBreakdown, type ConsolRowBreakdownItem } from '@/services/consolidationApi'
import { useNavigationStack, type NavigationEntry } from '@/composables/useNavigationStack'
import { useProjectStore } from '@/stores/project'
import { projectVisibleInOptions } from '@/components/consolidation/composables/consolEntityView'
import GtAmountCell from '@/components/common/GtAmountCell.vue'

const props = defineProps<{
  modelValue: boolean
  projectId: string
  year: number
  /** 报表行次（报表页右键传的就是行次；纯数字按科目码走已落库的穿透明细） */
  accountCode?: string
  /** 汇总节点；省略 = 根合并节点 */
  nodeKey?: string | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  jump: [payload: { source_project_id: string; row: ConsolRowBreakdownItem }]
}>()

const router = useRouter()
const route = useRoute()
const { push: navPush } = useNavigationStack()
const projectStore = useProjectStore()

const loading = ref(false)
const data = ref<ConsolRowBreakdown | null>(null)
const failMessage = ref('')
let seq = 0

const rows = computed<ConsolRowBreakdownItem[]>(() =>
  data.value?.has_breakdown !== false && Array.isArray(data.value?.by_company) ? data.value!.by_company : [],
)
const title = computed(() => (data.value?.row_name ? `查看合并明细 · ${data.value.row_name}` : '查看合并明细'))

/** 空态文案：读取失败原因 > 后端说明（如「该行合并数留空：…」）> 默认 */
const emptyMessage = computed(() => failMessage.value || data.value?.message || '该报表行暂无合并明细')

function isBlank(v: unknown): boolean {
  return v === null || v === undefined || v === ''
}

function rowLabel(row: ConsolRowBreakdownItem): string {
  return row.display_name || row.company_name || row.company_code
}

/** 差额户（本级抵销与调整）整行高亮 */
function rowClass({ row }: { row: ConsolRowBreakdownItem }): string {
  return row.kind === 'elim' ? 'cbd-row-elim' : ''
}

/** 占比：读时路径用后端百分数；已落库路径用 4 位小数比例换算；留空 / 合并数为 0 ⇒「—」 */
function pctText(row: ConsolRowBreakdownItem): string {
  if (!isBlank(row.pct)) return `${row.pct}%`
  if (isBlank(row.ratio) || isBlank(row.amount)) return '—'
  try {
    return `${new Decimal(row.ratio as string).times(100).toFixed(2)}%`
  } catch {
    return '—'
  }
}

/** 可进入的项目：单体数据节点 → 单体报表；下级合并节点 → 其合并报表；差额户没有项目 */
function jumpTarget(row: ConsolRowBreakdownItem): { path: string; query: Record<string, string> } | null {
  const pid = row.source_project_id
  if (!pid || row.kind === 'elim') return null
  if (row.kind === 'aggregate') return { path: `/projects/${pid}/consolidation`, query: { year: String(props.year), tab: 'report' } }
  return { path: `/projects/${pid}/reports`, query: { year: String(props.year) } }
}

watch(
  () => [props.modelValue, props.projectId, props.year, props.accountCode, props.nodeKey] as const,
  ([open]) => { if (open) void fetchBreakdown() },
  { immediate: true },
)

async function fetchBreakdown() {
  const my = ++seq
  loading.value = true
  data.value = null
  failMessage.value = ''
  try {
    const res = await getConsolRowBreakdown(props.projectId, props.year, props.accountCode ?? '', props.nodeKey)
    if (my === seq) data.value = res
  } catch (e: any) {
    if (my !== seq) return
    const body = e?.response?.data
    const detail = body?.detail ?? body?.message
    failMessage.value = typeof detail === 'string' && detail ? `读取合并明细失败：${detail}` : '读取合并明细失败，请稍后重试'
  } finally {
    if (my === seq) loading.value = false
  }
}

/** 进入下级项目（单体报表 / 下级合并报表），纳入 Backspace 返回栈；前端预检只用于提示，权限由目标页接口判定 */
async function handleJump(row: ConsolRowBreakdownItem) {
  emit('jump', { source_project_id: row.source_project_id ?? row.company_code, row })
  const target = jumpTarget(row)
  if (!target) {
    ElMessage.info(row.kind === 'elim'
      ? '差额户没有对应项目，本级抵销与调整分录请在合并页「差额分录」中查看'
      : '该企业本年度没有对应项目，无法进入')
    return
  }
  if (!(await checkProjectAccess(row.source_project_id as string))) {
    ElMessage.warning('无权访问该企业项目')
    return
  }
  const entry: NavigationEntry = {
    source_view: route.fullPath,
    label: `合并明细 → ${rowLabel(row)}`,
    direction: 'down',
    scroll_position: window.scrollY,
  }
  navPush(entry)
  router.push(target)
  emit('update:modelValue', false)
}

async function checkProjectAccess(targetProjectId: string): Promise<boolean> {
  try {
    await projectStore.loadProjectOptions()
  } catch {
    return true
  }
  return projectVisibleInOptions(projectStore.projectOptions, targetProjectId)
}
</script>

<style scoped>
.consol-breakdown-table { width: 100%; }
.consol-breakdown-table :deep(.cbd-row-elim td) { background: var(--el-color-warning-light-9); }
.cbd-meta { margin-bottom: 8px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); }
.cbd-note { margin-bottom: 8px; }
.cbd-link { color: var(--gt-color-primary); cursor: pointer; }
.cbd-link:hover { text-decoration: underline; }
.cbd-blank { color: var(--gt-color-text-placeholder); cursor: help; }
.cbd-elim { margin-right: auto; display: inline-flex; align-items: center; gap: 4px; font-weight: 400; color: var(--gt-color-text-secondary); }
.consol-breakdown-footer {
  display: flex; align-items: center; justify-content: flex-end; gap: 12px;
  margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--gt-color-border, #ebeef5); font-weight: 600;
}
.consol-breakdown-footer__label { color: var(--gt-color-text-regular, #606266); }
</style>
