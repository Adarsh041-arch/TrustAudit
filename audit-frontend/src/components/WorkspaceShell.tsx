import { useState, type ReactNode } from 'react'
import { ShieldCheck, Plus, Moon, Sun, Menu, X, ArrowUpRight, FlaskConical, ChevronRight } from 'lucide-react'

type Props = {
  children: ReactNode; dark: boolean; onToggleDark: () => void
  activeTab: string; onNavigate: (id: string) => void
  navItems: { id: string; label: string; icon: ReactNode; badge?: number }[]
  isDemo: boolean; uploading: boolean; onLoadDemo: () => void; onExitDemo: () => void
}

export function WorkspaceShell(p: Props) {
  const [open, setOpen] = useState(false)
  const navigate = (id: string) => { p.onNavigate(id); setOpen(false) }
  return <div className="v2-app">
    <a href="#workspace-main" className="v2-skip">Skip to workspace</a>
    {open && <button className="v2-overlay" aria-label="Close navigation" onClick={() => setOpen(false)} />}
    <aside className={`v2-sidebar ${open ? 'is-open' : ''}`}>
      <a href="?mode=v2" className="v2-brand"><span><ShieldCheck size={23} /></span>TrustAudit <small>V2</small></a>
      <button className="v2-primary v2-new" onClick={() => navigate('upload')}><Plus size={17} /> New audit</button>
      <nav aria-label="Main navigation">
        {p.navItems.map((item, i) => <div key={item.id}>
          {(i === 0 || i === 4 || i === 7) && <p className="v2-nav-label">{i === 0 ? 'WORKSPACE' : i === 4 ? 'OPERATIONS' : 'MANAGE'}</p>}
          <button className={`v2-nav-item ${p.activeTab === item.id ? 'active' : ''}`} aria-current={p.activeTab === item.id ? 'page' : undefined} onClick={() => navigate(item.id)}>
            {item.icon}<span>{item.label}</span>{item.badge !== undefined && <small>{item.badge}</small>}
          </button>
        </div>)}
      </nav>
      <div className="v2-sidebar-bottom"><div className="v2-help"><FlaskConical size={18} /><strong>Explore an example</strong><p>Walk through a sample audit and its supporting evidence.</p><button onClick={p.onLoadDemo}>Open sample workspace <ArrowUpRight size={14} /></button></div><div className="v2-profile"><span>TA</span><div><strong>Audit workspace</strong><small>Document review & verification</small></div></div></div>
    </aside>
    <div className="v2-body">
      <header className="v2-topbar"><div className="v2-breadcrumb"><button className="v2-icon-button v2-mobile-menu" onClick={() => setOpen(!open)} aria-label={open ? 'Close navigation' : 'Open navigation'} aria-expanded={open}>{open ? <X size={19} /> : <Menu size={19} />}</button><span>Workspace</span><ChevronRight size={14} /><strong>{p.navItems.find(n => n.id === p.activeTab)?.label}</strong></div><div className="v2-top-actions"><span className="v2-session-label">{p.uploading ? 'Audit in progress' : p.isDemo ? 'Sample workspace' : 'Current session'}</span><button className="v2-icon-button" aria-label={p.dark ? 'Switch to light theme' : 'Switch to dark theme'} onClick={p.onToggleDark}>{p.dark ? <Sun size={18} /> : <Moon size={18} />}</button></div></header>
      <main id="workspace-main" className="v2-main" tabIndex={-1}>
        {p.isDemo && <div className="v2-demo-banner"><FlaskConical size={16} /><span><strong>Sample data.</strong> These examples are not live audit results. Your next upload starts a separate workspace.</span><button onClick={p.onExitDemo}>Exit sample <X size={14} /></button></div>}
        {p.uploading && p.activeTab !== 'upload' && <button className="v2-demo-banner" onClick={() => navigate('upload')}>Your audit is running. View progress <ArrowUpRight size={15} /></button>}
        {p.children}
      </main>
    </div>
  </div>
}
