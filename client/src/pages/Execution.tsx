import { useEffect, useState, useRef } from 'react';
import { useParams, useNavigate } from 'react-router';
import {
    ArrowLeft,
    CircleNotch,
    CheckCircle,
    XCircle,
    Stop,
    PaperPlaneRight,
} from '@phosphor-icons/react';
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ws, api, type Task, type WSEvent, type TaskMessage } from '../lib/swiftagent';

export default function Execution() {
    const { taskId } = useParams<{ taskId: string }>();
    const navigate = useNavigate();
    const [task, setTask] = useState<Task | null>(null);
    const [messages, setMessages] = useState<TaskMessage[]>([]);
    const [status, setStatus] = useState('running');
    const [progress, setProgress] = useState('Starting...');
    const [reply, setReply] = useState('');
    const [sending, setSending] = useState(false);
    const scrollRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLTextAreaElement>(null);

    // Load task data
    useEffect(() => {
        if (!taskId) return;
        api.getTask(taskId).then((t) => {
            setTask(t);
            setMessages(t.messages);
            setStatus(t.status);
            if (t.status === 'completed' || t.status === 'failed' || t.status === 'cancelled') {
                setProgress('');
            }
        });
    }, [taskId]);

    // Subscribe to real-time updates
    useEffect(() => {
        const unsubs: (() => void)[] = [];

        unsubs.push(
            ws.on('task:message', (e: WSEvent) => {
                if (e.task_id !== taskId) return;
                const payload = e.payload as { role: string; content: string };
                setMessages((prev) => [
                    ...prev,
                    {
                        id: Date.now().toString(),
                        role: payload.role,
                        content: payload.content,
                        timestamp: e.timestamp,
                    },
                ]);
                setProgress('Agent is responding...');
                setSending(false);
            })
        );

        unsubs.push(
            ws.on('task:progress', (e: WSEvent) => {
                if (e.task_id !== taskId) return;
                const payload = e.payload as { stage: string; message?: string };
                setProgress(payload.message || payload.stage);
            })
        );

        unsubs.push(
            ws.on('task:complete', (e: WSEvent) => {
                if (e.task_id !== taskId) return;
                const payload = e.payload as { status: string };
                setStatus(payload.status);
                setProgress('');
                setSending(false);
            })
        );

        unsubs.push(
            ws.on('task:error', (e: WSEvent) => {
                if (e.task_id !== taskId) return;
                setStatus('failed');
                setSending(false);
            })
        );

        unsubs.push(
            ws.on('tool:use', (e: WSEvent) => {
                if (e.task_id !== taskId) return;
                const payload = e.payload as { name: string };
                setProgress(`Using tool: ${payload.name}`);
            })
        );

        // Listen for new task started (from session resume)
        unsubs.push(
            ws.on('task:started', (e: WSEvent) => {
                const payload = e.payload as { id: string; session_id?: string };
                // If this is a resumed session, navigate to the new task
                if (payload.id && payload.id !== taskId) {
                    navigate(`/task/${payload.id}`, { replace: true });
                }
            })
        );

        return () => unsubs.forEach((u) => u());
    }, [taskId, navigate]);

    // Auto-scroll to bottom
    useEffect(() => {
        scrollRef.current?.scrollTo({
            top: scrollRef.current.scrollHeight,
            behavior: 'smooth',
        });
    }, [messages]);

    const handleCancel = () => {
        if (taskId) ws.cancelTask(taskId);
    };

    const handleSendReply = () => {
        const text = reply.trim();
        if (!text || !task?.session_id) return;

        setSending(true);
        setProgress('Sending follow-up...');

        // Add user message to the UI immediately
        setMessages((prev) => [
            ...prev,
            {
                id: Date.now().toString(),
                role: 'user',
                content: text,
                timestamp: new Date().toISOString(),
            },
        ]);

        // Resume the session with the new prompt
        ws.resumeSession(task.session_id, text);
        setReply('');
        setStatus('running');
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSendReply();
        }
    };

    const isRunning = status === 'running' || status === 'pending';
    const isCompleted = status === 'completed';
    const isFailed = status === 'failed' || status === 'cancelled';
    const canReply = task?.session_id && !sending;

    return (
        <div className="flex-1 flex flex-col h-screen">
            {/* Header */}
            <header className="h-14 border-b border-border flex items-center px-4 gap-3 shrink-0">
                <button
                    onClick={() => navigate('/')}
                    className="w-8 h-8 rounded-lg flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-accent/50 transition-colors"
                >
                    <ArrowLeft weight="bold" className="w-4 h-4" />
                </button>

                <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">
                        {task?.config.prompt || 'Loading...'}
                    </p>
                    <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                        {isRunning && (
                            <>
                                <CircleNotch weight="bold" className="w-3 h-3 animate-spin" />
                                {progress}
                            </>
                        )}
                        {isCompleted && (
                            <>
                                <CheckCircle weight="fill" className="w-3 h-3 text-green-500" />
                                Completed — you can send a follow-up below
                            </>
                        )}
                        {isFailed && (
                            <>
                                <XCircle weight="fill" className="w-3 h-3 text-red-500" />
                                {status === 'cancelled' ? 'Cancelled' : 'Failed'}
                            </>
                        )}
                    </p>
                </div>

                {isRunning && (
                    <button
                        onClick={handleCancel}
                        className="h-8 px-3 rounded-lg border border-destructive/30 text-destructive text-xs font-medium flex items-center gap-1.5 hover:bg-destructive/10 transition-colors"
                    >
                        <Stop weight="bold" className="w-3.5 h-3.5" />
                        Stop
                    </button>
                )}
            </header>

            {/* Messages */}
            <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
                <AnimatePresence>
                    {messages.map((msg, i) => (
                        <motion.div
                            key={msg.id || i}
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.2, delay: i * 0.02 }}
                            className={`max-w-3xl ${msg.role === 'user' ? 'ml-auto' : 'mr-auto'}`}
                        >
                            <div
                                className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${msg.role === 'user'
                                    ? 'bg-primary text-primary-foreground'
                                    : 'bg-muted text-foreground'
                                    }`}
                            >
                                {msg.role === 'assistant' ? (
                                    <div className="prose prose-sm dark:prose-invert max-w-none">
                                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                            {msg.content}
                                        </ReactMarkdown>
                                    </div>
                                ) : (
                                    <p className="whitespace-pre-wrap">{msg.content}</p>
                                )}
                            </div>
                        </motion.div>
                    ))}
                </AnimatePresence>

                {/* Loading indicator */}
                {isRunning && messages.length === 0 && (
                    <div className="flex items-center justify-center py-12">
                        <CircleNotch weight="bold" className="w-6 h-6 text-muted-foreground animate-spin" />
                    </div>
                )}

                {/* Typing indicator when agent is responding */}
                {(isRunning || sending) && messages.length > 0 && (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        className="max-w-3xl mr-auto"
                    >
                        <div className="rounded-2xl px-4 py-3 bg-muted text-muted-foreground text-sm flex items-center gap-2">
                            <CircleNotch weight="bold" className="w-4 h-4 animate-spin" />
                            <span>{progress || 'Thinking...'}</span>
                        </div>
                    </motion.div>
                )}
            </div>

            {/* Reply input — always visible */}
            <div className="border-t border-border px-4 py-3 shrink-0">
                <div className="max-w-3xl mx-auto flex items-end gap-2">
                    <textarea
                        ref={inputRef}
                        value={reply}
                        onChange={(e) => setReply(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder={
                            canReply
                                ? 'Send a follow-up message...'
                                : isRunning
                                    ? 'Waiting for agent to finish...'
                                    : !task?.session_id
                                        ? 'Waiting for session...'
                                        : 'Type a message...'
                        }
                        disabled={sending || (isRunning && !isCompleted)}
                        rows={1}
                        className="flex-1 resize-none rounded-xl border border-border bg-background px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary disabled:opacity-50 disabled:cursor-not-allowed"
                        style={{
                            minHeight: '42px',
                            maxHeight: '120px',
                            height: 'auto',
                            overflow: reply.split('\n').length > 3 ? 'auto' : 'hidden',
                        }}
                        onInput={(e) => {
                            const el = e.currentTarget;
                            el.style.height = 'auto';
                            el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
                        }}
                    />
                    <button
                        onClick={handleSendReply}
                        disabled={!reply.trim() || !canReply}
                        className="w-10 h-10 rounded-xl bg-primary text-primary-foreground flex items-center justify-center hover:bg-primary/90 transition-colors disabled:opacity-30 disabled:cursor-not-allowed shrink-0"
                    >
                        {sending ? (
                            <CircleNotch weight="bold" className="w-4 h-4 animate-spin" />
                        ) : (
                            <PaperPlaneRight weight="fill" className="w-4 h-4" />
                        )}
                    </button>
                </div>
            </div>
        </div>
    );
}
