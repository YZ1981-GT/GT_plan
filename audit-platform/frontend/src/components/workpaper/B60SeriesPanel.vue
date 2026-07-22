<!--
  B60SeriesPanel.vue — B60「总体审计策略及具体审计计划」系列底稿面板

  B60 系列由 1 个工时表 xlsx + 9 个独立 docx 组成，但平台只为 B60 建了 1 条
  working_paper（关联工时表 xlsx，render-config 仅返回工时表 sheet）。9 个 docx
  是独立模板文件，无 working_paper 记录。

  本面板在 B60 底稿目录页展示全部 10 个系列底稿卡片：
  - docx（B60 主文档 / B60-2-* / B60-3 / B60A~D）→ WpInlinePopup 弹窗打开
    （复用平台既有 WpPopupDocxEditor：OnlyOffice 在线编辑 / 模板下载，后端零改动）
  - xlsx（B60-1 工时表）→ 切换到当前 render-config 已渲染的工时表 sheet

  纯前端静态清单驱动，不触碰后端 render-config 热路径。
-->
<template>
  <div class="b60-series">
    <div class="b60-series__header">
      <h4 class="b60-series__title">B60 系列底稿</h4>
      <span class="b60-series__hint">点击卡片打开对应底稿（Word 文档弹窗编辑，工时表切换页签）</span>
    </div>
    <div class="b60-series__grid">
      <div
        v-for="d in B60_SERIES"
        :key="d.wpCode"
        class="b60-series__card"
        @click="openDoc(d)"
      >
        <div class="b60-series__card-top">
          <span class="b60-series__code">{{ d.wpCode }}</span>
          <el-tag
            size="small"
            :type="d.kind === 'xlsx' ? 'success' : 'primary'"
            effect="plain"
          >{{ d.kind === 'xlsx' ? '表格' : '文档' }}</el-tag>
        </div>
        <span class="b60-series__name" :title="d.name">{{ d.name }}</span>
        <span class="b60-series__note">{{ d.note }}</span>
      </div>
    </div>

    <WpInlinePopup
      v-model:visible="popupVisible"
      :wp-code="activeWpCode"
      :wp-id="activeWpId"
      :project-id="projectId"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, defineAsyncComponent } from 'vue'
import { ElMessage } from 'element-plus'

const WpInlinePopup = defineAsyncComponent(() => import('./WpInlinePopup.vue'))

const props = defineProps<{
  projectId: string
  wpId: string
  /** 工时表在 render-config 中的真实 sheet 名（供切换页签） */
  worktimeSheetName?: string
}>()

const emit = defineEmits<{
  (e: 'jump-to-sheet', sheetName: string): void
}>()

interface B60Doc {
  wpCode: string
  name: string
  note: string
  kind: 'docx' | 'xlsx'
}

// B60 系列静态清单（对齐 wp_templates/B/ 实际文件 + wpPopupDocxConfigsB 注册）
const B60_SERIES: B60Doc[] = [
  { wpCode: 'B60', name: '总体审计策略及具体审计计划', note: '所有项目适用', kind: 'docx' },
  { wpCode: 'B60-1', name: '审计项目工时预算与控制表', note: '所有项目适用', kind: 'xlsx' },
  { wpCode: 'B60-2-1', name: 'IT复杂性判断表', note: '所有项目适用', kind: 'docx' },
  { wpCode: 'B60-2-2', name: 'IT审计进场前通知表', note: '需执行 IT 审计程序', kind: 'docx' },
  { wpCode: 'B60-2-3', name: 'IT审计计划备忘录', note: '需执行 IT 审计程序', kind: 'docx' },
  { wpCode: 'B60-3', name: '评估专家工作计划', note: '需利用专家工作', kind: 'docx' },
  { wpCode: 'B60A', name: '对内控审计的特殊考虑', note: '整合审计（含内控审计）', kind: 'docx' },
  { wpCode: 'B60B', name: '对IPO申报财务报表审计的特殊考虑', note: 'IPO 项目', kind: 'docx' },
  { wpCode: 'B60C', name: '对国有企业年度财务报表审计的特殊考虑', note: '国有企业项目', kind: 'docx' },
  { wpCode: 'B60D', name: '向监管机构报送策略和计划的函副本', note: '需向监管报送时', kind: 'docx' },
]

const popupVisible = ref(false)
const activeWpCode = ref('')

// 仅 B60 主文档有对应 working_paper（wpId）；其余子文档无独立实例，
// 传 undefined 让 WpPopupDocxEditor 走 by-wpCode 模板下载（避免误用主文档 wpId 打开错误内容）
const activeWpId = computed(() => (activeWpCode.value === 'B60' ? props.wpId : undefined))

function openDoc(doc: B60Doc): void {
  if (doc.kind === 'xlsx') {
    // 工时表 → 切换到 render-config 已渲染的 univer sheet
    if (props.worktimeSheetName) {
      emit('jump-to-sheet', props.worktimeSheetName)
    } else {
      ElMessage.info('工时表页签暂未就绪')
    }
    return
  }
  // docx → 弹窗打开（WpPopupDocxEditor：OnlyOffice / 下载）
  activeWpCode.value = doc.wpCode
  popupVisible.value = true
}
</script>

<style scoped>
.b60-series {
  margin-top: 28px;
}
.b60-series__header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
}
.b60-series__title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--gt-color-text-primary, #303133);
}
.b60-series__hint {
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
}
.b60-series__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 10px;
}
.b60-series__card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  border: 1px solid var(--gt-color-border-purple, #e8e4f0);
  border-radius: 8px;
  background: var(--gt-color-bg-white, #fff);
  cursor: pointer;
  transition: all 0.2s;
}
.b60-series__card:hover {
  border-color: var(--gt-color-primary, #4b2d77);
  box-shadow: 0 2px 8px rgba(75, 45, 119, 0.12);
  transform: translateY(-2px);
}
.b60-series__card-top {
  display: flex;
  align-items: center;
  gap: 6px;
}
.b60-series__code {
  font-size: var(--wp-font-size, 13px);
  font-weight: 700;
  color: var(--gt-color-primary, #4b2d77);
}
.b60-series__card-top :deep(.el-tag) {
  margin-left: auto;
}
.b60-series__name {
  font-size: var(--wp-font-size, 13px);
  line-height: 1.4;
  color: var(--gt-color-text-primary, #303133);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.b60-series__note {
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
}
</style>
