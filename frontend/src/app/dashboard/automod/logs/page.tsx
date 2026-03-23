import Link from 'next/link'
import { apiFetch } from '@/lib/api'
import { API_BASE } from '@/lib/constants'
import type { AutoModLog, GuildsMap } from '@/lib/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { DataTable, type Column } from '@/components/data-table'

function resolveGuildName(guilds: GuildsMap, guildId: string) {
  return guilds[guildId] ?? guildId
}

function actionBadge(action: string) {
  const colors: Record<string, string> = {
    banned: 'bg-red-600 hover:bg-red-600',
    timed_out: 'bg-yellow-500 hover:bg-yellow-500',
    kicked: 'bg-orange-500 hover:bg-orange-500',
  }
  return <Badge className={colors[action] ?? ''}>{action}</Badge>
}

export default async function AutoModLogsPage() {
  const res = await apiFetch<{ logs: AutoModLog[]; guilds: GuildsMap }>(`${API_BASE}/automod/logs`)

  const logs = res.data?.logs ?? []
  const guilds = res.data?.guilds ?? {}

  const columns: Column<AutoModLog>[] = [
    {
      header: 'Server',
      accessor: (row) => resolveGuildName(guilds, row.guild_id),
    },
    {
      header: 'User ID',
      accessor: (row) => (
        <code className="rounded bg-muted px-1.5 py-0.5 text-xs">{row.user_id}</code>
      ),
    },
    {
      header: 'Username',
      accessor: (row) => row.username,
    },
    {
      header: 'Action',
      accessor: (row) => actionBadge(row.action_taken),
    },
    {
      header: 'Reason',
      accessor: (row) => (
        <span className="max-w-xs truncate block" title={row.reason}>
          {row.reason}
        </span>
      ),
    },
    {
      header: 'Rule #',
      accessor: (row) => row.rule_id,
    },
    {
      header: 'Date',
      accessor: (row) => new Date(row.created_at).toLocaleString(),
    },
  ]

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link href="/dashboard/automod">
          <Button variant="outline" size="sm">
            Back
          </Button>
        </Link>
        <h1 className="text-2xl font-bold">AutoMod Logs</h1>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Action Logs</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable columns={columns} data={logs} emptyMessage="No AutoMod logs found" />
        </CardContent>
      </Card>
    </div>
  )
}
