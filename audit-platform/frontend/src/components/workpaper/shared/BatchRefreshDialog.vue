<script setup lang="ts">
/**
 * BatchRefreshDialog — 批量刷新底稿取数
 *
 * 树数据来自 wp_index（项目经理裁剪后的底稿索引），只显示项目中实际保留的底稿。
 * batch-refresh-workpaper-data spec Task 3
 */
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, FolderOpened, Files, Setting } from '@element-plus/icons-vue'
import { getWpIndex, type WpIndexItem } from '@/services/workpaperApi'
import http from '@/utils/http'

const props = defineProps<{
  projectId: string
  currentWpCode: string
  currentSheets: { name: string; wpCode: string; wpId?: string }[]
  readonly: boolean
}>()

const visible = defineModel<boolean>('visible', { default: false })
const emit = defineEmits<{ done: [] }>()

type RefreshMode = 'current-workbook' | 'all' | 'custom'
const mode = ref<RefreshMode>('current-workbook')

// ─── 裁剪后底稿索引（wp_index）─────────────────────────────────────────
const indexItems = ref<WpIndexItem[]>([])
const loadingList = ref(false)

async function loadIndex() {
  loadingList.value = true
  try {
    indexItems.value = await getWpIndex(props.projectId)
  } catch {
    ElMessage.error('加载底稿索引失败')
  } finally {
    loadingList.value = false
  }
}

watch(visible, (v) => { if (v) loadIndex() })

// ─── 循环分组 ──────────────────────────────────────────────────────────
const CYCLE_LABELS: Record<string, string> = {
  A: '报表/调整', B: '计划', C: '控制测试', D: '销售收入',
  E: '货币资金', F: '采购存货', G: '投资', H: '固定资产',
  I: '无形资产', J: '职工薪酬', K: '管理费用', L: '筹资',
  M: '股东权益', N: '税费', S: '专项',
}
const currentCycle = computed(() => props.currentWpCode?.[0]?.toUpperCase() || '')

function natCmp(a: string, b: string): number {
  return a.localeCompare(b, 'zh', { numeric: true, sensitivity: 'base' })
}

/** 只保留已生成底稿（有 wp_id 的） */
const generatedItems = computed(() => indexItems.value.filter(it => it.wp_id))

// ─── 两级树：cycle → 底稿 ──────────────────────────────────────────
interface TreeNode { id: string; label: string; children?: TreeNode[] }

const treeData = computed<TreeNode[]>(() => {
  const groups = new Map<string, WpIndexItem[]>()
  for (const it of generatedItems.value) {
    const c = (it.audit_cycle || it.wp_code?.[0] || '?').toUpperCase()
    ;(groups.get(c) ?? (groups.set(c, []), groups.get(c)!)).push(it)
  }
  return [...groups.entries()]
    .sort((a, b) => natCmp(a[0], b[0]))
    .map(([cycle, items]) => ({
      id: `cycle-${cycle}`,
      label: `${cycle} ${CYCLE_LABELS[cycle] || '循环'}（${items.length}）`,
      children: items
        .sort((a, b) => natCmp(a.wp_code, b.wp_code))
        .map(it => ({
          id: it.wp_id!,
          label: `${it.wp_code} ${it.wp_name}`,
        })),
    }))
})

const currentCycleCount = computed(() =>
  generatedItems.value.filter(it => (it.audit_cycle || it.wp_code?.[0] || '').toUpperCase() === currentCycle.value).length,
)
const totalCount = computed(() => generatedItems.value.length)

// ─── 勾选 ──────────────────────────────────────────────────────────────
const treeRef = ref<any>(null)
const checkedIds = ref<string[]>([])
function onTreeCheck(_: any, data: any) {
  checkedIds.value = data.checkedKeys.filter((k: string) => !k.startsWith('cycle-'))
}

const selectedWpIds = computed<string[]>(() => {
  if (mode.value === 'current-workbook') {
    return generatedItems.value
      .filter(it => (it.audit_cycle || it.wp_code?.[0] || '').toUpperCase() === currentCycle.value)
      .map(it => it.wp_id!)
  }
  if (mode.value === 'all') return generatedItems.value.map(it => it.wp_id!)
  return checkedIds.value
})
const selectedCount = computed(() => selectedWpIds.value.length)

// ─── 执行 ──────────────────────────────────────────────────────────────
const executing = ref(false)
const progress = ref('')
const resultSummary = ref<{ total: number; success: number; failed: number } | null>(null)

async function doRefresh() {
  const ids = selectedWpIds.value
  if (!ids.length) { ElMessage.warning('请至少选择一张底稿'); return }
  executing.value = true
  progress.value = ''
  resultSummary.value = null
  try {
    const res = await http.post('/api/workpapers/batch-refresh', { project_id: props.projectId, wp_ids: ids })
    const d = res.data?.data ?? res.data ?? {}
    resultSummary.value = { total: d.total ?? ids.length, success: d.success ?? 0, failed: d.failed ?? 0 }
    if (d.failed > 0) {
      progress.value = `${d.success} 成功，${d.failed} 失败`
    } else {
      progress.value = `全部 ${d.total || ids.length} 张底稿刷新完成`
      ElMessage.success(progress.value)
      setTimeout(() => { visible.value = false; emit('done') }, 1200)
    }
  } catch (e: any) {
    progress.value = ''
    ElMessage.error('刷新失败：' + (e?.response?.data?.detail?.message || e?.message || '请稍后重试'))
  } finally {
    executing.value = false
  }
}
</script>

<template>
  <el-dialog
    v-model="visible"
    width="520"
    :close-on-click-modal="!executing"
    :close-on-press-escape="!executing"
    append-to-body
    destroy-on-close
    class="gt-batch-refresh-dialog"
  >
    <template #header>
      <div class="br-header">
        <el-icon :size="20" color="var(--gt-color-primary, #4b2d77)"><Refresh /></el-icon>
        <span class="br-header__title">批量刷新取数</span>
        <el-tag v-if="loadingList" size="small" type="info" effect="plain" round>加载中...</el-tag>
        <el-tag v-else size="small" effect="plain" round>共 {{ totalCount }} 张底稿</el-tag>
      </div>
    </template>

    <div class="br-modes">
      <div class="br-mode-card" :class="{ 'is-active': mode === 'current-workbook' }" @click="mode = 'current-workbook'">
        <el-icon :size="22" class="br-mode-card__icon"><FolderOpened /></el-icon>
        <div class="br-mode-card__body">
          <div class="br-mode-card__name">当前工作簿</div>
          <div class="br-mode-card__desc">{{ currentCycle }} 循环 · {{ currentCycleCount }} 张底稿</div>
        </div>
        <span v-if="mode === 'current-workbook'" class="br-check">✓</span>
      </div>

      <div class="br-mode-card" :class="{ 'is-active': mode === 'all' }" @click="mode = 'all'">
        <el-icon :size="22" class="br-mode-card__icon"><Files /></el-icon>
        <div class="br-mode-card__body">
          <div class="br-mode-card__name">全部底稿</div>
          <div class="br-mode-card__desc">A~S 全部循环 · {{ totalCount }} 张<span class="br-warn-text">（耗时较长）</span></div>
        </div>
        <span v-if="mode === 'all'" class="br-check">✓</span>
      </div>

      <div class="br-mode-card" :class="{ 'is-active': mode === 'custom' }" @click="mode = 'custom'">
        <el-icon :size="22" class="br-mode-card__icon"><Setting /></el-icon>
        <div class="br-mode-card__body">
          <div class="br-mode-card__name">自定义选择</div>
          <div class="br-mode-card__desc">按循环或单张底稿勾选</div>
        </div>
        <span v-if="mode === 'custom'" class="br-check">✓</span>
      </div>
    </div>

    <transition name="el-fade-in">
      <div v-if="mode === 'custom'" class="br-tree-wrap">
        <el-tree
          ref="treeRef"
          :data="treeData"
          :props="{ label: 'label', children: 'children' }"
          show-checkbox
          node-key="id"
          :default-expand-all="false"
          :check-strictly="false"
          @check="onTreeCheck"
        />
      </div>
    </transition>

    <transition name="el-fade-in">
      <div v-if="executing || resultSummary" class="br-progress">
        <el-icon v-if="executing" class="is-loading" :size="16"><Refresh /></el-icon>
        <span>{{ executing ? `正在刷新 ${selectedCount} 张底稿...` : progress }}</span>
        <template v-if="resultSummary && resultSummary.failed > 0">
          <el-tag type="success" size="small" round>{{ resultSummary.success }} 成功</el-tag>
          <el-tag type="danger" size="small" round>{{ resultSummary.failed }} 失败</el-tag>
        </template>
      </div>
    </transition>

    <template #footer>
      <div class="br-footer">
        <el-button @click="visible = false" :disabled="executing">取消</el-button>
        <el-button type="primary" :loading="executing" :disabled="selectedCount === 0 || props.readonly || loadingList" @click="doRefresh">
          <el-icon><Refresh /></el-icon>
          开始刷新{{ selectedCount > 0 ? `（${selectedCount} 张）` : '' }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.br-header { display: flex; align-items: center; gap: 8px; }
.br-header__title { font-size: 16px; font-weight: 600; color: var(--gt-color-text-primary, #303133); }
.br-modes { display: flex; flex-direction: column; gap: 10px; }
.br-mode-card {
  display: flex; align-items: center; gap: 14px;
  padding: 14px 16px; border: 1.5px solid var(--el-border-color-lighter, #ebeef5);
  border-radius: 10px; cursor: pointer; transition: all 0.2s; background: var(--el-bg-color, #fff);
}
.br-mode-card:hover { border-color: var(--gt-color-primary-lighter, #d8b8ee); background: #faf7ff; }
.br-mode-card.is-active {
  border-color: var(--gt-color-primary, #4b2d77);
  background: linear-gradient(135deg, #f9f5ff 0%, #f0ebfa 100%);
  box-shadow: 0 0 0 1px var(--gt-color-primary, #4b2d77) inset;
}
.br-mode-card__icon { flex-shrink: 0; color: var(--gt-color-primary, #4b2d77); opacity: 0.7; }
.br-mode-card.is-active .br-mode-card__icon { opacity: 1; }
.br-mode-card__body { flex: 1; min-width: 0; }
.br-mode-card__name { font-size: 14px; font-weight: 600; color: var(--gt-color-text-primary, #303133); }
.br-mode-card__desc { font-size: 12px; color: var(--gt-color-text-secondary, #909399); margin-top: 2px; }
.br-warn-text { color: var(--el-color-warning, #e6a23c); font-weight: 500; }
.br-check { flex-shrink: 0; color: var(--gt-color-primary, #4b2d77); font-size: 18px; font-weight: 700; }
.br-tree-wrap {
  max-height: 320px; overflow-y: auto;
  border: 1px solid var(--el-border-color-lighter, #ebeef5);
  border-radius: 8px; padding: 8px 4px; margin-top: 12px;
  background: var(--el-fill-color-blank, #fafafa);
}
.br-progress {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 14px; margin-top: 12px;
  background: var(--gt-color-primary-bg, #f9f5ff);
  border: 1px solid var(--gt-color-border-purple-light, #e8ddf5);
  border-radius: 8px; font-size: 13px;
}
.br-footer { display: flex; justify-content: flex-end; gap: 8px; }
</style>
<style>
.gt-batch-refresh-dialog .el-dialog__header { padding: 16px 20px 12px; margin: 0; border-bottom: 1px solid var(--el-border-color-lighter, #ebeef5); }
.gt-batch-refresh-dialog .el-dialog__body { padding: 16px 20px; }
.gt-batch-refresh-dialog .el-dialog__footer { padding: 12px 20px 16px; border-top: 1px solid var(--el-border-color-lighter, #ebeef5); }
.gt-batch-refresh-dialog .el-dialog { border-radius: 12px; overflow: hidden; }
</style>
