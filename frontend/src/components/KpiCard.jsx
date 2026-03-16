const solidColors = {
  blue:   { bg: 'bg-gradient-to-br from-blue-50 to-indigo-50/60', border: 'border-blue-100/80', title: 'text-blue-500/80', value: 'text-blue-700', icon: 'bg-blue-100 text-blue-600', accent: 'bg-blue-500' },
  green:  { bg: 'bg-gradient-to-br from-emerald-50 to-teal-50/60', border: 'border-emerald-100/80', title: 'text-emerald-500/80', value: 'text-emerald-700', icon: 'bg-emerald-100 text-emerald-600', accent: 'bg-emerald-500' },
  red:    { bg: 'bg-gradient-to-br from-rose-50 to-red-50/60', border: 'border-rose-100/80', title: 'text-rose-500/80', value: 'text-rose-700', icon: 'bg-rose-100 text-rose-600', accent: 'bg-rose-500' },
  yellow: { bg: 'bg-gradient-to-br from-amber-50 to-yellow-50/60', border: 'border-amber-100/80', title: 'text-amber-500/80', value: 'text-amber-700', icon: 'bg-amber-100 text-amber-600', accent: 'bg-amber-500' },
  purple: { bg: 'bg-gradient-to-br from-violet-50 to-purple-50/60', border: 'border-violet-100/80', title: 'text-violet-500/80', value: 'text-violet-700', icon: 'bg-violet-100 text-violet-600', accent: 'bg-violet-500' },
  indigo: { bg: 'bg-gradient-to-br from-indigo-50 to-blue-50/60', border: 'border-indigo-100/80', title: 'text-indigo-500/80', value: 'text-indigo-700', icon: 'bg-indigo-100 text-indigo-600', accent: 'bg-indigo-500' },
  teal:   { bg: 'bg-gradient-to-br from-teal-50 to-emerald-50/60', border: 'border-teal-100/80', title: 'text-teal-500/80', value: 'text-teal-700', icon: 'bg-teal-100 text-teal-600', accent: 'bg-teal-500' },
};

const lightColors = {
  blue:   { text: 'text-blue-700',   icon: 'bg-blue-50 text-blue-600', accent: 'bg-blue-500' },
  green:  { text: 'text-emerald-700', icon: 'bg-emerald-50 text-emerald-600', accent: 'bg-emerald-500' },
  red:    { text: 'text-rose-700',   icon: 'bg-rose-50 text-rose-600', accent: 'bg-rose-500' },
  yellow: { text: 'text-amber-700', icon: 'bg-amber-50 text-amber-600', accent: 'bg-amber-500' },
  purple: { text: 'text-violet-700', icon: 'bg-violet-50 text-violet-600', accent: 'bg-violet-500' },
  indigo: { text: 'text-indigo-700', icon: 'bg-indigo-50 text-indigo-600', accent: 'bg-indigo-500' },
  teal:   { text: 'text-teal-700', icon: 'bg-teal-50 text-teal-600', accent: 'bg-teal-500' },
};

export default function KpiCard({ title, value, subtitle, color = 'blue', icon: Icon, variant = 'solid' }) {
  const isSolid = variant === 'solid';
  const palette = isSolid
    ? (solidColors[color] || solidColors.blue)
    : (lightColors[color] || lightColors.blue);

  const bgClass = isSolid ? `${palette.bg} border ${palette.border}` : 'bg-white border border-gray-100/80';
  const titleClass = isSolid ? `${palette.title}` : 'text-gray-500';
  const valueClass = isSolid ? palette.value : palette.text;

  return (
    <div className={`kpi-card ${bgClass} rounded-2xl shadow-sm p-5 relative overflow-hidden`}>
      {/* Subtle top accent line */}
      <div className={`absolute top-0 left-0 right-0 h-[2px] ${palette.accent} opacity-40 rounded-t-2xl`} />

      <div className="flex items-center gap-4">
        {Icon && (
          <div className={`flex-shrink-0 w-12 h-12 rounded-xl flex items-center justify-center ${palette.icon} shadow-sm`}>
            <Icon className="w-5 h-5" strokeWidth={1.75} />
          </div>
        )}
        <div className="min-w-0 flex-1">
          <div className={`text-[11px] font-semibold uppercase tracking-wider ${titleClass}`}>{title}</div>
          <div className={`text-[22px] font-bold mt-0.5 tracking-tight ${valueClass}`}>{value}</div>
          {subtitle && <div className="text-[11px] text-gray-400 mt-0.5 truncate font-medium">{subtitle}</div>}
        </div>
      </div>
    </div>
  );
}
