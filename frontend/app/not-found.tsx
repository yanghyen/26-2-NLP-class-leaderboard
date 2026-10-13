import Link from "next/link";

export default function NotFound() {
  return <main className="flex min-h-screen items-center justify-center bg-zinc-50 px-6 text-center"><div><p className="text-sm font-bold text-emerald-700">404</p><h1 className="mt-2 text-2xl font-bold">페이지를 찾을 수 없습니다</h1><Link href="/" className="mt-6 inline-block rounded-md bg-zinc-950 px-4 py-2 text-sm font-semibold text-white">홈으로 이동</Link></div></main>;
}
