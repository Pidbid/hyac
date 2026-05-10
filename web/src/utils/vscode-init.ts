import getConfigurationServiceOverride from '@codingame/monaco-vscode-configuration-service-override';
import getFilesServiceOverride from '@codingame/monaco-vscode-files-service-override';
import getExtensionsServiceOverride from '@codingame/monaco-vscode-extensions-service-override';
import getEnvironmentServiceOverride from '@codingame/monaco-vscode-environment-service-override';
import getHostServiceOverride from '@codingame/monaco-vscode-host-service-override';
import getBaseServiceOverride from '@codingame/monaco-vscode-base-service-override';
import { StandaloneServices } from '@codingame/monaco-vscode-api';
import { URI } from '@codingame/monaco-vscode-api/vscode/vs/base/common/uri';
import 'vscode/localExtensionHost';

import '@codingame/monaco-vscode-python-default-extension';
import '@codingame/monaco-vscode-theme-defaults-default-extension';

let initialized = false;

export function ensureVscodeServicesInitialized(): void {
  if (initialized) {
    return;
  }
  initialized = true;

  try {
    StandaloneServices.initialize({
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
