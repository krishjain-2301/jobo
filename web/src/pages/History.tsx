import { Download, MailCheck } from "lucide-react";
import { Badge, Button, Card, Empty, PageHeader } from "../components/ui";
import { daysSince, useHistory } from "../lib/hooks";

export default function HistoryPage() {
  const { data: rows = [], isLoading } = useHistory();
  const due = rows.filter((r) => daysSince(r.sent_at) >= 7).length;

  return (
    <>
      <PageHeader
        title="History"
        description="Every application you've sent. No reply after a week? Send one short, polite follow-up on the same thread."
        action={
          <a href="/api/export/sent.csv">
            <Button icon={<Download className="size-4" />}>Export CSV</Button>
          </a>
        }
      />
      <Card>
        {isLoading ? null : rows.length === 0 ? (
          <Empty icon={<MailCheck className="size-5" />} title="No applications sent yet" />
        ) : (
          <>
            {due > 0 && (
              <div className="border-b border-slate-100 bg-amber-50/60 px-5 py-3 text-[13px] text-amber-900">
                {due} application{due > 1 ? "s are" : " is"} over a week old - a good time to follow up if you haven't heard back.
              </div>
            )}
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-xs font-medium uppercase tracking-wide text-slate-400">
                  <th className="px-5 py-2.5 font-medium">Sent</th>
                  <th className="px-3 py-2.5 font-medium">Company</th>
                  <th className="px-3 py-2.5 font-medium">To</th>
                  <th className="px-3 py-2.5 font-medium">Subject</th>
                  <th className="px-5 py-2.5 font-medium" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((r) => {
                  const days = daysSince(r.sent_at);
                  return (
                    <tr key={r.id} className="hover:bg-slate-50/60">
                      <td className="whitespace-nowrap px-5 py-3 text-slate-500">
                        {new Date(r.sent_at).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                      </td>
                      <td className="px-3 py-3 font-medium text-slate-800">{r.company}</td>
                      <td className="px-3 py-3 text-slate-600">{r.email}</td>
                      <td className="max-w-sm truncate px-3 py-3 text-slate-600">{r.subject}</td>
                      <td className="px-5 py-3 text-right">
                        {days >= 7 ? <Badge tone="amber">Follow up</Badge> : <Badge>{days === 0 ? "Today" : `${days} d ago`}</Badge>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </>
        )}
      </Card>
    </>
  );
}
