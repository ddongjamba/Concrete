export default function LandingPage() {
  return (
    <main className="min-h-screen bg-gray-950 text-white flex flex-col items-center justify-center gap-8 p-8">
      <div className="text-center">
        <h1 className="text-4xl font-bold mb-4">Facade Inspect</h1>
        <p className="text-gray-400 text-lg max-w-xl">
          드론 영상 한 번 업로드로 외벽 균열을 AI가 자동 분석하고,
          시간이 지남에 따라 균열이 얼마나 심해졌는지 추적합니다.
        </p>
      </div>

      <div className="flex gap-4">
        <a
          href="/login"
          className="px-6 py-3 bg-blue-600 rounded-lg hover:bg-blue-700 font-medium"
        >
          로그인
        </a>
        <a
          href="/register"
          className="px-6 py-3 border border-gray-600 rounded-lg hover:border-gray-400 font-medium"
        >
          무료 체험 시작
        </a>
      </div>

      <div className="grid grid-cols-3 gap-6 mt-8 max-w-3xl w-full">
        {[
          { icon: "🚁", title: "원클릭 분석", desc: "드론 영상 업로드 후 버튼 하나로 균열 탐지" },
          { icon: "📏", title: "정밀 정량화", desc: "균열 폭(mm), 길이(mm), 면적(cm²) 자동 측정" },
          { icon: "📈", title: "시계열 추적", desc: "1년 후 동일 균열이 얼마나 악화됐는지 확인" },
        ].map((f) => (
          <div key={f.title} className="bg-gray-900 rounded-xl p-5 border border-gray-800">
            <div className="text-3xl mb-3">{f.icon}</div>
            <h3 className="font-semibold mb-1">{f.title}</h3>
            <p className="text-gray-400 text-sm">{f.desc}</p>
          </div>
        ))}
      </div>

      {/* Health check indicator */}
      <ApiStatus />
    </main>
  );
}

async function ApiStatus() {
  try {
    const res = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL || "http://backend:8000"}/health`,
      { cache: "no-store" }
    );
    const data = await res.json();
    return (
      <p className="text-xs text-green-400">
        API {data.status} — v{data.version}
      </p>
    );
  } catch {
    return <p className="text-xs text-gray-600">API 연결 확인 중...</p>;
  }
}
