<template>
  <div class="adj-screen">
    <header class="adj-header">
      <h1 class="adj-header__title">调整分录</h1>
      <span class="adj-header__count">
        共 {{ entries.length }} 条分录（已批准 {{ approvedCount }} 条，只有已批准的进入试算表）
      </span>
    </header>

    <p v-if="!year" class="citar-adj__empty">{{ yearLoading ? '正在读取项目信息…' : '项目未设置审核年度，请先在项目信息里填写' }}</p>
    <template v-else>
      <div class="adj-toolbar">
        <button class="adj-button" type="button" disabled title="请在原调整分录页使用粘贴导入">导入分录</button>
        <button class="adj-button" type="button" :disabled="exporting || !entries.length" @click="exportSummary">
          {{ exporting ? '导出中…' : '导出分录' }}
        </button>
        <button class="adj-button" type="button" :disabled="loading" @click="load">刷新</button>
      </div>

      <p v-if="loading && !entries.length" class="citar-adj__empty">正在读取调整分录…</p>
      <p v-else-if="error" class="citar-adj__empty">{{ error }}</p>

      <datalist :id="DATALIST_ID">
        <option v-for="a in accounts" :key="a.code" :value="a.code">{{ a.name }}</option>
      </datalist>

      <CitarAdjustmentCard
        v-for="entry in visibleEntries"
        :key="entry.groupId || 'new'"
        :entry="entry"
        :editing="editingKey === keyOf(entry)"
        :busy="busy"
        :datalist-id="DATALIST_ID"
        :account-names="accountNames"
        :can-review="canReview"
        @edit="startEdit(entry)"
        @cancel="cancelEdit"
        @save="onSave(entry)"
        @remove="onRemove(entry)"
        @review="(status) => onReview(entry, status)"
        @revoke="onRevoke(entry)"
      />

      <p v-if="!loading && !error && !visibleEntries.length" class="citar-adj__empty">本年度还没有调整分录。</p>

      <div class="adj-footer">
        <button class="adj-add-entry" type="button" :disabled="!!editingKey || busy" @click="startNew">+ 增加一条分录</button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * 调整分录（CITAR 版式，接平台调整分录）：
 * 列表 / 新建 / 编辑 / 删除（草稿与驳回）/ 提交复核 / 复核通过 / 驳回 / 撤回复核 / 导出汇总。
 * 一次只编辑一条：未保存的修改在取消或刷新时丢弃。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import { accountChart as P_chart, adjustments as P_adj } from '@/services/apiPaths'
import { downloadFile } from '@/utils/http'
import { handleApiError } from '@/utils/errorHandler'
import { useProjectRole } from '@/composables/useProjectRole'
import { ADJUSTMENT_STATUS } from '@/constants/statusEnum'
import CitarAdjustmentCard from '../components/CitarAdjustmentCard.vue'
import { newEntry, useCitarAdjustments, type AdjEntry, type ReviewTarget } from '../useCitarAdjustments'
import { useCitarProject } from '../useCitarProject'

defineOptions({ name: 'CitarAdjustment' })

const DATALIST_ID = 'citar-adj-accounts'

const { projectId, year, yearLoading } = useCitarProject()
const { entries, loading, error, load, save, remove, review, revoke } = useCitarAdjustments(
  () => projectId.value,
  () => year.value,
)
const { projectCan } = useProjectRole(projectId)
const canReview = computed(() => projectCan('adjustment:review'))

const busy = ref(false)
const exporting = ref(false)
/** 正在编辑的分录：已保存的用 groupId，新建的用 'new' */
const editingKey = ref('')
/** 新建中的分录（保存前不在列表里） */
const draft = ref<AdjEntry | null>(null)
/** 编辑前的快照，取消时还原 */
let snapshot = ''

const keyOf = (e: AdjEntry) => e.groupId || 'new'
const approvedCount = computed(() => entries.value.filter(e => e.status === ADJUSTMENT_STATUS.APPROVED).length)
const visibleEntries = computed(() => (draft.value ? [...entries.value, draft.value] : entries.value))

// ── 科目选项 ──
// 先取平台调整分录页同源的下拉（报表行次已确认的标准科目，名称是标准名）；
// 新项目还没确认行次时它是空的，再并上标准科目表 —— 后端校验的就是「在标准科目表里」。
const accounts = ref<{ code: string; name: string }[]>([])
const accountNames = computed(() => new Map(accounts.value.map(a => [a.code, a.name])))

async function loadAccounts() {
  const silent = { _silent: true } as any
  const [dropdown, chart] = await Promise.allSettled([
    api.get(P_adj.accountDropdown(projectId.value), silent),
    api.get(P_chart.standard(projectId.value), silent),
  ])
  const merged = new Map<string, string>()
  if (dropdown.status === 'fulfilled' && Array.isArray(dropdown.value)) {
    for (const o of dropdown.value as any[]) merged.set(o.code, o.name)
  }
  if (chart.status === 'fulfilled' && Array.isArray(chart.value)) {
    for (const a of chart.value as any[]) if (!merged.has(a.account_code)) merged.set(a.account_code, a.account_name)
  }
  accounts.value = [...merged].map(([code, name]) => ({ code, name })).sort((a, b) => a.code.localeCompare(b.code))
}

function startNew() {
  draft.value = newEntry()
  editingKey.value = 'new'
}

function startEdit(entry: AdjEntry) {
  snapshot = JSON.stringify(entry)
  editingKey.value = keyOf(entry)
}

function cancelEdit() {
  if (editingKey.value === 'new') {
    draft.value = null
  } else {
    const restored = JSON.parse(snapshot) as AdjEntry
    const i = entries.value.findIndex(e => e.groupId === restored.groupId)
    if (i >= 0) entries.value[i] = restored
  }
  editingKey.value = ''
}

async function run(action: () => Promise<void>, context: string, done: string) {
  busy.value = true
  try {
    await action()
    ElMessage.success(done)
    editingKey.value = ''
    draft.value = null
    await load()
  } catch (e) {
    handleApiError(e, context)
  } finally {
    busy.value = false
  }
}

function onSave(entry: AdjEntry) {
  void run(() => save(entry), '保存调整分录', entry.groupId ? '已保存' : '已新建，状态为草稿')
}

async function onRemove(entry: AdjEntry) {
  try {
    await ElMessageBox.confirm(`删除分录 ${entry.no}？删除后不再显示，也不计入试算表。`, '删除调整分录', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  void run(() => remove(entry), '删除调整分录', '已删除')
}

const REVIEW_DONE: Record<ReviewTarget, string> = {
  [ADJUSTMENT_STATUS.PENDING_REVIEW]: '已提交复核',
  [ADJUSTMENT_STATUS.APPROVED]: '已复核通过，试算表将按此分录重算',
  [ADJUSTMENT_STATUS.REJECTED]: '已驳回',
}

async function onReview(entry: AdjEntry, status: ReviewTarget) {
  let reason: string | undefined
  if (status === ADJUSTMENT_STATUS.REJECTED) {
    try {
      const { value } = await ElMessageBox.prompt('请填写驳回原因', `驳回 ${entry.no}`, {
        confirmButtonText: '驳回',
        cancelButtonText: '取消',
        inputValidator: (v: string) => (!!v && !!v.trim()) || '驳回原因不能为空',
      })
      reason = value.trim()
    } catch {
      return
    }
  }
  void run(() => review(entry, status, reason), '变更复核状态', REVIEW_DONE[status])
}

async function onRevoke(entry: AdjEntry) {
  try {
    await ElMessageBox.confirm(`撤回 ${entry.no} 的复核？分录回到草稿，试算表将不再计入。`, '撤回复核', {
      type: 'warning',
      confirmButtonText: '撤回',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  void run(() => revoke(entry), '撤回复核', '已撤回，分录回到草稿')
}

async function exportSummary() {
  if (!year.value) return
  exporting.value = true
  try {
    await downloadFile(P_adj.exportSummary(projectId.value), {
      params: { year: year.value, format: 'excel' },
      fileName: `调整分录汇总_${year.value}.xlsx`,
      silent: true,
    })
  } catch (e) {
    handleApiError(e, '导出调整分录')
  } finally {
    exporting.value = false
  }
}

watch(
  [projectId, year],
  () => {
    editingKey.value = ''
    draft.value = null
    void load()
    void loadAccounts()
  },
  { immediate: true },
)
</script>

<style scoped src="../styles/adjustment.css"></style>

<style scoped>
.citar-adj__empty {
  margin-top: 16px;
  padding: 24px 16px;
  border: 1px dashed #e4d8f3;
  border-radius: 8px;
  text-align: center;
  font-size: var(--citar-fs-13);
  color: var(--citar-c-9a9aa4);
  background: var(--citar-c-fdfcff);
}

.adj-add-entry:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}
</style>
