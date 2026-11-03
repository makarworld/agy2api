import { NavLink, Outlet } from 'react-router-dom';
import {
  Key,
  Terminal,
  MessageSquare,
  Image as ImageIcon,
  Mic,
  BarChart3,
  Users,
  Layers,
  LogOut,
  Settings as SettingsIcon,
  Bot,
  Zap,
  Globe,
} from 'lucide-react';
import { useApiKey } from '../hooks/use-api-key';
import { useI18n } from '../lib/i18n';

export function Layout() {
  const { clearApiKey } = useApiKey();
  const { lang, setLang, t } = useI18n();

  const handleLogout = () => {
    if (window.confirm(t.logoutConfirm)) {
      clearApiKey();
    }
  };

  return (
    <div className="flex h-screen bg-background text-foreground overflow-hidden">
      {/* Sidebar */}
      <aside className="w-64 border-r border-border/70 bg-card/40 backdrop-blur-md flex flex-col shrink-0 select-none">
        {/* Brand Header */}
        <div className="p-4 border-b border-border/70 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-primary/15 text-primary flex items-center justify-center border border-primary/25 shadow-xs">
              <Bot className="w-4 h-4" />
            </div>
            <div>
              <h2 className="font-bold text-sm tracking-tight text-foreground flex items-center gap-1.5 leading-none">
                AGY2API
                <span className="text-[10px] font-mono font-medium px-1.5 py-0.2 rounded bg-muted text-muted-foreground border border-border/60">
                  {t.version}
                </span>
              </h2>
              <p className="text-[11px] text-muted-foreground mt-1 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                {t.serviceActive}
              </p>
            </div>
          </div>
        </div>

        {/* Navigation Sections */}
        <nav className="flex-1 p-3 space-y-4 overflow-y-auto">
          <div>
            <div className="space-y-0.5">
              <NavItem to="/" icon={<Zap className="w-4 h-4 text-amber-500" />} label={t.navQuickstart} />
            </div>
          </div>

          <div>
            <div className="px-3 mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60 font-sans">
              {t.navPlayground}
            </div>
            <div className="space-y-0.5">
              <NavItem to="/chat" icon={<MessageSquare className="w-4 h-4" />} label={t.navChat} />
              <NavItem to="/images" icon={<ImageIcon className="w-4 h-4" />} label={t.navImages} />
              <NavItem to="/audio" icon={<Mic className="w-4 h-4" />} label={t.navAudio} />
            </div>
          </div>

          <div>
            <div className="px-3 mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60 font-sans">
              {t.navMonitoring}
            </div>
            <div className="space-y-0.5">
              <NavItem to="/requests" icon={<Layers className="w-4 h-4" />} label={t.navRequests} />
              <NavItem to="/stats" icon={<BarChart3 className="w-4 h-4" />} label={t.navStats} />
              <NavItem to="/logs" icon={<Terminal className="w-4 h-4" />} label={t.navLogs} />
            </div>
          </div>

          <div>
            <div className="px-3 mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60 font-sans">
              {t.navConfiguration}
            </div>
            <div className="space-y-0.5">
              <NavItem to="/pool" icon={<Users className="w-4 h-4" />} label={t.navPool} />
              <NavItem to="/settings" icon={<SettingsIcon className="w-4 h-4" />} label={t.navSettings} />
              <NavItem to="/keys" icon={<Key className="w-4 h-4" />} label={t.navKeys} />
            </div>
          </div>
        </nav>

        {/* Sidebar Footer */}
        <div className="p-3 border-t border-border/70 bg-muted/20">
          <button
            onClick={handleLogout}
            className="flex items-center gap-2.5 w-full px-3 py-2 rounded-lg text-xs font-medium text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors cursor-pointer"
          >
            <LogOut className="w-3.5 h-3.5" />
            <span>{t.logout}</span>
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col min-w-0 h-full overflow-hidden bg-background">
        {/* Top Header Bar with Language Switcher */}
        <header className="h-12 border-b border-border/60 bg-card/20 px-6 flex items-center justify-between shrink-0 select-none">
          <div className="flex items-center gap-2 text-xs text-muted-foreground font-mono">
            <span className="w-2 h-2 rounded-full bg-emerald-500" />
            <span>AGY2API Proxy Server</span>
          </div>

          <div className="flex items-center gap-3">
            {/* Language Switcher */}
            <div className="flex items-center bg-muted/50 p-0.5 rounded-lg border border-border/60 text-xs font-sans">
              <div className="px-1.5 py-1 text-muted-foreground flex items-center">
                <Globe className="w-3.5 h-3.5" />
              </div>
              <button
                onClick={() => setLang('ru')}
                className={`px-2 py-0.5 rounded-md font-semibold transition-all cursor-pointer ${
                  lang === 'ru'
                    ? 'bg-background text-foreground shadow-2xs border border-border/40'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
                title="Русский язык"
              >
                RU
              </button>
              <button
                onClick={() => setLang('en')}
                className={`px-2 py-0.5 rounded-md font-semibold transition-all cursor-pointer ${
                  lang === 'en'
                    ? 'bg-background text-foreground shadow-2xs border border-border/40'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
                title="English language"
              >
                EN
              </button>
            </div>
          </div>
        </header>

        {/* Content View */}
        <div className="flex-1 flex flex-col min-h-0 overflow-auto">
          <Outlet />
        </div>
      </main>
    </div>
  );
}

function NavItem({ to, icon, label }: { to: string; icon: React.ReactNode; label: string }) {
  return (
    <NavLink
      to={to}
      end={to === '/'}
      className={({ isActive }) =>
        `flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium transition-all ${
          isActive
            ? 'bg-primary/10 text-primary border border-primary/20 shadow-2xs font-semibold'
            : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
        }`
      }
    >
      <span className="shrink-0">{icon}</span>
      <span className="truncate">{label}</span>
    </NavLink>
  );
}
