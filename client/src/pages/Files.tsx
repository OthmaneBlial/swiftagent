import { useEffect, useState } from 'react';
import { Folder, FileText, FloppyDisk, Trash, ArrowUUpLeft, Plus, PencilSimpleLine } from '@phosphor-icons/react';
import { api, type FileEntry } from '../lib/swiftagent';
import { toast } from '../lib/toast';

export default function Files() {
    const [cwd, setCwd] = useState('.');
    const [parent, setParent] = useState<string | null>(null);
    const [entries, setEntries] = useState<FileEntry[]>([]);
    const [selectedFile, setSelectedFile] = useState<string | null>(null);
    const [content, setContent] = useState('');
    const [loading, setLoading] = useState(true);

    const load = async (path = cwd) => {
        setLoading(true);
        try {
            const res = await api.listFiles(path);
            setCwd(res.path);
            setParent(res.parent);
            setEntries(res.entries);
            if (selectedFile && !res.entries.find((e) => e.path === selectedFile)) {
                setSelectedFile(null);
                setContent('');
            }
        } catch (error) {
            toast.error('Failed to load directory', (error as Error).message);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        void load('.');
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const openFile = async (path: string) => {
        try {
            const res = await api.readFile(path);
            setSelectedFile(res.path);
            setContent(res.content);
        } catch (error) {
            toast.error('Failed to read file', (error as Error).message);
        }
    };

    const saveFile = async () => {
        if (!selectedFile) return;
        try {
            await api.writeFile(selectedFile, content, true);
            toast.success('File saved', selectedFile);
            await load(cwd);
        } catch (error) {
            toast.error('Failed to save file', (error as Error).message);
        }
    };

    const createFile = async () => {
        const name = window.prompt('New file path (relative to current directory):');
        if (!name) return;
        const full = cwd === '.' ? name : `${cwd}/${name}`;
        try {
            await api.writeFile(full, '', true);
            toast.success('File created', full);
            await load(cwd);
        } catch (error) {
            toast.error('Failed to create file', (error as Error).message);
        }
    };

    const createFolder = async () => {
        const name = window.prompt('New folder path (relative to current directory):');
        if (!name) return;
        const full = cwd === '.' ? name : `${cwd}/${name}`;
        try {
            await api.mkdir(full, true);
            toast.success('Folder created', full);
            await load(cwd);
        } catch (error) {
            toast.error('Failed to create folder', (error as Error).message);
        }
    };

    const deletePath = async (path: string, isDir: boolean) => {
        if (!window.confirm(`Delete ${path}?`)) return;
        try {
            await api.deleteFile(path, isDir);
            if (selectedFile === path) {
                setSelectedFile(null);
                setContent('');
            }
            toast.success('Deleted', path);
            await load(cwd);
        } catch (error) {
            toast.error('Failed to delete', (error as Error).message);
        }
    };

    const movePath = async (sourcePath: string) => {
        const target = window.prompt(`Move ${sourcePath} to:`);
        if (!target) return;
        const normalizedTarget =
            target.startsWith('/') || cwd === '.' ? target : `${cwd}/${target}`.replace(/\/{2,}/g, '/');
        try {
            await api.moveFile(sourcePath, normalizedTarget, true);
            toast.success('Moved', `${sourcePath} -> ${normalizedTarget}`);
            if (selectedFile === sourcePath) {
                setSelectedFile(normalizedTarget);
            }
            await load(cwd);
        } catch (error) {
            toast.error('Failed to move path', (error as Error).message);
        }
    };

    return (
        <div className="flex-1 min-h-0 flex">
            <div className="w-[360px] border-r border-border flex flex-col min-h-0">
                <header className="h-12 border-b border-border flex items-center justify-between px-3 shrink-0">
                    <p className="text-sm font-semibold text-foreground">Files</p>
                    <div className="flex items-center gap-1">
                        <button
                            onClick={createFolder}
                            className="h-8 w-8 rounded-md hover:bg-accent/50 text-muted-foreground hover:text-foreground"
                            title="New folder"
                        >
                            <Folder className="w-4 h-4 mx-auto" />
                        </button>
                        <button
                            onClick={createFile}
                            className="h-8 w-8 rounded-md hover:bg-accent/50 text-muted-foreground hover:text-foreground"
                            title="New file"
                        >
                            <Plus className="w-4 h-4 mx-auto" />
                        </button>
                    </div>
                </header>

                <div className="px-3 py-2 border-b border-border text-xs text-muted-foreground truncate">{cwd}</div>

                <div className="flex-1 overflow-y-auto p-2 space-y-1">
                    {parent ? (
                        <button
                            onClick={() => load(parent)}
                            className="w-full h-9 px-2 rounded-md text-left text-sm hover:bg-accent/50 flex items-center gap-2"
                        >
                            <ArrowUUpLeft className="w-4 h-4" />
                            ..
                        </button>
                    ) : null}

                    {loading ? (
                        <p className="text-xs text-muted-foreground px-2 py-3">Loading...</p>
                    ) : entries.length === 0 ? (
                        <p className="text-xs text-muted-foreground px-2 py-3">Empty directory</p>
                    ) : (
                        entries.map((entry) => (
                            <div key={entry.path} className="group flex items-center gap-1">
                                <button
                                    onClick={() =>
                                        entry.type === 'directory' ? load(entry.path) : openFile(entry.path)
                                    }
                                    className={`flex-1 h-9 px-2 rounded-md text-left text-sm hover:bg-accent/50 flex items-center gap-2 ${
                                        selectedFile === entry.path ? 'bg-accent/60' : ''
                                    }`}
                                >
                                    {entry.type === 'directory' ? (
                                        <Folder className="w-4 h-4 text-blue-500" />
                                    ) : (
                                        <FileText className="w-4 h-4 text-muted-foreground" />
                                    )}
                                    <span className="truncate">{entry.name}</span>
                                </button>

                                <button
                                    onClick={() => movePath(entry.path)}
                                    className="opacity-0 group-hover:opacity-100 h-8 w-8 rounded-md hover:bg-accent/50 text-muted-foreground"
                                    title="Move / rename"
                                >
                                    <PencilSimpleLine className="w-3.5 h-3.5 mx-auto" />
                                </button>
                                <button
                                    onClick={() => deletePath(entry.path, entry.type === 'directory')}
                                    className="opacity-0 group-hover:opacity-100 h-8 w-8 rounded-md hover:bg-destructive/10 text-muted-foreground hover:text-destructive"
                                    title="Delete"
                                >
                                    <Trash className="w-3.5 h-3.5 mx-auto" />
                                </button>
                            </div>
                        ))
                    )}
                </div>
            </div>

            <div className="flex-1 min-h-0 flex flex-col">
                <header className="h-12 border-b border-border px-3 flex items-center justify-between">
                    <p className="text-sm text-foreground truncate">{selectedFile || 'No file selected'}</p>
                    <button
                        onClick={saveFile}
                        disabled={!selectedFile}
                        className="h-8 px-3 rounded-md bg-primary text-primary-foreground text-xs disabled:opacity-40 inline-flex items-center gap-1"
                    >
                        <FloppyDisk className="w-3.5 h-3.5" />
                        Save
                    </button>
                </header>

                <div className="flex-1 min-h-0 p-3">
                    <textarea
                        value={content}
                        onChange={(e) => setContent(e.target.value)}
                        disabled={!selectedFile}
                        className="w-full h-full resize-none rounded-lg border border-border bg-background p-3 text-sm font-mono text-foreground disabled:opacity-50"
                        placeholder="Select a file to view/edit"
                    />
                </div>
            </div>
        </div>
    );
}
