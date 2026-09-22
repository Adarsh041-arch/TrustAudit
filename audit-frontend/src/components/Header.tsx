interface HeaderProps {
  dark: boolean
  onToggleDark: () => void
  title?: string
}

export function Header({ dark, onToggleDark, title }: HeaderProps) {
  return (
    <header className="flex items-center justify-between px-6 py-4 border-b-[0.5px] border-border">
      <div className="flex items-center gap-3">
        <img
          src={dark ? "/trustaudit-logo-dark.png" : "/trustaudit-logo-transparent.png"}
          alt="TrustAudit"
          className="h-8 w-auto object-contain"
        />
        {title && (
          <>
            <span className="text-muted mx-1">/</span>
            <span className="text-body text-muted">{title}</span>
          </>
        )}
      </div>
      <button
        onClick={onToggleDark}
        className="text-[13px] text-muted hover:text-ink transition-colors border-[0.5px] border-border rounded-lg px-3 py-1.5 bg-transparent hover:bg-ink-50 cursor-pointer"
      >
        {dark ? '☀ Light' : '☾ Dark'}
      </button>
    </header>
  )
}
