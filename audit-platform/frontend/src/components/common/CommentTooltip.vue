<script lang="ts">
/**
 * 批注 hover 气泡：有批注时用 el-tooltip 包住单元格；没有批注时直接渲染唯一的子节点，不多一层。
 *
 * 原先没批注时渲染 `<slot />` 片段根：外层 el-tooltip（附注校验提示、报表公式提示）把触发属性与定位用的 ref 指令
 * 挂到本组件上，片段根接不住 ⇒ Vue 告警、外层提示永远不出现（spec note-chain-followup-optimizations R5）。现在：
 * - 没批注、唯一子节点：子节点原样作根，父级传来的属性 / 指令落到真实元素上；
 * - 有批注：父级属性转给触发元素（el-tooltip 自身的根是片段）；多个子节点包一层 span（el-tooltip 只认一个触发元素，
 *   原先只渲染第一个、其余静默丢掉）。外层提示的指令此时仍到不了元素 —— 调用处别把本组件放进另一个提示里
 *   （附注单元格：校验提示包单元格容器，本组件只包 GtGridCell）；
 * - Enter / 空格不开合气泡（triggerKeys 置空）：单元格里正在编辑时这两个键是提交 / 输入，不能被气泡 preventDefault。
 */
import { Comment, Fragment, Static, Text, cloneVNode, computed, defineComponent, h, type PropType, type VNode } from 'vue'
import { ElTooltip } from 'element-plus'
import type { CellComment } from '@/composables/useCellComments'

/** 去掉注释节点、展开片段后的子节点。 */
function flatChildren(nodes: VNode[] | undefined): VNode[] {
  const out: VNode[] = []
  for (const node of nodes ?? []) {
    if (node.type === Comment) continue
    if (node.type === Fragment && Array.isArray(node.children)) out.push(...flatChildren(node.children as VNode[]))
    else out.push(node)
  }
  return out
}

/** 唯一的元素 / 组件子节点（能接住属性与指令）；文字、多个子节点 ⇒ null。 */
function onlyElement(nodes: VNode[]): VNode | null {
  if (nodes.length !== 1) return null
  const type = nodes[0].type
  return type === Text || type === Static || type === Fragment ? null : nodes[0]
}

export default defineComponent({
  name: 'CommentTooltip',
  inheritAttrs: false,
  props: {
    comment: { type: Object as PropType<CellComment | null>, default: null },
  },
  setup(props, { slots, attrs }) {
    const tooltipContent = computed(() => {
      if (!props.comment) return ''
      const parts: string[] = []
      if (props.comment.comment) parts.push(props.comment.comment)
      if (props.comment.comment_type === 'review' && props.comment.status === 'reviewed') {
        parts.push('✓ 已复核')
      }
      if (props.comment.created_at) {
        const d = new Date(props.comment.created_at)
        if (!isNaN(d.getTime())) parts.push(d.toLocaleString('zh-CN'))
      }
      return parts.join(' · ')
    })

    return () => {
      const children = slots.default?.() ?? []
      const only = onlyElement(flatChildren(children))
      if (!props.comment) return only ? cloneVNode(only, { ...attrs }) : children
      const trigger = only ? cloneVNode(only, { ...attrs }) : h('span', { ...attrs }, children)
      return h(ElTooltip, {
        content: tooltipContent.value,
        placement: 'top',
        showAfter: 300,
        hideAfter: 0,
        effect: 'light',
        popperClass: 'gt-comment-tooltip',
        triggerKeys: [],
      }, { default: () => trigger })
    }
  },
})
</script>

<style>
/* 非 scoped，因为 popper 渲染在 body 上 */
.gt-comment-tooltip {
  max-width: 300px !important;
  font-size: var(--gt-font-size-xs) !important;
  line-height: 1.6 !important;
  border: 1px solid var(--gt-color-wheat) !important;
  background: var(--gt-color-wheat-light) !important;
}
.gt-comment-tooltip .el-tooltip__arrow::before {
  border-color: var(--gt-color-wheat) !important;
  background: var(--gt-color-wheat-light) !important;
}
</style>
