import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router';
import {
    ArrowLeft,
    ArrowsLeftRight,
    CaretDown,
    Check,
    CircleNotch,
    Eye,
    ShieldCheck,
    WarningCircle,
} from '@phosphor-icons/react';
import AgentBadge from '../components/agents/AgentBadge';
import {
    api,
    type AgentStatus,
    type AppSettings,
    type HandoffPreview,
    type RunReceipt,
} from '../lib/swiftagent';
import { toast } from '../lib/toast';

const isAgentReady = (agent: AgentStatus) => (
    agent.installed &&
    agent.compatible !== false &&
    agent.auth_status !== 'action_required' &&
    agent.auth_status !== 'error'
);

const configuredModelFor = (agentId: string, settings: AppSettings | null) => {
    if (!settings) return '';
    if (agentId === 'opencode') return settings.opencode_model ?? '';
    if (agentId === 'codex') return settings.codex_model ?? '';
    if (agentId === 'claude-code') return settings.claude_model ?? '';
    return '';
};

function unresolvedQuestionCount(receipt: RunReceipt): number {
    const requested = new Set<string>();
    const resolved = new Set<string>();
    for (const event of receipt.ledger) {
        const requestId = String(event.payload.request_id || `sequence-${event.sequence}`);
        if (event.type === 'question.requested') requested.add(requestId);
        if (event.type === 'question.resolved' && event.payload.answered) resolved.add(requestId);
    }
    return [...requested].filter((requestId) => !resolved.has(requestId)).length;
}

interface ContextChoiceProps {
    checked: boolean;
    disabled?: boolean;
    label: string;
    detail: string;
    onChange: (checked: boolean) => void;
}

function ContextChoice({ checked, disabled, label, detail, onChange }: ContextChoiceProps) {
    return (
        <label className={`flex gap-3 rounded-xl border border-border bg-background p-3 ${disabled ? 'opacity-45' : 'cursor-pointer'}`}>
            <input
                type="checkbox"
                checked={checked}
                disabled={disabled}
                onChange={(event) => onChange(event.target.checked)}
                className="mt-0.5 h-4 w-4 rounded border-border text-primary focus:ring-primary/30"
            />
            <span className="min-w-0">
                <span className="block text-xs font-semibold text-foreground">{label}</span>
                <span className="mt-0.5 block text-[11px] leading-relaxed text-muted-foreground">{detail}</span>
            </span>
        </label>
    );
}

export default function Handoff() {
    const { taskId } = useParams<{ taskId: string }>();
    const navigate = useNavigate();
    const [receipt, setReceipt] = useState<RunReceipt | null>(null);
    const [agents, setAgents] = useState<AgentStatus[]>([]);
    const [settings, setSettings] = useState<AppSettings | null>(null);
    const [targetAgentId, setTargetAgentId] = useState('');
    const [targetModelId, setTargetModelId] = useState('');
    const [approvedSummary, setApprovedSummary] = useState('');
    const [summaryApproved, setSummaryApproved] = useState(false);
    const [userInstructions, setUserInstructions] = useState('');
    const [includeIntent, setIncludeIntent] = useState(true);
    const [includeSummary, setIncludeSummary] = useState(true);
    const [includeChangedFiles, setIncludeChangedFiles] = useState(true);
    const [includeDiffSummary, setIncludeDiffSummary] = useState(true);
    const [includeVerification, setIncludeVerification] = useState(true);
    const [includeQuestions, setIncludeQuestions] = useState(true);
    const [preview, setPreview] = useState<HandoffPreview | null>(null);
    const [loading, setLoading] = useState(true);
    const [reviewing, setReviewing] = useState(false);
    const [starting, setStarting] = useState(false);

    useEffect(() => {
        if (!taskId) return;
        let cancelled = false;
        Promise.all([api.getRunReceipt(taskId), api.listAgents(), api.getSettings()])
            .then(([sourceReceipt, catalog, currentSettings]) => {
                if (cancelled) return;
                const eligible = catalog.agents.filter(
                    (agent) => agent.agent_id !== sourceReceipt.agent.agent_id && isAgentReady(agent),
                );
                const preferred = eligible.find(
                    (agent) => agent.agent_id === currentSettings.default_agent_id,
                ) ?? eligible[0];
                const summary = sourceReceipt.result?.summary || '';
                setReceipt(sourceReceipt);
                setAgents(catalog.agents);
                setSettings(currentSettings);
                setApprovedSummary(summary);
                setIncludeSummary(Boolean(summary));
                setIncludeChangedFiles(sourceReceipt.git.changed_files.length > 0);
                setIncludeDiffSummary(Boolean(sourceReceipt.git.post_run_diff_summary));
                setIncludeQuestions(unresolvedQuestionCount(sourceReceipt) > 0);
                if (preferred) {
                    setTargetAgentId(preferred.agent_id);
                    setTargetModelId(configuredModelFor(preferred.agent_id, currentSettings));
                }
            })
            .catch((error: Error) => toast.error('Could not prepare handoff', error.message))
            .finally(() => {
                if (!cancelled) setLoading(false);
            });
        return () => {
            cancelled = true;
        };
    }, [taskId]);

    const targetAgent = useMemo(
        () => agents.find((agent) => agent.agent_id === targetAgentId) ?? null,
        [agents, targetAgentId],
    );
    const eligibleTargets = useMemo(
        () => agents.filter((agent) => agent.agent_id !== receipt?.agent.agent_id),
        [agents, receipt?.agent.agent_id],
    );
    const questionCount = receipt ? unresolvedQuestionCount(receipt) : 0;

    const invalidate = () => setPreview(null);

    const reviewPreview = async () => {
        if (!taskId || !receipt || !targetAgent || !isAgentReady(targetAgent)) return;
        if (includeSummary && (!approvedSummary.trim() || !summaryApproved)) {
            toast.error('Approve the summary', 'Review the summary text and confirm it before transfer.');
            return;
        }
        setReviewing(true);
        try {
            const prepared = await api.previewHandoff(taskId, {
                target_agent_id: targetAgent.agent_id,
                target_model_id: targetModelId.trim() || undefined,
                include_intent: includeIntent,
                include_summary: includeSummary,
                include_changed_files: includeChangedFiles,
                include_diff_summary: includeDiffSummary,
                include_verification: includeVerification,
                include_unresolved_questions: includeQuestions,
                approved_summary: includeSummary ? approvedSummary.trim() : undefined,
                summary_approved: includeSummary && summaryApproved,
                user_instructions: userInstructions.trim() || undefined,
            });
            setPreview(prepared);
        } catch (error) {
            toast.error('Could not build preview', (error as Error).message);
        } finally {
            setReviewing(false);
        }
    };

    const startReviewedHandoff = async () => {
        if (!preview || starting) return;
        setStarting(true);
        try {
            const task = await api.startHandoff(preview.id);
            navigate(`/task/${task.id}`, { replace: true });
        } catch (error) {
            toast.error('Could not start handoff', (error as Error).message);
            setStarting(false);
        }
    };

    if (loading) {
        return (
            <div className="flex flex-1 items-center justify-center gap-2 text-sm text-muted-foreground">
                <CircleNotch className="h-4 w-4 animate-spin" /> Preparing handoff…
            </div>
        );
    }

    if (!receipt) {
        return (
            <div className="flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
                <WarningCircle className="h-8 w-8 text-amber-500" />
                <p className="text-sm text-foreground">The source receipt is unavailable.</p>
                <Link to="/history" className="text-xs font-medium text-primary hover:underline">Return to history</Link>
            </div>
        );
    }

    return (
        <div className="flex-1 overflow-y-auto px-4 py-6 sm:px-8">
            <div className="mx-auto w-full max-w-5xl space-y-5">
                <header className="flex flex-wrap items-start gap-3">
                    <button
                        type="button"
                        onClick={() => navigate(`/task/${receipt.run_id}`)}
                        className="flex h-9 w-9 items-center justify-center rounded-xl border border-border bg-background text-muted-foreground transition hover:bg-accent hover:text-foreground"
                        title="Back to source run"
                    >
                        <ArrowLeft className="h-4 w-4" />
                    </button>
                    <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                            <h1 className="text-xl font-semibold tracking-tight text-foreground">Review cross-agent handoff</h1>
                            <span className="rounded-full border border-emerald-500/25 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase text-emerald-700 dark:text-emerald-300">Local only</span>
                        </div>
                        <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted-foreground">
                            Choose the exact context to carry forward. The source run and its native session remain unchanged.
                        </p>
                    </div>
                </header>

                {!preview ? (
                    <div className="grid gap-5 lg:grid-cols-[minmax(0,1.15fr)_minmax(300px,0.85fr)]">
                        <section className="space-y-5 rounded-2xl border border-border bg-card p-5 shadow-sm">
                            <div>
                                <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">Route</p>
                                <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center">
                                    <div className="flex min-w-0 flex-1 items-center gap-2 rounded-xl border border-border bg-muted/30 p-3">
                                        <AgentBadge name={receipt.agent.display_name} />
                                        <span className="truncate font-mono text-[10px] text-muted-foreground">{receipt.run_id}</span>
                                    </div>
                                    <ArrowsLeftRight className="mx-auto h-5 w-5 shrink-0 text-primary sm:mx-0" />
                                    <label className="relative min-w-0 flex-1">
                                        <span className="sr-only">Target coding agent</span>
                                        <select
                                            value={targetAgentId}
                                            onChange={(event) => {
                                                const next = event.target.value;
                                                setTargetAgentId(next);
                                                setTargetModelId(configuredModelFor(next, settings));
                                                invalidate();
                                            }}
                                            className="h-12 w-full appearance-none rounded-xl border border-border bg-background pl-3 pr-9 text-sm font-semibold text-foreground outline-none focus:ring-2 focus:ring-primary/20"
                                            aria-label="Target coding agent"
                                        >
                                            <option value="">Choose another agent</option>
                                            {eligibleTargets.map((agent) => (
                                                <option key={agent.agent_id} value={agent.agent_id} disabled={!isAgentReady(agent)}>
                                                    {agent.display_name} · {isAgentReady(agent) ? 'ready' : 'not ready'}
                                                </option>
                                            ))}
                                        </select>
                                        <CaretDown className="pointer-events-none absolute right-3 top-4 h-4 w-4 text-muted-foreground" />
                                    </label>
                                </div>
                                {targetAgent?.capabilities.model_discovery ? (
                                    <label className="mt-3 block space-y-1.5">
                                        <span className="text-xs font-medium text-foreground">Target model</span>
                                        {targetAgent.models.length ? (
                                            <select
                                                value={targetModelId}
                                                onChange={(event) => {
                                                    setTargetModelId(event.target.value);
                                                    invalidate();
                                                }}
                                                className="h-10 w-full rounded-xl border border-border bg-background px-3 text-sm text-foreground outline-none focus:ring-2 focus:ring-primary/20"
                                            >
                                                <option value="">Agent default</option>
                                                {targetAgent.models.map((model) => <option key={model.id} value={model.id}>{model.name}</option>)}
                                            </select>
                                        ) : (
                                            <input
                                                value={targetModelId}
                                                onChange={(event) => {
                                                    setTargetModelId(event.target.value);
                                                    invalidate();
                                                }}
                                                placeholder="Agent default"
                                                className="h-10 w-full rounded-xl border border-border bg-background px-3 text-sm text-foreground outline-none focus:ring-2 focus:ring-primary/20"
                                            />
                                        )}
                                    </label>
                                ) : null}
                            </div>

                            <div>
                                <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">Context to include</p>
                                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                                    <ContextChoice checked={includeIntent} onChange={(value) => { setIncludeIntent(value); invalidate(); }} label="Original intent" detail="User-authored source request, bounded and redacted." />
                                    <ContextChoice checked={includeSummary} onChange={(value) => { setIncludeSummary(value); setSummaryApproved(false); invalidate(); }} label="Approved summary" detail="Only the editable summary you explicitly approve." />
                                    <ContextChoice checked={includeChangedFiles} disabled={!receipt.git.changed_files.length} onChange={(value) => { setIncludeChangedFiles(value); invalidate(); }} label="Changed-file names" detail={`${receipt.git.changed_files.length} net path(s); never file contents.`} />
                                    <ContextChoice checked={includeDiffSummary} disabled={!receipt.git.post_run_diff_summary} onChange={(value) => { setIncludeDiffSummary(value); invalidate(); }} label="Bounded diff summary" detail="Final Git stat, with sensitive path names redacted." />
                                    <ContextChoice checked={includeVerification} onChange={(value) => { setIncludeVerification(value); invalidate(); }} label="Verification result" detail={`Explicit status: ${receipt.verification.status.replaceAll('_', ' ')}.`} />
                                    <ContextChoice checked={includeQuestions} disabled={!questionCount} onChange={(value) => { setIncludeQuestions(value); invalidate(); }} label="Unresolved questions" detail={`${questionCount} unanswered question(s); answers are never copied.`} />
                                </div>
                            </div>

                            {includeSummary ? (
                                <div className="space-y-2 rounded-xl border border-primary/20 bg-primary/[0.035] p-4">
                                    <label className="block text-xs font-semibold text-foreground" htmlFor="handoff-summary">Summary to transfer</label>
                                    <textarea
                                        id="handoff-summary"
                                        value={approvedSummary}
                                        onChange={(event) => {
                                            setApprovedSummary(event.target.value);
                                            setSummaryApproved(false);
                                            invalidate();
                                        }}
                                        rows={5}
                                        className="w-full resize-y rounded-xl border border-border bg-background px-3 py-2 text-sm leading-relaxed text-foreground outline-none focus:ring-2 focus:ring-primary/20"
                                    />
                                    <label className="flex cursor-pointer items-start gap-2 text-xs text-foreground">
                                        <input
                                            type="checkbox"
                                            checked={summaryApproved}
                                            onChange={(event) => {
                                                setSummaryApproved(event.target.checked);
                                                invalidate();
                                            }}
                                            className="mt-0.5 h-4 w-4 rounded border-border text-primary focus:ring-primary/30"
                                        />
                                        I reviewed this summary and approve it for the target agent.
                                    </label>
                                </div>
                            ) : null}

                            <label className="block space-y-2">
                                <span className="text-xs font-semibold text-foreground">Additional instructions written by you</span>
                                <textarea
                                    value={userInstructions}
                                    onChange={(event) => {
                                        setUserInstructions(event.target.value);
                                        invalidate();
                                    }}
                                    rows={4}
                                    placeholder="Optional constraints or next steps. Credential-like values will be redacted before preview storage."
                                    className="w-full resize-y rounded-xl border border-border bg-background px-3 py-2 text-sm leading-relaxed text-foreground outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-primary/20"
                                />
                            </label>
                        </section>

                        <aside className="space-y-4">
                            <div className="rounded-2xl border border-border bg-card p-5 shadow-sm">
                                <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                                    <ShieldCheck className="h-4 w-4 text-emerald-600" /> Excluded before transfer
                                </div>
                                <ul className="mt-3 space-y-2 text-xs leading-relaxed text-muted-foreground">
                                    <li>• Native session IDs and incompatible session state</li>
                                    <li>• Hidden reasoning, native metadata, and full tool output</li>
                                    <li>• Full environment dumps and credential-like values</li>
                                    <li>• File contents; only selected path names and bounded Git stat</li>
                                </ul>
                            </div>
                            <div className="rounded-2xl border border-border bg-card p-5 shadow-sm">
                                <p className="text-xs font-semibold text-foreground">Source workspace</p>
                                <p className="mt-2 break-all font-mono text-[11px] text-muted-foreground">{receipt.workspace}</p>
                                <p className="mt-3 text-xs leading-relaxed text-muted-foreground">The new run starts in this workspace as a separate task. It never resumes the source agent's native session.</p>
                            </div>
                            <button
                                type="button"
                                onClick={() => void reviewPreview()}
                                disabled={reviewing || !targetAgent || !isAgentReady(targetAgent) || (includeSummary && (!approvedSummary.trim() || !summaryApproved))}
                                className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-40"
                            >
                                {reviewing ? <CircleNotch className="h-4 w-4 animate-spin" /> : <Eye className="h-4 w-4" />}
                                Review redacted preview
                            </button>
                            {!eligibleTargets.some(isAgentReady) ? (
                                <Link to="/settings" className="block text-center text-xs font-medium text-primary hover:underline">Connect another ready agent</Link>
                            ) : null}
                        </aside>
                    </div>
                ) : (
                    <div className="grid gap-5 lg:grid-cols-[minmax(0,1.25fr)_minmax(280px,0.75fr)]">
                        <section className="overflow-hidden rounded-2xl border border-border bg-card shadow-sm">
                            <div className="flex flex-wrap items-center gap-3 border-b border-border bg-muted/30 px-5 py-4">
                                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10 text-primary"><Eye className="h-4 w-4" /></div>
                                <div className="min-w-0 flex-1">
                                    <h2 className="text-sm font-semibold text-foreground">Exact context for {preview.target_agent_name}</h2>
                                    <p className="font-mono text-[10px] text-muted-foreground">Preview {preview.id.slice(0, 12)} · single use</p>
                                </div>
                                <AgentBadge name={preview.target_agent_name} />
                            </div>
                            <pre className="max-h-[65vh] overflow-auto whitespace-pre-wrap break-words p-5 text-xs leading-relaxed text-foreground">{preview.rendered_prompt}</pre>
                        </section>

                        <aside className="space-y-4">
                            <div className="rounded-2xl border border-border bg-card p-5 shadow-sm">
                                <p className="text-xs font-semibold text-foreground">Redaction report</p>
                                {preview.redactions.length ? (
                                    <div className="mt-3 space-y-2">
                                        {preview.redactions.map((redaction) => (
                                            <div key={redaction.category} className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-2.5">
                                                <p className="text-[11px] font-semibold capitalize text-amber-800 dark:text-amber-200">{redaction.category.replaceAll('_', ' ')} · {redaction.replacements}</p>
                                                <p className="mt-1 text-[10px] leading-relaxed text-amber-800/80 dark:text-amber-200/80">{redaction.explanation}</p>
                                            </div>
                                        ))}
                                    </div>
                                ) : (
                                    <p className="mt-2 text-xs text-muted-foreground">No credential-like value required replacement.</p>
                                )}
                            </div>
                            <div className="rounded-2xl border border-border bg-card p-5 shadow-sm">
                                <p className="text-xs font-semibold text-foreground">Always excluded</p>
                                <ul className="mt-3 space-y-1.5 text-[11px] leading-relaxed text-muted-foreground">
                                    {preview.excluded_by_design.map((item) => <li key={item}>• {item}</li>)}
                                </ul>
                                <p className="mt-3 text-[10px] text-muted-foreground">Expires {new Date(preview.expires_at).toLocaleTimeString()} if not used.</p>
                            </div>
                            <div className="flex gap-2">
                                <button
                                    type="button"
                                    onClick={() => setPreview(null)}
                                    disabled={starting}
                                    className="h-11 flex-1 rounded-xl border border-border bg-background px-3 text-sm font-semibold text-foreground transition hover:bg-accent disabled:opacity-40"
                                >
                                    Edit
                                </button>
                                <button
                                    type="button"
                                    onClick={() => void startReviewedHandoff()}
                                    disabled={starting}
                                    className="inline-flex h-11 flex-[1.5] items-center justify-center gap-2 rounded-xl bg-primary px-3 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-40"
                                >
                                    {starting ? <CircleNotch className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                                    Start new run
                                </button>
                            </div>
                        </aside>
                    </div>
                )}
            </div>
        </div>
    );
}
