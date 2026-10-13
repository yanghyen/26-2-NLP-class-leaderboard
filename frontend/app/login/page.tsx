"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Eye, EyeOff, LogIn, Trophy } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";

import { useAuth } from "../../components/auth-provider";
import { Button, Field, inputClass, MockBadge } from "../../components/ui";

export default function LoginPage() {
  const { user, loading, login } = useAuth();
  const router = useRouter();
  const [loginId, setLoginId] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && user) router.replace("/admin");
  }, [loading, router, user]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(loginId, password);
      router.replace("/admin");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "로그인에 실패했습니다.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="grid min-h-screen bg-white lg:grid-cols-[minmax(320px,0.8fr)_1.2fr]">
      <section className="flex flex-col justify-between bg-zinc-950 px-8 py-10 text-white lg:px-12">
        <div className="flex items-center gap-3"><Trophy className="h-6 w-6 text-emerald-400" /><span className="font-bold">NLP Course Leaderboard</span></div>
        <div className="my-16 max-w-md"><p className="text-sm font-semibold text-emerald-400">2026 자연어처리 프로젝트</p><h1 className="mt-3 text-3xl font-bold leading-tight">제출부터 평가 결과까지 한곳에서 확인하세요.</h1><p className="mt-4 text-sm leading-7 text-zinc-300">안전하게 모델을 제출하고, 공개 점수와 리더보드 변화를 확인할 수 있습니다.</p></div>
        <MockBadge />
      </section>
      <section className="flex items-center justify-center px-6 py-12">
        <form onSubmit={onSubmit} className="w-full max-w-md" noValidate>
          <h2 className="text-2xl font-bold text-zinc-950">관리자 로그인</h2>
          <p className="mt-2 text-sm text-zinc-600">관리자 닉네임과 비밀번호를 입력하세요. 학생은 로그인 없이 제출할 수 있습니다.</p>
          <div className="mt-8 space-y-5">
            <Field label="로그인 아이디"><input className={inputClass} value={loginId} onChange={(e) => setLoginId(e.target.value)} autoComplete="username" required /></Field>
            <Field label="비밀번호"><div className="relative"><input className={`${inputClass} pr-11`} type={showPassword ? "text" : "password"} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required /><button type="button" onClick={() => setShowPassword((value) => !value)} title={showPassword ? "비밀번호 숨기기" : "비밀번호 보기"} className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-2 text-zinc-500 hover:bg-zinc-100">{showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}</button></div></Field>
          </div>
          {error && <p className="mt-4 border border-red-200 bg-red-50 p-3 text-sm text-red-800" role="alert">{error}</p>}
          <Button className="mt-6 w-full" disabled={submitting || !loginId || !password}><LogIn className="h-4 w-4" />{submitting ? "로그인 중" : "로그인"}</Button>
          <Link href="/tasks">공개 태스크로 이동</Link>
        </form>
      </section>
    </main>
  );
}
