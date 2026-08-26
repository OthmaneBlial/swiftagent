# bwrap Strict Sandbox Roadmap

## Why this file exists

SwiftAgent currently supports two runtime safety modes:

- `strict`: Claude runs inside `bwrap` (OS sandbox)
- `fallback`: Claude runs without OS isolation after an explicit user choice

Right now, this machine reports:

- `bwrap_available = true`
- `bwrap_usable = false`
- reason: `bwrap: setting up uid map: Permission denied`

So `strict` tasks will now **fail before launch** rather than silently falling back. This is intentional: the Files API's workspace guard cannot isolate an unsandboxed Claude process.

---

## Target state

`GET /api/engine/status` should return:

- `"sandbox_mode": "strict"`
- `"strict_sandbox_active": true`
- `"degraded": false`
- `"bwrap_usable": true`

When this is true, Claude task execution is OS-isolated by `bwrap`.

---

## Phase 1: Diagnose host limitations

Run:

```bash
bwrap --version
sysctl kernel.unprivileged_userns_clone 2>/dev/null || true
sysctl user.max_user_namespaces 2>/dev/null || true
```

Manual probe (same pattern SwiftAgent uses):

```bash
workspace="$HOME/.swiftagent/workspace"
mkdir -p "$workspace" "$HOME/.claude"
bwrap --die-with-parent \
  --ro-bind / / \
  --dev-bind /dev /dev \
  --proc /proc \
  --tmpfs /tmp \
  --bind "$workspace" "$workspace" \
  --bind "$HOME/.claude" "$HOME/.claude" \
  --chdir "$workspace" \
  --setenv HOME "$HOME" \
  /bin/true
echo $?
```

Expected exit code: `0`.

---

## Phase 2: Enable required kernel/userns settings (if disabled)

### Debian/Ubuntu-style systems

Temporary:

```bash
sudo sysctl -w kernel.unprivileged_userns_clone=1
sudo sysctl -w user.max_user_namespaces=15000
```

Persistent:

```bash
cat <<'EOF' | sudo tee /etc/sysctl.d/99-swiftagent-userns.conf
kernel.unprivileged_userns_clone=1
user.max_user_namespaces=15000
EOF
sudo sysctl --system
```

### If inside container/VM/devbox

Host or runtime policy may block user namespaces (`uid map` errors).  
Fix must be applied at the container/host policy layer, not only inside SwiftAgent.

---

## Phase 3: Verify strict mode end-to-end

1. Restart app:

```bash
cd /home/othmane/APP-DIVERS-PROJECTS/swiftagent
make dev
```

2. Check engine status:

```bash
curl -s http://127.0.0.1:8000/api/engine/status?probe_auth=false
```

3. Confirm:

- `bwrap_usable: true`
- `strict_sandbox_active: true`
- `degraded: false`

4. Run a normal task and make sure no sandbox failure appears in server logs.

---

## Phase 4: Security hardening follow-ups

After strict mode works, implement these improvements:

Implemented:

1. Strict task launch fails closed when `bwrap` is missing or unusable.
2. Engine status exposes degraded strict-mode state in the UI.
3. Regression coverage verifies that strict mode never silently downgrades.

Remaining:

1. Add a host-level integration test that a strict task cannot write outside its workspace.

---

## Operational fallback (temporary)

If you need productivity over strict isolation for a short period:

```bash
SWIFTAGENT_SANDBOX_MODE=fallback make dev
```

Or persist in `.env`:

```env
SWIFTAGENT_SANDBOX_MODE=fallback
```

Use this only as temporary operational mode until strict sandbox is fixed.
