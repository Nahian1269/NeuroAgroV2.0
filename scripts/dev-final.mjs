import { execFileSync, spawn } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, '..');
const requestedPort = Number(process.env.IOT_APP_PORT || 5001);
let port = requestedPort;
let appUrl = '';
let healthUrl = '';

let backend = null;
let opened = false;

function setPort(nextPort) {
  port = nextPort;
  appUrl = `http://127.0.0.1:${port}`;
  healthUrl = `${appUrl}/api/health`;
}

setPort(port);

function pythonPath() {
  const venvPython = process.platform === 'win32'
    ? path.join(root, '.venv', 'Scripts', 'python.exe')
    : path.join(root, '.venv', 'bin', 'python');
  if (fs.existsSync(venvPython)) return venvPython;
  return process.platform === 'win32' ? 'python' : 'python3';
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

async function waitForApp() {
  for (let attempt = 0; attempt < 75; attempt += 1) {
    if ((await requestStatus(healthUrl)) === 200) return true;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  return false;
}

function openBrowser() {
  if (process.argv.includes('--no-open') || opened) return;
  opened = true;

  if (os.platform() === 'win32') {
    spawn('cmd', ['/c', 'start', '', appUrl], { detached: true, stdio: 'ignore' }).unref();
  } else if (os.platform() === 'darwin') {
    spawn('open', [appUrl], { detached: true, stdio: 'ignore' }).unref();
  } else {
    spawn('xdg-open', [appUrl], { detached: true, stdio: 'ignore' }).unref();
  }
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
  console.log(`Starting NuroAgro at ${appUrl}...`);
  backend = spawn(pythonPath(), ['run_iot.py'], {
    cwd: root,
    env: {
      ...process.env,
      IOT_APP_PORT: String(port),
      DISEASE_MODEL_PRELOAD: process.env.DISEASE_MODEL_PRELOAD || 'false',
      DISEASE_INFERENCE_SUBPROCESS: process.env.DISEASE_INFERENCE_SUBPROCESS || 'true',
      DISEASE_INFERENCE_TIMEOUT_SECONDS: process.env.DISEASE_INFERENCE_TIMEOUT_SECONDS || '110',
      WEATHER_TRANSFORMER_TIMEOUT_SECONDS: process.env.WEATHER_TRANSFORMER_TIMEOUT_SECONDS || '8',
    },
    stdio: 'inherit',
  });

  if (await waitForApp()) return true;
  stopBackend();
  await new Promise((resolve) => setTimeout(resolve, 1200));
  return false;
}

async function main() {
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
    console.error(`NuroAgro started, but ${healthUrl} did not become ready.`);
    console.error('Check the Python output above for errors.');
    process.exit(1);
  }

  console.log(`NuroAgro is ready: ${appUrl}`);
  openBrowser();
}

main().catch((error) => {
  console.error(error);
  stopBackend();
  process.exit(1);
});
