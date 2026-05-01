'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { API_BASE } from '@/lib/constants'
import type { AutoReactionConfig, GuildsMap, ChannelsMap } from '@/lib/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { DataTable, type Column } from '@/components/data-table'
import { DeleteButton } from '@/components/delete-button'
import { GuildChannelSelector } from '@/components/guild-channel-selector'
import { ToggleButton } from '@/components/toggle-button'

function resolveGuildName(guilds: GuildsMap, guildId: string) {
  return guilds[guildId] ?? guildId
}

function resolveChannelName(channels: ChannelsMap, guildId: string, channelId: string) {
  const list = channels[guildId] ?? []
  const ch = list.find((c) => c.id === channelId)
  return ch ? `#${ch.name}` : channelId
}

function parseEmojiInput(raw: string): string[] {
  return raw.split(/\s+/).filter((s) => s.length > 0)
}

export default function AutoReactionPage() {
  const router = useRouter()
  const [configs, setConfigs] = useState<AutoReactionConfig[]>([])
  const [guilds, setGuilds] = useState<GuildsMap>({})
  const [channels, setChannels] = useState<ChannelsMap>({})
  const [loading, setLoading] = useState(true)

  const [selectedGuild, setSelectedGuild] = useState('')
  const [selectedChannel, setSelectedChannel] = useState('')
  const [emojis, setEmojis] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function fetchData() {
    const res = await fetch(`${API_BASE}/auto-reaction`).then((r) => r.json())
    setConfigs(res?.configs ?? [])
    setGuilds(res?.guilds ?? {})
    setChannels(res?.channels ?? {})
    setLoading(false)
  }

  useEffect(() => {
    fetchData()
  }, [])

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!selectedGuild || !selectedChannel) return
    const emojiList = parseEmojiInput(emojis)
    if (emojiList.length === 0) return
    setSubmitting(true)
    try {
      await fetch(`${API_BASE}/auto-reaction`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          guild_id: selectedGuild,
          channel_id: selectedChannel,
          emojis: emojiList,
        }),
      })
      setSelectedGuild('')
      setSelectedChannel('')
      setEmojis('')
      fetchData()
      router.refresh()
    } finally {
      setSubmitting(false)
    }
  }

  const columns: Column<AutoReactionConfig>[] = [
    {
      header: 'Server',
      accessor: (row) => resolveGuildName(guilds, row.guild_id),
    },
    {
      header: 'Channel',
      accessor: (row) => resolveChannelName(channels, row.guild_id, row.channel_id),
    },
    {
      header: 'Emojis',
      accessor: (row) =>
        row.emojis.length > 0 ? (
          <span className="font-mono text-sm">{row.emojis.join(' ')}</span>
        ) : (
          <span className="text-muted-foreground">(none)</span>
        ),
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
            endpoint={`${API_BASE}/auto-reaction/${row.id}/toggle`}
            enabled={row.enabled}
          />
          <DeleteButton endpoint={`${API_BASE}/auto-reaction/${row.id}`} />
        </div>
      ),
    },
  ]

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Auto Reaction</h1>
        <p className="text-muted-foreground">Loading...</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Auto Reaction</h1>

      <Card>
        <CardHeader>
          <CardTitle>Add Auto Reaction</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <GuildChannelSelector
              guilds={guilds}
              channels={channels}
              selectedGuild={selectedGuild}
              selectedChannel={selectedChannel}
              onGuildChange={setSelectedGuild}
              onChannelChange={setSelectedChannel}
            />
            <div>
              <label className="text-sm font-medium mb-1.5 block">
                Emojis (space-separated; Unicode 絵文字 or {'<:name:id>'} for custom)
              </label>
              <Input
                type="text"
                placeholder="👍 ❤️ <:custom:123456789012345678>"
                value={emojis}
                onChange={(e) => setEmojis(e.target.value)}
              />
            </div>
            <div>
              <Button
                type="submit"
                disabled={
                  submitting ||
                  !selectedGuild ||
                  !selectedChannel ||
                  parseEmojiInput(emojis).length === 0
                }
              >
                {submitting ? 'Adding...' : 'Add'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Configured Auto Reactions</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable columns={columns} data={configs} emptyMessage="No auto reactions configured" />
        </CardContent>
      </Card>
    </div>
  )
}
