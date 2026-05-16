<!--
  EnumDictTab.vue — 全局枚举字典 Tab [template-library-coordination Sprint 6 Task 6.1]

  需求 21.1-21.6：
  - 集中展示全部系统枚举字典（GET /api/system/dicts），按字典分组
  - 每个枚举项显示：value/label/color(预览)/sort_order/引用计数
  - 引用计数从 GET /api/system/dicts/{key}/usage-count 动态加载
  - admin/partner 可编辑（v-permission），但当前 _DICTS 硬编码在代码中：
      → 编辑/新增/删除按钮显示 + 提示"枚举字典硬编码在 system_dicts.py，需修改源码并重启"
      → 通过 PUT/POST/DELETE 端点（返回 405）测试一致性

  D13 ADR：当前 _DICTS 是代码定义的硬编码资源（非 JSON 源也非 DB 表），
  视为"代码源"只读。任何 mutation 端点返回 405 + ENUM_DICT_HARDCODED hint。
-->
<template>
  <div class="gt-edt">
    <!-- 顶部工具栏 -->
    <div class="gt-edt-toolbar">
      <span class="gt-edt-stats-item">
        总字典：<span class="gt-amt">{{ dictKeys.length }}</span>
      </span>
      <span class="gt-edt-stats-item">
        总枚举值：<span class="gt-amt">{{ totalEntries }}</span>
      </span>
      <div class="gt-edt-spacer" />
      <el-input
        v-model="searchInput"
        size="small"
        placeholder="搜索字典名 / 枚举 value / label"
        clearable
        class="gt-edt-search"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      <el-button
        size="small"
        :loading="loading"
        @click="refreshAll"
        round
      >
        <el-icon style="margin-right: 4px"><Refresh /></el-icon>
        刷新
      </el-button>
    </div>

    <!-- 只读提示横幅（D13 ADR） -->
    <el-alert
      type="info"
      :closable="false"
      class="gt-edt-banner"
      show-icon
    >
      <template #title>
        <span>枚举字典当前为代码定义（<code>backend/app/routers/system_dicts.py</code> 中的 <code>_DICTS</code>）</span>
      </template>
      <template #default>
        <div class="gt-edt-banner-body">
          如需新增/修改/禁用枚举值请提交 PR 编辑源码后重启后端。已被引用的值（引用计数 > 0）不允许物理删除。
        </div>
      </template>
    </el-alert>

    <!-- 字典分组列表（el-collapse） -->
    <div v-loading="loading" class="gt-edt-body">
      <el-empty
        v-if="!loading && filteredDicts.length === 0"
        :description="dictKeys.length === 0 ? '暂无字典数据' : '未匹配到字典'"
      />
      <el-collapse
        v-else
        v-model="expandedKeys"
        class="gt-edt-collapse"
      >
        <el-collapse-item
          v-for="dictKey in filteredDicts"
          :key="dictKey"
          :name="dictKey"
        >
          <template #title>
            <span class="gt-edt-dict-title">
              <el-icon><CollectionTag /></el-icon>
              <code class="gt-edt-dict-key">{{ dictKey }}</code>
              <span class="gt-edt-dict-label">{{ dictLabels[dictKey] || dictKey }}</span>
              <el-tag size="small" type="info" effect="plain" round>
                {{ dictData[dictKey]?.length || 0 }} 项
              </el-tag>
              <el-tag
                v-if="usageCountsLoaded[dictKey]"
                size="small"
                effect="light"
                round
                style="margin-left: 4px"
              >
                总引用 {{ totalUsageOfDict(dictKey) }}
              </el-tag>
            </span>
          </template>
          <el-table
            :data="filteredEntries(dictKey)"
            size="small"
            :header-cell-style="{ background: '#f0edf5', color: '#303133', fontWeight: '600' }"
            class="gt-edt-table"
          >
            <el-table-column label="排序" width="70" align="right">
              <template #default="{ $index }">
                <span class="gt-amt">{{ $index + 1 }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="value" label="value" min-width="180">
              <template #default="{ row }">
                <code class="gt-edt-value">{{ row.value }}</code>
              </template>
            </el-table-column>
            <el-table-column prop="label" label="label" min-width="160" />
            <el-table-column label="预览" width="120" align="center">
              <template #default="{ row }">
                <el-tag
                  :type="(row.color || 'info') as any"
                  size="small"
                  effect="light"
                  round
                >
                  {{ row.label }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="color" label="color (el-tag type)" width="160" align="center">
              <template #default="{ row }">
                <code class="gt-edt-color">{{ row.color || '(empty)' }}</code>
              </template>
            </el-table-column>
            <el-table-column label="引用计数" width="120" align="right">
              <template #default="{ row }">
                <template v-if="usageCountsLoaded[dictKey]">
                  <el-tag
                    v-if="(usageCountMap[dictKey]?.[row.value] || 0) > 0"
                    type="warning"
                    size="small"
                    effect="plain"
                    round
                    class="gt-amt"
                  >
                    {{ usageCountMap[dictKey]?.[row.value] || 0 }}
                  </el-tag>
                  <span v-else class="gt-amt gt-edt-em">0</span>
                </template>
                <el-button
                  v-else
                  link
                  size="small"
                  :loading="loadingUsage[dictKey]"
                  @click="loadUsageCount(dictKey)"
                >
                  加载
                </el-button>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="200" align="center" fixed="right">
              <template #default="{ row }">
                <el-tooltip
                  content="枚举字典硬编码在 system_dicts.py 中，需修改源码并重启后端"
                  placement="top"
                >
                  <span>
                    <el-button
                      size="small"
                      link
                      type="primary"
                      disabled
                    >编辑</el-button>
                  </span>
                </el-tooltip>
                <el-tooltip
                  :content="(usageCountMap[dictKey]?.[row.value] || 0) > 0
                    ? '该值已被引用，不允许删除'
                    : '枚举字典硬编码，无法删除'"
                  placement="top"
                >
                  <span>
                    <el-button
                      size="small"
                      link
                      type="danger"
                      disabled
                    >删除</el-button>
                  </span>
                </el-tooltip>
              </template>
            </el-table-column>
          </el-table>
        </el-collapse-item>
      </el-collapse>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Search, Refresh, CollectionTag } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import { systemDicts as P_dicts } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'

interface DictEntry {
  value: string
  label: string
  color: string
}
interface UsageCountItem {
  value: string
  count: number
}

// ─── 状态 ───
const loading = ref(false)
const dictData = ref<Record<string, DictEntry[]>>({})
const usageCountMap = ref<Record<string, Record<string, number>>>({})
const usageCountsLoaded = ref<Record<string, boolean>>({})
const loadingUsage = ref<Record<string, boolean>>({})
const expandedKeys = ref<string[]>([])
const searchInput = ref('')

// 字典分组的中文标签（与后端 _DICTS 同步维护）
const dictLabels: Record<string, string> = {
  wp_status: '底稿状态',
  wp_review_status: '底稿复核状态',
  adjustment_status: '调整分录状态',
  report_status: '审计报告状态',
  template_status: '模板状态',
  project_status: '项目状态',
  issue_status: '工单状态',
  pdf_task_status: 'PDF 任务状态',
  workhour_status: '工时状态',
}

const dictKeys = computed(() => Object.keys(dictData.value).sort())
const totalEntries = computed(() =>
  Object.values(dictData.value).reduce((sum, list) => sum + list.length, 0),
)

const filteredDicts = computed(() => {
  const kw = searchInput.value.trim().toLowerCase()
  if (!kw) return dictKeys.value
  return dictKeys.value.filter(
    (k) =>
      k.toLowerCase().includes(kw) ||
      (dictLabels[k] || '').toLowerCase().includes(kw) ||
      (dictData.value[k] || []).some(
        (e) =>
          e.value.toLowerCase().includes(kw) ||
          (e.label || '').toLowerCase().includes(kw),
      ),
  )
})

function filteredEntries(dictKey: string): DictEntry[] {
  const kw = searchInput.value.trim().toLowerCase()
  const entries = dictData.value[dictKey] || []
  if (!kw) return entries
  // 字典 key 命中时返回完整列表，否则按 value/label 过滤
  if (
    dictKey.toLowerCase().includes(kw) ||
    (dictLabels[dictKey] || '').toLowerCase().includes(kw)
  ) {
    return entries
  }
  return entries.filter(
    (e) =>
      e.value.toLowerCase().includes(kw) || (e.label || '').toLowerCase().includes(kw),
  )
}

function totalUsageOfDict(dictKey: string): number {
  const m = usageCountMap.value[dictKey]
  if (!m) return 0
  return Object.values(m).reduce((sum, n) => sum + (n || 0), 0)
}

// ─── 数据加载 ───
async function loadDicts() {
  loading.value = true
  try {
    const data = await api.get(P_dicts.list)
    if (data && typeof data === 'object') {
      dictData.value = data as Record<string, DictEntry[]>
    }
  } catch (e: any) {
    handleApiError(e, '加载枚举字典')
  } finally {
    loading.value = false
  }
}

async function loadUsageCount(dictKey: string) {
  if (loadingUsage.value[dictKey] || usageCountsLoaded.value[dictKey]) return
  loadingUsage.value[dictKey] = true
  try {
    const list = await api.get<UsageCountItem[]>(P_dicts.usageCount(dictKey))
    const map: Record<string, number> = {}
    if (Array.isArray(list)) {
      for (const item of list) {
        map[item.value] = item.count
      }
    }
    usageCountMap.value[dictKey] = map
    usageCountsLoaded.value[dictKey] = true
  } catch (e: any) {
    handleApiError(e, `加载 ${dictKey} 引用计数`)
  } finally {
    loadingUsage.value[dictKey] = false
  }
}

async function refreshAll() {
  // 清除引用计数缓存，强制重新拉
  usageCountsLoaded.value = {}
  usageCountMap.value = {}
  await loadDicts()
}

onMounted(() => {
  loadDicts()
})
</script>

<style scoped>
.gt-edt {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
  height: 100%;
}
.gt-edt-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: var(--gt-color-bg-white);
  border-radius: 6px;
  border: 1px solid #ebeef5;
}
.gt-edt-stats-item { font-size: var(--gt-font-size-sm); color: var(--gt-color-text-regular); }
.gt-edt-spacer { flex: 1; }
.gt-edt-search { width: 280px; }
.gt-amt {
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  font-weight: 600;
}
.gt-edt-em { color: var(--gt-color-text-placeholder); font-weight: 400; }

.gt-edt-banner {
  margin: 0;
}
.gt-edt-banner code {
  background: rgba(75, 45, 119, 0.08);
  padding: 1px 6px;
  border-radius: 4px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-primary);
}
.gt-edt-banner-body { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-regular); }

.gt-edt-body { flex: 1; min-height: 0; overflow: auto; }
.gt-edt-collapse { border: none; }
.gt-edt-collapse :deep(.el-collapse-item__header) {
  padding: 0 12px;
  background: var(--gt-color-bg);
  border-bottom: 1px solid #ebeef5;
}
.gt-edt-dict-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: var(--gt-font-size-sm);
}
.gt-edt-dict-key {
  font-family: 'JetBrains Mono', Menlo, Consolas, monospace;
  background: var(--gt-color-primary-bg);
  padding: 2px 8px;
  border-radius: 4px;
  color: var(--gt-color-primary);
  font-weight: 600;
}
.gt-edt-dict-label { color: var(--gt-color-text-primary); }

.gt-edt-table { margin: 0 0 8px 0; }
.gt-edt-value {
  font-family: 'JetBrains Mono', Menlo, Consolas, monospace;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-primary);
}
.gt-edt-color {
  font-family: 'JetBrains Mono', Menlo, Consolas, monospace;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-info);
}
</style>
