import type { Meta, StoryObj } from '@storybook/vue3'
import SyncStatusIndicator from '@/components/common/SyncStatusIndicator.vue'

const meta = {
  title: 'Common/SyncStatusIndicator',
  component: SyncStatusIndicator,
  tags: ['autodocs'],
  decorators: [
    () => ({
      template: '<div style="background: #4b2d77; padding: 16px; display: inline-block;"><story /></div>',
    }),
  ],
} satisfies Meta<typeof SyncStatusIndicator>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {}

export const Synced: Story = {
  parameters: {
    docs: { description: { story: '同步正常状态，显示刷新图标' } },
  },
}
