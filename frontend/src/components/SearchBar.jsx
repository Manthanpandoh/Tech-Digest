function SearchBar({ search, setSearch }) {
  return (
    <input
      type="text"
      placeholder="Search AI News..."
      value={search}
      onChange={(e) => setSearch(e.target.value)}
      className="w-full rounded-xl border border-pink-500/20 bg-[#111827] p-4 text-white outline-none transition-all focus:border-pink-500 focus:ring-2 focus:ring-pink-500/30"
    />
  );
}

export default SearchBar;