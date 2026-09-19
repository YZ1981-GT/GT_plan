<template>
  <div class="g7-linkage-entry" data-testid="g7-linkage-entry">
    <el-button
      size="small"
      type="primary"
      plain
      :loading="linkage.loading.value"
      @click="handleOpen"
    >
      🔗 联动到合并工作底稿
      <el-badge
        v-if="linkage.stale.value"
        is-dot
        type="warning"
        class="stale-dot"
      />
    </el-button>

    <el-dialog
      v-model="visible"
      title="联动到合并工作底稿"
      width="720px"
      append-to-body
      data-testid="g7-linkage-dialog"
    >
      <el-alert
        v-if="linkage.configError.value"
        type="error"
        :closable="false"
        show-icon
        :title="linkage.configError.value"
        class="cfg-error"
      />

      <template v-else-if="linkage.preview.value">
        <el-alert
          v-if="linkage.stale.value"
          type="warning"
          :closable="false"
          show-icon
          title="合并侧联动结果已过期，建议重新导入以同步最新 G7 数据"
          class="stale-alert"
        />

        <el-descriptions :column="2" border size="small" class="preview-summary">
          <el-descriptions-item label="可导入行数">
            {{ importableTotal }}
          </el-descriptions-item>
          <el-descriptions-item label="候选主体">
            {{ linkage.preview.value.available_companies?.length ?? 0 }}
          </el-descriptions-item>
          <el-descriptions-item label="未匹配主体">
            <el-tag v-if="linkage.unresolvedCount.value" type="warning" size="small">
              {{ linkage.unresolvedCount.value }}
            </el-tag>
            <span v-else>—</span>
          </el-descriptions-item>
          <el-descriptions-item label="建议草稿">
            {{ linkage.suggestionCount.value }} 条
          </el-descriptions-item>
        </el-descriptions>

        <el-table
          :data="targetRows"
          border
          size="small"
          class="target-table"
          max-height="240"
        >
          <el-table-column label="目标表" prop="label" min-width="200" />
          <el-table-column label="候选" prop="candidate" width="90" align="right" />
          <el-table-column label="可导入" prop="importable" width="90" align="right" />
        </el-table>

        <div v-if="linkage.unresolvedCount.value" class="unresolved-list">
          <span class="ul-label">未匹配主体（不会导入）：</span>
          <el-tag
            v-for="name in linkage.preview.value.unresolved_companies"
            :key="name"
            size="small"
            type="info"
            effect="plain"
          >{{ name }}</el-tag>
        </div>
      </template>

      <el-empty v-else description="点击「预览」加载联动摘要" :image-size="60" />

      <template #footer>
        <el-button size="small" @click="linkage.gotoConsolidation()">前往合并工作底稿</el-button>
        <el-button size="small" @click="handleOpen">重新预览</el-button>
        <el-button
          size="small"
          type="primary"
          :loading="linkage.importing.value"
          :disabled="!canImport"
          data-testid="g7-linkage-confirm"
          @click="handleImport"
        >
          确认导入
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * G7ConsolLinkageEntryDialog — G7 底稿侧发起合并联动入口（R1）。
 * 只复用既有 preview/import 端点，不新造后端口径；只读态/无编辑权禁用确认导入。
 */
import { computed, ref } from 'vue'
import { useG7ConsolLinkageEntry } from '../../composables/g7ConsolLinkageEntry'

const props = defineProps<{
  projectId: string
  year: number
  readonly?: boolean
  canEdit?: boolean
}>()

const visible = ref(false)
const projectIdRef = computed(() => props.projectId)
const yearRef = computed(() => props.year)
const linkage = useG7ConsolLinkageEntry(projectIdRef, yearRef)

const canImport = computed(
  () => !props.readonly && props.canEdit !== false && !!linkage.preview.value && !linkage.configError.value,
)

const importableTotal = computed(() => {
  const imp = linkage.preview.value?.importable ?? {}
  return Object.values(imp).reduce((sum, rows) => sum + (Array.isArray(rows) ? rows.length : 0), 0)
})

const SHEET_LABELS: Record<string, string> = {
  info: '被投资单位基本信息',
  cost: '成本法投资',
  equity_inv: '权益法投资',
  net_asset: '被投资单位净资产',
}

const targetRows = computed(() => {
  const counts = linkage.preview.value?.counts ?? {}
  return Object.entries(counts).map(([key, c]) => ({
    label: SHEET_LABELS[key] ?? key,
    candidate: c?.candidate ?? 0,
    importable: c?.importable ?? 0,
  }))
})

async function handleOpen(): Promise<void> {
  visible.value = true
  await linkage.openPreview()
}

async function handleImport(): Promise<void> {
  const ok = await linkage.confirmImport()
  if (ok) {
    visible.value = false
    // 通知两侧 stale 常驻提示刷新（main 主入口 / ConsolWorksheetTabs）
    window.dispatchEvent(new CustomEvent('g7:linkage-changed'))
  }
}
</script>

<style scoped>
.g7-linkage-entry { display: inline-block; }
.stale-dot { margin-left: 2px; }
.cfg-error,
.stale-alert { margin-bottom: 12px; }
.preview-summary { margin-bottom: 12px; }
.target-table { margin-bottom: 10px; }
.unresolved-list { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; font-size: 12px; }
.ul-label { color: #909399; }
</style>
