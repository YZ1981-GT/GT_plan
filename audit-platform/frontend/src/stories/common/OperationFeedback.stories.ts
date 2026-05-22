import type { Meta, StoryObj } from '@storybook/vue3'
import OperationFeedback from '@/components/common/OperationFeedback.vue'

const meta = {
  title: 'Common/OperationFeedback',
  component: OperationFeedback,
  tags: ['autodocs'],
} satisfies Meta<typeof OperationFeedback>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    showProgress: false,
    progress: 0,
  },
}

export const InProgress: Story = {
  args: {
    showProgress: true,
    progress: 45,
    progressStatus: '',
  },
}

export const Success: Story = {
  args: {
    showProgress: true,
    progress: 100,
    progressStatus: 'success',
  },
}

export const Error: Story = {
  args: {
    showProgress: true,
    progress: 70,
    progressStatus: 'exception',
  },
}
