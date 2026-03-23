"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import type { RolePanel, GuildsMap, ChannelsMap } from "@/lib/types";
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

export default function RolePanelsPage() {
  const [panels, setPanels] = useState<RolePanel[]>([]);
  const [guilds, setGuilds] = useState<GuildsMap>({});
  const [channels, setChannels] = useState<ChannelsMap>({});
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    const [panelsRes, guildsRes, channelsRes] = await Promise.all([
      fetch("/api/v1/rolepanels").then((r) => r.json()),
      fetch("/api/v1/guilds").then((r) => r.json()),
      fetch("/api/v1/channels").then((r) => r.json()),
    ]);
    setPanels(panelsRes ?? []);
    setGuilds(guildsRes ?? {});
    setChannels(channelsRes ?? {});
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const columns: Column<RolePanel>[] = [
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
      header: "Type",
      accessor: (row) => (
        <Badge variant="secondary">{row.panel_type === "button" ? "Button" : "Reaction"}</Badge>
      ),
    },
    {
      header: "Items",
      accessor: (row) => row.item_count,
    },
    {
      header: "Posted",
      accessor: (row) =>
        row.message_id ? (
          <Badge className="bg-green-600 hover:bg-green-600">Yes</Badge>
        ) : (
          <Badge variant="secondary">No</Badge>
        ),
    },
    {
      header: "Actions",
      accessor: (row) => (
        <div className="flex items-center gap-2">
          <Link href={`/dashboard/roles/${row.id}`}>
            <Button variant="outline" size="sm">
              Edit
            </Button>
          </Link>
          <DeleteButton
            endpoint={`/api/v1/rolepanels/${row.id}`}
            confirmMessage="Are you sure you want to delete this role panel? This action cannot be undone."
          />
        </div>
      ),
    },
  ];

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Role Panels</h1>
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Role Panels</h1>
        <Link href="/dashboard/roles/new">
          <Button>+ Create Panel</Button>
        </Link>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Configured Panels</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable columns={columns} data={panels} emptyMessage="No role panels configured" />
        </CardContent>
      </Card>
    </div>
  );
}
