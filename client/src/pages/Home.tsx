import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router';
import {
    CaretDown,
    CircleNotch,
    FolderOpen,
    PaperPlaneRight,
    ShieldCheck,
    SlidersHorizontal,
    Sparkle,
    WarningCircle,
} from '@phosphor-icons/react';
import { AnimatePresence, motion } from 'framer-motion';
import { api, type AgentStatus, type AppSettings, ws } from '../lib/swiftagent';
import { toast } from '../lib/toast';

const isAgentReady = (agent: AgentStatus) => (
    agent.installed &&
    agent.compatible !== false &&
    agent.auth_status !== 'action_required' &&
    agent.auth_status !== 'error'
);

const configuredModelFor = (agentId: string, settings: AppSettings) => {
    if (agentId === 'opencode') return settings.opencode_model ?? '';
    if (agentId === 'codex') return settings.codex_model ?? '';
    if (agentId === 'claude-code') return settings.claude_model ?? '';
    return '';
};

export default function Home() {
    const [prompt, setPrompt] = useState('');
    const [loading, setLoading] = useState(false);
    const [loadingAgents, setLoadingAgents] = useState(true);
    const [agents, setAgents] = useState<AgentStatus[]>([]);
    const [settings, setSettings] = useState<AppSettings | null>(null);
    const [agentId, setAgentId] = useState('');
    const [workingDirectory, setWorkingDirectory] = useState('.');
    const [modelId, setModelId] = useState('');
    const [showOptions, setShowOptions] = useState(false);
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const startTimeoutRef = useRef<number | null>(null);
    const navigate = useNavigate();

    const selectedAgent = useMemo(
        () => agents.find((agent) => agent.agent_id === agentId) ?? null,
        [agentId, agents],
    );
    const agentReady = Boolean(selectedAgent && isAgentReady(selectedAgent));

    useEffect(() => {
        textareaRef.current?.focus();
        let cancelled = false;
        Promise.all([api.listAgents(), api.getSettings()])
            .then(([catalog, currentSettings]) => {
                if (cancelled) return;
                setAgents(catalog.agents);
                setSettings(currentSettings);
                const preferred = catalog.agents.find(
                    (agent) =>
                        agent.agent_id === currentSettings.default_agent_id &&
                        isAgentReady(agent),
                );
                const firstReady = catalog.agents.find(
                    isAgentReady,
                );
                const initialAgentId = (preferred ?? firstReady ?? catalog.agents[0])?.agent_id ?? '';
                setAgentId(initialAgentId);
                setModelId(configuredModelFor(initialAgentId, currentSettings));
            })
            .catch((error: Error) => toast.error('Could not load agents', error.message))
            .finally(() => {
                if (!cancelled) setLoadingAgents(false);
            });
        return () => {
            cancelled = true;
        };
    }, []);

    useEffect(() => {
        const unsubStarted = ws.on('task:started', (event) => {
            const taskId = event.task_id || (event.payload as { id?: string })?.id;
            if (taskId) {
                setLoading(false);
                if (startTimeoutRef.current) {
                    window.clearTimeout(startTimeoutRef.current);
                    startTimeoutRef.current = null;
                }
                navigate(`/task/${taskId}`);
            }
        });
        const unsubError = ws.on('task:error', (event) => {
            if (event.task_id) return;
            const payload = event.payload as { error?: string };
            setLoading(false);
            toast.error('Failed to start task', payload.error || 'Unknown error');
        });
        return () => {
            unsubStarted();
            unsubError();
            if (startTimeoutRef.current) window.clearTimeout(startTimeoutRef.current);
        };
    }, [navigate]);

    const handleSubmit = () => {
        const trimmed = prompt.trim();
        if (!trimmed || loading || !selectedAgent || !agentReady) return;

        setLoading(true);
        ws.startTask({
            prompt: trimmed,
            agent_id: selectedAgent.agent_id,
            working_directory: workingDirectory.trim() || undefined,
            model_id: modelId.trim() || undefined,
        });
        if (startTimeoutRef.current) window.clearTimeout(startTimeoutRef.current);
        startTimeoutRef.current = window.setTimeout(() => {
            setLoading(false);
            toast.error('Task start timed out', 'No response from the local SwiftAgent server.');
        }, 15000);
    };

    const handleInput = () => {
        const element = textareaRef.current;
        if (!element) return;
        element.style.height = 'auto';
        element.style.height = `${Math.min(element.scrollHeight, 240)}px`;
    };

    return (
        <div className="relative flex flex-1 flex-col items-center justify-center overflow-y-auto px-4 py-10 sm:px-8">
            <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
                <div className="absolute left-1/2 top-1/3 h-96 w-96 -translate-x-1/2 rounded-full bg-primary/[0.055] blur-3xl" />
            </div>

            <motion.div
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.45, ease: 'easeOut' }}
                className="relative w-full max-w-3xl space-y-7"
            >
                <header className="space-y-3 text-center">
                    <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-2xl border border-primary/20 bg-primary/10 text-primary">
                        <Sparkle weight="fill" className="h-5 w-5" />
                    </div>
                    <div>
                        <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
                            One workspace. Your choice of agent.
                        </h1>
                        <p className="mx-auto mt-2 max-w-xl text-sm leading-relaxed text-muted-foreground">
                            Delegate locally, follow every tool call, and keep a durable history you control.
                        </p>
                    </div>
                </header>

                <section className="overflow-hidden rounded-3xl border border-border bg-card shadow-[0_24px_80px_-48px_hsl(var(--foreground))]">
                    <div className="flex flex-col gap-3 border-b border-border bg-muted/30 px-4 py-3 sm:flex-row sm:items-center">
                        <label className="relative min-w-0 flex-1">
                            <span className="sr-only">Coding agent</span>
                            <select
                                value={agentId}
                                onChange={(event) => {
                                    const nextAgentId = event.target.value;
                                    setAgentId(nextAgentId);
                                    setModelId(settings ? configuredModelFor(nextAgentId, settings) : '');
                                }}
                                disabled={loadingAgents || agents.length === 0}
                                className="h-10 w-full appearance-none rounded-xl border border-border bg-background pl-3 pr-9 text-sm font-medium text-foreground outline-none transition focus:border-primary/50 focus:ring-2 focus:ring-primary/10 disabled:opacity-50"
                            >
                                {agents.map((agent) => (
                                    <option key={agent.agent_id} value={agent.agent_id}>
                                        {agent.display_name} · {!agent.installed ? 'missing' : !isAgentReady(agent) ? 'attention required' : 'ready'}
                                    </option>
                                ))}
                            </select>
                            <CaretDown className="pointer-events-none absolute right-3 top-3 h-4 w-4 text-muted-foreground" />
                        </label>

                        <div className="flex min-w-0 items-center gap-2 text-xs text-muted-foreground sm:max-w-[46%]">
                            <FolderOpen className="h-4 w-4 shrink-0" />
                            <span className="truncate" title={settings?.workspace_dir}>
                                {settings?.workspace_dir || 'Loading workspace…'}
                            </span>
                        </div>
                    </div>

                    <div className="relative">
                        <textarea
                            ref={textareaRef}
                            value={prompt}
                            onChange={(event) => {
                                setPrompt(event.target.value);
                                handleInput();
                            }}
                            onKeyDown={(event) => {
                                if (event.key === 'Enter' && !event.shiftKey) {
                                    event.preventDefault();
                                    handleSubmit();
                                }
                            }}
                            placeholder="Describe the outcome you want…"
                            className="min-h-36 max-h-60 w-full resize-none bg-transparent px-5 pb-16 pt-5 text-[15px] leading-relaxed text-foreground outline-none placeholder:text-muted-foreground/60"
                            disabled={loading}
                            rows={4}
                        />

                        <div className="absolute bottom-3 left-3 right-3 flex items-center justify-between gap-3">
                            <button
                                type="button"
                                onClick={() => setShowOptions((visible) => !visible)}
                                className="inline-flex h-9 items-center gap-2 rounded-xl px-3 text-xs font-medium text-muted-foreground transition hover:bg-accent hover:text-foreground"
                                aria-expanded={showOptions}
                            >
                                <SlidersHorizontal className="h-4 w-4" />
                                Run options
                            </button>

                            <button
                                type="button"
                                onClick={handleSubmit}
                                disabled={!prompt.trim() || loading || !agentReady}
                                className="inline-flex h-10 items-center gap-2 rounded-xl bg-primary px-4 text-sm font-medium text-primary-foreground transition hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-40"
                            >
                                {loading ? <CircleNotch weight="bold" className="h-4 w-4 animate-spin" /> : <PaperPlaneRight weight="fill" className="h-4 w-4" />}
                                Run
                            </button>
                        </div>
                    </div>

                    <AnimatePresence initial={false}>
                        {showOptions ? (
                            <motion.div
                                initial={{ height: 0, opacity: 0 }}
                                animate={{ height: 'auto', opacity: 1 }}
                                exit={{ height: 0, opacity: 0 }}
                                className="overflow-hidden border-t border-border"
                            >
                                <div className="grid gap-4 bg-muted/20 p-4 sm:grid-cols-2">
                                    <label className="space-y-1.5">
                                        <span className="text-xs font-medium text-foreground">Directory inside workspace</span>
                                        <input
                                            value={workingDirectory}
                                            onChange={(event) => setWorkingDirectory(event.target.value)}
                                            placeholder="."
                                            className="h-10 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-primary/50 focus:ring-2 focus:ring-primary/10"
                                        />
                                    </label>
                                    {selectedAgent?.capabilities.model_discovery ? (
                                        <label className="space-y-1.5">
                                            <span className="text-xs font-medium text-foreground">Model</span>
                                            {selectedAgent.models.length ? (
                                                <select
                                                    value={modelId}
                                                    onChange={(event) => setModelId(event.target.value)}
                                                    className="h-10 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-primary/50 focus:ring-2 focus:ring-primary/10"
                                                >
                                                    <option value="">Agent default</option>
                                                    {selectedAgent.models.map((model) => (
                                                        <option key={model.id} value={model.id}>{model.name}</option>
                                                    ))}
                                                </select>
                                            ) : (
                                                <input
                                                    value={modelId}
                                                    onChange={(event) => setModelId(event.target.value)}
                                                    placeholder="Agent default"
                                                    className="h-10 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-primary/50 focus:ring-2 focus:ring-primary/10"
                                                />
                                            )}
                                        </label>
                                    ) : null}
                                </div>
                            </motion.div>
                        ) : null}
                    </AnimatePresence>
                </section>

                {selectedAgent ? (
                    <div className="flex flex-col justify-between gap-3 px-1 text-xs text-muted-foreground sm:flex-row sm:items-center">
                        <span className="inline-flex items-center gap-2">
                            {agentReady ? <ShieldCheck className="h-4 w-4 text-emerald-600" /> : <WarningCircle className="h-4 w-4 text-amber-600" />}
                            {agentReady
                                ? `${selectedAgent.display_name} · ${settings?.sandbox_mode === 'strict' ? 'strict isolation requested' : 'trusted local fallback'}`
                                : selectedAgent.detail || 'This agent is not ready to run.'}
                        </span>
                        <Link to="/settings" className="shrink-0 font-medium text-primary hover:underline">
                            Manage agents
                        </Link>
                    </div>
                ) : (
                    <p className="text-center text-xs text-muted-foreground">
                        No runnable adapter is configured. Open Your agents to connect one.
                    </p>
                )}
            </motion.div>
        </div>
    );
}
