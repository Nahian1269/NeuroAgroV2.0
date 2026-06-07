import { execFileSync, spawn } from 'node:child_process';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, '..');
const requestedPort = Number(process.env.IOT_APP_PORT || 5001);
let port = requestedPort;
const host = '127.0.0.1';
let appUrl = '';
let healthUrl = '';
const noOpen = process.argv.includes('--no-open');

let backend = null;
let opened = false;

function setPort(nextPort) {
  port = nextPort;
  appUrl = `http://${host}:${port}`;
  healthUrl = `${appUrl}/api/health`;
}

setPort(port);

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
  for (let attempt = 0; attempt < 30; attempt += 1) {
    if (await requestOk(healthUrl)) return true;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  return false;
}

function stopOldNuroAgroBackends() {
  if (process.platform !== 'win32') return;
  const escapedRoot = root.replace(/'/g, "''");
  const script = `
    $rootPattern = [regex]::Escape('${escapedRoot}')
    $listenerTargets = @()
    $listeners = Get-NetTCPConnection -LocalPort ${port} -State Listen -ErrorAction SilentlyContinue |
      Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($processId in $listeners) {
      $process = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
      if ($process -and $process.Name -eq 'python.exe' -and $process.CommandLine -match 'run_iot.py|app_iot.py') {
        $listenerTargets += $processId
      }
    }
    $scriptTargets = Get-CimInstance Win32_Process -Filter "name = 'python.exe'" -ErrorAction SilentlyContinue |
      Where-Object {
        $_.CommandLine -match 'run_iot.py|app_iot.py'
      } |
      Select-Object -ExpandProperty ProcessId
    $pathTargets = Get-CimInstance Win32_Process -Filter "name = 'python.exe'" -ErrorAction SilentlyContinue |
      Where-Object {
        $_.CommandLine -match 'run_iot.py|app_iot.py' -and
        ($_.CommandLine -match $rootPattern -or $_.CommandLine -match 'NeuroAgro|YOLOv12|iMAGE PROCESSING PART')
      } |
      Select-Object -ExpandProperty ProcessId
    $targets = @($listenerTargets + $scriptTargets + $pathTargets) | Sort-Object -Unique
    foreach ($targetId in $targets) {
      Stop-Process -Id $targetId -Force -ErrorAction SilentlyContinue
    }
  `;
  try {
    execFileSync('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script], {
      stdio: 'ignore',
    });
  } catch {
    // Continue; backend startup will show if the port is still blocked.
  }
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
    if (process.platform === 'win32' && backend.pid) {
      try {
        execFileSync('taskkill', ['/PID', String(backend.pid), '/T', '/F'], { stdio: 'ignore' });
      } catch {
        backend.kill('SIGTERM');
      }
    } else {
      backend.kill('SIGTERM');
    }
  }
  backend = null;
}

async function startBackend(targetPort) {
  setPort(targetPort);
  const python = pythonPath();
  console.log(`Starting NuroAgro backend at ${appUrl}...`);
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

  if (await waitForServer()) return true;
  stopBackend();
  await new Promise((resolve) => setTimeout(resolve, 1200));
  return false;
}

async function main() {
  if (await requestOk(healthUrl)) {
    console.log(`NuroAgro is already running: ${appUrl}`);
    openBrowser(appUrl);
    return;
  }

  console.log('Stopping old NuroAgro backend processes...');
  stopOldNuroAgroBackends();
  await new Promise((resolve) => setTimeout(resolve, 1200));

  process.on('SIGINT', () => {
    stopBackend();
    process.exit(0);
  });
  process.on('SIGTERM', () => {
    stopBackend();
    process.exit(0);
  });
  process.on('exit', stopBackend);

  let ready = await startBackend(requestedPort);
  if (!ready && !process.env.IOT_APP_PORT) {
    const fallbackPort = requestedPort + 1;
    console.warn(`NuroAgro did not become healthy on port ${requestedPort}; retrying on ${fallbackPort}.`);
    ready = await startBackend(fallbackPort);
  }

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
