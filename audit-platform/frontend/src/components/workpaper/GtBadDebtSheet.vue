<!--
  GtBadDebtSheet.vue — 坏账准备明细表 D2-3 嵌套子表编辑器（Task 11）

  致同 2025 修订版 D2-3 两层嵌套：计提类别父行 → 明细子行 + 合计行。
  - 层级渲染：父行加粗 / 子行缩进"其中：XXX" / 合计行
  - 展开折叠：切换父行下子行可见性
  - 右键菜单：父行→新增子行；子行→删除/上方插入/下方插入
  - 只读保护：合计行 + 含子行的父行金额列只读（汇总值，不可直接编辑）
  - 预填来源 tooltip：prefill_source 非空时在期初/期末未审数列提示来源

  后端：/api/workpapers/{wpId}/bad-debt-rows（wpId = wp_index_id）。
  http 客户端：@/services/apiProxy（api.get/post/put/delete 返回业务数据）。
  Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7
-->

<template>
  <div class="gt-bad-debt-sheet" v-loading="loading">
    <div class="gbds-toolbar">
      <span class="gbds-title">坏账准备明细表 D2-3</span>
      <el-button size="small" class="gbds-btn-add" @click="onAddParent">
        ＋ 新增计提类别
      </el-button>
    </div>

    <table class="gbds-table">
      <thead>
        <tr class="gbds-head-group">
          <th rowspan="2" class="gbds-col-label">项目</th>
          <th colspan="4">期初</th>
          <th colspan="2">本期增加</th>
          <th colspan="3">本期减少</th>
          <th colspan="4">期末</th>
        </tr>
        <tr class="gbds-head-col">
          <th v-for="c in AMOUNT_COLS" :key="c.key">{{ c.title }}</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="parent in tree.parents" :key="parent.id">
          <tr
            class="gbds-row gbds-parent"
            @contextmenu.prevent="openMenu($event, parent, null)"
          >
            <td class="gbds-col-label">
              <span
                class="gbds-toggle"
                @click="toggleExpand(parent.id)"
              >{{ isExpanded(parent.id) ? '▼' : '▶' }}</span>
              <strong>{{ parent.row_label }}</strong>
              <span class="gbds-method-tag">{{ parent.provision_method_label }}</span>
            </td>
            <td
              v-for="c in AMOUNT_COLS"
              :key="c.key"
              class="gbds-amount gbds-readonly"
              :class="{ 'gbds-editable': parent.is_editable }"
            >
              <el-input-number
                v-if="parent.is_editable"
                :model-value="numVal(parent.amounts[c.key])"
                :controls="false"
                :precision="2"
                size="small"
                class="gbds-input"
                @change="(v) => onEditAmount(parent, c.key, v)"
              />
              <span v-else>{{ fmt(parent.amounts[c.key]) }}</span>
            </td>
          </tr>

          <tr
            v-for="child in parent.children"
            v-show="isExpanded(parent.id)"
            :key="child.id"
            class="gbds-row gbds-child"
            @contextmenu.prevent="openMenu($event, parent, child)"
          >
            <td class="gbds-col-label gbds-indent">其中：{{ child.row_label }}</td>
            <td
              v-for="c in AMOUNT_COLS"
              :key="c.key"
              class="gbds-amount gbds-editable"
            >
              <el-tooltip
                :disabled="!prefillTip(c.key)"
                :content="prefillTip(c.key)"
                placement="top"
              >
                <el-input-number
                  :model-value="numVal(child.amounts[c.key])"
                  :controls="false"
                  :precision="2"
                  size="small"
                  class="gbds-input"
                  @change="(v) => onEditAmount(child, c.key, v)"
                />
              </el-tooltip>
            </td>
          </tr>
        </template>

        <tr class="gbds-row gbds-summary">
          <td class="gbds-col-label"><strong>合计</strong></td>
          <td
            v-for="c in AMOUNT_COLS"
            :key="c.key"
            class="gbds-amount gbds-readonly"
          >{{ fmt(tree.summary?.amounts?.[c.key]) }}</td>
        </tr>
      </tbody>
    </table>

    <!-- 右键上下文菜单 -->
    <ul
      v-if="menu.visible"
      class="gbds-menu"
      :style="{ left: menu.x + 'px', top: menu.y + 'px' }"
    >
      <li v-if="!menu.child" @click="onAddChild(menu.parent)">新增子行</li>
      <template v-if="menu.child">
        <li @click="onInsertChild(menu.parent, menu.child, 'above')">在上方插入子行</li>
        <li @click="onInsertChild(menu.parent, menu.child, 'below')">在下方插入子行</li>
        <li class="gbds-menu-danger" @click="onDeleteChild(menu.child)">删除子行</li>
      </template>
    </ul>
  </div>
</template>


<script setup lang="ts">
import { reactive, ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'

interface RowAmounts {
  [key: string]: string | null
}
interface ChildRow {
  id: string
  parent_row_id: string
  sort_order: number
  row_label: string
  amounts: RowAmounts
  version: number
}
interface ParentRow {
  id: string
  provision_method: string
  provision_method_label: string
  sort_order: number
  row_label: string
  amounts: RowAmounts
  children: ChildRow[]
  version: number
  is_editable: boolean
}
interface Tree {
  wp_index_id: string
  summary: { amounts: RowAmounts; balance_check?: any } | null
  parents: ParentRow[]
  prefill_source: string | null
}

const props = defineProps<{
  wpId: string
  sheetName?: string
  readonly?: boolean
  schema?: Record<string, any>
  htmlData?: Record<string, any>
}>()

// 13 金额列 amount_b ~ amount_n
const AMOUNT_COLS = [
  { key: 'amount_b', title: '期初未审数' },
  { key: 'amount_c', title: '期初账项调整' },
  { key: 'amount_d', title: '重分类(期初)' },
  { key: 'amount_e', title: '期初审定数' },
  { key: 'amount_f', title: '本期计提' },
  { key: 'amount_g', title: '其他增加' },
  { key: 'amount_h', title: '本期转回' },
  { key: 'amount_i', title: '核销' },
  { key: 'amount_j', title: '其他减少' },
  { key: 'amount_k', title: '期末未审数' },
  { key: 'amount_l', title: '期末账项调整' },
  { key: 'amount_m', title: '重分类(期末)' },
  { key: 'amount_n', title: '期末审定数' },
]

const loading = ref(false)
const tree = reactive<Tree>({
  wp_index_id: '',
  summary: null,
  parents: [],
  prefill_source: null,
})
const expanded = reactive<Record<string, boolean>>({})
const provisionMethods = ref<{ value: string; label: string }[]>([])

const menu = reactive<{
  visible: boolean
  x: number
  y: number
  parent: ParentRow | null
  child: ChildRow | null
}>({ visible: false, x: 0, y: 0, parent: null, child: null })

function base(): string {
  return `/api/workpapers/${props.wpId}/bad-debt-rows`
}

function numVal(v: string | null | undefined): number | undefined {
  if (v === null || v === undefined || v === '') return undefined
  return Number(v)
}

function fmt(v: string | null | undefined): string {
  if (v === null || v === undefined || v === '') return ''
  const n = Number(v)
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function isExpanded(pid: string): boolean {
  return expanded[pid] !== false // 默认展开
}
function toggleExpand(pid: string): void {
  expanded[pid] = !isExpanded(pid)
}

function prefillTip(key: string): string {
  if (!tree.prefill_source) return ''
  if (key === 'amount_b' || key === 'amount_k') return `来自${tree.prefill_source}`
  return ''
}

async function loadTree(): Promise<void> {
  loading.value = true
  try {
    const data = await api.get(base())
    Object.assign(tree, data)
  } catch (e: any) {
    ElMessage.error('加载坏账准备明细表失败')
  } finally {
    loading.value = false
  }
}

async function loadMethods(): Promise<void> {
  try {
    provisionMethods.value = (await api.get(`${base()}/provision-methods`)) || []
  } catch {
    provisionMethods.value = []
  }
}

async function onAddParent(): Promise<void> {
  const used = new Set(tree.parents.map((p) => p.provision_method))
  const avail = provisionMethods.value.filter((m) => !used.has(m.value))
  if (avail.length === 0) {
    ElMessage.warning('所有计提类别已添加')
    return
  }
  try {
    const { value } = await ElMessageBox.prompt(
      `计提类别：${avail.map((m) => m.label).join(' / ')}`,
      '新增计提类别',
      { inputValue: avail[0].label },
    )
    const method = avail.find((m) => m.label === value) || avail[0]
    await api.post(`${base()}/parents`, {
      provision_method: method.value,
      row_label: method.label,
    })
    await loadTree()
  } catch {
    /* 取消 */
  }
}

async function onAddChild(parent: ParentRow | null): Promise<void> {
  closeMenu()
  if (!parent) return
  try {
    const { value } = await ElMessageBox.prompt('明细项目名称', '新增子行')
    await api.post(`${base()}/${parent.id}/children`, { row_label: value })
    await loadTree()
  } catch {
    /* 取消 */
  }
}

async function onInsertChild(
  parent: ParentRow | null,
  child: ChildRow | null,
  pos: 'above' | 'below',
): Promise<void> {
  closeMenu()
  if (!parent || !child) return
  try {
    const { value } = await ElMessageBox.prompt('请输入子行标签', '插入子行', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /.+/,
      inputErrorMessage: '标签不能为空',
    })
    const body: Record<string, unknown> = { row_label: value }
    if (pos === 'above') body.insert_before_id = child.id
    else body.insert_after_id = child.id
    await api.post(`${base()}/${parent.id}/children`, body)
    await loadTree()
  } catch {
    /* 取消 */
  }
}

async function onDeleteChild(child: ChildRow | null): Promise<void> {
  closeMenu()
  if (!child) return
  try {
    await ElMessageBox.confirm('确认删除该子行？', '删除确认', { type: 'warning' })
    await api.delete(`${base()}/${child.id}`)
    await loadTree()
  } catch {
    /* 取消 */
  }
}

async function onEditAmount(
  row: ParentRow | ChildRow,
  key: string,
  value: number | undefined,
): Promise<void> {
  const amounts: RowAmounts = { [key]: value === undefined ? null : String(value) }
  try {
    await api.put(`${base()}/${row.id}`, { version: row.version, amounts })
    await loadTree()
  } catch (e: any) {
    if (e?.response?.status === 409) {
      ElMessage.error('数据已被他人修改，请刷新后重试')
    } else {
      ElMessage.error('保存失败')
    }
    await loadTree()
  }
}

function openMenu(ev: MouseEvent, parent: ParentRow, child: ChildRow | null): void {
  menu.visible = true
  menu.x = ev.clientX
  menu.y = ev.clientY
  menu.parent = parent
  menu.child = child
}
function closeMenu(): void {
  menu.visible = false
}

onMounted(async () => {
  window.addEventListener('click', closeMenu)
  await loadMethods()
  await loadTree()
})

defineExpose({ loadTree, tree })
</script>

<style scoped>
.gt-bad-debt-sheet {
  --gbds-purple: var(--gt-color-primary, #4b2d77);
  --gbds-purple-bg: var(--gt-color-primary-bg, #f4f0fa);
  font-size: 13px;
}
.gbds-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 4px;
}
.gbds-title {
  font-weight: 600;
  color: var(--gbds-purple);
}
.gbds-table {
  width: 100%;
  border-collapse: collapse;
}
.gbds-table th,
.gbds-table td {
  border: 1px solid var(--gt-color-border-purple-light, #d8b8ee);
  padding: 4px 6px;
  text-align: right;
}
.gbds-head-group th,
.gbds-head-col th {
  background: var(--gbds-purple-bg);
  color: var(--gbds-purple);
  text-align: center;
  font-weight: 600;
}
.gbds-col-label {
  text-align: left;
  min-width: 200px;
}
.gbds-parent {
  background: var(--gbds-purple-bg);
}
.gbds-toggle {
  cursor: pointer;
  margin-right: 4px;
  user-select: none;
}
.gbds-method-tag {
  margin-left: 8px;
  font-size: 11px;
  color: var(--gbds-purple);
  opacity: 0.8;
}
.gbds-indent {
  padding-left: 28px;
}
.gbds-summary {
  background: var(--gbds-purple-bg);
  font-weight: 600;
}
.gbds-readonly {
  color: #333;
}
.gbds-input {
  width: 100%;
}
.gbds-menu {
  position: fixed;
  z-index: 3000;
  background: #fff;
  border: 1px solid var(--gt-color-border-purple-light, #d8b8ee);
  border-radius: 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  list-style: none;
  margin: 0;
  padding: 4px 0;
  min-width: 140px;
}
.gbds-menu li {
  padding: 6px 16px;
  cursor: pointer;
}
.gbds-menu li:hover {
  background: var(--gbds-purple-bg);
}
.gbds-menu-danger {
  color: #c0392b;
}
</style>
