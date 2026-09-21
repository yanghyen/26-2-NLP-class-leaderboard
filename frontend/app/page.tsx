import { Trophy, UploadCloud, Users } from "lucide-react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function getHealth() {
  try {
    const res = await fetch(`${API_BASE_URL}/health`, { cache: "no-store" });
    return res.ok ? "API online" : "API unavailable";
  } catch {
    return "API unavailable";
  }
}

export default async function Home() {
  const health = await getHealth();

  return (
    <main className="min-h-screen">
      <section className="border-b border-neutral-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <Trophy className="h-6 w-6 text-emerald-600" />
            <span className="text-lg font-semibold">NLP Course Leaderboard</span>
          </div>
          <span className="rounded-full bg-neutral-100 px-3 py-1 text-sm text-neutral-700">{health}</span>
        </div>
      </section>

      <section className="mx-auto grid max-w-6xl gap-6 px-6 py-10 md:grid-cols-[1.2fr_0.8fr]">
        <div>
          <h1 className="text-3xl font-bold tracking-normal text-neutral-950 md:text-4xl">
            제출, 평가 queue, 리더보드를 분리한 수업용 플랫폼
          </h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-neutral-700">
            Phase 2에서는 계정, 수강생 명단, 태스크, 제출 레코드 API가 먼저 완성되었습니다.
            제출 파일 검증과 실제 평가 worker는 다음 단계에서 같은 데이터 모델 위에 붙습니다.
          </p>
        </div>

        <div className="grid gap-3">
          <div className="rounded-lg border border-neutral-200 bg-white p-5">
            <Users className="h-5 w-5 text-blue-600" />
            <h2 className="mt-3 text-base font-semibold">Roster gated signup</h2>
            <p className="mt-2 text-sm leading-6 text-neutral-600">
              학번과 본명은 관리자 명단과 일치해야 하며, 공개 화면은 이모지와 닉네임만 사용합니다.
            </p>
          </div>
          <div className="rounded-lg border border-neutral-200 bg-white p-5">
            <UploadCloud className="h-5 w-5 text-emerald-600" />
            <h2 className="mt-3 text-base font-semibold">Submission lifecycle</h2>
            <p className="mt-2 text-sm leading-6 text-neutral-600">
              임시저장과 평가 제출을 구분하고, 평가 제출은 queue job으로 분리될 수 있게 저장됩니다.
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}

