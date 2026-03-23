import { apiFetch } from "@/lib/api";
import type { BumpConfig, BumpReminder, GuildsMap, ChannelsMap } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { DataTable, type Column } from "@/components/data-table";
import { DeleteButton } from "@/components/delete-button";
import { ToggleButton } from "@/components/toggle-button";

function resolveGuildName(guilds: GuildsMap, guildId: string) {
  return guilds[guildId] ?? guildId;
}

function resolveChannelName(channels: ChannelsMap, guildId: string, channelId: string) {
  const list = channels[guildId] ?? [];
  const ch = list.find((c) => c.id === channelId);
  return ch ? `#${ch.name}` : channelId;
}

interface BumpData {
  configs: BumpConfig[];
  reminders: BumpReminder[];
}

export default async function BumpPage() {
  const [bumpRes, guildsRes, channelsRes] = await Promise.all([
    apiFetch<BumpData>("/api/v1/bump"),
    apiFetch<GuildsMap>("/api/v1/guilds"),
    apiFetch<ChannelsMap>("/api/v1/channels"),
  ]);

  const configs = bumpRes.data?.configs ?? [];
  const reminders = bumpRes.data?.reminders ?? [];
  const guilds = guildsRes.data ?? {};
  const channels = channelsRes.data ?? {};

  const configColumns: Column<BumpConfig>[] = [
    {
      header: "Server",
      accessor: (row) => resolveGuildName(guilds, row.guild_id),
    },
    {
      header: "Channel",
      accessor: (row) => resolveChannelName(channels, row.guild_id, row.channel_id),
    },
    {
      header: "Service",
      accessor: (row) => row.service_name,
    },
    {
      header: "Actions",
      accessor: (row) => <DeleteButton endpoint={`/api/v1/bump/config/${row.guild_id}/delete`} />,
    },
  ];

  const reminderColumns: Column<BumpReminder>[] = [
    {
      header: "Server",
      accessor: (row) => resolveGuildName(guilds, row.guild_id),
    },
    {
      header: "Channel",
      accessor: (row) => resolveChannelName(channels, row.guild_id, row.channel_id),
    },
    {
      header: "Service",
      accessor: (row) => row.service_name,
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
          <ToggleButton endpoint={`/api/v1/bump/reminder/${row.id}/toggle`} enabled={row.enabled} />
          <DeleteButton endpoint={`/api/v1/bump/reminder/${row.id}/delete`} />
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Bump</h1>

      <Card>
        <CardHeader>
          <CardTitle>Bump Configs</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable
            columns={configColumns}
            data={configs}
            emptyMessage="No bump configs configured"
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Bump Reminders</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable
            columns={reminderColumns}
            data={reminders}
            emptyMessage="No bump reminders configured"
          />
        </CardContent>
      </Card>
    </div>
  );
}
