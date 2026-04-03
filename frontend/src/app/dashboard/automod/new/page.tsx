'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { API_BASE } from '@/lib/constants'
import type { GuildsMap, ChannelsMap } from '@/lib/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import Link from 'next/link'

const RULE_TYPES = [
  { value: 'username_match', label: 'Username Match' },
  { value: 'account_age', label: 'Account Age' },
  { value: 'no_avatar', label: 'No Avatar' },
  { value: 'role_acquired', label: 'Role Acquired' },
  { value: 'vc_join', label: 'VC Join' },
  { value: 'message_post', label: 'Message Post' },
  { value: 'vc_without_intro', label: 'VC Without Intro' },
  { value: 'msg_without_intro', label: 'Message Without Intro' },
  { value: 'role_count', label: 'Role Count' },
]

const ACTIONS = [
  { value: 'ban', label: 'Ban' },
  { value: 'kick', label: 'Kick' },
  { value: 'timeout', label: 'Timeout' },
]

export default function AutoModNewPage() {
  const router = useRouter()
  const [guilds, setGuilds] = useState<GuildsMap>({})
  const [channels, setChannels] = useState<ChannelsMap>({})
  const [submitting, setSubmitting] = useState(false)

  // Form state
  const [selectedGuild, setSelectedGuild] = useState('')
  const [ruleType, setRuleType] = useState('')
  const [action, setAction] = useState('')
  const [pattern, setPattern] = useState('')
  const [useWildcard, setUseWildcard] = useState(false)
  const [thresholdMinutes, setThresholdMinutes] = useState('')
  const [timeoutDurationMinutes, setTimeoutDurationMinutes] = useState('')
  const [requiredChannelId, setRequiredChannelId] = useState('')

  useEffect(() => {
    async function fetchData() {
      const res = await fetch(`${API_BASE}/automod/form-data`).then((r) => r.json())
      setGuilds(res?.guilds ?? {})
      setChannels(res?.channels ?? {})
    }
    fetchData()
  }, [])

  const filteredChannels = selectedGuild ? (channels[selectedGuild] ?? []) : []

  const showPattern = ruleType === 'username_match'
  const showAccountAge = ruleType === 'account_age'
  const showThreshold = ['role_acquired', 'vc_join', 'message_post'].includes(ruleType)
  const showRoleCount = ruleType === 'role_count'
  const showRequiredChannel = ['vc_without_intro', 'msg_without_intro'].includes(ruleType)
  const showTimeoutDuration = action === 'timeout'

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!selectedGuild || !ruleType || !action) return
    setSubmitting(true)
    try {
      let thresholdSeconds: number | null = null
      if (showAccountAge && thresholdMinutes) {
        thresholdSeconds = parseInt(thresholdMinutes, 10) * 60
      } else if (showThreshold && thresholdMinutes) {
        thresholdSeconds = parseInt(thresholdMinutes, 10)
      } else if (showRoleCount && thresholdMinutes) {
        thresholdSeconds = parseInt(thresholdMinutes, 10)
      }

      let timeoutSeconds: number | null = null
      if (showTimeoutDuration && timeoutDurationMinutes) {
        timeoutSeconds = parseInt(timeoutDurationMinutes, 10) * 60
      }

      const body: Record<string, unknown> = {
        guild_id: selectedGuild,
        rule_type: ruleType,
        action,
        pattern: showPattern ? pattern || null : null,
        use_wildcard: showPattern ? useWildcard : false,
        threshold_seconds: thresholdSeconds,
        timeout_duration_seconds: timeoutSeconds,
        required_channel_id: showRequiredChannel ? requiredChannelId || null : null,
      }

      await fetch(`${API_BASE}/automod/rules`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      router.push('/dashboard/automod')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link href="/dashboard/automod">
          <Button variant="outline" size="sm">
            Back
          </Button>
        </Link>
        <h1 className="text-2xl font-bold">Create AutoMod Rule</h1>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>New Rule</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium mb-1.5 block">Server</label>
              <Select
                value={selectedGuild}
                onValueChange={(v) => {
                  setSelectedGuild(v)
                  setRequiredChannelId('')
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

            <div>
              <label className="text-sm font-medium mb-1.5 block">Rule Type</label>
              <Select value={ruleType} onValueChange={setRuleType}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select rule type" />
                </SelectTrigger>
                <SelectContent>
                  {RULE_TYPES.map((rt) => (
                    <SelectItem key={rt.value} value={rt.value}>
                      {rt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <label className="text-sm font-medium mb-1.5 block">Action</label>
              <Select value={action} onValueChange={setAction}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select action" />
                </SelectTrigger>
                <SelectContent>
                  {ACTIONS.map((a) => (
                    <SelectItem key={a.value} value={a.value}>
                      {a.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {showPattern && (
              <>
                <div>
                  <label className="text-sm font-medium mb-1.5 block">Pattern</label>
                  <Input
                    value={pattern}
                    onChange={(e) => setPattern(e.target.value)}
                    placeholder="e.g. spam*bot"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <Checkbox
                    id="use_wildcard"
                    checked={useWildcard}
                    onCheckedChange={(checked) => setUseWildcard(checked === true)}
                  />
                  <label htmlFor="use_wildcard" className="text-sm">
                    Use wildcard matching
                  </label>
                </div>
              </>
            )}

            {showAccountAge && (
              <div>
                <label className="text-sm font-medium mb-1.5 block">
                  Account Age Threshold (minutes, 1-20160)
                </label>
                <Input
                  type="number"
                  min={1}
                  max={20160}
                  value={thresholdMinutes}
                  onChange={(e) => setThresholdMinutes(e.target.value)}
                  placeholder="e.g. 60"
                />
              </div>
            )}

            {showThreshold && (
              <div>
                <label className="text-sm font-medium mb-1.5 block">
                  Threshold (seconds, 1-3600)
                </label>
                <Input
                  type="number"
                  min={1}
                  max={3600}
                  value={thresholdMinutes}
                  onChange={(e) => setThresholdMinutes(e.target.value)}
                  placeholder="e.g. 300"
                />
              </div>
            )}

            {showRoleCount && (
              <div>
                <label className="text-sm font-medium mb-1.5 block">
                  Role Count (1-100, @everyone excluded)
                </label>
                <Input
                  type="number"
                  min={1}
                  max={100}
                  value={thresholdMinutes}
                  onChange={(e) => setThresholdMinutes(e.target.value)}
                  placeholder="e.g. 5"
                />
              </div>
            )}

            {showRequiredChannel && (
              <div>
                <label className="text-sm font-medium mb-1.5 block">Required Channel</label>
                <Select
                  value={requiredChannelId}
                  onValueChange={setRequiredChannelId}
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
            )}

            {showTimeoutDuration && (
              <div>
                <label className="text-sm font-medium mb-1.5 block">
                  Timeout Duration (minutes, 1-40320)
                </label>
                <Input
                  type="number"
                  min={1}
                  max={40320}
                  value={timeoutDurationMinutes}
                  onChange={(e) => setTimeoutDurationMinutes(e.target.value)}
                  placeholder="e.g. 60"
                />
              </div>
            )}

            <Button type="submit" disabled={submitting || !selectedGuild || !ruleType || !action}>
              {submitting ? 'Creating...' : 'Create Rule'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
