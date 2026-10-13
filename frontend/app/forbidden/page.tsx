import Link from "next/link";
import { ShieldX } from "lucide-react";

export default function ForbiddenPage() {
  return <main className="flex min-h-screen items-center justify-center bg-zinc-50 px-6"><div className="max-w-md text-center"><ShieldX className="mx-auto h-10 w-10 text-red-700" /><h1 className="mt-4 text-2xl font-bold">접근 권한이 없습니다</h1><p className="mt-2 text-sm leading-6 text-zinc-600">현재 계정으로 이 페이지를 열 수 없습니다.</p><Link href="/" className="mt-6 inline-block rounded-md bg-zinc-950 px-4 py-2 text-sm font-semibold text-white">홈으로 이동</Link></div></main>;
}
