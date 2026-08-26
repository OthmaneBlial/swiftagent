import { useEffect, useState } from 'react';
import {
    ArrowCounterClockwise,
    ArrowsLeftRight,
    CaretDown,
    DownloadSimple,
    Flask,
    GitDiff,
    Receipt,
    ShieldCheck,
} from '@phosphor-icons/react';
import { api, type RunReceipt, type VerificationStatus } from '../../lib/swiftagent';
import { toast } from '../../lib/toast';
import { Link } from 'react-router';

interface RunReceiptPanelProps {
    receipt: RunReceipt;
    onReceiptChange: (receipt: RunReceipt) => void;
    onResume: () => void;
    onHandoff: () => void;
}

function durationLabel(durationMs: number | null): string {
    if (durationMs === null) return 'In progress';
    if (durationMs < 1_000) return `${durationMs} ms`;
    const seconds = Math.round(durationMs / 1_000);
    if (seconds < 60) return `${seconds}s`;
    return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

function statusLabel(value: string): string {
    return value.replaceAll('_', ' ');
}

function evidenceTone(status: VerificationStatus): string {
    if (status === 'passed') return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300';
    if (status === 'failed') return 'border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300';
    return 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300';
}

export default function RunReceiptPanel({
    receipt,
    onReceiptChange,
    onResume,
    onHandoff,
}: RunReceiptPanelProps) {
    const [verificationStatus, setVerificationStatus] = useState<VerificationStatus>(receipt.verification.status);
    const [verificationSummary, setVerificationSummary] = useState(receipt.verification.summary || '');
    const [verificationCommand, setVerificationCommand] = useState(receipt.verification.command || '');
    const [savingVerification, setSavingVerification] = useState(false);

    useEffect(() => {
        setVerificationStatus(receipt.verification.status);
        setVerificationSummary(receipt.verification.summary || '');
        setVerificationCommand(receipt.verification.command || '');
    }, [receipt.verification]);

    const saveVerification = async () => {
        if (verificationStatus !== 'not_run' && !verificationSummary.trim()) {
            toast.error('Evidence required', 'Explain what passed or failed. Agent prose is not test evidence.');
            return;
        }
        setSavingVerification(true);
        try {
            const updated = await api.updateRunVerification(receipt.run_id, {
                status: verificationStatus,
                summary: verificationSummary.trim(),
                command: verificationCommand.trim(),
            });
            onReceiptChange(updated);
            toast.success('Verification saved', `Receipt now reports ${statusLabel(verificationStatus)}.`);
        } catch (error) {
            toast.error('Could not save verification', (error as Error).message);
        } finally {
            setSavingVerification(false);
        }
    };

    const download = async (format: 'json' | 'markdown') => {
        try {
            await api.downloadRunReceipt(receipt.run_id, format);
        } catch (error) {
            toast.error('Could not export receipt', (error as Error).message);
        }
    };

    const native = receipt.safety.native;
    const isolation = receipt.safety.swiftagent_isolation;
    const resultText = receipt.result?.summary || receipt.result?.error || 'No terminal result yet.';

    return (
        <section className="mx-auto min-w-0 w-full max-w-4xl overflow-hidden rounded-2xl border border-border bg-card shadow-sm">
            <div className="flex flex-wrap items-center gap-3 border-b border-border bg-muted/30 px-5 py-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
                    <Receipt weight="duotone" className="h-5 w-5" />
                </div>
                <div className="min-w-0 flex-1">
                    <h2 className="text-sm font-semibold text-foreground">Local Run Receipt</h2>
                    <p className="truncate font-mono text-[11px] text-muted-foreground">{receipt.run_id}</p>
                    {receipt.handoff_source_run_id ? (
                        <Link
                            to={`/task/${receipt.handoff_source_run_id}`}
                            className="mt-1 inline-flex text-[11px] font-medium text-primary hover:underline"
                        >
                            Handoff from run {receipt.handoff_source_run_id}
                        </Link>
                    ) : null}
                </div>
                <span className="rounded-full border border-border bg-background px-2.5 py-1 text-[11px] font-medium capitalize text-foreground">
                    {statusLabel(receipt.status)}
                </span>
                <button
                    type="button"
                    onClick={() => void download('json')}
                    className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border bg-background px-2.5 text-xs text-foreground transition-colors hover:bg-accent"
                >
                    <DownloadSimple className="h-3.5 w-3.5" /> JSON
                </button>
                <button
                    type="button"
                    onClick={() => void download('markdown')}
                    className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border bg-background px-2.5 text-xs text-foreground transition-colors hover:bg-accent"
                >
                    <DownloadSimple className="h-3.5 w-3.5" /> Markdown
                </button>
            </div>

            <div className="min-w-0 space-y-5 p-5">
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    {[
                        ['Agent', receipt.agent.display_name],
                        ['Adapter', `${receipt.agent.adapter_id} v${receipt.agent.adapter_version}`],
                        ['Protocol', receipt.agent.protocol],
                        ['Model', receipt.agent.model || 'Not reported'],
                        ['Duration', durationLabel(receipt.duration_ms)],
                        ['Workspace', receipt.workspace],
                        ['Native session', receipt.agent.native_session_id || 'Not reported'],
                        ['Started', new Date(receipt.started_at).toLocaleString()],
                        ['Completed', receipt.completed_at ? new Date(receipt.completed_at).toLocaleString() : 'Not complete'],
                    ].map(([label, value]) => (
                        <div key={label} className="min-w-0 rounded-xl border border-border bg-background p-3">
                            <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{label}</p>
                            <p className="mt-1 break-words text-xs font-medium text-foreground">{value}</p>
                        </div>
                    ))}
                </div>

                <div className="min-w-0 rounded-xl border border-border bg-background p-4">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Intent</p>
                    <p className="mt-2 whitespace-pre-wrap break-words text-sm text-foreground">{receipt.intent}</p>
                    <div className="mt-4 border-t border-border pt-4">
                        <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Result</p>
                        <p className="mt-2 whitespace-pre-wrap break-words text-sm text-foreground">{resultText}</p>
                    </div>
                </div>

                <div>
                    <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
                        <ShieldCheck className="h-4 w-4 text-primary" /> Safety layers
                    </div>
                    <div className="grid gap-3 md:grid-cols-2">
                        <div className="min-w-0 rounded-xl border border-border bg-background p-4">
                            <p className="text-xs font-semibold text-foreground">Native agent controls</p>
                            <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                                {native.supported ? 'Exposed' : 'Not exposed'} · mode {native.mode || 'unknown'}
                                {native.permission_policy ? ` · permissions ${native.permission_policy}` : ''}
                            </p>
                            {native.notice ? <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">{native.notice}</p> : null}
                        </div>
                        <div className="min-w-0 rounded-xl border border-border bg-background p-4">
                            <p className="text-xs font-semibold text-foreground">SwiftAgent isolation</p>
                            <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                                Requested {isolation.mode || 'unknown'} · {isolation.active === true ? 'active' : isolation.active === false ? 'not active' : 'unverified'}
                            </p>
                            {isolation.notice ? <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">{isolation.notice}</p> : null}
                        </div>
                    </div>
                    <p className="mt-2 rounded-lg bg-muted px-3 py-2 text-xs text-muted-foreground">{receipt.safety.effective_summary}</p>
                </div>

                <div className="grid gap-4 lg:grid-cols-2">
                    <div className="min-w-0 rounded-xl border border-border bg-background p-4">
                        <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                            <GitDiff className="h-4 w-4 text-primary" /> Git impact
                        </div>
                        {receipt.git.available ? (
                            <div className="mt-3 space-y-2 text-xs text-muted-foreground">
                                <p>Baseline <span className="font-mono text-foreground">{receipt.git.baseline_sha?.slice(0, 10) || 'unborn'}</span> · initial tree {receipt.git.initial_dirty ? 'dirty' : 'clean'}</p>
                                {receipt.git.initial_changed_files.length ? (
                                    <details className="rounded-lg border border-border bg-muted/40 px-2 py-1.5">
                                        <summary className="cursor-pointer text-[11px] text-foreground">
                                            Initial dirty paths ({receipt.git.initial_changed_files.length})
                                        </summary>
                                        <ul className="mt-2 max-h-24 space-y-1 overflow-auto font-mono text-[10px] text-foreground">
                                            {receipt.git.initial_changed_files.map((file) => <li key={file}>{file}</li>)}
                                        </ul>
                                    </details>
                                ) : null}
                                <p>{receipt.git.changed_files.length} file(s) changed during this run</p>
                                {receipt.git.changed_files.length ? (
                                    <ul className="max-h-28 space-y-1 overflow-auto rounded-lg bg-muted p-2 font-mono text-[11px] text-foreground">
                                        {receipt.git.changed_files.map((file) => <li key={file}>{file}</li>)}
                                    </ul>
                                ) : null}
                                <p className="whitespace-pre-wrap">{receipt.git.post_run_diff_summary || 'No post-run diff detected.'}</p>
                            </div>
                        ) : (
                            <p className="mt-3 text-xs text-muted-foreground">{receipt.git.error || 'Git evidence unavailable.'}</p>
                        )}
                    </div>

                    <div className="min-w-0 rounded-xl border border-border bg-background p-4">
                        <div className="flex items-center justify-between gap-2">
                            <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                                <Flask className="h-4 w-4 text-primary" /> Verification
                            </div>
                            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase ${evidenceTone(receipt.verification.status)}`}>
                                {statusLabel(receipt.verification.status)}
                            </span>
                        </div>
                        <div className="mt-3 space-y-2">
                            <select
                                value={verificationStatus}
                                onChange={(event) => setVerificationStatus(event.target.value as VerificationStatus)}
                                className="h-9 w-full rounded-lg border border-border bg-background px-2.5 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/30"
                            >
                                <option value="not_run">Not run</option>
                                <option value="passed">Passed</option>
                                <option value="failed">Failed</option>
                            </select>
                            <input
                                value={verificationCommand}
                                onChange={(event) => setVerificationCommand(event.target.value)}
                                placeholder="Command (optional), e.g. make test"
                                className="h-9 w-full rounded-lg border border-border bg-background px-2.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30"
                            />
                            <textarea
                                value={verificationSummary}
                                onChange={(event) => setVerificationSummary(event.target.value)}
                                placeholder="Evidence summary — required for passed or failed"
                                rows={2}
                                className="w-full resize-none rounded-lg border border-border bg-background px-2.5 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30"
                            />
                            <button
                                type="button"
                                onClick={() => void saveVerification()}
                                disabled={savingVerification}
                                className="h-8 rounded-lg bg-primary px-3 text-xs font-semibold text-primary-foreground transition-opacity disabled:opacity-50"
                            >
                                {savingVerification ? 'Saving…' : 'Save evidence'}
                            </button>
                        </div>
                    </div>
                </div>

                <div className="grid gap-3 md:grid-cols-3">
                    <div className="min-w-0 rounded-xl border border-border bg-background p-4">
                        <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Interactions</p>
                        <p className="mt-2 text-xs text-foreground">
                            {receipt.interactions.tools_started} tools · {receipt.interactions.approvals_requested} approvals · {receipt.interactions.approvals_denied} denied · {receipt.interactions.questions_requested} questions
                        </p>
                    </div>
                    <div className="min-w-0 rounded-xl border border-border bg-background p-4">
                        <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Latest plan state</p>
                        <pre className="mt-2 max-h-28 overflow-auto whitespace-pre-wrap text-[10px] text-foreground">
                            {receipt.interactions.latest_plan ? JSON.stringify(receipt.interactions.latest_plan, null, 2) : 'Not reported'}
                        </pre>
                    </div>
                    <div className="min-w-0 rounded-xl border border-border bg-background p-4">
                        <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Latest usage</p>
                        <pre className="mt-2 max-h-28 overflow-auto whitespace-pre-wrap text-[10px] text-foreground">
                            {receipt.interactions.latest_usage ? JSON.stringify(receipt.interactions.latest_usage, null, 2) : 'Not reported'}
                        </pre>
                    </div>
                </div>

                <div className="min-w-0 rounded-xl border border-border bg-background p-4">
                    <p className="text-sm font-semibold text-foreground">Normalized activity ledger</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                        {receipt.ledger.length < receipt.ledger_total ? `${receipt.ledger.length} shown of ` : ''}{receipt.ledger_total} persisted event(s) · {receipt.interactions.tools_started} tools · {receipt.interactions.approvals_requested} approvals ({receipt.interactions.approvals_denied} denied) · {receipt.interactions.questions_requested} questions
                    </p>
                    <div className="mt-3 max-h-96 space-y-2 overflow-auto pr-1">
                        {receipt.ledger.length ? receipt.ledger.map((entry) => (
                            <details key={entry.sequence} className="group min-w-0 rounded-lg border border-border bg-muted/30">
                                <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-xs text-foreground">
                                    <CaretDown className="h-3 w-3 shrink-0 -rotate-90 transition-transform group-open:rotate-0" />
                                    <span className="shrink-0 font-mono text-[10px] text-muted-foreground">#{entry.sequence}</span>
                                    <span className="min-w-0 flex-1 truncate">{entry.summary}</span>
                                    <span className="shrink-0 font-mono text-[10px] text-muted-foreground">{entry.type}</span>
                                </summary>
                                <div className="min-w-0 space-y-2 border-t border-border px-3 py-3">
                                    <p className="text-[11px] text-muted-foreground">{new Date(entry.timestamp).toLocaleString()} · native {entry.native_event_type || 'not reported'}</p>
                                    <div>
                                        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Normalized payload</p>
                                        <pre className="max-h-52 max-w-full overflow-auto rounded-md bg-background p-2 text-[10px] text-foreground">{JSON.stringify(entry.payload, null, 2)}</pre>
                                    </div>
                                    <div>
                                        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Native details</p>
                                        <pre className="max-h-52 max-w-full overflow-auto rounded-md bg-background p-2 text-[10px] text-foreground">{JSON.stringify(entry.native_metadata, null, 2)}</pre>
                                    </div>
                                </div>
                            </details>
                        )) : (
                            <p className="rounded-lg bg-muted p-3 text-xs text-muted-foreground">No normalized events persisted yet.</p>
                        )}
                    </div>
                </div>

                <div className="flex flex-wrap gap-2 border-t border-border pt-4">
                    <button
                        type="button"
                        onClick={onResume}
                        disabled={!receipt.actions.resume_same_agent}
                        className="inline-flex h-9 items-center gap-2 rounded-lg border border-border bg-background px-3 text-xs font-semibold text-foreground transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-40"
                    >
                        <ArrowCounterClockwise className="h-4 w-4" /> Resume with {receipt.agent.display_name}
                    </button>
                    <button
                        type="button"
                        onClick={onHandoff}
                        disabled={!receipt.actions.create_handoff}
                        className="inline-flex h-9 items-center gap-2 rounded-lg border border-border bg-background px-3 text-xs font-semibold text-foreground transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-40"
                    >
                        <ArrowsLeftRight className="h-4 w-4" /> Continue with another agent
                    </button>
                </div>
            </div>
        </section>
    );
}
