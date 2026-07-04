import { createRequire } from 'node:module';
import { JSDOM } from 'jsdom';

const require = createRequire(import.meta.url);
const tokuiPkg = require('@jboltai/tokui/package.json');

const MAX_STDIN_BYTES = 512 * 1024;

function readStdin() {
  return new Promise((resolve, reject) => {
    let size = 0;
    let data = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (chunk) => {
      size += Buffer.byteLength(chunk, 'utf8');
      if (size > MAX_STDIN_BYTES) {
        reject(new Error(`input exceeds ${MAX_STDIN_BYTES} bytes`));
        process.stdin.destroy();
        return;
      }
      data += chunk;
    });
    process.stdin.on('end', () => resolve(data));
    process.stdin.on('error', reject);
  });
}

function normalizeError(error) {
  return {
    message: error instanceof Error ? error.message : String(error),
    code: 'TOKUI_RENDER_ERROR',
    path: '',
  };
}

function writeResult(result) {
  process.stdout.write(
    JSON.stringify({
      parser_version: tokuiPkg.version || '',
      ...result,
    }),
  );
}

async function main() {
  const raw = await readStdin();
  const payload = raw ? JSON.parse(raw) : {};
  const dsl = typeof payload.dsl === 'string' ? payload.dsl : '';
  if (!dsl.trim()) {
    writeResult({
      ok: false,
      errors: [{ message: 'TokUI DSL is empty', code: 'TOKUI_EMPTY_DSL', path: '' }],
    });
    return;
  }

  const dom = new JSDOM('<!doctype html><html><body><div id="tokui-root"></div></body></html>', {
    url: 'http://localhost/',
    pretendToBeVisual: true,
  });

  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  Object.defineProperty(globalThis, 'navigator', {
    value: dom.window.navigator,
    configurable: true,
  });
  globalThis.HTMLElement = dom.window.HTMLElement;
  globalThis.Event = dom.window.Event;
  globalThis.CustomEvent = dom.window.CustomEvent;

  try {
    const { TokUI } = await import('@jboltai/tokui');
    const ui = new TokUI({
      container: '#tokui-root',
      streaming: false,
      theme: payload.theme || 'default',
      locale: payload.locale || 'zh-CN',
    });
    ui.render(dsl);
    const root = dom.window.document.querySelector('#tokui-root');
    const childCount = root ? root.childNodes.length : 0;
    writeResult({
      ok: childCount > 0,
      errors: childCount > 0 ? [] : [{ message: 'TokUI rendered empty output', code: 'TOKUI_EMPTY_RENDER', path: '' }],
    });
  } catch (error) {
    writeResult({
      ok: false,
      errors: [normalizeError(error)],
    });
  } finally {
    dom.window.close();
  }
}

main().catch((error) => {
  process.stderr.write(error instanceof Error ? error.stack || error.message : String(error));
  process.exit(1);
});
