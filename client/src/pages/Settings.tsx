import { useEffect, useState } from 'react';
import {
    ArrowsClockwise,
    CheckCircle,
    GearSix,
    Info,
    ShieldCheck,
} from '@phosphor-icons/react';
import AgentCard from '../components/agents/AgentCard';
import { api, type AgentStatus, type AppSettings, type EngineStatus } from '../lib/swiftagent';
import { applyTheme } from '../lib/theme';
import { toast } from '../lib/toast';

const PERMISSION_MODES = ['default', 'acceptEdits', 'dontAsk', 'bypassPermissions', 'plan'];

export default function Settings() {
    const [settings, setSettings] = useState<AppSettings | null>(null);
    const [agents, setAgents] = useState<AgentStatus[]>([]);
    const [engineStatus, setEngineStatus] = useState<EngineStatus | null>(null);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [refreshing, setRefreshing] = useState(false);

    useEffect(() => {
        let cancelled = false;
        Promise.all([api.getSettings(), api.listAgents(), api.getEngineStatus(false)])
            .then(([currentSettings, catalog, status]) => {
                if (cancelled) return;
                setSettings(currentSettings);
                setAgents(catalog.agents);
                setEngineStatus(status);
            })
            .catch((error: Error) => toast.error('Failed to load settings', error.message))
            .finally(() => {
                if (!cancelled) setLoading(false);
            });
        return () => {
            cancelled = true;
        };
    }, []);

    const update = <K extends keyof AppSettings>(key: K, value: AppSettings[K]) => {
        if (!settings) return;
        setSettings({ ...settings, [key]: value });
        if (key === 'theme') applyTheme(value as AppSettings['theme']);
    };

    const save = async () => {
        if (!settings) return;
        setSaving(true);
        try {
            const updated = await api.updateSettings(settings);
            setSettings(updated);
            const catalog = await api.listAgents(true);
            setAgents(catalog.agents);
            applyTheme(updated.theme);
            toast.success('Settings saved', `${updated.default_agent_id} is your default agent.`);
        } catch (error) {
            toast.error('Failed to save settings', (error as Error).message);
        } finally {
            setSaving(false);
        }
    };

    const refreshAgents = async () => {
        setRefreshing(true);
        try {
            const [catalog, status] = await Promise.all([api.listAgents(true), api.getEngineStatus(false)]);
            setAgents(catalog.agents);
            setEngineStatus(status);
            toast.success('Agent detection refreshed');
        } catch (error) {
            toast.error('Detection failed', (error as Error).message);
        } finally {
            setRefreshing(false);
        }
    };

    if (loading) return <div className="p-6 text-sm text-muted-foreground">Loading your agents…</div>;
    if (!settings) return <div className="p-6 text-sm text-destructive">Settings unavailable.</div>;

    return (
        <div className="flex-1 overflow-y-auto px-4 py-6 sm:px-8">
            <div className="mx-auto max-w-4xl space-y-8">
                <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
                    <div>
                        <div className="flex items-center gap-2 text-muted-foreground">
                            <GearSix weight="bold" className="h-4 w-4" />
                            <span className="text-xs font-semibold uppercase tracking-[0.18em]">Local control</span>
                        </div>
                        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">Your agents</h1>
                        <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted-foreground">
                            SwiftAgent detects local coding agents and exposes only the features each adapter can prove.
                        </p>
                    </div>
                    <button
                        type="button"
                        onClick={refreshAgents}
                        disabled={refreshing}
                        className="inline-flex h-9 items-center justify-center gap-2 rounded-xl border border-border bg-card px-3 text-xs font-medium text-foreground transition hover:bg-accent disabled:opacity-50"
                    >
                        <ArrowsClockwise className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
                        Detect again
                    </button>
                </header>

                <div className="flex items-start gap-3 rounded-2xl border border-primary/20 bg-primary/[0.06] p-4 text-sm">
                    <Info weight="fill" className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                    <div>
                        <p className="font-medium text-foreground">Your existing Claude sessions are still here.</p>
                        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                            This upgrade adds agent identity without moving history or asking for new credentials. Authentication remains owned by each local CLI.
                        </p>
                    </div>
                </div>

                <section aria-labelledby="agent-list-title" className="space-y-3">
                    <div className="flex items-center justify-between">
                        <h2 id="agent-list-title" className="text-sm font-semibold text-foreground">Detected integrations</h2>
                        <span className="text-xs text-muted-foreground">{agents.length} adapter{agents.length === 1 ? '' : 's'}</span>
                    </div>
                    <div className="grid gap-3">
                        {agents.map((agent) => (
                            <AgentCard
                                key={agent.agent_id}
                                agent={agent}
                                selected={settings.default_agent_id === agent.agent_id}
                                onSelect={() => update('default_agent_id', agent.agent_id)}
                            />
                        ))}
                    </div>
                </section>

                <section className="grid gap-4 lg:grid-cols-[1.25fr_0.75fr]">
                    <div className="rounded-2xl border border-border bg-card p-5">
                        <div className="flex items-center gap-2">
                            <ShieldCheck weight="bold" className="h-4 w-4 text-foreground" />
                            <h2 className="text-sm font-semibold text-foreground">Workspace & safety</h2>
                        </div>
                        <div className="mt-4 space-y-4">
                            <label className="block space-y-1.5">
                                <span className="text-xs font-medium text-foreground">Workspace root</span>
                                <input
                                    value={settings.workspace_dir}
                                    onChange={(event) => update('workspace_dir', event.target.value)}
                                    className="h-10 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-primary/50 focus:ring-2 focus:ring-primary/10"
                                />
                                <span className="block text-[11px] text-muted-foreground">Every file action and task directory stays under this root.</span>
                            </label>

                            <label className="block space-y-1.5">
                                <span className="text-xs font-medium text-foreground">Isolation policy</span>
                                <select
                                    value={settings.sandbox_mode}
                                    onChange={(event) => update('sandbox_mode', event.target.value as AppSettings['sandbox_mode'])}
                                    className="h-10 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-primary/50 focus:ring-2 focus:ring-primary/10"
                                >
                                    <option value="strict">Strict · block when isolation is unavailable</option>
                                    <option value="fallback">Trusted local fallback · no OS isolation</option>
                                </select>
                            </label>

                            {engineStatus?.degraded ? (
                                <div role="alert" className="rounded-xl border border-amber-500/35 bg-amber-500/10 p-3 text-xs leading-relaxed text-amber-800 dark:text-amber-200">
                                    <strong>Strict runs are currently blocked.</strong> {engineStatus.degraded_reason}
                                </div>
                            ) : (
                                <div className="inline-flex items-center gap-2 text-xs text-emerald-700 dark:text-emerald-300">
                                    <CheckCircle weight="fill" className="h-4 w-4" />
                                    {settings.sandbox_mode === 'strict' ? 'Strict isolation is available.' : 'Fallback is explicitly enabled.'}
                                </div>
                            )}
                        </div>
                    </div>

                    <div className="rounded-2xl border border-border bg-card p-5">
                        <h2 className="text-sm font-semibold text-foreground">Appearance</h2>
                        <div className="mt-4 space-y-4">
                            <label className="block space-y-1.5">
                                <span className="text-xs font-medium text-foreground">Theme</span>
                                <select
                                    value={settings.theme}
                                    onChange={(event) => update('theme', event.target.value as AppSettings['theme'])}
                                    className="h-10 w-full rounded-xl border border-border bg-background px-3 text-sm"
                                >
                                    <option value="system">System</option>
                                    <option value="light">Light</option>
                                    <option value="dark">Dark</option>
                                </select>
                            </label>
                            <label className="flex items-center justify-between rounded-xl border border-border px-3 py-2.5">
                                <span className="text-xs font-medium text-foreground">Debug diagnostics</span>
                                <input
                                    type="checkbox"
                                    checked={settings.debug_mode}
                                    onChange={(event) => update('debug_mode', event.target.checked)}
                                    className="h-4 w-4"
                                />
                            </label>
                        </div>
                    </div>
                </section>

                {agents.some((agent) => agent.agent_id === 'claude-code') ? (
                    <details className="rounded-2xl border border-border bg-card p-5">
                        <summary className="cursor-pointer text-sm font-semibold text-foreground">Claude Code adapter options</summary>
                        <div className="mt-4 grid gap-4 sm:grid-cols-3">
                            <label className="space-y-1.5">
                                <span className="text-xs text-muted-foreground">Model override</span>
                                <input
                                    value={settings.claude_model ?? ''}
                                    onChange={(event) => update('claude_model', event.target.value || null)}
                                    placeholder="CLI default"
                                    className="h-10 w-full rounded-xl border border-border bg-background px-3 text-sm"
                                />
                            </label>
                            <label className="space-y-1.5">
                                <span className="text-xs text-muted-foreground">Permission mode</span>
                                <select
                                    value={settings.claude_permission_mode}
                                    onChange={(event) => update('claude_permission_mode', event.target.value)}
                                    className="h-10 w-full rounded-xl border border-border bg-background px-3 text-sm"
                                >
                                    {PERMISSION_MODES.map((mode) => <option key={mode} value={mode}>{mode}</option>)}
                                </select>
                            </label>
                            <label className="space-y-1.5">
                                <span className="text-xs text-muted-foreground">Executable path</span>
                                <input
                                    value={settings.claude_cli_path ?? ''}
                                    onChange={(event) => update('claude_cli_path', event.target.value || null)}
                                    placeholder="Auto-detect"
                                    className="h-10 w-full rounded-xl border border-border bg-background px-3 text-sm"
                                />
                            </label>
                        </div>
                    </details>
                ) : null}

                {agents.some((agent) => agent.agent_id === 'acp-agent') ? (
                    <details className="rounded-2xl border border-border bg-card p-5">
                        <summary className="cursor-pointer text-sm font-semibold text-foreground">ACP adapter options</summary>
                        <div className="mt-4 space-y-2">
                            <label className="block space-y-1.5">
                                <span className="text-xs text-muted-foreground">Literal command array</span>
                                <input
                                    value={settings.acp_command_json}
                                    onChange={(event) => update('acp_command_json', event.target.value)}
                                    placeholder='["your-agent", "acp"]'
                                    spellCheck={false}
                                    className="h-10 w-full rounded-xl border border-border bg-background px-3 font-mono text-xs"
                                />
                            </label>
                            <p className="text-[11px] leading-relaxed text-muted-foreground">
                                One JSON string per argument. SwiftAgent launches this directly without a shell; authentication stays with the agent.
                            </p>
                        </div>
                    </details>
                ) : null}

                <div className="sticky bottom-4 flex justify-end">
                    <button
                        type="button"
                        onClick={save}
                        disabled={saving}
                        className="h-10 rounded-xl bg-primary px-5 text-sm font-medium text-primary-foreground shadow-lg transition hover:bg-primary/90 disabled:opacity-50"
                    >
                        {saving ? 'Saving…' : 'Save changes'}
                    </button>
                </div>
            </div>
        </div>
    );
}
