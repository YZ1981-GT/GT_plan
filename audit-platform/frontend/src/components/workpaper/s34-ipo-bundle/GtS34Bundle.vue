<script setup lang="ts">
/**
 * GtS34Bundle — S34 首发审核（IPO）特项底稿聚合组件
 *
 * 将 S34-0 核查事项清单 + S34-1~S34-41 共 41 个专项核查底稿聚合为单一 Bundle，
 * 内部通过分组可滚动 el-tabs 分发渲染各专项核查底稿。
 *
 * 核心特征：
 * - 8 业务主题分组 + 1 overview（核查清单总览面板）
 * - el-tabs type="card" 可滚动，分组标签以小标头区分
 * - overview 恒可见，专项 Tab 仅 wpIdMap 有值时显示（Property 3）
 * - sheetName 路由直接定位到指定 Tab（Property 4）
 * - readonly 模式透传所有子组件（Property 7）
 *
 * 🔴 没有内部 el-tabs（仅此顶级 bundle 有 el-tabs）
 * 🔴 wpIdMap 必须用 item.wp_id 不能用 item.id
 *
 * Spec: .kiro/specs/s34-ipo-review-bundle/
 * Task: 5.1
 * Requirements: 4.1, 4.2, 4.3, 4.6
 */
import { ref, computed, watch, onMounted, provide } from 'vue'
import { useRoute } from 'vue-router'
import { CircleCheckFilled, Loading, RemoveFilled, CloseBold } from '@element-plus/icons-vue'
import { useS34BundleState } from '../composables/useS34BundleState'
import { useS34CrossRef } from './useS34CrossRef'
import { S34_TAB_DEFS, S34_GROUP_NAMES, type TabDef } from './S34_TAB_CONFIG'
import GtAProgramConsole from '../GtAProgramConsole.vue'
import GtS34ChecklistOverview from './GtS34ChecklistOverview.vue'
import GtS34SubCheckTable from './GtS34SubCheckTable.vue'

// ─── Props (Req 1.3) ───
const props = withDefaults(defineProps<{
  wpId: string
  sheetName?: string
  readonly?: boolean
}>(), {
  readonly: false,
})

// ─── Route & State ───
const route = useRoute()
const projectId = computed(() => (route.params.projectId as string) || '')

const {
  wpIdMap,
  checklist,
  applicableCodes,
  completionMap,
  regRefMap,
  progressSummary,
  loading,
  loadWpIndex,
  refreshCompletion,
  loadChecklist,
} = useS34BundleState({ projectId })

// ─── Visible Tabs (Property 3: Tab 可见性由 wp_index 存在性驱动) ───
const visibleTabs = computed<TabDef[]>(() => {
  return S34_TAB_DEFS.filter((tab) => {
    // overview 恒可见
    if (tab.id === 'overview') return true
    // 专项 Tab 仅 wpIdMap 有值时显示
    return tab.wpCode ? !!wpIdMap.value[tab.wpCode] : false
  })
})

/** 可见分组（仅含有可见 Tab 的分组）*/
const visibleGroups = computed(() => {
  const groups: Array<{ group: string; tabs: TabDef[] }> = []
  for (const groupName of S34_GROUP_NAMES) {
    const tabs = visibleTabs.value.filter(
      (t) => t.group === groupName && t.wpCode,
    )
    if (tabs.length > 0) {
      groups.push({ group: groupName, tabs })
    }
  }
  return groups
})

// ─── Active Tab (Property 4: sheetName 路由正确激活 Tab) ───
const activeTab = ref(props.sheetName || 'overview')

// ─── Cross-ref 跨底稿引用导航 (Req 6.1, 6.2, 6.3) ───
const { handleChipClick: handleCrossRefClick } = useS34CrossRef({
  visibleTabs,
  activeTab,
  projectId,
})

// Provide navigate function for child components (GtAProgramConsole chip delegation)
provide('s34-bundle-navigate', (wpCode: string) => {
  handleCrossRefClick(wpCode)
})

// Initialize active tab once visibleTabs are resolved
watch(visibleTabs, (tabs) => {
  if (tabs.length > 0 && !tabs.some(t => t.id === activeTab.value)) {
    activeTab.value = 'overview'
  }
}, { immediate: true })

// Watch props.sheetName changes (Req 7.3)
watch(() => props.sheetName, (newSheet) => {
  if (newSheet && visibleTabs.value.some(t => t.id === newSheet)) {
    activeTab.value = newSheet
  }
  // If sheetName not in visible tabs → keep current (Req 7.4)
})

// Watch route query ?sheet=S34-x (Req 7.2)
watch(() => route.query.sheet as string | undefined, (qs) => {
  if (qs && visibleTabs.value.some(t => t.id === qs)) {
    activeTab.value = qs
  }
})

// ─── Tab change → refresh completion (Req 10.5) ───
watch(activeTab, (_newTab, oldTab) => {
  if (oldTab && oldTab !== _newTab && oldTab !== 'overview') {
    const prevTabDef = S34_TAB_DEFS.find(t => t.id === oldTab)
    if (prevTabDef?.wpCode) {
      refreshCompletion(prevTabDef.wpCode)
    }
  }
})

// ─── 法规溯源上下文区块 (Req 12.2) ───
const activeRegRef = computed(() => {
  const tab = S34_TAB_DEFS.find(t => t.id === activeTab.value)
  if (!tab?.wpCode) return null
  return regRefMap.value[tab.wpCode] || null
})

// ─── 仪表盘计算（Req 10.2, 10.3, 10.4）───
/** 进度条总基数（已完成+进行中+未开始，不含不适用） */
const progressTotal = computed(() =>
  progressSummary.value.completed + progressSummary.value.inProgress + progressSummary.value.notStarted + progressSummary.value.notApplicable,
)

/** 三色进度条百分比（以可统计总数为基准） */
function barPercent(key: 'completed' | 'inProgress' | 'notStarted'): string {
  const total = progressSummary.value.completed + progressSummary.value.inProgress + progressSummary.value.notStarted
  if (total <= 0) return '0%'
  return `${(progressSummary.value[key] / total) * 100}%`
}

// ─── Lifecycle ───
onMounted(async () => {
  await loadWpIndex()
  await loadChecklist()

  // Resolve initial active tab from props or query (Req 7.1, 7.2)
  const qs = route.query.sheet as string | undefined
  const targetSheet = props.sheetName || qs
  if (targetSheet && visibleTabs.value.some(t => t.id === targetSheet)) {
    activeTab.value = targetSheet
  } else if (!visibleTabs.value.some(t => t.id === activeTab.value)) {
    activeTab.value = 'overview'
  }
})
</script>

<template>
  <div class="gt-s34-bundle" v-loading="loading">
    <!-- 空状态：无任何 S34 底稿 (Req 9.4) -->
    <div v-if="!loading && visibleTabs.length <= 1" class="gt-s34-bundle__empty">
      <el-result icon="info" title="本项目未启用首发审核专项底稿">
        <template #sub-title>
          <span>项目底稿索引中未包含 S34 系列底稿，请在底稿管理中确认是否需要启用。</span>
        </template>
      </el-result>
    </div>

    <template v-else>
      <!-- 审计目标 (gold) -->
      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="gt-s34-bundle__objective"
      >
        <template #title>审计目标</template>
        <div class="objective-text">
          对照证监会发行监管问答及沪深北交易所审核规则，对首发上市各专项事项执行核查，评估相关信息披露的充分性与合规性，并形成核查结论。
        </div>
      </el-alert>

      <!-- 编制提示 (gold) -->
      <details class="gt-s34-bundle__prep">
        <summary>编制提示</summary>
        <div class="prep-content">
          先在「核查事项清单」总览确认各事项的适用性与完成进度，不适用项填写理由；点击事项名称可跳转到对应专项底稿；各专项底稿上方展示对应监管条文溯源，据以确定核查范围与依据。
        </div>
      </details>

      <!-- 完成进度仪表盘 (Req 10.2, 10.3, 10.4) -->
      <!-- 联动 overview：点击统计数字跳转到 overview 面板查看详情 -->
      <div class="gt-s34-bundle__dashboard" data-testid="s34-dashboard">
        <div class="dashboard-stats">
          <span
            class="dashboard-stat dashboard-stat--success dashboard-stat--clickable"
            :title="'点击查看已完成底稿详情'"
            @click="activeTab = 'overview'"
          >
            <el-icon :size="14"><CircleCheckFilled /></el-icon>
            <strong>{{ progressSummary.completed }}</strong> 已完成
          </span>
          <span
            class="dashboard-stat dashboard-stat--warning dashboard-stat--clickable"
            :title="'点击查看进行中底稿详情'"
            @click="activeTab = 'overview'"
          >
            <el-icon :size="14"><Loading /></el-icon>
            <strong>{{ progressSummary.inProgress }}</strong> 进行中
          </span>
          <span
            class="dashboard-stat dashboard-stat--info dashboard-stat--clickable"
            :title="'点击查看未开始底稿详情'"
            @click="activeTab = 'overview'"
          >
            <el-icon :size="14"><RemoveFilled /></el-icon>
            <strong>{{ progressSummary.notStarted }}</strong> 未开始
          </span>
          <span
            v-if="progressSummary.notApplicable > 0"
            class="dashboard-stat dashboard-stat--disabled dashboard-stat--clickable"
            :title="'点击查看不适用底稿'"
            @click="activeTab = 'overview'"
          >
            <el-icon :size="14"><CloseBold /></el-icon>
            <s>{{ progressSummary.notApplicable }}</s> 不适用
          </span>
          <span class="dashboard-stat dashboard-stat--total">
            共 {{ progressTotal }} 项
          </span>
        </div>
        <!-- 三色进度条（Req 10.3: 绿=已完成，黄=进行中，灰=未开始） -->
        <div class="dashboard-bar" data-testid="s34-dashboard-bar">
          <div
            class="dashboard-bar__segment dashboard-bar__segment--success"
            :style="{ width: barPercent('completed') }"
            :title="`已完成 ${progressSummary.completed} 项`"
          />
          <div
            class="dashboard-bar__segment dashboard-bar__segment--warning"
            :style="{ width: barPercent('inProgress') }"
            :title="`进行中 ${progressSummary.inProgress} 项`"
          />
          <div
            class="dashboard-bar__segment dashboard-bar__segment--info"
            :style="{ width: barPercent('notStarted') }"
            :title="`未开始 ${progressSummary.notStarted} 项`"
          />
        </div>
      </div>

      <!-- 分组标签导航（el-tabs 上方的分组名提示） -->
      <div class="gt-s34-bundle__group-nav" data-testid="s34-group-nav">
        <span
          v-for="g in visibleGroups"
          :key="g.group"
          class="group-nav__tag"
          :class="{ 'group-nav__tag--active': g.tabs.some(t => t.id === activeTab) }"
        >
          {{ g.group }}（{{ g.tabs.length }}）
        </span>
      </div>

      <!-- el-tabs 可滚动 (Req 4.1, 4.2) -->
      <el-tabs
        v-model="activeTab"
        type="card"
        class="gt-s34-bundle__tabs"
      >
        <el-tab-pane
          v-for="tab in visibleTabs"
          :key="tab.id"
          :label="tab.label"
          :name="tab.id"
          lazy
        >
          <!-- Overview: 核查清单总览面板 (Req 3.1, 3.2, 12.3) -->
          <template v-if="tab.id === 'overview'">
            <GtS34ChecklistOverview
              :checklist="checklist"
              :readonly="props.readonly"
              data-testid="s34-overview"
              @navigate="(wpCode: string) => {
                if (visibleTabs.some(t => t.id === wpCode)) {
                  activeTab = wpCode
                }
              }"
              @update-reason="(wpCode: string, reason: string) => {
                // 不适用理由填写 (Req 9.2) — 当前仅传递事件，持久化由父组件/API处理
              }"
            />
          </template>

          <!-- 专项底稿 Tab: GtAProgramConsole embedded (Req 4.4) -->
          <template v-else>
            <!-- 法规溯源方法论上下文区块 (Req 12.2) -->
            <div
              v-if="tab.wpCode && regRefMap[tab.wpCode]"
              class="gt-s34-bundle__reg-ref"
              data-testid="s34-reg-ref"
            >
              <div class="reg-ref__title">{{ regRefMap[tab.wpCode]?.title }}</div>
              <div class="reg-ref__items">
                <span v-if="regRefMap[tab.wpCode]?.csrc" class="reg-ref__item">
                  证监会：{{ regRefMap[tab.wpCode]!.csrc }}
                </span>
                <span v-if="regRefMap[tab.wpCode]?.sse" class="reg-ref__item">
                  上交所：{{ regRefMap[tab.wpCode]!.sse }}
                </span>
                <span v-if="regRefMap[tab.wpCode]?.szse" class="reg-ref__item">
                  深交所：{{ regRefMap[tab.wpCode]!.szse }}
                </span>
                <span v-if="regRefMap[tab.wpCode]?.bse" class="reg-ref__item">
                  北交所：{{ regRefMap[tab.wpCode]!.bse }}
                </span>
              </div>
            </div>

            <!-- GtAProgramConsole: 专项核查程序表 (Req 4.4, 8.4) -->
            <!-- selfLoad 模式：bundle 内嵌场景 htmlData 为 null，GtAProgramConsole 自动
                 通过 render-config API 加载程序行数据 -->
            <GtAProgramConsole
              v-if="tab.wpCode && wpIdMap[tab.wpCode]"
              :wp-id="wpIdMap[tab.wpCode]"
              :sheet-name="`${tab.wpCode}程序表`"
              :readonly="props.readonly"
              @jump-to-workpaper="handleCrossRefClick"
            />

            <!-- 子检查表切换：含 hasSubTable 的底稿显示子 sheet 分段 (Req 5.1) -->
            <GtS34SubCheckTable
              v-if="tab.hasSubTable && tab.subSheets?.length"
              :wp-id="wpIdMap[tab.wpCode!]"
              :sub-sheets="tab.subSheets"
              :wp-id-map="wpIdMap"
              :project-id="projectId"
              :readonly="props.readonly"
            />
          </template>
        </el-tab-pane>
      </el-tabs>
    </template>
  </div>
</template>

<style scoped>
.gt-s34-bundle {
  padding: var(--gt-space-4, 16px);
}

/* ─── 审计目标 (gold) ─── */
.gt-s34-bundle__objective {
  margin-bottom: 12px;
}
.gt-s34-bundle__objective :deep(.el-alert__title) {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}
.gt-s34-bundle__objective .objective-text {
  font-size: var(--wp-font-size, 13px);
  line-height: 1.6;
}

/* ─── 编制提示 (gold) ─── */
.gt-s34-bundle__prep {
  margin-bottom: 12px;
  border: 1px solid var(--gt-color-border-light, #ebeef5);
  border-radius: var(--gt-radius-sm, 4px);
  background: var(--gt-color-bg-elevated, #fafafa);
}
.gt-s34-bundle__prep summary {
  padding: 8px 12px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: var(--gt-color-text-secondary, #606266);
  cursor: pointer;
  user-select: none;
}
.gt-s34-bundle__prep .prep-content {
  padding: 4px 12px 12px;
  font-size: var(--wp-font-size, 13px);
  line-height: 1.6;
  color: var(--gt-color-text-secondary, #606266);
}

/* ─── Dashboard (Req 10.2, 10.3) ─── */
.gt-s34-bundle__dashboard {
  padding: 10px 16px;
  margin-bottom: 12px;
  background: var(--gt-color-bg-elevated, #fafafa);
  border-radius: var(--gt-radius-sm, 4px);
  border: 1px solid var(--gt-color-border-light, #ebeef5);
  font-size: var(--wp-font-size, 13px);
}

.dashboard-stats {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 8px;
}

.dashboard-stat {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.dashboard-stat--success { color: var(--gt-color-success, #67c23a); font-weight: 500; }
.dashboard-stat--warning { color: var(--gt-color-warning, #e6a23c); font-weight: 500; }
.dashboard-stat--info { color: var(--gt-color-text-tertiary, #909399); }
.dashboard-stat--disabled { color: var(--gt-color-text-placeholder, #c0c4cc); }
.dashboard-stat--total {
  margin-left: auto;
  color: var(--gt-color-text-secondary, #606266);
  font-weight: 500;
}

.dashboard-stat--clickable {
  cursor: pointer;
  border-radius: 4px;
  padding: 2px 6px;
  transition: background-color 0.2s ease;
}
.dashboard-stat--clickable:hover {
  background-color: var(--gt-color-bg-elevated, #f5f7fa);
}

/* 三色进度条 */
.dashboard-bar {
  display: flex;
  height: 6px;
  border-radius: 3px;
  overflow: hidden;
  background: var(--gt-color-border-light, #ebeef5);
}
.dashboard-bar__segment { transition: width 0.3s ease; }
.dashboard-bar__segment--success { background: var(--gt-color-success, #67c23a); }
.dashboard-bar__segment--warning { background: var(--gt-color-warning, #e6a23c); }
.dashboard-bar__segment--info { background: var(--gt-color-text-tertiary, #c0c4cc); }

/* ─── Group Navigation Tags (Req 4.3) ─── */
.gt-s34-bundle__group-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 0;
  margin-bottom: 4px;
}

.group-nav__tag {
  display: inline-block;
  padding: 2px 10px;
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
  background: var(--gt-color-bg-elevated, #f5f7fa);
  border-radius: 10px;
  border: 1px solid var(--gt-color-border-light, #ebeef5);
  transition: all 0.2s ease;
}

.group-nav__tag--active {
  color: var(--gt-color-primary, #409eff);
  background: var(--el-color-primary-light-9, #ecf5ff);
  border-color: var(--el-color-primary-light-7, #c6e2ff);
  font-weight: 500;
}

/* ─── Tabs 可滚动 (Req 4.1, 4.2) ─── */
.gt-s34-bundle__tabs :deep(.el-tabs__nav-scroll) {
  overflow-x: auto;
}
.gt-s34-bundle__tabs :deep(.el-tabs__nav) {
  flex-wrap: nowrap;
}
.gt-s34-bundle__tabs :deep(.el-tabs__header) {
  margin-bottom: 12px;
}

/* ─── RegRef 方法论上下文区块 (Req 12.2) ─── */
.gt-s34-bundle__reg-ref {
  margin-bottom: 12px;
  padding: 10px 14px;
  border-left: 3px solid var(--gt-color-warning, #e6a23c);
  background: #fffbe6;
  border-radius: 0 var(--gt-radius-sm, 4px) var(--gt-radius-sm, 4px) 0;
}

.reg-ref__title {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
  color: var(--gt-color-text-primary, #303133);
  margin-bottom: 6px;
}

.reg-ref__items {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.reg-ref__item {
  font-size: 12px;
  color: var(--gt-color-text-secondary, #606266);
}

/* ─── Empty state ─── */
.gt-s34-bundle__empty {
  padding: 60px 20px;
  text-align: center;
}
</style>
