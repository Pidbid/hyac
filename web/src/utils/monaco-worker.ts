import editorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker';

const EditorWorker = editorWorker;

globalThis.MonacoEnvironment = {
  getWorker() {
    return new EditorWorker();
  }
};
