<template>
  <el-dialog
    v-model="visible"
    title="导出附注离线编辑包"
    width="600px"
    :close-on-click-modal="false"
  >
    <!-- 导出范围 -->
    <el-form label-width="100px">
      <el-form-item label="导出范围">
        <el-radio-group v-model="exportScope">
          <el-radio value="all">全部章节</el-radio>
          <el-radio value="with_data">仅有数据章节</el-radio>
          <el-radio value="custom">自定义勾选</el-radio>
        </el-radio-group>
      </el-form-item>

      <!-- 章节多选树 -->
      <el-form-item v-if="exportScope === 'custom'" label="选择章节">
        <div style="width: 100%">
          <div style="margin-bottom: 6px; display: flex; gap: 8px; align-items: center;">
            <el-button size="small" text @click="checkAll(true)">全选</el-button>
            <el-button size="small" text @click="checkAll(false)">全不选</el-button>
            <el-button size="small" text @click="toggleExpandAll">{{ expandedAll ? '收起' : '展开' }}全部</el-button>
            <span style="margin-left: auto; font-size: 12px; color: var(--gt-color-text-tertiary)">
              已选 {{ checkedCount }} 节
            </span>
          </div>
          <el-tree
            ref="treeRef"
            :data="sectionTree"
            show-checkbox
            node-key="section_id"
            :default-checked-keys="defaultChecked"
            :default-expand-all="expandedAll"
            :props="{ label: 'title', children: 'children' }"
            style="max-height: 320px; overflow-y: auto; width: 100%; border: 1px solid var(--gt-color-border, #d8b8ee); border-radius: 4px; padding: 6px"
            @check="onTreeCheck"
          />
        </div>
      </el-form-item>

      <!-- 导出内容选项 -->
      <el-form-item label="导出内容">
        <el-checkbox v-model="options.includeFormulas">包含公式表达式</el-checkbox>
        <el-checkbox v-model="options.includeProvenance">包含数据源溯源</el-checkbox>
      </el-form-item>

      <!-- 加密选项 -->
      <el-form-item label="文件加密">
        <el-switch v-model="options.encrypt" />
        <el-input
          v-if="options.encrypt"
          v-model="options.password"
          type="password"
          placeholder="设置密码（通过其他渠道告知接收方）"
          style="margin-top: 8px; width: 100%"
          show-password
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="exporting" @click="handleExport">
        导出
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'

interface Props {
  modelValue: boolean
  projectId: string
  year: number
  sections: Array<{ section_id: string; title: string; has_data?: boolean }>
}

const props = defineProps<Props>()
const emit = defineEmits<{ 'update:modelValue': [val: boolean] }>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const treeRef = ref()
const exportScope = ref<'all' | 'with_data' | 'custom'>('all')
const exporting = ref(false)
const options = ref({
  includeFormulas: true,
  includeProvenance: true,
  encrypt: false,
  password: '',
})

const sectionTree = computed(() => buildSectionTree(props.sections))

/**
 * 把扁平章节列表按"章节号前缀"组装成两级树。
 * note_section（=section_id）形如：`四`（一级章）/ `四、会计期间`（四的子节）。
 * 规则：取第一个「、」前的中文章节号作为分组键；裸章节号作为父节点，
 * `X、xxx` 归到父 X 下。无法解析的（无「、」且非已知父）单独成顶层叶子。
 * 父节点 section_id 用 `__group__:前缀`，避免与真实章节 id 冲突；
 * 仅当有真实裸章节行时复用其真实 id（保证勾选父=勾选该章节本身）。
 */
function buildSectionTree(
  sections: Array<{ section_id: string; title: string; has_data?: boolean }>,
) {
  const splitPrefix = (code: string): string => {
    const idx = code.search(/[、，]/)
    return idx > 0 ? code.slice(0, idx) : code
  }
  // 保持入参顺序（父级已按 sort_order 由后端/上游排好）
  const groups: Array<{
    key: string
    parent: { section_id: string; title: string } | null
    children: Array<{ section_id: string; title: string }>
  }> = []
  const groupIndex = new Map<string, number>()

  const ensureGroup = (key: string) => {
    if (!groupIndex.has(key)) {
      groupIndex.set(key, groups.length)
      groups.push({ key, parent: null, children: [] })
    }
    return groups[groupIndex.get(key)!]
  }

  for (const s of sections) {
    const code = s.section_id || ''
    const prefix = splitPrefix(code)
    const g = ensureGroup(prefix)
    const isBareChapter = code === prefix // 形如 `四`，章节本身
    if (isBareChapter) {
      g.parent = { section_id: s.section_id, title: s.title }
    } else {
      g.children.push({ section_id: s.section_id, title: s.title })
    }
  }

  return groups.map((g) => {
    // 无子节点 → 单章节直接作叶子（避免出现只有父无子的空壳分组）
    if (g.children.length === 0 && g.parent) {
      return { section_id: g.parent.section_id, title: g.parent.title }
    }
    // 有子节点：父节点 id 复用真实裸章节 id；无裸章节行时用合成分组 id
    const parentId = g.parent?.section_id ?? `__group__:${g.key}`
    const parentTitle = g.parent?.title ?? g.key
    return {
      section_id: parentId,
      title: parentTitle,
      children: g.children,
    }
  })
}

/** 仅真实章节 id（排除合成分组父节点），用于默认全选 + 提交过滤 */
const realSectionIds = computed(() =>
  props.sections.map((s) => s.section_id),
)

const defaultChecked = computed(() => realSectionIds.value)

const expandedAll = ref(true)
const checkedCount = ref(realSectionIds.value.length)

function checkAll(checked: boolean) {
  if (!treeRef.value) return
  treeRef.value.setCheckedKeys(checked ? realSectionIds.value : [])
  refreshCheckedCount()
}

function toggleExpandAll() {
  expandedAll.value = !expandedAll.value
  // el-tree 无直接 API，重建展开状态：遍历 store nodes
  const store = treeRef.value?.store
  if (store) {
    Object.values(store.nodesMap || {}).forEach((n: any) => {
      n.expanded = expandedAll.value
    })
  }
}

function onTreeCheck() {
  refreshCheckedCount()
}

/** 统计真实章节选中数（排除合成分组父节点 __group__:） */
function refreshCheckedCount() {
  if (!treeRef.value) { checkedCount.value = 0; return }
  const keys: string[] = treeRef.value.getCheckedKeys(false) || []
  checkedCount.value = keys.filter((k) => !String(k).startsWith('__group__:')).length
}

// 切到自定义时刷新一次计数
watch(exportScope, (v) => {
  if (v === 'custom') {
    setTimeout(refreshCheckedCount, 0)
  }
})

async function handleExport() {
  exporting.value = true
  try {
    let sectionIds: string[] | undefined
    if (exportScope.value === 'custom' && treeRef.value) {
      // 排除合成分组父节点（__group__:），只提交真实章节 id
      const checked: string[] = treeRef.value.getCheckedKeys(false) || []
      sectionIds = checked.filter((k) => !String(k).startsWith('__group__:'))
    } else if (exportScope.value === 'with_data') {
      sectionIds = props.sections.filter(s => s.has_data).map(s => s.section_id)
    }

    const resp = await api.post(
      `/api/disclosure-notes/${props.projectId}/${props.year}/offline-export`,
      {
        section_ids: sectionIds,
        include_formulas: options.value.includeFormulas,
        include_provenance: options.value.includeProvenance,
        password: options.value.encrypt ? options.value.password : undefined,
      },
      { responseType: 'blob' }
    )

    // Download file
    const blob = new Blob([resp as any], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `附注离线编辑包_${props.year}.xlsx`
    a.click()
    URL.revokeObjectURL(url)

    ElMessage.success('导出成功')
    visible.value = false
  } catch (e: any) {
    handleApiError(e, '导出')
  } finally {
    exporting.value = false
  }
}
</script>
