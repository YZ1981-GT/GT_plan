import type { Meta, StoryObj } from '@storybook/vue3'
import GlobalSearchDialog from '@/components/common/GlobalSearchDialog.vue'

const meta = {
  title: 'Common/GlobalSearchDialog',
  component: GlobalSearchDialog,
  tags: ['autodocs'],
} satisfies Meta<typeof GlobalSearchDialog>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    visible: true,
  },
}

export const Closed: Story = {
  args: {
    visible: false,
  },
}
