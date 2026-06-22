import React from 'react';
import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom';
import HomePage from './pages/HomePage';
import IncidentPage from './pages/IncidentPage';
import HistoryPage from './pages/HistoryPage';

const AppLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const location = useLocation();
  const path = location.pathname;

  return (
    <div className="min-h-screen flex flex-col">
      {/* Navbar */}
      <header className="sticky top-0 z-50 glass-card rounded-none border-t-0 border-l-0 border-r-0 border-b border-slate-700/50 bg-[#080d1a]/80">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link to="/" className="flex items-center gap-2 group">
              <div className="w-8 h-8 rounded-lg bg-blue-500 flex items-center justify-center font-bold text-white shadow-lg shadow-blue-500/20 group-hover:scale-105 transition-transform">
                AI
              </div>
              <span className="font-bold text-lg text-white hidden sm:block tracking-tight">
                APIE <span className="text-slate-500 font-normal">| Incident Engineer</span>
              </span>
            </Link>
          </div>

          <nav className="flex flex-1 justify-center max-w-md mx-8">
            <div className="flex space-x-1 p-1 bg-slate-800/40 rounded-xl border border-slate-700/50">
              <Link
                to="/"
                className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all duration-200
                  ${path === '/' ? 'bg-slate-700/50 text-white shadow' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'}`}
              >
                Dashboard
              </Link>
              <Link
                to="/history"
                className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all duration-200
                  ${path.startsWith('/history') ? 'bg-slate-700/50 text-white shadow' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'}`}
              >
                History
              </Link>
            </div>
          </nav>

          <div className="flex items-center gap-3">
            <div className="hidden md:flex items-center gap-2 text-xs text-slate-400 bg-slate-800/30 px-3 py-1.5 rounded-full border border-slate-700/30">
              <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
              Agents Online
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {children}
      </main>

      {/* Footer */}
      <footer className="py-6 text-center text-xs text-slate-500 border-t border-slate-800/50 mt-auto">
        Autonomous Production Incident Engineer (APIE) • AI-Driven Reliability System
      </footer>
    </div>
  );
};

const App: React.FC = () => {
  return (
    <BrowserRouter>
      <AppLayout>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/incidents/:id" element={<IncidentPage />} />
          <Route path="/history" element={<HistoryPage />} />
        </Routes>
      </AppLayout>
    </BrowserRouter>
  );
};

export default App;
