"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import type { TicketPanel, GuildsMap, ChannelsMap } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable, type Column } from "@/components/data-table";
import { DeleteButton } from "@/components/delete-button";

function resolveGuildName(guilds: GuildsMap, guildId: string) {
  return guilds[guildId] ?? guildId;
}

function resolveChannelName(channels: ChannelsMap, guildId: string, channelId: string) {
  const list = channels[guildId] ?? [];
  const ch = list.find((c) => c.id === channelId);
  return ch ? `#${ch.name}` : channelId;
}

export default function TicketPanelsPage() {
  const [panels, setPanels] = useState<TicketPanel[]>([]);
  const [guilds, setGuilds] = useState<GuildsMap>({});
  const [channels, setChannels] = useState<ChannelsMap>({});
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    const [panelsRes, guildsRes, channelsRes] = await Promise.all([
      fetch("/api/proxy/api/v1/tickets/panels").then((r) => r.json()),
      fetch("/api/proxy/api/v1/guilds").then((r) => r.json()),
      fetch("/api/proxy/api/v1/channels").then((r) => r.json()),
    ]);
    setPanels(panelsRes ?? []);
    setGuilds(guildsRes ?? {});
    setChannels(channelsRes ?? {});
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const columns: Column<TicketPanel>[] = [
    {
      header: "Server",
      accessor: (row) => resolveGuildName(guilds, row.guild_id),
    },
    {
      header: "Channel",
      accessor: (row) => resolveChannelName(channels, row.guild_id, row.channel_id),
    },
    {
      header: "Title",
      accessor: (row) => row.title,
    },
    {
      header: "Posted",
      accessor: (row) => (
        <Badge
          className={
            row.message_id ? "bg-green-600 hover:bg-green-600" : "bg-gray-500 hover:bg-gray-500"
          }
        >
          {row.message_id ? "Yes" : "No"}
        </Badge>
      ),
    },
    {
      header: "Actions",
      accessor: (row) => (
        <div className="flex items-center gap-2">
          <Link href={`/dashboard/tickets/panels/${row.id}`}>
            <Button variant="outline" size="sm">
              View
            </Button>
          </Link>
          <DeleteButton endpoint={`/api/proxy/api/v1/tickets/panels/${row.id}/delete`} />
        </div>
      ),
    },
  ];

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Ticket Panels</h1>
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link href="/dashboard/tickets">
            <Button variant="outline" size="sm">
              Back
            </Button>
          </Link>
          <h1 className="text-2xl font-bold">Ticket Panels</h1>
        </div>
        <Link href="/dashboard/tickets/panels/new">
          <Button>+ Create Panel</Button>
        </Link>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Configured Panels</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable columns={columns} data={panels} emptyMessage="No ticket panels configured" />
        </CardContent>
      </Card>
    </div>
  );
}
