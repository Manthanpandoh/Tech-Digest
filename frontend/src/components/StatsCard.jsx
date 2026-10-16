function StatsCard({ title, value, color }) {
  return (

  <div className="
bg-[#111827]
rounded-2xl
border
border-pink-500/20
p-6
hover:border-pink-500
hover:shadow-[0_0_25px_rgba(255,46,136,0.35)]
transition-all
duration-300">

      <h2 className="text-gray-400">
        {title}
      </h2>

      <h1 className={`text-4xl font-bold ${color}`}>
        {value}
      </h1>

    </div>

  );
}

export default StatsCard;