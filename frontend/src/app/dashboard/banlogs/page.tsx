import { apiFetch } from '@/lib/api'
import { API_BASE } from '@/lib/constants'
import type { BanLog, GuildsMap } from '@/lib/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { DataTable, type Column } from '@/components/data-table'

function resolveGuildName(guilds: GuildsMap, guildId: string) {
  return guilds[guildId] ?? guildId
}

export default async function BanLogsPage() {
  const res = await apiFetch<{ logs: BanLog[]; guilds: GuildsMap }>(`${API_BASE}/banlogs`)

  const logs = res.data?.logs ?? []
  const guilds = res.data?.guilds ?? {}

  const columns: Column<BanLog>[] = [
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
      header: 'Reason',
      accessor: (row) => (
        <span className="max-w-xs truncate block" title={row.reason ?? ''}>
          {row.reason ?? '-'}
        </span>
      ),
    },
    {
      header: 'Source',
      accessor: (row) => (
        <Badge
          className={
            row.is_automod ? 'bg-red-600 hover:bg-red-600' : 'bg-blue-600 hover:bg-blue-600'
          }
        >
          {row.is_automod ? 'AutoMod' : 'Manual'}
        </Badge>
      ),
    },
    {
      header: 'Date',
      accessor: (row) => new Date(row.created_at).toLocaleString(),
    },
  ]

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Ban Logs</h1>

      <Card>
        <CardHeader>
          <CardTitle>All Bans</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable columns={columns} data={logs} emptyMessage="No ban logs found" />
        </CardContent>
      </Card>
    </div>
  )
}
