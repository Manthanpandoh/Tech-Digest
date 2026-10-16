function EmptyState({ message = "No articles found.", suggestion = "Try another keyword or category." }) {
  return (
    <div className="col-span-2 py-20 text-center">
      <div className="text-6xl mb-6">😔</div>
      <h2 className="text-3xl font-bold text-pink-500">{message}</h2>
      <p className="mt-4 text-gray-400">{suggestion}</p>
    </div>
  );
}

export default EmptyState;
