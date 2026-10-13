"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { BarChart3, ClipboardList, FileArchive, Home, LayoutDashboard, ListChecks, LogOut, ShieldAlert, Trophy, Upload, UserRound, Users } from "lucide-react";
import { useEffect } from "react";

import { useAuth } from "./auth-provider";
import { LoadingState, MockBadge } from "./ui";

const studentNav = [
  ["Home", "/dashboard", Home], ["Tasks", "/tasks", ClipboardList], ["Submit", "/submit", Upload],
  ["My Submissions", "/submissions", FileArchive], ["Leaderboard", "/leaderboard", Trophy], ["Profile", "/profile", UserRound]
] as const;
const adminNav = [
  ["Dashboard", "/admin", LayoutDashboard], ["Roster", "/admin/roster", Users], ["Participants", "/admin/participants", Users],
  ["Tasks", "/admin/tasks", ClipboardList], ["Submissions", "/admin/submissions", FileArchive], ["Evaluation Jobs", "/admin/jobs", ListChecks],
  ["Quarantine", "/admin/quarantine", ShieldAlert]
] as const;

export function ProtectedShell({ children }: { children: React.ReactNode }) {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  useEffect(() => {
    if (pathname.startsWith("/admin") && !loading && user?.role !== "ADMIN") router.replace("/login");
  }, [loading, pathname, router, user]);
  const admin = pathname.startsWith("/admin");
  if (admin && (loading || user?.role !== "ADMIN")) return <LoadingState label="관리자 계정을 확인하는 중" />;
  const nav = admin ? adminNav : studentNav;
  return (
    <div className="min-h-screen bg-zinc-50">
      <header className="sticky top-0 z-30 border-b border-zinc-200 bg-white">
        <div className="mx-auto flex h-16 max-w-[1440px] items-center justify-between px-4 sm:px-6">
          <Link href={admin ? "/admin" : "/dashboard"} className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-md bg-emerald-700 text-white"><BarChart3 className="h-5 w-5" /></span>
            <span className="hidden text-sm font-bold text-zinc-950 sm:block">NLP Leaderboard</span>
          </Link>
          <div className="flex items-center gap-3">
            <MockBadge />
            <span className="max-w-36 truncate text-sm font-medium text-zinc-800">{admin ? "관리자" : "연습용 리더보드"}</span>
            {user && <button onClick={logout} title="로그아웃" className="rounded-md p-2 text-zinc-600 hover:bg-zinc-100 focus:outline-none focus:ring-2 focus:ring-emerald-500"><LogOut className="h-5 w-5" /></button>}
          </div>
        </div>
      </header>
      <div className="mx-auto flex max-w-[1440px]">
        <aside className="hidden min-h-[calc(100vh-4rem)] w-60 shrink-0 border-r border-zinc-200 bg-white p-4 lg:block">
          <nav className="space-y-1" aria-label="주요 메뉴">
            {nav.map(([label, href, Icon]) => {
              const active = pathname === href || (href !== "/admin" && pathname.startsWith(`${href}/`));
              return <Link key={href} href={href} className={`flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium ${active ? "bg-emerald-50 text-emerald-900" : "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-950"}`}><Icon className="h-4 w-4" /> {label}</Link>;
            })}
          </nav>
        </aside>
        <div className="min-w-0 flex-1">
          <nav className="flex gap-1 overflow-x-auto border-b border-zinc-200 bg-white px-3 py-2 lg:hidden" aria-label="모바일 메뉴">
            {nav.map(([label, href, Icon]) => <Link key={href} href={href} className={`flex shrink-0 items-center gap-2 rounded-md px-3 py-2 text-xs font-semibold ${pathname === href ? "bg-emerald-50 text-emerald-900" : "text-zinc-600"}`}><Icon className="h-4 w-4" /> {label}</Link>)}
          </nav>
          <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-8"><p className="mb-6 rounded border border-emerald-200 bg-emerald-50 p-4 text-sm">이 홈페이지의 제출과 리더보드는 모델 개발을 위한 연습용입니다. 공식 최종 제출은 e-Class LMS에 Notebook, 모델 ZIP, 개발 보고서를 업로드해야 완료됩니다.</p>{children}</main>
        </div>
      </div>
    </div>
  );
}
