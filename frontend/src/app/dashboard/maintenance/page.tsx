"use client";

import { useEffect, useState, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogClose,
} from "@/components/ui/dialog";
import { toast } from "sonner";

interface MaintenanceStats {
  lobbies: number;
  sessions: number;
  orphaned_channels: number;
  sticky_messages: number;
  bump_configs: number;
  automod_rules: number;
  tickets_open: number;
  tickets_closed: number;
  role_panels: number;
  join_role_configs: number;
  join_role_assignments: number;
  eventlog_configs: number;
}

interface CleanupResult {
  orphaned_channels_removed: number;
  expired_assignments_removed: number;
  stale_sessions_removed: number;
  message: string;
}

export default function MaintenancePage() {
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<MaintenanceStats | null>(null);
  const [cleaning, setCleaning] = useState(false);
  const [cleanupResult, setCleanupResult] = useState<CleanupResult | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch("/api/proxy/api/v1/maintenance");
      if (res.ok) {
        const data: MaintenanceStats = await res.json();
        setStats(data);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  async function handleCleanup() {
    setCleaning(true);
    setCleanupResult(null);
    setDialogOpen(false);
    try {
      const res = await fetch("/api/proxy/api/v1/maintenance/cleanup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (res.ok) {
        const result: CleanupResult = await res.json();
        setCleanupResult(result);
        toast.success("Cleanup completed successfully");
        // Refresh stats
        fetchStats();
      } else {
        const body = await res.text();
        let msg: string;
        try {
          msg = JSON.parse(body).detail || body;
        } catch {
          msg = body;
        }
        toast.error(`Cleanup failed: ${msg}`);
      }
    } catch {
      toast.error("Cleanup failed");
    } finally {
      setCleaning(false);
    }
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Maintenance</h1>
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  const statCards = stats
    ? [
        { label: "Voice Lobbies", value: stats.lobbies },
        { label: "Active Sessions", value: stats.sessions },
        { label: "Orphaned Channels", value: stats.orphaned_channels },
        { label: "Sticky Messages", value: stats.sticky_messages },
        { label: "Bump Configs", value: stats.bump_configs },
        { label: "AutoMod Rules", value: stats.automod_rules },
        { label: "Open Tickets", value: stats.tickets_open },
        { label: "Closed Tickets", value: stats.tickets_closed },
        { label: "Role Panels", value: stats.role_panels },
        { label: "Join Role Configs", value: stats.join_role_configs },
        { label: "Join Role Assignments", value: stats.join_role_assignments },
        { label: "Event Log Configs", value: stats.eventlog_configs },
      ]
    : [];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Maintenance</h1>

      {/* Stats Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {statCards.map((stat) => (
          <Card key={stat.label}>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                {stat.label}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">{stat.value}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Cleanup Action */}
      <Card>
        <CardHeader>
          <CardTitle>Database Cleanup</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Run cleanup to remove orphaned channels, expired join role assignments, and stale voice
            sessions.
          </p>

          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button variant="destructive" disabled={cleaning}>
                {cleaning ? "Running Cleanup..." : "Run Cleanup"}
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Confirm Cleanup</DialogTitle>
                <DialogDescription>
                  This will remove orphaned channels, expired assignments, and stale sessions from
                  the database. This action cannot be undone.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <DialogClose asChild>
                  <Button variant="outline">Cancel</Button>
                </DialogClose>
                <Button variant="destructive" onClick={handleCleanup}>
                  Confirm Cleanup
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          {/* Cleanup Results */}
          {cleanupResult && (
            <Card className="border-green-500/30 bg-green-500/5">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Cleanup Results</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-1 text-sm">
                  <li>
                    Orphaned channels removed:{" "}
                    <span className="font-medium">{cleanupResult.orphaned_channels_removed}</span>
                  </li>
                  <li>
                    Expired assignments removed:{" "}
                    <span className="font-medium">{cleanupResult.expired_assignments_removed}</span>
                  </li>
                  <li>
                    Stale sessions removed:{" "}
                    <span className="font-medium">{cleanupResult.stale_sessions_removed}</span>
                  </li>
                </ul>
                {cleanupResult.message && (
                  <p className="mt-2 text-sm text-muted-foreground">{cleanupResult.message}</p>
                )}
              </CardContent>
            </Card>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
