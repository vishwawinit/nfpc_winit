# Frontend Changes Log — NFPC Reports Dashboard UI Overhaul

> All changes are UI/UX, filter system, and layout improvements focused on the Dashboard page and shared components.

---

## Files Changed (Frontend)

| # | File Path | What Changed |
|---|-----------|-------------|
| 1 | `frontend/src/index.css` | Complete design system rewrite |
| 2 | `frontend/src/App.jsx` | Layout wrapper updated |
| 3 | `frontend/src/api.js` | Added ASM filter + cascading params |
| 4 | `frontend/src/components/FilterPanel.jsx` | Full rewrite — fixed dropdowns, added ASM, cascading hierarchy, date layout |
| 5 | `frontend/src/components/KpiCard.jsx` | Premium card redesign |
| 6 | `frontend/src/components/DataTable.jsx` | Enterprise table styling |
| 7 | `frontend/src/components/Sidebar.jsx` | Navigation redesign |
| 8 | `frontend/src/components/Loading.jsx` | Improved loading skeleton |
| 9 | `frontend/src/pages/Dashboard.jsx` | Full dashboard UI overhaul + chart layout changes |

---

## Detailed Changes Per File

---

### 1. `frontend/src/index.css`

**Purpose:** Global design system and CSS foundations.

**Changes:**
- Added CSS custom properties (design tokens) for colors, spacing, shadows, border-radius, typography
- `--color-primary-*` (indigo palette), `--color-surface-*`, `--color-border-*`, `--color-text-*`
- `--shadow-card` / `--shadow-card-hover` layered depth system
- `--radius-sm/md/lg/xl` border radius scale
- `--space-1` through `--space-10` spacing scale (4px base)
- Custom scrollbar styling (6px slim tracks, gray thumbs)
- `.card-enterprise` class with hover shadow elevation
- `.chart-container`, `.chart-header`, `.chart-body` classes for chart cards
- `.kpi-card` class with `translateY(-1px)` hover lift
- Recharts legend/tooltip spacing overrides
- `::selection` styling with indigo tint
- `@keyframes fadeIn` — page entrance animation
- `@keyframes shimmer` — skeleton loading effect
- `@keyframes progressGrow` — progress bar grow animation
- `.animate-fade-in`, `.shimmer`, `.animate-progress` utility classes
- `input[type="date"]` — z-index fix + calendar picker indicator hover styling
- `font-feature-settings: 'cv02', 'cv03', 'cv04', 'cv11'` for Inter font
- `.tabular-nums` font-variant for data alignment

---

### 2. `frontend/src/App.jsx`

**Purpose:** Root layout wrapper with sidebar + main content area.

**Changes:**
- Parent `<div>`: changed `min-h-screen` to `h-screen` (fixed viewport height)
- Added `bg-[#f8f9fb]` explicit surface background
- `<main>`: changed `p-6` to `px-8 py-6` (wider horizontal padding for enterprise monitors)
- `<main>`: changed `overflow-auto max-h-screen` to `overflow-y-auto` (fixes native date picker popup clipping)

---

### 3. `frontend/src/api.js`

**Purpose:** Axios API client for all backend calls.

**Changes:**
- Added `fetchFilters.asms(salesOrg)` — new ASM filter endpoint
- Changed `fetchFilters.routes(salesOrg)` to `fetchFilters.routes(params)` — now accepts object with `sales_org`, `depot`, `supervisor`, `asm` for cascading
- Changed `fetchFilters.users(salesOrg)` to `fetchFilters.users(params)` — now accepts object with `sales_org`, `asm`, `supervisor`, `depot` for cascading
- Changed `fetchFilters.depots(salesOrg)` to `fetchFilters.depots(params)` — now accepts object with `sales_org`, `asm`
- Changed `fetchFilters.supervisors(salesOrg)` to `fetchFilters.supervisors(params)` — now accepts object with `sales_org`, `asm`

---

### 4. `frontend/src/components/FilterPanel.jsx`

**Purpose:** Reusable filter bar used by all dashboard pages.

**Changes (MultiSelect dropdown):**
- Fixed critical bug: dropdown items were not clickable (original `<label>` had no `onClick` handler, no actual `<input>` element) — now uses `<div onClick={() => toggle(o.code)}>`
- Changed dropdown from `position: absolute; z-index: 50` to `position: fixed; zIndex: 9999` — escapes `overflow-auto` clipping on `<main>`
- Dropdown position calculated via `getBoundingClientRect()` from trigger button
- Auto-detects space below — opens above if not enough room
- Minimum dropdown width `240px` so narrow grid columns don't squash it
- Closes on `<main>` scroll to prevent floating detached
- Repositions on `window.resize`
- Added active state on trigger button: `border-indigo-400 ring-2` when open
- Added chevron rotation animation (180deg) when open
- Added "X selected" count banner with "Clear all" button when items are selected
- Added clear button (circle X) on trigger when items selected
- Larger option rows: `py-[7px]` (was `py-[6px]`), `18x18px` checkboxes (was `16x16`)
- Code badges show in `bg-gray-100` pill next to name
- Empty state: "No options available" vs "No matching results"
- Search input: better styling with `bg-gray-50/40` header, placeholder "Type to search..."
- Added `loading` prop — shows "Loading..." and disabled state during cascade fetches
- Search resets when dropdown opens

**Changes (fieldMeta):**
- Added `asm: { label: 'ASM', icon: Shield, multi: true }`
- Reordered fields to hierarchy: `sales_org → asm → depot → supervisor → user_code → route → channel → brand → category`

**Changes (Cascading filter hierarchy):**
- ASMs depend on: `sales_org`
- Supervisors depend on: `sales_org`, `asm`
- Depots depend on: `sales_org`, `asm`
- Users/Salesman depend on: `sales_org`, `asm`, `supervisor`, `depot`
- Routes depend on: `sales_org`, `asm`, `supervisor`, `depot`
- Cascade clearing: changing a parent filter auto-clears all child filters
  - `sales_org` change → clears `asm`, `supervisor`, `user_code`, `depot`, `route`
  - `asm` change → clears `supervisor`, `user_code`, `route`
  - `supervisor` change → clears `user_code`, `route`
  - `depot` change → clears `user_code`, `route`
- Loading states per cascading field (`loadingAsms`, `loadingSupervisors`, `loadingUsers`, `loadingRoutes`, `loadingDepots`)

**Changes (Layout):**
- Date filters now on their own row (separate from other filters)
- Date inputs: `min-w-[180px]`, `max-w-[220px]` — proper width for native date picker
- Other filters on second row with responsive grid: `xl:grid-cols-7` for 7 filters
- Container: `bg-white/70` (removed `backdrop-blur-sm` that was creating stacking context issues)
- Gap: `gap-x-3 gap-y-4` (separate horizontal/vertical gaps)
- Label styling: `text-gray-500` (was `text-gray-400`), `w-3.5 h-3.5` icons (was `w-3 h-3`)

---

### 5. `frontend/src/components/KpiCard.jsx`

**Purpose:** KPI metric cards used across all dashboard pages.

**Changes:**
- Background: changed flat `bg-blue-50` to gradient `bg-gradient-to-br from-blue-50 to-indigo-50/60` (all color variants)
- Added 2px colored accent line at top of each card (`absolute top-0` bar with color-matched `bg-*-500 opacity-40`)
- Icon container: increased from `w-11 h-11` to `w-12 h-12`, added `shadow-sm`
- Icon stroke width: `strokeWidth={1.75}` for balanced density
- Title: `text-[11px]` (was `text-xs`), color changed from `text-blue-400` to `text-blue-500/80` (all variants)
- Value: `text-[22px]` (was `text-2xl`), added `tracking-tight`
- Subtitle: `text-[11px]` with `font-medium` (was `text-xs`)
- Added `.kpi-card` CSS class for hover lift animation (`translateY(-1px)` + shadow expansion)
- Card has `relative overflow-hidden` for accent line containment
- Light variant: icon bg changed from `bg-blue-100` to `bg-blue-50` (softer)
- Added `accent` color to both solid and light palettes

---

### 6. `frontend/src/components/DataTable.jsx`

**Purpose:** Sortable, searchable data table with CSV export.

**Changes:**
- Root container: added `.card-enterprise` class for hover shadow elevation
- Toolbar padding: `px-5 py-3.5` (was `px-4 py-3`)
- Search input: `py-[7px]`, `bg-gray-50/80`, added `hover:border-gray-300`
- Row count badge: `text-[11px] font-semibold` (was `text-xs font-medium`)
- Export button: `text-[13px] font-semibold`, `px-4 py-[7px]`, added `active:bg-indigo-800`, `shadow-sm shadow-indigo-600/10`
- Download icon: `w-3.5 h-3.5 strokeWidth={2}` (was `w-4 h-4`)
- Table font: `text-[13px]` (was `text-sm`)
- Table header: `text-[11px]`, `bg-gray-50/60`, added `hover:text-gray-600`, `duration-150`
- Sort icons: `w-3 h-3` (was `w-3.5 h-3.5`)
- Row striping: `bg-white` / `bg-gray-50/30` (was transparent / `bg-gray-50/50`)
- Row hover: `hover:bg-indigo-50/40` with `duration-100`
- Numeric cells: added `font-medium` for currency/number/percent columns
- Empty state: `text-base font-semibold` title + `text-[13px]` subtitle, `py-16` (was `py-12`)

---

### 7. `frontend/src/components/Sidebar.jsx`

**Purpose:** Left navigation sidebar.

**Changes:**
- Width: `w-[244px]` (was `w-60` / 240px), added `border-r border-slate-700/30`
- Background: added `via-slate-900` to gradient for smoother transition
- Logo: replaced gradient banner with icon + text layout
  - Square `w-8 h-8 rounded-lg` gradient icon with "N" letter
  - `shadow-lg shadow-indigo-500/20` on icon
  - Title: `text-[15px]` (was `text-lg`)
  - Subtitle: `text-[10px] text-slate-400` with `tracking-wide`
  - Separated by `border-b border-slate-700/40` (was gradient background)
- Section labels: `px-2.5 mb-2`, `tracking-[0.08em]` (was `px-2 mb-1.5 tracking-widest`)
- Section spacing: `space-y-5` (was `space-y-4`)
- Nav items: `py-[7px]` (was `py-1.5`)
- Active state: `bg-indigo-500/15` (was `bg-white/10 backdrop-blur`), `border-l-[3px]` (was `border-l-2`), `pl-[7px]`
- Hover state: `hover:bg-white/[0.04]` (was `hover:bg-white/5`)
- Icons: `w-[15px] h-[15px] strokeWidth={1.75}` (was `w-4 h-4`)
- Footer: `py-3.5`, `font-medium`, `border-t border-slate-700/40` (was `border-slate-700/50`)

---

### 8. `frontend/src/components/Loading.jsx`

**Purpose:** Loading state with spinner and skeleton.

**Changes:**
- Added `animate-fade-in` class on container
- Padding: `py-20` (was `py-16`)
- Spinner: `w-9 h-9` (was `w-10 h-10`), border `2px` (was `border-2`), color `border-t-indigo-500` (was `border-t-indigo-600`)
- Outer ring: `border-gray-200/60` (was `border-gray-200`)
- Loading text: added `tracking-wide`
- Skeleton rows: margin `mt-10` (was `mt-8`), max-width `max-w-lg` (was `max-w-md`), padding `px-6` (was `px-4`)
- Skeleton bars: `h-2.5` (was `h-3`), uses `.shimmer` class (gradient animation) instead of `bg-gray-100 animate-pulse`
- Added 4th skeleton row (`w-2/3`)

---

### 9. `frontend/src/pages/Dashboard.jsx`

**Purpose:** Main dashboard page with KPIs, charts, and route data.

**Changes (Layout & Structure):**
- Added `animate-fade-in` on root container
- Page title: `text-[22px] tracking-tight` (was `text-2xl`)
- Subtitle: `text-[13px] text-gray-400 font-medium` (was `text-sm text-gray-500`)
- KPI grid: `xl:grid-cols-4` (was `lg:grid-cols-4`) for better breakpoint
- Daily charts grid gap: `gap-5` (was `gap-4`)
- `showFields` updated: added `'asm'`, reordered to `['date_from', 'date_to', 'sales_org', 'asm', 'depot', 'supervisor', 'user_code', 'route', 'brand']`

**Changes (Chart containers):**
- All chart cards now use `.chart-container` CSS class (hover shadow, rounded corners, border)
- Added `SectionHeader` component — consistent card headers with bottom border divider
- Added `SummaryBadge` component — inline KPI badges in chart headers (e.g., "Total Sales: AED 1,234")
- Charts wrapped in `.chart-header` + `.chart-body` structure

**Changes (Chart styling — all charts):**
- Centralized `COLORS` object: `sales: '#6366f1'`, `collection: '#10b981'`, `target: '#f59e0b'`, `salesLight: '#a5b4fc'`, `pending: '#e5e7eb'`, `visited: '#34d399'`, `grid: '#f3f4f6'`
- Removed vertical grid lines on standard charts (`vertical={false}`)
- Removed horizontal grid lines on horizontal charts (`horizontal={false}`)
- X/Y axis: softer colors (`fill: '#9ca3af'`), removed axis lines (`axisLine={false}`), removed tick lines (`tickLine={false}`)
- Tooltip: updated padding `10px 14px`, `fontSize: 13px`, stronger shadow
- Tooltip cursor: subtle colored fill (e.g., `rgba(99, 102, 241, 0.04)`)
- Legend: `iconType="circle"`, `iconSize={8}`, `fontSize: '12px'`, `color: '#6b7280'`
- Added `barCategoryGap="20%"` for better bar spacing

**Changes (Target vs Achievement KPI card):**
- Added 2px amber accent line at top
- Icon: `w-12 h-12` with `shadow-sm`, `strokeWidth={1.75}`
- Label: `text-[11px] text-amber-500/80`
- Values: `text-[13px]`, `font-bold`, `tabular-nums`
- Progress bar: `h-2` (was `h-2.5`), added `animate-progress` grow animation, `overflow-hidden` on track
- Percentage: `text-[13px] tabular-nums`

**Changes (Calls & Coverage KPI card):**
- Added 2px violet accent line at top
- Icon: `w-12 h-12` with `shadow-sm`, `strokeWidth={1.75}`
- Label: `text-[11px] text-violet-500/80`
- Metrics: `text-[13px]`, `font-bold tabular-nums`, `text-gray-400 font-medium` labels
- Coverage badge: `bg-violet-50 text-violet-700 border border-violet-100/80` (was `bg-violet-100 text-violet-700`)

**Changes (Route Wise Sales vs Target vs Collection chart):**
- Changed from vertical layout (horizontal bars) to **horizontal layout** (vertical bars)
- Removed `layout="vertical"` and `margin={{ left: 120 }}`
- Routes now on X-axis with `-35deg` angle labels, `height={70}` for label space
- `interval={0}` to show every route label
- Horizontal scrollbar: `overflow-x-auto` with `minWidth: routeSales.length * 100px` (min 600px)
- Bar radius changed from `[0, 6, 6, 0]` to `[6, 6, 0, 0]` (top-rounded for vertical bars)
- Chart height: fixed `360px`

**Changes (Route Wise Visits chart):**
- Changed from vertical layout (horizontal bars) to **horizontal layout** (vertical bars)
- Removed `layout="vertical"` and `margin={{ left: 120 }}`
- Routes now on X-axis with `-35deg` angle labels, `height={60}` for label space
- `interval={0}` to show every route label
- Horizontal scrollbar: `overflow-x-auto` with `minWidth: routeVisits.length * 80px` (min 600px)
- Bar radius changed from `[0, 6, 6, 0]` to `[6, 6, 0, 0]` (top-rounded for vertical bars)
- Chart height: fixed `340px`

---

## Files NOT Changed (Frontend)

The following frontend files were **not modified**:

- `frontend/src/main.jsx`
- `frontend/src/App.css`
- `frontend/src/assets/react.svg`
- `frontend/src/pages/SalesPerformance.jsx`
- `frontend/src/pages/TopCustomers.jsx`
- `frontend/src/pages/TopProducts.jsx`
- `frontend/src/pages/MarketSales.jsx`
- `frontend/src/pages/TargetAchievement.jsx`
- `frontend/src/pages/Endorsement.jsx`
- `frontend/src/pages/DailySalesOverview.jsx`
- `frontend/src/pages/MtdWastage.jsx`
- `frontend/src/pages/WeeklySalesReturns.jsx`
- `frontend/src/pages/BrandWiseSales.jsx`
- `frontend/src/pages/MtdSalesOverview.jsx`
- `frontend/src/pages/LogReport.jsx`
- `frontend/src/pages/TimeManagement.jsx`
- `frontend/src/pages/CustomerAttendance.jsx`
- `frontend/src/pages/MtdAttendance.jsx`
- `frontend/src/pages/JourneyPlanCompliance.jsx`
- `frontend/src/pages/OutstandingCollection.jsx`
- `frontend/src/pages/EotStatus.jsx`
- `frontend/src/pages/ProductivityCoverage.jsx`
- `frontend/src/pages/SalesmanJourney.jsx`
- `frontend/src/pages/RevenueDispersion.jsx`
- `frontend/src/pages/MonthlySalesStock.jsx`

---

## Backend Files Also Changed (API)

These backend files were modified to support the new filter system:

| # | File Path | What Changed |
|---|-----------|-------------|
| 1 | `api/routes/filters.py` | Added ASM endpoint, cascading params on supervisors/users/depots/routes |
| 2 | `api/routes/dashboard.py` | Added `asm` parameter, fixed brand/channel filter crash on tables without those columns |
| 3 | `api/models.py` | Added ASM to `resolve_user_codes()` hierarchy resolution |

---
