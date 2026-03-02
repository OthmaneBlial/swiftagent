import { useEffect, useState } from 'react';
import { onToast, type ToastMessage } from '../../lib/toast';

export default function ToastViewport() {
    const [items, setItems] = useState<ToastMessage[]>([]);

    useEffect(() => {
        const unsub = onToast((toast) => {
            setItems((prev) => [...prev, toast]);
            setTimeout(() => {
                setItems((prev) => prev.filter((i) => i.id !== toast.id));
            }, 4000);
        });
        return unsub;
    }, []);

    return (
        <div className="fixed top-4 right-4 z-[60] space-y-2 w-[320px] max-w-[calc(100vw-2rem)]">
            {items.map((item) => (
                <div
                    key={item.id}
                    className={`rounded-lg border px-3 py-2 shadow-lg backdrop-blur ${
                        item.level === 'error'
                            ? 'border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300'
                            : item.level === 'success'
                                ? 'border-green-500/30 bg-green-500/10 text-green-700 dark:text-green-300'
                                : 'border-border bg-background text-foreground'
                    }`}
                >
                    <p className="text-sm font-medium">{item.title}</p>
                    {item.description ? <p className="text-xs mt-0.5 opacity-90">{item.description}</p> : null}
                </div>
            ))}
        </div>
    );
}
