import type { Meta, StoryObj } from '@storybook/vue3'
import VRHeatmap from '@/components/qc/VRHeatmap.vue'

const meta = {
  title: 'Common/VRHeatmap',
  component: VRHeatmap,
  tags: ['autodocs'],
} satisfies Meta<typeof VRHeatmap>

export default meta
type Story = StoryObj<typeof meta>

const sampleMatrix = [
  { cycle: 'D', blocking: 2, warning: 5, info: 1 },
  { cycle: 'E', blocking: 0, warning: 3, info: 2 },
  { cycle: 'F', blocking: 1, warning: 4, info: 0 },
  { cycle: 'G', blocking: 0, warning: 2, info: 3 },
  { cycle: 'H', blocking: 3, warning: 6, info: 1 },
  { cycle: 'I', blocking: 0, warning: 1, info: 1 },
  { cycle: 'J', blocking: 0, warning: 2, info: 0 },
  { cycle: 'K', blocking: 1, warning: 3, info: 2 },
  { cycle: 'L', blocking: 0, warning: 1, info: 1 },
  { cycle: 'M', blocking: 0, warning: 0, info: 1 },
  { cycle: 'N', blocking: 1, warning: 2, info: 0 },
]

export const Default: Story = {
  args: {
    matrix: sampleMatrix,
    total: { blocking: 8, warning: 29, info: 12 },
    loading: false,
  },
}

export const Loading: Story = {
  args: {
    matrix: [],
    total: null,
    loading: true,
  },
}

export const AllClear: Story = {
  args: {
    matrix: sampleMatrix.map(r => ({ ...r, blocking: 0, warning: 0, info: 0 })),
    total: { blocking: 0, warning: 0, info: 0 },
    loading: false,
  },
}
