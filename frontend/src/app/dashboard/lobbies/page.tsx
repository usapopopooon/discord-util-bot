import { apiFetch } from "@/lib/api";
import type { Lobby, GuildsMap, ChannelsMap } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable, type Column } from "@/components/data-table";
import { DeleteButton } from "@/components/delete-button";

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

export default async function LobbiesPage() {
  const [lobbiesRes, guildsRes, channelsRes] = await Promise.all([
    apiFetch<Lobby[]>("/api/v1/lobbies"),
    apiFetch<GuildsMap>("/api/v1/guilds"),
    apiFetch<ChannelsMap>("/api/v1/channels"),
  ]);

  const lobbies = lobbiesRes.data ?? [];
  const guilds = guildsRes.data ?? {};
  const channels = channelsRes.data ?? {};

  const columns: Column<Lobby>[] = [
    {
      header: "Server",
      accessor: (row) => resolveGuildName(guilds, row.guild_id),
    },
    {
      header: "Channel",
      accessor: (row) =>
        resolveChannelName(channels, row.guild_id, row.lobby_channel_id),
    },
    {
      header: "User Limit",
      accessor: (row) => row.default_user_limit,
    },
    {
      header: "Bitrate",
      accessor: (row) =>
        row.default_bitrate ? `${row.default_bitrate / 1000}kbps` : "-",
    },
    {
      header: "Actions",
      accessor: (row) => (
        <DeleteButton endpoint={`/api/proxy/api/v1/lobbies/${row.id}`} />
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Voice Lobbies</h1>
      <Card>
        <CardHeader>
          <CardTitle>Configured Lobbies</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable
            columns={columns}
            data={lobbies}
            emptyMessage="No lobbies configured"
          />
        </CardContent>
      </Card>
    </div>
  );
}
