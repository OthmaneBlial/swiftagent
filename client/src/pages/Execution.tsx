import { useEffect, useState, useRef } from 'react';
import { useParams, useNavigate } from 'react-router';
import {
    ArrowLeft,
    CircleNotch,
    CheckCircle,
    XCircle,
    Stop,
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
    const scrollRef = useRef<HTMLDivElement>(null);

    // Load task data
    useEffect(() => {
        if (!taskId) return;
        api.getTask(taskId).then((t) => {
            setTask(t);
            setMessages(t.messages);
            setStatus(t.status);
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
            })
        );

        unsubs.push(
            ws.on('task:error', (e: WSEvent) => {
                if (e.task_id !== taskId) return;
                setStatus('failed');
            })
        );

        unsubs.push(
            ws.on('tool:use', (e: WSEvent) => {
                if (e.task_id !== taskId) return;
                const payload = e.payload as { name: string };
                setProgress(`Using tool: ${payload.name}`);
            })
        );

        return () => unsubs.forEach((u) => u());
    }, [taskId]);

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

    const isRunning = status === 'running' || status === 'pending';
    const isCompleted = status === 'completed';
    const isFailed = status === 'failed' || status === 'cancelled';

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
                                Completed
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
            </div>
        </div>
    );
}
