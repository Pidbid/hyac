# LSP Sidecar E2E Checklist

## 1. Startup
- Ensure compose includes `lsp-sidecar` service and it is running.
- Set env:
  - `LSP_MODE=sidecar`
  - `LSP_SIDECAR_URL=ws://hyac_lsp_sidecar:9002/lsp`
  - `LSP_SIDECAR_FALLBACK_LEGACY=true`

## 2. Health checks
- Sidecar:
  - `curl -f http://localhost:9002/health`
- Runtime:
  - Open function editor page and confirm websocket to `/{appId}/__lsp__` is connected.

## 3. Automated smoke
- Run:
  - `bash test/lsp_e2e.sh`
- Optional runtime smoke:
  - `RUNTIME_WS_URL='wss://<app-id>.<domain>/__lsp__' bash test/lsp_e2e.sh`

## 4. Functional checks in editor
- First open function file:
  - syntax highlight available
  - no websocket reconnect loop
- Edit code:
  - diagnostics refresh after changes
  - no stale diagnostics from previous file
- Context scenario:
  - type `context.` and verify completion is improved (depends on shim/type stubs)

## 5. Fallback verification
- Keep `LSP_SIDECAR_FALLBACK_LEGACY=true`.
- Stop `lsp-sidecar`.
- Re-open editor.
- Expect runtime log includes fallback message:
  - `Falling back to legacy pylsp mode...`

## 6. Failure criteria
- `initialize` timeout > 8s
- editor websocket closes repeatedly
- no diagnostics after `didChange`
- sidecar process crash and runtime does not fallback

