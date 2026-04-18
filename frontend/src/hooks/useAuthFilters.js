import { useAuth } from '../context/AuthContext';

/**
 * Returns default filters merged with the current user's locked filters.
 * Use this as the initial value for a page's filter state so locked
 * filters are present from the very first API call.
 *
 * Usage:
 *   const initFilters = useAuthFilters({ date_from: '...', date_to: '...' });
 *   const [filters, setFilters] = useState(initFilters);
 */
export function useAuthFilters(defaults = {}) {
  const { user } = useAuth() || {};
  const locked = user?.locked_filters || {};
  return { ...defaults, ...locked };
}
