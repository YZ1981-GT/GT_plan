import type { Meta, StoryObj } from '@storybook/vue3'
import GtStatusTag from '@/components/common/GtStatusTag.vue'

const meta = {
  title: 'Common/GtStatusTag',
  component: GtStatusTag,
  tags: ['autodocs'],
  argTypes: {
    size: { control: 'select', options: ['large', 'default', 'small'] },
  },
} satisfies Meta<typeof GtStatusTag>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    dictKey: 'wp_status',
    value: 'draft',
  },
}

export const ReviewStatus: Story = {
  args: {
    dictKey: 'adjustment_status',
    value: 'approved',
    size: 'default',
  },
}

export const NullValue: Story = {
  args: {
    dictKey: 'wp_status',
    value: null,
  },
}

export const LargeSize: Story = {
  args: {
    dictKey: 'wp_status',
    value: 'completed',
    size: 'large',
  },
}
