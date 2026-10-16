function SkeletonCard() {
  return (
    <div className="animate-pulse overflow-hidden rounded-2xl bg-[#111827] border border-pink-500/10">

      <div className="h-52 bg-slate-700"></div>

      <div className="p-6">

        <div className="h-4 w-24 rounded bg-slate-700"></div>

        <div className="mt-5 h-8 rounded bg-slate-700"></div>

        <div className="mt-2 h-8 w-4/5 rounded bg-slate-700"></div>

        <div className="mt-6 h-4 w-1/2 rounded bg-slate-700"></div>

        <div className="mt-8 h-10 rounded bg-slate-700"></div>

        <div className="mt-6 flex gap-3">

          <div className="h-12 flex-1 rounded bg-slate-700"></div>

          <div className="h-12 w-12 rounded bg-slate-700"></div>

          <div className="h-12 w-12 rounded bg-slate-700"></div>

        </div>

      </div>

    </div>
  );
}

export default SkeletonCard;