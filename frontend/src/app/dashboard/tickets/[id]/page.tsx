"use client";

import { useEffect, useState, useCallback, use } from "react";
import Link from "next/link";
import type { TicketDetail, GuildsMap } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DeleteButton } from "@/components/delete-button";

function resolveGuildName(guilds: GuildsMap, guildId: string) {
  return guilds[guildId] ?? guildId;
}

export default function TicketDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [ticket, setTicket] = useState<TicketDetail | null>(null);
  const [guilds, setGuilds] = useState<GuildsMap>({});
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    const [ticketRes, guildsRes] = await Promise.all([
      fetch(`/api/proxy/api/v1/tickets/${id}`).then((r) => r.json()),
      fetch("/api/proxy/api/v1/guilds").then((r) => r.json()),
    ]);
    setTicket(ticketRes ?? null);
    setGuilds(guildsRes ?? {});
    setLoading(false);
  }, [id]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Ticket Detail</h1>
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (!ticket) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Ticket Not Found</h1>
        <Link href="/dashboard/tickets">
          <Button variant="outline">Back to Tickets</Button>
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link href="/dashboard/tickets">
          <Button variant="outline" size="sm">
            Back
          </Button>
        </Link>
        <h1 className="text-2xl font-bold">Ticket #{ticket.ticket_number}</h1>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-3">
            Ticket Info
            <Badge
              className={
                ticket.status === "open"
                  ? "bg-green-600 hover:bg-green-600"
                  : "bg-gray-500 hover:bg-gray-500"
              }
            >
              {ticket.status}
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <dt className="font-medium text-muted-foreground">Server</dt>
              <dd>{resolveGuildName(guilds, ticket.guild_id)}</dd>
            </div>
            <div>
              <dt className="font-medium text-muted-foreground">Ticket Number</dt>
              <dd>#{ticket.ticket_number}</dd>
            </div>
            <div>
              <dt className="font-medium text-muted-foreground">User</dt>
              <dd>{ticket.username}</dd>
            </div>
            <div>
              <dt className="font-medium text-muted-foreground">User ID</dt>
              <dd className="font-mono text-xs">{ticket.user_id}</dd>
            </div>
            <div>
              <dt className="font-medium text-muted-foreground">Claimed By</dt>
              <dd>{ticket.claimed_by ?? "-"}</dd>
            </div>
            <div>
              <dt className="font-medium text-muted-foreground">Closed By</dt>
              <dd>{ticket.closed_by ?? "-"}</dd>
            </div>
            <div>
              <dt className="font-medium text-muted-foreground">Created</dt>
              <dd>{new Date(ticket.created_at).toLocaleString()}</dd>
            </div>
            <div>
              <dt className="font-medium text-muted-foreground">Closed At</dt>
              <dd>{ticket.closed_at ? new Date(ticket.closed_at).toLocaleString() : "-"}</dd>
            </div>
            <div>
              <dt className="font-medium text-muted-foreground">Channel ID</dt>
              <dd className="font-mono text-xs">{ticket.channel_id ?? "Deleted"}</dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      {ticket.transcript && (
        <Card>
          <CardHeader>
            <CardTitle>Transcript</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="max-h-[600px] overflow-auto rounded-md bg-muted p-4 text-sm whitespace-pre-wrap">
              {ticket.transcript}
            </pre>
          </CardContent>
        </Card>
      )}

      <div>
        <DeleteButton
          endpoint={`/api/proxy/api/v1/tickets/${id}/delete`}
          label="Delete Ticket"
          confirmMessage="Are you sure you want to delete this ticket? This action cannot be undone."
        />
      </div>
    </div>
  );
}
