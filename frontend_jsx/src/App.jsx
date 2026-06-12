import { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Bell,
  BookOpen,
Camera,
  CheckCircle2,
  ChevronRight,
  CircleOff,
  CloudSun,
  Cpu,
  Database,
  Droplets,
  Eye,
  Edit3,
Fish,
  Gauge,
  History,
Globe2,
  Home,
  Leaf,
  Lightbulb,
  LineChart,
  Lock,
  LogIn,
  LogOut,
  MapPin,
  MessageCircle,
  MessageSquare,
Microscope,
  Moon,
  Plus,
  Power,
  RefreshCcw,
  Save,
  Search,
  Send,
Settings,
  ShieldCheck,
  SlidersHorizontal,
  Sprout,
  Sun,
  Thermometer,
  Trash2,
  Upload,
  User,
  UserCheck,
  UserPlus,
  Users,
  Waves,
  Wind,
  Zap
} from 'lucide-react';
import appLogo from './assets/Picture1.png';

const LOCAL_BACKEND_BASE = 'http://127.0.0.1:5001';

function resolveApiBase() {
  const configuredBase = import.meta.env.VITE_API_BASE;
  if (typeof window === 'undefined') return '';

  const localHosts = new Set(['127.0.0.1', 'localhost', '0.0.0.0']);
  const frontendDevPorts = new Set(['3000', '5173', '5174', '5175', '5176']);
  const { protocol, hostname, port } = window.location;
  const isLocalFrontendDev = localHosts.has(hostname) && frontendDevPorts.has(port);

  if (protocol === 'file:' || isLocalFrontendDev) {
    return configuredBase ? configuredBase.replace(/\/$/, '') : LOCAL_BACKEND_BASE;
  }

  if (configuredBase && !localHosts.has(hostname)) return configuredBase.replace(/\/$/, '');
  return '';
}

const API_BASE = resolveApiBase();
const API_KEY = import.meta.env.VITE_DEVICE_API_KEY || '';
const SUPABASE_CONFIGURED = Boolean(import.meta.env.VITE_SUPABASE_URL && import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY);
const PROJECT_KEY = 'nuroagro_project';

const emptyAuthForm = {
  username: '',
  email: '',
  password: '',
  passwordConfirm: '',
  deviceId: '',
  fullName: '',
  organization: ''
};

const emptyProjectForm = {
  name: '',
  area: '',
  latitude: '',
  longitude: '',
  climate: 'hybrid',
  stories: '4',
  waterSystem: 'hybrid',
  cropGoal: 'leafy greens',
  weather: 'temperate',
  notes: ''
};

const emptyAdminUserForm = {
  username: '',
  email: '',
  password: '',
  deviceId: '',
  farmName: '',
  plantType: '',
  approvalStatus: 'accepted'
};

const emptyWeatherData = {
  records: [],
  latest_prediction: null,
  latest_realtime: null,
  latest_training_run: null
};
const emptyHistoryData = {
  sensor_readings: [],
  weather_records: [],
  disease_detections: [],
  recommendations: [],
  notifications: [],
  weather_training_runs: []
};

const emptyProfileForm = {
  fullName: '',
  phone: '',
  profileNotes: '',
  farmName: '',
  plantType: '',
  farmSize: '',
  latitude: '',
  longitude: ''
};

const emptyForumForm = {
  title: '',
  category: 'general',
  plantType: '',
  content: ''
};

const cropOptions = ['Lettuce', 'Basil', 'Spinach', 'Tomato', 'Strawberry', 'Pak choi', 'Mint', 'Cucumber'];
const fishOptions = ['Tilapia fry', 'Guppy', 'Molly', 'Zebra danio', 'Goldfish juveniles'];
const systemOptions = ['hydroponic', 'aquaponic', 'aeroponic', 'hybrid', 'soil'];
const modeOptions = ['hybrid', 'vertical', 'traditional', 'hydroponic', 'aquaponic', 'aeroponic'];
const DISEASE_UPLOAD_MAX_EDGE = 1280;
const DISEASE_UPLOAD_JPEG_QUALITY = 0.82;
const DISEASE_UPLOAD_SKIP_BYTES = 1400 * 1024;

function optionalNumber(value) {
  if (value === '' || value === null || value === undefined) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function initialPageFromPath() {
  const path = window.location.pathname.toLowerCase();
  if (path.startsWith('/admin')) return 'admin';
  if (path.startsWith('/disease')) return 'disease';
  if (path.startsWith('/history')) return 'history';
  if (path.startsWith('/profile')) return 'profile';
  if (path.startsWith('/chat')) return 'chat';
  if (path.startsWith('/community')) return 'community';
  if (path.startsWith('/manual')) return 'manual';
  if (path.startsWith('/projects') || path.startsWith('/setup')) return 'projects';
  if (path.startsWith('/dashboard')) return 'dashboard';
  if (path.startsWith('/login') || path.startsWith('/register')) return 'auth';
  return 'home';
}

function initialTheme() {
  if (typeof window === 'undefined') return 'dark';
  const saved = window.localStorage.getItem('nuroagro_theme');
  if (saved === 'light' || saved === 'dark') return saved;
  return window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

async function imageBitmapFromFile(file) {
  if ('createImageBitmap' in window) {
    return createImageBitmap(file);
  }
  return new Promise((resolve, reject) => {
    const image = new Image();
    const url = URL.createObjectURL(file);
    image.onload = () => {
      URL.revokeObjectURL(url);
      resolve(image);
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('Could not read image'));
    };
    image.src = url;
  });
}

async function prepareDiseaseUpload(file) {
  if (!file?.type?.startsWith('image/') || file.type === 'image/gif') return file;
  try {
    const source = await imageBitmapFromFile(file);
    const width = source.width;
    const height = source.height;
    const longest = Math.max(width, height);
    if (longest <= DISEASE_UPLOAD_MAX_EDGE && file.size <= DISEASE_UPLOAD_SKIP_BYTES) {
      source.close?.();
      return file;
    }

    const scale = Math.min(1, DISEASE_UPLOAD_MAX_EDGE / longest);
    const targetWidth = Math.max(1, Math.round(width * scale));
    const targetHeight = Math.max(1, Math.round(height * scale));
    const canvas = document.createElement('canvas');
    canvas.width = targetWidth;
    canvas.height = targetHeight;
    const context = canvas.getContext('2d');
    context.drawImage(source, 0, 0, targetWidth, targetHeight);
    source.close?.();

    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', DISEASE_UPLOAD_JPEG_QUALITY));
    if (!blob || (file.type === 'image/jpeg' && blob.size >= file.size)) return file;
    const baseName = file.name.replace(/\.[^.]+$/, '') || 'plant-scan';
    return new File([blob], `${baseName}_scan.jpg`, { type: 'image/jpeg', lastModified: Date.now() });
  } catch {
    return file;
  }
}

export default function App() {
  const [page, setPage] = useState(initialPageFromPath());
  const [theme, setTheme] = useState(initialTheme);
  const [authMode, setAuthMode] = useState('login');
  const [authForm, setAuthForm] = useState(emptyAuthForm);
  const [authError, setAuthError] = useState('');
  const [authNotice, setAuthNotice] = useState('');
  const [user, setUser] = useState(null);
  const [deviceId, setDeviceId] = useState('ESP32_001');
  const [readings, setReadings] = useState([]);
  const [status, setStatus] = useState(null);
  const [recommendations, setRecommendations] = useState([]);
  const [analysis, setAnalysis] = useState(null);
  const [notifications, setNotifications] = useState([]);
  const [project, setProject] = useState(loadProject());
  const [projectForm, setProjectForm] = useState(project || emptyProjectForm);
  const [adminPassword, setAdminPassword] = useState('');
  const [adminData, setAdminData] = useState(null);
  const [adminUserForm, setAdminUserForm] = useState(emptyAdminUserForm);
  const [adminMessage, setAdminMessage] = useState('');
  const [diseaseResult, setDiseaseResult] = useState(null);
  const [diseaseHistory, setDiseaseHistory] = useState([]);
  const [weatherData, setWeatherData] = useState(emptyWeatherData);
  const [geoWeatherStatus, setGeoWeatherStatus] = useState(null);
  const [historyData, setHistoryData] = useState(emptyHistoryData);
  const [profileForm, setProfileForm] = useState(emptyProfileForm);
  const [profileDashboard, setProfileDashboard] = useState(null);
  const [chatMessages, setChatMessages] = useState([]);
  const [chatText, setChatText] = useState('');
  const [communityPosts, setCommunityPosts] = useState([]);
  const [forumForm, setForumForm] = useState(emptyForumForm);
  const [replyDrafts, setReplyDrafts] = useState({});
  const [adminThreads, setAdminThreads] = useState([]);
  const [adminThread, setAdminThread] = useState(null);
  const [adminChatText, setAdminChatText] = useState('');
  const [supabaseStatus, setSupabaseStatus] = useState({ configured: SUPABASE_CONFIGURED, ok: false });
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(false);

  const latest = readings[0];
  const health = useMemo(() => getHealth(latest, status), [latest, status]);
  const projectAdvice = useMemo(() => analyzeProject(project || projectForm), [project, projectForm]);
  const hardware = useMemo(() => buildHardware(latest, status), [latest, status]);
  const searchOptions = useMemo(() => buildSearchOptions(user), [user]);

  function openAuth(mode) {
    setAuthMode(mode);
    setAuthError('');
    setAuthNotice('');
    setPage('auth');
  }

  function applySession(data) {
    const nextUser = data?.user ? { ...data.user, devices: data.devices || [] } : null;
    setUser(nextUser);
    if (nextUser) setProfileForm(profileToForm(nextUser));
    if (data?.active_device_id) setDeviceId(data.active_device_id);
    return data?.active_device_id || deviceId;
  }

  async function apiFetch(path, options = {}) {
    const headers = options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' };
    return fetch(`${API_BASE}${path}`, {
      credentials: 'include',
      ...options,
      headers: { ...headers, ...(options.headers || {}) }
    });
  }

  function apiTarget(path) {
    const origin = typeof window !== 'undefined' ? window.location.origin : '';
    return `${API_BASE || origin}${path}`;
  }

  function goToSearchItem(item) {
    if (!item) return;
    if (item.requiresAuth && !user) {
      openAuth('login');
      return;
    }
    setPage(item.page);
    setSearchTerm('');
  }

  async function loadSupabaseStatus() {
    try {
      const response = await apiFetch('/api/supabase/status');
      if (response.ok) setSupabaseStatus(await response.json());
    } catch {
      setSupabaseStatus((current) => ({ ...current, ok: false }));
    }
  }

  async function loadSession() {
    try {
      const response = await apiFetch('/api/auth/me');
      if (!response.ok) return;
      const data = await response.json();
      const activeDevice = applySession(data);
      const loadedProject = await loadProjects();
      setPage(loadedProject || project ? 'dashboard' : 'projects');
      await refresh(activeDevice, true);
    } catch {
      setUser(null);
    }
  }

  async function submitAuth(event) {
    event.preventDefault();
    setLoading(true);
    setAuthError('');
    setAuthNotice('');

    const payload = authMode === 'login'
      ? { identifier: authForm.username || authForm.email, password: authForm.password }
      : {
          username: authForm.username,
          email: authForm.email,
          password: authForm.password,
          password_confirm: authForm.passwordConfirm,
          device_id: authForm.deviceId,
          farm_name: authForm.organization || authForm.fullName || 'NuroAgro Farm',
          plant_type: cropOptions[0]
        };

    try {
      const response = await apiFetch(`/api/auth/${authMode === 'login' ? 'login' : 'register'}`, {
        method: 'POST',
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (!response.ok) {
        setAuthError(data.error || 'Authentication failed');
        return;
      }
      if (data.status === 'pending_approval') {
        setAuthForm(emptyAuthForm);
        setAuthNotice(data.message || 'Account created and waiting for admin acceptance.');
        setAuthMode('login');
        return;
      }
      const activeDevice = applySession(data);
      setAuthForm(emptyAuthForm);
      const loadedProject = await loadProjects();
      setPage(loadedProject || project ? 'dashboard' : 'projects');
      await refresh(activeDevice, true);
    } catch {
      setAuthError('Could not reach the NuroAgro server.');
    } finally {
      setLoading(false);
    }
  }

  async function logout() {
    await apiFetch('/api/auth/logout', { method: 'POST' });
    setUser(null);
    setReadings([]);
    setStatus(null);
    setRecommendations([]);
    setNotifications([]);
    setDiseaseHistory([]);
    setWeatherData(emptyWeatherData);
    setGeoWeatherStatus(null);
    setHistoryData(emptyHistoryData);
    setProfileForm(emptyProfileForm);
    setProfileDashboard(null);
    setChatMessages([]);
    setChatText('');
    setCommunityPosts([]);
    setForumForm(emptyForumForm);
    setReplyDrafts({});
    setPage('home');
  }

  async function refresh(targetDeviceId = deviceId, force = false) {
    if (!force && !user) return;
    setLoading(true);
    try {
      const [sensorResponse, statusResponse, recResponse, notificationResponse, weatherResponse, diseaseResponse] = await Promise.all([
        apiFetch(`/api/sensor-data/${targetDeviceId}?limit=1&hours=96`),
        apiFetch(`/api/device-status/${targetDeviceId}`),
        apiFetch(`/api/recommendations/${targetDeviceId}?limit=18`),
        apiFetch('/api/notifications'),
        apiFetch(`/api/weather/${targetDeviceId}?limit=72`),
        apiFetch(`/api/disease-detections/${targetDeviceId}?limit=12`)
      ]);

      setReadings(sensorResponse.ok ? (await sensorResponse.json()).readings || [] : []);
      setStatus(statusResponse.ok ? await statusResponse.json() : null);
      setRecommendations(recResponse.ok ? (await recResponse.json()).recommendations || [] : []);
      setNotifications(notificationResponse.ok ? await notificationResponse.json() : []);
      const nextWeatherData = weatherResponse.ok ? await weatherResponse.json() : emptyWeatherData;
      setWeatherData(nextWeatherData);
      setGeoWeatherStatus(nextWeatherData.geo_status || null);
      setDiseaseHistory(diseaseResponse.ok ? (await diseaseResponse.json()).detections || [] : []);
    } finally {
      setLoading(false);
    }
  }

  async function loadProjects() {
    try {
      const response = await apiFetch('/api/projects');
      if (!response.ok) return null;
      const data = await response.json();
      const firstProject = data.projects?.[0] || null;
      if (firstProject) {
        setProject(firstProject);
        localStorage.setItem(PROJECT_KEY, JSON.stringify(firstProject));
        setProjectForm(projectToForm(firstProject));
      } else {
        setProject(null);
        localStorage.removeItem(PROJECT_KEY);
        setProjectForm(emptyProjectForm);
      }
      return firstProject;
    } catch {
      return null;
    }
  }

  async function saveProject(event) {
    event.preventDefault();
    const nextProject = {
      id: project?.id,
      ...projectForm,
      area: optionalNumber(projectForm.area),
      stories: Number(projectForm.stories || 1),
      latitude: optionalNumber(projectForm.latitude),
      longitude: optionalNumber(projectForm.longitude),
      createdAt: project?.createdAt || new Date().toISOString()
    };

    if (user) {
      const response = await apiFetch('/api/projects', {
        method: 'POST',
        body: JSON.stringify(nextProject)
      });
      if (response.ok) {
        const data = await response.json();
        setProject(data.project);
        setProjectForm(projectToForm(data.project));
        localStorage.setItem(PROJECT_KEY, JSON.stringify(data.project));
      } else {
        setProject(nextProject);
        localStorage.setItem(PROJECT_KEY, JSON.stringify(nextProject));
      }
    }
    setPage('dashboard');
    await refresh(deviceId, true);
  }

  async function deleteProject() {
    if (!project?.id) {
      setProject(null);
      setProjectForm(emptyProjectForm);
      localStorage.removeItem(PROJECT_KEY);
      return;
    }

    setLoading(true);
    try {
      const response = await apiFetch(`/api/projects/${project.id}`, { method: 'DELETE' });
      if (response.ok) {
        setProject(null);
        setProjectForm(emptyProjectForm);
        localStorage.removeItem(PROJECT_KEY);
        setPage('projects');
      }
    } finally {
      setLoading(false);
    }
  }

  async function loadHistory(targetDeviceId = deviceId) {
    try {
      const response = await apiFetch(`/api/history/${targetDeviceId}?limit=500`);
      setHistoryData(response.ok ? await response.json() : emptyHistoryData);
    } catch {
      setHistoryData(emptyHistoryData);
    }
  }

  async function loadProfile() {
    try {
      const [profileResponse, dashboardResponse] = await Promise.all([
        apiFetch('/api/profile'),
        apiFetch('/api/profile/dashboard')
      ]);
      if (profileResponse.ok) {
        const data = await profileResponse.json();
        setProfileForm(profileToForm(data.profile));
        setUser((current) => current ? { ...current, ...data.profile, devices: current.devices || [] } : data.profile);
      }
      if (dashboardResponse.ok) setProfileDashboard(await dashboardResponse.json());
    } catch {
      setProfileDashboard(null);
    }
  }

  async function saveProfile(event) {
    event.preventDefault();
    setLoading(true);
    try {
      const response = await apiFetch('/api/profile', {
        method: 'PUT',
        body: JSON.stringify({
          full_name: profileForm.fullName,
          phone: profileForm.phone,
          profile_notes: profileForm.profileNotes,
          farm_name: profileForm.farmName,
          plant_type: profileForm.plantType,
          farm_size: optionalNumber(profileForm.farmSize),
          latitude: optionalNumber(profileForm.latitude),
          longitude: optionalNumber(profileForm.longitude)
        })
      });
      if (response.ok) await loadProfile();
    } finally {
      setLoading(false);
    }
  }

  async function loadChat() {
    try {
      const response = await apiFetch('/api/chat');
      if (response.ok) setChatMessages((await response.json()).messages || []);
    } catch {
      setChatMessages([]);
    }
  }

  async function sendChat(event) {
    event.preventDefault();
    const message = chatText.trim();
    if (!message) return;
    setChatText('');
    const response = await apiFetch('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ message })
    });
    if (response.ok) await loadChat();
  }

  async function loadCommunity() {
    try {
      const response = await apiFetch('/api/community/posts');
      if (response.ok) setCommunityPosts((await response.json()).posts || []);
    } catch {
      setCommunityPosts([]);
    }
  }

  async function createCommunityPost(event) {
    event.preventDefault();
    if (!forumForm.title.trim() || !forumForm.content.trim()) return;
    const response = await apiFetch('/api/community/posts', {
      method: 'POST',
      body: JSON.stringify({
        title: forumForm.title,
        category: forumForm.category,
        plant_type: forumForm.plantType,
        content: forumForm.content
      })
    });
    if (response.ok) {
      setForumForm(emptyForumForm);
      await loadCommunity();
    }
  }

  async function sendCommunityReply(postId) {
    const content = (replyDrafts[postId] || '').trim();
    if (!content) return;
    const response = await apiFetch(`/api/community/posts/${postId}/replies`, {
      method: 'POST',
      body: JSON.stringify({ content })
    });
    if (response.ok) {
      setReplyDrafts((current) => ({ ...current, [postId]: '' }));
      await loadCommunity();
    }
  }
  async function useCurrentLocation() {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition((position) => {
      setProjectForm((current) => ({
        ...current,
        latitude: position.coords.latitude.toFixed(5),
        longitude: position.coords.longitude.toFixed(5)
      }));
    });
  }

  function pushLatestPrediction(prediction) {
    if (!prediction) return;
    setWeatherData((current) => {
      const remaining = (current.records || []).filter((item) => item.id !== prediction.id);
      return {
        ...current,
        latest_prediction: prediction,
        records: [prediction, ...remaining].slice(0, 72)
      };
    });
  }

  async function loadWeather(targetDeviceId = deviceId) {
    try {
      const response = await apiFetch(`/api/weather/${targetDeviceId}?limit=72`);
      if (response.ok) {
        const data = await response.json();
        setWeatherData(data);
        setGeoWeatherStatus(data.geo_status || null);
      }
    } catch {
      setWeatherData((current) => ({ ...current }));
    }
  }

  async function loadDiseaseHistory(targetDeviceId = deviceId) {
    try {
      const response = await apiFetch(`/api/disease-detections/${targetDeviceId}?limit=12`);
      if (response.ok) setDiseaseHistory((await response.json()).detections || []);
    } catch {
      setDiseaseHistory([]);
    }
  }

  async function runSensorAnalysis(silent = false) {
    if (!silent) setLoading(true);
    try {
      const response = await apiFetch(`/api/farm-analysis/${deviceId}?hours=96&limit=180`, { method: 'POST' });
      if (response.ok) {
        const result = await response.json();
        setAnalysis(result);
        pushLatestPrediction(result.weather);
        await refresh(deviceId, true);
      }
    } finally {
      if (!silent) setLoading(false);
    }
  }

  async function runWeatherPrediction(silent = false) {
    if (!silent) setLoading(true);
    try {
      const response = await apiFetch(`/api/weather/predict/${deviceId}`, { method: 'POST' });
      if (response.ok) {
        const result = await response.json();
        pushLatestPrediction(result.prediction);
        await refresh(deviceId, true);
      }
    } finally {
      if (!silent) setLoading(false);
    }
  }

  async function syncGeoWeather(force = false) {
    setLoading(true);
    try {
      const response = await apiFetch(`/api/weather/geo/${deviceId}${force ? '?force=1' : ''}`, { method: 'POST' });
      const result = await response.json().catch(() => null);
      setGeoWeatherStatus(result || { status: response.ok ? 'success' : 'error' });
      if (response.ok) await loadWeather(deviceId);
    } catch (error) {
      setGeoWeatherStatus({ status: 'error', error: error?.message || 'Could not sync geolocation weather.' });
    } finally {
      setLoading(false);
    }
  }

  async function runWeatherTick() {
    try {
      const response = await apiFetch(`/api/weather/tick/${deviceId}`, { method: 'POST' });
      if (response.ok) {
        const result = await response.json();
        pushLatestPrediction(result.prediction);
        await loadWeather(deviceId);
      }
    } catch {
      // Background weather notifications should never interrupt the operator UI.
    }
  }

  async function trainWeatherModel() {
    setLoading(true);
    try {
      const response = await apiFetch(`/api/weather/train/${deviceId}`, { method: 'POST' });
      if (response.ok) {
        const result = await response.json();
        setWeatherData((current) => ({ ...current, latest_training_run: result.training_run || result.training }));
        await refresh(deviceId, true);
      }
    } finally {
      setLoading(false);
    }
  }

  async function sendCommand(command, extra = {}) {
    await apiFetch('/api/device-command', {
      method: 'POST',
      headers: API_KEY ? { 'X-API-Key': API_KEY } : {},
      body: JSON.stringify({ device_id: deviceId, command, ...extra })
    });
    await refresh(deviceId, true);
  }

  async function updateDeviceStatus(updates) {
    await apiFetch(`/api/device-status/${deviceId}`, {
      method: 'PUT',
      body: JSON.stringify(updates)
    });
    await refresh(deviceId, true);
  }

  async function seedVirtualFarm() {
    if (!user) {
      openAuth('login');
      return;
    }
    setLoading(true);
    try {
      const response = await apiFetch(`/api/demo/seed/${deviceId}`, { method: 'POST' });
      if (response.ok) {
        const data = await response.json();
        if (data.device?.device_id) setDeviceId(data.device.device_id);
        pushLatestPrediction(data.weather_prediction);
        await refresh(data.device?.device_id || deviceId, true);
        setPage('dashboard');
      }
    } finally {
      setLoading(false);
    }
  }

  async function submitDiseaseImage(event) {
    event.preventDefault();
    const image = event.currentTarget.elements.image.files[0];
    if (!image || !image.size) {
      setDiseaseResult({ error: 'Please take or select a plant image first.' });
      return;
    }
    setLoading(true);
    setDiseaseResult(null);
    const uploadImage = await prepareDiseaseUpload(image);
    const data = new FormData();
    data.append('image', uploadImage);
    data.append('device_id', deviceId);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 120000);
    try {
      const response = await apiFetch('/api/disease-detection', { method: 'POST', body: data, signal: controller.signal });
      const result = await response.json();
      setDiseaseResult(response.ok ? result : { error: result.error || 'Disease detection failed.' });
      if (response.ok) {
        await loadDiseaseHistory(deviceId);
      }
    } catch (error) {
      setDiseaseResult({
        error: error.name === 'AbortError'
          ? 'Disease analysis is taking too long. Try a smaller, clearer image and scan again.'
          : 'Could not upload image for analysis.'
      });
    } finally {
      clearTimeout(timeout);
      setLoading(false);
    }
  }

  async function requestCameraScan() {
    setLoading(true);
    try {
      await sendCommand('camera_scan');
      await loadDiseaseHistory(deviceId);
    } finally {
      setLoading(false);
    }
  }

  async function loadAdmin(event) {
    event?.preventDefault();
    setLoading(true);
    setAdminMessage('');
    try {
      const response = await apiFetch('/api/admin/overview', {
        headers: { 'X-Admin-Password': adminPassword }
      });
      const data = await response.json();
      if (response.ok) {
        setAdminData(data);
        await loadAdminThreads();
      } else {
        setAdminData({ error: data.error || 'Admin login failed' });
      }
    } catch (error) {
      setAdminData({
        error: `Admin API request failed. Page: ${window.location.origin}. API: ${apiTarget('/api/admin/overview')}. ${error.message || 'Network request blocked.'}`
      });
    } finally {
      setLoading(false);
    }
  }

  async function adminCreateUser(event) {
    event.preventDefault();
    setLoading(true);
    setAdminMessage('');
    try {
      const response = await apiFetch('/api/admin/users', {
        method: 'POST',
        headers: { 'X-Admin-Password': adminPassword },
        body: JSON.stringify({
          username: adminUserForm.username,
          email: adminUserForm.email,
          password: adminUserForm.password,
          device_id: adminUserForm.deviceId,
          farm_name: adminUserForm.farmName,
          plant_type: adminUserForm.plantType,
          approval_status: adminUserForm.approvalStatus
        })
      });
      const data = await response.json();
      if (!response.ok) {
        setAdminMessage(data.error || 'Could not create user.');
        return;
      }
      setAdminUserForm(emptyAdminUserForm);
      setAdminMessage(`Created user ${data.user?.username || adminUserForm.username}.`);
      await loadAdmin();
    } catch {
      setAdminMessage('Admin create-user API could not be reached. Open http://127.0.0.1:5001/admin and try again.');
    } finally {
      setLoading(false);
    }
  }

  async function adminUserAction(userId, action) {
    setAdminMessage('');
    const method = action === 'delete' ? 'DELETE' : 'PATCH';
    const response = await apiFetch(`/api/admin/users/${userId}`, {
      method,
      headers: { 'X-Admin-Password': adminPassword },
      body: method === 'PATCH' ? JSON.stringify({ approval_status: action }) : undefined
    });
    if (response.ok) {
      const overview = await apiFetch('/api/admin/overview', {
        headers: { 'X-Admin-Password': adminPassword }
      });
      if (overview.ok) setAdminData(await overview.json());
      setAdminMessage(action === 'delete' ? 'User deleted.' : `User marked ${action}.`);
    }
  }

  async function loadAdminThreads() {
    if (!adminPassword) return;
    try {
      const response = await apiFetch('/api/admin/chat', {
        headers: { 'X-Admin-Password': adminPassword }
      });
      if (response.ok) setAdminThreads((await response.json()).threads || []);
    } catch {
      setAdminThreads([]);
    }
  }

  async function openAdminThread(userId) {
    const response = await apiFetch(`/api/admin/chat/${userId}`, {
      headers: { 'X-Admin-Password': adminPassword }
    });
    if (response.ok) setAdminThread(await response.json());
  }

  async function sendAdminChat(event) {
    event.preventDefault();
    const message = adminChatText.trim();
    if (!message || !adminThread?.user?.id) return;
    setAdminChatText('');
    const response = await apiFetch(`/api/admin/chat/${adminThread.user.id}`, {
      method: 'POST',
      headers: { 'X-Admin-Password': adminPassword },
      body: JSON.stringify({ message })
    });
    if (response.ok) {
      await openAdminThread(adminThread.user.id);
      await loadAdminThreads();
    }
  }
  useEffect(() => {
    loadSupabaseStatus();
    loadSession();
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem('nuroagro_theme', theme);
  }, [theme]);

  useEffect(() => {
    if (!user) return undefined;
    refresh(deviceId, true);
    const timer = setInterval(() => refresh(deviceId, true), 15000);
    return () => clearInterval(timer);
  }, [deviceId, user?.id]);

  useEffect(() => {
    if (!user) return undefined;
    const weatherTimer = setInterval(() => runWeatherTick(), 30 * 60 * 1000);
    const analysisTimer = setInterval(() => runSensorAnalysis(true), 60 * 60 * 1000);
    return () => {
      clearInterval(weatherTimer);
      clearInterval(analysisTimer);
    };
  }, [deviceId, user?.id]);

  useEffect(() => {
    if (!user) return;
    if (page === 'history') loadHistory(deviceId);
    if (page === 'profile') loadProfile();
    if (page === 'chat') loadChat();
    if (page === 'community') loadCommunity();
  }, [page, deviceId, user?.id]);
  return (
    <main className="app-shell">
      <header className="topbar">
        <button className="brand" onClick={() => setPage(user ? 'dashboard' : 'home')}>
          <img src={appLogo} alt="NeuroAgro logo" />
          <span>
            <b>NeuroAgro</b>
            <small>Smart Farm OS</small>
          </span>
        </button>
        <nav className="nav-tabs" aria-label="Primary">
          <NavButton icon={<Home />} active={page === 'home'} title="Console" onClick={() => setPage('home')} />
          <NavButton icon={<Plus />} active={page === 'projects'} title="Project" onClick={() => user ? setPage('projects') : openAuth('login')} />
          <NavButton icon={<Gauge />} active={page === 'dashboard'} title="Dashboard" onClick={() => user ? setPage('dashboard') : openAuth('login')} />
          <NavButton icon={<History />} active={page === 'history'} title="History" onClick={() => user ? setPage('history') : openAuth('login')} />
          <NavButton icon={<Microscope />} active={page === 'disease'} title="Disease" onClick={() => user ? setPage('disease') : openAuth('login')} />
          <NavButton icon={<MessageCircle />} active={page === 'chat'} title="Chat" onClick={() => user ? setPage('chat') : openAuth('login')} />
          <NavButton icon={<BookOpen />} active={page === 'community'} title="Community" onClick={() => user ? setPage('community') : openAuth('login')} />
          <NavButton icon={<BookOpen />} active={page === 'manual'} title="Manual" onClick={() => setPage('manual')} />
          <NavButton icon={<User />} active={page === 'profile'} title="Profile" onClick={() => user ? setPage('profile') : openAuth('login')} />
          <NavButton icon={<ShieldCheck />} active={page === 'admin'} title="Admin" onClick={() => setPage('admin')} />
        </nav>
        <GlobalSearch
          value={searchTerm}
          setValue={setSearchTerm}
          options={searchOptions}
          onSelect={goToSearchItem}
        />
        <div className="auth-actions">
          <button
            className="icon-button theme-toggle"
            onClick={() => setTheme((current) => current === 'dark' ? 'light' : 'dark')}
            title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          {user ? (
            <>
              <span className="user-chip"><UserCheck size={16} /> {user.username}</span>
              <button className="icon-button" onClick={() => refresh(deviceId, true)} title="Refresh" aria-label="Refresh">
                <RefreshCcw size={18} className={loading ? 'spin' : ''} />
              </button>
              <button className="icon-button" onClick={logout} title="Logout" aria-label="Logout">
                <LogOut size={18} />
              </button>
            </>
          ) : (
            <>
              <button className="secondary-button small" onClick={() => openAuth('login')}><LogIn size={17} /> Login</button>
              <button className="primary-button small" onClick={() => openAuth('register')}><UserPlus size={17} /> Register</button>
            </>
          )}
        </div>
      </header>

      {page === 'home' && (
        <HomePage
          user={user}
          latest={latest}
          health={health}
          hardware={hardware}
          supabaseStatus={supabaseStatus}
          openAuth={openAuth}
          setPage={setPage}
        />
      )}
      {page === 'auth' && (
        <AuthPage
          mode={authMode}
          setMode={setAuthMode}
          form={authForm}
          setForm={setAuthForm}
          error={authError}
          notice={authNotice}
          loading={loading}
          onSubmit={submitAuth}
        />
      )}
      {page === 'projects' && user && (
        <ProjectPage
          form={projectForm}
          setForm={setProjectForm}
          project={project}
          advice={projectAdvice}
          onSubmit={saveProject}
          onDelete={deleteProject}
          useCurrentLocation={useCurrentLocation}
          user={user}
          supabaseStatus={supabaseStatus}
        />
      )}
      {page === 'dashboard' && user && (
        <DashboardPage
          user={user}
          project={project}
          advice={projectAdvice}
          deviceId={deviceId}
          setDeviceId={setDeviceId}
          latest={latest}
          readings={readings}
          status={status}
          health={health}
          hardware={hardware}
          recommendations={recommendations}
          notifications={notifications}
          analysis={analysis}
          weatherData={weatherData}
          geoWeatherStatus={geoWeatherStatus}
          diseaseHistory={diseaseHistory}
          runSensorAnalysis={runSensorAnalysis}
          runWeatherPrediction={runWeatherPrediction}
          syncGeoWeather={syncGeoWeather}
          trainWeatherModel={trainWeatherModel}
          sendCommand={sendCommand}
          updateDeviceStatus={updateDeviceStatus}
          seedVirtualFarm={seedVirtualFarm}
          loading={loading}
          setPage={setPage}
        />
      )}
      {page === 'history' && user && (
        <HistoryPage
          historyData={historyData}
          deviceId={deviceId}
          loading={loading}
          onRefresh={() => loadHistory(deviceId)}
        />
      )}
      {page === 'profile' && user && (
        <ProfilePage
          user={user}
          form={profileForm}
          setForm={setProfileForm}
          dashboard={profileDashboard}
          loading={loading}
          onSubmit={saveProfile}
          onRefresh={loadProfile}
        />
      )}
      {page === 'chat' && user && (
        <ChatPage
          messages={chatMessages}
          text={chatText}
          setText={setChatText}
          onSubmit={sendChat}
          onRefresh={loadChat}
        />
      )}
      {page === 'community' && user && (
        <CommunityPage
          posts={communityPosts}
          form={forumForm}
          setForm={setForumForm}
          replyDrafts={replyDrafts}
          setReplyDrafts={setReplyDrafts}
          onCreate={createCommunityPost}
          onReply={sendCommunityReply}
          onRefresh={loadCommunity}
        />
      )}
      {page === 'manual' && (
        <ManualPage
          user={user}
          setPage={setPage}
          openAuth={openAuth}
          seedVirtualFarm={seedVirtualFarm}
          loading={loading}
        />
      )}
      {page === 'disease' && user && (
        <DiseasePage
          result={diseaseResult}
          history={diseaseHistory}
          loading={loading}
          onSubmit={submitDiseaseImage}
          onCameraScan={requestCameraScan}
          deviceId={deviceId}
        />
      )}
      {page === 'admin' && (
        <AdminPage
          password={adminPassword}
          setPassword={setAdminPassword}
          data={adminData}
          loading={loading}
          onSubmit={loadAdmin}
          createForm={adminUserForm}
          setCreateForm={setAdminUserForm}
          message={adminMessage}
          onCreateUser={adminCreateUser}
          onAction={adminUserAction}
          adminThreads={adminThreads}
          adminThread={adminThread}
          onOpenThread={openAdminThread}
          adminChatText={adminChatText}
          setAdminChatText={setAdminChatText}
          onAdminChatSubmit={sendAdminChat}
        />
      )}
      <AppFooter setPage={setPage} user={user} theme={theme} />
    </main>
  );
}

function NavButton({ icon, active, title, onClick }) {
  return (
    <button className={active ? 'active' : ''} onClick={onClick} title={title} aria-label={title}>
      {icon}
    </button>
  );
}

function GlobalSearch({ value, setValue, options, onSelect }) {
  const normalized = value.trim().toLowerCase();
  const visibleOptions = normalized
    ? options.filter((item) => item.keywords.includes(normalized) || item.label.toLowerCase().includes(normalized)).slice(0, 6)
    : options.slice(0, 6);

  function submit(event) {
    event.preventDefault();
    if (!normalized) return;
    const match = options.find((item) => item.label.toLowerCase() === normalized)
      || options.find((item) => item.keywords.includes(normalized) || item.label.toLowerCase().includes(normalized));
    onSelect(match);
  }

  return (
    <form className="global-search" onSubmit={submit}>
      <Search size={16} />
      <input
        value={value}
        list="nuroagro-search-options"
        placeholder="Search"
        onChange={(event) => setValue(event.target.value)}
        aria-label="Search pages"
      />
      <datalist id="nuroagro-search-options">
        {visibleOptions.map((item) => <option key={item.label} value={item.label} />)}
      </datalist>
    </form>
  );
}

function ManualPage({ user, setPage, openAuth, seedVirtualFarm, loading }) {
  const pinRows = [
    ['DHT11', 'GPIO 4', '3.3V, GND'],
    ['Soil moisture', 'GPIO 34 ADC1', '3.3V analog, GND'],
    ['MQ-5', 'GPIO 35 ADC1', '5V sensor board, shared GND'],
    ['MQ-7', 'GPIO 32 ADC1', '5V sensor board, shared GND'],
    ['MQ-135', 'GPIO 33 ADC1', '5V sensor board, shared GND'],
    ['Raindrop analog', 'GPIO 39 ADC1', '3.3V/5V module, GND'],
    ['PIR motion', 'GPIO 23', '3.3V/5V module, GND'],
    ['Relay pump A', 'GPIO 12', 'External pump supply'],
    ['Optional relay pump B', 'GPIO 14', 'External pump supply'],
    ['Optional relay UV/light', 'GPIO 13', 'External light supply']
  ];

  return (
    <>
      <section className="manual-hero">
        <div>
          <p className="eyebrow">Product manual</p>
          <h2>NuroAgro Setup Guide</h2>
          <p>Run the platform with ESP32 hardware, without hardware in Virtual Farm Mode, locally, or on Render.</p>
        </div>
        <div className="manual-actions">
          <button className="primary-button" onClick={() => user ? setPage('dashboard') : openAuth('register')}>
            <Gauge size={18} /> {user ? 'Open Dashboard' : 'Create Account'}
          </button>
          <button className="secondary-button" onClick={seedVirtualFarm} disabled={!user || loading}>
            <Cpu size={18} /> Virtual Farm Mode
          </button>
        </div>
      </section>

      <section className="manual-grid">
        <article className="panel manual-card">
          <div className="panel-title"><h3>Quick Start</h3><Sprout size={18} /></div>
          <p>Login with the demo account or create an accepted user from Admin, save a project, then open Dashboard.</p>
          <p>Use Virtual Farm Mode when ESP32 hardware is not connected. It stores real database rows so weather, history, alerts, and recommendations stay active.</p>
        </article>
        <article className="panel manual-card">
          <div className="panel-title"><h3>Disease Detection</h3><Microscope size={18} /></div>
          <p>Upload a sharp leaf photo from the Disease page. The app warms YOLO after startup and analyzes resized images for faster scans.</p>
          <p>Use close-up images with good light when confidence is low, then compare the annotated result and saved history.</p>
        </article>
        <article className="panel manual-card">
          <div className="panel-title"><h3>Weather Transformer</h3><CloudSun size={18} /></div>
          <p>Weather prediction uses the Transformer model when `weather_prediction_transformer_model.keras` and `scaler.pkl` are available.</p>
          <p>If the model is unavailable, the app keeps running with the local calibrated fallback and records the model status.</p>
        </article>
        <article className="panel manual-card">
          <div className="panel-title"><h3>Deployment</h3><Globe2 size={18} /></div>
          <p>Render is the preferred single-service deployment because Flask serves both the API and the built React app.</p>
          <p>Vercel can host the frontend separately, but the Python backend and ML models should stay on Render or another Python service.</p>
        </article>
      </section>

      <section className="table-panel">
        <div className="panel-title"><h3>ESP32 Pin Diagram</h3><Cpu size={18} /></div>
        <div className="pin-diagram">
          <div className="esp-board">
            <span>ESP-WROOM-32</span>
            <i>USB</i>
          </div>
          <div className="pin-lines">
            {pinRows.map(([module, pin]) => <span key={module}><b>{pin}</b>{module}</span>)}
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Module</th><th>ESP32 Pin</th><th>Power</th></tr></thead>
            <tbody>
              {pinRows.map(([module, pin, power]) => <tr key={module}><td>{module}</td><td>{pin}</td><td>{power}</td></tr>)}
            </tbody>
          </table>
        </div>
      </section>

      <section className="manual-grid">
        <article className="panel manual-card">
          <div className="panel-title"><h3>Local Run</h3><Settings size={18} /></div>
          <p>Install Python and Node dependencies, run the final dev script, then open the Flask URL shown in the terminal.</p>
          <p>Keep `DEVICE_API_KEY` the same in `.env` and ESP32 code.</p>
        </article>
        <article className="panel manual-card">
          <div className="panel-title"><h3>Render Run</h3><ShieldCheck size={18} /></div>
          <p>Use `render.yaml`, set `SECRET_KEY`, `DEVICE_API_KEY`, and `ADMIN_PASSWORD`, then deploy the repository.</p>
          <p>Use a paid plan for smoother TensorFlow and YOLO cold starts.</p>
        </article>
      </section>
    </>
  );
}

function AppFooter({ setPage, user, theme }) {
  const year = new Date().getFullYear();
  return (
    <footer className="app-footer">
      <div className="footer-brand">
        <img src={appLogo} alt="NeuroAgro logo" />
        <div>
          <strong>NeuroAgro</strong>
          <span>Intelligent farming, IoT control, weather intelligence, and crop disease vision.</span>
        </div>
      </div>
      <div className="footer-columns">
        <section>
          <h4>Product</h4>
          <button onClick={() => setPage(user ? 'dashboard' : 'home')}>Dashboard</button>
          <button onClick={() => setPage(user ? 'projects' : 'home')}>Project setup</button>
          <button onClick={() => setPage(user ? 'disease' : 'home')}>Disease vision</button>
        </section>
        <section>
          <h4>System</h4>
          <button onClick={() => setPage('manual')}>Manual</button>
          <button onClick={() => setPage('admin')}>Admin</button>
          <button onClick={() => setPage(user ? 'history' : 'home')}>History</button>
        </section>
        <section>
          <h4>Status</h4>
          <span>{theme === 'dark' ? 'Dark mode active' : 'Light mode active'}</span>
          <span>ESP32 telemetry ready</span>
          <span>Disease API enabled</span>
        </section>
      </div>
      <div className="footer-bottom">
        <span>© {year} NeuroAgro. Built for modern protected farming.</span>
        <nav aria-label="Footer quick links">
          <button onClick={() => setPage('manual')}>Documentation</button>
          <button onClick={() => setPage(user ? 'chat' : 'home')}>Support</button>
          <button onClick={() => setPage(user ? 'community' : 'home')}>Community</button>
        </nav>
      </div>
    </footer>
  );
}

function HomePage({ user, latest, health, hardware, supabaseStatus, openAuth, setPage }) {
  return (
    <>
      <section className="launch-grid">
        <div className="launch-copy">
          <p className="eyebrow">Smart agriculture operating system</p>
          <h1>NuroAgro</h1>
          <p className="lead">
            Vertical-first farm control for hydroponic, aquaponic, aeroponic, hybrid, and traditional farms.
          </p>
          <div className="launch-actions">
            <button className="primary-button" onClick={() => user ? setPage('dashboard') : openAuth('register')}>
              <Sprout size={18} /> {user ? 'Open Farm' : 'Create Account'}
            </button>
            <button className="secondary-button" onClick={() => user ? setPage('projects') : openAuth('login')}>
              <ChevronRight size={18} /> {user ? 'Project Setup' : 'Login'}
            </button>
          </div>
        </div>
        <NuroAgroVisual health={health} latest={latest} />
      </section>

      <section className="signal-grid">
        <Signal icon={<Cpu />} label="Controller" value="ESP-WROOM-32" />
        <Signal icon={<Database />} label="Database" value={supabaseLabel(supabaseStatus)} />
        <Signal icon={<Camera />} label="Vision" value="YOLO disease AI" />
        <Signal icon={<Waves />} label="Growing Modes" value="Hydro + Aqua + Soil" />
      </section>

      <section className="hardware-section">
        <div className="section-title">
          <div>
            <p className="eyebrow">Hardware mesh</p>
            <h2>Connected Modules</h2>
          </div>
          <span className={`system-pill ${health.tone}`}>{health.label}</span>
        </div>
        <HardwareGrid hardware={hardware} />
      </section>
    </>
  );
}

function AuthPage({ mode, setMode, form, setForm, error, notice, loading, onSubmit }) {
  const register = mode === 'register';
  const update = (field, value) => setForm((current) => ({ ...current, [field]: value }));

  return (
    <section className="auth-layout">
      <form className="panel form-panel" onSubmit={onSubmit}>
        <p className="eyebrow">Purchased product access</p>
        <h2>{register ? 'Create NuroAgro Account' : 'Login'}</h2>
        <div className="mode-tabs">
          <button type="button" className={!register ? 'active' : ''} onClick={() => setMode('login')}><LogIn size={16} /> Login</button>
          <button type="button" className={register ? 'active' : ''} onClick={() => setMode('register')}><UserPlus size={16} /> Register</button>
        </div>
        <div className="form-grid">
          <Field icon={<User />} label={register ? 'Username' : 'Username or email'} value={form.username} onChange={(value) => update('username', value)} />
          {register && <Field icon={<User />} label="Full name" value={form.fullName} onChange={(value) => update('fullName', value)} />}
          {register && <Field icon={<Database />} label="Email" type="email" value={form.email} onChange={(value) => update('email', value)} />}
          {register && <Field icon={<Cpu />} label="Device ID" value={form.deviceId} placeholder="ESP32_001" onChange={(value) => update('deviceId', value)} />}
          {register && <Field icon={<Sprout />} label="Farm or organization" value={form.organization} onChange={(value) => update('organization', value)} />}
          <Field icon={<Lock />} label="Password" type="password" value={form.password} onChange={(value) => update('password', value)} />
          {register && <Field icon={<Lock />} label="Confirm password" type="password" value={form.passwordConfirm} onChange={(value) => update('passwordConfirm', value)} />}
        </div>
        {notice && <p className="form-notice">{notice}</p>}
        {error && <p className="form-error">{error}</p>}
        <button className="primary-button auth-submit" disabled={loading}>
          {register ? <UserPlus size={18} /> : <LogIn size={18} />}
          {loading ? 'Working' : register ? 'Create Account' : 'Login'}
        </button>
      </form>
      <aside className="approval-rail">
        <div className="approval-step active"><UserPlus size={18} /><span>Register</span></div>
        <div className="approval-step active"><ShieldCheck size={18} /><span>Admin acceptance</span></div>
        <div className="approval-step"><Settings size={18} /><span>Profile setup</span></div>
        <div className="approval-step"><Gauge size={18} /><span>Project dashboard</span></div>
      </aside>
    </section>
  );
}

function ProjectPage({ form, setForm, project, advice, onSubmit, onDelete, useCurrentLocation, user, supabaseStatus }) {
  const update = (field, value) => setForm((current) => ({ ...current, [field]: value }));

  return (
    <>
      <section className="section-title page-title">
        <div>
          <p className="eyebrow">Project setup</p>
          <h2>{project?.name || 'New Farm Module'}</h2>
        </div>
        <button className="secondary-button" onClick={useCurrentLocation}><MapPin size={17} /> Detect Location</button>
      </section>

      <section className="split-grid wide-left">
        <form className="panel form-panel" onSubmit={onSubmit}>
          <div className="profile-strip">
            <span><UserCheck size={16} /> {user.username}</span>
            <span><ShieldCheck size={16} /> {title(user.approval_status || 'accepted')}</span>
            <span><Database size={16} /> {supabaseLabel(supabaseStatus)}</span>
          </div>
          <div className="form-grid">
            <Field icon={<Sprout />} label="Project name" value={form.name} onChange={(value) => update('name', value)} />
            <Field icon={<BarChart3 />} label="Area / land size (sq ft)" type="number" value={form.area} onChange={(value) => update('area', value)} />
            <Field icon={<MapPin />} label="Latitude" type="number" value={form.latitude} onChange={(value) => update('latitude', value)} />
            <Field icon={<MapPin />} label="Longitude" type="number" value={form.longitude} onChange={(value) => update('longitude', value)} />
            <SelectField icon={<Leaf />} label="Farming goal" value={form.climate} onChange={(value) => update('climate', value)} options={modeOptions} />
            <SelectField icon={<Home />} label="Vertical floors" value={form.stories} onChange={(value) => update('stories', value)} options={['1', '2', '3', '4']} />
            <SelectField icon={<Waves />} label="Water system" value={form.waterSystem} onChange={(value) => update('waterSystem', value)} options={systemOptions} />
            <SelectField icon={<CloudSun />} label="Weather profile" value={form.weather} onChange={(value) => update('weather', value)} options={['temperate', 'humid', 'dry', 'hot', 'cool', 'monsoon']} />
            <Field icon={<Sprout />} label="Crop goal" value={form.cropGoal} onChange={(value) => update('cropGoal', value)} />
            <Field icon={<Settings />} label="Setup notes" value={form.notes} onChange={(value) => update('notes', value)} />
          </div>
          <div className="form-actions">
            <button className="primary-button auth-submit"><Save size={18} /> {project?.id ? 'Update Project' : 'Save Project'}</button>
            {project?.id && <button type="button" className="secondary-button danger-button" onClick={onDelete}><Trash2 size={18} /> Delete Project</button>}
          </div>
        </form>
        <AdvicePanel project={project || form} advice={advice} />
      </section>
    </>
  );
}

function DashboardPage(props) {
  const {
    user, project, advice, deviceId, setDeviceId, latest, readings, status, health, hardware,
    recommendations, notifications, analysis, weatherData, geoWeatherStatus, runSensorAnalysis, runWeatherPrediction,
    syncGeoWeather, trainWeatherModel, sendCommand, updateDeviceStatus, seedVirtualFarm, loading, setPage
  } = props;

  const devices = user.devices || [];

  return (
    <>
      <section className="dashboard-head">
        <div>
          <p className="eyebrow">Live project dashboard</p>
          <h2>{project?.name || 'Unconfigured Farm'}</h2>
          <p>{advice.primary}</p>
        </div>
        <div className="dashboard-actions">
          <label className="inline-field">
            <span>Device</span>
            <select value={deviceId} onChange={(event) => setDeviceId(event.target.value)}>
              {devices.map((device) => <option key={device.device_id} value={device.device_id}>{device.device_name || device.device_id}</option>)}
              {!devices.length && <option value={deviceId}>{deviceId}</option>}
            </select>
          </label>
          <button className="primary-button" onClick={runSensorAnalysis}><Activity size={18} /> {loading ? 'Analyzing' : 'Analyze Sensors'}</button>
          <button className="secondary-button" onClick={seedVirtualFarm} disabled={loading}><Cpu size={18} /> Virtual Farm</button>
        </div>
      </section>

      <section className={`status-band ${health.tone}`}>
        <Leaf size={28} />
        <div>
          <h2>{health.label}</h2>
          <p>{health.detail}</p>
        </div>
      </section>

      <FeatureCoverage latest={latest} weatherData={weatherData} diseaseHistory={props.diseaseHistory || []} recommendations={recommendations} />
      <CropGuardPanel latest={latest} weatherData={weatherData} diseaseHistory={props.diseaseHistory || []} />

      <section className="metric-grid">
        <Metric icon={<Thermometer />} label="Temperature" value={`${format(latest?.temperature)} C`} tone={toneFor(latest?.temperature, 18, 34)} />
        <Metric icon={<Droplets />} label="Humidity" value={`${format(latest?.humidity)}%`} tone={toneFor(latest?.humidity, 45, 78)} />
        <Metric icon={<Droplets />} label="Soil moisture" value={`${format(latest?.soil_moisture)}%`} tone={toneFor(latest?.soil_moisture, 30, 82)} />
        <Metric icon={<Waves />} label="Water level" value={`${format(latest?.water_level)}%`} tone={toneFor(latest?.water_level, 20, 100)} />
        <Metric icon={<CloudSun />} label="Rain sensor" value={format(latest?.rain_level)} tone={Number(latest?.rain_level || 0) > 60 ? 'warn' : 'good'} />
        <Metric icon={<Lightbulb />} label="Lux / UV" value={format(latest?.light_intensity)} tone={toneFor(latest?.light_intensity, 250, 1600)} />
        <Metric icon={<Wind />} label="MQ gas stack" value={gasSummary(latest)} tone={Number(latest?.mq135 || 0) > 400 ? 'warn' : 'good'} />
        <Metric icon={<Eye />} label="Motion" value={latest?.motion_detected ? 'Detected' : 'Clear'} tone={latest?.motion_detected ? 'danger' : 'good'} />
      </section>

      <section className="split-grid wide-left">
        <NuroAgroVisual health={health} latest={latest} compact />
        <ControlPanel status={status} sendCommand={sendCommand} updateDeviceStatus={updateDeviceStatus} />
      </section>

      <WeatherPanel
        weatherData={weatherData}
        geoWeatherStatus={geoWeatherStatus}
        loading={loading}
        onPredict={runWeatherPrediction}
        onGeoWeather={syncGeoWeather}
        onTrain={trainWeatherModel}
      />

      <section className="hardware-section">
        <div className="panel-title">
          <h3>ESP32 Hardware State</h3>
          <Cpu size={18} />
        </div>
        <HardwareGrid hardware={hardware} />
      </section>

      <section className="split-grid wide-left">
        <div className="stack">
          <AdvicePanel project={project} advice={advice} compact />
          <RecommendationList recommendations={recommendations} analysis={analysis} />
        </div>
        <div className="stack">
          <NotificationList notifications={notifications} />
          <article className="panel">
            <div className="panel-title"><h3>Stored History</h3><History size={18} /></div>
            <p className="muted">Live dashboard shows only the latest ESP32 packet. Sensor, weather, disease, alerts, recommendations, and training records stay saved in History.</p>
            <button className="secondary-button" onClick={() => setPage('history')}><Database size={17} /> Open History</button>
          </article>
        </div>
      </section>

      <section className="action-row">
        <button onClick={() => setPage('projects')}><Settings size={18} /> Project Setup</button>
        <button onClick={() => setPage('history')}><History size={18} /> History</button>
        <button onClick={() => setPage('disease')}><Camera size={18} /> Disease Detection</button>
        <button onClick={() => setPage('chat')}><MessageCircle size={18} /> Chat Admin</button>
        <button onClick={() => setPage('community')}><BookOpen size={18} /> Community</button>
        <button onClick={() => setPage('manual')}><BookOpen size={18} /> Manual</button>
        <button onClick={() => setPage('profile')}><User size={18} /> Profile</button>
      </section>
    </>
  );
}

function FeatureCoverage({ latest, weatherData, diseaseHistory, recommendations }) {
  const prediction = weatherData?.latest_prediction;
  const featureItems = [
    { icon: <Cpu />, label: 'ESP32 telemetry', ready: Boolean(latest), detail: latest ? timeAgo(latest.timestamp) : 'waiting' },
    { icon: <CloudSun />, label: 'Weather AI', ready: Boolean(prediction), detail: prediction?.model_status || 'no prediction' },
    { icon: <Microscope />, label: 'Disease vision', ready: Boolean((diseaseHistory || []).length), detail: `${(diseaseHistory || []).length} scans` },
    { icon: <Activity />, label: 'Recommendations', ready: Boolean((recommendations || []).length), detail: `${(recommendations || []).length} active` },
    { icon: <ShieldCheck />, label: 'Render-ready backend', ready: true, detail: 'Flask + React' }
  ];

  return (
    <section className="feature-strip">
      {featureItems.map((item) => (
        <article className={`feature-chip ${item.ready ? 'ready' : 'waiting'}`} key={item.label}>
          {item.icon}
          <div>
            <strong>{item.label}</strong>
            <span>{item.detail}</span>
          </div>
        </article>
      ))}
    </section>
  );
}

function CropGuardPanel({ latest, weatherData, diseaseHistory }) {
  const prediction = weatherData?.latest_prediction || {};
  const daily = weatherData?.daily_records || [];
  const latestDaily = daily[0] || {};
  const latestDisease = (diseaseHistory || [])[0] || {};
  const factors = [];

  function add(condition, points, label, detail) {
    if (condition) factors.push({ points, label, detail });
  }

  const rainfall = Math.max(Number(prediction.rainfall || 0), Number(latestDaily.rainfall || 0));
  add(Number(latest?.soil_moisture || 0) < 30, 18, 'Low root moisture', 'Irrigation should be checked before stress rises.');
  add(Number(latest?.soil_moisture || 0) > 82, 15, 'Saturated media', 'Pause watering and check drainage.');
  add(Number(prediction.humidity || latest?.humidity || 0) > 78, 16, 'High humidity', 'Disease pressure increases when leaves stay wet.');
  add(Number(prediction.max_temperature || latest?.temperature || 0) > 34, 18, 'Heat stress', 'Improve shade, airflow, or mist timing.');
  add(rainfall > 18, 14, 'Rain/wetness risk', 'Outdoor watering should pause during wet periods.');
  add(Number(latestDisease.disease_confidence || 0) >= 20, 22, 'Disease evidence', `${latestDisease.primary_disease || 'Leaf issue'} was detected recently.`);
  add(Number(latest?.mq135 || 0) > 400, 12, 'Air quality warning', 'Ventilation or gas sensor calibration needs review.');

  const score = clamp(factors.reduce((sum, item) => sum + item.points, 0), 0, 100);
  const tone = score >= 70 ? 'danger' : score >= 38 ? 'warn' : 'good';
  const label = score >= 70 ? 'High crop risk' : score >= 38 ? 'Moderate crop risk' : 'Low crop risk';
  const action = factors[0]?.detail || 'Conditions are stable. Keep collecting sensor, geo weather, and disease history.';

  return (
    <section className={`cropguard-panel ${tone}`}>
      <div>
        <p className="eyebrow">Unique feature</p>
        <h3>CropGuard Risk Index</h3>
        <p>{action}</p>
      </div>
      <div className="risk-meter" aria-label="CropGuard risk score">
        <strong>{Math.round(score)}</strong>
        <span>{label}</span>
        <i style={{ width: `${score}%` }} />
      </div>
      <div className="risk-factors">
        {(factors.length ? factors.slice(0, 3) : [{ label: 'Stable climate', detail: 'No major risk factor found.' }]).map((item) => (
          <span key={item.label}><b>{item.label}</b>{item.detail}</span>
        ))}
      </div>
    </section>
  );
}

function DataTable({ title: heading, icon, columns, rows, empty }) {
  return (
    <section className="table-panel history-table">
      <div className="panel-title"><h3>{heading}</h3>{icon}</div>
      <div className="table-wrap">
        <table>
          <thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={row.key || index}>{row.cells.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>
            ))}
            {!rows.length && <tr><td colSpan={columns.length}>{empty}</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function HistoryPage({ historyData, deviceId, loading, onRefresh }) {
  const sensors = historyData?.sensor_readings || [];
  const weather = historyData?.weather_records || [];
  const diseases = historyData?.disease_detections || [];
  const recs = historyData?.recommendations || [];
  const alerts = historyData?.notifications || [];
  const training = historyData?.weather_training_runs || [];

  return (
    <>
      <section className="section-title page-title">
        <div>
          <p className="eyebrow">Stored farm history</p>
          <h2>{deviceId} Records</h2>
        </div>
        <button className="secondary-button" onClick={onRefresh} disabled={loading}><RefreshCcw size={17} /> Refresh History</button>
      </section>
      <section className="history-grid">
        <DataTable
          title="Sensor Readings"
          icon={<Database size={18} />}
          columns={['Time', 'Temp', 'Humidity', 'Soil', 'Water', 'Lux', 'MQ-135']}
          empty="No stored ESP32 sensor readings yet."
          rows={sensors.map((item) => ({
            key: `sensor-${item.id}`,
            cells: [dateText(item.timestamp), format(item.temperature), format(item.humidity), format(item.soil_moisture), format(item.water_level), format(item.light_intensity), format(item.mq135)]
          }))}
        />
        <DataTable
          title="Weather History"
          icon={<CloudSun size={18} />}
          columns={['Time', 'Max C', 'Min C', 'Humidity', 'Rainfall', 'Pressure', 'Agent Advice']}
          empty="No predicted or realtime weather records stored yet."
          rows={weather.map((item) => ({
            key: `weather-${item.id}`,
            cells: [dateText(item.created_at || item.forecast_for), format(item.max_temperature), format(item.min_temperature), `${format(item.humidity)}%`, `${format(item.rainfall)} mm`, `${format(item.pressure)} hPa`, shortText(item.agent_summary || item.model_status || 'Saved')]
          }))}
        />
        <DataTable
          title="Disease Scans"
          icon={<Microscope size={18} />}
          columns={['Time', 'Disease', 'Confidence', 'Severity', 'Source']}
          empty="No manual or ESP camera disease scans stored yet."
          rows={diseases.map((item) => ({
            key: `disease-${item.id}`,
            cells: [dateText(item.timestamp), item.primary_disease || 'Healthy / unknown', `${format(item.disease_confidence)}%`, item.severity_level || 'Review', item.is_from_camera ? 'ESP camera' : 'Manual']
          }))}
        />
        <DataTable
          title="Recommendations"
          icon={<Activity size={18} />}
          columns={['Time', 'Type', 'Reason']}
          empty="No saved AI recommendations yet."
          rows={recs.map((item) => ({
            key: `rec-${item.id}`,
            cells: [dateText(item.time_of_analysis), title(item.recommendation_type || 'guidance'), shortText(item.reason || 'Stored analysis result')]
          }))}
        />
        <DataTable
          title="Notifications"
          icon={<Bell size={18} />}
          columns={['Time', 'Title', 'Message']}
          empty="No notification history yet."
          rows={alerts.map((item) => ({
            key: `alert-${item.id}`,
            cells: [dateText(item.created_at), item.title || title(item.notification_type || 'alert'), shortText(item.message || '')]
          }))}
        />
        <DataTable
          title="Weather Training Runs"
          icon={<LineChart size={18} />}
          columns={['Started', 'Samples', 'Accuracy', 'MAE', 'Status']}
          empty="No 3-month weather model training runs yet."
          rows={training.map((item) => ({
            key: `train-${item.id}`,
            cells: [dateText(item.started_at || item.completed_at), item.samples_count || 0, format(item.accuracy_score), format(item.mean_absolute_error), title(item.status || 'queued')]
          }))}
        />
      </section>
    </>
  );
}

function ProfilePage({ user, form, setForm, dashboard, loading, onSubmit, onRefresh }) {
  const update = (field, value) => setForm((current) => ({ ...current, [field]: value }));
  const counts = dashboard?.counts || {};

  return (
    <>
      <section className="section-title page-title">
        <div>
          <p className="eyebrow">Personal farm dashboard</p>
          <h2>{form.fullName || user.username}</h2>
        </div>
        <button className="secondary-button" onClick={onRefresh}><RefreshCcw size={17} /> Refresh Profile</button>
      </section>
      <section className="admin-metrics profile-metrics">
        <Signal icon={<Cpu />} label="Devices" value={counts.devices || 0} />
        <Signal icon={<Plus />} label="Projects" value={counts.projects || 0} />
        <Signal icon={<Database />} label="Sensor History" value={counts.sensor_readings || 0} />
        <Signal icon={<CloudSun />} label="Weather Records" value={counts.weather_records || 0} />
        <Signal icon={<MessageCircle />} label="Unread Chat" value={counts.chat_unread || 0} />
        <Signal icon={<BookOpen />} label="Forum Posts" value={counts.forum_posts || 0} />
      </section>
      <section className="split-grid wide-left">
        <form className="panel form-panel" onSubmit={onSubmit}>
          <div className="panel-title"><h3>Update Profile</h3><Edit3 size={18} /></div>
          <div className="form-grid">
            <Field icon={<User />} label="Full name" value={form.fullName} onChange={(value) => update('fullName', value)} />
            <Field icon={<MessageCircle />} label="Phone" value={form.phone} onChange={(value) => update('phone', value)} />
            <Field icon={<Sprout />} label="Farm name" value={form.farmName} onChange={(value) => update('farmName', value)} />
            <Field icon={<Leaf />} label="Plant type" value={form.plantType} onChange={(value) => update('plantType', value)} />
            <Field icon={<BarChart3 />} label="Farm area (sq ft)" type="number" value={form.farmSize} onChange={(value) => update('farmSize', value)} />
            <Field icon={<MapPin />} label="Latitude" type="number" value={form.latitude} onChange={(value) => update('latitude', value)} />
            <Field icon={<MapPin />} label="Longitude" type="number" value={form.longitude} onChange={(value) => update('longitude', value)} />
            <TextAreaField icon={<Settings />} label="Profile notes" value={form.profileNotes} onChange={(value) => update('profileNotes', value)} />
          </div>
          <button className="primary-button auth-submit" disabled={loading}><Save size={18} /> Save Profile</button>
        </form>
        <article className="panel">
          <div className="panel-title"><h3>Latest Activity</h3><Activity size={18} /></div>
          <div className="stat-list">
            <span><b>{dashboard?.latest?.sensor ? timeAgo(dashboard.latest.sensor.timestamp) : 'No data'}</b> latest sensor packet</span>
            <span><b>{dashboard?.latest?.weather ? timeAgo(dashboard.latest.weather.created_at) : 'No data'}</b> latest weather prediction</span>
            <span><b>{dashboard?.latest?.disease?.primary_disease || 'No scan'}</b> latest disease result</span>
          </div>
        </article>
      </section>
    </>
  );
}

function ChatPage({ messages, text, setText, onSubmit, onRefresh }) {
  return (
    <>
      <section className="section-title page-title">
        <div>
          <p className="eyebrow">Admin support</p>
          <h2>Chat With Admin</h2>
        </div>
        <button className="secondary-button" onClick={onRefresh}><RefreshCcw size={17} /> Refresh Chat</button>
      </section>
      <section className="panel chat-panel">
        <div className="message-list">
          {messages.map((message) => (
            <div className={`chat-message ${message.sender_role}`} key={message.id}>
              <strong>{message.sender_role === 'admin' ? 'Admin' : message.username || 'You'}</strong>
              <p>{message.message}</p>
              <small>{dateText(message.created_at)}</small>
            </div>
          ))}
          {!messages.length && <p className="muted">No messages yet. Send the first support message to the admin team.</p>}
        </div>
        <form className="chat-compose" onSubmit={onSubmit}>
          <textarea value={text} onChange={(event) => setText(event.target.value)} rows="3" placeholder="Write your message" />
          <button className="primary-button"><Send size={18} /> Send</button>
        </form>
      </section>
    </>
  );
}

function CommunityPage({ posts, form, setForm, replyDrafts, setReplyDrafts, onCreate, onReply, onRefresh }) {
  const update = (field, value) => setForm((current) => ({ ...current, [field]: value }));

  return (
    <>
      <section className="section-title page-title">
        <div>
          <p className="eyebrow">Grower community</p>
          <h2>Plant Problem Forum</h2>
        </div>
        <button className="secondary-button" onClick={onRefresh}><RefreshCcw size={17} /> Refresh Forum</button>
      </section>
      <section className="split-grid wide-left community-layout">
        <form className="panel form-panel" onSubmit={onCreate}>
          <div className="panel-title"><h3>Create Discussion</h3><MessageSquare size={18} /></div>
          <div className="form-grid">
            <Field icon={<BookOpen />} label="Title" value={form.title} onChange={(value) => update('title', value)} />
            <SelectField icon={<Settings />} label="Category" value={form.category} onChange={(value) => update('category', value)} options={['general', 'disease', 'hydroponic', 'aquaponic', 'vertical', 'soil']} />
            <Field icon={<Leaf />} label="Plant type" value={form.plantType} onChange={(value) => update('plantType', value)} />
            <TextAreaField icon={<MessageSquare />} label="Problem or idea" value={form.content} onChange={(value) => update('content', value)} />
          </div>
          <button className="primary-button auth-submit"><Plus size={18} /> Publish Post</button>
        </form>
        <div className="forum-list">
          {posts.map((post) => (
            <article className="panel forum-post" key={post.id}>
              <div className="panel-title">
                <h3>{post.title}</h3>
                <span className="pill">{title(post.category || 'general')}</span>
              </div>
              <p>{post.content}</p>
              <div className="pill-row">
                <span className="pill good">{post.username || 'Grower'}</span>
                {post.plant_type && <span className="pill">{post.plant_type}</span>}
                <span className="pill">{post.reply_count || 0} replies</span>
              </div>
              <div className="reply-list">
                {(post.replies || []).map((reply) => (
                  <div className="reply-item" key={reply.id}><strong>{reply.username || 'Grower'}</strong><p>{reply.content}</p></div>
                ))}
              </div>
              <form className="reply-row" onSubmit={(event) => { event.preventDefault(); onReply(post.id); }}>
                <input value={replyDrafts[post.id] || ''} onChange={(event) => setReplyDrafts((current) => ({ ...current, [post.id]: event.target.value }))} placeholder="Reply" />
                <button className="secondary-button small"><Send size={16} /> Reply</button>
              </form>
            </article>
          ))}
          {!posts.length && <article className="panel"><p className="muted">No community posts yet. Start a discussion about a plant, system, or farm problem.</p></article>}
        </div>
      </section>
    </>
  );
}

function AdminChatPanel({ threads, thread, onOpenThread, text, setText, onSubmit }) {
  return (
    <article className="panel admin-chat-panel">
      <div className="panel-title"><h3>Admin Chat Inbox</h3><MessageCircle size={18} /></div>
      <div className="admin-chat-layout">
        <div className="thread-list">
          {threads.map((item) => (
            <button type="button" key={item.user.id} onClick={() => onOpenThread(item.user.id)}>
              <strong>{item.user.username}</strong>
              <small>{item.unread_count || 0} unread</small>
            </button>
          ))}
          {!threads.length && <p className="muted">No user messages yet.</p>}
        </div>
        <div className="admin-thread">
          <div className="message-list compact">
            {(thread?.messages || []).map((message) => (
              <div className={`chat-message ${message.sender_role}`} key={message.id}>
                <strong>{message.sender_role === 'admin' ? 'Admin' : message.username || 'User'}</strong>
                <p>{message.message}</p>
              </div>
            ))}
            {!thread?.messages?.length && <p className="muted">Select a conversation to reply.</p>}
          </div>
          <form className="chat-compose" onSubmit={onSubmit}>
            <textarea value={text} onChange={(event) => setText(event.target.value)} rows="2" placeholder="Admin reply" />
            <button className="primary-button small"><Send size={16} /> Reply</button>
          </form>
        </div>
      </div>
    </article>
  );
}
function DiseasePage({ result, history, loading, onSubmit, onCameraScan, deviceId }) {
  const imageUrl = result?.image_url || result?.annotated_image_url;
  const confidence = result?.confidence ?? result?.disease_confidence;
  const recommendations = Array.isArray(result?.recommendations) ? result.recommendations : [];
  const discarded = result?.discarded_low_confidence || 0;
  const threshold = result?.confidence_threshold;

  return (
    <>
      <section className="section-title page-title">
        <div>
          <p className="eyebrow">YOLO plant disease analysis</p>
          <h2>Manual And ESP Camera Detection</h2>
        </div>
        <button className="secondary-button" onClick={onCameraScan} disabled={loading}>
          <Camera size={17} /> Request ESP Capture
        </button>
      </section>

      <section className="split-grid wide-left">
        <form className="panel form-panel disease-form" onSubmit={onSubmit}>
          <div className="panel-title">
            <h3>Manual Upload</h3>
            <Upload size={18} />
          </div>
          <div className="camera-strip">
            <Camera size={18} />
            <span>{deviceId}</span>
            <span>ESP camera module automatic upload</span>
          </div>
          <div className="quality-list">
            <span>Use a sharp close-up leaf image</span>
            <span>Fill most of the frame with the affected area</span>
            <span>Avoid blur, shadow, and mixed backgrounds</span>
          </div>
          <label className="upload-box">
            <Upload size={30} />
            <span>Take or select plant image</span>
            <input name="image" type="file" accept="image/*" capture="environment" required />
          </label>
          <button className="primary-button auth-submit" disabled={loading}><Microscope size={18} /> {loading ? 'Analyzing' : 'Analyze Disease'}</button>
        </form>
        <article className="panel diagnosis-panel">
          <div className="panel-title">
            <h3>Latest Diagnosis</h3>
            <Camera size={18} />
          </div>
          {!result && (
            <div className="sample-image">
              <img src={assetUrl('/uploads/rice-disease.jpg')} alt="Leaf disease sample" />
            </div>
          )}
          {result?.error && <p className="form-error">{result.error}</p>}
          {result && !result.error && (
            <div className="diagnosis">
              {imageUrl && <img src={assetUrl(imageUrl)} alt="Disease detection result" />}
              <strong>{result.primary_disease || 'No disease detected'}</strong>
              <span>{format(confidence)}% confidence</span>
              <p>Severity: {result.severity || result.severity_level || 'Not classified'}</p>
              {threshold && <p className="muted">Disease confidence threshold: {format(threshold)}%. {discarded ? `${discarded} low-confidence marks ignored.` : 'No low-confidence disease marks ignored.'}</p>}
              {recommendations.map((item, index) => <p key={index} className="rec-item">{item}</p>)}
            </div>
          )}
        </article>
      </section>

      <DiseaseHistoryPanel history={history} />
    </>
  );
}

function AdminPage({ password, setPassword, data, loading, onSubmit, createForm, setCreateForm, message, onCreateUser, onAction, adminThreads = [], adminThread, onOpenThread, adminChatText, setAdminChatText, onAdminChatSubmit }) {
  const users = data?.users || [];
  const totals = data?.totals || {};
  const updateCreate = (field, value) => setCreateForm((current) => ({ ...current, [field]: value }));

  return (
    <section className="admin-page">
      <div className="admin-hero">
        <div>
          <p className="eyebrow">Administrator</p>
          <h2>NuroAgro Admin</h2>
          <p>Manage users, farm locations, visitors, devices, and account access from one control dashboard.</p>
        </div>
        <form className="admin-login-panel" onSubmit={onSubmit}>
          <Field icon={<Lock />} label="Admin password" type="password" value={password} onChange={setPassword} />
          <button className="primary-button" disabled={loading}><ShieldCheck size={18} /> Open Dashboard</button>
        </form>
      </div>

      {data?.error && <p className="form-error">{data.error}</p>}
      {message && <p className={message.toLowerCase().includes('could not') || message.toLowerCase().includes('api') ? 'form-error' : 'form-notice'}>{message}</p>}

      {data && !data.error && (
        <>
          <section className="admin-metrics">
            <Signal icon={<Users />} label="Total Users" value={totals.users || 0} />
            <Signal icon={<CheckCircle2 />} label="Accepted" value={totals.accepted || 0} />
            <Signal icon={<AlertTriangle />} label="Pending" value={totals.pending || 0} />
            <Signal icon={<CircleOff />} label="Rejected" value={totals.rejected || 0} />
            <Signal icon={<Activity />} label="Web Visitors" value={totals.visitors || 0} />
            <Signal icon={<Cpu />} label="Devices" value={totals.devices || 0} />
          </section>

          <section className="admin-dashboard-grid">
            <form className="panel admin-create-panel" onSubmit={onCreateUser}>
              <div className="panel-title"><h3>Create New User</h3><UserPlus size={18} /></div>
              <div className="form-grid">
                <Field icon={<User />} label="Username" value={createForm.username} onChange={(value) => updateCreate('username', value)} />
                <Field icon={<Database />} label="Email" type="email" value={createForm.email} onChange={(value) => updateCreate('email', value)} />
                <Field icon={<Lock />} label="Password" type="password" value={createForm.password} onChange={(value) => updateCreate('password', value)} />
                <Field icon={<Cpu />} label="Device ID" value={createForm.deviceId} placeholder="Optional" onChange={(value) => updateCreate('deviceId', value)} />
                <Field icon={<Sprout />} label="Farm name" value={createForm.farmName} onChange={(value) => updateCreate('farmName', value)} />
                <Field icon={<Leaf />} label="Plant type" value={createForm.plantType} onChange={(value) => updateCreate('plantType', value)} />
                <SelectField icon={<ShieldCheck />} label="Status" value={createForm.approvalStatus} onChange={(value) => updateCreate('approvalStatus', value)} options={['accepted', 'pending', 'rejected']} />
              </div>
              <button className="primary-button auth-submit" disabled={loading}><UserPlus size={18} /> Create User</button>
            </form>

            <AdminGraph totals={totals} />

            <article className="panel">
              <div className="panel-title"><h3>System Information</h3><LineChart size={18} /></div>
              <div className="stat-list">
                <span><b>{totals.projects || 0}</b> projects</span>
                <span><b>{totals.sensor_readings || 0}</b> sensor records</span>
                <span><b>{totals.weather_records || 0}</b> weather records</span>
                <span><b>{totals.disease_detections || 0}</b> disease scans</span>
                <span><b>{totals.recommendations || 0}</b> active recommendations</span>
                <span><b>{totals.chat_messages || 0}</b> support messages</span>
                <span><b>{totals.forum_posts || 0}</b> forum posts</span>
              </div>
            </article>

            <AdminChatPanel
              threads={adminThreads}
              thread={adminThread}
              onOpenThread={onOpenThread}
              text={adminChatText}
              setText={setAdminChatText}
              onSubmit={onAdminChatSubmit}
            />
          </section>

          <section className="table-panel admin-table-panel">
            <div className="panel-title"><h3>User Information</h3><Search size={18} /></div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>User</th>
                    <th>Email</th>
                    <th>Farm</th>
                    <th>Location</th>
                    <th>Devices</th>
                    <th>Projects</th>
                    <th>Last Sensor</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((item) => (
                    <tr key={item.id}>
                      <td><strong>{item.username}</strong></td>
                      <td>{item.email}</td>
                      <td>{item.farm_name || 'Unconfigured'}</td>
                      <td>{locationText(item)}</td>
                      <td>{item.counts?.devices || 0}</td>
                      <td>{item.counts?.projects || 0}</td>
                      <td>{item.latest_reading ? timeAgo(item.latest_reading.timestamp) : 'No data'}</td>
                      <td><span className={`pill ${statusClass(item.approval_status)}`}>{title(item.approval_status || 'pending')}</span></td>
                      <td>
                        <div className="table-actions">
                          <button title="Accept user" onClick={() => onAction(item.id, 'accepted')}><UserCheck size={16} /></button>
                          <button title="Reject user" onClick={() => onAction(item.id, 'rejected')}><CircleOff size={16} /></button>
                          <button title="Delete user" onClick={() => onAction(item.id, 'delete')}><Trash2 size={16} /></button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {!users.length && <tr><td colSpan="9">No users registered yet.</td></tr>}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </section>
  );
}

function NuroAgroVisual({ health, latest, compact = false }) {
  const moisture = clamp(Number(latest?.soil_moisture ?? 48), 0, 100);
  const lux = clamp(Number(latest?.light_intensity ?? 620), 0, 1800);
  const water = clamp(Number(latest?.water_level ?? 72), 0, 100);

  return (
    <section className={`farm-visual ${compact ? 'compact' : ''}`}>
      <div className="visual-glass">
        <div className="tower-frame">
          {[1, 2, 3, 4].map((floor) => (
            <div className="grow-floor" key={floor}>
              <span className="floor-index">F{floor}</span>
              <div className="uv-bar" style={{ width: `${Math.max(18, lux / 18)}%` }} />
              <div className="plant-row">
                {Array.from({ length: 8 }).map((_, index) => <i key={index} />)}
              </div>
            </div>
          ))}
        </div>
        <div className="sensor-column">
          <VisualChip icon={<Cpu size={15} />} label="ESP32" value={latest ? 'Online' : 'Standby'} />
          <VisualChip icon={<Droplets size={15} />} label="Soil" value={`${format(moisture)}%`} />
          <VisualChip icon={<Waves size={15} />} label="Tank" value={`${format(water)}%`} />
          <VisualChip icon={<Camera size={15} />} label="Camera" value="YOLO" />
        </div>
      </div>
      <div className="visual-footer">
        <span className={`status-dot ${health.tone}`} />
        <strong>{health.label}</strong>
        <small>{latest ? `Last ESP32 packet ${timeAgo(latest.timestamp)}` : 'Waiting for first stored sensor packet'}</small>
      </div>
    </section>
  );
}

function VisualChip({ icon, label, value }) {
  return (
    <div className="visual-chip">
      {icon}
      <span>{label}</span>
      <b>{value}</b>
    </div>
  );
}

function ControlPanel({ status, sendCommand, updateDeviceStatus }) {
  const threshold = Number(status?.moisture_threshold ?? 30);
  const uvLevel = Number(status?.uv_light_level ?? 65);

  return (
    <article className="panel control-panel">
      <div className="panel-title">
        <h3>Relays And Automation</h3>
        <SlidersHorizontal size={18} />
      </div>
      <div className="control-list">
        <Control title="Pump A" active={status?.pump_on} onOn={() => sendCommand('pump_on')} onOff={() => sendCommand('pump_off')} />
        <Control title="Pump B" active={status?.pump_b_on} onOn={() => sendCommand('pump_b_on')} onOff={() => sendCommand('pump_b_off')} />
        <Control title="Blue UV Lights" active={status?.light_on} onOn={() => sendCommand('light_on')} onOff={() => sendCommand('light_off')} />
      </div>
      <label className="toggle-row">
        <input
          type="checkbox"
          checked={Boolean(status?.auto_watering_enabled)}
          onChange={(event) => updateDeviceStatus({ auto_watering_enabled: event.target.checked })}
        />
        <span>Automatic moisture watering</span>
      </label>
      <RangeControl
        icon={<Droplets size={16} />}
        label="Moisture threshold"
        value={threshold}
        min="10"
        max="70"
        unit="%"
        onChange={(value) => updateDeviceStatus({ moisture_threshold: Number(value) })}
      />
      <RangeControl
        icon={<Lightbulb size={16} />}
        label="UV light level"
        value={uvLevel}
        min="0"
        max="100"
        unit="%"
        onChange={(value) => sendCommand('uv_level', { uv_light_level: Number(value) })}
      />
    </article>
  );
}

function Control({ title, active, onOn, onOff }) {
  return (
    <div className="control-row">
      <div className="control-copy">
        <span>{title}</span>
        <strong className={active ? 'relay-on' : 'relay-off'}>{active ? 'Running' : 'Stopped'}</strong>
      </div>
      <div className="button-pair">
        <button type="button" className={active ? 'selected' : ''} aria-pressed={Boolean(active)} onClick={onOn} title={`${title} on`}>
          <Power size={16} /> On
        </button>
        <button type="button" className={!active ? 'selected off' : 'off'} aria-pressed={!active} onClick={onOff} title={`${title} off`}>
          <CircleOff size={16} /> Off
        </button>
      </div>
    </div>
  );
}

function RangeControl({ icon, label, value, min, max, unit, onChange }) {
  return (
    <label className="range-control">
      <span>{icon}{label}<b>{value}{unit}</b></span>
      <input type="range" min={min} max={max} value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function WeatherPanel({ weatherData, geoWeatherStatus, loading, onPredict, onGeoWeather, onTrain }) {
  const prediction = weatherData?.latest_prediction;
  const realtime = weatherData?.latest_realtime;
  const geoDaily = weatherData?.daily_records || [];
  const latestGeoDaily = weatherData?.latest_geo_daily || geoDaily[0];
  const training = weatherData?.latest_training_run;
  const records = weatherData?.records || [];
  const plants = Array.isArray(prediction?.recommended_plants) ? prediction.recommended_plants : [];
  const rawPrediction = prediction?.raw_payload || {};
  const modelSource = rawPrediction.source || prediction?.source || 'waiting';
  const sampleCount = rawPrediction.input_samples;
  const geoStatus = geoWeatherStatus || weatherData?.geo_status || null;
  const geoStatusClass = ['success', 'updated', 'cached'].includes(geoStatus?.status)
    ? 'good'
    : geoStatus?.status === 'fallback'
      ? 'warn'
      : geoStatus?.status
        ? 'danger'
        : 'aqua';
  const geoStatusDetail = geoStatus?.error || geoStatus?.reason || (
    geoStatus?.status === 'missing_location' ? 'Add project or profile latitude/longitude.' : ''
  );

  return (
    <section className="panel weather-panel">
      <div className="panel-title">
        <h3>Weather Prediction And Crop Agent</h3>
        <CloudSun size={18} />
      </div>
      <div className="panel-actions">
        <button className="primary-button small" onClick={() => onPredict(false)} disabled={loading}>
          <RefreshCcw size={16} /> Predict 30 Min
        </button>
        <button className="secondary-button small" onClick={() => onGeoWeather(true)} disabled={loading}>
          <Globe2 size={16} /> Sync Location Weather
        </button>
        <button className="secondary-button small" onClick={onTrain} disabled={loading}>
          <LineChart size={16} /> Train 3-Month Model
        </button>
      </div>

      <div className="model-status-row">
        <span className={`pill ${modelSource === 'transformer' ? 'good' : 'aqua'}`}>{title(modelSource)}</span>
        <span>{prediction?.model_status || 'No weather model run yet'}</span>
        <span>{sampleCount === undefined ? 'Waiting for sensor samples' : `${sampleCount} sensor samples used`}</span>
        {geoStatus?.status && <span className={`pill ${geoStatusClass}`}>Geo {title(geoStatus.status)}</span>}
        {geoStatusDetail && <span>{shortText(geoStatusDetail, 90)}</span>}
        {rawPrediction.transformer_model_file_exists === false && <span>Transformer file missing</span>}
      </div>

      <div className="weather-grid">
        <WeatherMetric label="Max Temperature" value={`${format(prediction?.max_temperature)} C`} />
        <WeatherMetric label="Min Temperature" value={`${format(prediction?.min_temperature)} C`} />
        <WeatherMetric label="Apparent Temperature" value={`${format(prediction?.apparent_temperature)} C`} />
        <WeatherMetric label="Humidity" value={`${format(prediction?.humidity)} %`} />
        <WeatherMetric label="Pressure" value={`${format(prediction?.pressure)} hPa`} />
        <WeatherMetric label="Rainfall" value={`${format(prediction?.rainfall)} mm`} />
      </div>

      <div className="weather-insight-grid">
        <article className="insight-box">
          <span>ChatGPT crop agent</span>
          <strong>{plants.length ? plants.join(', ') : 'Waiting for prediction'}</strong>
          <p>{prediction?.agent_summary || 'The agent will analyze predicted and stored 3-month weather data when a prediction is saved.'}</p>
        </article>
        <article className="insight-box">
          <span>Realtime weather packet</span>
          <strong>{realtime ? `${format(realtime.apparent_temperature)} C apparent` : 'No realtime weather stored'}</strong>
          <p>{realtime ? `Stored ${timeAgo(realtime.created_at)} from ${title(realtime.source || 'weather')}.` : 'Realtime values are saved from ESP32 or geolocation weather sync.'}</p>
        </article>
        <article className="insight-box">
          <span>Geo daily weather</span>
          <strong>{latestGeoDaily ? `${format(latestGeoDaily.max_temperature)} / ${format(latestGeoDaily.min_temperature)} C` : 'No location forecast'}</strong>
          <p>{latestGeoDaily ? `${title(latestGeoDaily.source)} saved for ${dateText(latestGeoDaily.forecast_for)}.` : 'Add project latitude/longitude, then sync location weather.'}</p>
        </article>
        <article className="insight-box">
          <span>Transformer calibration</span>
          <strong>{training ? title(training.status) : 'Not trained yet'}</strong>
          <p>{training ? `${training.samples_count || 0} paired samples, ${format(training.accuracy_score)}% score, MAE ${format(training.mean_absolute_error)}.` : 'Press Train 3-Month Model after enough realtime and predicted weather history is stored.'}</p>
        </article>
      </div>

      <div className="daily-weather-strip">
        {geoDaily.slice(0, 7).map((item) => (
          <article key={`daily-${item.id || item.forecast_for}`}>
            <span>{item.forecast_for ? new Date(item.forecast_for).toLocaleDateString(undefined, { weekday: 'short' }) : 'Day'}</span>
            <strong>{format(item.max_temperature)} C</strong>
            <small>{format(item.min_temperature)} C min</small>
            <small>{format(item.rainfall)} mm rain</small>
          </article>
        ))} 
        {!geoDaily.length && <p className="muted">{geoStatus?.status === 'missing_location' ? 'Add project latitude/longitude, then sync location weather.' : 'No geolocation daily weather saved yet.'}</p>}
      </div>

      <div className="table-wrap weather-history">
        <table>
          <thead><tr><th>Time</th><th>Source</th><th>Max</th><th>Min</th><th>Humidity</th><th>Pressure</th><th>Rainfall</th><th>Status</th></tr></thead>
          <tbody>
            {records.slice(0, 12).map((item) => (
              <tr key={`${item.source}-${item.id}-${item.created_at}`}>
                <td>{item.created_at ? new Date(item.created_at).toLocaleString() : 'Saved'}</td>
                <td>{title(item.source || 'weather')}</td>
                <td>{format(item.max_temperature)}</td>
                <td>{format(item.min_temperature)}</td>
                <td>{format(item.humidity)}</td>
                <td>{format(item.pressure)}</td>
                <td>{format(item.rainfall)}</td>
                <td>{item.model_status || 'stored'}</td>
              </tr>
            ))}
            {!records.length && <tr><td colSpan="8">No realtime or predicted weather data stored yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function WeatherMetric({ label, value }) {
  return (
    <div className="weather-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function DiseaseHistoryPanel({ history }) {
  return (
    <section className="table-panel disease-history-panel">
      <div className="panel-title"><h3>Disease Scan History</h3><Database size={18} /></div>
      <div className="disease-history-grid">
        {(history || []).map((scan) => (
          <article className="scan-row" key={scan.id}>
            {scan.image_url && <img src={assetUrl(scan.image_url)} alt="Stored disease scan" />}
            <div>
              <span className={`pill ${scan.is_from_camera ? 'aqua' : 'good'}`}>{scan.is_from_camera ? 'ESP camera' : 'Manual'}</span>
              <strong>{scan.primary_disease || 'No disease detected'}</strong>
              <p>{format(scan.disease_confidence)}% confidence, severity {scan.severity_level || 'not classified'}.</p>
              <small>{scan.timestamp ? timeAgo(scan.timestamp) : 'Saved scan'}</small>
            </div>
          </article>
        ))}
        {!(history || []).length && <p className="muted">No disease scans saved yet. Upload manually or request an ESP camera capture.</p>}
      </div>
    </section>
  );
}

function HardwareGrid({ hardware }) {
  return (
    <div className="hardware-grid">
      {hardware.map((item) => (
        <article className={`hardware-card ${item.tone}`} key={item.label}>
          <div>{item.icon}</div>
          <span>{item.label}</span>
          <strong>{item.value}</strong>
        </article>
      ))}
    </div>
  );
}

function Field({ icon, label, value, onChange, type = 'text', placeholder = '' }) {
  return (
    <label className="field">
      <span>{icon}{label}</span>
      <input type={type} value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function TextAreaField({ icon, label, value, onChange, placeholder = '' }) {
  return (
    <label className="field full-field">
      <span>{icon}{label}</span>
      <textarea value={value} placeholder={placeholder} rows="4" onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function SelectField({ icon, label, value, onChange, options }) {
  return (
    <label className="field">
      <span>{icon}{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => <option key={option} value={option}>{title(option)}</option>)}
      </select>
    </label>
  );
}

function Signal({ icon, label, value }) {
  return <article className="signal-card"><div>{icon}</div><span>{label}</span><strong>{value}</strong></article>;
}

function Metric({ icon, label, value, tone = 'good' }) {
  return <article className={`metric-card ${tone}`}><div className="metric-icon">{icon}</div><span>{label}</span><strong>{value}</strong></article>;
}

function AdvicePanel({ project, advice, compact = false }) {
  return (
    <article className="panel advice-panel">
      <div className="panel-title">
        <h3>AI Farm Recommendation</h3>
        <Sprout size={18} />
      </div>
      {!project?.name && <p className="muted">Create a project to unlock suitability, plant, fish, and system recommendations.</p>}
      {project?.name && (
        <div className="advice">
          <strong>{advice.primary}</strong>
          <p>{advice.reason}</p>
          {!compact && <p>{advice.system}</p>}
          <div className="score-grid">
            <Score label="Vertical" value={advice.verticalScore} />
            <Score label="Traditional" value={advice.traditionalScore} />
            <Score label="Hybrid" value={advice.hybridScore} />
          </div>
          <div className="pill-row">
            {advice.systems.map((system) => <span className="pill" key={system}>{system}</span>)}
          </div>
          <div className="pill-row">
            {advice.plants.map((plant) => <span className="pill good" key={plant}>{plant}</span>)}
          </div>
          <div className="pill-row">
            {advice.fish.map((fish) => <span className="pill aqua" key={fish}><Fish size={14} /> {fish}</span>)}
          </div>
        </div>
      )}
    </article>
  );
}

function Score({ label, value }) {
  return (
    <div className="score">
      <span>{label}</span>
      <strong>{Math.round(value)}</strong>
      <i style={{ width: `${clamp(value, 0, 100)}%` }} />
    </div>
  );
}

function HistoryPanel({ readings }) {
  return (
    <section className="table-panel">
      <div className="panel-title"><h3>Sensor History</h3><Database size={18} /></div>
      <TrendStrip readings={readings} />
      <div className="table-wrap">
        <table>
          <thead><tr><th>Time</th><th>Temp</th><th>Humidity</th><th>Soil</th><th>Water</th><th>Lux</th><th>MQ-135</th></tr></thead>
          <tbody>
            {readings.slice(0, 16).map((reading) => (
              <tr key={reading.id}>
                <td>{new Date(reading.timestamp).toLocaleString()}</td>
                <td>{format(reading.temperature)}</td>
                <td>{format(reading.humidity)}</td>
                <td>{format(reading.soil_moisture)}</td>
                <td>{format(reading.water_level)}</td>
                <td>{format(reading.light_intensity)}</td>
                <td>{format(reading.mq135)}</td>
              </tr>
            ))}
            {!readings.length && <tr><td colSpan="7">No ESP32 readings stored yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function TrendStrip({ readings }) {
  const series = readings.slice(0, 24).reverse();
  if (!series.length) return <div className="trend-strip empty" />;
  return (
    <div className="trend-strip" aria-label="Sensor trend">
      {series.map((item) => (
        <span key={item.id} style={{ height: `${Math.max(12, Number(item.soil_moisture || 0))}%` }} />
      ))}
    </div>
  );
}

function RecommendationList({ recommendations, analysis }) {
  return (
    <article className="panel">
      <div className="panel-title"><h3>Timed Recommendations</h3><Activity size={18} /></div>
      {analysis?.summary && <p className="muted">Analyzed {analysis.summary.sample_count} stored sensor samples.</p>}
      <div className="rec-list">
        {recommendations.slice(0, 5).map((rec) => (
          <div className="rec-item" key={rec.id}>
            <strong>{title(rec.recommendation_type || 'farm guidance')}</strong>
            <p>{rec.reason || 'Stored recommendation from the sensor analysis agent.'}</p>
          </div>
        ))}
        {!recommendations.length && <p className="muted">No saved recommendations yet.</p>}
      </div>
    </article>
  );
}

function NotificationList({ notifications }) {
  return (
    <article className="panel">
      <div className="panel-title"><h3>Alerts</h3><Bell size={18} /></div>
      <div className="rec-list">
        {notifications.slice(0, 5).map((item) => (
          <div className="rec-item" key={item.id}>
            <strong>{item.title}</strong>
            <p>{item.message}</p>
          </div>
        ))}
        {!notifications.length && <p className="muted">No alerts yet.</p>}
      </div>
    </article>
  );
}

function AdminGraph({ totals }) {
  const items = [
    ['Users', totals.users || 0],
    ['Accepted', totals.accepted || 0],
    ['Pending', totals.pending || 0],
    ['Visitors', totals.visitors || 0],
    ['Devices', totals.devices || 0]
  ];
  const max = Math.max(...items.map((item) => item[1]), 1);
  return (
    <article className="panel admin-graph">
      <div className="panel-title"><h3>Admin Graph</h3><BarChart3 size={18} /></div>
      <div className="bars">
        {items.map(([label, value]) => (
          <span key={label}>
            <i style={{ height: `${Math.max(8, (value / max) * 100)}%` }} />
            <b>{value}</b>
            <small>{label}</small>
          </span>
        ))}
      </div>
    </article>
  );
}

function buildSearchOptions(user) {
  const auth = Boolean(user);
  return [
    { label: 'Home Console', page: 'home', requiresAuth: false, keywords: 'home console product landing nuroagro' },
    { label: 'Project Setup', page: 'projects', requiresAuth: true, keywords: 'project setup farm location geolocation crop fish system' },
    { label: 'Dashboard', page: 'dashboard', requiresAuth: true, keywords: 'dashboard live sensors virtual farm iot esp32 controller telemetry' },
    { label: 'Virtual Farm Mode', page: auth ? 'dashboard' : 'auth', requiresAuth: true, keywords: 'virtual farm no iot demo simulator sample data seed' },
    { label: 'Weather Prediction', page: 'dashboard', requiresAuth: true, keywords: 'weather prediction transformer forecast train calibration rainfall humidity' },
    { label: 'History Records', page: 'history', requiresAuth: true, keywords: 'history records sensor weather disease recommendation notifications training' },
    { label: 'Disease Detection', page: 'disease', requiresAuth: true, keywords: 'disease detection yolo leaf crop image upload camera' },
    { label: 'Admin Chat', page: 'chat', requiresAuth: true, keywords: 'chat support admin message help' },
    { label: 'Community Forum', page: 'community', requiresAuth: true, keywords: 'community forum posts replies growers disease hydroponic' },
    { label: 'Profile', page: 'profile', requiresAuth: true, keywords: 'profile user farm phone location plant account' },
    { label: 'Manual And Wiring', page: 'manual', requiresAuth: false, keywords: 'manual guide wiring pin diagram esp32 render vercel deploy local instructions' },
    { label: 'Admin Panel', page: 'admin', requiresAuth: false, keywords: 'admin users approval visitors database system' }
  ];
}

function analyzeProject(project) {
  if (!project?.name) {
    return {
      primary: 'Project not configured',
      reason: '',
      system: '',
      plants: [],
      fish: [],
      systems: [],
      verticalScore: 0,
      traditionalScore: 0,
      hybridScore: 0
    };
  }

  const area = Number(project.area || project.land_area || 0);
  const stories = Number(project.stories || project.vertical_stories || 1);
  const waterSystem = project.waterSystem || project.water_system || 'hybrid';
  const weather = project.weather || 'temperate';
  const compactArea = area > 0 && area < 220;
  const bigField = area > 900;
  const waterBonus = ['hydroponic', 'aquaponic', 'aeroponic', 'hybrid'].includes(waterSystem) ? 12 : 0;
  const climateBonus = ['humid', 'temperate', 'cool'].includes(weather) ? 5 : 0;
  const verticalScore = clamp(52 + stories * 8 + waterBonus + (compactArea ? 13 : 3) + climateBonus, 0, 96);
  const traditionalScore = clamp(72 + (bigField ? 14 : 0) - stories * 6 + (waterSystem === 'soil' ? 8 : 0), 28, 94);
  const hybridScore = clamp((verticalScore + traditionalScore) / 2 + (waterSystem === 'hybrid' ? 10 : 3), 0, 98);
  const bestScore = Math.max(verticalScore, traditionalScore, hybridScore);
  const primary = bestScore === hybridScore
    ? 'Recommended: hybrid vertical farm with controlled water systems'
    : bestScore === verticalScore
      ? `Recommended: vertical ${title(waterSystem)} farming`
      : 'Recommended: traditional farming with smart automation';
  const reason = `Vertical ${Math.round(verticalScore)}/100, traditional ${Math.round(traditionalScore)}/100, and hybrid ${Math.round(hybridScore)}/100 from area, floors, weather, geolocation, and water system.`;
  const system = waterSystem === 'aquaponic' || waterSystem === 'hybrid'
    ? 'Use biofilter monitoring, low-density fish stocking, moisture failover pumps, lux control, gas alerts, and camera disease scans.'
    : 'Use moisture-triggered pumps, lux-based blue UV lighting, rain pause, motion alerts, gas monitoring, and periodic camera scans.';
  const plants = compactArea
    ? ['Lettuce', 'Basil', 'Spinach', 'Pak choi', 'Mint']
    : ['Tomato', 'Cucumber', 'Spinach', 'Basil', 'Strawberry'];
  const systems = waterSystem === 'hybrid'
    ? ['Hydroponic', 'Aquaponic', 'Aeroponic', 'Soil backup']
    : [title(waterSystem), 'Drip irrigation', 'Sensor automation'];
  const fish = waterSystem === 'aquaponic' || waterSystem === 'hybrid'
    ? fishOptions
    : ['Optional aquaponic expansion'];

  return { primary, reason, system, plants, fish, systems, verticalScore, traditionalScore, hybridScore };
}

function buildHardware(latest, status) {
  return [
    { icon: <Cpu />, label: 'ESP-WROOM-32', value: latest ? 'Streaming' : 'Waiting', tone: latest ? 'good' : 'idle' },
    { icon: <Wind />, label: 'MQ-05', value: format(latest?.mq5), tone: Number(latest?.mq5 || 0) > 350 ? 'warn' : 'good' },
    { icon: <Wind />, label: 'MQ-07', value: format(latest?.mq7), tone: Number(latest?.mq7 || 0) > 280 ? 'warn' : 'good' },
    { icon: <Wind />, label: 'MQ-135', value: format(latest?.mq135), tone: Number(latest?.mq135 || 0) > 400 ? 'warn' : 'good' },
    { icon: <Thermometer />, label: 'DHT11', value: `${format(latest?.temperature)} C`, tone: toneFor(latest?.temperature, 18, 34) },
    { icon: <Lightbulb />, label: 'TEMT6000', value: format(latest?.light_intensity), tone: toneFor(latest?.light_intensity, 250, 1600) },
    { icon: <CloudSun />, label: 'Raindrop', value: format(latest?.rain_level), tone: Number(latest?.rain_level || 0) > 60 ? 'warn' : 'good' },
    { icon: <Droplets />, label: 'Soil Moisture', value: `${format(latest?.soil_moisture)}%`, tone: toneFor(latest?.soil_moisture, 30, 82) },
    { icon: <Waves />, label: 'Water Pump A', value: status?.pump_on ? 'ON' : 'OFF', tone: status?.pump_on ? 'good' : 'idle' },
    { icon: <Waves />, label: 'Water Pump B', value: status?.pump_b_on ? 'ON' : 'OFF', tone: status?.pump_b_on ? 'good' : 'idle' },
    { icon: <Zap />, label: '6V Relay', value: status?.pump_on || status?.pump_b_on || status?.light_on ? 'Active' : 'Idle', tone: status?.pump_on || status?.pump_b_on || status?.light_on ? 'good' : 'idle' },
    { icon: <Lightbulb />, label: 'Blue UV Lights', value: `${format(status?.uv_light_level ?? 65)}%`, tone: status?.light_on ? 'good' : 'idle' },
    { icon: <Eye />, label: 'Motion Sensor', value: latest?.motion_detected ? 'Detected' : 'Clear', tone: latest?.motion_detected ? 'danger' : 'good' },
    { icon: <Camera />, label: 'ESP Camera', value: 'Ready', tone: 'good' }
  ];
}

function getHealth(latest, status) {
  if (!latest) return { label: 'Waiting for ESP32 data', detail: 'No sensor history has arrived yet.', tone: 'idle' };
  if (latest.motion_detected) return { label: 'Motion alert', detail: 'Movement was detected near the farm or grow rack.', tone: 'danger' };
  if (Number(latest.water_level ?? 100) < 20) return { label: 'Water level is low', detail: 'Refill the reservoir before automatic watering continues.', tone: 'danger' };
  if (Number(latest.soil_moisture ?? 100) < Number(status?.moisture_threshold ?? 30)) return { label: 'Soil moisture is low', detail: 'Automatic pump start is recommended unless manual mode is active.', tone: 'warn' };
  if (Number(latest.soil_moisture ?? 0) > 82) return { label: 'Soil is saturated', detail: 'Pause irrigation and check drainage or grow medium weight.', tone: 'warn' };
  if (Number(latest.temperature ?? 0) > 35) return { label: 'Temperature is high', detail: 'Improve ventilation or shade before crop stress rises.', tone: 'danger' };
  if (Number(latest.mq135 ?? 0) > 400) return { label: 'Air quality warning', detail: 'MQ-135 is elevated. Check ventilation, fertilizer gases, and calibration.', tone: 'warn' };
  if (Number(latest.rain_level ?? 0) > 60) return { label: 'Rain detected', detail: 'Outdoor watering should pause while rain is present.', tone: 'warn' };
  return { label: 'Farm conditions stable', detail: 'Recent moisture, air, light, and temperature readings are inside range.', tone: 'good' };
}

function profileToForm(profile = {}) {
  const farmLocation = profile.farm_location || {};
  return {
    fullName: profile.full_name || profile.fullName || '',
    phone: profile.phone || '',
    profileNotes: profile.profile_notes || profile.profileNotes || '',
    farmName: profile.farm_name || profile.farmName || '',
    plantType: profile.plant_type || profile.plantType || '',
    farmSize: profile.farm_size || profile.farmSize || '',
    latitude: farmLocation.latitude ?? profile.farm_location_lat ?? profile.latitude ?? '',
    longitude: farmLocation.longitude ?? profile.farm_location_lon ?? profile.longitude ?? ''
  };
}
function projectToForm(project) {
  return {
    name: project.name || project.project_name || '',
    area: project.area || project.land_area || '',
    latitude: project.latitude || '',
    longitude: project.longitude || '',
    climate: project.climate || project.farming_mode || 'hybrid',
    stories: String(project.stories || project.vertical_stories || 4),
    waterSystem: project.waterSystem || project.water_system || 'hybrid',
    cropGoal: project.cropGoal || 'leafy greens',
    weather: project.weather || 'temperate',
    notes: project.notes || ''
  };
}

function loadProject() {
  try {
    return JSON.parse(localStorage.getItem(PROJECT_KEY)) || null;
  } catch {
    return null;
  }
}

function format(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '--';
  return Number(value).toFixed(1);
}

function assetUrl(value) {
  if (!value) return '';
  const text = String(value).replaceAll('\\', '/');
  if (text.startsWith('http://') || text.startsWith('https://')) return text;
  const normalized = text.startsWith('/static/uploads/')
    ? text.replace('/static/uploads/', '/uploads/')
    : text;
  return `${API_BASE}${normalized.startsWith('/') ? normalized : `/${normalized}`}`;
}

function title(value) {
  return String(value || '').replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function dateText(value) {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '--';
  return date.toLocaleString();
}

function shortText(value, max = 110) {
  const text = String(value || '');
  return text.length > max ? `${text.slice(0, max)}...` : text;
}
function timeAgo(value) {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 60000));
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes} min ago`;
  return `${Math.round(minutes / 60)} hr ago`;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, Number.isFinite(value) ? value : min));
}

function toneFor(value, low, high) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return 'idle';
  const number = Number(value);
  if (number < low || number > high) return 'warn';
  return 'good';
}

function gasSummary(latest) {
  if (!latest) return '--';
  const values = [latest.mq5, latest.mq7, latest.mq135].filter((value) => value !== null && value !== undefined);
  if (!values.length) return '--';
  return format(Math.max(...values.map(Number)));
}

function locationText(user) {
  const lat = user.farm_location?.latitude ?? user.farm_location_lat;
  const lon = user.farm_location?.longitude ?? user.farm_location_lon;
  if (!lat || !lon) return 'Not set';
  return `${Number(lat).toFixed(2)}, ${Number(lon).toFixed(2)}`;
}

function statusClass(status) {
  if (status === 'accepted') return 'good';
  if (status === 'rejected') return 'danger';
  return 'warn';
}

function supabaseLabel(status) {
  if (status?.write_ok) return 'Supabase connected';
  if (status?.read_ok) return 'Supabase read only';
  if (status?.configured) return 'Supabase blocked';
  return 'Supabase not configured';
}

function dotPosition(user, index) {
  const lat = user.farm_location?.latitude ?? user.farm_location_lat;
  const lon = user.farm_location?.longitude ?? user.farm_location_lon;
  if (lat && lon) {
    return {
      left: `${clamp((Number(lon) + 180) / 360 * 100, 8, 92)}%`,
      top: `${clamp((90 - Number(lat)) / 180 * 100, 12, 88)}%`
    };
  }
  return {
    left: `${18 + (index * 17) % 66}%`,
    top: `${22 + (index * 23) % 50}%`
  };
}



