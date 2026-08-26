import { useEffect, useState } from 'react';
import { GearSix, ShieldCheck, ArrowsClockwise } from '@phosphor-icons/react';
import { api, type AppSettings, type EngineStatus } from '../lib/swiftagent';
import { toast } from '../lib/toast';
import { applyTheme } from '../lib/theme';

const PERMISSION_MODES = ['default', 'acceptEdits', 'dontAsk', 'bypassPermissions', 'plan'];

export default function Settings() {
    const [settings, setSettings] = useState<AppSettings | null>(null);
    const [engineStatus, setEngineStatus] = useState<EngineStatus | null>(null);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        let cancelled = false;

        Promise.all([api.getSettings(), api.getEngineStatus(false)])
            .then(([s, status]) => {
                if (cancelled) return;
                setSettings(s);
                setEngineStatus(status);
                setLoading(false);
            })
            .catch((error: Error) => {
                if (cancelled) return;
                toast.error('Failed to load settings', error.message);
                setLoading(false);
            });

        return () => {
            cancelled = true;
        };
    }, []);

    const update = <K extends keyof AppSettings>(key: K, value: AppSettings[K]) => {
        if (!settings) return;
        const next = { ...settings, [key]: value };
        setSettings(next);
        if (key === 'theme') {
            applyTheme(value as AppSettings['theme']);
        }
    };

    const save = async () => {
        if (!settings) return;
        setSaving(true);
        try {
            const updated = await api.updateSettings(settings);
            setSettings(updated);
            applyTheme(updated.theme);
            toast.success('Settings saved');
        } catch (error) {
            toast.error('Failed to save settings', (error as Error).message);
        } finally {
            setSaving(false);
        }
    };

    const refreshEngine = async (probeAuth: boolean) => {
        try {
            const status = await api.getEngineStatus(probeAuth);
            setEngineStatus(status);
            if (probeAuth) {
                toast.success('Auth probe complete', `Status: ${status.auth_probe.status}`);
            }
        } catch (error) {
            toast.error('Failed to load engine status', (error as Error).message);
        }
    };

    if (loading) {
        return <div className="p-6 text-sm text-muted-foreground">Loading settings...</div>;
    }

    if (!settings) {
        return <div className="p-6 text-sm text-red-500">Settings unavailable.</div>;
    }

    return (
        <div className="flex-1 overflow-y-auto p-6">
            <div className="max-w-3xl mx-auto space-y-6">
                <header className="flex items-center gap-2">
                    <GearSix weight="bold" className="w-5 h-5 text-foreground" />
                    <h1 className="text-lg font-semibold text-foreground">Settings</h1>
                </header>

                <section className="rounded-xl border border-border bg-card p-4 space-y-4">
                    <h2 className="text-sm font-semibold text-foreground">Claude</h2>

                    <label className="block space-y-1">
                        <span className="text-xs text-muted-foreground">Claude Model</span>
                        <input
                            value={settings.claude_model ?? ''}
                            onChange={(e) => update('claude_model', e.target.value || null)}
                            placeholder="CLI default"
                            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                        />
                    </label>

                    <label className="block space-y-1">
                        <span className="text-xs text-muted-foreground">Permission Mode</span>
                        <select
                            value={settings.claude_permission_mode}
                            onChange={(e) => update('claude_permission_mode', e.target.value)}
                            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                        >
                            {PERMISSION_MODES.map((mode) => (
                                <option key={mode} value={mode}>
                                    {mode}
                                </option>
                            ))}
                        </select>
                    </label>

                    <label className="block space-y-1">
                        <span className="text-xs text-muted-foreground">Claude CLI Path</span>
                        <input
                            value={settings.claude_cli_path ?? ''}
                            onChange={(e) => update('claude_cli_path', e.target.value || null)}
                            placeholder="Auto-detect from PATH"
                            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                        />
                    </label>
                </section>

                <section className="rounded-xl border border-border bg-card p-4 space-y-4">
                    <h2 className="text-sm font-semibold text-foreground">Workspace & Safety</h2>

                    <label className="block space-y-1">
                        <span className="text-xs text-muted-foreground">Workspace Directory</span>
                        <input
                            value={settings.workspace_dir}
                            onChange={(e) => update('workspace_dir', e.target.value)}
                            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                        />
                    </label>

                    <label className="block space-y-1">
                        <span className="text-xs text-muted-foreground">Sandbox Mode</span>
                        <select
                            value={settings.sandbox_mode}
                            onChange={(e) => update('sandbox_mode', e.target.value as AppSettings['sandbox_mode'])}
                            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                        >
                            <option value="strict">strict</option>
                            <option value="fallback">fallback</option>
                        </select>
                    </label>
                    <p className="text-xs text-muted-foreground">
                        Strict blocks a task if OS isolation is unavailable. Fallback is an explicit, unisolated mode for a trusted local machine.
                    </p>
                    {engineStatus?.degraded ? (
                        <div role="alert" className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-800 dark:text-amber-200">
                            <strong>Tasks are blocked in strict mode.</strong> {engineStatus.degraded_reason}
                        </div>
                    ) : null}
                </section>

                <section className="rounded-xl border border-border bg-card p-4 space-y-4">
                    <h2 className="text-sm font-semibold text-foreground">Appearance</h2>

                    <label className="block space-y-1">
                        <span className="text-xs text-muted-foreground">Theme</span>
                        <select
                            value={settings.theme}
                            onChange={(e) => update('theme', e.target.value as AppSettings['theme'])}
                            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                        >
                            <option value="system">system</option>
                            <option value="light">light</option>
                            <option value="dark">dark</option>
                        </select>
                    </label>

                    <label className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
                        <span className="text-xs text-muted-foreground">Debug Mode</span>
                        <input
                            type="checkbox"
                            checked={settings.debug_mode}
                            onChange={(e) => update('debug_mode', e.target.checked)}
                            className="h-4 w-4"
                        />
                    </label>
                </section>

                <section className="rounded-xl border border-border bg-card p-4 space-y-3">
                    <div className="flex items-center gap-2">
                        <ShieldCheck weight="bold" className="w-4 h-4 text-foreground" />
                        <h2 className="text-sm font-semibold text-foreground">Engine Status</h2>
                    </div>

                    {engineStatus ? (
                        <div className="text-xs text-muted-foreground space-y-1">
                            <p>Claude CLI: {engineStatus.claude_cli_available ? 'available' : 'missing'}</p>
                            <p>CLI path: {engineStatus.claude_cli_path || '(auto)'}</p>
                            <p>bwrap: {engineStatus.bwrap_available ? 'available' : 'missing'}</p>
                            {engineStatus.bwrap_available ? (
                                <p>bwrap usable: {engineStatus.bwrap_usable ? 'yes' : 'no'}</p>
                            ) : null}
                            <p>Sandbox mode: {engineStatus.sandbox_mode}</p>
                            <p>Strict sandbox active: {engineStatus.strict_sandbox_active ? 'yes' : 'no'}</p>
                            <p>Workspace: {engineStatus.workspace_dir}</p>
                            <p>Auth probe: {engineStatus.auth_probe.status}</p>
                            {engineStatus.bwrap_reason ? <p>{engineStatus.bwrap_reason}</p> : null}
                            {engineStatus.degraded_reason ? <p className="text-amber-600">{engineStatus.degraded_reason}</p> : null}
                        </div>
                    ) : (
                        <p className="text-xs text-muted-foreground">Engine status unavailable</p>
                    )}

                    <div className="flex gap-2">
                        <button
                            onClick={() => refreshEngine(false)}
                            className="h-8 px-3 rounded-lg border border-border text-xs hover:bg-accent/50 inline-flex items-center gap-1"
                        >
                            <ArrowsClockwise className="w-3.5 h-3.5" />
                            Refresh
                        </button>
                        <button
                            onClick={() => refreshEngine(true)}
                            className="h-8 px-3 rounded-lg border border-border text-xs hover:bg-accent/50"
                        >
                            Run Auth Probe
                        </button>
                    </div>
                </section>

                <div className="flex justify-end">
                    <button
                        onClick={save}
                        disabled={saving}
                        className="h-9 px-4 rounded-lg bg-primary text-primary-foreground text-sm hover:bg-primary/90 disabled:opacity-50"
                    >
                        {saving ? 'Saving...' : 'Save Changes'}
                    </button>
                </div>
            </div>
        </div>
    );
}
