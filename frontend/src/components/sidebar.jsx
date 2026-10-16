import { useEffect, useState } from "react";
import API from "../services/api";

function Sidebar() {
  const [trending, setTrending] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    API.get("/news/trending?limit=6")
      .then(({ data }) => {
        setTrending(data.data || []);
      })
      .catch(() => {
        // Fallback to topic labels if API is unavailable
        setTrending([]);
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="bg-[#111827] border border-pink-500/20 rounded-2xl p-6">
      <h2 className="text-2xl font-bold mb-5">🔥 Trending</h2>

      {loading ? (
        <ul className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <li key={i} className="h-4 rounded bg-slate-700 animate-pulse" />
          ))}
        </ul>
      ) : trending.length > 0 ? (
        <ul className="space-y-4">
          {trending.map((item, i) => (
            <li key={i}>
              <a
                href={item.link}
                target="_blank"
                rel="noreferrer"
                className="block text-sm text-gray-300 hover:text-cyan-400 transition line-clamp-2 leading-relaxed"
              >
                <span className="text-pink-500 font-bold mr-2">#{i + 1}</span>
                {item.clean_title || item.title}
              </a>
            </li>
          ))}
        </ul>
      ) : (
        <ul className="space-y-3 text-gray-400">
          {["OpenAI", "Gemini", "Nvidia", "Google", "Microsoft", "AWS"].map((t) => (
            <li key={t} className="hover:text-cyan-400 transition cursor-default">
              {t}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default Sidebar;
