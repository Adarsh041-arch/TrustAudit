import { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import AppV1 from './App.tsx'
import { AppV2 } from './AppV2.tsx'

function Root() {
  const [mode, setMode] = useState<'v1' | 'v2'>(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const modeParam = urlParams.get('mode');
    if (modeParam === 'v2') return 'v2';
    return (localStorage.getItem('app_mode') as 'v1' | 'v2') || 'v1';
  });

  const toggleMode = (newMode: 'v1' | 'v2') => {
    setMode(newMode);
    localStorage.setItem('app_mode', newMode);
    const url = new URL(window.location.href);
    url.searchParams.set('mode', newMode);
    window.history.pushState({}, '', url.toString());
  };

  return (
    <>
      <div className="fixed bottom-6 right-6 z-[9999] bg-slate-900/90 border border-slate-700/80 text-slate-100 px-4 py-2 rounded-full text-xs font-semibold shadow-2xl backdrop-blur-md flex items-center gap-3 transition-all hover:scale-105">
        <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">UI Mode:</span>
        <button
          onClick={() => toggleMode('v1')}
          className={`px-3 py-1 rounded-full cursor-pointer transition-all ${
            mode === 'v1'
              ? 'bg-gradient-to-r from-teal-500 to-emerald-600 text-white font-bold shadow shadow-teal-500/30'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          V1 (Agentic)
        </button>
        <button
          onClick={() => toggleMode('v2')}
          className={`px-3 py-1 rounded-full cursor-pointer transition-all ${
            mode === 'v2'
              ? 'bg-gradient-to-r from-teal-500 to-emerald-600 text-white font-bold shadow shadow-teal-500/30'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          V2 (Temporal)
        </button>
      </div>
      <StrictMode>
        {mode === 'v1' ? <AppV1 /> : <AppV2 />}
      </StrictMode>
    </>
  )
}

createRoot(document.getElementById('root')!).render(<Root />)
