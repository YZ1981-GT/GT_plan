<template>
  <div class="gt-proc-launcher">
    <div class="gt-proc-launcher-title">
      <span>📋 程序面板</span>
    </div>
    <div class="gt-proc-launcher-grid">
      <el-button
        v-for="btn in buttons"
        :key="btn.sheetKey"
        size="small"
        plain
        @click="openDialog(btn)"
      >
        <span class="gt-proc-launcher-icon">{{ btn.icon }}</span>
        {{ btn.label }}
      </el-button>
    </div>

    <!-- 程序总控台（C 类） -->
    <el-dialog
      v-model="showControlPanel"
      :fullscreen="true"
      title="审计程序总控台"
      :close-on-press-escape="false"
      class="gt-fullscreen-dialog"
    >
      <ProcedureControlPanel
        :project-id="projectId"
        :wp-id="wpId"
        :wp-code="wpCode"
        procedure-sheet-name="货币资金实质性程序表E1A"
        @wp-ref-click="onWpRefClick"
      />
    </el-dialog>

    <!-- B 类检查清单 -->
    <BCheckListDialog
      v-if="activeDialog === 'B'"
      v-model="dialogVisible"
      :project-id="projectId"
      :wp-id="wpId"
      :sheet-key="activeSheetKey"
      :title="activeTitle"
      :procedure-code="activeProcCode"
      :assertions="activeAssertions"
      :risk-level="activeRiskLevel"
      @saved="onDialogSaved"
    />
    <!-- D 类盘点 -->
    <DCountDialog
      v-if="activeDialog === 'D'"
      v-model="dialogVisible"
      :project-id="projectId"
      :wp-id="wpId"
      :sheet-key="activeSheetKey"
      :title="activeTitle"
      :procedure-code="activeProcCode"
      :assertions="activeAssertions"
      :risk-level="activeRiskLevel"
      @saved="onDialogSaved"
    />
    <!-- E1 类截止测试 -->
    <E1CutoffDialog
      v-if="activeDialog === 'E1'"
      v-model="dialogVisible"
      :project-id="projectId"
      :wp-id="wpId"
      :sheet-key="activeSheetKey"
      :title="activeTitle"
      :procedure-code="activeProcCode"
      :assertions="activeAssertions"
      :risk-level="activeRiskLevel"
      @saved="onDialogSaved"
    />
    <!-- E2 类人工 -->
    <E2ManualDialog
      v-if="activeDialog === 'E2'"
      v-model="dialogVisible"
      :project-id="projectId"
      :wp-id="wpId"
      :sheet-key="activeSheetKey"
      :title="activeTitle"
      :procedure-code="activeProcCode"
      :assertions="activeAssertions"
      :risk-level="activeRiskLevel"
      @saved="onDialogSaved"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * ProcedureDialogLauncher — B/C/D/E 类弹窗入口按钮（Sprint 2 Task 2.7）
 *
 * 在左侧导航 sheet 列表下方，按 sheet 类型加图标 📋/📦/⏱/✏️
 * 点击后打开对应 4 类弹窗 + 1 类总控台
 *
 * E1 默认配置 13 个弹窗按钮，未来可推广到 D-N 全循环
 */
import { ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { useRouter } from 'vue-router'
import ProcedureControlPanel from './ProcedureControlPanel.vue'
import BCheckListDialog from './dialogs/BCheckListDialog.vue'
import DCountDialog from './dialogs/DCountDialog.vue'
import E1CutoffDialog from './dialogs/E1CutoffDialog.vue'
import E2ManualDialog from './dialogs/E2ManualDialog.vue'

interface Props {
  projectId: string
  wpId: string
  wpCode: string
}
const props = defineProps<Props>()
const router = useRouter()

interface ButtonDef {
  sheetKey: string
  label: string
  type: 'C' | 'B' | 'D' | 'E1' | 'E2'
  icon: string
  procedureCode?: string
  assertions?: string[]
  riskLevel?: string
}

// E1 默认按钮配置（依据 README v2.1 33 sheet 分类）
const buttons: ButtonDef[] = [
  // 总控台
  { sheetKey: 'e1a', label: 'E1A 总控台', type: 'C', icon: '📋' },
  // D 类盘点
  { sheetKey: 'e1_7', label: 'E1-7 库存现金盘点', type: 'D', icon: '📦', procedureCode: 'R22', assertions: ['A'], riskLevel: '中' },
  { sheetKey: 'e1_8', label: 'E1-8 外币盘点', type: 'D', icon: '📦', procedureCode: 'R22', assertions: ['A'], riskLevel: '中' },
  { sheetKey: 'e1_9', label: 'E1-9 银行存单盘点', type: 'D', icon: '📦', procedureCode: 'R22', assertions: ['A', 'B'], riskLevel: '中' },
  // B 类检查清单
  { sheetKey: 'e1_10', label: 'E1-10 银行账户清单', type: 'B', icon: '✅', procedureCode: 'R29', assertions: ['B', 'C'], riskLevel: '中' },
  { sheetKey: 'e1_11', label: 'E1-11 承诺书', type: 'B', icon: '✅', procedureCode: 'R30', assertions: ['B', 'C'], riskLevel: '中' },
  { sheetKey: 'e1_18', label: 'E1-18 征信报告检查', type: 'B', icon: '✅', procedureCode: 'R32', assertions: ['B', 'C'], riskLevel: '中' },
  { sheetKey: 'e1_19', label: 'E1-19 受限货币资金', type: 'B', icon: '✅', procedureCode: 'R33', assertions: ['C', 'E'], riskLevel: '高' },
  // E1 类截止测试
  { sheetKey: 'e1_21', label: 'E1-21 银行回单截止测试', type: 'E1', icon: '⏱', procedureCode: 'R34', assertions: ['A', 'B'], riskLevel: '高' },
  { sheetKey: 'e1_22', label: 'E1-22 大额转账截止', type: 'E1', icon: '⏱', procedureCode: 'R35', assertions: ['A', 'B'], riskLevel: '高' },
  { sheetKey: 'e1_23', label: 'E1-23 跨期付款检查', type: 'E1', icon: '⏱', procedureCode: 'R36', assertions: ['A', 'B'], riskLevel: '高' },
  // E2 类人工
  { sheetKey: 'e1_20', label: 'E1-20 利息收入测算', type: 'E2', icon: '✏️', procedureCode: 'R37', assertions: ['D'], riskLevel: '中' },
  { sheetKey: 'e1_6', label: 'E1-6 余额调节表', type: 'E2', icon: '✏️', procedureCode: 'R20', assertions: ['A', 'B', 'D'], riskLevel: '中' },
]

const showControlPanel = ref(false)
const dialogVisible = ref(false)
const activeDialog = ref<'B' | 'D' | 'E1' | 'E2' | null>(null)
const activeSheetKey = ref('')
const activeTitle = ref('')
const activeProcCode = ref('')
const activeAssertions = ref<string[]>([])
const activeRiskLevel = ref('')

function openDialog(btn: ButtonDef) {
  if (btn.type === 'C') {
    showControlPanel.value = true
    return
  }
  activeDialog.value = btn.type
  activeSheetKey.value = btn.sheetKey
  activeTitle.value = btn.label
  activeProcCode.value = btn.procedureCode || ''
  activeAssertions.value = btn.assertions || []
  activeRiskLevel.value = btn.riskLevel || ''
  dialogVisible.value = true
}

function onDialogSaved() {
  // E1 Sprint 2 Task 2.12: 返回时通过 eventBus 触发 prefill 重执行
  eventBus.emit('manual-refresh', { projectId: props.projectId, wpId: props.wpId })
}

function onWpRefClick(ref: string) {
  // E1 Sprint 2 Task 2.19: cross_wp_ref 超链接跳转
  const cleanRef = ref.split(/[\s,，]/)[0].trim()
  if (!cleanRef) return
  router.push({
    name: 'WorkpaperList',
    params: { projectId: props.projectId },
    query: { highlight: cleanRef },
  })
}
</script>

<style scoped>
.gt-proc-launcher {
  border: 1px solid var(--gt-color-border-light, #e4e7ed);
  border-radius: 6px;
  background: var(--gt-color-bg-white, #fff);
  padding: 8px;
}
.gt-proc-launcher-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--gt-color-text-primary, #333);
  margin-bottom: 6px;
}
.gt-proc-launcher-grid {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.gt-proc-launcher-grid :deep(.el-button) {
  justify-content: flex-start;
  text-align: left;
  width: 100%;
}
.gt-proc-launcher-icon {
  margin-right: 4px;
}
.gt-fullscreen-dialog :deep(.el-dialog__body) {
  height: calc(100vh - 110px);
  overflow-y: auto;
}
</style>
