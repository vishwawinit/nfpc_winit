import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { User, LogIn, AlertCircle, Loader2 } from 'lucide-react';

export default function LoginPage() {
  const { login, loading, error, user } = useAuth();
  const [userCode, setUserCode] = useState('');
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  // If already logged in, redirect
  useEffect(() => {
    if (user) navigate('/', { replace: true });
  }, [user, navigate]);

  // Auto-login from URL param ?userCode=XXX
  useEffect(() => {
    const code = searchParams.get('userCode');
    if (code) {
      login(code).then(() => navigate('/', { replace: true })).catch(() => {});
    }
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!userCode.trim()) return;
    try {
      await login(userCode);
      navigate('/', { replace: true });
    } catch {}
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-indigo-950 flex items-center justify-center p-4">
      {/* Background decoration */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-96 h-96 bg-indigo-500/10 rounded-full blur-3xl" />
        <div className="absolute -bottom-40 -left-40 w-96 h-96 bg-purple-500/10 rounded-full blur-3xl" />
      </div>

      <div className="relative w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-br from-indigo-500 to-indigo-600 shadow-2xl shadow-indigo-500/30 mb-4">
            <span className="text-2xl font-bold text-white">N</span>
          </div>
          <h1 className="text-2xl font-bold text-white tracking-tight">NFPC Reports</h1>
          <p className="text-slate-400 text-sm mt-1 font-medium">Enterprise Sales Dashboard</p>
        </div>

        {/* Card */}
        <div className="bg-white/[0.06] backdrop-blur-xl border border-white/10 rounded-2xl p-8 shadow-2xl">
          <h2 className="text-[15px] font-semibold text-white mb-1">Sign in</h2>
          <p className="text-slate-400 text-[13px] mb-6">Enter your user code to continue</p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-[12px] font-semibold text-slate-300 uppercase tracking-wider mb-2">
                User Code
              </label>
              <div className="relative">
                <User className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type="text"
                  value={userCode}
                  onChange={e => setUserCode(e.target.value)}
                  placeholder="e.g. 177894"
                  autoFocus
                  autoComplete="off"
                  className="w-full pl-10 pr-4 py-3 bg-white/[0.07] border border-white/10 rounded-xl text-white placeholder-slate-500 text-[14px] focus:outline-none focus:ring-2 focus:ring-indigo-500/60 focus:border-indigo-500/40 transition-all"
                />
              </div>
            </div>

            {error && (
              <div className="flex items-center gap-2.5 px-3.5 py-3 bg-rose-500/10 border border-rose-500/20 rounded-xl">
                <AlertCircle className="w-4 h-4 text-rose-400 flex-shrink-0" />
                <span className="text-rose-300 text-[13px] font-medium">{error}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={loading || !userCode.trim()}
              className="w-full flex items-center justify-center gap-2 py-3 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold text-[14px] rounded-xl transition-all shadow-lg shadow-indigo-500/20"
            >
              {loading ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> Signing in...</>
              ) : (
                <><LogIn className="w-4 h-4" /> Sign In</>
              )}
            </button>
          </form>
        </div>

        <p className="text-center text-slate-600 text-[11px] mt-6">
          NFPC UAE &middot; Confidential Reporting System
        </p>
      </div>
    </div>
  );
}
