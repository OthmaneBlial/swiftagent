export function applyTheme(theme: 'light' | 'dark' | 'system') {
    const root = document.documentElement;
    if (theme === 'dark') {
        root.classList.add('dark');
        return;
    }
    if (theme === 'light') {
        root.classList.remove('dark');
        return;
    }

    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    root.classList.toggle('dark', prefersDark);
}
