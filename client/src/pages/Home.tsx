import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router';
import { PaperPlaneRight, Sparkle, CircleNotch } from '@phosphor-icons/react';
import { motion, AnimatePresence } from 'framer-motion';
import { ws, api, type Task } from '../lib/swiftagent';

export default function Home() {
    const [prompt, setPrompt] = useState('');
    const [loading, setLoading] = useState(false);
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const navigate = useNavigate();

    useEffect(() => {
        textareaRef.current?.focus();
    }, []);

    // Listen for task:started to navigate to execution page
    useEffect(() => {
        const unsub = ws.on('task:started', (event) => {
            const taskId = event.task_id || (event.payload as { id?: string })?.id;
            if (taskId) {
                setLoading(false);
                navigate(`/task/${taskId}`);
            }
        });
        return unsub;
    }, [navigate]);

    const handleSubmit = async () => {
        const trimmed = prompt.trim();
        if (!trimmed || loading) return;

        setLoading(true);
        ws.startTask({ prompt: trimmed });
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSubmit();
        }
    };

    // Auto-resize textarea
    const handleInput = () => {
        const el = textareaRef.current;
        if (el) {
            el.style.height = 'auto';
            el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
        }
    };

    return (
        <div className="flex-1 flex flex-col items-center justify-center px-6">
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, ease: 'easeOut' }}
                className="w-full max-w-2xl space-y-6"
            >
                {/* Header */}
                <div className="text-center space-y-2">
                    <div className="flex items-center justify-center gap-2">
                        <Sparkle weight="fill" className="w-6 h-6 text-primary" />
                        <h1 className="text-2xl font-semibold text-foreground">
                            SwiftAgent
                        </h1>
                    </div>
                    <p className="text-muted-foreground text-sm">
                        Describe a task and let the AI handle it for you.
                    </p>
                </div>

                {/* Input area */}
                <div className="relative group">
                    <div className="rounded-2xl border border-border bg-card shadow-sm transition-shadow group-focus-within:shadow-md group-focus-within:border-primary/30">
                        <textarea
                            ref={textareaRef}
                            value={prompt}
                            onChange={(e) => {
                                setPrompt(e.target.value);
                                handleInput();
                            }}
                            onKeyDown={handleKeyDown}
                            placeholder="What would you like me to do?"
                            className="w-full resize-none bg-transparent px-5 pt-4 pb-14 text-foreground placeholder:text-muted-foreground/60 focus:outline-none text-[15px] leading-relaxed min-h-[56px] max-h-[200px]"
                            rows={1}
                            disabled={loading}
                        />

                        {/* Bottom bar */}
                        <div className="absolute bottom-3 left-3 right-3 flex items-center justify-between">
                            <span className="text-xs text-muted-foreground/50">
                                {prompt.length > 0 ? `${prompt.length} chars` : 'Shift+Enter for new line'}
                            </span>

                            <button
                                onClick={handleSubmit}
                                disabled={!prompt.trim() || loading}
                                className="h-8 w-8 rounded-lg bg-primary text-primary-foreground flex items-center justify-center disabled:opacity-40 disabled:cursor-not-allowed hover:bg-primary/90 transition-colors"
                            >
                                <AnimatePresence mode="wait">
                                    {loading ? (
                                        <motion.div
                                            key="loading"
                                            initial={{ opacity: 0, rotate: 0 }}
                                            animate={{ opacity: 1, rotate: 360 }}
                                            transition={{ rotate: { duration: 1, repeat: Infinity, ease: 'linear' } }}
                                        >
                                            <CircleNotch weight="bold" className="w-4 h-4" />
                                        </motion.div>
                                    ) : (
                                        <motion.div
                                            key="send"
                                            initial={{ opacity: 0, scale: 0.8 }}
                                            animate={{ opacity: 1, scale: 1 }}
                                        >
                                            <PaperPlaneRight weight="fill" className="w-4 h-4" />
                                        </motion.div>
                                    )}
                                </AnimatePresence>
                            </button>
                        </div>
                    </div>
                </div>
            </motion.div>
        </div>
    );
}
