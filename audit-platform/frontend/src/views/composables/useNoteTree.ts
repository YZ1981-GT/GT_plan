/**
 * useNoteTree — 附注章节树加载、拖拽排序、节点选中相关逻辑
 *
 * 从 DisclosureEditor.vue 抽取，保持原有语义不变。
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { getDisclosureNoteTree, type DisclosureNoteTreeItem } from '@/services/auditPlatformApi'
import { api } from '@/services/apiProxy'
import { withLoading } from '@/composables/useLoading'
import { handleApiError } from '@/utils/errorHandler'

export interface TreeNode {
  id: string
  label: string
  data?: any
  children?: TreeNode[]
  isGroup?: boolean
}

export interface UseNoteTreeOptions {
  projectId: ComputedRef<string> | Ref<string>
  year: ComputedRef<number> | Ref<number>
  templateType: Ref<string>
  isEqcrRole: ComputedRef<boolean>
  /** Called after fetchTree succeeds to refresh section numbering */
  onTreeLoaded?: () => void
}

export interface UseNoteTreeReturn {
  noteList: Ref<DisclosureNoteTreeItem[]>
  treeLoading: Ref<boolean>
  treeSearch: Ref<string>
  noteTreeRef: Ref<any>
  treeViewMode: Ref<'tree' | 'flat'>
  treeData: ComputedRef<TreeNode[]>
  filteredTreeData: ComputedRef<TreeNode[]>
  flatNoteList: ComputedRef<DisclosureNoteTreeItem[]>
  fetchTree: () => Promise<void>
  allowTreeDrop: (draggingNode: any, dropNode: any, type: 'prev' | 'next' | 'inner') => boolean
  onTreeNodeDrop: (draggingNode: any, dropNode: any, dropType: 'before' | 'after' | 'inner', _evt: DragEvent) => Promise<void>
  expandAll: () => void
  collapseAll: () => void
}

// ─── 树分组常量 ─────────────────────────────────────────────────────────────────

const CHAPTER_GROUPS = [
  { prefix: '一' },
  { prefix: '二' },
  { prefix: '三' },
  { prefix: '四' },
  { prefix: '五' },
  { prefix: '六' },
  { prefix: '七' },
  { prefix: '八' },
  { prefix: '九' },
  { prefix: '十' },
  { prefix: '十一' },
  { prefix: '十二' },
  { prefix: '十三' },
  { prefix: '十四' },
  { prefix: '十五' },
  { prefix: '十六' },
  { prefix: '十七' },
]

// 国企版14章标题
const SOE_LABELS: Record<string, string> = {
  '一': '公司基本情况', '二': '财务报表编制基础', '三': '遵循企业会计准则的声明',
  '四': '重要会计政策、会计估计', '五': '会计政策变更及差错更正', '六': '税项',
  '七': '企业合并及合并财务报表', '八': '财务报表主要项目注释',
  '九': '或有事项', '十': '资产负债表日后事项', '十一': '关联方关系及其交易',
  '十二': '母公司财务报表附注', '十三': '其他披露内容', '十四': '财务报表之批准',
}
// 上市版17章标题
const LISTED_LABELS: Record<string, string> = {
  '一': '公司基本情况', '二': '财务报表的编制基础', '三': '重要会计政策及会计估计',
  '四': '税项', '五': '合并财务报表项目附注', '六': '研发支出',
  '七': '在其他主体中的权益', '八': '政府补助', '九': '金融工具风险管理',
  '十': '公允价值', '十一': '关联方及关联交易', '十二': '股份支付',
  '十三': '承诺及或有事项', '十四': '资产负债表日后事项', '十五': '其他重要事项',
  '十六': '公司财务报表主要项目注释', '十七': '补充资料',
}

// 五章内按资产/负债/权益/损益/其他分组
const SECTION_GROUPS: Record<string, { label: string; range: [number, number] }> = {
  'asset': { label: '流动资产 + 非流动资产', range: [1, 15] },
  'liability': { label: '流动负债 + 非流动负债', range: [16, 23] },
  'equity': { label: '所有者权益', range: [24, 28] },
  'income': { label: '损益类', range: [29, 35] },
  'other': { label: '其他科目注释', range: [36, 79] },
  'disclosure': { label: '补充披露事项', range: [80, 199] },
}

// 会计政策分组关键词
const POLICY_GROUPS: Record<string, { label: string; keywords: string[] }> = {
  'basic': { label: '基础政策', keywords: ['会计期间', '记账本位币', '记账基础', '现金及现金等价物', '公允价值', '营业周期', '遵循'] },
  'consolidation': { label: '合并与合营', keywords: ['企业合并', '合并财务报表', '合营安排', '同一控制', '非同一控制', '控制的判断', '子公司'] },
  'financial': { label: '金融工具与外币', keywords: ['金融工具', '套期', '外币', '应付债券', '优先股', '永续债', '资产证券化'] },
  'asset': { label: '资产类政策', keywords: ['存货', '长期股权', '投资性房地产', '固定资产', '在建工程', '生物资产', '油气资产', '使用权资产', '无形资产', '研究开发', '长期待摊', '资产减值', '借款费用', '商誉'] },
  'liability_income': { label: '负债与收入', keywords: ['职工薪酬', '股份支付', '预计负债', '收入', '合同成本', '合同履约', '政府补助', '递延所得税', '安全生产', '应付债券'] },
  'lease_other': { label: '租赁与其他', keywords: ['租赁', '持有待售', '终止经营'] },
}

// 企业合并分组关键词
const MERGE_GROUPS: Record<string, { label: string; keywords: string[] }> = {
  'scope': { label: '合并范围', keywords: ['纳入合并', '不再纳入', '新纳入', '子公司基本'] },
  'control': { label: '控制与表决权', keywords: ['表决权不足', '直接或通过', '非全资', '所有者权益份额'] },
  'transaction': { label: '合并交易', keywords: ['同一控制下企业合并', '非同一控制下企业合并', '吸收合并'] },
  'restriction': { label: '限制与结构化主体', keywords: ['重大限制', '结构化主体', '转移资金'] },
}

// 关联方分组关键词
const RELATED_GROUPS: Record<string, { label: string; keywords: string[] }> = {
  'party': { label: '关联方情况', keywords: ['母公司', '子公司情况', '合营企业', '联营企业', '其他关联方'] },
  'transaction': { label: '关联交易', keywords: ['关联交易', '应收应付'] },
}

// ─── 通用分组函数 ────────────────────────────────────────────────────────────────

function buildGroupedChildren(
  items: DisclosureNoteTreeItem[],
  groups: Record<string, { label: string; keywords: string[] }>,
  idPrefix: string,
): TreeNode[] {
  const children: TreeNode[] = []
  const used = new Set<string>()
  for (const [gk, gv] of Object.entries(groups)) {
    const matched = items.filter(n => gv.keywords.some(kw => (n.section_title || '').includes(kw)))
    if (matched.length) {
      matched.forEach(n => used.add(n.id))
      children.push({
        id: `${idPrefix}_${gk}`, label: gv.label, isGroup: true,
        children: matched.map(n => ({ id: n.id, label: n.section_title, data: n })),
      })
    }
  }
  const ungrouped = items.filter(n => !used.has(n.id))
  if (ungrouped.length) {
    children.push({
      id: `${idPrefix}_other`, label: '其他', isGroup: true,
      children: ungrouped.map(n => ({ id: n.id, label: n.section_title, data: n })),
    })
  }
  return children
}

// ─── Composable 主体 ─────────────────────────────────────────────────────────────

export function useNoteTree(options: UseNoteTreeOptions): UseNoteTreeReturn {
  const { projectId, year, templateType, isEqcrRole, onTreeLoaded } = options

  // ─── Reactive state ─────────────────────────────────────────────────────────
  const noteList = ref<DisclosureNoteTreeItem[]>([])
  const treeLoading = ref(false)
  const treeSearch = ref('')
  const noteTreeRef = ref<any>(null)
  const treeViewMode = ref<'tree' | 'flat'>('tree')

  // ─── fetchTree ──────────────────────────────────────────────────────────────
  const fetchTree = withLoading(treeLoading, async () => {
    try {
      noteList.value = await getDisclosureNoteTree(projectId.value, year.value)
      // C.3.11: 刷新章节序号
      onTreeLoaded?.()
    }
    catch { noteList.value = [] }
  })

  // ─── 树形结构计算 ───────────────────────────────────────────────────────────
  const treeData = computed<TreeNode[]>(() => {
    const notes = noteList.value
    if (!notes.length) return []

    const result: TreeNode[] = []

    for (const ch of CHAPTER_GROUPS) {
      const prefix = ch.prefix + '、'
      const items = notes.filter(n => n.note_section.startsWith(prefix))
      if (!items.length) continue  // 空章节不显示

      // 动态获取章节标题（根据模板类型）
      const labels = templateType.value === 'listed' ? LISTED_LABELS : SOE_LABELS
      const chLabel = `${ch.prefix}、${labels[ch.prefix] || items[0]?.section_title || ''}`

      // 会计政策（国企四/上市三）：直接按模板顺序平铺，不分大类
      if ((ch.prefix === '三' || ch.prefix === '四') && items.length > 10) {
        result.push({
          id: `chapter_${ch.prefix}`, label: `${chLabel}（${items.length}）`, isGroup: true,
          children: items.map(n => ({ id: n.id, label: n.section_title, data: n })),
        })

      // 报表注释（国企八/上市五）：按资产/负债/权益/损益分组
      } else if ((ch.prefix === '五' || ch.prefix === '八') && items.length > 10) {
        const subChildren: TreeNode[] = []
        for (const [gKey, gInfo] of Object.entries(SECTION_GROUPS)) {
          const matched = items.filter(n => {
            const num = parseInt(n.note_section.replace(prefix, ''))
            return num >= gInfo.range[0] && num <= gInfo.range[1]
          })
          if (matched.length) {
            subChildren.push({
              id: `group_${ch.prefix}_${gKey}`, label: gInfo.label, isGroup: true,
              children: matched.map(n => ({ id: n.id, label: n.section_title, data: n })),
            })
          }
        }
        result.push({ id: `chapter_${ch.prefix}`, label: `${chLabel}（${items.length}）`, isGroup: true, children: subChildren })

      // 企业合并（国企七）：>5个子章节时分组
      } else if (ch.prefix === '七' && items.length > 5) {
        result.push({
          id: `chapter_${ch.prefix}`, label: `${chLabel}（${items.length}）`, isGroup: true,
          children: buildGroupedChildren(items, MERGE_GROUPS, 'ch7'),
        })

      // 关联方（国企十一/上市十一）：>3个子章节时分组
      } else if (ch.prefix === '十一' && items.length > 3) {
        result.push({
          id: `chapter_${ch.prefix}`, label: `${chLabel}（${items.length}）`, isGroup: true,
          children: buildGroupedChildren(items, RELATED_GROUPS, 'ch11'),
        })

      // 其他章节：直接平铺
      } else {
        result.push({
          id: `chapter_${ch.prefix}`,
          label: items.length > 3 ? `${chLabel}（${items.length}）` : chLabel,
          isGroup: true,
          children: items.map(n => ({ id: n.id, label: n.section_title, data: n })),
        })
      }
    }

    return result
  })

  const filteredTreeData = computed(() => {
    const kw = treeSearch.value.toLowerCase()
    if (!kw) return treeData.value
    // 搜索时展平到叶子节点过滤
    return treeData.value.map(group => {
      if (!group.children?.length) return group
      const filtered = group.children.map(child => {
        if (child.children) {
          // 二级分组
          const subFiltered = child.children.filter(n =>
            (n.label || '').toLowerCase().includes(kw) || (n.data?.account_name || '').toLowerCase().includes(kw)
          )
          return subFiltered.length ? { ...child, children: subFiltered } : null
        }
        // 叶子节点
        return (child.label || '').toLowerCase().includes(kw) || (child.data?.account_name || '').toLowerCase().includes(kw) ? child : null
      }).filter(Boolean) as TreeNode[]
      return filtered.length ? { ...group, children: filtered } : null
    }).filter(Boolean) as TreeNode[]
  })

  // ─── 平铺视图数据 ──────────────────────────────────────────────────────────
  const flatNoteList = computed(() => {
    const kw = treeSearch.value.toLowerCase()
    let list = noteList.value
    if (kw) {
      list = list.filter(n => (n.section_title || '').toLowerCase().includes(kw) || (n.note_section || '').toLowerCase().includes(kw))
    }
    return list
  })

  // ─── 树节点展开/收起 ───────────────────────────────────────────────────────
  function expandAll() {
    const tree = noteTreeRef.value
    if (!tree) return
    const nodes = tree.store?.nodesMap
    if (nodes) {
      Object.values(nodes).forEach((node: any) => { node.expanded = true })
    }
  }

  function collapseAll() {
    const tree = noteTreeRef.value
    if (!tree) return
    const nodes = tree.store?.nodesMap
    if (nodes) {
      Object.values(nodes).forEach((node: any) => { node.expanded = false })
    }
  }

  // ─── 拖拽排序 ──────────────────────────────────────────────────────────────
  function allowTreeDrop(draggingNode: any, dropNode: any, type: 'prev' | 'next' | 'inner'): boolean {
    // 不允许拖入分组节点（仅同级排序）
    if (type === 'inner') return false
    // 不允许拖到章节分组（isGroup）下方
    if (dropNode.data?.isGroup) return false
    // 必须同 parent
    return draggingNode.parent?.data === dropNode.parent?.data
  }

  async function onTreeNodeDrop(draggingNode: any, dropNode: any, dropType: 'before' | 'after' | 'inner', _evt: DragEvent) {
    if (dropType === 'inner') return
    const sectionId = draggingNode.data?.data?.note_section
    const targetId = dropNode.data?.data?.note_section
    if (!sectionId || !targetId) return

    try {
      await api.put(
        `/api/disclosure-notes/${projectId.value}/${year.value}/sections/${sectionId}/move`,
        { target_section_id: targetId, position: dropType }
      )
      ElMessage.success('章节排序已更新')
      // 刷新树以及章节序号
      await fetchTree()
    } catch (e: any) {
      handleApiError(e, '排序')
      // 刷新还原
      await fetchTree()
    }
  }

  return {
    noteList,
    treeLoading,
    treeSearch,
    noteTreeRef,
    treeViewMode,
    treeData,
    filteredTreeData,
    flatNoteList,
    fetchTree,
    allowTreeDrop,
    onTreeNodeDrop,
    expandAll,
    collapseAll,
  }
}
