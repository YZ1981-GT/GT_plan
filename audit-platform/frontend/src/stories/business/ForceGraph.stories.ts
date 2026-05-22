import type { Meta, StoryObj } from '@storybook/vue3'
import ForceGraph from '@/components/panorama/ForceGraph.vue'
import type { D3Node, D3Link } from '@/composables/usePanoramaGraph'

const meta = {
  title: 'Business/ForceGraph',
  component: ForceGraph,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component: 'D3.js 力导向联动全景图：节点按循环着色，边按 severity 粗细/颜色区分，支持 zoom/drag/hover 高亮',
      },
    },
    layout: 'fullscreen',
  },
} satisfies Meta<typeof ForceGraph>

export default meta
type Story = StoryObj<typeof meta>

const sampleNodes: D3Node[] = [
  { id: 'D2-1', wp_code: 'D2-1', cycle: 'D', label: '收入审定表', is_stale: false, degree: 4, is_module: false },
  { id: 'D4-1', wp_code: 'D4-1', cycle: 'D', label: '应收账款审定表', is_stale: true, degree: 3, is_module: false },
  { id: 'E1-1', wp_code: 'E1-1', cycle: 'E', label: '货币资金审定表', is_stale: false, degree: 2, is_module: false },
  { id: 'F2-1', wp_code: 'F2-1', cycle: 'F', label: '存货审定表', is_stale: false, degree: 3, is_module: false },
  { id: 'H1-1', wp_code: 'H1-1', cycle: 'H', label: '固定资产审定表', is_stale: true, degree: 2, is_module: false },
  { id: '__module__trial_balance', wp_code: 'TB', cycle: 'module', label: '试算平衡表', is_stale: false, degree: 5, is_module: true },
  { id: 'K8-1', wp_code: 'K8-1', cycle: 'K', label: '销售费用审定表', is_stale: false, degree: 2, is_module: false },
  { id: 'N2-1', wp_code: 'N2-1', cycle: 'N', label: '应交税费审定表', is_stale: false, degree: 2, is_module: false },
]

const sampleLinks: D3Link[] = [
  { id: 'CW-001', source: 'D2-1', target: 'D4-1', ref_id: 'CW-001', severity: 'blocking', category: 'prefill', description: '收入→应收联动', is_stale: false, label: '' },
  { id: 'CW-002', source: 'D4-1', target: 'E1-1', ref_id: 'CW-002', severity: 'warning', category: 'cross_check', description: '应收→货币资金核对', is_stale: true, label: '' },
  { id: 'CW-003', source: 'F2-1', target: '__module__trial_balance', ref_id: 'CW-003', severity: 'info', category: 'report', description: '存货→TB 汇总', is_stale: false, label: '' },
  { id: 'CW-004', source: '__module__trial_balance', target: 'D2-1', ref_id: 'CW-004', severity: 'blocking', category: 'prefill', description: 'TB→收入 prefill', is_stale: false, label: '' },
  { id: 'CW-005', source: 'H1-1', target: 'K8-1', ref_id: 'CW-005', severity: 'warning', category: 'depreciation', description: '固定资产折旧→费用', is_stale: true, label: '' },
  { id: 'CW-006', source: 'D2-1', target: 'N2-1', ref_id: 'CW-006', severity: 'required', category: 'tax', description: '收入→增值税', is_stale: false, label: '' },
]

export const Default: Story = {
  args: {
    nodes: sampleNodes,
    links: sampleLinks,
    width: 900,
    height: 600,
  },
}

export const WithStaleNodes: Story = {
  args: {
    nodes: sampleNodes.map(n => ({ ...n, is_stale: true })),
    links: sampleLinks.map(l => ({ ...l, is_stale: true })),
    width: 900,
    height: 600,
  },
}

export const MinimalGraph: Story = {
  args: {
    nodes: sampleNodes.slice(0, 3),
    links: sampleLinks.slice(0, 2),
    width: 600,
    height: 400,
  },
}
