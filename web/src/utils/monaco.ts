// import '@codingame/monaco-vscode-language-pack-zh-hans';
import '@codingame/monaco-vscode-python-default-extension';
import '@codingame/monaco-vscode-theme-defaults-default-extension';
import '@codingame/monaco-vscode-css-default-extension'

// import 'monaco-editor/esm/vs/editor/editor.all.js';

import 'monaco-editor/esm/vs/language/json/monaco.contribution';
import 'monaco-editor/esm/vs/basic-languages/monaco.contribution';

import * as monaco from 'monaco-editor/esm/vs/editor/editor.api';

import { initialize } from '@codingame/monaco-vscode-api';

// @ts-ignore
import getLanguagesServiceOverride from '@codingame/monaco-vscode-languages-service-override';
// @ts-ignore
import getThemeServiceOverride from '@codingame/monaco-vscode-theme-service-override';
// @ts-ignore
import getTextMateServiceOverride from '@codingame/monaco-vscode-textmate-service-override';


async function initMonaco() {
  await initialize({
    ...getTextMateServiceOverride(),
    ...getThemeServiceOverride(),
    ...getLanguagesServiceOverride()
  });
}

export { monaco, initMonaco };
