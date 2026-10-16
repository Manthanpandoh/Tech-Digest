import { useState } from "react";
import {
  FaWhatsapp,
  FaBookmark,
  FaExternalLinkAlt,
  FaRobot,
} from "react-icons/fa";

import SummaryModal from "./SummaryModal";

function NewsCard({ item }) {
  const [open, setOpen] = useState(false);

  const shareWhatsapp = () => {
    const message = `🚀 TechPulse AI

${item.clean_title || item.title}

📂 Category: ${item.category}

⭐ AI Score: ${item.score}

Read Full Article:
${item.link}

Shared via TechPulse AI`;

    window.open(
      `https://wa.me/?text=${encodeURIComponent(message)}`,
      "_blank"
    );
  };

  return (
    <>
      <div className="group overflow-hidden rounded-2xl border border-pink-500/20 bg-[#111827] transition-all duration-300 hover:-translate-y-2 hover:border-pink-500 hover:shadow-[0_0_35px_rgba(255,46,136,.35)]">

        <img
          src={
            item.image ||
            "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=1200"
          }
          alt={item.clean_title || item.title}
          className="h-52 w-full object-cover"
        />

        <div className="p-6">

          <span className="rounded-full bg-gradient-to-r from-pink-500 to-purple-600 px-3 py-1 text-xs font-semibold text-white">
            {item.category}
          </span>

          <h2 className="mt-4 line-clamp-2 text-2xl font-bold text-white">
            {item.clean_title || item.title}
          </h2>

          <p className="mt-2 text-slate-400">
            📰 {item.source}
          </p>

          <div className="mt-4 flex items-center justify-between">

            <div className="rounded-lg bg-pink-500/10 px-4 py-2 text-pink-400">
              ⭐ AI Score : {item.score}
            </div>

            <button
              onClick={() => setOpen(true)}
              className="rounded-lg bg-gradient-to-r from-pink-500 to-purple-600 px-4 py-2 text-white transition hover:scale-105"
            >
              <FaRobot className="mr-2 inline" />
              AI Summary
            </button>

          </div>

          <div className="mt-6 flex gap-3">

            <a
              href={item.link}
              target="_blank"
              rel="noreferrer"
              className="flex-1 rounded-lg bg-cyan-500 px-4 py-3 text-center font-semibold text-black transition hover:bg-cyan-400"
            >
              <FaExternalLinkAlt className="mr-2 inline" />
              Read
            </a>

            <button
              onClick={shareWhatsapp}
              className="rounded-lg bg-green-500 p-3 text-white transition hover:bg-green-600"
            >
              <FaWhatsapp />
            </button>

            <button className="rounded-lg bg-pink-500 p-3 text-white transition hover:bg-pink-600">
              <FaBookmark />
            </button>

          </div>

        </div>
      </div>

      <SummaryModal
        open={open}
        onClose={() => setOpen(false)}
        article={item}
      />
    </>
  );
}

export default NewsCard;