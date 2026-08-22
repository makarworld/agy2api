import { NavLink, Outlet } from 'react-router-dom';
import { Key, Terminal, MessageSquare, Image as ImageIcon, Mic, BarChart3, Users, Layers } from 'lucide-react';

export function Layout() {
  return (
    <div className="flex h-screen bg-background text-foreground">
      {/* Sidebar */}
      <div className="w-64 border-r bg-sidebar flex flex-col">
        <div className="p-4 border-b border-sidebar-border">
          <h2 className="font-bold text-lg tracking-tight text-sidebar-foreground">AGY2API</h2>
          <p className="text-xs text-muted-foreground">Admin UI</p>
        </div>
        <nav className="flex-1 p-4 space-y-1">
          <NavItem to="/" icon={<MessageSquare className="w-4 h-4" />} label="Chat" />
          <NavItem to="/images" icon={<ImageIcon className="w-4 h-4" />} label="Images" />
          <NavItem to="/audio" icon={<Mic className="w-4 h-4" />} label="Audio" />
          <NavItem to="/requests" icon={<Layers className="w-4 h-4" />} label="Requests" />
          <NavItem to="/stats" icon={<BarChart3 className="w-4 h-4" />} label="Stats" />
          <NavItem to="/pool" icon={<Users className="w-4 h-4" />} label="Pool" />
          <NavItem to="/logs" icon={<Terminal className="w-4 h-4" />} label="Logs" />
          <NavItem to="/keys" icon={<Key className="w-4 h-4" />} label="API Keys" />
        </nav>
      </div>

      {/* Main Content */}
      <main className="flex-1 flex flex-col min-w-0">
        <Outlet />
      </main>
    </div>
  );
}

function NavItem({ to, icon, label }: { to: string; icon: React.ReactNode; label: string }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
          isActive
            ? 'bg-sidebar-accent text-sidebar-accent-foreground'
            : 'text-sidebar-foreground hover:bg-sidebar-accent/50'
        }`
      }
    >
      {icon}
      {label}
    </NavLink>
  );
}
