import { type ColumnDef } from '@tanstack/react-table'

import type { OrderSummary } from '@/api/gen'
import { type DataGridFeatures } from '@/components/reui/data-grid/data-grid'
import { DataGridColumnHeader } from '@/components/reui/data-grid/data-grid-column-header'
import { OrderStatusBadge } from '@/components/order-status-badge'
import { DECISION_ACTION_LABELS, formatDateTime } from '@/lib/labels'

import { ActionsCell, AmountCell, BuyerCell, OrderCell, RiskCell } from './cells'

export const columns: ColumnDef<DataGridFeatures, OrderSummary>[] = [
  {
    id: 'order',
    accessorFn: (o) => o.external_id ?? o.id,
    header: ({ column }) => <DataGridColumnHeader column={column} visibility={true} />,
    cell: ({ row }) => <OrderCell row={row} />,
    size: 170,
    enableSorting: true,
    enableHiding: false,
    enableResizing: true,
    meta: { headerTitle: 'Order ID', headerClassName: 'ps-4!', cellClassName: 'ps-4!' },
  },
  {
    id: 'buyer',
    accessorKey: 'buyer_name',
    header: ({ column }) => <DataGridColumnHeader column={column} visibility={true} />,
    cell: ({ row }) => <BuyerCell row={row} />,
    size: 210,
    minSize: 180,
    enableSorting: true,
    enableHiding: false,
    enableResizing: true,
    meta: { headerTitle: 'Buyer', autoSize: true },
  },
  {
    id: 'cod_amount_vnd',
    accessorKey: 'cod_amount_vnd',
    header: ({ column }) => <DataGridColumnHeader column={column} visibility={true} />,
    cell: ({ row }) => <AmountCell row={row} />,
    size: 160,
    enableSorting: true,
    enableHiding: true,
    enableResizing: true,
    meta: { headerTitle: 'COD' },
  },
  {
    id: 'risk_score',
    accessorKey: 'risk_score',
    header: ({ column }) => <DataGridColumnHeader column={column} visibility={true} />,
    cell: ({ row }) => <RiskCell row={row} />,
    size: 140,
    enableSorting: true,
    enableHiding: true,
    enableResizing: true,
    meta: { headerTitle: 'Risk' },
  },
  {
    id: 'current_action',
    accessorFn: (o) => (o.current_action ? DECISION_ACTION_LABELS[o.current_action] : ''),
    header: ({ column }) => <DataGridColumnHeader column={column} visibility={true} />,
    cell: ({ getValue }) => <span className="text-foreground">{(getValue() as string) || '—'}</span>,
    size: 150,
    enableSorting: true,
    enableHiding: true,
    enableResizing: true,
    meta: { headerTitle: 'Action' },
  },
  {
    id: 'status',
    accessorKey: 'status',
    header: ({ column }) => <DataGridColumnHeader column={column} visibility={true} />,
    cell: ({ row }) => <OrderStatusBadge status={row.original.status} />,
    size: 140,
    enableSorting: true,
    enableHiding: true,
    enableResizing: true,
    meta: { headerTitle: 'Status' },
  },
  {
    id: 'placed_at',
    accessorKey: 'placed_at',
    header: ({ column }) => <DataGridColumnHeader column={column} visibility={true} />,
    cell: ({ row }) => (
      <span className="text-muted-foreground tabular-nums">{formatDateTime(row.original.placed_at)}</span>
    ),
    size: 140,
    enableSorting: true,
    enableHiding: true,
    enableResizing: true,
    meta: { headerTitle: 'Placed at' },
  },
  {
    id: 'actions',
    header: '',
    cell: ({ row }) => <ActionsCell row={row} />,
    size: 50,
    enableSorting: false,
    enableHiding: false,
    enableResizing: false,
  },
]
