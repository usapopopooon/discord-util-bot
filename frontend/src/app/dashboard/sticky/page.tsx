import { apiFetch } from '@/lib/api'
import { API_BASE } from '@/lib/constants'
import type { StickyMessage, GuildsMap, ChannelsMap } from '@/lib/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { DataTable, type Column } from '@/components/data-table'
import { DeleteButton } from '@/components/delete-button'

function resolveGuildName(guilds: GuildsMap, guildId: string) {
  return guilds[guildId] ?? guildId
}

function resolveChannelName(channels: ChannelsMap, guildId: string, channelId: string) {
  const list = channels[guildId] ?? []
  const ch = list.find((c) => c.id === channelId)
  return ch ? `#${ch.name}` : channelId
}

export default async function StickyPage() {
  const res = await apiFetch<{
    stickies: StickyMessage[]
    guilds: GuildsMap
    channels: ChannelsMap
  }>(`${API_BASE}/sticky`)

  const stickies = res.data?.stickies ?? []
  const guilds = res.data?.guilds ?? {}
  const channels = res.data?.channels ?? {}

  const columns: Column<StickyMessage>[] = [
    {
      header: 'Server',
      accessor: (row) => resolveGuildName(guilds, row.guild_id),
    },
    {
      header: 'Channel',
      accessor: (row) => resolveChannelName(channels, row.guild_id, row.channel_id),
    },
    {
      header: 'Type',
      accessor: (row) => row.message_type,
    },
    {
      header: 'Title',
      accessor: (row) => row.title || '-',
    },
    {
      header: 'Cooldown',
      accessor: (row) => `${row.cooldown_seconds}s`,
    },
    {
      header: 'Actions',
      accessor: (row) => <DeleteButton endpoint={`${API_BASE}/sticky/${row.id}`} />,
    },
  ]

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Sticky Messages</h1>
      <Card>
        <CardHeader>
          <CardTitle>Configured Messages</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable
            columns={columns}
            data={stickies}
            emptyMessage="No sticky messages configured"
          />
        </CardContent>
      </Card>
    </div>
  )
}
