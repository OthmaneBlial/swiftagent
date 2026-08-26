import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import {
    ArrowLeft,
    CheckCircle,
    CircleNotch,
    PaperPlaneRight,
    Stop,
    XCircle,
} from '@phosphor-icons/react';
import { AnimatePresence, motion } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import AgentBadge from '../components/agents/AgentBadge';
import PermissionDialog, { type PermissionPayload } from '../components/execution/PermissionDialog';
import RunReceiptPanel from '../components/execution/RunReceiptPanel';
import { api, type RunReceipt, type Task, type TaskMessage, type WSEvent, ws } from '../lib/swiftagent';
import { toast } from '../lib/toast';

type TaskViewStatus =
    | 'pending'
    | 'queued'
    | 'running'
    | 'waiting_for_permission'
    | 'waiting_for_question'
    | 'completed'
    | 'failed'
    | 'cancelled';

const ACTIVE_STATUSES = new Set<TaskViewStatus>([
    'pending',
    'queued',
    'running',
    'waiting_for_permission',
    'waiting_for_question',
]);

interface PendingRequest {
    kind: 'permission' | 'question';
    requestId: string;
    payload: PermissionPayload;
}

function isActiveStatus(status: string): status is TaskViewStatus {
    return ACTIVE_STATUSES.has(status as TaskViewStatus);
}

function statusProgress(status: string): string {
    if (status === 'pending') return 'Pending...';
    if (status === 'queued') return 'Queued...';
    if (status === 'waiting_for_permission') return 'Waiting for your approval...';
    if (status === 'waiting_for_question') return 'Waiting for your input...';
    if (status === 'running') return 'Running...';
    return '';
}

function stageLabel(agentName: string, stage?: string, fallback?: string): string {
    if (fallback && fallback.trim()) return fallback;
    if (!stage) return 'Running...';
    if (stage === 'starting') return `Starting ${agentName}...`;
    return stage;
}

export default function Execution() {
    const { taskId } = useParams<{ taskId: string }>();
    const navigate = useNavigate();

    const [task, setTask] = useState<Task | null>(null);
    const [messages, setMessages] = useState<TaskMessage[]>([]);
    const [status, setStatus] = useState<TaskViewStatus>('running');
    const [progress, setProgress] = useState('Loading task...');
    const [loadingTask, setLoadingTask] = useState(true);
    const [reply, setReply] = useState('');
    const [sendingReply, setSendingReply] = useState(false);
    const [pendingRequest, setPendingRequest] = useState<PendingRequest | null>(null);
    const [agentName, setAgentName] = useState('Coding agent');
    const [receipt, setReceipt] = useState<RunReceipt | null>(null);

    const eventKeysRef = useRef<Set<string>>(new Set());
    const scrollRef = useRef<HTMLDivElement>(null);
    const followUpSessionRef = useRef<string | null>(null);
    const followUpTimeoutRef = useRef<number | null>(null);
    const replyTextareaRef = useRef<HTMLTextAreaElement>(null);

    useEffect(() => {
        if (!taskId) {
            return;
        }

        let cancelled = false;
        const loadTask = async () => {
            setLoadingTask(true);
            setPendingRequest(null);
            eventKeysRef.current.clear();

            try {
                const [loadedTask, catalog, loadedReceipt] = await Promise.all([
                    api.getTask(taskId),
                    api.listAgents().catch(() => null),
                    api.getRunReceipt(taskId).catch(() => null),
                ]);
                if (cancelled) return;
                if (!loadedTask) {
                    throw new Error('Task not found');
                }

                setTask(loadedTask);
                setAgentName(
                    catalog?.agents.find((agent) => agent.agent_id === loadedTask.agent_id)?.display_name ||
                        loadedTask.agent_id,
                );
                setMessages(loadedTask.messages ?? []);
                setStatus(loadedTask.status as TaskViewStatus);
                setProgress(statusProgress(loadedTask.status));
                setReceipt(loadedReceipt);
            } catch (error) {
                if (cancelled) return;
                setStatus('failed');
                setProgress('Failed to load task');
                toast.error('Failed to load task', (error as Error).message);
            } finally {
                if (!cancelled) {
                    setLoadingTask(false);
                }
            }
        };

        void loadTask();

        return () => {
            cancelled = true;
        };
    }, [taskId]);

    useEffect(() => {
        const markSeen = (event: WSEvent) => {
            const key = `${event.timestamp}|${event.type}|${event.task_id ?? ''}|${JSON.stringify(event.payload)}`;
            if (eventKeysRef.current.has(key)) {
                return true;
            }
            eventKeysRef.current.add(key);
            if (eventKeysRef.current.size > 500) {
                const oldest = eventKeysRef.current.values().next().value as string | undefined;
                if (oldest) eventKeysRef.current.delete(oldest);
            }
            return false;
        };

        const isCurrentTask = (event: WSEvent) => event.task_id === taskId;

        const unsubs: Array<() => void> = [];

        unsubs.push(
            ws.on('task:progress', (event) => {
                if (!isCurrentTask(event) || markSeen(event)) return;
                const payload = event.payload as { stage?: string; message?: string };
                if (payload.stage === 'starting') {
                    setStatus('running');
                }
                setProgress(stageLabel(agentName, payload.stage, payload.message));
            })
        );

        unsubs.push(
            ws.on('task:message', (event) => {
                if (!isCurrentTask(event) || markSeen(event)) return;
                const payload = event.payload as { role?: string; content?: string };
                const role = payload.role || 'assistant';
                const content = payload.content || '';
                setMessages((prev) => [
                    ...prev,
                    {
                        id: `${event.timestamp}-${prev.length}`,
                        role,
                        content,
                        timestamp: event.timestamp,
                    },
                ]);
                if (role === 'assistant') {
                    setProgress(`${agentName} is responding...`);
                }
                setStatus((prev) => (prev === 'completed' || prev === 'failed' || prev === 'cancelled' ? prev : 'running'));
                setSendingReply(false);
            })
        );

        unsubs.push(
            ws.on('tool:use', (event) => {
                if (!isCurrentTask(event) || markSeen(event)) return;
                const payload = event.payload as { name?: string };
                setProgress(payload.name ? `Using tool: ${payload.name}` : 'Using tool...');
            })
        );

        unsubs.push(
            ws.on('tool:result', (event) => {
                if (!isCurrentTask(event) || markSeen(event)) return;
                const payload = event.payload as { is_error?: boolean };
                if (payload.is_error) {
                    setProgress('Tool returned an error');
                }
            })
        );

        unsubs.push(
            ws.on('task:error', (event) => {
                if (!isCurrentTask(event) || markSeen(event)) return;
                const payload = event.payload as { error?: string };
                setStatus('failed');
                setProgress('');
                setSendingReply(false);
                if (followUpTimeoutRef.current) {
                    window.clearTimeout(followUpTimeoutRef.current);
                    followUpTimeoutRef.current = null;
                }
                setPendingRequest(null);
                toast.error('Task error', payload.error || 'Unknown error');
            })
        );

        unsubs.push(
            ws.on('task:complete', (event) => {
                if (!isCurrentTask(event) || markSeen(event)) return;
                const payload = event.payload as {
                    status?: TaskViewStatus;
                    error?: string;
                    session_id?: string | null;
                };
                const nextStatus = payload.status || 'completed';
                setStatus(nextStatus);
                setProgress('');
                setSendingReply(false);
                if (followUpTimeoutRef.current) {
                    window.clearTimeout(followUpTimeoutRef.current);
                    followUpTimeoutRef.current = null;
                }
                setPendingRequest(null);
                setTask((prev) => {
                    if (!prev) return prev;
                    return {
                        ...prev,
                        status: nextStatus,
                        session_id: payload.session_id ?? prev.session_id,
                    };
                });
                if (payload.error && nextStatus !== 'cancelled') {
                    toast.error('Task failed', payload.error);
                }
                window.setTimeout(() => {
                    if (taskId) {
                        void api.getRunReceipt(taskId).then(setReceipt).catch(() => undefined);
                    }
                }, 150);
            })
        );

        const refreshTerminalReceipt = (event: WSEvent) => {
            if (!taskId || event.run_id !== taskId) return;
            void api.getRunReceipt(taskId).then(setReceipt).catch(() => undefined);
        };
        unsubs.push(ws.on('run.completed', refreshTerminalReceipt));
        unsubs.push(ws.on('run.failed', refreshTerminalReceipt));

        unsubs.push(
            ws.on('permission:request', (event) => {
                if (!isCurrentTask(event) || markSeen(event)) return;
                const payload = event.payload as Record<string, unknown>;
                const requestId = String(payload.id ?? payload.request_id ?? '');
                if (!requestId) return;
                setStatus('waiting_for_permission');
                setPendingRequest({
                    kind: 'permission',
                    requestId,
                    payload: {
                        id: requestId,
                        task_id: taskId,
                        description: String(payload.description ?? ''),
                        tool_name: payload.tool_name ? String(payload.tool_name) : undefined,
                        file_path: payload.file_path ? String(payload.file_path) : undefined,
                    },
                });
            })
        );

        unsubs.push(
            ws.on('question:request', (event) => {
                if (!isCurrentTask(event) || markSeen(event)) return;
                const payload = event.payload as Record<string, unknown>;
                const requestId = String(payload.id ?? payload.request_id ?? '');
                if (!requestId) return;
                setStatus('waiting_for_question');
                setPendingRequest({
                    kind: 'question',
                    requestId,
                    payload: {
                        id: requestId,
                        task_id: taskId,
                        question: String(payload.question ?? payload.description ?? ''),
                        description: String(payload.description ?? 'Agent requested additional input.'),
                    },
                });
            })
        );

        unsubs.push(
            ws.on('task:started', (event) => {
                const payload = event.payload as { id?: string; session_id?: string | null };
                if (!payload.id || !followUpSessionRef.current) return;
                if (payload.session_id !== followUpSessionRef.current) return;
                if (payload.id === taskId) return;
                followUpSessionRef.current = null;
                setSendingReply(false);
                if (followUpTimeoutRef.current) {
                    window.clearTimeout(followUpTimeoutRef.current);
                    followUpTimeoutRef.current = null;
                }
                navigate(`/task/${payload.id}`, { replace: true });
            })
        );

        return () => {
            unsubs.forEach((unsub) => unsub());
            if (followUpTimeoutRef.current) {
                window.clearTimeout(followUpTimeoutRef.current);
                followUpTimeoutRef.current = null;
            }
        };
    }, [agentName, navigate, taskId]);

    useEffect(() => {
        scrollRef.current?.scrollTo({
            top: scrollRef.current.scrollHeight,
            behavior: 'smooth',
        });
    }, [messages, pendingRequest, progress]);

    const handleCancel = () => {
        if (!taskId) return;
        setProgress('Cancelling...');
        ws.cancelTask(taskId);
    };

    const handleSendReply = () => {
        const text = reply.trim();
        const sessionId = task?.session_id;
        if (!text || !sessionId || sendingReply) return;

        setSendingReply(true);
        setReply('');
        setStatus('running');
        setProgress('Starting follow-up...');
        followUpSessionRef.current = sessionId;
        ws.resumeSession(sessionId, text, task?.agent_id || task?.config.agent_id);
        if (followUpTimeoutRef.current) {
            window.clearTimeout(followUpTimeoutRef.current);
        }
        followUpTimeoutRef.current = window.setTimeout(() => {
            setSendingReply(false);
            followUpSessionRef.current = null;
            setProgress('');
            toast.error('Follow-up timed out', 'No new task was started for the resumed session.');
        }, 15000);
    };

    const handlePermissionResponse = (approved: boolean, answer?: string) => {
        if (!pendingRequest) return;
        if (pendingRequest.kind === 'question') {
            ws.respondToQuestion(pendingRequest.requestId, approved ? answer || '' : '');
        } else {
            ws.respondToPermission(pendingRequest.requestId, approved);
        }
        setPendingRequest(null);
        setStatus('running');
        setProgress(`Waiting for ${agentName}...`);
    };

    const isRunning = isActiveStatus(status);
    const isCompleted = status === 'completed';
    const isFailed = status === 'failed' || status === 'cancelled';
    const canReply = Boolean(
        task?.session_id && task.capability_snapshot?.session_resume !== false,
    ) && !isRunning && !sendingReply;
    const showTypingIndicator = isRunning && !pendingRequest && !loadingTask;

    const focusResumeComposer = () => {
        if (!canReply) {
            toast.error('Resume unavailable', 'This run has no resumable native session.');
            return;
        }
        replyTextareaRef.current?.focus();
        replyTextareaRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    };

    const prepareHandoff = () => {
        if (!taskId) return;
        navigate(`/handoff/${encodeURIComponent(taskId)}`);
    };

    return (
        <div className="min-w-0 flex-1 flex flex-col h-screen">
            <header className="h-14 border-b border-border flex items-center px-4 gap-3 shrink-0">
                <button
                    onClick={() => navigate('/')}
                    className="w-8 h-8 rounded-lg flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-accent/50 transition-colors"
                    title="Back to tasks"
                >
                    <ArrowLeft weight="bold" className="w-4 h-4" />
                </button>

                <div className="flex-1 min-w-0">
                    <div className="flex min-w-0 items-center gap-2">
                        <p className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">
                            {task?.config.prompt || 'Task execution'}
                        </p>
                        <AgentBadge name={agentName} className="hidden shrink-0 sm:inline-flex" />
                        {task?.capability_snapshot?.effective_sandbox_mode ? (
                            <span className="hidden shrink-0 rounded-full border border-border px-2 py-1 text-[10px] text-muted-foreground md:inline-flex">
                                {String(task.capability_snapshot.effective_sandbox_mode)} safety
                            </span>
                        ) : null}
                    </div>
                    <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                        {isRunning ? (
                            <>
                                <CircleNotch weight="bold" className="w-3 h-3 animate-spin" />
                                {progress || statusProgress(status)}
                            </>
                        ) : null}
                        {isCompleted ? (
                            <>
                                <CheckCircle weight="fill" className="w-3 h-3 text-green-500" />
                                Completed
                            </>
                        ) : null}
                        {isFailed ? (
                            <>
                                <XCircle weight="fill" className="w-3 h-3 text-red-500" />
                                {status === 'cancelled' ? 'Cancelled' : 'Failed'}
                            </>
                        ) : null}
                    </p>
                </div>

                {isRunning ? (
                    <button
                        onClick={handleCancel}
                        className="h-8 px-3 rounded-lg border border-destructive/30 text-destructive text-xs font-medium flex items-center gap-1.5 hover:bg-destructive/10 transition-colors"
                    >
                        <Stop weight="bold" className="w-3.5 h-3.5" />
                        Stop
                    </button>
                ) : null}
            </header>

            <div ref={scrollRef} className="min-w-0 flex-1 overflow-y-auto overflow-x-hidden px-4 py-4 space-y-4">
                {loadingTask ? (
                    <div className="flex items-center justify-center py-12 text-sm text-muted-foreground gap-2">
                        <CircleNotch className="w-4 h-4 animate-spin" />
                        Loading task...
                    </div>
                ) : null}

                <AnimatePresence>
                    {messages.map((msg, index) => (
                        <motion.div
                            key={msg.id || `${msg.timestamp}-${index}`}
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.2 }}
                            className={`min-w-0 max-w-3xl ${msg.role === 'user' ? 'ml-auto' : 'mr-auto'}`}
                        >
                            <div
                                className={`min-w-0 overflow-hidden rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                                    msg.role === 'user'
                                        ? 'bg-primary text-primary-foreground'
                                        : msg.role === 'tool'
                                            ? 'bg-amber-500/10 text-amber-900 dark:text-amber-200 border border-amber-500/20'
                                            : 'bg-muted text-foreground'
                                }`}
                            >
                                {msg.role === 'assistant' ? (
                                    <div className="prose prose-sm max-w-none break-words dark:prose-invert [&_code]:break-all [&_pre]:max-w-full [&_pre]:overflow-x-auto">
                                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                            {msg.content}
                                        </ReactMarkdown>
                                    </div>
                                ) : (
                                    <p className="whitespace-pre-wrap break-words">{msg.content}</p>
                                )}
                            </div>
                        </motion.div>
                    ))}
                </AnimatePresence>

                {showTypingIndicator ? (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="max-w-3xl mr-auto">
                        <div className="rounded-2xl px-4 py-3 bg-muted text-muted-foreground text-sm flex items-center gap-2">
                            <CircleNotch weight="bold" className="w-4 h-4 animate-spin" />
                            <span>{progress || 'Running...'}</span>
                        </div>
                    </motion.div>
                ) : null}

                {receipt ? (
                    <RunReceiptPanel
                        receipt={receipt}
                        onReceiptChange={setReceipt}
                        onResume={focusResumeComposer}
                        onHandoff={prepareHandoff}
                    />
                ) : null}
            </div>

            <div className="border-t border-border px-4 py-3 shrink-0">
                <div className="max-w-3xl mx-auto flex items-end gap-2">
                    <textarea
                        ref={replyTextareaRef}
                        value={reply}
                        onChange={(event) => setReply(event.target.value)}
                        onKeyDown={(event) => {
                            if (event.key === 'Enter' && !event.shiftKey) {
                                event.preventDefault();
                                handleSendReply();
                            }
                        }}
                        placeholder={
                            canReply
                                ? 'Send a follow-up message...'
                                : !task?.session_id
                                    ? 'Session id not available yet'
                                    : isRunning
                                        ? 'Wait for task completion...'
                                        : 'Type a message...'
                        }
                        disabled={!canReply}
                        rows={1}
                        className="flex-1 resize-none rounded-xl border border-border bg-background px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary disabled:opacity-50 disabled:cursor-not-allowed"
                        style={{ minHeight: '42px', maxHeight: '120px' }}
                    />
                    <button
                        onClick={handleSendReply}
                        disabled={!canReply || !reply.trim()}
                        className="w-10 h-10 rounded-xl bg-primary text-primary-foreground flex items-center justify-center hover:bg-primary/90 transition-colors disabled:opacity-30 disabled:cursor-not-allowed shrink-0"
                        title="Send follow-up"
                    >
                        {sendingReply ? (
                            <CircleNotch weight="bold" className="w-4 h-4 animate-spin" />
                        ) : (
                            <PaperPlaneRight weight="fill" className="w-4 h-4" />
                        )}
                    </button>
                </div>
            </div>

            {pendingRequest ? (
                <PermissionDialog payload={pendingRequest.payload} onRespond={handlePermissionResponse} />
            ) : null}
        </div>
    );
}
