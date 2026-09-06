import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { relativeTime, type Stats } from "@/lib/api";

export function StatsCards({ stats }: { stats: Stats }) {
  const items: { label: string; value: string }[] = [
    { label: "Messages", value: String(Number(stats.messages_received ?? 0)) },
    { label: "Replies", value: String(Number(stats.replies_sent ?? 0)) },
    { label: "Last message", value: relativeTime(stats.last_message_at) },
  ];

  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {items.map((item) => (
        <Card key={item.label}>
          <CardHeader className="space-y-0 p-4">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {item.label}
            </CardTitle>
          </CardHeader>
          <CardContent className="pb-4 pt-0">
            <p className="text-2xl font-semibold tracking-tight">{item.value}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}