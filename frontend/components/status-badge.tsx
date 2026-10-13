import { statusTone, submissionStatusLabel } from "../lib/format";
import type { SubmissionKind, SubmissionStatus } from "../lib/types";

export function StatusBadge({ status, kind }: { status: SubmissionStatus; kind?: SubmissionKind }) {
  const tone = statusTone(status);
  const colors = {
    success: "border-emerald-200 bg-emerald-50 text-emerald-800",
    danger: "border-red-200 bg-red-50 text-red-800",
    progress: "border-blue-200 bg-blue-50 text-blue-800",
    neutral: "border-zinc-200 bg-zinc-100 text-zinc-700"
  };
  return (
    <span className={`inline-flex items-center rounded border px-2 py-1 text-xs font-semibold ${colors[tone]}`}>
      {submissionStatusLabel(kind, status)}
    </span>
  );
}
