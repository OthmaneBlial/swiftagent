import {
    ArrowSquareOut,
    Check,
    CircleNotch,
    Code,
    PlugsConnected,
    ShieldCheck,
    WarningCircle,
    Wrench,
} from '@phosphor-icons/react';
import type { AgentStatus } from '../../lib/swiftagent';

interface AgentCardProps {
    agent: AgentStatus;
    selected?: boolean;
    onSelect?: () => void;
}

const capabilityLabels: Array<[keyof AgentStatus['capabilities'], string]> = [
    ['structured_streaming', 'Live stream'],
    ['tool_events', 'Tool events'],
    ['session_resume', 'Resume'],
    ['approvals', 'Approvals'],
    ['questions', 'Questions'],
    ['plan_updates', 'Plans'],
    ['usage', 'Usage'],
];

function readiness(agent: AgentStatus) {
    if (!agent.installed) {
        return { label: 'Not installed', tone: 'text-muted-foreground', Icon: PlugsConnected };
    }
    if (agent.compatible === false) {
        return { label: 'Needs attention', tone: 'text-amber-600 dark:text-amber-300', Icon: WarningCircle };
    }
    return { label: 'Detected', tone: 'text-emerald-700 dark:text-emerald-300', Icon: Check };
}

export default function AgentCard({ agent, selected = false, onSelect }: AgentCardProps) {
    const state = readiness(agent);
    const StateIcon = state.Icon;
    const enabledCapabilities = capabilityLabels.filter(([key]) => Boolean(agent.capabilities[key]));

    return (
        <article
            className={`rounded-2xl border bg-card p-4 transition-colors ${
                selected ? 'border-primary/50 shadow-sm' : 'border-border'
            }`}
        >
            <div className="flex items-start gap-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-border bg-muted/60">
                    <Code weight="bold" className="h-5 w-5 text-foreground" />
                </div>
                <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-sm font-semibold text-foreground">{agent.display_name}</h3>
                        <span className={`inline-flex items-center gap-1 text-[11px] font-medium ${state.tone}`}>
                            <StateIcon weight="bold" className="h-3 w-3" />
                            {state.label}
                        </span>
                    </div>
                    <p className="mt-0.5 truncate text-xs text-muted-foreground">
                        {agent.version || agent.executable_path || agent.protocol}
                    </p>
                </div>
                {onSelect ? (
                    <button
                        type="button"
                        onClick={onSelect}
                        disabled={!agent.installed || agent.compatible === false || selected}
                        className="h-8 rounded-lg border border-border px-3 text-xs font-medium text-foreground hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
                    >
                        {selected ? 'Default' : 'Set default'}
                    </button>
                ) : null}
            </div>

            <div className="mt-4 flex flex-wrap gap-1.5">
                {enabledCapabilities.length ? (
                    enabledCapabilities.map(([key, label]) => (
                        <span key={key} className="rounded-md bg-muted px-2 py-1 text-[10px] font-medium text-muted-foreground">
                            {label}
                        </span>
                    ))
                ) : (
                    <span className="text-[11px] text-muted-foreground">Text output and cancellation</span>
                )}
            </div>

            <div className="mt-4 grid gap-2 text-[11px] text-muted-foreground sm:grid-cols-3">
                <span className="inline-flex items-center gap-1.5">
                    <Wrench className="h-3.5 w-3.5" /> {agent.protocol}
                </span>
                <span className="inline-flex items-center gap-1.5">
                    <ShieldCheck className="h-3.5 w-3.5" />
                    {agent.capabilities.native_sandbox ? 'Native safety' : `${agent.capabilities.external_sandbox} isolation`}
                </span>
                <span className="inline-flex items-center gap-1.5">
                    {agent.auth_status === 'ready' ? <Check className="h-3.5 w-3.5" /> : <CircleNotch className="h-3.5 w-3.5" />}
                    Auth {agent.auth_status.replace('_', ' ')}
                </span>
            </div>

            {agent.detail ? (
                <p className="mt-3 border-t border-border pt-3 text-[11px] leading-relaxed text-muted-foreground">
                    {agent.detail}
                </p>
            ) : null}

            {!agent.installed && agent.install_url ? (
                <a
                    href={agent.install_url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
                >
                    Official setup <ArrowSquareOut className="h-3 w-3" />
                </a>
            ) : null}
        </article>
    );
}
