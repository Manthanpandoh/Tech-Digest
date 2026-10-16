function TrendingCard({ title }) {
  return (
    <div className="bg-slate-800 p-4 rounded-xl border border-slate-700 hover:border-cyan-500 transition">
      <h3 className="font-semibold">{title}</h3>
    </div>
  );
}

export default TrendingCard;