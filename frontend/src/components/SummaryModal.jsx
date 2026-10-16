import { useEffect, useState } from "react";
import API from "../services/api";

function SummaryModal({ open, onClose, article }) {
  const [loading, setLoading] = useState(false);
  const [summary, setSummary] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (open && article) {
      if (article.summary && article.summary.trim().length > 15) {
        setSummary(article.summary);
        setLoading(false);
      } else {
        generateSummary();
      }
    } else {
      setSummary("");
      setError("");
    }
  }, [open, article]);

  const generateSummary = async () => {
    if (!article) return;

    setLoading(true);
    setSummary("");
    setError("");

    try {
      const title = article.clean_title || article.title || "Technology News";

      const content =
        article.content ||
        article.description ||
        article.summary ||
        "";

      const response = await API.post("/summary", {
        title: title,
        content: content,
      });

      console.log("AI Summary Response:", response.data);

      if (response.data.success) {
        setSummary(response.data.summary);
      } else {
        setError("Unable to generate summary.");
      }
    } catch (err) {
      console.error("AI Summary Error:", err);

      if (err.response) {
        console.error("Backend Response:", err.response.data);
      }

      setError("Unable to connect to AI Server.");
    } finally {
      setLoading(false);
    }
  };

  if (!open || !article) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4">

      <div className="w-full max-w-[750px] max-h-[90vh] overflow-y-auto rounded-2xl border border-pink-500/30 bg-[#111827] p-8 shadow-[0_0_40px_rgba(255,46,136,.35)]">

        {/* Header */}
        <div className="flex items-center justify-between">

          <h2 className="bg-gradient-to-r from-pink-500 via-purple-500 to-cyan-400 bg-clip-text text-3xl font-bold text-transparent">
            🤖 AI Summary
          </h2>

          <button
            onClick={onClose}
            className="text-3xl text-gray-400 transition hover:text-white"
          >
            ×
          </button>

        </div>

        <hr className="my-5 border-pink-500/20" />

        {/* Article Title */}
        <h3 className="text-xl font-semibold leading-8 text-white">
          {article.clean_title || article.title}
        </h3>

        {/* AI Summary Box */}
        <div className="mt-6 rounded-xl bg-slate-900 p-6">

          <h4 className="mb-4 text-lg font-bold text-pink-400">
            AI Generated Summary
          </h4>

          {/* Loading */}
          {loading && (
            <div className="flex items-center gap-3 text-cyan-400">

              <div className="h-5 w-5 animate-spin rounded-full border-2 border-cyan-400 border-t-transparent"></div>

              <span>
                Generating AI Summary...
              </span>

            </div>
          )}

          {/* Error */}
          {!loading && error && (
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-red-400">
              {error}
            </div>
          )}

          {/* Summary */}
          {!loading && !error && summary && (
            <div className="whitespace-pre-wrap font-sans leading-8 text-slate-300">
              {summary}
            </div>
          )}

        </div>

        {/* Close Button */}
        <div className="mt-6 flex justify-end">

          <button
            onClick={onClose}
            className="rounded-lg bg-gradient-to-r from-pink-500 to-purple-600 px-6 py-2 font-semibold text-white transition hover:scale-105"
          >
            Close
          </button>

        </div>

      </div>

    </div>
  );
}

export default SummaryModal;