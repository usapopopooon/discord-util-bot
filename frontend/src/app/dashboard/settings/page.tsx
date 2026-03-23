"use client";

import { useEffect, useState, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";

interface SettingsData {
  timezone_offset: number;
  email: string;
  pending_email: string | null;
}

export default function SettingsPage() {
  const [loading, setLoading] = useState(true);

  // Timezone
  const [timezoneOffset, setTimezoneOffset] = useState(9);
  const [savingTimezone, setSavingTimezone] = useState(false);

  // Email
  const [currentEmail, setCurrentEmail] = useState("");
  const [pendingEmail, setPendingEmail] = useState<string | null>(null);
  const [newEmail, setNewEmail] = useState("");
  const [savingEmail, setSavingEmail] = useState(false);

  // Password
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [savingPassword, setSavingPassword] = useState(false);

  const fetchSettings = useCallback(async () => {
    try {
      const res = await fetch("/api/v1/settings");
      if (res.ok) {
        const data: SettingsData = await res.json();
        setTimezoneOffset(data.timezone_offset);
        setCurrentEmail(data.email);
        setPendingEmail(data.pending_email ?? null);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  async function handleSaveTimezone(e: React.FormEvent) {
    e.preventDefault();
    setSavingTimezone(true);
    try {
      const res = await fetch("/api/v1/settings/timezone", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ timezone_offset: timezoneOffset }),
      });
      if (res.ok) {
        toast.success("Timezone updated successfully");
      } else {
        const body = await res.text();
        let msg: string;
        try {
          msg = JSON.parse(body).detail || body;
        } catch {
          msg = body;
        }
        toast.error(`Failed to update timezone: ${msg}`);
      }
    } catch {
      toast.error("Failed to update timezone");
    } finally {
      setSavingTimezone(false);
    }
  }

  async function handleSaveEmail(e: React.FormEvent) {
    e.preventDefault();
    if (!newEmail.trim()) return;
    setSavingEmail(true);
    try {
      const res = await fetch("/api/v1/settings/email", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: newEmail }),
      });
      if (res.ok) {
        toast.success("Email updated successfully");
        setCurrentEmail(newEmail);
        setNewEmail("");
        setPendingEmail(null);
      } else {
        const body = await res.text();
        let msg: string;
        try {
          msg = JSON.parse(body).detail || body;
        } catch {
          msg = body;
        }
        toast.error(`Failed to update email: ${msg}`);
      }
    } catch {
      toast.error("Failed to update email");
    } finally {
      setSavingEmail(false);
    }
  }

  async function handleSavePassword(e: React.FormEvent) {
    e.preventDefault();
    if (!newPassword) return;
    if (newPassword !== confirmPassword) {
      toast.error("Passwords do not match");
      return;
    }
    setSavingPassword(true);
    try {
      const res = await fetch("/api/v1/settings/password", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password: newPassword }),
      });
      if (res.ok) {
        toast.success("Password updated successfully");
        setNewPassword("");
        setConfirmPassword("");
      } else {
        const body = await res.text();
        let msg: string;
        try {
          msg = JSON.parse(body).detail || body;
        } catch {
          msg = body;
        }
        toast.error(`Failed to update password: ${msg}`);
      }
    } catch {
      toast.error("Failed to update password");
    } finally {
      setSavingPassword(false);
    }
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  const offsetLabel = timezoneOffset >= 0 ? `UTC+${timezoneOffset}` : `UTC${timezoneOffset}`;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Settings</h1>

      {/* Timezone */}
      <Card>
        <CardHeader>
          <CardTitle>Timezone</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSaveTimezone} className="space-y-4 max-w-md">
            <p className="text-sm text-muted-foreground">
              Current timezone: <span className="font-medium text-foreground">{offsetLabel}</span>
            </p>
            <div>
              <Label htmlFor="timezone-offset">UTC Offset</Label>
              <Input
                id="timezone-offset"
                type="number"
                min={-12}
                max={14}
                value={timezoneOffset}
                onChange={(e) =>
                  setTimezoneOffset(Math.min(14, Math.max(-12, parseInt(e.target.value, 10) || 0)))
                }
                className="w-32 mt-1.5"
              />
            </div>
            <Button type="submit" disabled={savingTimezone}>
              {savingTimezone ? "Saving..." : "Save Timezone"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Email */}
      <Card>
        <CardHeader>
          <CardTitle>Email</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSaveEmail} className="space-y-4 max-w-md">
            <p className="text-sm text-muted-foreground">
              Current email: <span className="font-medium text-foreground">{currentEmail}</span>
            </p>
            {pendingEmail && (
              <p className="text-sm text-yellow-500">Pending email change: {pendingEmail}</p>
            )}
            <div>
              <Label htmlFor="new-email">New Email</Label>
              <Input
                id="new-email"
                type="email"
                value={newEmail}
                onChange={(e) => setNewEmail(e.target.value)}
                placeholder="Enter new email..."
                className="mt-1.5"
              />
            </div>
            <Button type="submit" disabled={savingEmail || !newEmail.trim()}>
              {savingEmail ? "Saving..." : "Update Email"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Password */}
      <Card>
        <CardHeader>
          <CardTitle>Password</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSavePassword} className="space-y-4 max-w-md">
            <div>
              <Label htmlFor="new-password">New Password</Label>
              <Input
                id="new-password"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="Enter new password..."
                className="mt-1.5"
              />
            </div>
            <div>
              <Label htmlFor="confirm-password">Confirm Password</Label>
              <Input
                id="confirm-password"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Confirm new password..."
                className="mt-1.5"
              />
            </div>
            <Button type="submit" disabled={savingPassword || !newPassword}>
              {savingPassword ? "Saving..." : "Update Password"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
