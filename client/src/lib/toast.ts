export type ToastLevel = 'info' | 'success' | 'error';

export interface ToastMessage {
    id: string;
    level: ToastLevel;
    title: string;
    description?: string;
}

const listeners = new Set<(toast: ToastMessage) => void>();

export function onToast(listener: (toast: ToastMessage) => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
}

function emit(toast: ToastMessage) {
    listeners.forEach((listener) => listener(toast));
}

function create(level: ToastLevel, title: string, description?: string) {
    emit({
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        level,
        title,
        description,
    });
}

export const toast = {
    info: (title: string, description?: string) => create('info', title, description),
    success: (title: string, description?: string) => create('success', title, description),
    error: (title: string, description?: string) => create('error', title, description),
};
