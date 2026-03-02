import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import {
    ClockCounterClockwise,
    Trash,
    CheckCircle,
    XCircle,
    ArrowRight,
} from '@phosphor-icons/react';
import { motion, AnimatePresence } from 'framer-motion';
import { api, type Task } from '../lib/swiftagent';
import { toast } from '../lib/toast';

export default function History() {
    const [tasks, setTasks] = useState<Task[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let cancelled = false;
        api.listTasks()
            .then((t) => {
                if (cancelled) return;
                setTasks(t);
            })
            .catch((error: Error) => {
                if (cancelled) return;
                toast.error('Failed to load history', error.message);
            })
            .finally(() => {
                if (!cancelled) {
                    setLoading(false);
                }
            });

        return () => {
            cancelled = true;
        };
    }, []);

    const handleDelete = async (taskId: string) => {
        try {
            await api.deleteTask(taskId);
            setTasks((prev) => prev.filter((t) => t.id !== taskId));
        } catch (error) {
            toast.error('Failed to delete task', (error as Error).message);
        }
    };

    const handleClearAll = async () => {
        if (!window.confirm('Clear all task history?')) return;
        try {
            await api.clearHistory();
            setTasks([]);
        } catch (error) {
            toast.error('Failed to clear history', (error as Error).message);
        }
    };

    const statusIcon = (status: string) => {
        if (status === 'completed')
            return <CheckCircle weight="fill" className="w-4 h-4 text-green-500" />;
        if (status === 'failed' || status === 'cancelled')
            return <XCircle weight="fill" className="w-4 h-4 text-red-500" />;
        return <ClockCounterClockwise weight="regular" className="w-4 h-4 text-muted-foreground" />;
    };

    return (
        <div className="flex-1 flex flex-col">
            {/* Header */}
            <header className="h-14 border-b border-border flex items-center justify-between px-4 shrink-0">
                <div className="flex items-center gap-2">
                    <ClockCounterClockwise weight="bold" className="w-5 h-5 text-foreground" />
                    <h1 className="text-sm font-semibold text-foreground">Task History</h1>
                    <span className="text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded-full">
                        {tasks.length}
                    </span>
                </div>

                {tasks.length > 0 && (
                    <button
                        onClick={handleClearAll}
                        className="text-xs text-muted-foreground hover:text-destructive transition-colors flex items-center gap-1"
                    >
                        <Trash weight="regular" className="w-3.5 h-3.5" />
                        Clear all
                    </button>
                )}
            </header>

            {/* Task list */}
            <div className="flex-1 overflow-y-auto p-4">
                {loading ? (
                    <div className="flex items-center justify-center py-12 text-muted-foreground text-sm">
                        Loading...
                    </div>
                ) : tasks.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-12 gap-2 text-muted-foreground">
                        <ClockCounterClockwise weight="thin" className="w-12 h-12" />
                        <p className="text-sm">No tasks yet</p>
                        <Link
                            to="/"
                            className="text-xs text-primary hover:underline mt-2"
                        >
                            Start your first task →
                        </Link>
                    </div>
                ) : (
                    <AnimatePresence>
                        <div className="space-y-2 max-w-2xl mx-auto">
                            {tasks.map((task, i) => (
                                <motion.div
                                    key={task.id}
                                    initial={{ opacity: 0, y: 10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    exit={{ opacity: 0, x: -50 }}
                                    transition={{ duration: 0.2, delay: i * 0.03 }}
                                >
                                    <Link
                                        to={`/task/${task.id}`}
                                        className="flex items-center gap-3 p-3 rounded-xl border border-border hover:border-primary/20 hover:bg-accent/30 transition-colors group"
                                    >
                                        {statusIcon(task.status)}

                                        <div className="flex-1 min-w-0">
                                            <p className="text-sm font-medium text-foreground truncate">
                                                {task.config.prompt}
                                            </p>
                                            <p className="text-xs text-muted-foreground mt-0.5">
                                                {new Date(task.created_at).toLocaleDateString(undefined, {
                                                    month: 'short',
                                                    day: 'numeric',
                                                    hour: '2-digit',
                                                    minute: '2-digit',
                                                })}
                                            </p>
                                        </div>

                                        <button
                                            onClick={(e) => {
                                                e.preventDefault();
                                                handleDelete(task.id);
                                            }}
                                            className="opacity-0 group-hover:opacity-100 w-7 h-7 rounded-md flex items-center justify-center text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all"
                                        >
                                            <Trash weight="regular" className="w-3.5 h-3.5" />
                                        </button>

                                        <ArrowRight
                                            weight="bold"
                                            className="w-4 h-4 text-muted-foreground/40 group-hover:text-foreground transition-colors"
                                        />
                                    </Link>
                                </motion.div>
                            ))}
                        </div>
                    </AnimatePresence>
                )}
            </div>
        </div>
    );
}
