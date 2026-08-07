/* eslint-disable no-await-in-loop, no-console, no-underscore-dangle */
import assert from 'node:assert/strict';
import { Buffer } from 'node:buffer';
import { readFile } from 'node:fs/promises';
import process from 'node:process';
import { chromium } from 'playwright';

function requiredEnvironment(name) {
  const value = process.env[name];
  assert.ok(value, `${name} is required`);
  return value;
}

function guardWaiter(promise) {
  promise.catch(() => undefined);
  return promise;
}

function combineWaiters(waiters) {
  return guardWaiter(Promise.all(waiters));
}

function waitForApiResponse(page, pathname) {
  return guardWaiter(
    page.waitForResponse(response => {
      const request = response.request();
      return request.method() === 'POST' && new URL(response.url()).pathname === pathname;
    })
  );
}

async function readSuccessfulApiResponse(response, operation) {
  const body = await response.json();
  assert.equal(response.ok(), true, `${operation}: ${JSON.stringify(body)}`);
  assert.equal(body.code, 0, `${operation}: ${JSON.stringify(body)}`);
  return body;
}

async function confirmVisibleDialog(page) {
  const dialog = page.locator('.n-dialog:visible').last();
  await dialog.waitFor({ state: 'visible' });
  await dialog.locator('.n-dialog__action button').last().click();
  return dialog;
}

async function waitForVisibleOrAbsent(locator, timeout = 2_000) {
  try {
    await locator.waitFor({ state: 'visible', timeout });
    return true;
  } catch (error) {
    if ((await locator.count()) === 0) return false;
    throw error;
  }
}

async function deleteFunctionThroughUi(page, functionName) {
  const functionItem = page.locator('.function-item').filter({ hasText: functionName });
  if (!(await waitForVisibleOrAbsent(functionItem))) return false;

  const deleteResponsePromise = waitForApiResponse(page, '/function/delete');
  await functionItem.locator('.delete-btn').click();
  await confirmVisibleDialog(page);
  await readSuccessfulApiResponse(await deleteResponsePromise, 'delete function');
  await functionItem.waitFor({ state: 'detached' });
  return true;
}

async function replaceMonacoContent(page, editor, value) {
  await editor.waitFor({ state: 'visible' });
  const input = editor.locator('textarea');
  await input.waitFor({ state: 'visible' });
  await editor.click({ position: { x: 60, y: 10 } });
  assert.equal(
    await editor.evaluate(element => element.classList.contains('focused')),
    true,
    'Monaco editor did not enter its focused state'
  );
  assert.equal(await input.isEditable(), true, 'Monaco input is read-only');
  const readRenderedText = async () =>
    (await editor.locator('.view-line').allTextContents()).join('').replaceAll('\u00A0', ' ').trim();
  await page.keyboard.press('Control+A');
  await page.waitForTimeout(100);
  await page.keyboard.press('Backspace');
  let clearedText = await readRenderedText();
  for (let attempt = 0; attempt < 20 && clearedText; attempt += 1) {
    await page.waitForTimeout(50);
    clearedText = await readRenderedText();
  }
  assert.equal(clearedText, '', `Monaco content was not cleared: ${clearedText}`);
  const valueToType = value.startsWith('{') && value.endsWith('}') ? value.slice(0, -1) : value;
  await page.keyboard.insertText(valueToType);
  await page.waitForTimeout(100);
}

async function findDocumentRow(page, marker) {
  const rows = page.locator('.document-table tr');
  for (let index = 0; index < (await rows.count()); index += 1) {
    const textarea = rows.nth(index).locator('textarea');
    if ((await textarea.count()) > 0 && (await textarea.inputValue()).includes(marker)) {
      return rows.nth(index);
    }
  }
  throw new Error(`database document row not found: ${marker}`);
}

async function deleteStorageFileThroughUi(page, fileName) {
  const fileRow = page.locator('tr').filter({ hasText: fileName }).first();
  if (!(await waitForVisibleOrAbsent(fileRow))) return false;

  const deleteResponsePromise = waitForApiResponse(page, '/storage/delete_file');
  const listAfterDeletePromise = waitForApiResponse(page, '/storage/list_objects');
  const deleteResponsesPromise = combineWaiters([deleteResponsePromise, listAfterDeletePromise]);
  await fileRow.locator('button').last().click();
  await confirmVisibleDialog(page);
  const [deleteResponse, listAfterDeleteResponse] = await deleteResponsesPromise;
  await readSuccessfulApiResponse(deleteResponse, 'delete storage file');
  await readSuccessfulApiResponse(listAfterDeleteResponse, 'list storage after delete');
  await fileRow.waitFor({ state: 'detached' });
  return true;
}

async function deleteCollectionThroughUi(page, collectionName, clearFirst = false) {
  let collectionItem = page.locator('.collection-panel .n-list-item').filter({ hasText: collectionName }).first();
  if (!(await waitForVisibleOrAbsent(collectionItem))) return false;

  if (clearFirst) {
    const clearResponsePromise = waitForApiResponse(page, '/database/clear_collection');
    const documentsAfterClearPromise = waitForApiResponse(page, '/database/documents');
    const clearResponsesPromise = combineWaiters([clearResponsePromise, documentsAfterClearPromise]);
    await collectionItem.locator('button').first().click();
    const clearDialog = await confirmVisibleDialog(page);
    const [clearResponse, documentsAfterClearResponse] = await clearResponsesPromise;
    await readSuccessfulApiResponse(clearResponse, 'clear database collection for cleanup');
    await readSuccessfulApiResponse(documentsAfterClearResponse, 'list documents after cleanup clear');
    await clearDialog.waitFor({ state: 'hidden' });
    collectionItem = page.locator('.collection-panel .n-list-item').filter({ hasText: collectionName }).first();
  }

  const deleteResponsePromise = waitForApiResponse(page, '/database/delete_collection');
  const collectionsAfterDeletePromise = waitForApiResponse(page, '/database/collections');
  const deleteResponsesPromise = combineWaiters([deleteResponsePromise, collectionsAfterDeletePromise]);
  await collectionItem.locator('button').last().click();
  await confirmVisibleDialog(page);
  const [deleteResponse, collectionsAfterDeleteResponse] = await deleteResponsesPromise;
  await readSuccessfulApiResponse(deleteResponse, 'delete database collection');
  await readSuccessfulApiResponse(collectionsAfterDeleteResponse, 'list collections after delete');
  await collectionItem.waitFor({ state: 'detached' });
  return true;
}

function waitForDownloadFromPageOrPopup(page) {
  const context = page.context();
  const watchedPages = new Set();
  let cancelDownload = () => undefined;

  const promise = guardWaiter(
    new Promise((resolve, reject) => {
      let settled = false;
      let timeout;

      function cleanup() {
        clearTimeout(timeout);
        context.off('page', watchPage);
        for (const watchedPage of watchedPages) {
          watchedPage.off('download', handleDownload);
        }
      }

      function settle(callback, value) {
        if (settled) return;
        settled = true;
        cleanup();
        callback(value);
      }

      function handleDownload(download) {
        settle(resolve, download);
      }

      function watchPage(candidate) {
        watchedPages.add(candidate);
        candidate.once('download', handleDownload);
      }

      cancelDownload = reason => {
        const error = reason instanceof Error ? reason : new Error(String(reason));
        settle(reject, error);
      };

      timeout = setTimeout(() => {
        settle(reject, new Error('storage download did not start within 60 seconds'));
      }, 60_000);

      for (const existingPage of context.pages()) watchPage(existingPage);
      context.on('page', watchPage);
    })
  );

  return {
    promise,
    cancel: reason => cancelDownload(reason || new Error('storage download waiter cancelled'))
  };
}

const baseUrl = requiredEnvironment('SMOKE_BASE_URL');
const username = requiredEnvironment('SMOKE_ADMIN_USERNAME');
const password = requiredEnvironment('SMOKE_ADMIN_PASSWORD');
const captcha = requiredEnvironment('SMOKE_CAPTCHA');
const appName = process.env.SMOKE_APP_NAME || 'demo';
const runId = Date.now().toString(36);
const functionName = process.env.SMOKE_FUNCTION_NAME || `chrome_lifecycle_${runId}`;
const expectedResult = `Chrome lifecycle ${runId}`;
const storageFileName = `chrome_storage_${runId}.json`;
const storageMarker = `storage-${runId}`;
const storageContent = JSON.stringify({
  marker: storageMarker,
  source: 'chrome-e2e'
});
const collectionName = `chrome_db_${runId}`;
const documentMarker = `database-${runId}`;
const updatedDocumentMarker = `database-updated-${runId}`;
const updatedCode = `async def handler(ctx, request):
    return {"code": 0, "msg": "success", "data": "${expectedResult}"}`;

const browser = await chromium.launch({
  channel: 'chrome',
  headless: true,
  args: [
    '--ignore-certificate-errors',
    '--allow-insecure-localhost',
    '--no-proxy-server',
    '--host-resolver-rules=MAP *.ci.example.com 127.0.0.1,MAP console.ci.example.com 127.0.0.1,MAP server.ci.example.com 127.0.0.1,MAP oss.ci.example.com 127.0.0.1'
  ]
});

let page;
let createdFunctionId = '';
let functionCreateAttempted = false;
let deleted = false;
let storageUploadAttempted = false;
let storageDeleted = false;
let collectionCreateAttempted = false;
let collectionDeleted = false;
let activeDownloadWatcher;

try {
  page = await browser.newPage({
    ignoreHTTPSErrors: true,
    viewport: { width: 1600, height: 1000 }
  });
  page.setDefaultTimeout(60_000);

  await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
  const form = page.locator('form');
  await form.locator('input[autocomplete="username"]').fill(username);
  await form.locator('input[autocomplete="current-password"]').fill(password);
  await form.locator('input').nth(2).fill(captcha);

  const loginResponsePromise = waitForApiResponse(page, '/users/login');
  await form.locator('button').last().click();
  const loginBody = await readSuccessfulApiResponse(await loginResponsePromise, 'login');
  const accessToken = loginBody.data?.token;
  assert.ok(accessToken, JSON.stringify(loginBody));
  await page.waitForURL(url => !url.pathname.includes('/login'));
  console.log('chrome_login=passed');

  const appRow = page.locator('tr').filter({ hasText: appName }).first();
  await appRow.waitFor({ state: 'visible' });
  await appRow.locator('button').first().click();
  await page.waitForURL(url => url.pathname === '/apps');

  const functionDataPromise = waitForApiResponse(page, '/function/data');
  await page.goto(new URL('/function', baseUrl).href, {
    waitUntil: 'domcontentloaded'
  });
  await readSuccessfulApiResponse(await functionDataPromise, 'load functions');

  await page.locator('.add-btn').click();
  const createDialog = page.locator('.n-dialog:visible').last();
  await createDialog.waitFor({ state: 'visible' });
  await createDialog.locator('input:visible').first().fill(functionName);
  assert.equal(await createDialog.locator('[role="switch"]').getAttribute('aria-checked'), 'false');
  await createDialog.locator('.n-base-selection').click();
  await page.locator('.n-base-select-option:visible').first().click();

  const createResponsePromise = waitForApiResponse(page, '/function/create');
  functionCreateAttempted = true;
  await createDialog.locator('.n-dialog__action button').last().click();
  const createResponse = await createResponsePromise;
  assert.equal(createResponse.request().postDataJSON().requires_auth, false);
  const createBody = await readSuccessfulApiResponse(createResponse, 'create function');
  createdFunctionId = createBody.data?.function_id || '';
  assert.ok(createdFunctionId, JSON.stringify(createBody));
  const functionItem = page.locator('.function-item').filter({ hasText: functionName });
  await functionItem.waitFor({ state: 'visible' });
  console.log(`function_created=${createdFunctionId}`);

  const editorInput = page.locator('.monaco-editor textarea').first();
  await editorInput.waitFor({ state: 'visible' });
  await page.locator('.n-modal-mask:visible').waitFor({ state: 'hidden' });
  await page
    .locator('.monaco-editor')
    .first()
    .click({ position: { x: 240, y: 100 } });
  await page.keyboard.press('Control+A');
  await page.keyboard.insertText(updatedCode);

  const publishButton = page.locator('.action-btn.publish-btn');
  await publishButton.waitFor({ state: 'visible' });
  const publishResponsePromise = waitForApiResponse(page, '/function/update_code');
  await publishButton.click();
  const publishResponse = await publishResponsePromise;
  assert.equal(publishResponse.request().postDataJSON().code, updatedCode);
  await readSuccessfulApiResponse(publishResponse, 'publish function');
  await page.locator('.action-btn.saved-btn').waitFor({ state: 'visible' });
  console.log('function_published=passed');

  let invoked = false;
  for (let attempt = 0; attempt < 30; attempt += 1) {
    const proxyResponsePromise = waitForApiResponse(page, '/function/proxy_test');
    await page.locator('.send-btn').click();
    const proxyBody = await readSuccessfulApiResponse(await proxyResponsePromise, 'invoke function');
    const statusCode = proxyBody.data?.status_code;
    let responseData;
    try {
      responseData = JSON.parse(proxyBody.data?.content || '{}').data;
    } catch {
      responseData = undefined;
    }
    if (statusCode === 200 && responseData === expectedResult) {
      invoked = true;
      break;
    }
    await page.waitForTimeout(500);
  }
  assert.equal(invoked, true, `published function never returned ${expectedResult}`);
  await page.locator('.response-content').filter({ hasText: expectedResult }).waitFor({ state: 'visible' });
  console.log(`public_function_invoked=${expectedResult}`);

  const functionUrl = (await page.locator('.address-text').textContent())?.trim();
  assert.ok(functionUrl, 'function URL was not rendered');
  const directFunctionUrl = new URL(functionUrl);
  directFunctionUrl.port = new URL(baseUrl).port;
  const publicPage = await browser.newPage({ ignoreHTTPSErrors: true });
  const publicResponse = await publicPage.goto(directFunctionUrl.href, { waitUntil: 'domcontentloaded' });
  assert.equal(publicResponse?.status(), 200, `public function returned ${publicResponse?.status()}`);
  assert.equal((await publicPage.textContent('body'))?.includes(expectedResult), true);
  await publicPage.close();
  console.log('public_function_anonymous_access=passed');

  await page.locator('.edit-btn').click();
  const editDialog = page.locator('.n-dialog:visible').last();
  await editDialog.waitFor({ state: 'visible' });
  const authSwitch = editDialog.locator('[role="switch"]');
  await authSwitch.waitFor({ state: 'visible' });
  assert.equal(await authSwitch.getAttribute('aria-checked'), 'false');
  await authSwitch.click();
  const updateMetaResponsePromise = waitForApiResponse(page, '/function/update_meta');
  await editDialog.locator('.n-dialog__action button').last().click();
  const updateMetaResponse = await updateMetaResponsePromise;
  assert.equal(updateMetaResponse.request().postDataJSON().requires_auth, true);
  await readSuccessfulApiResponse(updateMetaResponse, 'enable function authentication');
  await editDialog.waitFor({ state: 'hidden' });

  const protectedProxyResponsePromise = waitForApiResponse(page, '/function/proxy_test');
  await page.locator('.send-btn').click();
  const protectedProxyBody = await readSuccessfulApiResponse(
    await protectedProxyResponsePromise,
    'invoke protected function through console'
  );
  assert.equal(protectedProxyBody.data?.status_code, 200, JSON.stringify(protectedProxyBody));
  assert.equal(JSON.parse(protectedProxyBody.data?.content || '{}').data, expectedResult);
  console.log('protected_function_console_access=passed');

  const anonymousPage = await browser.newPage({ ignoreHTTPSErrors: true });
  const anonymousResponse = await anonymousPage.goto(directFunctionUrl.href, { waitUntil: 'domcontentloaded' });
  assert.equal(anonymousResponse?.status(), 401, `protected function returned ${anonymousResponse?.status()}`);
  assert.deepEqual(JSON.parse((await anonymousPage.textContent('body')) || '{}'), {
    code: 401,
    msg: 'Access token required',
    data: null
  });
  await anonymousPage.close();
  console.log('protected_function_anonymous_access=denied');

  const deletedFunctionId = createdFunctionId;
  deleted = await deleteFunctionThroughUi(page, functionName);
  assert.equal(deleted, true, 'created function was not deleted through the UI');
  const functionsAfterDeletePromise = waitForApiResponse(page, '/function/data');
  await page.reload({ waitUntil: 'domcontentloaded' });
  const functionsAfterDelete = await readSuccessfulApiResponse(
    await functionsAfterDeletePromise,
    'reload functions after delete'
  );
  assert.equal(
    functionsAfterDelete.data.data.some(item => item.function_id === deletedFunctionId),
    false,
    JSON.stringify(functionsAfterDelete)
  );
  assert.equal(await page.locator('.function-item').filter({ hasText: functionName }).count(), 0);
  console.log(`function_deleted=${deletedFunctionId}`);
  console.log('chrome_function_lifecycle=passed');

  const storageDataPromise = waitForApiResponse(page, '/storage/list_objects');
  await page.goto(new URL('/storage', baseUrl).href, {
    waitUntil: 'domcontentloaded'
  });
  await readSuccessfulApiResponse(await storageDataPromise, 'load storage');

  const uploadResponsePromise = waitForApiResponse(page, '/storage/upload_file');
  const storageAfterUploadPromise = waitForApiResponse(page, '/storage/list_objects');
  const uploadResponsesPromise = combineWaiters([uploadResponsePromise, storageAfterUploadPromise]);
  const fileChooserPromise = guardWaiter(page.waitForEvent('filechooser'));
  await page.locator('.storage-actions button').last().click();
  const fileChooser = await fileChooserPromise;
  storageUploadAttempted = true;
  await fileChooser.setFiles({
    name: storageFileName,
    mimeType: 'application/json',
    buffer: Buffer.from(storageContent)
  });
  const [uploadResponse, storageAfterUploadResponse] = await uploadResponsesPromise;
  await readSuccessfulApiResponse(uploadResponse, 'upload storage file');
  await readSuccessfulApiResponse(storageAfterUploadResponse, 'list storage after upload');
  const storageRow = page.locator('tr').filter({ hasText: storageFileName }).first();
  await storageRow.waitFor({ state: 'visible' });
  console.log(`storage_uploaded=${storageFileName}`);

  const downloadUrlBodyPromise = guardWaiter(
    waitForApiResponse(page, '/storage/get_download_url').then(response =>
      readSuccessfulApiResponse(response, 'get storage download URL')
    )
  );
  const popupPromise = guardWaiter(page.waitForEvent('popup'));
  activeDownloadWatcher = waitForDownloadFromPageOrPopup(page);
  const downloadResponsesPromise = combineWaiters([
    downloadUrlBodyPromise,
    popupPromise,
    activeDownloadWatcher.promise
  ]);
  try {
    await storageRow.locator('button').first().click();
    const [downloadUrlBody, downloadPage, download] = await downloadResponsesPromise;
    assert.ok(downloadUrlBody.data?.url, JSON.stringify(downloadUrlBody));
    assert.equal(download.suggestedFilename(), storageFileName);
    const downloadedPath = await download.path();
    assert.ok(downloadedPath, 'Chrome did not persist the downloaded storage file');
    assert.match(await readFile(downloadedPath, 'utf8'), new RegExp(storageMarker));
    if (!downloadPage.isClosed()) await downloadPage.close();
  } finally {
    activeDownloadWatcher.cancel(new Error('storage download flow completed'));
    activeDownloadWatcher = undefined;
  }
  console.log(`storage_download_verified=${storageMarker}`);

  storageDeleted = await deleteStorageFileThroughUi(page, storageFileName);
  assert.equal(storageDeleted, true, 'uploaded storage file was not deleted through the UI');
  console.log(`storage_deleted=${storageFileName}`);
  console.log('chrome_storage_lifecycle=passed');

  const collectionsPromise = waitForApiResponse(page, '/database/collections');
  await page.goto(new URL('/database', baseUrl).href, {
    waitUntil: 'domcontentloaded'
  });
  await readSuccessfulApiResponse(await collectionsPromise, 'load database collections');

  await page.locator('.collection-panel button.n-button--primary-type').first().click();
  const collectionDialog = page.locator('.n-dialog:visible').last();
  await collectionDialog.waitFor({ state: 'visible' });
  await collectionDialog.locator('input:visible').fill(collectionName);
  const createCollectionResponsePromise = waitForApiResponse(page, '/database/create_collection');
  const collectionsAfterCreatePromise = waitForApiResponse(page, '/database/collections');
  const createCollectionResponsesPromise = combineWaiters([
    createCollectionResponsePromise,
    collectionsAfterCreatePromise
  ]);
  collectionCreateAttempted = true;
  await collectionDialog.locator('.n-dialog__action button').last().click();
  const [createCollectionResponse, collectionsAfterCreateResponse] = await createCollectionResponsesPromise;
  await readSuccessfulApiResponse(createCollectionResponse, 'create database collection');
  await readSuccessfulApiResponse(collectionsAfterCreateResponse, 'list collections after create');
  let collectionItem = page.locator('.collection-panel .n-list-item').filter({ hasText: collectionName }).first();
  await collectionItem.waitFor({ state: 'visible' });
  console.log(`database_collection_created=${collectionName}`);

  await page.locator('.document-panel button.n-button--primary-type').first().click();
  const documentDialog = page.locator('.n-dialog:visible').last();
  await documentDialog.waitFor({ state: 'visible' });
  await replaceMonacoContent(
    page,
    documentDialog.locator('.monaco-editor'),
    JSON.stringify({ marker: documentMarker, version: 1 }, null, 2)
  );
  const insertDocumentResponsePromise = waitForApiResponse(page, '/database/insert_document');
  const documentsAfterInsertPromise = waitForApiResponse(page, '/database/documents');
  const insertDocumentResponsesPromise = combineWaiters([insertDocumentResponsePromise, documentsAfterInsertPromise]);
  await documentDialog.locator('.n-dialog__action button').last().click();
  const [insertDocumentResponse, documentsAfterInsertResponse] = await insertDocumentResponsesPromise;
  assert.deepEqual(insertDocumentResponse.request().postDataJSON().docData, {
    marker: documentMarker,
    version: 1
  });
  const insertDocumentBody = await readSuccessfulApiResponse(insertDocumentResponse, 'insert database document');
  const insertedDocumentId = insertDocumentBody.data?.inserted_id;
  assert.ok(insertedDocumentId, JSON.stringify(insertDocumentBody));
  const documentsAfterInsert = await readSuccessfulApiResponse(
    documentsAfterInsertResponse,
    'list documents after insert'
  );
  assert.equal(
    documentsAfterInsert.data.data.some(item => item._id === insertedDocumentId && item.marker === documentMarker),
    true,
    JSON.stringify(documentsAfterInsert)
  );
  let documentRow = await findDocumentRow(page, documentMarker);
  await documentRow.locator('button').first().click();
  console.log(`database_document_inserted=${insertedDocumentId}`);

  const updatedDocument = {
    _id: insertedDocumentId,
    marker: updatedDocumentMarker,
    version: 2
  };
  await replaceMonacoContent(
    page,
    page.locator('.operation-panel .monaco-editor'),
    JSON.stringify(updatedDocument, null, 2)
  );
  const updateDocumentResponsePromise = waitForApiResponse(page, '/database/update_document');
  const documentsAfterUpdatePromise = waitForApiResponse(page, '/database/documents');
  const updateDocumentResponsesPromise = combineWaiters([updateDocumentResponsePromise, documentsAfterUpdatePromise]);
  await page.locator('.operation-panel button.n-button--primary-type').click();
  const [updateDocumentResponse, documentsAfterUpdateResponse] = await updateDocumentResponsesPromise;
  assert.deepEqual(updateDocumentResponse.request().postDataJSON().docData, updatedDocument);
  await readSuccessfulApiResponse(updateDocumentResponse, 'update database document');
  const documentsAfterUpdate = await readSuccessfulApiResponse(
    documentsAfterUpdateResponse,
    'list documents after update'
  );
  assert.equal(
    documentsAfterUpdate.data.data.some(
      item => item._id === insertedDocumentId && item.marker === updatedDocumentMarker && item.version === 2
    ),
    true,
    JSON.stringify(documentsAfterUpdate)
  );
  documentRow = await findDocumentRow(page, updatedDocumentMarker);
  console.log(`database_document_updated=${insertedDocumentId}`);

  const deleteDocumentResponsePromise = waitForApiResponse(page, '/database/delete_document');
  const documentsAfterDeletePromise = waitForApiResponse(page, '/database/documents');
  const deleteDocumentResponsesPromise = combineWaiters([deleteDocumentResponsePromise, documentsAfterDeletePromise]);
  await documentRow.locator('button').last().click();
  await confirmVisibleDialog(page);
  const [deleteDocumentResponse, documentsAfterDeleteResponse] = await deleteDocumentResponsesPromise;
  await readSuccessfulApiResponse(deleteDocumentResponse, 'delete database document');
  const documentsAfterDelete = await readSuccessfulApiResponse(
    documentsAfterDeleteResponse,
    'list documents after delete'
  );
  assert.equal(
    documentsAfterDelete.data.data.some(item => item._id === insertedDocumentId),
    false,
    JSON.stringify(documentsAfterDelete)
  );
  console.log(`database_document_deleted=${insertedDocumentId}`);

  collectionItem = page.locator('.collection-panel .n-list-item').filter({ hasText: collectionName }).first();
  collectionDeleted = await deleteCollectionThroughUi(page, collectionName);
  assert.equal(collectionDeleted, true, 'created database collection was not deleted through the UI');
  assert.equal(await collectionItem.count(), 0);
  console.log(`database_collection_deleted=${collectionName}`);
  console.log('chrome_database_lifecycle=passed');
  console.log('chrome_full_lifecycle=passed');
} finally {
  activeDownloadWatcher?.cancel(new Error('browser cleanup started'));
  activeDownloadWatcher = undefined;
  if (page && functionCreateAttempted && !deleted && !page.isClosed()) {
    try {
      const cleanupFunctionsPromise = waitForApiResponse(page, '/function/data');
      await page.goto(new URL('/function', baseUrl).href, {
        waitUntil: 'domcontentloaded'
      });
      await cleanupFunctionsPromise;
      await deleteFunctionThroughUi(page, functionName);
    } catch (error) {
      console.error(`function_cleanup_failed=${error instanceof Error ? error.message : String(error)}`);
    }
  }
  if (page && storageUploadAttempted && !storageDeleted && !page.isClosed()) {
    try {
      const cleanupStoragePromise = waitForApiResponse(page, '/storage/list_objects');
      await page.goto(new URL('/storage', baseUrl).href, {
        waitUntil: 'domcontentloaded'
      });
      await cleanupStoragePromise;
      await deleteStorageFileThroughUi(page, storageFileName);
    } catch (error) {
      console.error(`storage_cleanup_failed=${error instanceof Error ? error.message : String(error)}`);
    }
  }
  if (page && collectionCreateAttempted && !collectionDeleted && !page.isClosed()) {
    try {
      const cleanupCollectionsPromise = waitForApiResponse(page, '/database/collections');
      await page.goto(new URL('/database', baseUrl).href, {
        waitUntil: 'domcontentloaded'
      });
      await cleanupCollectionsPromise;
      await deleteCollectionThroughUi(page, collectionName, true);
    } catch (error) {
      console.error(`database_cleanup_failed=${error instanceof Error ? error.message : String(error)}`);
    }
  }
  await browser.close();
}
