<template>
  <div class="cf-verification">
    <!-- 切换按钮（右上角下拉） -->
    <el-dropdown class="cf-verification__switch-dropdown" trigger="click" @command="onSwitchTab" popper-class="gt-a1-switch-popper">
      <span class="cf-verification__switch-trigger">
        <el-icon><Switch /></el-icon>
        切换
        <el-icon class="cf-verification__switch-arrow"><ArrowDown /></el-icon>
      </span>
      <template #dropdown>
        <el-dropdown-menu>
          <div class="gt-a1-switch-popper__header">快速跳转页签</div>
          <el-dropdown-item command="cash" :class="{ 'is-active-item': activeTab === 'cash' }">
            <el-icon><Document /></el-icon>现金等价物
          </el-dropdown-item>
          <el-dropdown-item command="reconcile" :class="{ 'is-active-item': activeTab === 'reconcile' }">
            <el-icon><Document /></el-icon>勾稽核对
          </el-dropdown-item>
          <el-dropdown-item command="main" :class="{ 'is-active-item': activeTab === 'main' }">
            <el-icon><Document /></el-icon>主表逆算
          </el-dropdown-item>
          <el-dropdown-item command="supplementary" :class="{ 'is-active-item': activeTab === 'supplementary' }">
            <el-icon><Document /></el-icon>附表间接法
          </el-dropdown-item>
          <el-dropdown-item command="adjustment" :class="{ 'is-active-item': activeTab === 'adjustment' }">
            <el-icon><Document /></el-icon>CF调整
          </el-dropdown-item>
          <el-dropdown-item divided disabled style="height:1px;padding:0;margin:4px 12px;background:#ebeef5;" />
          <el-dropdown-item command="a5-1" :class="{ 'is-active-item': activeTab === 'a5-1' }">
            <el-icon><Document /></el-icon>A5-1 现金流量表审计
          </el-dropdown-item>
          <el-dropdown-item command="a5-2" :class="{ 'is-active-item': activeTab === 'a5-2' }">
            <el-icon><Document /></el-icon>A5-2 承诺事项
          </el-dropdown-item>
          <el-dropdown-item command="a5-3" :class="{ 'is-active-item': activeTab === 'a5-3' }">
            <el-icon><Document /></el-icon>A5-3 或有事项
          </el-dropdown-item>
          <el-dropdown-item command="a5-4" :class="{ 'is-active-item': activeTab === 'a5-4' }">
            <el-icon><Document /></el-icon>A5-4 持续经营净利润和终止经营净利润
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>

    <div style="display: flex; justify-content: flex-end; margin-bottom: 8px">
      <el-button size="small" @click="refreshKey++" :icon="Refresh">重新核查</el-button>
    </div>
    <el-tabs v-model="activeTab" type="border-card" :key="refreshKey" @wheel.prevent="onTabWheel">
      <el-tab-pane label="现金等价物" name="cash">
        <CfCashEquivalents :project-id="projectId" :year="year" />
      </el-tab-pane>
      <el-tab-pane label="勾稽核对" name="reconcile">
        <CfReconciliation :project-id="projectId" :year="year" />
      </el-tab-pane>
      <el-tab-pane label="主表逆算" name="main">
        <el-alert type="info" :closable="false" style="margin-bottom: 8px" show-icon>
          逆算公式中涉及增值税影响（如销售收到现金）暂未扣除增值税销项税额，差异可能包含税金影响。
        </el-alert>
        <CfMainTable :project-id="projectId" :year="year" />
      </el-tab-pane>
      <el-tab-pane label="附表间接法" name="supplementary">
        <CfSupplementary :project-id="projectId" :year="year" />
      </el-tab-pane>
      <el-tab-pane label="CF调整" name="adjustment">
        <CfAdjustment :project-id="projectId" :year="year" />
      </el-tab-pane>
      <!-- A5-1 专属组件 Tab -->
      <el-tab-pane label="A5-1 现金流量表审计" name="a5-1" lazy>
        <GtA51CashflowAudit
          v-if="subWpIdMap['A5-1']"
          :wp-id="subWpIdMap['A5-1']"
        />
        <el-empty v-else description="A5-1 现金流量表审计 底稿未创建" />
      </el-tab-pane>
      <!-- 其他子底稿 Tab（A5-2~A5-4，OnlyOffice 渲染） -->
      <el-tab-pane
        v-for="sub in otherSubWorkpapers"
        :key="sub.code"
        :label="sub.label"
        :name="sub.code"
        lazy
      >
        <GtOnlyOfficeSheet
          v-if="sub.wpId"
          :wp-id="sub.wpId"
          :sheet-name="sub.code"
          :project-id="projectId"
          :whole-workbook="true"
        />
        <el-empty v-else :description="`${sub.label} 底稿未创建`" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, defineAsyncComponent } from 'vue'
import { Refresh, Switch, ArrowDown, Document } from '@element-plus/icons-vue'
import CfCashEquivalents from './cf/CfCashEquivalents.vue'
import CfReconciliation from './cf/CfReconciliation.vue'
import CfMainTable from './cf/CfMainTable.vue'
import CfSupplementary from './cf/CfSupplementary.vue'
import CfAdjustment from './cf/CfAdjustment.vue'
import GtOnlyOfficeSheet from './GtOnlyOfficeSheet.vue'
import { api } from '@/services/apiProxy'

const GtA51CashflowAudit = defineAsyncComponent(() => import('./GtA51CashflowAudit.vue'))

const props = defineProps<{
  projectId: string
  year: number
  wpId?: string
}>()

const activeTab = ref('cash')
const refreshKey = ref(0)

// ─── 子底稿定义 ───
interface SubWp { code: string; label: string; wpId: string }

// A5-1 单独用专属组件渲染
const subWpIdMap = ref<Record<string, string>>({})
const otherSubWorkpapers = ref<SubWp[]>([
  { code: 'a5-2', label: 'A5-2 承诺事项', wpId: '' },
  { code: 'a5-3', label: 'A5-3 或有事项', wpId: '' },
  { code: 'a5-4', label: 'A5-4 持续经营净利润', wpId: '' },
])

// ─── 加载子底稿 wpId ───
async function loadSubWpIds() {
  if (!props.projectId) return
  try {
    const res = await api.get<any>(`/api/projects/${props.projectId}/wp-index`, { _silent: true } as any)
    const list = res?.items || res || []
    const wpCodeMap: Record<string, string> = {}
    for (const item of list) {
      if (item.wp_code?.startsWith('A5-')) {
        wpCodeMap[item.wp_code] = item.wp_id || item.id
      }
    }
    // A5-1 单独映射
    if (wpCodeMap['A5-1']) subWpIdMap.value['A5-1'] = wpCodeMap['A5-1']
    // 其他子底稿
    for (const sub of otherSubWorkpapers.value) {
      const wpCode = sub.code.toUpperCase()
      if (wpCodeMap[wpCode]) sub.wpId = wpCodeMap[wpCode]
    }
  } catch { /* silent */ }
}

// ─── Tab 滚轮切换 ───
function onTabWheel(e: WheelEvent): void {
  const tabsEl = document.querySelector('.cf-verification .el-tabs__nav-scroll')
  if (tabsEl) tabsEl.scrollLeft += e.deltaY || e.deltaX
}

// ─── 切换下拉 ───
function onSwitchTab(tabName: string): void {
  activeTab.value = tabName
}

onMounted(() => loadSubWpIds())
</script>

<style scoped>
.cf-verification {
  padding: 16px;
  position: relative;
}

.cf-verification__switch-dropdown {
  position: absolute;
  right: 16px;
  top: 16px;
  z-index: 10;
}

.cf-verification__switch-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  font-size: 13px;
  font-weight: 500;
  color: #6750A4;
  cursor: pointer;
  border: 1px solid #d4c5f9;
  border-radius: 6px;
  background: #faf7ff;
  transition: all 0.15s;
  user-select: none;
}

.cf-verification__switch-trigger:hover {
  background: #f0ebff;
  border-color: #6750A4;
  box-shadow: 0 2px 6px rgba(103, 80, 164, 0.12);
}

.cf-verification__switch-arrow {
  font-size: 12px;
}
</style>
