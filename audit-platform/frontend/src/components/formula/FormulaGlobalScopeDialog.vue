<!--
  全局公式总览弹窗（从 FormulaManagerDialog 拆出；优化建议 #1 面板拆分 Phase 2）。
  展示项目级公式（7 类作用域分组）+ 项目级 vs 主模板差异对比 + 报表预设/附注预设快捷入口。
-->
<template>
  <el-dialog
    v-model="visible"
    title="🌐 全局公式管理 — 跨作用域总览"
    width="88%"
    top="3vh"
    append-to-body
    destroy-on-close
    class="gt-fm-global-scope"
  >
    <div style="margin-bottom: 8px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary);">
      本页统计的是<strong>项目级公式</strong>（存储于 wp_formula，按底稿编码派生 7 类作用域），共 {{ totalCount }} 条。各作用域公式集互不串扰。
    </div>
    <el-alert type="info" :closable="false" show-icon
      title="报表 / 附注预设是模板级，不计入本页统计"
      description="报表预设存于 report_config（按适用准则共用，报表引擎直接消费），附注校验预设存于附注预设集；两者不会被复制进项目。要查看或修改它们，用下面的按钮跳到对应节点，或打开「📊 公式看板」按域总览。"
      style="margin-bottom: 10px;" />
    <div style="margin-bottom: 10px; display: flex; gap: 8px; flex-wrap: wrap;">
      <el-button size="small" plain @click="$emit('go-report-presets')">📄 查看报表预设（模板级）</el-button>
      <el-button size="small" plain @click="$emit('go-note-presets')">📝 查看附注预设（模板级）</el-button>
      <el-button size="small" plain @click="$emit('open-dashboard')">📊 打开公式看板</el-button>
    </div>

    <!-- 项目级 vs 主模板差异 -->
    <div class="gt-fm-master-diff">
      <div class="gt-fm-master-diff__head">
        <span class="gt-fm-master-diff__title">项目级 ↔ 主模板差异</span>
        <el-tag v-if="masterDiffLoaded" size="small" :type="filteredDiff.length ? 'warning' : 'success'" effect="plain">
          {{ filteredDiff.length }} 条
        </el-tag>
        <span v-if="masterDiffStandard" class="gt-fm-master-diff__std">对比准则：{{ masterDiffStandard }}</span>
        <el-checkbox v-if="masterDiffLoaded" v-model="onlyFormula" size="small">
          只看公式差异（全部 {{ masterDiffAll.length }} 条）
        </el-checkbox>
        <el-button size="small" link type="primary" :loading="masterDiffLoading" @click="$emit('load-diff')">
          {{ masterDiffLoaded ? '重新比对' : '开始比对' }}
        </el-button>
        <el-button v-if="masterDiffLoaded" size="small" link type="primary" :loading="masterDiffApplying"
          @click="$emit('apply-master')">⬇ 同步主模板更新到本项目</el-button>
      </div>
      <div v-if="!masterDiffLoaded" class="gt-fm-master-diff__hint">
        比对本项目配置与主模板的公式差异：项目改对了可回流主模板，主模板更新了可同步下来。
      </div>
      <el-alert v-else-if="!filteredDiff.length" type="success" :closable="false" show-icon
        :title="masterDiffAll.length
          ? `无公式层面差异（另有 ${masterDiffAll.length} 条仅结构行差异）`
          : '项目级与主模板一致（或本项目尚未落入项目级配置）'"
        style="margin-bottom: 8px;" />
      <el-table v-else :data="filteredDiff.slice(0, 50)" size="small" border style="width: 100%; margin-bottom: 8px;"
        :header-cell-style="{ background: '#edf3f9', fontSize: '11px', whiteSpace: 'nowrap' }">
        <el-table-column prop="row_code" label="行次" width="100" />
        <el-table-column label="差异" width="110" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="diffTagType(row.diff_type)" effect="plain">{{ diffLabel(row.diff_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="项目级公式" min-width="200" show-overflow-tooltip>
          <template #default="{ row }"><code class="gt-fm-mono">{{ row.project_formula || '—' }}</code></template>
        </el-table-column>
        <el-table-column label="主模板公式" min-width="200" show-overflow-tooltip>
          <template #default="{ row }"><code class="gt-fm-mono">{{ row.master_formula || '—' }}</code></template>
        </el-table-column>
        <el-table-column label="操作" width="110" align="center">
          <template #default="{ row }">
            <el-button v-if="row.project_formula" size="small" link type="primary"
              @click="$emit('suggest-to-master', row)">回流主模板</el-button>
            <span v-else style="color: var(--gt-color-text-placeholder); font-size: var(--gt-font-size-xs);">—</span>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="filteredDiff.length > 50" class="gt-fm-master-diff__hint">
        仅展示前 50 条（共 {{ filteredDiff.length }} 条）。
      </div>
    </div>

    <!-- 项目级公式分域展示 -->
    <div v-if="!nonEmptyGroups.length" style="text-align: center; padding: 24px 20px;">
      <el-empty description="暂无公式" :image-size="80" style="margin-bottom: 16px;" />
      <div style="color: var(--gt-color-text-secondary); font-size: var(--gt-font-size-sm); margin-bottom: 20px; line-height: 1.8;">
        本项目尚无项目级公式。项目级公式在各底稿页新增，模板级预设请走上方按钮。
      </div>
      <div style="display: flex; flex-wrap: wrap; justify-content: center; gap: 12px;">
        <el-button type="primary" plain @click="$emit('go-report-presets')">📄 去报表预设（{{ reportPresetHint }}）</el-button>
        <el-button type="primary" plain @click="$emit('materialize-presets')">📥 把报表预设落入项目</el-button>
        <el-button plain @click="visible = false">✏️ 手动新增公式</el-button>
      </div>
    </div>
    <div v-else style="max-height: 72vh; overflow-y: auto;">
      <div v-for="group in groups" :key="group.scope" style="margin-bottom: 14px;">
        <div style="font-weight: 600; font-size: var(--gt-font-size-sm); margin-bottom: 6px;">
          {{ group.label }}
          <span style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-left: 6px;">{{ group.rows.length }} 条</span>
        </div>
        <div v-if="!group.rows.length" style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-placeholder); padding: 2px 0 6px;">
          本作用域暂无项目级公式
        </div>
        <el-table v-else :data="group.rows" size="small" border style="width: 100%;"
          :header-cell-style="{ background: '#edf3f9', fontSize: '11px', whiteSpace: 'nowrap' }">
          <el-table-column label="目标单元" prop="targetCell" min-width="150" show-overflow-tooltip>
            <template #default="{ row }"><span class="gt-fm-mono">{{ row.targetCell }}</span></template>
          </el-table-column>
          <el-table-column label="公式" prop="expression" min-width="240" show-overflow-tooltip>
            <template #default="{ row }"><code class="gt-fm-mono">{{ row.expression || '—' }}</code></template>
          </el-table-column>
          <el-table-column label="类型" width="110" align="center">
            <template #default="{ row }">
              <el-tag :type="categoryTagType(row.formulaType) || undefined" size="small">{{ categoryLabel(row.formulaType) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="来源地址" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">
              <span style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary);">{{ row.sourceLabel || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="最近计算" width="160" align="center">
            <template #default="{ row }">
              <span style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary);">{{ row.lastComputedAt || '尚未计算' }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

defineOptions({ name: 'FormulaGlobalScopeDialog' })

const visible = defineModel<boolean>({ default: false })

const props = defineProps<{
  totalCount: number
  groups: Array<{ scope: string; label: string; rows: any[] }>
  reportPresetHint: string
  categoryLabel: (cat: string) => string
  categoryTagType: (cat: string) => string
  masterDiffAll: any[]
  masterDiffStandard: string
  masterDiffLoaded: boolean
  masterDiffLoading: boolean
  masterDiffApplying: boolean
}>()

defineEmits<{
  'go-report-presets': []
  'go-note-presets': []
  'open-dashboard': []
  'load-diff': []
  'apply-master': []
  'suggest-to-master': [row: any]
  'materialize-presets': []
}>()

const onlyFormula = ref(true)

const filteredDiff = computed(() =>
  onlyFormula.value
    ? props.masterDiffAll.filter((r) => r.project_formula || r.master_formula)
    : props.masterDiffAll,
)

const nonEmptyGroups = computed(() => props.groups.filter((g) => g.rows.length > 0))

function diffLabel(t: string): string {
  const m: Record<string, string> = { added: '项目新增', removed: '项目删除', changed: '公式不同', structure: '结构差异' }
  return m[t] || t
}
function diffTagType(t: string): 'warning' | 'success' | 'info' {
  return ({ changed: 'warning', added: 'success' } as Record<string, 'warning' | 'success'>)[t] || 'info'
}
</script>
