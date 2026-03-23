"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import type {
  EventLogConfig,
  GuildsMap,
  ChannelsMap,
} from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { DataTable, type Column } from "@/components/data-table";
import { DeleteButton } from "@/components/delete-button";
import { ToggleButton } from "@/components/toggle-button";

const EVENT_TYPES = [
  "message_delete",
  "message_edit",
  "message_purge",
  "member_join",
  "member_leave",
  "member_kick",
  "member_ban",
  "member_unban",
  "member_timeout",
  "role_change",
  "nickname_change",
  "channel_create",
  "channel_delete",
  "channel_update",
  "role_create",
  "role_delete",
  "role_update",
  "voice_state",
  "invite_create",
  "invite_delete",
  "thread_create",
  "thread_delete",
  "thread_update",
  "server_update",
  "emoji_update",
] as const;

function resolveGuildName(guilds: GuildsMap, guildId: string) {
  return guilds[guildId] ?? guildId;
}

function resolveChannelName(
  channels: ChannelsMap,
  guildId: string,
  channelId: string
) {
  const list = channels[guildId] ?? [];
  const ch = list.find((c) => c.id === channelId);
  return ch ? `#${ch.name}` : channelId;
}

export default function EventLogPage() {
  const router = useRouter();
  const [configs, setConfigs] = useState<EventLogConfig[]>([]);
  const [guilds, setGuilds] = useState<GuildsMap>({});
  const [channels, setChannels] = useState<ChannelsMap>({});
  const [loading, setLoading] = useState(true);

  // Form state
  const [selectedGuild, setSelectedGuild] = useState("");
  const [selectedEventType, setSelectedEventType] = useState("");
  const [selectedChannel, setSelectedChannel] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const fetchData = useCallback(async () => {
    const [configsRes, guildsRes, channelsRes] = await Promise.all([
      fetch("/api/proxy/api/v1/eventlog").then((r) => r.json()),
      fetch("/api/proxy/api/v1/guilds").then((r) => r.json()),
      fetch("/api/proxy/api/v1/channels").then((r) => r.json()),
    ]);
    setConfigs(configsRes ?? []);
    setGuilds(guildsRes ?? {});
    setChannels(channelsRes ?? {});
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const filteredChannels = selectedGuild
    ? channels[selectedGuild] ?? []
    : [];

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedGuild || !selectedEventType || !selectedChannel) return;
    setSubmitting(true);
    try {
      await fetch("/api/proxy/api/v1/eventlog", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          guild_id: selectedGuild,
          event_type: selectedEventType,
          channel_id: selectedChannel,
        }),
      });
      setSelectedGuild("");
      setSelectedEventType("");
      setSelectedChannel("");
      fetchData();
      router.refresh();
    } finally {
      setSubmitting(false);
    }
  }

  const columns: Column<EventLogConfig>[] = [
    {
      header: "Server",
      accessor: (row) => resolveGuildName(guilds, row.guild_id),
    },
    {
      header: "Event Type",
      accessor: (row) => (
        <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
          {row.event_type}
        </code>
      ),
    },
    {
      header: "Channel",
      accessor: (row) =>
        resolveChannelName(channels, row.guild_id, row.channel_id),
    },
    {
      header: "Status",
      accessor: (row) => (
        <Badge
          variant={row.enabled ? "default" : "secondary"}
          className={row.enabled ? "bg-green-600 hover:bg-green-600" : ""}
        >
          {row.enabled ? "Enabled" : "Disabled"}
        </Badge>
      ),
    },
    {
      header: "Actions",
      accessor: (row) => (
        <div className="flex items-center gap-2">
          <ToggleButton
            endpoint={`/api/proxy/api/v1/eventlog/${row.id}/toggle`}
            enabled={row.enabled}
          />
          <DeleteButton
            endpoint={`/api/proxy/api/v1/eventlog/${row.id}/delete`}
          />
        </div>
      ),
    },
  ];

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Event Log</h1>
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Event Log</h1>

      <Card>
        <CardHeader>
          <CardTitle>Add Event Log</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex items-end gap-4">
            <div className="flex-1">
              <label className="text-sm font-medium mb-1.5 block">Server</label>
              <Select
                value={selectedGuild}
                onValueChange={(v) => {
                  setSelectedGuild(v);
                  setSelectedChannel("");
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
              <label className="text-sm font-medium mb-1.5 block">
                Event Type
              </label>
              <Select
                value={selectedEventType}
                onValueChange={setSelectedEventType}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select event type" />
                </SelectTrigger>
                <SelectContent>
                  {EVENT_TYPES.map((type) => (
                    <SelectItem key={type} value={type}>
                      {type}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex-1">
              <label className="text-sm font-medium mb-1.5 block">
                Channel
              </label>
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
            <Button
              type="submit"
              disabled={
                submitting ||
                !selectedGuild ||
                !selectedEventType ||
                !selectedChannel
              }
            >
              {submitting ? "Adding..." : "Add"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Configured Event Logs</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable
            columns={columns}
            data={configs}
            emptyMessage="No event logs configured"
          />
        </CardContent>
      </Card>
    </div>
  );
}
