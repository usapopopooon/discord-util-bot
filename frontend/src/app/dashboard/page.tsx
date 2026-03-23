import { apiFetch } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import Link from "next/link";

interface DashboardData {
  email: string;
}

const quickLinks = [
  {
    href: "/dashboard/automod",
    title: "AutoMod",
    description: "Manage auto-moderation rules and settings",
  },
  {
    href: "/dashboard/roles",
    title: "Role Panels",
    description: "Configure self-assignable role panels",
  },
  {
    href: "/dashboard/tickets",
    title: "Tickets",
    description: "Manage support ticket system",
  },
  {
    href: "/dashboard/sticky",
    title: "Sticky Messages",
    description: "Configure persistent channel messages",
  },
  {
    href: "/dashboard/bump",
    title: "Bump",
    description: "Bump reminder configuration",
  },
  {
    href: "/dashboard/lobbies",
    title: "Voice Lobbies",
    description: "Manage voice channel lobbies",
  },
  {
    href: "/dashboard/eventlog",
    title: "Event Log",
    description: "Configure event logging channels",
  },
  {
    href: "/dashboard/joinrole",
    title: "Join Roles",
    description: "Auto-assign roles on member join",
  },
  {
    href: "/dashboard/settings",
    title: "Settings",
    description: "Timezone, email, and password settings",
  },
  {
    href: "/dashboard/maintenance",
    title: "Maintenance",
    description: "Database cleanup and system stats",
  },
];

export default async function DashboardPage() {
  const dashboardRes = await apiFetch<DashboardData>("/api/v1/dashboard");
  const email = dashboardRes.data?.email ?? "Admin";

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Dashboard</h1>

      <Card>
        <CardHeader>
          <CardTitle>Welcome</CardTitle>
          <CardDescription>Discord Bot Admin Panel</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">
            Logged in as <span className="font-medium text-foreground">{email}</span>. Select a
            section from the sidebar or use the quick links below.
          </p>
        </CardContent>
      </Card>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {quickLinks.map((link) => (
          <Link key={link.href} href={link.href} className="group">
            <Card className="h-full transition-colors group-hover:border-primary/50">
              <CardHeader className="pb-2">
                <CardTitle className="text-base">{link.title}</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">{link.description}</p>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
