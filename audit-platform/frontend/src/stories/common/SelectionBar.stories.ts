import type { Meta, StoryObj } from '@storybook/vue3'
import SelectionBar from '@/components/common/SelectionBar.vue'

const meta = {
  title: 'Common/SelectionBar',
  component: SelectionBar,
  tags: ['autodocs'],
} satisfies Meta<typeof SelectionBar>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    stats: {
      count: 5,
      numCount: 5,
      sum: 12500000,
      avg: 2500000,
      max: 4950000,
      min: 50000,
    },
  },
}

export const MixedSelection: Story = {
  args: {
    stats: {
      count: 8,
      numCount: 3,
      sum: 6000000,
      avg: 2000000,
      max: 4000000,
      min: 500000,
    },
  },
}

export const SingleCell: Story = {
  args: {
    stats: {
      count: 1,
      numCount: 1,
      sum: 1234567,
      avg: 1234567,
      max: 1234567,
      min: 1234567,
    },
  },
}

export const Empty: Story = {
  args: {
    stats: null,
  },
}
