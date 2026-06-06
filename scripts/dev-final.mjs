import { execFileSync, spawn } from 'node:child_process';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, '..');
const port = Number(process.env.IOT_APP_PORT || 5001);
const appUrl = `http://127.0.0.1:${port}`;

let backend = null;
let opened = false;

function pythonPath() {
  return process.platform === 'win32'
    ? path.join(root, '.venv', 'Scripts', 'python.exe')
    : path.join(root, '.venv', 'bin', 'python');
}

function stopOldNuroAgroBackends() {
  if (process.platform !== 'win32') return;
  const script = `
    $targets = Get-CimInstance Win32_Process -Filter "name = 'python.exe'" -ErrorAction SilentlyContinue |
      Where-Object {
        $_.CommandLine -match 'run_iot.py|app_iot.py' -and
        $_.CommandLine -match 'NeuroAgro|YOLOv12|iMAGE PROCESSING PART'
      } |
      Select-Object -ExpandProperty ProcessId
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
  for (let attempt = 0; attempt < 90; attempt += 1) {
    if ((await requestStatus(`${appUrl}/admin`)) === 200) return true;
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
    backend.kill('SIGTERM');
  }
}

async function main() {
  console.log('Stopping old NuroAgro backend processes...');
  stopOldNuroAgroBackends();
  await new Promise((resolve) => setTimeout(resolve, 1200));

  console.log(`Starting NuroAgro at ${appUrl}...`);
  backend = spawn(pythonPath(), ['run_iot.py'], {
    cwd: root,
    env: { ...process.env, IOT_APP_PORT: String(port) },
    stdio: 'inherit',
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

  if (!(await waitForApp())) {
    console.error(`NuroAgro started, but /admin did not become ready at ${appUrl}.`);
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
