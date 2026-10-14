import { createFileRoute } from '@tanstack/react-router'

import { DemoControls } from '@/components/demo/demo-controls'

export const Route = createFileRoute('/_shop/demo')({
  staticData: { crumb: 'Demo' },
  component: DemoControls,
})
