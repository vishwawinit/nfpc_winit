import { createContext, useContext, useState } from 'react';
import axios from 'axios';

const AuthContext = createContext(null);

const STORAGE_KEY = 'nfpc_user';

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY)); } catch { return null; }
  });
  const [loading, setLoading] = useState(false);
  const [error, setError]   = useState(null);

  const login = async (userCode) => {
    setLoading(true);
    setError(null);
    try {
      const res  = await axios.get(`/api/auth/login?userCode=${encodeURIComponent(userCode.trim())}`);
      const data = res.data;
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
      setUser(data);
      return data;
    } catch (err) {
      const msg = err.response?.data?.detail || 'Login failed. Please check your user code.';
      setError(msg);
      throw new Error(msg);
    } finally {
      setLoading(false);
    }
  };

  const logout = () => {
    localStorage.removeItem(STORAGE_KEY);
    setUser(null);
  };

  const canAccess = (path) => {
    if (!user) return false;
    if (!user.allowed_pages) return true; // null = all pages
    return user.allowed_pages.includes(path);
  };

  return (
    <AuthContext.Provider value={{ user, login, logout, loading, error, canAccess }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
