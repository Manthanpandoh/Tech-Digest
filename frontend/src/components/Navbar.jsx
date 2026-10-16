function Navbar({ onRefresh }) {
  return (
    <nav className="sticky top-0 z-50 border-b border-pink-500/20 bg-[#050816]/90 backdrop-blur-xl">
      <div className="max-w-7xl mx-auto flex items-center justify-between px-6 py-4">
        <h1 className="text-3xl font-bold text-cyan-400">🚀 TechPulse AI</h1>

        <div className="flex items-center gap-8 text-gray-300">
          <a href="#" className="hover:text-cyan-400 transition">Home</a>
          <a href="#" className="hover:text-cyan-400 transition">Trending</a>
          <a href="#" className="hover:text-cyan-400 transition">Analytics</a>
          {onRefresh && (
            <button
              onClick={onRefresh}
              className="rounded-lg bg-gradient-to-r from-pink-500 to-purple-600 px-4 py-2 text-sm text-white transition hover:scale-105"
            >
              ↻ Refresh
            </button>
          )}
        </div>
      </div>
    </nav>
  );
}

export default Navbar;
