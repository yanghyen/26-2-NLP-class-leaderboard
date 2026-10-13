import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import { AlertCircle, Inbox, LoaderCircle, RefreshCw } from "lucide-react";

export function PageHeader({
  title,
  description,
  action
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3 border-b border-zinc-200 pb-5 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-2xl font-bold text-zinc-950">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm leading-6 text-zinc-600">{description}</p>}
      </div>
      {action}
    </div>
  );
}

export function Button({
  variant = "primary",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger" | "ghost";
}) {
  const variants = {
    primary: "bg-zinc-950 text-white hover:bg-zinc-800",
    secondary: "border border-zinc-300 bg-white text-zinc-800 hover:bg-zinc-50",
    danger: "bg-red-700 text-white hover:bg-red-800",
    ghost: "text-zinc-700 hover:bg-zinc-100"
  };
  return (
    <button
      className={`inline-flex min-h-10 items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-semibold transition focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 ${variants[variant]} ${className}`}
      {...props}
    />
  );
}

export function LinkButton({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      className="inline-flex min-h-10 items-center justify-center rounded-md bg-zinc-950 px-4 py-2 text-sm font-semibold text-white hover:bg-zinc-800 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2"
    >
      {children}
    </Link>
  );
}

export function Field({
  label,
  hint,
  children
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block text-sm font-medium text-zinc-800">
      <span>{label}</span>
      <span className="mt-2 block">{children}</span>
      {hint && <span className="mt-1 block text-xs font-normal text-zinc-500">{hint}</span>}
    </label>
  );
}

export const inputClass =
  "w-full rounded-md border border-zinc-300 bg-white px-3 py-2.5 text-sm text-zinc-950 outline-none transition placeholder:text-zinc-400 focus:border-emerald-600 focus:ring-2 focus:ring-emerald-100 disabled:bg-zinc-100";

export function LoadingState({ label = "불러오는 중" }: { label?: string }) {
  return (
    <div className="flex min-h-48 items-center justify-center gap-3 text-sm text-zinc-600" role="status">
      <LoaderCircle className="h-5 w-5 animate-spin" /> {label}
    </div>
  );
}

export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <div className="border border-red-200 bg-red-50 p-5 text-sm text-red-900" role="alert">
      <div className="flex items-start gap-3">
        <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />
        <div className="flex-1">
          <p>{message}</p>
          {retry && (
            <Button variant="secondary" className="mt-4" onClick={retry}>
              <RefreshCw className="h-4 w-4" /> 다시 시도
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="border border-dashed border-zinc-300 bg-white px-6 py-12 text-center">
      <Inbox className="mx-auto h-7 w-7 text-zinc-400" />
      <h2 className="mt-3 text-base font-semibold text-zinc-900">{title}</h2>
      <p className="mx-auto mt-1 max-w-md text-sm leading-6 text-zinc-600">{description}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function Stat({ label, value, icon: Icon }: { label: string; value: string | number; icon: LucideIcon }) {
  return (
    <div className="border border-zinc-200 bg-white p-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-zinc-600">{label}</p>
        <Icon className="h-4 w-4 text-emerald-700" />
      </div>
      <p className="mt-2 text-2xl font-bold text-zinc-950">{value}</p>
    </div>
  );
}

export function MockBadge() {
  if (process.env.NEXT_PUBLIC_SHOW_MOCK_EVALUATION !== "true") return null;
  return (
    <span className="inline-flex items-center rounded border border-amber-300 bg-amber-50 px-2 py-1 text-xs font-semibold text-amber-900">
      Mock Evaluation
    </span>
  );
}
