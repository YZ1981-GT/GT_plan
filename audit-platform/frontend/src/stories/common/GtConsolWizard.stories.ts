import type { Meta, StoryObj } from '@storybook/vue3'
import GtConsolWizard from '@/components/common/GtConsolWizard.vue'

const meta = {
  title: 'Common/GtConsolWizard',
  component: GtConsolWizard,
  tags: ['autodocs'],
} satisfies Meta<typeof GtConsolWizard>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    activeStep: 0,
  },
}

export const MidProgress: Story = {
  args: {
    activeStep: 3,
    completedSteps: [true, true, true, false, false, false],
  },
}

export const AllCompleted: Story = {
  args: {
    activeStep: 5,
    completedSteps: [true, true, true, true, true, true],
  },
}
