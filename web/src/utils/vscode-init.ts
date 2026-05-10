import getConfigurationServiceOverride, {
  ConfigurationScope,
  configurationRegistry,
  initUserConfiguration
} from '@codingame/monaco-vscode-configuration-service-override';
import getFilesServiceOverride from '@codingame/monaco-vscode-files-service-override';
import getExtensionsServiceOverride from '@codingame/monaco-vscode-extensions-service-override';
import getEnvironmentServiceOverride from '@codingame/monaco-vscode-environment-service-override';
import getHostServiceOverride from '@codingame/monaco-vscode-host-service-override';
import getBaseServiceOverride from '@codingame/monaco-vscode-base-service-override';
import { initialize } from '@codingame/monaco-vscode-api';
import { URI } from '@codingame/monaco-vscode-api/vscode/vs/base/common/uri';
import { SuggestMemoryService } from '@codingame/monaco-vscode-api/vscode/vs/editor/contrib/suggest/browser/suggestMemory';
import { ISuggestMemoryService } from '@codingame/monaco-vscode-api/vscode/vs/editor/contrib/suggest/browser/suggestMemory.service';
import {
  InstantiationType,
  registerSingleton
} from '@codingame/monaco-vscode-api/vscode/vs/platform/instantiation/common/extensions';
import 'vscode/localExtensionHost';

import '@codingame/monaco-vscode-python-default-extension';
import '@codingame/monaco-vscode-theme-defaults-default-extension';

let initialized = false;

function registerSuggestMemoryService() {
  try {
    registerSingleton(ISuggestMemoryService, SuggestMemoryService, InstantiationType.Delayed);
  } catch {
    // The service can already be registered when Monaco was initialized elsewhere.
  }
}

async function registerEditorConfiguration() {
  try {
    configurationRegistry.registerConfiguration({
      id: 'editor',
      order: 5,
      type: 'object',
      title: 'Editor',
      scope: ConfigurationScope.LANGUAGE_OVERRIDABLE,
      properties: {
        'editor.wordBasedSuggestions': {
          enum: ['off', 'currentDocument', 'matchingDocuments', 'allDocuments'],
          default: 'matchingDocuments',
          description: 'Controls whether completions should be computed based on words in the document.'
        },
        'editor.suggest.insertMode': {
          type: 'string',
          enum: ['insert', 'replace'],
          default: 'insert',
          description: 'Controls whether words are overwritten when accepting completions.'
        },
        'editor.suggest.filterGraceful': {
          type: 'boolean',
          default: true,
          description: 'Controls whether filtering and sorting suggestions accounts for small typos.'
        },
        'editor.suggest.snippetsPreventQuickSuggestions': {
          type: 'boolean',
          default: true,
          description: 'Controls whether an active snippet prevents quick suggestions.'
        },
        'editor.suggest.showIcons': {
          type: 'boolean',
          default: true,
          description: 'Controls whether to show or hide icons in suggestions.'
        },
        'editor.suggest.showStatusBar': {
          type: 'boolean',
          default: false,
          description: 'Controls the visibility of the status bar at the bottom of the suggest widget.'
        },
        'editor.suggest.preview': {
          type: 'boolean',
          default: false,
          description: 'Controls whether the editor should highlight predicate matches for the selected item.'
        },
        'editor.suggest.shareSuggestSelections': {
          type: 'boolean',
          default: false,
          description:
            'Controls whether remembered suggestion selections are shared between multiple workspaces and windows.'
        },
        'editor.suggestSelection': {
          type: 'string',
          enum: ['first', 'recentlyUsed', 'recentlyUsedByPrefix'],
          default: 'first',
          description: 'Controls how suggestions are pre-selected when showing the suggest list.'
        },
        'editor.suggest.selectionMode': {
          type: 'string',
          enum: ['always', 'never', 'whenTriggerCharacter', 'whenQuickSuggestion'],
          default: 'always',
          description: 'Controls whether a suggestion is selected when the widget shows.'
        },
        'editor.suggestPreviewMode': {
          type: 'string',
          enum: ['prefix', 'subword', 'subwordSmart'],
          default: 'subwordSmart',
          description: 'Controls which mode to use when previewing a suggestion.'
        }
      }
    });

    const editorSettings = {
      'editor.wordBasedSuggestions': 'matchingDocuments',
      'editor.suggest.insertMode': 'insert',
      'editor.suggest.filterGraceful': true,
      'editor.suggest.snippetsPreventQuickSuggestions': true,
      'editor.suggest.showIcons': true,
      'editor.suggest.showStatusBar': false,
      'editor.suggest.preview': false,
      'editor.suggest.shareSuggestSelections': false,
      'editor.suggestSelection': 'first',
      'editor.suggest.selectionMode': 'always',
      'editor.suggestPreviewMode': 'subwordSmart'
    };
    await initUserConfiguration(JSON.stringify(editorSettings, null, 2));
  } catch {
    // ignore
  }
}

export async function ensureVscodeServicesInitialized(): Promise<void> {
  if (initialized) {
    return;
  }
  initialized = true;

  registerSuggestMemoryService();
  await registerEditorConfiguration();

  try {
    await initialize({
      ...getEnvironmentServiceOverride(),
      ...getExtensionsServiceOverride(),
      ...getFilesServiceOverride(),
      ...getHostServiceOverride(),
      ...getBaseServiceOverride(),
      ...getConfigurationServiceOverride(URI.file('/tmp'))
    });
  } catch (e: any) {
    if (e.message?.includes('already initialized') || e.message?.includes('Cannot register')) {
      return;
    }
    console.error('Failed to initialize vscode services:', e);
  }
}
