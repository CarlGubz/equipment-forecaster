import type { Prediction } from "./types";

export function downloadText(filename: string, text: string, mime = "text/csv") {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function predictionsToCsv(preds: Prediction[]): string {
  const cols = [
    "client",
    "part_number",
    "part_name",
    "equipment",
    "last_order_date",
    "predicted_next_order_date",
    "days_until_due",
    "avg_interval_days",
    "status",
    "confidence",
    "suggested_quantity",
    "order_count",
  ];
  const escape = (v: unknown) => {
    const s = v === null || v === undefined ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const header = cols.join(",");
  const rows = preds.map((p) =>
    cols.map((c) => escape((p as unknown as Record<string, unknown>)[c])).join(",")
  );
  return [header, ...rows].join("\n");
}

export function statusLabel(status: string): string {
  switch (status) {
    case "overdue":
      return "Overdue";
    case "due_soon":
      return "Due soon";
    case "scheduled":
      return "Scheduled";
    default:
      return "Low history";
  }
}

export function daysLabel(days: number | null): string {
  if (days === null) return "—";
  if (days < 0) return `${Math.abs(days)}d overdue`;
  if (days === 0) return "today";
  return `in ${days}d`;
}
