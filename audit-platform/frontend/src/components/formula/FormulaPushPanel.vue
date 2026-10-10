<template>
  <!-- 加载中整块遮罩：否则慢请求期间显示「尚未推送过 / 推送规则（0）」，像是真的没有规则 -->
  <div v-loading="loading" class="gt-fp-panel">
    <div class="gt-fp-toolbar">
      <span class="gt-fp-title">公式推送 · {{ wpCode }}</span>
      <el-button size="small" :loading="running === 'dry'" :disabled="!canRun" @click="onRun(true)">试跑（不写入）</el-button>
      <el-button size="small" type="primary" :loading="running === 'run'" :disabled="!canRun" @click="onRun(false)">
        立即推送
      </el-button>
      <el-button
        v-if="props.supportedWpCodes.length > 1"
        size="small" :loading="running === 'all'" :disabled="!canRun"
        @click="onRunAll"
      >
        全部推送
      </el-button>
      <el-button size="small" :loading="loading" @click="loadAll">刷新</el-button>
    </div>

    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon class="gt-fp-block" />

    <!-- 最近一次推送 -->
    <div class="gt-fp-block">
      <div class="gt-fp-subtitle">最近一次推送</div>
      <div v-if="latest" class="gt-fp-latest">
        <el-tag size="small" :type="runStatusTag(latest.status)">
          {{ labelOf(RUN_STATUS_LABELS, latest.status) }}
        </el-tag>
        <span>触发：{{ labelOf(TRIGGER_LABELS, latest.trigger) }}</span>
        <span>写入 {{ latest.written_count }}</span>
        <span>未变化 {{ latest.unchanged_count }}</span>
        <span>保留 {{ latest.kept_count }}</span>
        <span>跳过 {{ latest.skipped_count }}</span>
        <span class="gt-fp-muted">{{ latest.finished_at || latest.started_at || '' }}</span>
      </div>
      <el-empty v-else description="本年度尚未推送过" :image-size="48" />
      <div v-if="dryRun" class="gt-fp-dry">{{ dryRunText }}</div>
      <ul v-if="warnings.length" class="gt-fp-warnings">
        <li v-for="w in warnings" :key="w">{{ w }}</li>
      </ul>
    </div>

    <!-- 运行历史 -->
    <div class="gt-fp-block">
      <div class="gt-fp-subtitle">
        运行历史
        <el-button size="small" text @click="loadRunHistory">刷新</el-button>
      </div>
      <el-table
        v-loading="historyLoading" :data="runHistory"
        size="small" border max-height="240"
        empty-text="暂无运行记录"
        highlight-current-row
        @current-change="onRunSelect"
      >
        <el-table-column label="时间" width="165">
          <template #default="{ row }">{{ row.finished_at || row.started_at || '' }}</template>
        </el-table-column>
        <el-table-column label="触发" width="120">
          <template #default="{ row }">{{ labelOf(TRIGGER_LABELS, row.trigger) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="runStatusTag(row.status)">{{ labelOf(RUN_STATUS_LABELS, row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="写入" width="60" align="right" prop="written_count" />
        <el-table-column label="跳过" width="60" align="right" prop="skipped_count" />
        <el-table-column label="保留" width="60" align="right" prop="kept_count" />
      </el-table>
      <!-- 选中 run 的逐项明细 -->
      <template v-if="selectedRunId">
        <div class="gt-fp-subtitle" style="margin-top:8px">
          运行明细
          <el-select v-model="outcomeFilter" size="small" clearable placeholder="全部" style="width:120px">
            <el-option label="全部" value="" />
            <el-option label="已跳过" value="skipped" />
            <el-option label="失败" value="failed" />
            <el-option label="冲突" value="conflict" />
            <el-option label="已写入" value="written" />
          </el-select>
        </div>
        <el-table
          v-loading="itemsLoading" :data="runItems"
          size="small" border max-height="280"
          empty-text="无匹配项"
        >
          <el-table-column label="规则" prop="rule_id" min-width="200" show-overflow-tooltip />
          <el-table-column label="阶段" prop="stage" width="70" />
          <el-table-column label="结果" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="itemOutcomeTag(row.outcome)">{{ row.outcome || '—' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="说明" prop="reason" min-width="200" show-overflow-tooltip />
        </el-table>
      </template>
    </div>

    <!-- 待处理差异 -->
    <div class="gt-fp-block">
      <div class="gt-fp-subtitle">
        待处理差异（{{ pending.length }}）
        <el-button
          size="small" type="warning" text :disabled="!selectedAddrs.length || !canEdit"
          @click="onAdopt(selectedAddrs)"
        >采用选中项的公式值</el-button>
      </div>
      <el-table
        :data="pending" size="small" border max-height="320" empty-text="暂无待处理差异"
        @selection-change="onSelect"
      >
        <el-table-column type="selection" width="42" :selectable="actionable" />
        <el-table-column label="目标" prop="addr_id" min-width="260" show-overflow-tooltip />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="row.state === 'locked' ? 'info' : 'warning'">{{ labelOf(STATE_LABELS, row.state) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="当前值" width="140" align="right">
          <template #default="{ row }">{{ valueText(row.current_value) }}</template>
        </el-table-column>
        <el-table-column label="公式值" width="140" align="right">
          <template #default="{ row }">{{ valueText(row.formula_value) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="190">
          <template #default="{ row }">
            <template v-if="actionable(row)">
              <el-button size="small" text type="primary" :disabled="!canEdit" @click="onAdopt([row.addr_id])">采用公式值</el-button>
              <el-button size="small" text :disabled="!canEdit" @click="onLock(row)">
                {{ row.state === 'locked' ? '解锁' : '保持并锁定' }}
              </el-button>
            </template>
            <span v-else class="gt-fp-muted">在附注模块中处理</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 规则清单 -->
    <div class="gt-fp-block">
      <div class="gt-fp-subtitle">推送规则（{{ rules.length }}）</div>
      <el-table :data="rules" size="small" border max-height="360" empty-text="暂无推送规则">
        <el-table-column label="阶段" width="70">
          <template #default="{ row }">{{ labelOf(STAGE_LABELS, row.stage) }}</template>
        </el-table-column>
        <el-table-column label="目标" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ targetText(row) }}</template>
        </el-table-column>
        <el-table-column label="来源公式" min-width="260" show-overflow-tooltip>
          <template #default="{ row }"><code class="gt-fp-mono">{{ row.formula }}</code></template>
        </el-table-column>
        <el-table-column label="写入策略" width="170">
          <template #default="{ row }">{{ labelOf(POLICY_LABELS, row.policy) }}</template>
        </el-table-column>
        <el-table-column label="触发" width="190">
          <template #default="{ row }">{{ triggersText(row.triggers) }}</template>
        </el-table-column>
        <el-table-column label="说明" min-width="220" prop="description" show-overflow-tooltip />
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 公式管理「公式推送」面板（spec chain-closure-phase2-formula-push-engine · 任务 14 · 需求 1.4 / 3.4）。
 *
 * 规则表 / 最近推送 / 待处理差异 / 立即推送（可试跑）/ 采用公式值 / 保持并锁定。
 * 展示逻辑在 `formulaPushView.ts`（纯函数）；本组件只做请求与状态。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import { formulaPush } from '@/services/apiPaths'
import {
  POLICY_LABELS, RUN_STATUS_LABELS, STAGE_LABELS, STATE_LABELS, TRIGGER_LABELS,
  actionable, labelOf, pendingStates, runStatusTag, targetText, triggersText, valueText,
  type PushRuleView, type PushStateView,
} from './formulaPushView'

const props = withDefaults(defineProps<{
  projectId: string
  year: number
  wpCode?: string
  /** 后端已接入的全部底稿编码（用于「全部推送」入口） */
  supportedWpCodes?: string[]
  /** 调用方是否有项目编辑权（无则按钮置灰；后端同样校验） */
  canEdit?: boolean
}>(), { wpCode: 'E1', supportedWpCodes: () => [], canEdit: true })

const rules = ref<PushRuleView[]>([])
const states = ref<PushStateView[]>([])
const latest = ref<any>(null)
const dryRun = ref<any>(null)
const warnings = ref<string[]>([])
const loading = ref(false)
const running = ref<'' | 'run' | 'dry' | 'all'>('')
const error = ref('')
const selectedAddrs = ref<string[]>([])

const pending = computed(() => pendingStates(states.value))
/** 试跑摘要：四类计数与「最近一次推送」同口径（含未变化，否则看不出为何只写入少数几项） */
const dryRunText = computed(() => {
  const d = dryRun.value
  if (!d) return ''
  return `试跑结果：将写入 ${d.written_count ?? 0} 项，未变化 ${d.unchanged_count ?? 0} 项，`
    + `保留 ${d.kept_count ?? 0} 项，跳过 ${d.skipped_count ?? 0} 项（未写入任何数据）`
})
const canRun = computed(() => props.canEdit && !!props.projectId && !!props.year && !running.value)

function detailOf(e: any): string {
  const d = e?.response?.data?.detail ?? e?.response?.data?.message ?? e?.message
  return typeof d === 'string' && d ? d : '请求失败，请稍后重试'
}

async function loadAll(): Promise<void> {
  if (!props.projectId || !props.year) return
  loading.value = true
  error.value = ''
  try {
    const [r, l, s] = await Promise.all([
      api.get(formulaPush.rules(props.projectId), { params: { wp_code: props.wpCode } }),
      api.get(formulaPush.latest(props.projectId), { params: { year: props.year, wp_code: props.wpCode } }),
      api.get(formulaPush.states(props.projectId), { params: { year: props.year, wp_code: props.wpCode } }),
    ])
    rules.value = (r as any)?.rules ?? []
    latest.value = (l as any)?.run ?? null
    warnings.value = latest.value?.detail?.warnings ?? []
    states.value = (s as any)?.states ?? []
  } catch (e) {
    error.value = detailOf(e)
  } finally {
    loading.value = false
  }
}

async function onRun(dry: boolean): Promise<void> {
  running.value = dry ? 'dry' : 'run'
  try {
    const res: any = await api.post(formulaPush.run(props.projectId), {
      year: props.year, dry_run: dry,
      ...(props.wpCode ? { wp_codes: [props.wpCode] } : {}),
    })
    if (dry) {
      dryRun.value = res
      warnings.value = res?.warnings ?? []
      return
    }
    dryRun.value = null
    ElMessage.success(`推送完成：写入 ${res?.written_count ?? 0} 项，保留 ${res?.kept_count ?? 0} 项`)
    await loadAll()
  } catch (e) {
    ElMessage.error(detailOf(e))
  } finally {
    running.value = ''
  }
}

async function onRunAll(): Promise<void> {
  const codes = props.supportedWpCodes
  if (!codes.length) return
  try {
    await ElMessageBox.confirm(
      `将对所有已接入底稿（${codes.join('、')}）执行全量推送。确认？`,
      '全部推送', { confirmButtonText: '确认推送', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  running.value = 'all'
  try {
    const res: any = await api.post(formulaPush.run(props.projectId), { year: props.year, dry_run: false })
    ElMessage.success(`全部推送完成：写入 ${res?.written_count ?? 0} 项，保留 ${res?.kept_count ?? 0} 项`)
    await loadAll()
  } catch (e) {
    ElMessage.error(detailOf(e))
  } finally {
    running.value = ''
  }
}

async function onAdopt(addrIds: string[]): Promise<void> {
  if (!addrIds.length) return
  try {
    await ElMessageBox.confirm(
      `将以当前公式值覆盖 ${addrIds.length} 个目标的现值，并恢复为随公式自动更新。确认采用？`,
      '采用公式值', { confirmButtonText: '采用', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await api.post(formulaPush.adopt(props.projectId), { year: props.year, addr_ids: addrIds })
    ElMessage.success('已采用公式值')
    await loadAll()
  } catch (e) {
    ElMessage.error(detailOf(e))
  }
}

async function onLock(row: PushStateView): Promise<void> {
  const locked = row.state !== 'locked'
  try {
    await api.post(formulaPush.lock(props.projectId), { year: props.year, addr_ids: [row.addr_id], locked })
    ElMessage.success(locked ? '已锁定：后续推送不再覆盖该值' : '已解锁：下次推送重新判定')
    await loadAll()
  } catch (e) {
    ElMessage.error(detailOf(e))
  }
}

function onSelect(rows: PushStateView[]): void {
  selectedAddrs.value = rows.filter(actionable).map((r) => r.addr_id)
}

// ── 运行历史 ──────────────────────────────────────────────────
const runHistory = ref<any[]>([])
const historyLoading = ref(false)
const selectedRunId = ref('')
const outcomeFilter = ref('')
const runItems = ref<any[]>([])
const itemsLoading = ref(false)

function itemOutcomeTag(outcome: string | undefined): string {
  if (!outcome) return 'info'
  if (outcome === 'written' || outcome === 'unchanged') return 'success'
  if (outcome === 'kept') return ''
  if (outcome === 'skipped') return 'warning'
  if (outcome === 'conflict' || outcome === 'failed') return 'danger'
  return 'info'
}

async function loadRunHistory(): Promise<void> {
  if (!props.projectId || !props.year) return
  historyLoading.value = true
  try {
    const res: any = await api.get(formulaPush.runs(props.projectId), {
      params: { year: props.year, limit: 20, offset: 0 },
    })
    runHistory.value = res?.runs ?? []
  } catch {
    runHistory.value = []
  } finally {
    historyLoading.value = false
  }
}

async function loadRunItems(): Promise<void> {
  if (!props.projectId || !selectedRunId.value) return
  itemsLoading.value = true
  try {
    const res: any = await api.get(
      formulaPush.runItems(props.projectId, selectedRunId.value),
      { params: outcomeFilter.value ? { outcome: outcomeFilter.value } : {} },
    )
    runItems.value = res?.items ?? []
  } catch {
    runItems.value = []
  } finally {
    itemsLoading.value = false
  }
}

function onRunSelect(row: any): void {
  selectedRunId.value = row?.run_id || ''
  if (selectedRunId.value) loadRunItems()
}

watch(outcomeFilter, () => { if (selectedRunId.value) loadRunItems() })

onMounted(loadAll)
onMounted(loadRunHistory)
watch(() => [props.projectId, props.year, props.wpCode], loadAll)
watch(() => [props.projectId, props.year, props.wpCode], loadRunHistory)
</script>

<style scoped>
.gt-fp-panel { display: flex; flex-direction: column; gap: 12px; }
.gt-fp-toolbar { display: flex; align-items: center; gap: 8px; }
.gt-fp-title { font-weight: 600; margin-right: auto; }
.gt-fp-block { display: flex; flex-direction: column; gap: 6px; }
.gt-fp-subtitle { font-weight: 600; font-size: var(--gt-font-size-sm); display: flex; align-items: center; gap: 8px; }
.gt-fp-latest { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; font-size: var(--gt-font-size-sm); }
.gt-fp-dry { font-size: var(--gt-font-size-sm); color: var(--gt-color-primary); }
.gt-fp-warnings { margin: 0; padding-left: 18px; font-size: var(--gt-font-size-xs); color: var(--gt-color-warning); }
.gt-fp-muted { color: var(--gt-color-text-secondary); font-size: var(--gt-font-size-xs); }
.gt-fp-mono { font-family: var(--gt-font-family-mono, monospace); font-size: var(--gt-font-size-xs); }
</style>
