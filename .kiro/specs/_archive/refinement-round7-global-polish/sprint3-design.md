# Sprint 3（P2）设计文档

## D1：全局组件铺设模式

每个视图改造遵循统一模板：

```vue
<template>
  <div class="gt-xxx gt-fade-in">
    <!-- 第一行：横幅 -->
    <GtPageHeader :title="pageTitle" :show-sync-status="true" @back="router.push('/projects')">
      <GtInfoBar :show-unit="true" :show-year="true" />
      <template #actions>
        <GtToolbar
          :show-copy="true"
          :show-fullscreen="true"
          :show-export="true"
          :show-edit-toggle="true"
          :is-editing="editMode.isEditing"
          @copy="onCopy"
          @fullscreen="toggleFullscreen()"
          @export="onExport"
          @edit-toggle="editMode.toggle()"
        >
          <template #left>
            <!-- 模块特有按钮 -->
          </template>
        </GtToolbar>
      </template>
    </GtPageHeader>

    <!-- 第二行：联动状态横条（按需） -->
    <LinkageStatusBar v-if="hasStaleData" :stale-count="staleCount" @recalc="onRecalcAll" />

    <!-- 第三行：搜索/筛选 -->
    <TableSearchBar v-model="searchText" @search="onSearch" />

    <!-- 主体 -->
    <GtEditableTable ... />
    <!-- 或 el-table（只读展示） -->

    <!-- 底部 -->
    <SelectionBar :stats="selectionStats" />
  </div>
</template>
```

## D2：statusMaps 收敛步骤

1. 后端 `core/dicts.py` 或 seed 文件补齐 9 套字典
2. 前端 `GtStatusTag.vue` 简化为：
```ts
const resolvedLabel = computed(() => dictStore.label(props.dictKey, props.value))
const resolvedType = computed(() => dictStore.type(props.dictKey, props.value))
```
3. 删除 `utils/statusMaps.ts`
4. 删除 GtStatusTag 的 `statusMap` / `statusMapName` props（breaking change，需全量替换）

## D3：QC 主工作台

文件：`views/qc/QcInspectionWorkbench.vue` 升级

```vue
<template>
  <div class="gt-qc-hub">
    <GtPageHeader title="质控工作台" />
    <el-tabs v-model="activeTab">
      <el-tab-pane label="待抽查项目" name="due">
        <QcDueProjects />
      </el-tab-pane>
      <el-tab-pane label="抽查执行" name="inspect">
        <!-- 现有 QcInspectionWorkbench 内容 -->
      </el-tab-pane>
      <el-tab-pane label="规则库" name="rules">
        <QcRuleList :embedded="true" />
      </el-tab-pane>
      <el-tab-pane label="案例库" name="cases">
        <QcCaseLibrary :embedded="true" />
      </el-tab-pane>
      <el-tab-pane label="年报" name="annual">
        <QcAnnualReports :embedded="true" />
      </el-tab-pane>
      <el-tab-pane label="客户趋势" name="trend">
        <ClientQualityTrend :embedded="true" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>
```

## D4：ShadowCompareRow

文件：`components/eqcr/ShadowCompareRow.vue`

```vue
<template>
  <el-table :data="rows" border size="small" style="width: 100%">
    <el-table-column label="维度" prop="dimension" width="160" />
    <el-table-column label="项目组值" prop="teamValue" width="140" align="right">
      <template #default="{ row }">
        <GtAmountCell :value="row.teamValue" />
      </template>
    </el-table-column>
    <el-table-column label="影子值" prop="shadowValue" width="140" align="right">
      <template #default="{ row }">
        <GtAmountCell :value="row.shadowValue" />
      </template>
    </el-table-column>
    <el-table-column label="差异" width="120" align="right">
      <template #default="{ row }">
        <span :class="{ 'gt-amount--negative': row.diff !== 0 }">
          {{ displayPrefs.fmt(row.diff) }} ({{ row.diffPct }}%)
        </span>
      </template>
    </el-table-column>
    <el-table-column label="判断" width="160">
      <template #default="{ row }">
        <el-button size="small" type="success" @click="$emit('verdict', row, 'pass')">通过</el-button>
        <el-button size="small" type="danger" @click="$emit('verdict', row, 'flag')">标记</el-button>
      </template>
    </el-table-column>
  </el-table>
</template>
```

## D5：usePenetrate composable

文件：`composables/usePenetrate.ts`

```ts
import { useRouter, useRoute } from 'vue-router'

export function usePenetrate() {
  const router = useRouter()
  const route = useRoute()
  const pid = () => route.params.projectId as string

  return {
    toLedger: (accountCode: string) =>
      router.push({ path: `/projects/${pid()}/ledger`, query: { code: accountCode } }),
    toWorkpaper: (wpCode: string) =>
      router.push({ path: `/projects/${pid()}/workpapers`, query: { code: wpCode } }),
    toReportRow: (type: string, rowCode: string) =>
      router.push({ path: `/projects/${pid()}/reports`, query: { tab: type, row: rowCode } }),
    toAdjustment: (groupId: string) =>
      router.push({ path: `/projects/${pid()}/adjustments`, query: { group: groupId } }),
    toMisstatement: (id: string) =>
      router.push({ path: `/projects/${pid()}/misstatements`, query: { id } }),
    toNote: (sectionId: string) =>
      router.push({ path: `/projects/${pid()}/disclosure-notes`, query: { section: sectionId } }),
  }
}
```

## D6：LinkageStatusBar

文件：`components/common/LinkageStatusBar.vue`

```vue
<template>
  <div v-if="staleCount > 0" class="gt-linkage-bar">
    <el-icon><WarningFilled /></el-icon>
    <span>当前项目有 {{ staleCount }} 处数据过期</span>
    <el-button size="small" type="primary" text @click="$emit('recalc')">一键重算</el-button>
    <el-button size="small" text @click="$emit('detail')">查看详情</el-button>
    <el-button size="small" text class="gt-linkage-bar__close" @click="dismissed = true">×</el-button>
  </div>
</template>
```

## D7：跨表核对

ReportView.vue 新增 Tab "跨表核对"：

核对等式清单（硬编码 7 条，后续可配置化）：
1. 利润表净利润 = 所有者权益变动表未分配利润本年增加
2. 现金流量表期末现金 = 资产负债表期末货币资金
3. 资产负债表资产合计 = 负债合计 + 所有者权益合计
4. 利润表营业收入 - 营业成本 - 三费 = 营业利润
5. 现金流量表三类活动净额合计 = 现金净增加额
6. 所有者权益变动表期末余额 = 资产负债表所有者权益各项
7. 利润表所得税费用 / 利润总额 ≈ 有效税率（容差 5%）

每条等式：左值 / 右值 / 差异 / 状态（✅ 平 / ❌ 不平）

## D8：WorkpaperSidePanel 接口

文件：`components/workpaper/WorkpaperSidePanel.vue`

```vue
<template>
  <div class="gt-wp-side-panel">
    <el-tabs v-model="activeTab" type="border-card" stretch>
      <el-tab-pane label="AI" name="ai">
        <AiAssistantSidebar :project-id="projectId" :wp-id="wpId" />
      </el-tab-pane>
      <el-tab-pane label="附件" name="attachments">
        <AttachmentDropZone :project-id="projectId" :wp-id="wpId" />
      </el-tab-pane>
      <el-tab-pane label="版本" name="versions">
        <slot name="versions">
          <VersionHistoryList :project-id="projectId" :wp-id="wpId" />
        </slot>
      </el-tab-pane>
      <el-tab-pane label="批注" name="annotations">
        <slot name="annotations">
          <AnnotationList :project-id="projectId" :wp-id="wpId" />
        </slot>
      </el-tab-pane>
      <el-tab-pane label="程序要求" name="requirements">
        <ProgramRequirementsSidebar :wp-code="wpCode" />
      </el-tab-pane>
      <el-tab-pane label="依赖" name="dependencies">
        <DependencyGraph :project-id="projectId" :wp-id="wpId" />
      </el-tab-pane>
      <el-tab-pane label="一致性" name="consistency">
        <DataConsistencyMonitor :project-id="projectId" :wp-id="wpId" />
      </el-tab-pane>
      <el-tab-pane label="提示" name="tips">
        <SmartTipList :project-id="projectId" :wp-id="wpId" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import AiAssistantSidebar from '@/components/workpaper/AiAssistantSidebar.vue'
import AttachmentDropZone from '@/components/workpaper/AttachmentDropZone.vue'
import ProgramRequirementsSidebar from '@/components/workpaper/ProgramRequirementsSidebar.vue'
import DependencyGraph from '@/components/workpaper/DependencyGraph.vue'
import DataConsistencyMonitor from '@/components/workpaper/DataConsistencyMonitor.vue'
import SmartTipList from '@/components/workpaper/SmartTipList.vue'

defineProps<{
  projectId: string
  wpId: string
  wpCode?: string
}>()

const activeTab = ref('ai')
</script>
```

接入方式（以 WorkpaperEditor 为例）：
```vue
<div class="gt-wp-editor-layout">
  <div class="gt-wp-editor-main">
    <!-- Univer 编辑器 -->
  </div>
  <WorkpaperSidePanel
    :project-id="projectId"
    :wp-id="wpId"
    :wp-code="wpDetail?.wp_code"
    class="gt-wp-editor-side"
  />
</div>
```

## D9：clients 表 DDL + 迁移脚本

Alembic 迁移文件：`backend/app/migrations/round7_clients_20260508.py`

```python
"""Round 7: clients 主数据 + project_tags"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'round7_clients_20260508'
down_revision = 'round7_section_progress_gin'  # 上一个迁移

def upgrade():
    # clients 表
    op.create_table(
        'clients',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('normalized_name', sa.String(200), nullable=False, index=True),
        sa.Column('industry', sa.String(100), nullable=True),
        sa.Column('listed', sa.Boolean, server_default='false'),
        sa.Column('parent_id', UUID(as_uuid=True), sa.ForeignKey('clients.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_clients_normalized_name', 'clients', ['normalized_name'], unique=True)

    # Project.client_id FK
    op.add_column('projects', sa.Column('client_id', UUID(as_uuid=True), sa.ForeignKey('clients.id'), nullable=True))

    # project_tags
    op.create_table(
        'project_tags',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tag', sa.String(50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_project_tags_project_tag', 'project_tags', ['project_id', 'tag'], unique=True)

def downgrade():
    op.drop_table('project_tags')
    op.drop_column('projects', 'client_id')
    op.drop_table('clients')
```

迁移脚本 `scripts/migrate_clients.py`：
```python
"""从 Project.client_name 抽取去重生成 clients 记录，回填 project.client_id"""
# 1. SELECT DISTINCT client_name FROM projects WHERE client_name IS NOT NULL
# 2. 对每个 client_name 调用 normalize_client_name() 去重
# 3. INSERT INTO clients (name, normalized_name)
# 4. UPDATE projects SET client_id = clients.id WHERE normalize(client_name) = clients.normalized_name
```

## D10：usePasteImport 接口

文件：`composables/usePasteImport.ts`

```ts
import { onMounted, onUnmounted, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'

export interface PasteImportOptions {
  /** 表格容器 ref（监听 paste 事件） */
  containerRef: Ref<HTMLElement | null>
  /** 当前表格数据（用于判断插入位置） */
  tableData: Ref<Record<string, any>[]>
  /** 列定义（key + label），用于映射粘贴列 */
  columns: { key: string; label: string }[]
  /** 粘贴后回调：接收解析后的行数据 */
  onInsert: (rows: Record<string, any>[]) => Promise<void>
  /** 是否允许覆盖已有行（默认 false，只追加） */
  allowOverwrite?: boolean
}

export function usePasteImport(options: PasteImportOptions) {
  function onPaste(e: ClipboardEvent) {
    const text = e.clipboardData?.getData('text/plain')
    if (!text) return

    // 解析制表符分隔文本
    const lines = text.split('\n').filter(l => l.trim())
    const rows = lines.map(line => {
      const cells = line.split('\t')
      const row: Record<string, any> = {}
      options.columns.forEach((col, i) => {
        if (cells[i] !== undefined) row[col.key] = cells[i].trim()
      })
      return row
    })

    if (rows.length === 0) return

    // 确认弹窗
    ElMessageBox.confirm(
      `检测到粘贴 ${rows.length} 行数据，是否追加到表格末尾？`,
      '粘贴导入',
      { confirmButtonText: '追加', cancelButtonText: '取消', type: 'info' }
    ).then(() => {
      options.onInsert(rows)
    }).catch(() => {})

    e.preventDefault()
  }

  onMounted(() => {
    options.containerRef.value?.addEventListener('paste', onPaste)
  })
  onUnmounted(() => {
    options.containerRef.value?.removeEventListener('paste', onPaste)
  })
}
```
