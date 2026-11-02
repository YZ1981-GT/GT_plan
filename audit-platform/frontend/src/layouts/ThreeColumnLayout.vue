<template>
  <div class="gt-three-col" :class="{ 'gt-three-col--collapsed': sidebarCollapsed, 'gt-three-col--fullscreen': fullscreen }">
    <!-- 顶部导航栏 -->
    <header class="gt-topbar">
      <div class="gt-topbar-left">
        <div class="gt-logo" @click="sidebarCollapsed = !sidebarCollapsed" title="折叠/展开导航">
          <!-- 顶栏改白底后用深色版 logo。
               ⚠ 命名反直觉：logo-citar-light.png 是「用于浅色背景」的深紫+黑字版，
               而 logo-citar.png 是纯白版（只能用在深色底上）。切勿按文件名对调。 -->
          <img src="/logo-citar-light.png" alt="致同 CITAR" class="gt-logo-img" />
          <!-- logo 文字已清空（品牌更名）：平台名以页面标题呈现，顶栏只留图形标识 -->
          <transition name="gt-fade">
            <span v-if="!sidebarCollapsed" class="gt-logo-text"></span>
          </transition>
        </div>
      </div>
       <!-- <div class="gt-topbar-center">
        <el-breadcrumb separator="/">
          <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
          <el-breadcrumb-item v-if="currentModule">{{ currentModule }}</el-breadcrumb-item>
        </el-breadcrumb> 
      </div>  -->
      <div class="gt-topbar-right">
        <!-- ⛔ 顶栏按钮批量停用（税审 demo）：全局搜索 / 通知铃铛 / 显示设置 /
             四栏切换 / 回收站 / 系统设置 / 导入指示 / AI 助手 / 金额单位 / 暗色切换。
             用 <template v-if="false"> 而非 HTML 注释 —— 这些区块内部本身含注释，
             HTML 注释不可嵌套，内层 会提前闭合导致模板结构损坏。
             恢复时删掉对应的 template 包裹层即可。 -->
        <template v-if="false">
          <!-- 全局搜索（Ctrl+K） -->
          <el-tooltip content="全局搜索 (Ctrl+K)" placement="bottom">
            <span class="gt-topbar-btn" @click="$emit('open-global-search')">
              <el-icon><Search /></el-icon>
            </span>
          </el-tooltip>

          <!-- 通知铃铛 -->
          <slot name="nav-notifications" />

        <!-- 显示设置 Aa -->
        <el-popover placement="bottom" :width="240" trigger="click" :teleported="true">
          <template #reference>
            <div class="gt-topbar-btn" title="显示设置">
              <span class="gt-topbar-text-icon">Aa</span>
            </div>
          </template>
          <div class="gt-display-prefs-panel">
            <div class="gt-dp-row">
              <span class="gt-dp-label">金额单位</span>
              <el-radio-group v-model="displayPrefs.amountUnit" size="small" @change="(v: any) => displayPrefs.setUnit(v)">
                <el-radio-button v-for="opt in displayPrefs.unitOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</el-radio-button>
              </el-radio-group>
            </div>
            <div class="gt-dp-row">
              <span class="gt-dp-label">表格字号</span>
              <el-radio-group v-model="displayPrefs.fontSize" size="small" @change="(v: any) => displayPrefs.setFontSize(v)">
                <el-radio-button v-for="opt in displayPrefs.fontOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</el-radio-button>
              </el-radio-group>
            </div>
            <div class="gt-dp-row">
              <span class="gt-dp-label">小数位数</span>
              <el-radio-group v-model="displayPrefs.decimals" size="small" @change="(v: any) => displayPrefs.setDecimals(v)">
                <el-radio-button :value="0">整数</el-radio-button>
                <el-radio-button :value="2">2位</el-radio-button>
                <el-radio-button :value="4">4位</el-radio-button>
              </el-radio-group>
            </div>
            <div class="gt-dp-row">
              <span class="gt-dp-label">零值显示</span>
              <el-switch v-model="displayPrefs.showZero" size="small" active-text="0.00" inactive-text="—" @change="(v: any) => displayPrefs.setShowZero(v)" />
            </div>
            <div class="gt-dp-row">
              <span class="gt-dp-label">负数红色</span>
              <el-switch v-model="displayPrefs.negativeRed" size="small" @change="(v: any) => displayPrefs.setNegativeRed(v)" />
            </div>
            <div class="gt-dp-row">
              <span class="gt-dp-label">变动高亮</span>
              <el-radio-group v-model="displayPrefs.highlightThreshold" size="small" @change="(v: any) => displayPrefs.setHighlightThreshold(v)">
                <el-radio-button :value="0">关</el-radio-button>
                <el-radio-button :value="0.1">10%</el-radio-button>
                <el-radio-button :value="0.2">20%</el-radio-button>
                <el-radio-button :value="0.5">50%</el-radio-button>
              </el-radio-group>
            </div>
            </div>
          </el-popover>

          <div class="gt-topbar-divider" />

          <!-- 视图切换按钮（三栏/四栏） -->
          <el-tooltip :content="fourColumnMode ? '切换三栏视图' : '切换四栏视图（点击显示附注章节树）'" placement="bottom">
            <div
              class="gt-topbar-btn"
              :class="{ 'gt-topbar-btn--pulse': !fourColumnMode && isConsolNotePage }"
              @click="fourColumnMode = !fourColumnMode"
            >
              <el-icon :size="18"><Grid v-if="!fourColumnMode" /><Menu v-else /></el-icon>
            </div>
          </el-tooltip>
          <el-tooltip content="回收站" placement="bottom">
            <div class="gt-topbar-btn" @click="router.push('/recycle-bin')">
              <el-icon :size="18"><DeleteFilled /></el-icon>
            </div>
          </el-tooltip>
          <el-tooltip content="系统设置" placement="bottom">
            <div class="gt-topbar-btn" @click="router.push('/settings')">
              <el-icon :size="18"><Setting /></el-icon>
            </div>
          </el-tooltip>
        </template>
        <!-- 公式待确认角标 + 弹窗（formula-global-settings-sync R5：进入项目自动弹一次，角标常驻） -->
        <FormulaPendingSyncDialog :project-id="currentProjectId" @resolved="onFormulaSaved" />
        <!-- 后台导入任务指示：已停用（税审 demo）。
             条件置 false 而非删除，保留 bgImportStatus 相关逻辑不动。 -->
        <el-tooltip
          v-if="false && bgImportStatus"
          :content="bgImportStatus.tooltip"
          placement="bottom"
          effect="dark"
        >
          <div
            class="gt-topbar-btn gt-import-indicator"
            :class="`gt-phase-${bgImportStatus.phase}`"
            @click="navigateToImport"
          >
            <el-progress
              type="circle"
              :percentage="bgImportStatus.progress"
              :width="22"
              :stroke-width="3"
              :show-text="false"
              :color="phaseColor"
              :status="bgImportStatus.progress >= 100 ? 'success' : undefined"
              class="gt-import-progress-ring"
            />
            <span class="gt-import-label">{{ bgImportLabel }}</span>
          </div>
        </el-tooltip>

        <div class="gt-topbar-divider" />

        <!-- 复核收件箱入口（reviewer/partner/admin 可见） 
        <slot name="nav-review-inbox" />-->

        <!-- EQCR 独立复核工作台入口（partner/admin 可见，Round 5） 
        <slot name="nav-eqcr" />-->

        <!-- AI 助手快捷入口：已停用（与 DshPanel 折叠态触发按钮一并隐藏） -->
        <template v-if="false">
          <el-tooltip :content="showDshPanel ? '关闭 AI 助手' : '打开 AI 助手'" placement="bottom">
            <el-badge :value="dshUnreadCount" :hidden="dshUnreadCount === 0 || showDshPanel" :max="99" class="gt-dsh-badge">
              <button
                class="gt-topbar-btn"
                :class="{ 'gt-topbar-btn--active': showDshPanel }"
                type="button"
                :aria-label="showDshPanel ? '关闭 AI 助手' : '打开 AI 助手'"
                :aria-expanded="showDshPanel"
                aria-controls="dsh-panel-region"
                @click="showDshPanel = !showDshPanel"
              >
                <el-icon :size="18"><ChatDotSquare /></el-icon>
              </button>
            </el-badge>
          </el-tooltip>
        </template>

        <!-- formula-toolbar Task 5: primary outlet — AI 后、金额单位快捷前 -->
        <WorkpaperPrimaryCapabilitiesHost
          host-instance-id="three-column-primary"
          :owner-epoch="pageCapabilitiesOwnerEpoch"
        >
          <template #page-capabilities-primary>
            <slot name="page-capabilities-primary" />
          </template>
        </WorkpaperPrimaryCapabilitiesHost>

        <!-- 金额单位快捷 / 暗色模式切换：已停用（税审 demo） -->
        <template v-if="false">
          <el-tooltip content="金额单位" placement="bottom">
            <div class="gt-topbar-btn" title="金额单位" aria-label="金额单位">
              <span class="gt-topbar-text-icon">{{ amountUnitShortLabel }}</span>
            </div>
          </el-tooltip>

          <el-tooltip :content="isDark ? '切换到浅色模式' : '切换到暗色模式'" placement="bottom">
            <div class="gt-topbar-btn gt-theme-toggle" @click="toggleTheme">
              <span class="gt-theme-icon">{{ isDark ? '☀️' : '🌙' }}</span>
            </div>
          </el-tooltip>
        </template>

        <!-- 已进入项目：顶栏右侧给「项目列表」「退出登录」两个明按钮（税审 demo 样式）。
             用户名改纯文本展示（不再是头像下拉）—— 下拉里原本只有「退出登录」一项，
             既然已提成明按钮，下拉就没有内容可放了。
             🔴 未进入项目时保留原头像下拉：项目列表页本身没有「返回项目列表」的去处。 -->
        <template v-if="currentProjectId">
          <span class="gt-topbar-user-text">{{ authStore.username }}</span>
          <el-button size="small" @click="router.push('/projects')">项目列表</el-button>
          <el-button size="small" @click="handleLogout">退出登录</el-button>
        </template>
        <!-- 项目列表页（全宽卡片页、无左侧栏）：同样用纯文本用户名 + 明按钮。
             左侧栏隐藏后「账号权限」没有入口了 ⇒ 管理员在顶栏补一个按钮。 -->
        <template v-else-if="route.path === '/projects'">
          <span class="gt-topbar-user-text">{{ authStore.username }}</span>
          <el-button v-if="authStore.user?.role === 'admin'" size="small" @click="router.push('/settings/users')">账号权限</el-button>
          <el-button size="small" @click="handleLogout">退出登录</el-button>
        </template>
        <el-dropdown v-else trigger="click">
          <div class="gt-user-info">
            <el-avatar :size="30" class="gt-avatar">
              {{ (authStore.username || 'U').charAt(0).toUpperCase() }}
            </el-avatar>
            <span class="gt-username">{{ authStore.username }}</span>
            <el-icon :size="12"><ArrowDown /></el-icon>
          </div>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleLogout">
                <el-icon><SwitchButton /></el-icon>退出登录
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </header>

    <!-- 项目信息条：仅在项目上下文内显示（项目名 + 审核年度 + 三个角色） -->
    <ProjectEntryBar :project-id="currentProjectId" />

    <!-- 级联 degraded 状态横幅 [enterprise-linkage 4.8] -->
    <DegradedBanner />

    <!-- 三栏主体 -->
    <div class="gt-body">
      <!-- 左侧栏：1级功能导航 -->
      <!-- 项目内用固定窄栏（环节标签自动折行），不参与折叠与拖拽宽度 -->
      <aside
        v-show="!hideSidebar"
        class="gt-sidebar"
        :class="{ 'gt-sidebar--project': inProjectContext }"
        :style="inProjectContext ? undefined : { width: sidebarCollapsed ? '56px' : sidebarWidth + 'px' }"
        role="navigation"
      >
        <nav class="gt-nav" :class="{ 'gt-nav--project': inProjectContext }">
          <!-- 进入项目后侧栏只剩环节清单（分组标题 + 图标条目）；
               1 级菜单（项目 / 账号权限）与「收起」在项目内一并隐藏 ——
               返回项目列表走顶栏的「项目列表」按钮。
               条目与分组来自 `@/constants/projectStages`（单一真源）。 -->
          <template v-if="inProjectContext">
            <template v-for="group in PROJECT_STAGE_GROUPS" :key="group.key">
              <div class="gt-nav-group-title">{{ group.title }}</div>
              <el-tooltip
                v-for="item in group.items"
                :key="item.key"
                :content="item.pendingReason || ''"
                :disabled="!item.pending"
                placement="right"
              >
                <div
                  class="gt-nav-item gt-nav-item--stage"
                  :class="{
                    'gt-nav-item--active': activeProjectSubNav === item.key,
                    'gt-nav-item--pending': item.pending,
                  }"
                  @click="onProjectStageClick(item)"
                  :title="item.pending ? '' : item.label"
                >
                  <el-icon :size="17"><component :is="item.icon" /></el-icon>
                  <span class="gt-nav-stage-label">{{ item.label }}</span>
                  <span v-if="item.key === TAX_WORKPAPER_STAGE_KEY" class="gt-nav-stage-caret">{{ taxWpSubnavOpen ? '▾' : '▸' }}</span>
                </div>
              </el-tooltip>
            </template>
          </template>
          <template v-else v-for="item in navItems" :key="item.key">
            <div
              class="gt-nav-item"
              :class="{ 'gt-nav-item--active': activeNav === item.key }"
              @click="onNavClick(item)"
              :title="item.label"
            >
              <el-icon :size="20"><component :is="item.icon" /></el-icon>
              <transition name="gt-fade">
                <span v-if="!sidebarCollapsed" class="gt-nav-label">
                  {{ item.label }}
                  <span v-if="item.maturity === 'pilot'" class="gt-maturity-badge gt-maturity-pilot">试点</span>
                  <span v-else-if="item.maturity === 'experimental'" class="gt-maturity-badge gt-maturity-exp">实验</span>
                  <span v-else-if="item.maturity === 'developing'" class="gt-maturity-badge gt-maturity-dev">📌 即将上线</span>
                </span>
              </transition>
            </div>
          </template>
          <!-- ⛔「公式管理」「高级查询」菜单已隐藏（税审 demo）。
               两者都是弹窗触发而非路由，弹窗组件本身保留在下方（仍可由其他入口/
               eventBus 'open-formula-manager' 唤起），这里只摘掉侧栏入口。
               用 <template v-if="false"> 而非 HTML 注释：区块内部含注释，注释不可嵌套。 -->
          <template v-if="false">
            <!-- 公式管理（弹窗触发，非路由） -->
            <div class="gt-nav-item" @click="onOpenFormulaEvent()" title="公式管理">
              <span class="gt-tool-text-icon" style="font-style:italic;font-weight:700;width:20px;text-align:center;display:inline-block">ƒx</span>
              <transition name="gt-fade">
                <span v-if="!sidebarCollapsed" class="gt-nav-label">公式管理</span>
              </transition>
            </div>
            <!-- 高级查询（弹窗触发，非路由） -->
            <div class="gt-nav-item" @click="showCustomQuery = true" title="高级查询">
              <el-icon :size="20"><Search /></el-icon>
              <transition name="gt-fade">
                <span v-if="!sidebarCollapsed" class="gt-nav-label">高级查询</span>
              </transition>
            </div>
          </template>
          <!-- 收起（项目内隐藏：环节清单是固定宽度窄栏，不提供折叠） -->
          <div v-if="!inProjectContext" class="gt-nav-item" @click="sidebarCollapsed = !sidebarCollapsed" title="折叠">
            <el-icon :size="20"><DArrowLeft v-if="!sidebarCollapsed" /><DArrowRight v-else /></el-icon>
            <transition name="gt-fade">
              <span v-if="!sidebarCollapsed" class="gt-nav-label">收起</span>
            </transition>
          </div>
        </nav>
      </aside>

      <!-- 税审底稿二级栏「底稿目录」：与一级栏并排（CITAR ProjectShell 版式），只在税审底稿展开时出现 -->
      <TaxWorkpaperSubnav v-if="inProjectContext && !hideSidebar && taxWpSubnavOpen" />

      <!-- 左侧拖拽分隔线（始终显示，用于调整左侧栏宽度） -->
      <!-- 左拖拽分隔线：侧栏隐藏时一并隐藏，否则会留下一条无对应栏位的竖线 -->
      <!-- 项目内侧栏是固定宽度，拖拽线一并隐藏（否则拖了没反应） -->
      <div
        v-if="!sidebarCollapsed && !hideSidebar && !inProjectContext"
        class="gt-resizer"
        @mousedown="startResize('left', $event)"
      />

      <!-- 中间栏：2级内容 -->
      <section v-if="!props.hideMiddle && !middleCollapsed" class="gt-middle" :style="{ width: middleWidth + 'px' }" role="main">
        <div class="gt-middle-content">
          <slot name="middle">
            <router-view name="middle" />
          </slot>
        </div>
        <div class="gt-middle-bottom">
          <div class="gt-nav-item" @click="middleCollapsed = true" title="收起列表">
            <el-icon :size="18"><DArrowLeft /></el-icon>
            <span class="gt-nav-label">收起</span>
          </div>
        </div>
      </section>
      <!-- 中间栏收起态 -->
      <div
        v-if="!props.hideMiddle && middleCollapsed"
        class="gt-middle-collapsed"
        @click="middleCollapsed = false"
        title="展开项目列表"
      >
        <div class="gt-middle-collapsed-icon">
          <el-icon :size="18"><DArrowRight /></el-icon>
        </div>
      </div>

      <!-- 右侧拖拽分隔线 -->
      <div v-if="!props.hideMiddle && !middleCollapsed" class="gt-resizer" @mousedown="startResize('right', $event)" />

      <!-- 第3栏：功能目录（四栏模式下显示） -->
      <section
        v-if="fourColumnMode && !catalogCollapsed"
        class="gt-catalog"
        :style="{ width: catalogWidth + 'px' }"
      >
        <slot name="catalog" />
        <div class="gt-catalog-bottom">
          <div class="gt-nav-item" @click="catalogCollapsed = true" title="收起">
            <el-icon :size="18"><DArrowLeft /></el-icon>
            <span class="gt-nav-label">收起</span>
          </div>
        </div>
      </section>
      <!-- 第3栏收起态 -->
      <div
        v-if="fourColumnMode && catalogCollapsed"
        class="gt-catalog-collapsed"
        @click="catalogCollapsed = false"
        title="展开功能目录"
      >
        <div class="gt-catalog-collapsed-icon">
          <el-icon :size="18"><DArrowRight /></el-icon>
        </div>
      </div>

      <!-- 第3/4栏分隔线 -->
      <div v-if="fourColumnMode && !catalogCollapsed" class="gt-resizer" @mousedown="startResize('catalog', $event)" />

      <!-- 右侧栏：项目详情 / 主内容区 -->
      <section class="gt-detail" :role="props.hideMiddle ? 'main' : 'complementary'">
        <slot name="detail">
          <router-view name="detail" />
        </slot>
      </section>

      <!-- AI 助手面板（dsh） -->
      <DshPanel v-model="showDshPanel" @message-count="onDshMessageCount" />
    </div>

    <!-- 全局公式管理弹窗 -->
    <FormulaManagerDialog
      v-model="showFormulaManager"
      :rows="[]"
      :project-id="formulaContext?.projectId ?? currentProjectId"
      :year="formulaContext?.year ?? currentYear"
      :scope="formulaContext?.scope ?? 'report'"
      :wp-id="formulaContext?.wpId"
      :wp-code="formulaContext?.wpCode"
      :sheet-name="formulaContext?.sheetName"
      :host-sheet-codes="formulaContext?.sheetCodes"
      :template-type="formulaContext?.templateType"
      :note-section="formulaContext?.noteSection"
      :note-section-title="formulaContext?.noteSectionTitle"
      :initial-report-type="formulaContext?.initialReportType"
      :canonical-location="formulaContext?.canonicalLocation"
      :capability-snapshot="formulaContext?.capabilitySnapshot"
      :formula-session="formulaContext?.formulaSession"
      :read-only="formulaContext?.readOnly ?? false"
      @session-change="onFormulaSessionChange"
      @saved="onFormulaSaved"
      @applied="onFormulaApplied"
    />

    <!-- 全局一键刷新弹窗（formula-runtime-convergence Task 16） -->
    <GtRefreshScopeDialog
      :project-id="currentProjectId"
      :year="currentYear"
      @refresh-complete="onRefreshComplete"
    />

    <!-- 全局自定义查询弹窗 -->
    <CustomQueryDialog
      v-model="showCustomQuery"
      :project-id="currentProjectId"
      :year="currentYear"
      :initial-tab="customQueryInitialTab"
      :initial-source="customQueryInitialSource"
    />

    <!-- 全局快捷键帮助面板 [R7-S2-12] -->
    <ShortcutHelpDialog v-model="showShortcutHelp" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, provide } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { useRoleContextStore } from '@/stores/roleContext'
import { useTheme } from '@/composables/useTheme'
import { ElMessage, ElNotification } from 'element-plus'
import { api } from '@/services/apiProxy'
import {
  Odometer, FolderOpened, User, Reading, Timer, Connection,
  Stamp, Box, Setting, ArrowDown, SwitchButton,
  DArrowLeft, DArrowRight, Cpu, DeleteFilled, Grid, Menu, Paperclip,
  DataAnalysis, UserFilled, ChatDotSquare, Suitcase, Loading,
  Search,
  // 原项目子菜单的 6 个图标（Upload / Grid / Edit / Notebook / TrendCharts / Document）
  // 与「查账窗口」的 CopyDocument 已不再引用：项目内侧栏改纯文字环节清单。
  // Grid 仍保留 —— 四栏切换按钮在用。
} from '@element-plus/icons-vue'
import FormulaManagerDialog from '@/components/formula/FormulaManagerDialog.vue'
import GtRefreshScopeDialog from '@/components/formula/GtRefreshScopeDialog.vue'
import FormulaPendingSyncDialog from '@/components/formula/settings/FormulaPendingSyncDialog.vue'
import CustomQueryDialog from '@/components/query/CustomQueryDialog.vue'
import ShortcutHelpDialog from '@/components/common/ShortcutHelpDialog.vue'
import DshPanel from '@/components/ai/DshPanel.vue'
import WorkpaperPrimaryCapabilitiesHost from '@/shell/formula/WorkpaperPrimaryCapabilitiesHost.vue'
import {
  legacyPayloadToPartialCommand,
  type FormulaManagerSession,
} from '@/shell/formula/openFormulaManagerCommand'
import {
  receiveFormulaManagerOpen,
  receiveFormulaManagerSession,
  type FormulaManagerContextOwnerState,
} from '@/shell/formula/formulaManagerContextOwner'
import { DSH_ASSIST_BRIDGE_KEY, type DshAssistBridge } from '@/shell/formula/dshAssistBridge'
import { eventBus, type SyncEventPayload, type OpenFormulaManagerPayload, type FourColSwitchPayload } from '@/utils/eventBus'
import { reportActiveTab } from '@/composables/reportActiveTab'
import { operationHistory } from '@/utils/operationHistory'
import { openLedgerWindow } from '@/utils/openLedgerWindow'
import { subscribeProjectEvent, WILDCARD_EVENT, type ProjectEventSubscription } from '@/services/sse/projectEventStream'
import DegradedBanner from '@/components/DegradedBanner.vue'
import ProjectEntryBar from '@/components/layout/ProjectEntryBar.vue'
import TaxWorkpaperSubnav from '@/components/layout/TaxWorkpaperSubnav.vue'
import {
  PROJECT_STAGES, PROJECT_STAGE_GROUPS, TAX_WORKPAPER_STAGE_KEY, type ProjectStage,
} from '@/constants/projectStages'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const displayPrefs = useDisplayPrefsStore()
const { isDark, toggle: toggleTheme } = useTheme()

/** formula-toolbar Task 5 — primary outlet owner epoch (bumped on workpaper route change). */
const pageCapabilitiesOwnerEpoch = ref(1)
const amountUnitShortLabel = computed(() => {
  const unit = displayPrefs.amountUnit
  if (unit === 'wan') return '万'
  if (unit === 'qian') return '千'
  return '元'
})

watch(
  () => route.path,
  (path) => {
    if (path.includes('/workpapers') || path.includes('/workpaper')) {
      pageCapabilitiesOwnerEpoch.value += 1
    }
  },
)

// ── Props ──
const props = defineProps<{
  hideMiddle?: boolean
  fourColumn?: boolean
  catalogTitle?: string
  /**
   * 隐藏左侧 1 级功能导航栏。
   * 展示项目详情时由 DefaultLayout 下发（浏览模式 + 非四栏 + 已选中项目），
   * 让详情面板获得完整横向空间。
   * 🔴 用 v-show 而非 CSS 写死 display:none —— 写死会连带破坏响应式断点里的
   * .gt-sidebar 规则（移动端横向导航），且无法按场景恢复。
   */
  hideSidebar?: boolean
}>()

// ── 导航项（R7-S2-01：角色感知动态化） ──
const roleStore = useRoleContextStore()

/**
 * 左侧 1 级导航。
 * 税审 demo 只保留「项目」与「账号权限」两项，其余（仪表盘/人员档案/工时/看板/
 * 合并/函证/归档/附件/模板库/全局公式/知识库/私人库/AI 模型）已移除。
 * 🔴 「账号权限」保留 roles:['admin'] 限制 —— 它是用户与权限管理入口，
 *    放开给全角色等于把账号管理暴露给所有登录用户。
 */
const FALLBACK_NAV = [
  { key: 'projects', label: '项目', icon: FolderOpened, path: '/projects', maturity: 'production', roles: null },
  { key: 'users', label: '账号权限', icon: UserFilled, path: '/settings/users', maturity: 'production', roles: ['admin'] },
]

/**
 * 按角色过滤（roles=null 表示所有角色可见）。
 * 原先还按角色覆盖「看板」路径（manager/partner 各自仪表盘），该菜单已移除故一并删去。
 */
function buildNavForRole(nav: typeof FALLBACK_NAV, role: string) {
  return nav.filter(item => !item.roles || item.roles.includes(role))
}

// 原「合并菜单条件显示」探测（group-tree-architecture Task 17.1）已随「合并」菜单一并移除：
// 它每次布局挂载都要 GET /api/projects/tree?scope=consolidated 来决定是否显示该菜单，
// 菜单移除后这个请求纯属浪费。恢复「合并」菜单时需同时恢复该探测。

const navItems = computed(() =>
  buildNavForRole(FALLBACK_NAV, roleStore.effectiveRole || 'auditor'),
)

/**
 * 是否在项目上下文内（路由带 projectId）。
 * 为真时：左侧栏只显示环节清单（固定窄栏）、顶栏右侧换成「项目列表 / 退出登录」。
 */
const inProjectContext = computed(() => !!(route.params.projectId as string))

/**
 * 当前命中的环节 key（空串 = 未命中）。
 *
 * 🔴 按**路由名**匹配，不按路径前缀。
 *    原先用 `path.startsWith(item.path)`：`/trial-balance` 是 `/t...` 这类更长路径的
 *    前缀时会多命中；而现在两个条目可以指向同一路由（如报表页与报表内页签），
 *    路径前缀法无法区分。路由名是 vue-router 给的唯一标识，稳得多。
 */
const activeProjectSubNav = computed(() => {
  const current = route.name
  if (!current) return ''
  const sameRoute = PROJECT_STAGES.filter(s => s.routeName && s.routeName === current)
  // 同一路由挂了多个条目（「审定报表」与「报表分析」都是 Reports）时按页签区分 ——
  // 否则两项会同时高亮。页签取值：报表页已挂载时用它公布的**实际**页签（页内点页签不改 URL，
  // URL 上的 tab 会过期），未挂载才退回 URL。
  const tabNow = current === 'Reports' && reportActiveTab.value != null
    ? reportActiveTab.value
    : String(route.query.tab ?? '')
  const exact = sameRoute.find(s => s.query && Object.entries(s.query).every(
    ([k, v]) => (k === 'tab' ? tabNow : String(route.query[k] ?? '')) === v,
  ))
  return (exact || sameRoute.find(s => !s.query))?.key || ''
})

/**
 * 税审底稿二级栏是否展开。进入税审底稿页即展开、离开即收起
 * （切到其他环节后内容区才能用满宽度）；在本页内再点环节只切换显隐。
 */
const taxWpSubnavOpen = ref(false)
const taxWpRouteName = PROJECT_STAGES.find(s => s.key === TAX_WORKPAPER_STAGE_KEY)?.routeName
watch(() => route.name, (name, prev) => {
  const onPage = !!taxWpRouteName && name === taxWpRouteName
  if (onPage !== (!!taxWpRouteName && prev === taxWpRouteName)) taxWpSubnavOpen.value = onPage
}, { immediate: true })

/**
 * 环节点击：跳到该环节的具名路由，带上当前年度
 * （与 DetailProjectPanel 的 goTo 口径一致，漏传会让目标页退回自然年）。
 *
 * pending 条目（无 routeName）不跳转 —— 它们没有页面，跳过去就是白屏。
 */
function onProjectStageClick(item: ProjectStage) {
  if (item.pending || !item.routeName) return
  const pid = (route.params.projectId as string) || ''
  if (!pid) return
  // 已在税审底稿页再点「税审底稿」：只收起 / 展开二级栏，不重新跳转（CITAR 同口径）
  if (item.key === TAX_WORKPAPER_STAGE_KEY && route.name === item.routeName) {
    taxWpSubnavOpen.value = !taxWpSubnavOpen.value
    return
  }
  const year = route.query.year ? String(route.query.year) : undefined
  const query: Record<string, string> = { ...(year ? { year } : {}), ...(item.query || {}) }

  // 已停在报表页时点「审定报表」/「报表分析」：只是换页签 —— 原地切，不重新导航。
  // 🔴 不能改 URL：DefaultLayout 按 fullPath 给页面组件加 key，改 query（哪怕 replace）
  //    都会整页重建、筛选与滚动全丢。只发事件，由 ReportView 自己切页签；
  //    菜单高亮读 ReportView 公布的实际页签（reportActiveTab），不依赖 URL。
  //    空 tab ⇒ ReportView 回落到默认页签（资产负债表）＝「审定报表」。
  if (item.routeName === 'Reports' && route.name === 'Reports') {
    eventBus.emit('report:switch-tab', { projectId: pid, tab: item.query?.tab ?? '' })
    return
  }

  router.push({ name: item.routeName, params: { projectId: pid }, query })
}

const activeNav = computed(() => {
  const p = route.path
  // 「仪表盘」菜单已移除，根路径按项目高亮（登录后也统一落在项目页）
  if (p === '/') return 'projects'
  // 顶部栏路由不高亮左侧导航
  const topBarPaths = ['/recycle-bin', '/settings']
  if (topBarPaths.some(tp => p === tp || (tp !== '/settings' && p.startsWith(tp)))) return ''
  // 原先 /projects/:id/consolidation 高亮「合并」菜单；该菜单已移除，
  // 现按下方通用前缀匹配归入「项目」（否则该页面左侧无任何高亮）。
  for (const item of navItems.value) {
    if (item.path !== '/' && p.startsWith(item.path)) return item.key
  }
  // 兜底按项目高亮（左侧只剩项目与账号权限两项，未命中账号权限即项目）
  return 'projects'
})

const currentModule = computed(() => {
  const item = navItems.value.find(n => n.key === activeNav.value)
  return item?.label || ''
})

// 工具区 active 判断
const activeToolPath = computed(() => {
  const p = route.path
  const toolPaths = ['/knowledge', '/private-storage', '/settings/ai-models', '/settings/report-format', '/forum']
  return toolPaths.find(tp => p.startsWith(tp)) || ''
})

const emit = defineEmits<{
  (e: 'nav-change', key: string): void
  (e: 'view-change', mode: 'three' | 'four'): void
  (e: 'open-global-search'): void
}>()

function onNavClick(item: (typeof FALLBACK_NAV)[0]) {
  emit('nav-change', item.key)
  router.push(item.path)
}

// ── 布局状态 ──
const STORAGE_KEY = 'gt-layout-prefs'
const sidebarCollapsed = ref(false)
const sidebarWidth = ref(220)
const middleWidth = ref(340)
const middleCollapsed = ref(false)
const showDshPanel = ref(false)
const dshUnreadCount = ref(0)

const dshAssistBridge: DshAssistBridge = {
  isOpen: showDshPanel,
  open: () => {
    showDshPanel.value = true
  },
  close: (_options: { preserveDraft: boolean }) => {
    showDshPanel.value = false
  },
}
provide(DSH_ASSIST_BRIDGE_KEY, dshAssistBridge)

function onDshMessageCount(count: number) {
  dshUnreadCount.value = count
}
const catalogWidth = ref(280)
const catalogCollapsed = ref(false)
const fourColumnMode = ref(false)

/** 当前是否在合并附注页面——用于四栏切换按钮的脉冲提示 */
const isConsolNotePage = computed(() =>
  route.path.match(/^\/projects\/[^/]+\/consolidation/) != null
  && !fourColumnMode.value
)
const fullscreen = ref(false)
const showFormulaManager = ref(false)
const formulaOwnerState = ref<FormulaManagerContextOwnerState>({})
const formulaContext = computed(() => formulaOwnerState.value.active)
const showCustomQuery = ref(false)
const customQueryInitialTab = ref<'basic' | 'advanced'>('basic')
const customQueryInitialSource = ref<string | undefined>(undefined)
const showShortcutHelp = ref(false)
const currentProjectId = computed(() => (route.params.projectId as string) || '')
const currentYear = computed(() => Number(route.query.year) || new Date().getFullYear() - 1)

// 四栏模式由 props 或用户切换控制
watch(() => props.fourColumn, (v) => {
  if (v !== undefined) fourColumnMode.value = v
}, { immediate: true })

// 视图模式变化时通知父组件
watch(fourColumnMode, (v) => {
  if (v) catalogCollapsed.value = false  // 切换到四栏时自动展开 catalog
  emit('view-change', v ? 'four' : 'three')
})

// 监听折叠状态变化自动保存
watch([sidebarCollapsed, middleCollapsed, catalogCollapsed], () => savePrefs())

function loadPrefs() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const prefs = JSON.parse(raw)
      sidebarCollapsed.value = prefs.collapsed ?? false
      sidebarWidth.value = prefs.sidebarWidth ?? 220
      middleWidth.value = prefs.middleWidth ?? 340
      middleCollapsed.value = prefs.middleCollapsed ?? false
      catalogWidth.value = prefs.catalogWidth ?? 280
      catalogCollapsed.value = prefs.catalogCollapsed ?? false
    }
  } catch { /* ignore */ }
}

function savePrefs() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({
    collapsed: sidebarCollapsed.value,
    sidebarWidth: sidebarWidth.value,
    middleWidth: middleWidth.value,
    middleCollapsed: middleCollapsed.value,
    catalogWidth: catalogWidth.value,
    catalogCollapsed: catalogCollapsed.value,
  }))
}

// ── 拖拽调整宽度 ──
let resizing: 'left' | 'right' | 'catalog' | null = null
let startX = 0
let startW = 0

function startResize(side: 'left' | 'right' | 'catalog', e: MouseEvent) {
  resizing = side
  startX = e.clientX
  startW = side === 'left' ? sidebarWidth.value : side === 'right' ? middleWidth.value : catalogWidth.value
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  document.addEventListener('mousemove', onResize)
  document.addEventListener('mouseup', stopResize)
}

function onResize(e: MouseEvent) {
  if (!resizing) return
  const dx = e.clientX - startX
  if (resizing === 'left') {
    sidebarWidth.value = Math.max(180, Math.min(300, startW + dx))
  } else if (resizing === 'right') {
    middleWidth.value = Math.max(250, Math.min(500, startW + dx))
  } else if (resizing === 'catalog') {
    catalogWidth.value = Math.max(200, Math.min(450, startW + dx))
  }
}

function stopResize() {
  resizing = null
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  document.removeEventListener('mousemove', onResize)
  document.removeEventListener('mouseup', stopResize)
  savePrefs()
}

// ── 键盘快捷键 ──
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && fullscreen.value) {
    fullscreen.value = false
  }
}

// ── 移动端手势支持 ──
let touchStartX = 0
let touchStartY = 0
const SWIPE_THRESHOLD = 60

function onTouchStart(e: TouchEvent) {
  const touch = e.touches[0]
  touchStartX = touch.clientX
  touchStartY = touch.clientY
}

function onTouchEnd(e: TouchEvent) {
  const touch = e.changedTouches[0]
  const dx = touch.clientX - touchStartX
  const dy = touch.clientY - touchStartY

  // 只处理水平滑动（水平位移 > 垂直位移）
  if (Math.abs(dx) < SWIPE_THRESHOLD || Math.abs(dx) < Math.abs(dy)) return

  if (dx > 0) {
    // 右滑：展开导航
    sidebarCollapsed.value = false
  } else {
    // 左滑：收起导航
    sidebarCollapsed.value = true
  }
}

// ── 后台导入任务全局轮询 ──
// 状态模型（不直接用 route.params.projectId 作为 "追踪中 project"——
// 用户转后台后切到其他项目，原项目导入仍应被追踪直到结束）
interface BgImportStatus {
  projectId: string
  phase: string          // 来自 job.current_phase：bootstrap/parsing/validating/writing/activating/completed
  progress: number       // 0-100
  message: string        // 当前阶段人类可读消息
  tooltip: string        // 鼠标悬停完整信息
}
const bgImportStatus = ref<BgImportStatus | null>(null)
let importPollTimer: ReturnType<typeof setInterval> | null = null
/** 当前被追踪的 projectId（独立于路由，支持跨项目保留导入指示） */
const trackedProjectId = ref<string | null>(null)
/** 连续轮询错误计数——连续 6 次错误自动释放追踪（30s = 6 × 5s 轮询间隔） */
let pollErrorCount = 0
const MAX_POLL_ERRORS = 6

const PHASE_LABEL: Record<string, string> = {
  bootstrap: '启动',
  parsing: '解析',
  validating: '校验',
  writing: '写入',
  activating: '激活',
  completed: '完成',
  failed: '失败',
  canceled: '已取消',
  pending: '排队',
  queued: '排队',
}

const bgImportLabel = computed(() => {
  if (!bgImportStatus.value) return ''
  return `${bgImportStatus.value.progress}%`
})

// P3-3.2: 按阶段着色（解析蓝 / 校验橙 / 写入紫 / 激活绿）
// 注：completed 状态下 bgImportStatus 会被清空，指示器消失，
// 所以这里不需要包含 completed 颜色
const PHASE_COLORS: Record<string, string> = {
  bootstrap: '#909399',
  queued: '#909399',
  pending: '#909399',
  parsing: '#409eff',
  validating: '#e6a23c',
  writing: '#a855f7',
  activating: '#67c23a',
}

const phaseColor = computed(() => {
  if (!bgImportStatus.value) return '#409eff'
  return PHASE_COLORS[bgImportStatus.value.phase] || '#409eff'
})

async function pollImportQueue() {
  // 优先追踪 trackedProjectId；若无则回退到当前路由项目
  const trackId = trackedProjectId.value || (route.params.projectId as string)
  if (!trackId) {
    bgImportStatus.value = null
    return
  }
  try {
    const statusData: any = await api.get(
      `/api/projects/${trackId}/ledger-import/active-job`,
      { validateStatus: (s: number) => s < 600 },
    )
    pollErrorCount = 0  // 成功响应重置错误计数
    const status = statusData
    if (status && status.status === 'processing') {
      const phase = status.phase || status.current_phase || 'writing'
      const pct = status.progress ?? 0
      const phaseLabel = PHASE_LABEL[phase] || phase
      const msg = status.message || `${phaseLabel}中`
      // P3-5.5: 展示剩余耗时估算（上限 1 小时，超过不显示）
      const eta = status.estimated_remaining_seconds as number | null | undefined
      const etaText = typeof eta === 'number' && eta > 0 && eta <= 3600
        ? (eta < 60 ? `约 ${eta} 秒` : `约 ${Math.round(eta / 60)} 分钟`)
        : ''
      const tooltipLines = [
        `导入进行中 · ${phaseLabel} · ${pct}%`,
        msg,
      ]
      if (etaText) tooltipLines.push(`预计剩余 ${etaText}`)
      tooltipLines.push('点击跳转查看详情')
      bgImportStatus.value = {
        projectId: trackId,
        phase,
        progress: pct,
        message: msg,
        tooltip: tooltipLines.join('\n'),
      }
      // 第一次发现正在处理的 job → 记录为追踪对象
      if (!trackedProjectId.value) {
        trackedProjectId.value = trackId
      }
    } else if (bgImportStatus.value) {
      const prev = bgImportStatus.value
      bgImportStatus.value = null
      trackedProjectId.value = null
      // P3: toast 带 year 和 project 片段，便于用户识别是哪个任务完成
      const yr = status?.year ? `${status.year} 年度` : ''
      const finishedLabel = yr ? `（${yr}）` : ''
      // P2-1.2: 显式处理 canceled 状态
      if (status?.status === 'canceled' || status?.status === 'timed_out') {
        ElMessage.warning({
          message: `${status?.message || '导入已取消'}${finishedLabel}`,
          duration: 4000,
        })
      } else if (status?.status === 'failed') {
        ElNotification({
          title: '导入失败',
          message: `${status?.message || '后台导入失败'}${finishedLabel}，点击顶栏可查看历史`,
          type: 'error',
          duration: 6000,
        })
      } else {
        ElMessage.success({
          message: `${status?.message || '后台导入已完成'}${finishedLabel}`,
          duration: 4000,
        })
      }
    } else if (status?.status === 'idle' && trackedProjectId.value === trackId) {
      // 追踪中的项目已无 job（外部取消或其他原因），释放追踪
      trackedProjectId.value = null
    }
  } catch {
    // P2-1.2: 连续 3 次错误自动释放追踪，避免后端不可达时永久卡死
    pollErrorCount++
    if (pollErrorCount >= MAX_POLL_ERRORS) {
      bgImportStatus.value = null
      trackedProjectId.value = null
      pollErrorCount = 0
    }
  }
}

function navigateToImport() {
  const pid = bgImportStatus.value?.projectId || trackedProjectId.value || route.params.projectId
  if (!pid) return
  // 如果当前在项目列表页（概览面板可见），滚动到进度面板区域
  const progressPanel = document.querySelector('.gt-import-progress-panel')
  if (progressPanel) {
    progressPanel.scrollIntoView({ behavior: 'smooth', block: 'center' })
    // 闪烁高亮提示
    progressPanel.classList.add('gt-import-progress-panel--highlight')
    setTimeout(() => progressPanel.classList.remove('gt-import-progress-panel--highlight'), 1500)
    return
  }
  // 否则跳转到导入历史页面
  const targetPath = `/projects/${pid}/ledger/import-history`
  const currentPath = route.path
  if (currentPath === targetPath) {
    router.replace({ path: targetPath, query: { ...route.query, t: String(Date.now()) } })
  } else {
    router.push({ path: targetPath })
  }
}

watch(() => route.params.projectId, (newId) => {
  // 路由项目变化时：不清 bgImportStatus（跨项目保留追踪）；
  // 首次进入路由时主动触发一次轮询
  if (importPollTimer) { clearInterval(importPollTimer); importPollTimer = null }
  if (newId && !trackedProjectId.value) {
    // 当前没在追踪其他项目 → 轮询新项目
    pollImportQueue()
  } else if (trackedProjectId.value) {
    // 继续追踪旧项目，不切换
    pollImportQueue()
  }
  importPollTimer = setInterval(pollImportQueue, 5000)  // 5s 轮询比 10s 更实时
}, { immediate: true })

// 页面隐藏时暂停轮询（标签页切走或浏览器后台）节省请求
function onVisibilityChange() {
  if (document.hidden) {
    if (importPollTimer) { clearInterval(importPollTimer); importPollTimer = null }
  } else {
    if (!importPollTimer && (trackedProjectId.value || route.params.projectId)) {
      pollImportQueue()
      importPollTimer = setInterval(pollImportQueue, 5000)
    }
  }
}
document.addEventListener('visibilitychange', onVisibilityChange)

async function handleLogout() {
  await authStore.logout()
  router.push('/login')
}

// ── SSE 全局连接 ──
let sseSub: ProjectEventSubscription | null = null

function connectSSE(projectId: string) {
  // 切项目先退订旧的（避免连接泄漏）
  if (sseSub) {
    sseSub.close()
    sseSub = null
  }
  if (!projectId) return

  // 迁移到项目事件流单例总线（frontend-sse-connection-consolidation）：
  // 订阅通配 '*' 保持原 typed 事件 catch-all 语义（按 data.event_type 分流到 mitt sse:*）；
  // 共享连接去重（每项目一条 SSE），断线重连/退避由总线（createSSE）统一负责。
  sseSub = subscribeProjectEvent(
    projectId,
    WILDCARD_EVENT,
    (data) => {
      const d = data as SyncEventPayload | null
      if (!d || !d.event_type) return
      if (d.event_type === 'sync.failed') {
        eventBus.emit('sse:sync-failed', d)
      } else {
        eventBus.emit('sse:sync-event', d)
        // F-2：科目映射完成后给用户 toast 提示
        if (d.event_type === 'sync.completed' && (d as any).handler === '自动科目映射') {
          const msg = (d as any).message || '科目映射已完成，试算表已重算'
          const status = (d as any).status
          if (status === 'low_coverage') {
            ElMessage.warning(msg)
          } else {
            ElMessage.success(msg)
          }
        }
      }
    },
    {
      onReconnect: () => eventBus.emit('sse:connected'),
      onDegraded: () => eventBus.emit('sse:disconnected'),
    },
  )
}

// 监听项目切换，自动重连 SSE
watch(() => route.params.projectId, (newId) => {
  connectSSE(newId as string || '')
}, { immediate: true })

// 监听子组件打开公式管理的自定义事件
function onOpenFormulaEvent(payload?: OpenFormulaManagerPayload) {
  formulaOwnerState.value = receiveFormulaManagerOpen(formulaOwnerState.value, payload)
  sessionStorage.removeItem('gt-formula-target-node')
  // EventBus 只负责适配；dirty 会话由唯一 owner 固定完整上下文，nodeKey 仅为迁移元数据。
  const meta = legacyPayloadToPartialCommand(payload ?? {})
  if (meta.legacyNodeKey) {
    sessionStorage.setItem('gt-formula-target-node', meta.legacyNodeKey)
  }
  showFormulaManager.value = true
}

function onFormulaSessionChange(session: FormulaManagerSession) {
  formulaOwnerState.value = receiveFormulaManagerSession(formulaOwnerState.value, session)
}

watch(showFormulaManager, (open) => {
  if (!open) formulaOwnerState.value = {}
})

/** 监听全局打开自定义查询事件（如 Dashboard 快捷操作 / 模板页触发） */
function onOpenCustomQueryEvent(payload?: { tab?: 'basic' | 'advanced'; source?: string; project_id?: string }) {
  customQueryInitialTab.value = payload?.tab || 'basic'
  customQueryInitialSource.value = payload?.source || undefined
  showCustomQuery.value = true
}

// 公式保存/应用后广播通知所有表刷新
function onFormulaSaved() {
  eventBus.emit('formula-changed', { action: 'saved' })
}
function onFormulaApplied() {
  eventBus.emit('formula-changed', { action: 'applied' })
}

// 全局刷新成功/部分成功后触发数据重载（formula-runtime-convergence Task 16）
function onRefreshComplete(_result: unknown) {
  eventBus.emit('formula-changed', { action: 'refreshed' })
}

function onSwitchFourCol(payload: FourColSwitchPayload) {
  // 🔴 本函数自己会延迟转发一次给目录：收到的是转发件就不再处理，否则自己收自己转发、每 150 ms 重发永不停止
  if (payload?._relayed) return
  fourColumnMode.value = true
  catalogCollapsed.value = false
  // 目录可能随四栏模式刚挂载、没收到第一次：延迟转发一次（只一次）让它切到对应 tab
  if (payload?.tab) {
    setTimeout(() => {
      eventBus.emit('four-col-switch', { ...payload, _relayed: true })
    }, 150)
  }
}

/** 全局快捷键撤销 */
function onShortcutUndo() {
  operationHistory.undo()
}

onMounted(() => {
  loadPrefs()
  document.addEventListener('keydown', onKeydown)
  eventBus.on('open-formula-manager', onOpenFormulaEvent)
  eventBus.on('open-custom-query', onOpenCustomQueryEvent)
  eventBus.on('four-col-switch', onSwitchFourCol)
  eventBus.on('shortcut:undo', onShortcutUndo)
  eventBus.on('shortcut:help', () => { showShortcutHelp.value = true })
  // 移动端手势
  document.addEventListener('touchstart', onTouchStart, { passive: true })
  document.addEventListener('touchend', onTouchEnd, { passive: true })
})

onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
  document.removeEventListener('touchstart', onTouchStart)
  document.removeEventListener('visibilitychange', onVisibilityChange)
  eventBus.off('open-formula-manager', onOpenFormulaEvent)
  eventBus.off('open-custom-query', onOpenCustomQueryEvent)
  eventBus.off('four-col-switch', onSwitchFourCol)
  eventBus.off('shortcut:undo', onShortcutUndo)
  document.removeEventListener('touchend', onTouchEnd)
  if (importPollTimer) { clearInterval(importPollTimer); importPollTimer = null }
  // 关闭 SSE 订阅
  if (sseSub) { sseSub.close(); sseSub = null }
})
</script>

<style scoped>
/* ═══════════════════════════════════════════════════════════════
   三栏布局 — 整体结构
   ═══════════════════════════════════════════════════════════════ */
.gt-three-col {
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--gt-color-bg);
}

/* ── 顶部导航栏（白底）──
   原为致同品牌深紫底（--gt-color-primary）+ 全套反白前景色。
   改白底后，下方顶栏内所有前景色（logo / 面包屑 / 按钮 / 图标 / 用户区）
   都必须一并从「反白」改成常规文字色，否则白字落在白底上不可见。
   白底与下方内容区同色 ⇒ 必须补 border-bottom 才有层次分隔（原深紫底不需要）。 */
.gt-topbar {
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--gt-space-4);
  background: var(--gt-color-bg-white, #fff);
  border-bottom: 1px solid var(--gt-color-border-light, #ebeef5);
  flex-shrink: 0;
  z-index: 100;
}

.gt-topbar-left { display: flex; align-items: center; }
.gt-topbar-center { flex: 1; padding: 0 var(--gt-space-4); }
.gt-topbar-center :deep(.el-breadcrumb__inner),
.gt-topbar-center :deep(.el-breadcrumb__separator) { color: var(--gt-color-text-secondary, #606266); }
.gt-topbar-center :deep(.el-breadcrumb__inner.is-link) { color: var(--gt-color-primary); }
.gt-topbar-right { display: flex; align-items: center; gap: 4px; }
.gt-topbar-right > * { display: inline-flex; align-items: center; }

.gt-logo {
  display: flex;
  align-items: center;
  gap: var(--gt-space-2);
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--gt-radius-sm);
  transition: background var(--gt-transition-fast);
}
.gt-logo:hover { background: var(--gt-color-primary-bg, rgba(75, 45, 119, 0.06)); }
.gt-logo-img { height: 36px; width: auto; }
.gt-logo-text {
  font-size: var(--gt-font-size-sm);
  font-weight: 700;
  color: var(--gt-color-primary);
  white-space: nowrap;
}

.gt-topbar-btn {
  cursor: pointer;
  width: 34px;
  height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  border: none;
  background: transparent;
  padding: 0;
  font-family: inherit;
  color: var(--gt-color-text-secondary, #606266);
  font-size: var(--gt-font-size-sm);
  transition: background 0.15s ease;
}
.gt-topbar-btn:hover {
  background: var(--gt-color-primary-bg, rgba(75, 45, 119, 0.06));
  color: var(--gt-color-primary);
}
.gt-topbar-btn--active {
  background: var(--gt-color-primary);
  color: var(--gt-color-text-inverse, #fff);
}
.gt-topbar-btn--pulse {
  animation: gt-pulse-hint 1.5s ease-in-out infinite;
  position: relative;
}
.gt-topbar-btn--pulse::after {
  content: '';
  position: absolute;
  top: 1px; right: 1px;
  width: 10px; height: 10px;
  border-radius: 50%;
  background: #f56c6c;
  border: 2px solid #fff;
  animation: gt-dot-ping 1.2s ease-in-out infinite;
}
.gt-topbar-btn--pulse::before {
  content: '点击显示附注树';
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  white-space: nowrap;
  font-size: 11px;
  color: #e6a23c;
  font-weight: 700;
  margin-top: 4px;
  animation: gt-label-fade 2s ease-in-out infinite;
  pointer-events: none;
}
@keyframes gt-pulse-hint {
  0%, 100% { background: transparent; }
  50% { background: rgba(255, 200, 100, 0.35); }
}
@keyframes gt-dot-ping {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.6); opacity: 0.4; }
}
@keyframes gt-label-fade {
  0%, 100% { opacity: 0; }
  30%, 70% { opacity: 1; }
}
.gt-dsh-badge :deep(.el-badge__content) { top: 2px; right: 4px; }
.gt-theme-toggle {
  font-size: 16px;
}
.gt-theme-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}
.gt-topbar-text-icon {
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  line-height: 1;
}

/* 顶栏内所有 el-button text / el-icon / el-dropdown 适配白色背景 */
.gt-topbar-right :deep(.el-button--text) { color: var(--gt-color-text-secondary, #606266); }
.gt-topbar-right :deep(.el-button--text:hover) {
  color: var(--gt-color-primary);
  background: var(--gt-color-primary-bg, rgba(75, 45, 119, 0.06));
}
.gt-topbar-right :deep(.el-icon) { color: var(--gt-color-text-secondary, #606266); }
.gt-topbar-right :deep(.el-icon svg) { fill: currentColor; }
.gt-topbar-right :deep(.el-dropdown) { color: var(--gt-color-text, #303133); }

.gt-topbar-divider {
  width: 1px;
  height: 20px;
  background: var(--gt-color-border-light, #ebeef5);
  margin: 0 8px;
}

.gt-import-indicator {
  color: var(--gt-color-primary);
  background: var(--gt-color-primary-bg);
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: var(--gt-radius-sm);
  min-width: 62px;
  justify-content: center;
}
.gt-import-indicator:hover {
  background: var(--gt-color-primary-lighter);
  transform: scale(1.02);
}
.gt-import-progress-ring {
  flex: 0 0 22px;
}
.gt-import-label {
  font-size: var(--gt-font-size-xs);
  font-weight: 600;
  font-family: "Arial Narrow", Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.gt-user-info {
  display: flex;
  align-items: center;
  gap: var(--gt-space-2);
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--gt-radius-sm);
  transition: background var(--gt-transition-fast);
}
.gt-user-info:hover { background: var(--gt-color-primary-bg, rgba(75, 45, 119, 0.06)); }
.gt-avatar {
  /* 白底上头像改用品牌紫实底 + 白字，保证首字母可读 */
  background: var(--gt-gradient-primary);
  color: var(--gt-color-text-inverse, #fff);
  font-weight: 600;
  font-size: var(--gt-font-size-sm);
  border: none;
}
/* 项目内顶栏的用户名纯文本（无头像下拉） */
.gt-topbar-user-text {
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-secondary, #606266);
  margin-right: var(--gt-space-2);
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gt-username {
  font-size: var(--gt-font-size-sm);
  font-weight: 500;
  color: var(--gt-color-text, #303133);
}

/* ── 三栏主体 ── */
.gt-body {
  flex: 1;
  display: flex;
  min-height: 0;
  overflow: hidden;
}

/* ── 左侧栏（致同风格：浅灰底 + 紫色激活） ── */
.gt-sidebar {
  display: flex;
  flex-direction: column;
  background: var(--gt-color-primary-bg);
  border-right: 1px solid var(--gt-color-border-light);
  transition: width var(--gt-transition-base);
  overflow: hidden;
  flex-shrink: 0;
}

.gt-nav {
  flex: 1;
  padding: var(--gt-space-2) var(--gt-space-1);
  overflow-y: auto;
  overflow-x: hidden;
  min-height: 0; /* 允许 flex 子项收缩以触发滚动 */
}

.gt-nav-item {
  display: flex;
  align-items: center;
  gap: var(--gt-space-2);
  padding: 10px 12px;
  margin: 2px 4px;
  border-radius: var(--gt-radius-sm);
  cursor: pointer;
  color: var(--gt-color-text-secondary);
  font-size: var(--gt-font-size-sm);
  white-space: nowrap;
  transition: all var(--gt-transition-fast);
}
.gt-nav-item:hover {
  background: rgba(75, 45, 119, 0.05);
  color: var(--gt-color-primary);
}
.gt-nav-item--active {
  background: var(--gt-color-primary) !important;
  color: var(--gt-color-text-inverse) !important;
  box-shadow: 0 2px 8px rgba(75, 45, 119, 0.3);
}
.gt-nav-label { font-weight: 500; }

/* ── 项目子菜单：缩进 + 弱化，与 1 级项区分 ── */
.gt-nav-item--sub {
  padding: 7px 12px 7px 28px;
  font-size: var(--gt-font-size-xs);
  position: relative;
}

.gt-nav-item--sub:hover {
  color: var(--gt-color-primary);
}
.gt-nav-label--sub { font-weight: 400; }

/* ── 项目内侧栏：固定窄栏 + 纯文字环节清单（标签过长自动折行） ── */
/* 🔴 选择器必须带 .gt-three-col 前缀且 width 带 !important —— 两者缺一不可：
   下方响应式断点 max-width 1440px 有一条给 1 级图标导航用的规则，
   把 .gt-three-col:not(.gt-three-col--collapsed) .gt-sidebar 的宽度钉成
   56px !important。它是「2 类 + :not」，比单类选择器特异度更高
   ⇒ 只加 important 仍然输（实测环节清单被压成 56px、中文标签逐字折行）。
   ⚠ 本注释内禁写花括号（理由见下方 .gt-nav-item--stage 处注释）。 */
.gt-three-col .gt-sidebar--project {
  width: 190px !important;
  background: var(--gt-color-bg-white, #fff);
  overflow-y: auto;
}
.gt-nav--project { padding: var(--gt-space-2) 0 var(--gt-space-4); }

/* 分组标题（灰色小字，不可点） */
.gt-nav-group-title {
  padding: 14px 16px 6px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary, #909399);
  white-space: nowrap;
  cursor: default;
  user-select: none;
}
.gt-nav-group-title:first-child { padding-top: 6px; }

/* 🔴 justify-content 必须显式写 flex-start，且选择器带 .gt-three-col 前缀：
   下方响应式断点 max-width 1440px 给 .gt-sidebar .gt-nav-item 设了
   justify-content:center（1 级栏压成 56px 图标条时居中用）。
   不覆盖的话 ≤1440px 窗口下图标+文字会被整体推到栏中间
   （实测图标 x=55，而分组标题 x=0），与截图的左对齐不符。
   ⚠ CSS 注释里禁写右花括号 —— 注释不能嵌套，那个符号会提前闭合注释，
     余下文字漏成非法 CSS 并静默吃掉紧随其后的整条规则（本处实测踩过：
     选中态与 pending 灰字全部失效，且控制台无任何报错）。 */
.gt-three-col .gt-sidebar--project .gt-nav-item--stage {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 10px;
  padding: 9px 16px;
  margin: 0;
  border-radius: 0;
  white-space: nowrap;
  line-height: 1.4;
  color: var(--gt-color-text, #303133);
  font-size: var(--gt-font-size-sm);
}
.gt-three-col .gt-sidebar--project .gt-nav-item--stage:hover {
  background: var(--gt-color-primary-bg, #f4f0fa);
}
/* 选中态：浅紫底 + 主色文字（不是 1 级菜单那种深紫实底反白） */
.gt-three-col .gt-sidebar--project .gt-nav-item--stage.gt-nav-item--active {
  background: var(--gt-color-primary-bg, #f4f0fa) !important;
  color: var(--gt-color-primary, #4b2d77) !important;
  font-weight: 600;
  box-shadow: none;
}
/* 尚无页面的条目：灰掉且不响应 hover（点击由 onProjectStageClick 早退兜住）。
   🔴 选择器层数必须 ≥ 上面那条 .gt-nav-item--stage 规则，否则它的 color 会压过本条
   （实测 pending 字色曾恒为正文色，看不出不可点）。 */
.gt-three-col .gt-sidebar--project .gt-nav-item--pending {
  color: var(--gt-color-text-tertiary, #c0c4cc);
  cursor: not-allowed;
}
.gt-three-col .gt-sidebar--project .gt-nav-item--pending:hover {
  background: transparent;
}
.gt-nav-stage-label { word-break: keep-all; }
/* 有二级栏的环节（税审底稿）右侧展开标记 */
.gt-nav-stage-caret {
  margin-left: auto;
  font-size: 11px;
  color: #a79bb5;
}

/* 侧栏收起时子菜单只剩图标，取消缩进与竖线 */
.gt-three-col--collapsed .gt-nav-item--sub {
  padding: 7px 12px;
  justify-content: center;
}
.gt-three-col--collapsed .gt-nav-item--sub::before { display: none; }
.gt-maturity-badge {
  font-size: var(--gt-font-size-xs); font-weight: 600; padding: 1px 4px; border-radius: 3px;
  margin-left: 4px; vertical-align: middle; line-height: 1;
}
.gt-maturity-pilot { background: var(--gt-bg-warning); color: var(--gt-color-wheat); }
.gt-maturity-exp { background: var(--gt-color-coral-light); color: var(--gt-color-coral); }
.gt-maturity-dev { background: var(--gt-color-border-light); color: var(--gt-color-info); }

.gt-sidebar-bottom {
  padding: var(--gt-space-1);
  flex-shrink: 0;
  max-height: 45vh;
  overflow-y: auto;
}
.gt-sidebar-divider {
  height: 1px;
  background: var(--gt-color-border-purple-light, #d8b8ee);
  margin: 8px 12px;
  opacity: 0.6;
}

/* 工具簇（侧栏底部） */
.gt-sidebar-tools-title {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary, #909399);
  padding: 8px 14px 4px;
  letter-spacing: 0.5px;
}
.gt-tool-group-label {
  font-size: 11px;
  color: var(--gt-color-text-placeholder, #c0c4cc);
  padding: 6px 14px 2px;
  font-weight: 500;
  letter-spacing: 0.3px;
}
.gt-nav-item--tool {
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-secondary, #606266);
}
.gt-nav-item--tool:hover {
  background: rgba(75, 45, 119, 0.05);
  color: var(--gt-color-primary);
}
.gt-tool-text-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  font-size: var(--gt-font-size-sm);
  line-height: 1;
}

/* 折叠态 */
.gt-three-col--collapsed .gt-nav-item {
  justify-content: center;
  padding: 10px 0;
}

/* ── 拖拽分隔线 ── */
.gt-resizer {
  width: 4px;
  cursor: col-resize;
  background: transparent;
  flex-shrink: 0;
  position: relative;
  z-index: 5;
  transition: background var(--gt-transition-fast);
}
.gt-resizer:hover,
.gt-resizer:active {
  background: var(--gt-color-primary-lighter);
}

/* ── 中间栏 ── */
.gt-middle {
  flex-shrink: 0;
  background: var(--gt-color-bg-white);
  border-right: 1px solid var(--gt-color-border-light);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.gt-middle-content {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
}
.gt-middle-bottom {
  border-top: 1px solid var(--gt-color-border-light);
  padding: var(--gt-space-1);
  flex-shrink: 0;
}
.gt-middle-collapsed {
  width: 24px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  background: var(--gt-bg-subtle);
  border-right: 1px solid var(--gt-color-border-light);
  cursor: pointer;
  color: var(--gt-color-text-tertiary);
  transition: all var(--gt-transition-fast);
}
.gt-middle-collapsed:hover {
  background: var(--gt-color-primary-bg);
  color: var(--gt-color-primary);
}
.gt-middle-collapsed-icon {
  padding: 12px 0;
  display: flex;
  justify-content: center;
  border-top: 1px solid var(--gt-color-border-light);
}

/* ── 右侧栏 ── */
.gt-detail {
  flex: 1;
  min-width: 0;
  background: var(--gt-color-bg-white);
  overflow-y: auto;
}

/* ── 第3栏：功能目录（四栏模式） ── */
.gt-catalog {
  flex-shrink: 0;
  background: var(--gt-color-bg-white);
  border-right: 1px solid var(--gt-color-border-light);
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}
.gt-catalog-bottom {
  border-top: 1px solid var(--gt-color-border-light);
  padding: var(--gt-space-1);
  flex-shrink: 0;
}

.gt-catalog-collapsed {
  width: 24px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  background: var(--gt-bg-subtle);
  border-right: 1px solid var(--gt-color-border-light);
  cursor: pointer;
  color: var(--gt-color-text-tertiary);
  transition: all var(--gt-transition-fast);
}
.gt-catalog-collapsed:hover {
  background: var(--gt-color-primary-bg);
  color: var(--gt-color-primary);
}
.gt-catalog-collapsed-icon {
  padding: 12px 0;
  display: flex;
  justify-content: center;
  border-top: 1px solid var(--gt-color-border-light);
}

/* ── 全屏模式 ── */
.gt-three-col--fullscreen .gt-sidebar,
.gt-three-col--fullscreen .gt-middle,
.gt-three-col--fullscreen .gt-resizer {
  display: none;
}

/* ── 响应式 ── */

/* Desktop: > 1280px — default layout */

/* Tablet: 768px - 1280px */
@media (max-width: 1280px) {
  .gt-three-col:not(.gt-three-col--collapsed) .gt-sidebar {
    width: 56px !important;
  }
  .gt-three-col:not(.gt-three-col--collapsed) .gt-nav-label {
    display: none;
  }
  .gt-three-col:not(.gt-three-col--collapsed) .gt-nav-item {
    justify-content: center;
    padding: 10px 0;
  }
}

/* Tablet: 768px - 1024px — hide middle column */
@media (max-width: 1024px) {
  .gt-middle {
    display: none !important;
  }
  .gt-catalog {
    display: none !important;
  }
}

/* Mobile: < 768px — single column layout */
@media (max-width: 768px) {
  .gt-three-col {
    flex-direction: column;
  }
  .gt-sidebar {
    position: fixed;
    z-index: 1000;
    height: auto;
    width: 100% !important;
    flex-direction: row;
    overflow-x: auto;
    border-right: none;
    border-bottom: 1px solid var(--gt-border, #e4e7ed);
  }
  .gt-sidebar .gt-nav-list {
    flex-direction: row;
    gap: 0;
  }
  .gt-sidebar .gt-nav-item {
    padding: 8px 12px;
    flex-direction: column;
    font-size: var(--gt-font-size-xs);
  }
  .gt-sidebar .gt-nav-label {
    display: block;
    font-size: var(--gt-font-size-xs);
  }
  .gt-middle {
    display: none !important;
  }
  .gt-catalog {
    display: none !important;
  }
  .gt-main-area {
    margin-top: 56px;
    width: 100%;
  }
  .gt-topbar {
    font-size: var(--gt-font-size-sm);
  }
  .gt-topbar .gt-logo-text {
    display: none;
  }
}

/* ── 过渡动画 ── */
.gt-fade-enter-active, .gt-fade-leave-active {
  transition: opacity 0.15s, transform 0.15s;
}
.gt-fade-enter-from, .gt-fade-leave-to {
  opacity: 0;
  transform: translateX(-4px);
}

/* ── 显示设置面板 ── */
.gt-display-prefs-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.gt-dp-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.gt-dp-label {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-secondary);
  min-width: 56px;
  flex-shrink: 0;
}
.gt-dp-row :deep(.el-radio-button__inner) {
  padding: 4px 10px;
  font-size: var(--gt-font-size-xs);
}

/* 进度面板高亮闪烁 */
:deep(.gt-import-progress-panel--highlight) {
  animation: gt-progress-highlight 1.5s ease;
}
@keyframes gt-progress-highlight {
  0%, 100% { box-shadow: none; }
  25%, 75% { box-shadow: 0 0 0 3px var(--gt-color-primary, #4b2d77); }
}
</style>
