'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { API_BASE } from '@/lib/constants'
import type { HealthConfig, GuildsMap, ChannelsMap } from '@/lib/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { DataTable, type Column } from '@/components/data-table'
import { DeleteButton } from '@/components/delete-button'
import { ToggleButton } from '@/components/toggle-button'

function resolveGuildName(guilds: GuildsMap, guildId: string) {
  return guilds[guildId] ?? guildId
}

function resolveChannelName(channels: ChannelsMap, guildId: string, channelId: string) {
  const list = channels[guildId] ?? []
  const ch = list.find((c) => c.id === channelId)
  return ch ? `#${ch.name}` : channelId
}

export default function HealthPage() {
  const router = useRouter()
  const [configs, setConfigs] = useState<HealthConfig[]>([])
  const [guilds, setGuilds] = useState<GuildsMap>({})
  const [channels, setChannels] = useState<ChannelsMap>({})
  const [loading, setLoading] = useState(true)

  // Form state
  const [selectedGuild, setSelectedGuild] = useState('')
  const [selectedChannel, setSelectedChannel] = useState('')
  const [intervalSeconds, setIntervalSeconds] = useState('300')
  const [submitting, setSubmitting] = useState(false)

  async function fetchData() {
    const res = await fetch(`${API_BASE}/health/settings`).then((r) => r.json())
    setConfigs(res?.configs ?? [])
    setGuilds(res?.guilds ?? {})
    setChannels(res?.channels ?? {})
    setLoading(false)
  }

  useEffect(() => {
    fetchData()
  }, [])

  const filteredChannels = selectedGuild ? (channels[selectedGuild] ?? []) : []

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!selectedGuild || !selectedChannel || !intervalSeconds) return
    setSubmitting(true)
    try {
      await fetch(`${API_BASE}/health/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          guild_id: selectedGuild,
          channel_id: selectedChannel,
          interval_seconds: parseInt(intervalSeconds, 10),
        }),
      })
      setSelectedGuild('')
      setSelectedChannel('')
      setIntervalSeconds('300')
      fetchData()
      router.refresh()
    } finally {
      setSubmitting(false)
    }
  }

  const columns: Column<HealthConfig>[] = [
    {
      header: 'Server',
      accessor: (row) => resolveGuildName(guilds, row.guild_id),
    },
    {
      header: 'Channel',
      accessor: (row) => resolveChannelName(channels, row.guild_id, row.channel_id),
    },
    {
      header: 'Interval',
      accessor: (row) => `${row.interval_seconds}s`,
    },
    {
      header: 'Status',
      accessor: (row) => (
        <Badge
          variant={row.enabled ? 'default' : 'secondary'}
          className={row.enabled ? 'bg-green-600 hover:bg-green-600' : ''}
        >
          {row.enabled ? 'Enabled' : 'Disabled'}
        </Badge>
      ),
    },
    {
      header: 'Actions',
      accessor: (row) => (
        <div className="flex items-center gap-2">
          <ToggleButton
            endpoint={`${API_BASE}/health/settings/${row.id}/toggle`}
            enabled={row.enabled}
          />
          <DeleteButton endpoint={`${API_BASE}/health/settings/${row.id}/delete`} />
        </div>
      ),
    },
  ]

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Health Check</h1>
        <p className="text-muted-foreground">Loading...</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Health Check</h1>

      <Card>
        <CardHeader>
          <CardTitle>Add Health Config</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex items-end gap-4">
            <div className="flex-1">
              <label className="text-sm font-medium mb-1.5 block">Server</label>
              <Select
                value={selectedGuild}
                onValueChange={(v) => {
                  setSelectedGuild(v)
                  setSelectedChannel('')
                }}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select server" />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(guilds).map(([id, name]) => (
                    <SelectItem key={id} value={id}>
                      {name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex-1">
              <label className="text-sm font-medium mb-1.5 block">Channel</label>
              <Select
                value={selectedChannel}
                onValueChange={setSelectedChannel}
                disabled={!selectedGuild}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select channel" />
                </SelectTrigger>
                <SelectContent>
                  {filteredChannels.map((ch) => (
                    <SelectItem key={ch.id} value={ch.id}>
                      {ch.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="w-40">
              <label className="text-sm font-medium mb-1.5 block">Interval (seconds)</label>
              <Input
                type="number"
                min={60}
                max={86400}
                value={intervalSeconds}
                onChange={(e) => setIntervalSeconds(e.target.value)}
              />
            </div>
            <Button type="submit" disabled={submitting || !selectedGuild || !selectedChannel}>
              {submitting ? 'Adding...' : 'Add'}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Health Configs</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable columns={columns} data={configs} emptyMessage="No health configs configured" />
        </CardContent>
      </Card>
    </div>
  )
}
