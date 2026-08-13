const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
const statusNode = document.querySelector("#status");
const hardwareSeries = {
  cpu: {label: "CPU", color: "#176b3a", unit: "%", values: [], display: 0},
  memory: {label: "Memory", color: "#278a50", unit: "%", values: [], display: 0},
  gpu: {label: "GPU", color: "#46a96b", unit: "%", values: [], display: 0},
  power: {label: "Power", color: "#79c68f", unit: " W", values: [], display: 0}
};
let hardwareTimer = 0;
let hardwarePending = false;

async function request(url, options = {}) {
  const response = await fetch(url, {headers: {Accept: "application/json", ...(options.headers || {})}, ...options});
  const value = await response.json();
  if (!response.ok) throw new Error(value.message || value.code || `${response.status} ${response.statusText}`);
  return value;
}

function projects(items) {
  const root = document.querySelector("#project-list");
  document.querySelector("#project-count").textContent = items.length;
  root.innerHTML = items.length ? items.map(item => `<article class="card"><h3>${esc(item.name)}</h3><div class="meta">${esc(item.target)}</div><p>${esc(item.run_count)} run(s) · latest ${esc(item.latest_state)}</p></article>`).join("") : '<div class="empty">No project runs have been recorded.</div>';
}

function runs(items) {
  const root = document.querySelector("#run-list");
  document.querySelector("#run-count").textContent = items.length;
	root.innerHTML = items.length ? `<table><thead><tr><th>Run</th><th>State</th><th>Project</th><th>Updated</th><th>Control</th></tr></thead><tbody>${items.map(item => `<tr><td><a href="${esc(item.links.self)}">${esc(item.id)}</a></td><td><span class="state">${esc(item.state)}</span></td><td>${esc(item.target)}</td><td>${esc(item.updated_at)}</td><td><div class="actions">${["active","executing","running","resumed","validating"].includes(item.state) ? `<button class="pause" data-run="${esc(item.id)}" data-version="${esc(item.version)}">Pause</button>` : ""}<button class="deploy" data-run="${esc(item.id)}">Deploy task</button></div></td></tr>`).join("")}</tbody></table>` : '<div class="empty">No runs have been recorded.</div>';
}

function initializeHardware() {
  document.querySelector("#hardware-list").innerHTML = Object.entries(hardwareSeries).map(([key, series]) => `<article class="card metric"><div class="metric-heading"><span>${series.label}</span><strong id="metric-${key}">—</strong></div><canvas id="graph-${key}" class="metric-graph" aria-label="${series.label} history"></canvas></article>`).join("");
}

function addHardwareValue(key, rawValue, label) {
  const series = hardwareSeries[key];
  const value = Number(rawValue);
  if (!Number.isFinite(value)) return;
  series.values.push(value);
  if (series.values.length > 120) series.values.shift();
  document.querySelector(`#metric-${key}`).textContent = label;
}

async function hardware() {
  if (hardwarePending) return;
  hardwarePending = true;
  try {
	const snapshot = await request("/api/v1/hardware");
	const value = snapshot.hardware;
	const used = Number(value.memory.ram_used_gb);
	const total = Number(value.memory.ram_total_gb);
	addHardwareValue("cpu", value.cpu.utilization_percent, `${value.cpu.utilization_percent ?? "—"}%`);
	addHardwareValue("memory", total > 0 ? used / total * 100 : NaN, `${value.memory.ram_used_gb ?? "—"} / ${value.memory.ram_total_gb ?? "—"} GB`);
	addHardwareValue("gpu", value.gpu.utilization_percent, `${value.gpu.utilization_percent ?? "—"}%`);
	addHardwareValue("power", value.power.total_watts, `${value.power.total_watts ?? "—"} W`);
  } finally {
	hardwarePending = false;
  }
}

function scheduleHardware() {
  clearInterval(hardwareTimer);
  const hz = Number(document.querySelector("#hardware-hz").value);
  document.querySelector("#hardware-hz-value").textContent = `${hz} Hz`;
  hardwareTimer = setInterval(() => hardware().catch(error => { statusNode.textContent = `Hardware unavailable: ${error.message}`; }), 1000 / hz);
}

function drawGraphs() {
  for (const [key, series] of Object.entries(hardwareSeries)) {
	const canvas = document.querySelector(`#graph-${key}`);
	if (!canvas) continue;
	const width = canvas.clientWidth;
	const height = canvas.clientHeight;
	const scale = window.devicePixelRatio || 1;
	if (canvas.width !== width * scale || canvas.height !== height * scale) {
	  canvas.width = width * scale;
	  canvas.height = height * scale;
	}
	const context = canvas.getContext("2d");
	context.setTransform(scale, 0, 0, scale, 0, 0);
	context.clearRect(0, 0, width, height);
	const target = series.values.at(-1) ?? 0;
	series.display += (target - series.display) * 0.16;
	const points = [...series.values.slice(-59), series.display];
	const maximum = key === "power" ? Math.max(100, ...points) : 100;
	const gradient = context.createLinearGradient(0, 0, 0, height);
	gradient.addColorStop(0, `${series.color}55`);
	gradient.addColorStop(1, `${series.color}05`);
	context.beginPath();
	points.forEach((point, index) => {
	  const x = points.length === 1 ? width : index * width / (points.length - 1);
	  const y = height - Math.max(0, Math.min(point / maximum, 1)) * (height - 4) - 2;
	  if (index === 0) context.moveTo(x, y); else context.lineTo(x, y);
	});
	context.lineTo(width, height);
	context.lineTo(0, height);
	context.closePath();
	context.fillStyle = gradient;
	context.fill();
	context.beginPath();
	points.forEach((point, index) => {
	  const x = points.length === 1 ? width : index * width / (points.length - 1);
	  const y = height - Math.max(0, Math.min(point / maximum, 1)) * (height - 4) - 2;
	  if (index === 0) context.moveTo(x, y); else context.lineTo(x, y);
	});
	context.strokeStyle = series.color;
	context.lineWidth = 2;
	context.lineJoin = "round";
	context.stroke();
  }
  requestAnimationFrame(drawGraphs);
}

async function refresh() {
  const [projectData, runData] = await Promise.all([request("/api/v1/projects"), request("/api/v1/runs")]);
  projects(projectData.items);
  runs(runData.items);
  statusNode.textContent = "Native midend connected";
}

document.querySelector("#run-list").addEventListener("click", async event => {
	const deploy = event.target.closest("button.deploy");
  if (deploy) {
	const objective = prompt("Task objective for this codebase:");
	if (!objective) return;
	deploy.disabled = true;
	try {
	  const result = await request(`/api/v1/runs/${encodeURIComponent(deploy.dataset.run)}/commands/deploy`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({objective})});
	  statusNode.textContent = `Task deployed: ${result.task.task_id}`;
	  await refresh();
	} catch (error) {
	  statusNode.textContent = `Task rejected: ${error.message}`;
	  deploy.disabled = false;
	}
	return;
  }
  const button = event.target.closest("button.pause");
  if (!button) return;
  button.disabled = true;
  const now = new Date();
  const requestId = `req_${crypto.randomUUID().replaceAll("-", "")}`;
  const envelope = {
	leafos_object: "leafos.midend_action_request", version: 1, capability_id: "run.pause",
	request_id: requestId, session_id: `ses_${crypto.randomUUID().replaceAll("-", "")}`,
	subject: {type: "operator", id: "local-web"},
	target: {type: "run", id: button.dataset.run, version: Number(button.dataset.version)},
	nonce: crypto.randomUUID(), issued_at: now.toISOString(),
	expires_at: new Date(now.getTime() + 120000).toISOString(),
	payload: {reason: "operator requested pause from web console"}
  };
  try {
	const disposition = await request(`/api/v1/runs/${encodeURIComponent(button.dataset.run)}/commands/pause`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(envelope)});
	statusNode.textContent = `Pause ${disposition.status}: ${disposition.control_id}`;
	await refresh();
  } catch (error) {
	statusNode.textContent = `Pause rejected: ${error.message}`;
	button.disabled = false;
  }
});

document.querySelector("#project-form").addEventListener("submit", async event => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const button = event.currentTarget.querySelector("button");
  button.disabled = true;
  try {
	const result = await request("/api/v1/projects/commands/start", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({mode: form.get("mode"), target: form.get("target"), objective: form.get("objective"), provider: form.get("provider"), approved: true, template: "auto"})});
	statusNode.textContent = `Project ${result.action}: ${result.run_dir}`;
	event.currentTarget.reset();
	await refresh();
  } catch (error) {
	statusNode.textContent = `Project start rejected: ${error.message}`;
  } finally {
	button.disabled = false;
  }
});

document.querySelector("#hardware-hz").addEventListener("input", scheduleHardware);
initializeHardware();
scheduleHardware();
drawGraphs();
Promise.all([refresh(), hardware()]).catch(error => { statusNode.textContent = `Midend unavailable: ${error.message}`; });
