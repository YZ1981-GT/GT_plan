import type { Meta, StoryObj } from '@storybook/vue3'
import BatchActionBar from '@/components/workpaper/BatchActionBar.vue'

const meta = {
  title: 'Common/BatchActionBar',
  component: BatchActionBar,
  tags: ['autodocs'],
} satisfies Meta<typeof BatchActionBar>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    selectedCount: 3,
    selectedIds: ['wp-001', 'wp-002', 'wp-003'],
  },
}

export const ManySelected: Story = {
  args: {
    selectedCount: 12,
    selectedIds: Array.from({ length: 12 }, (_, i) => `wp-${String(i + 1).padStart(3, '0')}`),
  },
}

export const Hidden: Story = {
  args: {
    selectedCount: 0,
    selectedIds: [],
  },
}
