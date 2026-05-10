# Monaco Python 语法高亮方案

## 背景

项目使用 `@codingame/monaco-vscode-editor-api`（alias 为 `monaco-editor`）替代标准 Monaco。该 fork 不内置 Python 语法，需要显式注册语言和 tokenizer。

## 最终方案

文件: `web/src/views/function/modules/EditorMonaco.vue`

### 核心三步（模块顶层，按顺序执行）

```typescript
import * as monaco from 'monaco-editor';

// 1. 注册 Python 语言 ID（必须最先执行）
monaco.languages.register({
  id: 'python',
  extensions: ['.py'],
  aliases: ['Python', 'python', 'py']
});

// 2. 注册 Monarch 语法高亮 tokenizer
monaco.languages.setMonarchTokensProvider('python', {
  defaultToken: '',
  tokenizer: {
    root: [
      [/\b(def|class|import|from|return|if|for|while|...)\b/, 'keyword'],
      [/\b(True|False|None)\b/, 'number'],
      [/\b\d+(\.\d+)?\b/, 'number'],
      [/[rfb]?(?:'''|"""|'|")/, { token: 'string', next: '@stringState' }],
      [/#.*/, 'comment'],
      [/[{}()[\]]/, 'delimiter'],
      [/[+\-*/%=<>!&|^~]+/, 'operator']
    ],
    stringState: [
      [/[^\\'"]+/, 'string'],
      [/\\./, 'string.escape'],
      [/('''|"""|'|")/, { token: 'string', next: '@pop' }]
    ]
  }
});

// 3. 注册自定义补全（ctx.xxx 等）
monaco.languages.registerCompletionItemProvider('python', { ... });
```

### 关键注意事项

1. **`monaco.languages.register` 必须在 `setMonarchTokensProvider` 之前调用**，否则 token 无法附着。

2. **不要使用 `nextEmbedded`** —— 字符串状态机用 `next: '@pop'` 弹出即可，`nextEmbedded` 要求先有 `@push` 进入嵌入语言，未进入时调用会报错：
   ```
   python: cannot pop embedded language if not inside one
   ```

3. **不需要 `@codingame/monaco-vscode-python-default-extension`** —— 它内部调用 `registerExtension` 需要完整的 VS Code 扩展宿主初始化，太复杂且会触发 `Default api is not ready yet`。

4. **不需要 `@shikijs/monaco`** —— 函数签名是 `shikiToMonaco(highlighter, monaco, options)`，需要先创建 Shiki highlighter 实例，增加复杂度。

5. **LSP 直接通过 WebSocket JSON-RPC 实现** —— 绕过 `MonacoLanguageClient`（需要扩展宿主），`lsp.ts` 直接解析 LSP 协议消息：
   - `textDocument/publishDiagnostics` → `monaco.editor.setModelMarkers`
   - `textDocument/didOpen` / `didChange` → 同步编辑器内容
   - 诊断错误（红色波浪线）实时显示

### Worker 配置

`vite.config.ts` 中添加 `vite-plugin-monaco-editor-esm` 插件（已在 devDeps），自动处理 Monaco Worker：

```typescript
import monacoEditorPlugin from 'vite-plugin-monaco-editor-esm';

plugins: [
  monacoEditorPlugin(),
  // ...
]
```

不需要手动设置 `window.MonacoEnvironment`。

### 试错总结

| 尝试 | 结果 | 原因 |
|------|------|------|
| `language: 'python'` 直接创建编辑器 | ❌ 无高亮 (`mtk1` only) | fork 不内置 Python |
| `@codingame/monaco-vscode-python-default-extension` 导入 | ❌ 无高亮 | 需扩展宿主 |
| `@shikijs/monaco` `shikiToMonaco(monaco, ...)` | ❌ 参数错 + WASM | 签名 `(highlighter, monaco, options)` |
| Monarch 不用 `register` | ❌ 无高亮 | token 无法附着 |
| **`register` + Monarch** | ✅ **成功** | 正确的调用顺序 |
| Monarch 含 `nextEmbedded` | ❌ 报错 | 无嵌入语言却用 `@pop` |
| **`register` + Monarch（无 `nextEmbedded`）** | ✅ **最终方案** | |
