<template>
  <el-drawer
    :model-value="visible"
    title="附注就绪度（披露同步 / 校验）"
    size="62%"
    @update:model-value="(v: boolean) => emit('update:visible', v)"
    @open="load"
  >
    <div class="gt-nrp" v-loading="loading">
      <!-- 汇总卡 -->
      <div class="gt-nrp-summary">
        <div class="gt-nrp-stat">
          <div class="gt-nrp-stat-num">{{ summary.total }}</div>
          <div class="gt-nrp-stat-label">附注章节</div>
        </div>
        <div class="gt-nrp-stat" :class="{ warn: summary.empty > 0 }">
          <div class="gt-nrp-stat-num">{{ summary.empty }}</div>
          <div class="gt-nrp-stat-label">无数据</div>
        </div>
        <div class="gt-nrp-stat" :class="{ danger: summary.never_synced > 0 }">
          <div class="gt-nrp-stat-num">{{ summary.never_synced }}</div>
          <div class="gt-nrp-stat-label">未从底稿同步</div>
        </div>
        <el-tooltip placement="top" :content="`定向（关联变更，高置信）${summary.stale_report || 0} · 保守（无关联关系，全量提示）${summary.stale_report_fallback || 0}`">
          <div class="gt-nrp-stat" :class="{ warn: summary.stale > 0 }">
            <div class="gt-nrp-stat-num">{{ summary.stale }}</div>
            <div class="gt-nrp-stat-label">上游已变更</div>
            <div v-if="summary.stale > 0" class="gt-nrp-stat-sub">定向 {{ summary.stale_report || 0 }} / 保守 {{ summary.stale_report_fallback || 0 }}</div>
          </div>
        </el-tooltip>
        <div class="gt-nrp-stat" :class="{ danger: summary.error_sections > 0 }">
          <div class="gt-nrp-stat-num">{{ summary.error_sections }}</div>
          <div class="gt-nrp-stat-label">校验错误</div>
        </div>
        <div class="gt-nrp-stat" :class="{ warn: summary.warning_sections > 0 }">
          <div class="gt-nrp-stat-num">{{ summary.warning_sections }}</div>
          <div class="gt-nrp-stat-label">校验提醒</div>
        </div>
      </div>

      <!-- 公式求值状态（Req 5.2） -->
      <el-alert
        :type="summary.formula_enabled ? 'success' : 'info'"
        :closable="false"
        show-icon
        :title="`公式求值：${summary.formula_enabled ? '已启用' : '未启用'}`"
        :description="summary.formula_enabled ? '本项目附注表内公式（合计/变动恒等式）将自动求值并写入对应单元格。' : '本项目尚未启用表内公式求值，合计/变动恒等式暂不自动计算。可在项目设置中按需开启。'"
        style="margin-bottom: 10px"
      />

      <el-alert
        v-if="!summary.validation_ran"
        type="info"
        :closable="false"
        show-icon
        title="尚未执行过附注校验"
        description="生成 / 刷新 / 底稿同步后会自动校验；也可点工具栏「✅ 校验」手动执行。"
        style="margin-bottom: 10px"
      />
      <el-alert
        v-else-if="summary.validated_at"
        type="success"
        :closable="false"
        show-icon
        :title="`最近校验：${fmtTime(summary.validated_at)}`"
        style="margin-bottom: 10px"
      />

      <!-- 筛选 -->
      <div class="gt-nrp-toolbar">
        <el-radio-group v-model="filterMode" size="small">
          <el-radio-button value="all">全部（{{ sections.length }}）</el-radio-button>
          <el-radio-button value="needs_sync">未同步（{{ counts.needs_sync }}）</el-radio-button>
          <el-radio-button value="empty">无数据（{{ counts.empty }}）</el-radio-button>
          <el-radio-button value="issues">有校验问题（{{ counts.issues }}）</el-radio-button>
          <el-radio-button value="stale">已变更（{{ counts.stale }}）</el-radio-button>
        </el-radio-group>
        <el-button size="small" :loading="loading" @click="load">🔄 刷新</el-button>
      </div>

      <el-table :data="filtered" size="small" border stripe height="calc(100vh - 320px)">
        <el-table-column label="章节" min-width="200">
          <template #default="{ row }">
            <span class="gt-nrp-sec">{{ row.note_section }}</span>
            <span class="gt-nrp-title">{{ row.section_title }}</span>
          </template>
        </el-table-column>
        <el-table-column label="数据" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.has_data" type="success" size="small" round>有</el-tag>
            <el-tag v-else type="info" size="small" round>空</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="对应底稿" width="130">
          <template #default="{ row }">
            <template v-if="row.wp_codes.length">
              <el-tag
                v-for="c in row.wp_codes"
                :key="c"
                size="small"
                :type="row.wp_ids[c] ? 'primary' : 'info'"
                effect="plain"
                class="gt-nrp-wp"
              >{{ c }}</el-tag>
            </template>
            <span v-else class="gt-nrp-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="底稿同步" min-width="170">
          <template #default="{ row }">
            <template v-if="!row.wp_codes.length">
              <span class="gt-nrp-muted">无底稿映射</span>
            </template>
            <template v-else-if="row.last_sync_at">
              <el-tag type="success" size="small" round>已同步</el-tag>
              <span class="gt-nrp-muted">{{ fmtTime(row.last_sync_at) }}</span>
            </template>
            <el-tag v-else type="danger" size="small" round>从未同步</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="上游变更" width="120" align="center">
          <template #default="{ row }">
            <el-tooltip v-if="row.is_stale" :content="staleTip(row.stale_source)" placement="top">
              <el-tag :type="row.stale_source === 'report' ? 'warning' : 'info'" size="small" round>
                {{ row.stale_source === 'report' ? '关联变更' : '待刷新' }}
              </el-tag>
            </el-tooltip>
            <span v-else class="gt-nrp-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="校验" width="110" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.findings.error" type="danger" size="small" round>错误 {{ row.findings.error }}</el-tag>
            <el-tag v-else-if="row.findings.warning" type="warning" size="small" round>提醒 {{ row.findings.warning }}</el-tag>
            <span v-else class="gt-nrp-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" align="center">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="onOpenSection(row)">查看章节</el-button>
            <el-button
              v-if="firstWpId(row)"
              link
              type="primary"
              size="small"
              @click="onOpenWorkpaper(row)"
            >去底稿</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="当前筛选下无章节" :image-size="70" />
        </template>
      </el-table>

      <div class="gt-nrp-hint">
        「从未同步」表示该章节有对应底稿披露表，但从未点过底稿页的「同步到附注」——
        附注表格与说明因此仍是模板/取数结果，未反映底稿披露表的编制成果。
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
/**
 * 附注就绪度看板（附注模块联动复盘 P0-1）
 *
 * 只读呈现：哪些章节应由底稿维护但从未同步、哪些无数据、哪些有校验问题/上游变更，
 * 并提供「查看章节 / 去底稿」两个跳转，把"能力就绪但没人点"变成可行动清单。
 */
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  getDisclosureReadiness,
  type NoteReadinessSection,
  type NoteReadinessSummary,
} from '@/services/commonApi'
import { handleApiError } from '@/utils/errorHandler'

const props = defineProps<{
  visible: boolean
  projectId: string
  year: number
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'select-section', section: string): void
}>()

const router = useRouter()
const loading = ref(false)
const sections = ref<NoteReadinessSection[]>([])
const summary = ref<NoteReadinessSummary>({
  total: 0, with_data: 0, empty: 0, syncable: 0, never_synced: 0,
  stale: 0, stale_report: 0, stale_report_fallback: 0, error_sections: 0, warning_sections: 0,
  validated_at: null, validation_ran: false, formula_enabled: false,
})
const filterMode = ref<'all' | 'needs_sync' | 'empty' | 'issues' | 'stale'>('all')

async function load() {
  if (!props.projectId || !props.year) return
  loading.value = true
  try {
    const data = await getDisclosureReadiness(props.projectId, props.year)
    sections.value = data?.sections || []
    if (data?.summary) summary.value = data.summary
  } catch (err: any) {
    handleApiError(err, '加载附注就绪度')
    sections.value = []
  } finally {
    loading.value = false
  }
}

const counts = computed(() => ({
  needs_sync: sections.value.filter(s => s.needs_sync).length,
  empty: sections.value.filter(s => !s.has_data).length,
  issues: sections.value.filter(s => s.findings.error || s.findings.warning).length,
  stale: sections.value.filter(s => s.is_stale).length,
}))

const filtered = computed(() => {
  switch (filterMode.value) {
    case 'needs_sync': return sections.value.filter(s => s.needs_sync)
    case 'empty': return sections.value.filter(s => !s.has_data)
    case 'issues': return sections.value.filter(s => s.findings.error || s.findings.warning)
    case 'stale': return sections.value.filter(s => s.is_stale)
    default: return sections.value
  }
})

function firstWpId(row: NoteReadinessSection): string | null {
  for (const c of row.wp_codes) {
    if (row.wp_ids?.[c]) return row.wp_ids[c]
  }
  return null
}

function onOpenSection(row: NoteReadinessSection) {
  emit('select-section', row.note_section)
  emit('update:visible', false)
}

function onOpenWorkpaper(row: NoteReadinessSection) {
  const wpId = firstWpId(row)
  if (!wpId) {
    ElMessage.info('该底稿尚未生成，无法跳转')
    return
  }
  router.push({
    name: 'WorkpaperEditor',
    params: { projectId: props.projectId, wpId },
    query: row.wp_sheet ? { sheet: row.wp_sheet } : undefined,
  })
}

function staleTip(source: string | null): string {
  if (source === 'report') return '报表中与本章节存在关联关系的行次发生变更，建议刷新本章节'
  if (source === 'report_fallback') return '报表发生变更（本项目暂无逐章节关联关系，故整体提示）'
  if (source === 'workpaper') return '关联底稿发生变更，建议刷新本章节'
  if (source === 'trial_balance') return '试算表数据发生变更，建议刷新本章节'
  return '上游数据已变更，建议刷新本章节'
}

function fmtTime(iso: string | null): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return iso
  }
}

defineExpose({ load })
</script>

<style scoped>
.gt-nrp { font-size: 13px; }
.gt-nrp-summary {
  display: flex; gap: 10px; margin-bottom: 12px; flex-wrap: wrap;
}
.gt-nrp-stat {
  flex: 1 1 110px; padding: 8px 10px; border-radius: 8px;
  background: var(--el-fill-color-lighter);
  border-left: 3px solid var(--el-color-primary);
}
.gt-nrp-stat.warn { border-left-color: var(--el-color-warning); }
.gt-nrp-stat.danger { border-left-color: var(--el-color-danger); }
.gt-nrp-stat-num { font-size: 18px; font-weight: 600; color: var(--el-text-color-primary); }
.gt-nrp-stat-label { font-size: 12px; color: var(--el-text-color-secondary); }
.gt-nrp-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 8px; gap: 8px; flex-wrap: wrap;
}
.gt-nrp-sec { font-weight: 600; margin-right: 6px; }
.gt-nrp-title { color: var(--el-text-color-regular); }
.gt-nrp-muted { color: var(--el-text-color-secondary); font-size: 12px; margin-left: 4px; }
.gt-nrp-wp { margin-right: 4px; }
.gt-nrp-hint {
  margin-top: 10px; padding: 8px 10px; font-size: 12px; line-height: 1.6;
  color: #78350f; background: #fffbeb; border-left: 4px solid #f59e0b; border-radius: 4px;
}
.gt-nrp :deep(.el-table) { font-size: 13px; }
</style>
