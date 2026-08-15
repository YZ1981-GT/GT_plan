<script setup lang="ts">
/**
 * HiFourTableSourcePanel — H/I 循环通用四表取数源面板
 *
 * 展示各分段的 TB 取数公式+当前值，提供🔄刷新取数入口。
 * 通过 props 参数化科目分段配置，适用 H5-H10/I1-I6 全部 12 张审定表。
 *
 * Spec: .kiro/specs/hi-cycle-four-table-extraction/ Task 4.1
 */
import { computed, ref } from 'vue'
import { ElButton, ElCard, ElTable, ElTableColumn, ElTag, ElMessageBox, ElMessage } from 'element-plus'
import type { HiExtractionSegment } from '../composables/hiExtractionSegments'

const props = defineProps<{
  wpCode: string
  segments: HiExtractionSegment[]
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'refresh-complete'): void
}>()

const refreshing = ref(false)

/** 从 allResponses 读当前锚点值 */
const currentValues = computed(() => {
  const result: { label: string; expression: string; value: string; anchorKey: string }[] = []
  for (const seg of props.segments) {
    const item = props.allResponses?.get(seg.anchorKey)
    const val = item?.remark ?? item?.conclusion ?? ''
    result.push({
      label: seg.label,
      expression: seg.expression,
      value: val ? String(val) : '—',
      anchorKey: seg.anchorKey,
    })
  }
  return result
})

const hasManualValues = computed(() => {
  return currentValues.value.some(r => r.value && r.value !== '—' && r.value !== '0')
})

/**
 * 无取数段时的空表文案 —— 必须说清**为什么**没有，不能只显示 Element Plus 默认的
 * 「No Data」（英文 + 零信息，违反平台「UI 全中文化」与「absent 须显式说明」两条口径）。
 *
 * I5-1「其他非流动资产」实测：该循环真源 `I_CYCLE_ACCOUNT_SPECS.I5.fallback` 为空
 * （`1911` 在全库两张科目表都不存在，宁缺勿造不给兜底码）⇒ `segments` 为 `[]`
 * ⇒ 面板只剩一个「No Data」空表格 + 一个点了没意义的「🔄 刷新取数」按钮。
 */
const emptyText = computed(() =>
  `本循环（${props.wpCode}）在四表库中没有可取数的科目段 —— `
  + '通常是本项目科目表里确实没有该科目（属业务事实，审定表相关行留空即可，请勿填 0）。'
  + '若本项目确有该科目，请检查科目表导入与科目映射。',
)

/** absent 态下「刷新取数」无意义（没有段可刷），隐藏按钮避免误导 */
const hasSegments = computed(() => (props.segments || []).length > 0)

async function handleRefresh() {
  if (props.isReadonly) return

  if (hasManualValues.value) {
    try {
      await ElMessageBox.confirm(
        '部分锚点已有手工录入值或跨表带入数据，刷新将以四表库值覆盖。确认刷新？',
        '覆盖确认',
        { confirmButtonText: '确认刷新', cancelButtonText: '取消', type: 'warning' },
      )
    } catch {
      return // 取消
    }
  }

  refreshing.value = true
  try {
    // 通知父组件重新从 render-config 取数（render 灰度开时自动 seed responses_snapshot）
    emit('refresh-complete')
    ElMessage.success('已请求刷新取数，请等待底稿重新加载')
  } finally {
    refreshing.value = false
  }
}
</script>

<template>
  <el-card class="hi-source-panel" shadow="never">
    <template #header>
      <div class="hi-source-panel__header">
        <span class="hi-source-panel__title">🔗 四表取数（公式管理）</span>
        <el-button
          v-if="!isReadonly && hasSegments"
          type="primary"
          plain
          size="small"
          :loading="refreshing"
          @click="handleRefresh"
        >
          🔄 刷新取数
        </el-button>
      </div>
    </template>

    <el-table :data="currentValues" size="small" style="width: 100%" :empty-text="emptyText">
      <el-table-column prop="label" label="科目/分段" min-width="140" />
      <el-table-column prop="expression" label="取数公式" min-width="180">
        <template #default="{ row }">
          <code class="hi-source-panel__formula">{{ row.expression }}</code>
        </template>
      </el-table-column>
      <el-table-column prop="value" label="当前值" min-width="120" align="right">
        <template #default="{ row }">
          <el-tag v-if="row.value && row.value !== '—'" type="success" size="small">{{ row.value }}</el-tag>
          <span v-else style="color: #909399">—</span>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<style scoped>
.hi-source-panel {
  margin-bottom: 12px;
}
.hi-source-panel :deep(.el-card__header) {
  padding: 8px 16px;
  background: linear-gradient(135deg, #f0f9ff 0%, #e8f4fd 100%);
}
.hi-source-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.hi-source-panel__title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-color-primary);
}
.hi-source-panel__formula {
  font-size: 12px;
  color: #606266;
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 3px;
}
.hi-source-panel :deep(.el-table) {
  font-size: 13px;
}
</style>
