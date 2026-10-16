import { useCallback, useEffect, useMemo, useState } from "react";
import API from "../services/api";

import Navbar from "../components/Navbar";
import Header from "../components/Header";
import SearchBar from "../components/SearchBar";
import Category from "../components/Category";
import StatsCard from "../components/StatsCard";
import Sidebar from "../components/sidebar";
import Footer from "../components/Footer";
import NewsCard from "../components/NewsCard";
import SkeletonCard from "../components/SkeletonCard";
import EmptyState from "../components/EmptyState";

const PAGE_SIZE = 20;

function Home() {
  const [news, setNews] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);

  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [activeCategory, setActiveCategory] = useState("All");

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Debounce search input
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 400);
    return () => clearTimeout(t);
  }, [search]);

  // Reset to page 1 when filter/search changes
  useEffect(() => {
    setPage(1);
  }, [debouncedSearch, activeCategory]);

  // Fetch from the paginated backend endpoint
  const fetchNews = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const params = new URLSearchParams({
        page: page,
        page_size: PAGE_SIZE,
        sort_by: "score",
      });
      if (debouncedSearch) params.set("search", debouncedSearch);
      if (activeCategory !== "All") params.set("category", activeCategory);

      const { data } = await API.get(`/news?${params}`);
      setNews(data.data || []);
      setTotal(data.total || 0);
      setPage(data.page || 1);
      setPages(data.pages || 1);
    } catch (err) {
      if (import.meta.env.DEV) console.error(err);
      setError(
        err.response
          ? "Backend returned an error. Please try again."
          : "Unable to connect to the news server. Is the backend running?"
      );
      setNews([]);
    } finally {
      setLoading(false);
    }
  }, [page, debouncedSearch, activeCategory]);

  useEffect(() => {
    fetchNews();
  }, [fetchNews]);

  // Quick category stats from current page (approximate, backend has full count)
  const aiCount = useMemo(
    () => news.filter((i) => (i.category || "").toLowerCase().includes("artificial intelligence") || (i.category || "").toLowerCase() === "ai").length,
    [news]
  );
  const cloudCount = useMemo(
    () => news.filter((i) => (i.category || "").toLowerCase().includes("cloud")).length,
    [news]
  );
  const cyberCount = useMemo(
    () => news.filter((i) => (i.category || "").toLowerCase().includes("cyber")).length,
    [news]
  );

  return (
    <div className="min-h-screen bg-[#050816] text-white">
      <Navbar onRefresh={fetchNews} />

      <div className="max-w-7xl mx-auto px-6">
        <Header />

        <SearchBar search={search} setSearch={setSearch} />

        {/* Result counter */}
        <div className="mt-6 mb-4 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h2 className="text-3xl font-bold">
              {total.toLocaleString()}
              <span className="ml-3 text-cyan-400">Articles Found</span>
            </h2>
            <p className="mt-2 text-gray-400">
              Current Category:{" "}
              <span className="ml-1 font-semibold text-pink-500">{activeCategory}</span>
            </p>
          </div>

          <button
            onClick={fetchNews}
            className="self-start lg:self-auto rounded-lg border border-pink-500/30 bg-pink-500/10 px-5 py-2 text-pink-400 transition hover:bg-pink-500/20 hover:border-pink-500"
          >
            ↻ Refresh
          </button>
        </div>

        <Category activeCategory={activeCategory} setActiveCategory={setActiveCategory} />

        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5 my-8">
          <StatsCard title="Total Articles" value={total.toLocaleString()} color="text-pink-500" />
          <StatsCard title="AI News" value={aiCount} color="text-cyan-400" />
          <StatsCard title="Cloud" value={cloudCount} color="text-purple-400" />
          <StatsCard title="Cyber" value={cyberCount} color="text-green-400" />
        </div>

        {/* Error banner */}
        {error && (
          <div className="mb-6 rounded-xl bg-red-500/10 border border-red-500 p-5 text-red-400">
            ⚠️ {error}
          </div>
        )}

        {/* Main layout */}
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
          {/* News grid */}
          <div className="lg:col-span-3">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
              {loading ? (
                Array.from({ length: 6 }).map((_, i) => <SkeletonCard key={i} />)
              ) : news.length === 0 ? (
                <EmptyState
                  message="No Articles Found"
                  suggestion="Try a different keyword or select another category."
                />
              ) : (
                news.map((item, i) => <NewsCard key={item.link || i} item={item} />)
              )}
            </div>

            {/* Pagination */}
            {!loading && pages > 1 && (
              <div className="mt-10 flex items-center justify-center gap-4">
                <button
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="rounded-lg border border-pink-500/30 bg-[#111827] px-5 py-2 text-pink-400 disabled:opacity-30 transition hover:border-pink-500"
                >
                  ← Previous
                </button>
                <span className="text-gray-400">
                  Page {page} of {pages}
                </span>
                <button
                  disabled={page >= pages}
                  onClick={() => setPage((p) => Math.min(pages, p + 1))}
                  className="rounded-lg border border-pink-500/30 bg-[#111827] px-5 py-2 text-pink-400 disabled:opacity-30 transition hover:border-pink-500"
                >
                  Next →
                </button>
              </div>
            )}
          </div>

          {/* Sidebar */}
          <Sidebar />
        </div>
      </div>

      <Footer />
    </div>
  );
}

export default Home;
