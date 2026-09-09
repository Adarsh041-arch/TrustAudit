import { Shield, Sparkles, Moon, Sun, ShieldCheck, Activity, Cpu } from 'lucide-react'

interface HeaderV2Props {
  dark: boolean
  onToggleDark: () => void
  onLoadDemoData?: () => void
  hasData?: boolean
  totalDocs?: number
  findingsCount?: number
  chainValid?: boolean
}

export function HeaderV2({
  dark,
  onToggleDark,
  onLoadDemoData,
  hasData = false,
  totalDocs = 0,
  findingsCount = 0,
  chainValid = true,
}: HeaderV2Props) {
  return (
    <header className="sticky top-0 z-40 w-full border-b border-border/80 bg-surface-2/80 backdrop-blur-xl transition-colors duration-200">
      <div className="max-w-[1440px] mx-auto px-4 md:px-6 py-3.5 flex items-center justify-between gap-4">
        {/* Brand identity */}
        <div className="flex items-center gap-3">
          <div className="relative flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-teal-500 to-emerald-700 text-white shadow-lg shadow-teal-500/20 border border-teal-400/30">
            <Shield className="w-5 h-5 text-white" />
            <div className="absolute -bottom-1 -right-1 w-3.5 h-3.5 bg-emerald-500 rounded-full border-2 border-surface-2 animate-pulse" />
          </div>

          <div>
            <div className="flex items-center gap-2">
              <span className="text-[19px] font-bold tracking-tight text-ink font-sans">
                Trust<span className="text-teal-600 dark:text-teal-400">Audit</span>
              </span>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-gradient-to-r from-teal-500/15 to-emerald-500/15 text-teal-600 dark:text-teal-400 border border-teal-500/30 flex items-center gap-1">
                <Cpu className="w-2.5 h-2.5" />
                V2 Engine
              </span>
            </div>
            <p className="text-[11px] text-muted flex items-center gap-1.5">
              <span>Autonomous Forensic AI</span>
              <span className="text-border-bright">•</span>
              <span className="text-emerald-600 dark:text-emerald-400 font-medium">Temporal Workflow</span>
            </p>
          </div>
        </div>

        {/* Center Live Badges */}
        <div className="hidden lg:flex items-center gap-2.5">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-surface-1 border border-border text-[12px]">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
            <span className="text-muted">Status:</span>
            <span className="font-medium text-ink">v2.0 Core Active</span>
          </div>

          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface-1 border border-border text-[12px]">
            <ShieldCheck className={`w-3.5 h-3.5 ${chainValid ? 'text-teal-600 dark:text-teal-400' : 'text-coral-600'}`} />
            <span className="text-muted">Chain:</span>
            <span className="font-mono font-medium text-ink">
              {chainValid ? 'SHA-256 Verified' : 'Integrity Check Failed'}
            </span>
          </div>

          {hasData && (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-teal-500/10 border border-teal-500/30 text-[12px] text-teal-700 dark:text-teal-300">
              <Activity className="w-3.5 h-3.5" />
              <span>{totalDocs} Dossier(s)</span>
              <span className="opacity-50">|</span>
              <span>{findingsCount} Findings</span>
            </div>
          )}
        </div>

        {/* Right action controls */}
        <div className="flex items-center gap-2.5">
          {onLoadDemoData && (
            <button
              onClick={onLoadDemoData}
              title="Load full multi-document audit sample for instant inspection"
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-[12px] font-semibold bg-gradient-to-r from-teal-500 to-emerald-600 hover:from-teal-600 hover:to-emerald-700 text-white shadow-sm shadow-teal-500/30 hover:shadow-teal-500/50 transition-all duration-150 cursor-pointer active:scale-95"
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Load Sample Dossier</span>
              <span className="sm:hidden">Sample</span>
            </button>
          )}

          {/* Theme switcher */}
          <button
            onClick={onToggleDark}
            aria-label="Toggle theme"
            className="flex items-center justify-center w-9 h-9 rounded-lg border border-border bg-surface-1 hover:bg-surface-3 text-muted hover:text-ink transition-all cursor-pointer shadow-sm"
          >
            {dark ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4 text-slate-700" />}
          </button>
        </div>
      </div>
    </header>
  )
}
