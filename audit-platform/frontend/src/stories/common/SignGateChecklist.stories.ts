import type { Meta, StoryObj } from '@storybook/vue3'
import GateReadinessPanel from '@/components/gate/GateReadinessPanel.vue'

const meta = {
  title: 'Common/SignGateChecklist',
  component: GateReadinessPanel,
  tags: ['autodocs'],
} satisfies Meta<typeof GateReadinessPanel>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {}

export const ReadyToSign: Story = {
  parameters: {
    docs: { description: { story: '所有前置条件满足，可签字状态' } },
  },
}
