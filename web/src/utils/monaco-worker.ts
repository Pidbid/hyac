import editorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker';

const EditorWorker = editorWorker;

window.MonacoEnvironment = {
  getWorker() {
    return new EditorWorker();
  }
};
