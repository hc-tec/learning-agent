import http from 'node:http';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const MAX_BODY_BYTES = 512 * 1024;
const PORT = Number(process.env.TOKUI_VALIDATOR_PORT || 5811);
const HOST = process.env.TOKUI_VALIDATOR_HOST || '127.0.0.1';
const SCRIPT_PATH = join(dirname(fileURLToPath(import.meta.url)), 'validate-tokui.mjs');

function readBody(req) {
  return new Promise((resolve, reject) => {
    let size = 0;
    let data = '';
    req.setEncoding('utf8');
    req.on('data', (chunk) => {
      size += Buffer.byteLength(chunk, 'utf8');
      if (size > MAX_BODY_BYTES) {
        reject(new Error(`request body exceeds ${MAX_BODY_BYTES} bytes`));
        req.destroy();
        return;
      }
      data += chunk;
    });
    req.on('end', () => resolve(data));
    req.on('error', reject);
  });
}

function writeJson(res, statusCode, payload) {
  res.writeHead(statusCode, { 'content-type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify(payload));
}

function runValidator(payload) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [SCRIPT_PATH], {
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true,
    });
    let stdout = '';
    let stderr = '';
    const timer = setTimeout(() => {
      child.kill();
      reject(new Error('TokUI validation timed out'));
    }, 10000);

    child.stdout.setEncoding('utf8');
    child.stderr.setEncoding('utf8');
    child.stdout.on('data', (chunk) => {
      stdout += chunk;
    });
    child.stderr.on('data', (chunk) => {
      stderr += chunk;
    });
    child.on('error', (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on('close', (code) => {
      clearTimeout(timer);
      if (code !== 0) {
        reject(new Error(stderr || `validator exited with code ${code}`));
        return;
      }
      try {
        resolve(JSON.parse(stdout || '{}'));
      } catch (error) {
        reject(error);
      }
    });
    child.stdin.end(JSON.stringify(payload));
  });
}

const server = http.createServer(async (req, res) => {
  if (req.method === 'GET' && req.url === '/health') {
    writeJson(res, 200, { ok: true });
    return;
  }
  if (req.method !== 'POST' || req.url !== '/validate') {
    writeJson(res, 404, { ok: false, errors: [{ message: 'Not found', code: 'NOT_FOUND', path: '' }] });
    return;
  }

  try {
    const raw = await readBody(req);
    const payload = raw ? JSON.parse(raw) : {};
    const result = await runValidator(payload);
    writeJson(res, 200, result);
  } catch (error) {
    writeJson(res, 500, {
      ok: false,
      parser_version: '',
      errors: [
        {
          message: error instanceof Error ? error.message : String(error),
          code: 'TOKUI_VALIDATOR_SERVER_ERROR',
          path: '',
        },
      ],
    });
  }
});

server.listen(PORT, HOST, () => {
  process.stdout.write(`TokUI validator server listening on http://${HOST}:${PORT}\n`);
});
