const $ = (selector) => document.querySelector(selector);
const today = new Date();
let shownMonth = new Date(today.getFullYear(), today.getMonth(), 1);
let selectedDate = isoDate(today);
let currentView = 'calendar';
let entriesByDate = new Map();
let toastTimer;

function isoDate(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}
function prettyDate(value, options = { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' }) {
  return new Date(`${value}T12:00:00`).toLocaleDateString(undefined, options);
}
function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
}
function formatHours(value) {
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });
}
async function api(url, options) {
  const response = await fetch(url, options);
  const contentType = response.headers.get('content-type') || '';
  const body = contentType.includes('application/json') ? await response.json() : null;
  if (!response.ok) throw new Error(body?.error || `Request failed (${response.status}).`);
  return body;
}
function showToast(message) {
  const toast = $('#toast');
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('show'), 2300);
}
function monthBounds() {
  const first = new Date(shownMonth.getFullYear(), shownMonth.getMonth(), 1);
  const mondayOffset = (first.getDay() + 6) % 7;
  const start = new Date(first);
  start.setDate(first.getDate() - mondayOffset);
  const end = new Date(start);
  end.setDate(start.getDate() + 41);
  return { start: isoDate(start), end: isoDate(end) };
}
async function loadCalendar() {
  const { start, end } = monthBounds();
  const rows = await api(`/api/entries?start=${start}&end=${end}`);
  entriesByDate = new Map();
  for (const entry of rows) {
    if (!entriesByDate.has(entry.work_date)) entriesByDate.set(entry.work_date, []);
    entriesByDate.get(entry.work_date).push(entry);
  }
  renderCalendar();
}
function renderCalendar() {
  $('#monthTitle').textContent = shownMonth.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
  const first = new Date(shownMonth.getFullYear(), shownMonth.getMonth(), 1);
  const offset = (first.getDay() + 6) % 7;
  const start = new Date(first);
  start.setDate(first.getDate() - offset);
  const grid = $('#calendarGrid');
  grid.innerHTML = '';
  let monthHours = 0;
  for (let index = 0; index < 42; index++) {
    const date = new Date(start);
    date.setDate(start.getDate() + index);
    const key = isoDate(date);
    const records = entriesByDate.get(key) || [];
    const hours = records.reduce((total, row) => total + Number(row.hours), 0);
    if (date.getMonth() === shownMonth.getMonth()) monthHours += hours;
    const cell = document.createElement('div');
    cell.className = `day-cell${date.getMonth() !== shownMonth.getMonth() ? ' outside' : ''}${key === selectedDate ? ' selected-day' : ''}`;
    cell.setAttribute('role', 'button');
    cell.tabIndex = 0;
    cell.dataset.date = key;
    cell.setAttribute('aria-label', `${prettyDate(key)}${records.length ? `, ${formatHours(hours)} hours, ${records.length} record${records.length === 1 ? '' : 's'}` : ', no work recorded'}`);
    const dayLabel = key === isoDate(today)
      ? `<span class="today-pill">${date.getDate()}</span>` : `<span>${date.getDate()}</span>`;
    const recordMarkup = records.map((entry) => `
      <button class="entry-chip" data-entry-id="${entry.id}" title="${escapeHtml(entry.project_number)} · ${escapeHtml(entry.project_name)} — ${formatHours(entry.hours)} hours">
        <span class="day-hours">${formatHours(entry.hours)}h</span>
        <span class="day-project">${escapeHtml(entry.project_number)} · ${escapeHtml(entry.project_name)}</span>
      </button>`).join('');
    cell.innerHTML = `<span class="day-number">${dayLabel}<span class="add-mark" aria-hidden="true">＋</span></span><div class="day-summary">${recordMarkup}</div>`;
    grid.append(cell);
  }
  $('#monthTotal').textContent = `${formatHours(monthHours)} hours this month`;
}
function setView(view) {
  currentView = view;
  $('#calendarView').classList.toggle('hidden', view !== 'calendar');
  $('#statsView').classList.toggle('hidden', view !== 'stats');
  document.querySelectorAll('.tab').forEach((tab) => tab.classList.toggle('active', tab.dataset.view === view));
  if (view === 'stats') loadStats();
}
function rangeForPeriod(period, value) {
  const anchor = new Date(`${value}T12:00:00`);
  let start, end, label;
  if (period === 'week') {
    const mondayOffset = (anchor.getDay() + 6) % 7;
    start = new Date(anchor);
    start.setDate(anchor.getDate() - mondayOffset);
    end = new Date(start);
    end.setDate(start.getDate() + 6);
    label = `${prettyDate(isoDate(start), { month: 'short', day: 'numeric' })} – ${prettyDate(isoDate(end), { month: 'short', day: 'numeric', year: 'numeric' })}`;
  } else if (period === 'year') {
    start = new Date(anchor.getFullYear(), 0, 1);
    end = new Date(anchor.getFullYear(), 11, 31);
    label = `${anchor.getFullYear()}`;
  } else {
    start = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
    end = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0);
    label = anchor.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
  }
  return { start: isoDate(start), end: isoDate(end), label };
}
async function loadStats() {
  const period = $('#periodSelect').value;
  const date = $('#periodDate').value || isoDate(today);
  const range = rangeForPeriod(period, date);
  $('#periodCaption').textContent = range.label;
  try {
    const stats = await api(`/api/stats?start=${range.start}&end=${range.end}`);
    $('#totalHours').textContent = formatHours(stats.hours);
    $('#totalDays').textContent = stats.days;
    $('#totalRecords').textContent = stats.records;
    const list = $('#projectStats');
    if (!stats.projects.length) {
      list.innerHTML = '<div class="empty-state">No work records for this period yet.</div>';
    } else {
      list.innerHTML = stats.projects.map((project) => `
        <div class="project-row">
          <div><div class="project-name">${escapeHtml(project.project_name)}</div><div class="project-number">${escapeHtml(project.project_number)}</div></div>
          <div class="project-hours">${formatHours(project.hours)} h</div>
          <div class="project-records">${project.records} ${project.records === 1 ? 'record' : 'records'}</div>
        </div>`).join('');
    }
    $('#exportButton').onclick = () => { window.location.href = `/api/export.csv?start=${range.start}&end=${range.end}`; };
  } catch (error) {
    showToast(error.message);
  }
}
function openDialog(date = selectedDate, entry = null) {
  selectedDate = date;
  $('#entryId').value = entry?.id || '';
  $('#dialogTitle').textContent = entry ? 'Edit record' : 'Add a record';
  $('#dialogDate').textContent = prettyDate(date);
  $('#projectNumber').value = entry?.project_number || '';
  $('#projectName').value = entry?.project_name || '';
  $('#location').value = entry?.location || '';
  $('#hours').value = entry?.hours ?? 8;
  $('#note').value = entry?.note || '';
  $('#formError').textContent = '';
  $('#deleteEntry').classList.toggle('hidden', !entry);
  $('#entryDialog').showModal();
  if (!entry) $('#projectNumber').focus();
}
function closeDialog() { $('#entryDialog').close(); }

document.querySelectorAll('.tab').forEach((tab) => tab.addEventListener('click', () => setView(tab.dataset.view)));
$('#prevMonth').addEventListener('click', () => { shownMonth.setMonth(shownMonth.getMonth() - 1); loadCalendar().catch((e) => showToast(e.message)); });
$('#nextMonth').addEventListener('click', () => { shownMonth.setMonth(shownMonth.getMonth() + 1); loadCalendar().catch((e) => showToast(e.message)); });
$('#todayButton').addEventListener('click', () => { shownMonth = new Date(today.getFullYear(), today.getMonth(), 1); selectedDate = isoDate(today); loadCalendar().catch((e) => showToast(e.message)); });
$('#addEntry').addEventListener('click', () => openDialog(selectedDate || isoDate(today)));
$('#calendarGrid').addEventListener('click', (event) => {
  const cell = event.target.closest('.day-cell');
  if (!cell) return;
  const recordButton = event.target.closest('[data-entry-id]');
  const date = cell.dataset.date;
  selectedDate = date;
  if (recordButton) {
    const entry = (entriesByDate.get(date) || []).find((row) => row.id === Number(recordButton.dataset.entryId));
    if (entry) openDialog(date, entry);
  } else {
    if (new Date(`${date}T12:00:00`).getMonth() !== shownMonth.getMonth()) shownMonth = new Date(`${date}T12:00:00`);
    openDialog(date);
  }
});
$('#calendarGrid').addEventListener('keydown', (event) => {
  if ((event.key === 'Enter' || event.key === ' ') && event.target.classList.contains('day-cell')) {
    event.preventDefault();
    event.target.click();
  }
});
document.querySelectorAll('.close-dialog').forEach((button) => button.addEventListener('click', closeDialog));
$('#entryDialog').addEventListener('click', (event) => { if (event.target === $('#entryDialog')) closeDialog(); });
$('#entryForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const id = $('#entryId').value;
  const payload = {
    work_date: selectedDate,
    project_number: $('#projectNumber').value,
    project_name: $('#projectName').value,
    location: $('#location').value,
    hours: Number($('#hours').value),
    note: $('#note').value,
  };
  $('#saveEntry').disabled = true;
  try {
    await api(id ? `/api/entries/${id}` : '/api/entries', {
      method: id ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    });
    closeDialog();
    await loadCalendar();
    if (currentView === 'stats') await loadStats();
    showToast(id ? 'Record updated.' : 'Record saved.');
  } catch (error) {
    $('#formError').textContent = error.message;
  } finally {
    $('#saveEntry').disabled = false;
  }
});
$('#deleteEntry').addEventListener('click', async () => {
  const id = $('#entryId').value;
  if (!id || !window.confirm('Delete this work record?')) return;
  try {
    await api(`/api/entries/${id}`, { method: 'DELETE' });
    closeDialog();
    await loadCalendar();
    if (currentView === 'stats') await loadStats();
    showToast('Record deleted.');
  } catch (error) {
    $('#formError').textContent = error.message;
  }
});
$('#periodSelect').addEventListener('change', loadStats);
$('#periodDate').addEventListener('change', loadStats);
$('#periodDate').value = isoDate(today);
loadCalendar().catch((error) => showToast(error.message));
