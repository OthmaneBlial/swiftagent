import { Outlet, Link, useLocation } from 'react-router';
import {
    Lightning,
    ClockCounterClockwise,
    FolderSimple,
    GearSix,
} from '@phosphor-icons/react';
import { cn } from '../../lib/utils';

const navItems = [
    { path: '/', icon: Lightning, label: 'Tasks' },
    { path: '/history', icon: ClockCounterClockwise, label: 'History' },
    { path: '/files', icon: FolderSimple, label: 'Files' },
];

export default function Layout() {
    const location = useLocation();
    const isTaskPath = location.pathname === '/' || location.pathname.startsWith('/task/');

    return (
        <div className="min-h-screen bg-background flex">
            {/* Sidebar */}
            <aside className="w-16 border-r border-border flex flex-col items-center py-4 gap-2">
                {/* Logo */}
                <div className="w-9 h-9 rounded-lg bg-primary flex items-center justify-center mb-4">
                    <Lightning weight="bold" className="w-5 h-5 text-primary-foreground" />
                </div>

                {/* Navigation */}
                {navItems.map((item) => {
                    const Icon = item.icon;
                    const active =
                        item.path === '/'
                            ? isTaskPath
                            : location.pathname === item.path || location.pathname.startsWith(`${item.path}/`);
                    return (
                        <Link
                            key={item.path}
                            to={item.path}
                            className={cn(
                                'w-10 h-10 rounded-lg flex items-center justify-center transition-colors',
                                active
                                    ? 'bg-accent text-foreground'
                                    : 'text-muted-foreground hover:text-foreground hover:bg-accent/50'
                            )}
                            title={item.label}
                        >
                            <Icon weight={active ? 'fill' : 'regular'} className="w-5 h-5" />
                        </Link>
                    );
                })}

                <div className="flex-1" />

                {/* Settings */}
                <Link
                    to="/settings"
                    className={cn(
                        'w-10 h-10 rounded-lg flex items-center justify-center transition-colors',
                        location.pathname === '/settings'
                            ? 'bg-accent text-foreground'
                            : 'text-muted-foreground hover:text-foreground hover:bg-accent/50'
                    )}
                    title="Settings"
                >
                    <GearSix
                        weight={location.pathname === '/settings' ? 'fill' : 'regular'}
                        className="w-5 h-5"
                    />
                </Link>
            </aside>

            {/* Main content */}
            <main className="min-w-0 flex-1 flex flex-col">
                <Outlet />
            </main>
        </div>
    );
}
