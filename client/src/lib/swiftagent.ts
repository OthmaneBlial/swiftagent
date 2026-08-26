const localApiBase = 'http://localhost:8000';
const localWsUrl = 'ws://localhost:8000/ws';
const sameOriginApiBase = window.location.origin;
const sameOriginWsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`;

// The development server talks to FastAPI on port 8000. The production bundle
// is served by FastAPI itself, so it must follow its configured host and port.
const API_BASE = import.meta.env.VITE_API_URL || (import.meta.env.DEV ? localApiBase : sameOriginApiBase);
const WS_URL = import.meta.env.VITE_WS_URL || (import.meta.env.DEV ? localWsUrl : sameOriginWsUrl);

export interface Task {
    id: string;
    config: TaskConfig;
    status: string;
    messages: TaskMessage[];
    result: TaskResult | null;
    agent_id: string;
    adapter_id: string;
    adapter_version: string;
    native_session_id: string | null;
    capability_snapshot: Record<string, unknown>;
    session_id: string | null;
    summary: string | null;
    created_at: string;
    completed_at: string | null;
}

export interface TaskConfig {
    prompt: string;
    agent_id: string;
    working_directory?: string;
    model_id?: string;
}

export interface TaskMessage {
    id: string;
    role: string;
    content: string;
    timestamp: string;
    metadata?: Record<string, unknown>;
}

export interface TaskResult {
    success: boolean;
    summary?: string;
    error?: string;
}

export type VerificationStatus = 'passed' | 'failed' | 'not_run';

export interface VerificationEvidence {
    status: VerificationStatus;
    summary: string | null;
    command: string | null;
    source: 'user' | 'adapter' | 'system';
    recorded_at: string;
}

export interface SafetyLayer {
    supported: boolean | null;
    mode: string | null;
    permission_policy: string | null;
    active: boolean | null;
    evidence_status: 'verified' | 'partial' | 'unsupported' | 'unknown';
    notice: string | null;
}

export interface ActivityLedgerEntry {
    sequence: number;
    type: string;
    timestamp: string;
    summary: string;
    payload: Record<string, unknown>;
    native_event_type: string | null;
    native_metadata: Record<string, unknown>;
}

export interface RunReceipt {
    schema_version: 1;
    run_id: string;
    intent: string;
    status: string;
    agent: {
        agent_id: string;
        display_name: string;
        adapter_id: string;
        adapter_version: string;
        protocol: string;
        model: string | null;
        native_session_id: string | null;
    };
    workspace: string;
    started_at: string;
    completed_at: string | null;
    duration_ms: number | null;
    result: TaskResult | null;
    safety: {
        native: SafetyLayer;
        swiftagent_isolation: SafetyLayer;
        effective_summary: string;
    };
    interactions: {
        tools_started: number;
        tools_completed: number;
        approvals_requested: number;
        approvals_approved: number;
        approvals_denied: number;
        questions_requested: number;
        latest_plan: Record<string, unknown> | null;
        latest_usage: Record<string, unknown> | null;
    };
    git: {
        available: boolean;
        baseline_sha: string | null;
        final_sha: string | null;
        branch: string | null;
        initial_dirty: boolean;
        initial_changed_files: string[];
        changed_files: string[];
        post_run_diff_summary: string | null;
        error: string | null;
    };
    verification: VerificationEvidence;
    ledger: ActivityLedgerEntry[];
    ledger_total: number;
    actions: {
        inspect: boolean;
        resume_same_agent: boolean;
        create_handoff: boolean;
    };
}

export interface AppSettings {
    debug_mode: boolean;
    theme: 'light' | 'dark' | 'system';
    default_agent_id: string;
    claude_model: string | null;
    claude_permission_mode: string;
    claude_cli_path: string | null;
    acp_command_json: string;
    codex_model: string | null;
    codex_cli_path: string | null;
    codex_approval_policy: 'untrusted' | 'on-request' | 'never';
    codex_sandbox_mode: 'read-only' | 'workspace-write' | 'danger-full-access';
    codex_allow_dangerous_bypass: boolean;
    opencode_model: string | null;
    opencode_cli_path: string | null;
    generic_command_manifest_json: string;
    workspace_dir: string;
    sandbox_mode: 'strict' | 'fallback';
}

export interface AgentCapabilities {
    structured_streaming: boolean;
    session_create: boolean;
    session_resume: boolean;
    session_fork: boolean;
    tool_events: boolean;
    approvals: boolean;
    questions: boolean;
    plan_updates: boolean;
    attachments: boolean;
    attachment_types: string[];
    model_discovery: boolean;
    mode_discovery: boolean;
    usage: boolean;
    native_sandbox: boolean;
    external_sandbox: 'verified' | 'partial' | 'unsupported' | 'unknown';
    cancellation: boolean;
}

export interface AgentStatus {
    agent_id: string;
    display_name: string;
    adapter_id: string;
    adapter_version: string;
    protocol: string;
    install_url: string | null;
    documentation_url: string | null;
    installed: boolean;
    executable_path: string | null;
    version: string | null;
    compatible: boolean | null;
    auth_status: 'not_checked' | 'ready' | 'action_required' | 'unknown' | 'error';
    detail: string | null;
    checked_at: string;
    capabilities: AgentCapabilities;
    models: Array<{
        id: string;
        name: string;
        provider: string | null;
    }>;
}

export interface AgentListResponse {
    default_agent_id: string;
    agents: AgentStatus[];
}

export interface GenericCommandTestResult {
    success: boolean;
    stdout: string;
    stderr: string;
    version_output: string | null;
    sandbox_notice: string | null;
    tested_at: string;
}

export interface EngineStatus {
    claude_cli_available: boolean;
    claude_cli_path: string | null;
    bwrap_available: boolean;
    bwrap_usable?: boolean;
    bwrap_reason?: string | null;
    workspace_dir: string;
    sandbox_mode: 'strict' | 'fallback';
    strict_sandbox_active: boolean;
    degraded: boolean;
    degraded_reason: string | null;
    auth_probe: {
        status: string;
        message: string | null;
        checked_at: string | null;
    };
}

export interface FileEntry {
    name: string;
    path: string;
    type: 'file' | 'directory';
    size?: number | null;
    modified_at: string;
}

export interface FileListResponse {
    path: string;
    parent: string | null;
    entries: FileEntry[];
}

export interface FileReadResponse {
    path: string;
    content: string;
}

export interface WSEvent {
    type: string;
    payload: Record<string, unknown>;
    task_id?: string;
    run_id?: string;
    timestamp: string;
}

const inflightGetRequests = new Map<string, Promise<unknown>>();

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
    const method = (options?.method ?? 'GET').toUpperCase();
    const url = `${API_BASE}/api${path}`;

    const run = async () => {
        const res = await fetch(url, {
            headers: { 'Content-Type': 'application/json' },
            ...options,
        });

        if (!res.ok) {
            const err = await res.text();
            throw new Error(`API Error ${res.status}: ${err}`);
        }

        return res.json() as Promise<T>;
    };

    // Deduplicate concurrent GETs (helps React StrictMode double-mount in dev).
    if (method === 'GET') {
        const key = `${method} ${url}`;
        const existing = inflightGetRequests.get(key) as Promise<T> | undefined;
        if (existing) {
            return existing;
        }
        const request = run().finally(() => {
            inflightGetRequests.delete(key);
        });
        inflightGetRequests.set(key, request as Promise<unknown>);
        return request;
    }

    return run();
}

export const api = {
    health: async () => {
        const res = await fetch(`${API_BASE}/health`);
        if (!res.ok) {
            const err = await res.text();
            throw new Error(`Health Error ${res.status}: ${err}`);
        }
        return res.json() as Promise<{ status: string; version: string }>;
    },

    listTasks: () => apiFetch<Task[]>('/tasks'),
    getTask: (id: string) => apiFetch<Task>(`/tasks/${id}`),
    getRunReceipt: (id: string) => apiFetch<RunReceipt>(`/tasks/${id}/receipt`),
    updateRunVerification: (
        id: string,
        update: { status: VerificationStatus; summary?: string; command?: string },
    ) =>
        apiFetch<RunReceipt>(`/tasks/${id}/receipt/verification`, {
            method: 'PUT',
            body: JSON.stringify(update),
        }),
    downloadRunReceipt: async (id: string, format: 'json' | 'markdown') => {
        const response = await fetch(
            `${API_BASE}/api/tasks/${encodeURIComponent(id)}/receipt/export?format=${format}`,
        );
        if (!response.ok) {
            throw new Error(`Receipt export failed (${response.status})`);
        }
        const blob = await response.blob();
        const objectUrl = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = objectUrl;
        anchor.download = `swiftagent-receipt-${id}.${format === 'markdown' ? 'md' : 'json'}`;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(objectUrl);
    },
    deleteTask: (id: string) => apiFetch<{ ok: boolean }>(`/tasks/${id}`, { method: 'DELETE' }),
    clearHistory: () => apiFetch<{ ok: boolean }>('/tasks', { method: 'DELETE' }),

    getSettings: () => apiFetch<AppSettings>('/settings'),
    updateSettings: (update: Partial<AppSettings>) =>
        apiFetch<AppSettings>('/settings', { method: 'PUT', body: JSON.stringify(update) }),

    getEngineStatus: (probeAuth = false) =>
        apiFetch<EngineStatus>(`/engine/status?probe_auth=${probeAuth ? 'true' : 'false'}`),
    listAgents: (refresh = false) =>
        apiFetch<AgentListResponse>(`/agents?refresh=${refresh ? 'true' : 'false'}`),
    testGenericCommand: () =>
        apiFetch<GenericCommandTestResult>('/agents/generic-command/test', { method: 'POST' }),

    getWorkspace: () => apiFetch<{ workspace: string; path: string }>('/files/workspace'),
    listFiles: (path = '.') => apiFetch<FileListResponse>(`/files/list?path=${encodeURIComponent(path)}`),
    readFile: (path: string) =>
        apiFetch<FileReadResponse>('/files/read', {
            method: 'POST',
            body: JSON.stringify({ path }),
        }),
    writeFile: (path: string, content: string, createParents = true) =>
        apiFetch<{ ok: boolean; path: string }>('/files/write', {
            method: 'POST',
            body: JSON.stringify({ path, content, create_parents: createParents }),
        }),
    mkdir: (path: string, parents = true) =>
        apiFetch<{ ok: boolean; path: string }>('/files/mkdir', {
            method: 'POST',
            body: JSON.stringify({ path, parents }),
        }),
    moveFile: (sourcePath: string, targetPath: string, createParents = true) =>
        apiFetch<{ ok: boolean; source_path: string; target_path: string }>('/files/move', {
            method: 'POST',
            body: JSON.stringify({ source_path: sourcePath, target_path: targetPath, create_parents: createParents }),
        }),
    deleteFile: (path: string, recursive = false) =>
        apiFetch<{ ok: boolean; path: string }>('/files/delete', {
            method: 'POST',
            body: JSON.stringify({ path, recursive }),
        }),
};

type WSEventHandler = (event: WSEvent) => void;

class SwiftAgentWS {
    private ws: WebSocket | null = null;
    private handlers: Map<string, Set<WSEventHandler>> = new Map();
    private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    private _connected = false;
    private _manualClose = false;

    get connected() {
        return this._connected;
    }

    connect() {
        if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
            return;
        }

        this._manualClose = false;
        this.ws = new WebSocket(WS_URL);

        this.ws.onopen = () => {
            this._connected = true;
            console.log('[WS] Connected');
        };

        this.ws.onmessage = (event) => {
            try {
                const data: WSEvent = JSON.parse(event.data);
                this._dispatch(data);
            } catch (e) {
                console.error('[WS] Parse error:', e);
            }
        };

        this.ws.onclose = () => {
            this._connected = false;
            if (!this._manualClose) {
                if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
                this.reconnectTimer = setTimeout(() => this.connect(), 2000);
            }
        };

        this.ws.onerror = (e) => {
            console.error('[WS] Error:', e);
        };
    }

    disconnect() {
        this._manualClose = true;
        this._connected = false;
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
        this.ws?.close();
        this.ws = null;
    }

    on(eventType: string, handler: WSEventHandler): () => void {
        if (!this.handlers.has(eventType)) {
            this.handlers.set(eventType, new Set());
        }
        this.handlers.get(eventType)!.add(handler);
        return () => this.handlers.get(eventType)?.delete(handler);
    }

    send(type: string, payload: Record<string, unknown> = {}, taskId?: string) {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            console.warn('[WS] Not connected');
            return;
        }
        this.ws.send(JSON.stringify({ type, payload, task_id: taskId }));
    }

    startTask(config: TaskConfig) {
        this.send('task:start', config as unknown as Record<string, unknown>);
    }

    cancelTask(taskId: string) {
        this.send('task:cancel', {}, taskId);
    }

    respondToPermission(requestId: string, approved: boolean) {
        this.send('permission:response', { request_id: requestId, approved });
    }

    respondToQuestion(requestId: string, answer: string) {
        this.send('question:response', { request_id: requestId, answer });
    }

    resumeSession(sessionId: string, prompt: string, agentId: string) {
        this.send('session:resume', { session_id: sessionId, prompt, agent_id: agentId });
    }

    private _dispatch(event: WSEvent) {
        const handlers = this.handlers.get(event.type);
        if (handlers) handlers.forEach((h) => h(event));

        const wildcards = this.handlers.get('*');
        if (wildcards) wildcards.forEach((h) => h(event));
    }
}

export const ws = new SwiftAgentWS();
