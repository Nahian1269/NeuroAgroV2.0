import { spawn } from 'node:child_process';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, '..');
const port = Number(process.env.IOT_APP_PORT || 5001);
const host = '127.0.0.1';
const appUrl = `http://${host}:${port}`;
const noOpen = process.argv.includes('--no-open');

let backend = null;
let opened = false;

function pythonPath() {
  if (process.platform === 'win32') {
    return path.join(root, '.venv', 'Scripts', 'python.exe');
  }
  return path.join(root, '.venv', 'bin', 'python');
}

function requestOk(url) {
  return new Promise((resolve) => {
    const request = http.get(url, { timeout: 1500 }, (response) => {
      response.resume();
      resolve(response.statusCode >= 200 && response.statusCode < 500);
    });
    request.on('timeout', () => {
      request.destroy();
      resolve(false);
    });
    request.on('error', () => resolve(false));
  });
}

async function waitForServer() {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    if (await requestOk(appUrl)) return true;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  return false;
}

function openBrowser(url) {
  if (noOpen || opened) return;
  opened = true;

  const platform = os.platform();
  if (platform === 'win32') {
    spawn('cmd', ['/c', 'start', '', url], { detached: true, stdio: 'ignore' }).unref();
    return;
  }
  if (platform === 'darwin') {
    spawn('open', [url], { detached: true, stdio: 'ignore' }).unref();
    return;
  }
  spawn('xdg-open', [url], { detached: true, stdio: 'ignore' }).unref();
}

function stopBackend() {
  if (backend && !backend.killed) {
    backend.kill('SIGTERM');
  }
}

async function main() {
  if (await requestOk(appUrl)) {
    console.log(`NuroAgro is already running: ${appUrl}`);
    openBrowser(appUrl);
    return;
  }

  const python = pythonPath();
  console.log('Starting NuroAgro backend...');
  backend = spawn(python, ['run_iot.py'], {
    cwd: root,
    env: { ...process.env, IOT_APP_PORT: String(port) },
    stdio: 'inherit',
  });

  backend.on('exit', (code) => {
    if (code && code !== 0) {
      console.log(`NuroAgro backend exited with code ${code}.`);
    }
  });

  process.on('SIGINT', () => {
    stopBackend();
    process.exit(0);
  });
  process.on('SIGTERM', () => {
    stopBackend();
    process.exit(0);
  });
  process.on('exit', stopBackend);

  const ready = await waitForServer();
  if (!ready) {
    console.error(`Could not reach NuroAgro at ${appUrl}. Check the Python backend logs above.`);
    process.exit(1);
  }

  console.log(`NuroAgro is ready: ${appUrl}`);
  openBrowser(appUrl);
}

main().catch((error) => {
  console.error(error);
  stopBackend();
  process.exit(1);
});
