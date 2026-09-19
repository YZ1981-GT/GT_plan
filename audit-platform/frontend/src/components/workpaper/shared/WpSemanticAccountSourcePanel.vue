<script setup lang="ts">
/**
 * WpSemanticAccountSourcePanel — 语义科目定位溯源面板（平台共用，纯展示）
 *
 * 消费各循环 render 下发的 `html_data.tb_source_codes`（`semantic_account_resolver`
 * 口径）。让审计师在底稿当页就能回答「这个数是从哪个科目来的、为什么是这个科目」：
 *
 * - 每个语义槽的**命中科目码 + 科目名 + 命中来源**（客户科目表 / 标准科目表 / 兜底）
 * - `found=false` 显式显示「本项目无此科目」，**不伪装成 0**
 * - `exact=false`（包含匹配）打提示，要求审计师复核
 * - `report_config` 给的码与按名称定位结果**冲突**时橙色告警
 *   （平台实证 `report_config` 存在错码，故报表公式只作提示不作定位依据）
 * - 旧准则同族科目列为「待人工映射」（跨准则拆分是会计判断，平台不猜）
 * - 「叶子和 == 父科目额」两口径自检，不等时两个数都暴露
 *
 * 逻辑在 `composables/shared/semanticAccountSource.ts`（零 Vue 依赖纯函数、可单测）。
 */
import { computed, inject } from 'vue'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import {
  hasSemanticAccountSource,
  normalizeSemanticAccountSource,
  semanticConflictRows,
  semanticParentDiffCount,
  semanticSlotRows,
  semanticUnmappedRows,
} from '../composables/shared/semanticAccountSource'

const props = withDefaults(
  defineProps<{
    /** render 下发的 `html_data.tb_source_codes` 原始对象 */
    source?: unknown
    /** 槽 key 展示顺序（循环声明） */
    slotOrder?: string[]
    /** 槽 key → 中文名兜底（后端已给 label 时优先后端） */
    slotLabels?: Record<string, string>
    /** 面板标题 */
    title?: string
    /** 顶部说明（循环专属口径提示） */
    hint?: string
    defaultExpanded?: boolean
  }>(),
  {
    slotOrder: () => [],
    slotLabels: () => ({}),
    title: '四表取数科目溯源',
    hint: '',
    defaultExpanded: false,
  },
)

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

const src = computed(() => normalizeSemanticAccountSource(props.source))
const visible = computed(() => hasSemanticAccountSource(src.value))
const rows = computed(() => semanticSlotRows(src.value, props.slotOrder, props.slotLabels))
const conflicts = computed(() => semanticConflictRows(src.value))
const unmapped = computed(() => semanticUnmappedRows(src.value))
const parentDiffCount = computed(() => semanticParentDiffCount(src.value))
const foundCount = computed(() => rows.value.filter((r) => r.found).length)
const fuzzyCount = computed(() => rows.value.filter((r) => r.found && !r.exact).length)
</script>

<template>
  <details v-if="visible" class="wp-sem-source" :open="defaultExpanded">
    <summary>
      🔗 {{ title }}
      <el-tag size="small" type="success" effect="plain">
        命中 {{ foundCount }}/{{ rows.length }} 项
      </el-tag>
      <el-tag v-if="src.row_code" size="small" type="info" effect="plain">
        报表行 {{ src.row_code }}
      </el-tag>
      <el-tag v-if="conflicts.length" size="small" type="warning" effect="plain">
        {{ conflicts.length }} 项与报表公式不一致
      </el-tag>
      <el-tag v-if="parentDiffCount" size="small" type="danger" effect="plain">
        {{ parentDiffCount }} 项叶子和≠父额
      </el-tag>
    </summary>

    <div class="sem-body">
      <div v-if="hint" class="sem-hint">{{ hint }}</div>
      <div v-if="!src.chart_available" class="sem-warn">
        ⚠️ 本项目科目表未导入或不可用 —— 以下科目码全部来自兜底口径，请先导入科目表后重新取数。
      </div>

      <el-table :data="rows" border size="small" style="width: 100%" max-height="320">
        <el-table-column label="列报项目" min-width="150">
          <template #default="{ row }">
            <span class="sem-label">{{ row.label }}</span>
            <el-tag v-if="!row.found" size="small" type="info" effect="plain" class="sem-tag">
              本项目无此科目
            </el-tag>
            <el-tooltip
              v-else-if="!row.exact"
              content="按科目名「包含匹配」命中（非精确同名），请复核归属是否正确"
              placement="top"
            >
              <el-tag size="small" type="warning" effect="plain" class="sem-tag">需复核</el-tag>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="命中科目（原始码）" min-width="170">
          <template #default="{ row }">
            <code class="sem-code">{{ row.codesText }}</code>
          </template>
        </el-table-column>
        <el-table-column label="科目名称" min-width="180">
          <template #default="{ row }">{{ row.matchedNames }}</template>
        </el-table-column>
        <el-table-column label="标准码" min-width="120">
          <template #default="{ row }">
            <code class="sem-code">{{ row.standardCodesText }}</code>
          </template>
        </el-table-column>
        <el-table-column label="定位来源" width="120" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.resolvedFromTag" effect="plain">
              {{ row.resolvedFromLabel }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="src.formula" class="sem-formula-row">
        <span class="sem-formula-label">报表公式（仅提示，不作定位依据）：</span>
        <code class="sem-formula">{{ src.formula }}</code>
      </div>

      <div v-if="conflicts.length" class="sem-warn">
        ⚠️ 报表公式给的科目码与按科目名在本项目定位的结果不一致（平台实证 `report_config`
        存在错码，故以按名称定位为准，此处仅提示复核）：
        <ul class="sem-list">
          <li v-for="c in conflicts" :key="`${c.slotKey}-${c.reportCode}`">
            {{ c.slotKey }}：报表公式 <code>{{ c.reportCode }}</code> ↔ 实际
            <code>{{ c.actualCode }}</code>
          </li>
        </ul>
      </div>

      <div v-if="unmapped.length" class="sem-warn">
        ⚠️ 本项目存在同族**旧准则**科目，跨准则拆分属会计判断、平台不自动归属，请人工映射：
        <ul class="sem-list">
          <li v-for="u in unmapped" :key="u.code">
            <code>{{ u.code }}</code> {{ u.name }}
          </li>
        </ul>
      </div>

      <div v-if="parentDiffCount" class="sem-warn">
        ⚠️ 「叶子科目之和 ≠ 父科目余额」—— 通常意味着客户科目树被改动或数据集版本不一致，
        两个口径都列出供追溯（取数用的是**叶子**口径）：
        <ul class="sem-list">
          <template v-for="row in rows" :key="row.key">
            <li v-for="d in row.parentDiffs" :key="`${row.key}-${d.code}`">
              <code>{{ d.code }}</code>（{{ row.label }}）：叶子和
              {{ displayPrefs.fmtAmount(d.leaf) }} ｜ 父科目 {{ displayPrefs.fmtAmount(d.parent) }}
              ｜ 差异 {{ displayPrefs.fmtAmount(d.diff) }}
            </li>
          </template>
        </ul>
      </div>

      <div v-if="fuzzyCount" class="sem-hint">
        提示：{{ fuzzyCount }} 项走的是科目名「包含匹配」，请复核归属；精确同名的项目无需处理。
      </div>
    </div>
  </details>
</template>

<style scoped>
.wp-sem-source {
  margin-bottom: 12px;
  border: 1px solid #d9ecff;
  border-left: 3px solid #409eff;
  background: #f4f9ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.wp-sem-source summary {
  cursor: pointer;
  font-weight: 600;
  color: #337ecc;
  font-size: var(--wp-font-size, 13px);
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.sem-body { margin-top: 10px; }
.sem-hint {
  font-size: 12px;
  color: #606266;
  line-height: 1.6;
  margin-bottom: 8px;
}
.wp-sem-source :deep(.el-table),
.wp-sem-source :deep(.el-table th),
.wp-sem-source :deep(.el-table td),
.wp-sem-source :deep(.el-table .cell) {
  font-size: 13px;
}
.sem-label { font-weight: 600; color: #303133; }
.sem-tag { margin-left: 6px; }
.sem-code {
  font-family: 'Consolas', monospace;
  font-size: 12px;
  color: #409eff;
  background: #ecf5ff;
  padding: 1px 6px;
  border-radius: 3px;
}
.sem-formula-row {
  margin-top: 8px;
  font-size: 12px;
  color: #606266;
  line-height: 1.8;
}
.sem-formula-label { margin-right: 4px; }
.sem-formula {
  font-family: 'Consolas', monospace;
  font-size: 12px;
  color: #67c23a;
  background: #f0f9eb;
  padding: 1px 6px;
  border-radius: 3px;
}
.sem-warn {
  margin-top: 8px;
  font-size: 12px;
  color: #b88230;
  background: #fdf6ec;
  border-left: 3px solid #e6a23c;
  border-radius: 3px;
  padding: 6px 10px;
  line-height: 1.7;
}
.sem-list { margin: 4px 0 0; padding-left: 18px; }
</style>
