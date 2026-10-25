const $ = (id) => document.getElementById(id);
const form = $('prediction-form');
const button = $('predict-button');
let modelReady = false;
let busy = false;
let revision = 0;
let hasResult = false;
const numberFormat = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 2 });
for (let hour = 0; hour < 24; hour++) {
  const option = new Option(`${String(hour).padStart(2, '0')}:00 – ${String(hour + 1).padStart(2, '0')}:00`, hour);
  option.selected = hour === 8;
  $('hour').add(option);
}

function updateCalendar() {
  const value = $('date').value;
  if (!value) { $('calendar-info').textContent = 'Chọn ngày để xem thông tin lịch.'; return; }
  const date = new Date(`${value}T12:00:00`);
  if (Number.isNaN(date.getTime())) return;
  const md = value.slice(5);
  const season = md >= '03-21' && md < '06-21' ? 'Mùa xuân' : md >= '06-21' && md < '09-23' ? 'Mùa hè' : md >= '09-23' && md < '12-21' ? 'Mùa thu' : 'Mùa đông';
  const weekday = ['Chủ nhật', 'Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy'][date.getDay()];
  const working = date.getDay() > 0 && date.getDay() < 6 && !$('holiday').checked;
  $('calendar-info').textContent = `${weekday} · ${season} · ${$('holiday').checked ? 'Ngày lễ' : working ? 'Ngày làm việc' : 'Cuối tuần'}`;
}

function showError(message) { $('form-error').textContent = message; $('form-error').hidden = false; }

function renderPeakHours(result) {
  // Sao chép để giữ nguyên thứ tự 00:00–23:00 của biểu đồ.
  const topHours = [...result.hourly]
    .sort((a, b) => b.prediction - a.prediction || a.hour - b.hour)
    .slice(0, 3);

  const items = topHours.map((point) => {
    const item = document.createElement('li');
    const time = document.createElement('strong');
    const count = document.createElement('span');
    const start = String(point.hour).padStart(2, '0');
    const end = String(point.hour + 1).padStart(2, '0');
    time.textContent = `${start}:00 – ${end}:00`;
    count.textContent = `${numberFormat.format(point.rounded_prediction)} lượt thuê`;
    item.append(time, count);
    return item;
  });

  $('peak-list').replaceChildren(...items);
  $('peak-list').hidden = false;
  $('peak-note').hidden = false;
  const [year, month, day] = result.date.split('-');
  $('peak-status').textContent = `Ngày ${day}/${month}/${year} · Xếp từ cao xuống thấp.`;
}

function renderHourlyChart(result) {
  const points = result.hourly;
  const width = 720, height = 300, left = 56, right = 18, top = 30, bottom = 48;
  const max = Math.max(5, Math.ceil(Math.max(...points.map(p => p.rounded_prediction)) / 5) * 5);
  const x = hour => left + hour * (width - left - right) / 23;
  const y = value => height - bottom - value * (height - top - bottom) / max;
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', 'Biểu đồ đường lượt thuê ước tính từ 00:00 đến 23:00. Số liệu chi tiết ở bảng bên dưới.');
  const add = (tag, attributes, text) => {
    const element = document.createElementNS(svg.namespaceURI, tag);
    for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, value);
    if (text !== undefined) element.textContent = text;
    svg.append(element);
    return element;
  };
  add('text', { x: left, y: 16, class: 'chart-label' }, 'Lượt thuê');
  for (let tick = 0; tick <= 5; tick++) {
    const value = max * tick / 5;
    add('line', { x1: left, x2: width - right, y1: y(value), y2: y(value), class: 'chart-grid' });
    add('text', { x: left - 8, y: y(value) + 4, 'text-anchor': 'end', class: 'chart-label' }, numberFormat.format(value));
  }
  for (const hour of [0, 3, 6, 9, 12, 15, 18, 21, 23]) {
    add('text', { x: x(hour), y: height - 22, 'text-anchor': 'middle', class: 'chart-label' }, `${String(hour).padStart(2, '0')}:00`);
  }
  add('polyline', { points: points.map(p => `${x(p.hour)},${y(p.rounded_prediction)}`).join(' '), class: 'chart-line' });
  for (const point of points) {
    const dot = add('circle', { cx: x(point.hour), cy: y(point.rounded_prediction), r: point.hour === result.hour ? 6 : 3.5, class: point.hour === result.hour ? 'chart-dot selected' : 'chart-dot' });
    const title = document.createElementNS(svg.namespaceURI, 'title');
    title.textContent = `${String(point.hour).padStart(2, '0')}:00: ${numberFormat.format(point.rounded_prediction)} lượt thuê`;
    dot.append(title);
  }
  $('hourly-chart').replaceChildren(svg);
  $('hourly-chart').hidden = false;
  $('hourly-details').hidden = false;
  const [year, month, day] = result.date.split('-');
  $('chart-status').textContent = `${day}/${month}/${year} · Điểm nổi bật: ${String(result.hour).padStart(2, '0')}:00 · Di chuột vào điểm để xem số lượt.`;
  $('hourly-caption').textContent = `Ước tính ngày ${day}/${month}/${year}`;
  $('hourly-rows').replaceChildren(...points.map(point => {
    const row = document.createElement('tr');
    for (const value of [`${String(point.hour).padStart(2, '0')}:00 – ${String(point.hour + 1).padStart(2, '0')}:00`, numberFormat.format(point.rounded_prediction)]) {
      const cell = document.createElement('td'); cell.textContent = value; row.append(cell);
    }
    return row;
  }));
}

async function loadModel() {
  try {
    const response = await fetch('/api/model');
    const info = await response.json();
    if (!response.ok || !info.ready) throw new Error(info.error || 'Chưa kết nối được mô hình.');
    modelReady = true;
    $('model-status').textContent = 'Mô hình đã sẵn sàng';
    $('model-status').className = 'status ready';
    for (const [id, key] of [['r2-value', 'R2'], ['mae-value', 'MAE'], ['rmse-value', 'RMSE']]) {
      $(id).textContent = typeof info.test[key] === 'number' ? numberFormat.format(info.test[key]) : '—';
    }
    button.disabled = false;
  } catch (error) {
    $('model-status').textContent = 'Chưa kết nối mô hình';
    $('model-status').className = 'status error';
    showError(error.message || 'Không kết nối được máy chủ. Vui lòng tải lại trang.');
  }
}

form.addEventListener('input', () => {
  revision++;
  updateCalendar();
  if (hasResult) {
    $('result-state').textContent = 'Cần tính lại';
    $('chart-status').textContent = 'Đầu vào đã thay đổi. Chọn “Tính dự đoán” để cập nhật biểu đồ.';
    $('peak-status').textContent = 'Đầu vào đã thay đổi. Chọn “Tính dự đoán” để cập nhật giờ cao điểm.';
    $('peak-list').hidden = true;
    $('peak-note').hidden = true;
  }
});

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (!modelReady || busy || !form.reportValidity()) return;
  busy = true;
  button.disabled = true;
  button.textContent = 'Đang tính dự đoán…';
  $('form-error').hidden = true;
  $('peak-status').textContent = 'Đang tính giờ cao điểm…';
  $('peak-list').hidden = true;
  $('peak-note').hidden = true;
  const startedAt = revision;
  const payload = { date: $('date').value, hour: Number($('hour').value), weather: Number($('weather').value), holiday: $('holiday').checked };
  for (const field of ['temperature', 'feels_like', 'humidity', 'wind_speed']) payload[field] = $(field).value.trim() === '' ? null : Number($(field).value);
  const weatherText = $('weather').selectedOptions[0].textContent;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch('/api/predict', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: controller.signal });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Không thể dự đoán.');
    // Never label an old response as a result for newly changed inputs.
    if (startedAt !== revision) {
      $('result-state').textContent = 'Cần tính lại';
      $('peak-status').textContent = 'Đầu vào đã thay đổi. Chọn “Tính dự đoán” để cập nhật giờ cao điểm.';
      return;
    }
    $('prediction-value').textContent = new Intl.NumberFormat('vi-VN').format(result.rounded_prediction);
    $('prediction-caption').textContent = 'Ước tính từ mô hình đã huấn luyện, được làm tròn đến một lượt thuê.';
    $('result-state').textContent = 'Đã dự đoán';
    const [year, month, day] = result.date.split('-');
    $('result-time').textContent = `${String(result.hour).padStart(2, '0')}:00 · ${day}/${month}/${year}`;
    $('result-weather').textContent = weatherText;
    const labels = { temp: 'nhiệt độ', atemp: 'nhiệt độ cảm nhận', hum: 'độ ẩm', windspeed: 'tốc độ gió' };
    $('imputation-note').textContent = result.imputed_features.length ? `Đã điền giá trị thiếu cho: ${result.imputed_features.map((f) => labels[f] || f).join(', ')}.` : '';
    $('imputation-note').hidden = result.imputed_features.length === 0;
    renderHourlyChart(result);
    renderPeakHours(result);
    hasResult = true;
  } catch (error) {
    showError(error.name === 'AbortError' ? 'Yêu cầu mất quá nhiều thời gian. Vui lòng thử lại.' : error.message);
    $('peak-status').textContent = 'Chưa cập nhật được giờ cao điểm. Vui lòng tính dự đoán lại.';
    $('result-state').textContent = hasResult ? 'Kết quả trước đó' : 'Chưa dự đoán';
  } finally {
    clearTimeout(timeout);
    busy = false;
    button.disabled = !modelReady;
    button.textContent = 'Tính dự đoán';
  }
});
updateCalendar();
loadModel();
