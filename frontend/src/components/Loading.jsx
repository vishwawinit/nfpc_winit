export default function Loading() {
  return (
    <div className="flex flex-col items-center justify-center py-20 animate-fade-in">
      {/* Spinner */}
      <div className="relative w-9 h-9">
        <div className="absolute inset-0 rounded-full border-[2px] border-gray-200/60"></div>
        <div className="absolute inset-0 rounded-full border-[2px] border-transparent border-t-indigo-500 animate-spin"></div>
      </div>
      <span className="mt-4 text-sm font-medium text-gray-400 tracking-wide">Loading data...</span>

      {/* Skeleton pulse rows */}
      <div className="mt-10 w-full max-w-lg space-y-3 px-6">
        <div className="h-2.5 shimmer rounded-full w-full"></div>
        <div className="h-2.5 shimmer rounded-full w-4/5"></div>
        <div className="h-2.5 shimmer rounded-full w-3/5"></div>
        <div className="h-2.5 shimmer rounded-full w-2/3"></div>
      </div>
    </div>
  );
}
