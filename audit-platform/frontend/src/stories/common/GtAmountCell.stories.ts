import type { Meta, StoryObj } from '@storybook/vue3'
import GtAmountCell from '@/components/common/GtAmountCell.vue'

const meta = {
  title: 'Common/GtAmountCell',
  component: GtAmountCell,
  tags: ['autodocs'],
} satisfies Meta<typeof GtAmountCell>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    value: 1234567.89,
  },
}

export const NegativeAmount: Story = {
  args: {
    value: -500000,
  },
}

export const Clickable: Story = {
  args: {
    value: 9876543.21,
    clickable: true,
  },
}

export const WithPriorValue: Story = {
  args: {
    value: 1500000,
    priorValue: 1200000,
    clickable: true,
  },
}

export const NullValue: Story = {
  args: {
    value: null,
  },
}
