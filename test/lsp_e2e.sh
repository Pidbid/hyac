#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

SIDECAR_HEALTH_URL="${SIDECAR_HEALTH_URL:-http://localhost:9002/health}"
SIDECAR_WS_URL="${SIDECAR_WS_URL:-ws://localhost:9002/lsp?app_id=e2e&session_id=e2e-1&workspace=/tmp/hyac_lsp_e2e}"
RUNTIME_WS_URL="${RUNTIME_WS_URL:-}"

run_smoke() {
  local target_url="$1"
  if "${PYTHON_BIN}" -c "import websockets" >/dev/null 2>&1; then
    "${PYTHON_BIN}" "${ROOT_DIR}/test/lsp_smoke_client.py" --url "${target_url}"
    return
  fi

  echo "[WARN] local python missing websockets, fallback to hyac_server container"
  local container_url="${target_url}"
  container_url="${container_url/localhost:9002/hyac_lsp_sidecar:9002}"
  container_url="${container_url/127.0.0.1:9002/hyac_lsp_sidecar:9002}"

  docker exec -e TARGET_URL="${container_url}" hyac_server sh -lc "python - <<'PY'
import asyncio, json, websockets, os

url = os.environ['TARGET_URL']
doc_uri = os.environ.get('DOC_URI', 'inmemory:///tmp/smoke.py')

def init_req(doc_uri):
    root_uri = doc_uri.rsplit('/', 1)[0]
    return {
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'initialize',
        'params': {
            'processId': None,
            'rootUri': root_uri,
            'capabilities': {},
            'workspaceFolders': [{'uri': root_uri, 'name': 'smoke'}],
            'clientInfo': {'name': 'hyac-lsp-smoke', 'version': '0.1'},
        },
    }

async def recv_by_id(ws, req_id, timeout=8):
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout)
        data = json.loads(raw)
        if isinstance(data, dict) and data.get('id') == req_id:
            return data

async def run():
    async with websockets.connect(url, open_timeout=8) as ws:
        await ws.send(json.dumps(init_req(doc_uri)))
        init = await recv_by_id(ws, 1)
        if 'result' not in init:
            raise RuntimeError(f'initialize invalid: {init}')
        await ws.send(json.dumps({'jsonrpc': '2.0', 'method': 'initialized', 'params': {}}))
        await ws.send(json.dumps({
            'jsonrpc': '2.0',
            'method': 'textDocument/didOpen',
            'params': {'textDocument': {'uri': doc_uri, 'languageId': 'python', 'version': 1, 'text': 'def handler(ctx):\\n    return 1\\n'}},
        }))
        await ws.send(json.dumps({'jsonrpc': '2.0', 'id': 2, 'method': 'textDocument/documentSymbol', 'params': {'textDocument': {'uri': doc_uri}}}))
        sym = await recv_by_id(ws, 2)
        if 'result' not in sym:
            raise RuntimeError(f'documentSymbol invalid: {sym}')
    print('[OK] smoke passed:', url)

asyncio.run(run())
PY"
}

echo "[1/4] sidecar health check: ${SIDECAR_HEALTH_URL}"
curl -fsS "${SIDECAR_HEALTH_URL}" >/dev/null
echo "[OK] sidecar health is ready"

echo "[2/4] sidecar websocket smoke: ${SIDECAR_WS_URL}"
run_smoke "${SIDECAR_WS_URL}"

echo "[3/4] runtime websocket smoke (optional)"
if [[ -n "${RUNTIME_WS_URL}" ]]; then
  run_smoke "${RUNTIME_WS_URL}"
else
  echo "[SKIP] set RUNTIME_WS_URL to enable runtime __lsp__ smoke"
fi

cat <<'EOF'
[4/4] fallback check (manual)
- Set: LSP_MODE=sidecar, LSP_SIDECAR_URL=ws://hyac_lsp_sidecar:9002/lsp, LSP_SIDECAR_FALLBACK_LEGACY=true
- Stop sidecar service temporarily
- Reconnect editor to runtime __lsp__
- Expect: runtime logs "Falling back to legacy pylsp mode..."
EOF

echo "[DONE] LSP e2e smoke finished"
