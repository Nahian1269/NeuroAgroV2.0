import { execFileSync, spawn } from 'node:child_process';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, '..');
const port = Number(process.env.IOT_APP_PORT || 5001);
const host = '127.0.0.1';
const noOpen = process.argv.includes('--no-open');

let backend = null;
let opened = false;

function pythonPath() {
  if (process.platform === 'win32') {
    return path.join(root, '.venv', 'Scripts', 'python.exe');
  }
  return path.join(root, '.venv', 'bin', 'python');
}

function requestStatus(url) {
  return new Promise((resolve) => {
    const request = http.get(url, { timeout: 1500 }, (response) => {
      response.resume();
      resolve(response.statusCode || 0);
    });
    request.on('timeout', () => {
      request.destroy();
      resolve(0);
    });
    request.on('error', () => resolve(0));
  });
}

async function isNuroAgroServer(url) {
  return (await requestStatus(`${url}/admin`)) === 200;
}

async function waitForServer(url) {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    if (await isNuroAgroServer(url)) return true;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  return false;
}

function clearStaleNuroAgroPort() {
  if (process.platform !== 'win32') return;
  const script = `
    $listeners = Get-NetTCPConnection -LocalPort ${port} -ErrorAction SilentlyContinue |
      Where-Object { $_.State -eq 'Listen' } |
      Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($processId in $listeners) {
      $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
      if ($proc -and $proc.CommandLine -match 'run_iot.py|app_iot.py|YOLOv12|NeuroAgro') {
        Stop-Process -Id $processId -Force
      }
    }
  `;
  try {
    execFileSync('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script], {
      stdio: 'ignore',
    });
  } catch {
    // Startup below will print the useful error if cleanup could not free the port.
  }
}

function openBrowser(url) {
  if (noOpen || opened) return;
  opened = true;

  if (os.platform() === 'win32') {
    spawn('cmd', ['/c', 'start', '', url], { detached: true, stdio: 'ignore' }).unref();
    return;
  }
  if (os.platform() === 'darwin') {
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
  const appUrl = `http://${host}:${port}`;

  if (await isNuroAgroServer(appUrl)) {
    console.log(`NuroAgro is already running: ${appUrl}`);
    openBrowser(appUrl);
    return;
  }

  if ((await requestStatus(appUrl)) > 0) {
    console.log(`Port ${port} is occupied by a stale or wrong server. Cleaning it up...`);
    clearStaleNuroAgroPort();
    await new Promise((resolve) => setTimeout(resolve, 1200));
  }

  console.log(`Starting NuroAgro backend on ${appUrl}...`);
  backend = spawn(pythonPath(), ['run_iot.py'], {
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

  const ready = await waitForServer(appUrl);
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
