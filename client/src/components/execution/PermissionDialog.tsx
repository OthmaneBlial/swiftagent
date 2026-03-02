import { useState } from 'react';

export interface PermissionPayload {
    id?: string;
    task_id?: string;
    description?: string;
    tool_name?: string;
    file_path?: string;
    question?: string;
}

interface PermissionDialogProps {
    payload: PermissionPayload;
    onRespond: (approved: boolean, answer?: string) => void;
}

export default function PermissionDialog({ payload, onRespond }: PermissionDialogProps) {
    const [answer, setAnswer] = useState('');

    return (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center px-4">
            <div className="w-full max-w-lg rounded-xl border border-border bg-background p-4">
                <h2 className="text-base font-semibold text-foreground mb-2">Permission Required</h2>
                <p className="text-sm text-muted-foreground mb-3">
                    {payload.description || payload.question || 'Agent requested permission for an action.'}
                </p>
                {payload.file_path ? (
                    <p className="text-xs font-mono text-foreground/80 mb-3 break-all">{payload.file_path}</p>
                ) : null}
                {payload.tool_name ? (
                    <p className="text-xs text-muted-foreground mb-3">Tool: {payload.tool_name}</p>
                ) : null}

                <textarea
                    value={answer}
                    onChange={(e) => setAnswer(e.target.value)}
                    placeholder="Optional response for question-based prompts"
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground mb-3"
                    rows={3}
                />

                <div className="flex gap-2 justify-end">
                    <button
                        onClick={() => onRespond(false)}
                        className="h-9 px-3 rounded-lg border border-border text-sm text-foreground hover:bg-accent/50"
                    >
                        Deny
                    </button>
                    <button
                        onClick={() => onRespond(true, answer.trim() || undefined)}
                        className="h-9 px-3 rounded-lg bg-primary text-primary-foreground text-sm hover:bg-primary/90"
                    >
                        Allow
                    </button>
                </div>
            </div>
        </div>
    );
}
