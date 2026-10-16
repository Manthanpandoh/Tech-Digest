const categories = [
  "All",
  "AI",
  "Cloud",
  "Cyber",
  "Programming",
  "Google",
  "Microsoft",
  "Apple",
];

function Category({ activeCategory, setActiveCategory }) {
  return (
    <div className="flex flex-wrap items-center justify-center lg:justify-start gap-4 my-8">
      {categories.map((cat) => {
        const isActive = activeCategory === cat;

        return (
          <button
            key={cat}
            onClick={() => setActiveCategory(cat)}
            className={`
              relative
              overflow-hidden
              rounded-full
              px-6
              py-3
              font-medium
              text-sm
              transition-all
              duration-300
              border

              ${
                isActive
                  ? "bg-gradient-to-r from-pink-500 via-purple-500 to-cyan-500 text-white border-transparent shadow-lg shadow-pink-500/30 scale-105"
                  : "bg-[#111827] text-gray-300 border-pink-500/20 hover:border-pink-500 hover:text-white hover:scale-105 hover:shadow-lg hover:shadow-pink-500/20"
              }
            `}
          >
            {cat}
          </button>
        );
      })}
    </div>
  );
}

export default Category;