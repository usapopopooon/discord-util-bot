"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import type { Ticket, GuildsMap } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable, type Column } from "@/components/data-table";
import { DeleteButton } from "@/components/delete-button";

type StatusFilter = "all" | "open" | "closed";

function resolveGuildName(guilds: GuildsMap, guildId: string) {
  return guilds[guildId] ?? guildId;
}

export default function TicketsPage() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [guilds, setGuilds] = useState<GuildsMap>({});
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");

  const fetchData = useCallback(async () => {
    const [ticketsRes, guildsRes] = await Promise.all([
      fetch("/api/proxy/api/v1/tickets").then((r) => r.json()),
      fetch("/api/proxy/api/v1/guilds").then((r) => r.json()),
    ]);
    setTickets(ticketsRes ?? []);
    setGuilds(guildsRes ?? {});
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const filteredTickets =
    statusFilter === "all"
      ? tickets
      : tickets.filter((t) => t.status === statusFilter);

  const columns: Column<Ticket>[] = [
    {
      header: "Server",
      accessor: (row) => resolveGuildName(guilds, row.guild_id),
    },
    {
      header: "#Number",
      accessor: (row) => `#${row.ticket_number}`,
    },
    {
      header: "User",
      accessor: (row) => row.username,
    },
    {
      header: "Status",
      accessor: (row) => (
        <Badge
          className={
            row.status === "open"
              ? "bg-green-600 hover:bg-green-600"
              : "bg-gray-500 hover:bg-gray-500"
          }
        >
          {row.status}
        </Badge>
      ),
    },
    {
      header: "Claimed By",
      accessor: (row) => row.claimed_by ?? "-",
    },
    {
      header: "Created",
      accessor: (row) => new Date(row.created_at).toLocaleDateString(),
    },
    {
      header: "Actions",
      accessor: (row) => (
        <div className="flex items-center gap-2">
          <Link href={`/dashboard/tickets/${row.id}`}>
            <Button variant="outline" size="sm">
              View
            </Button>
          </Link>
          <DeleteButton
            endpoint={`/api/proxy/api/v1/tickets/${row.id}/delete`}
          />
        </div>
      ),
    },
  ];

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Tickets</h1>
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Tickets</h1>
        <div className="flex gap-2">
          <Link href="/dashboard/tickets/panels">
            <Button variant="outline">Panels</Button>
          </Link>
        </div>
      </div>

      <div className="flex gap-2">
        {(["all", "open", "closed"] as const).map((status) => (
          <Button
            key={status}
            variant={statusFilter === status ? "default" : "outline"}
            size="sm"
            onClick={() => setStatusFilter(status)}
          >
            {status.charAt(0).toUpperCase() + status.slice(1)}
          </Button>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Tickets</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable
            columns={columns}
            data={filteredTickets}
            emptyMessage="No tickets found"
          />
        </CardContent>
      </Card>
    </div>
  );
}
