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
  if (hasResult) $('result-state').textContent = 'Cần tính lại';
});

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (!modelReady || busy || !form.reportValidity()) return;
  busy = true;
  button.disabled = true;
  button.textContent = 'Đang tính dự đoán…';
  $('form-error').hidden = true;
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
    if (startedAt !== revision) { $('result-state').textContent = 'Cần tính lại'; return; }
    $('prediction-value').textContent = new Intl.NumberFormat('vi-VN').format(result.rounded_prediction);
    $('prediction-caption').textContent = 'Ước tính từ mô hình đã huấn luyện, được làm tròn đến một lượt thuê.';
    $('result-state').textContent = 'Đã dự đoán';
    const [year, month, day] = result.date.split('-');
    $('result-time').textContent = `${String(result.hour).padStart(2, '0')}:00 · ${day}/${month}/${year}`;
    $('result-weather').textContent = weatherText;
    const labels = { temp: 'nhiệt độ', atemp: 'nhiệt độ cảm nhận', hum: 'độ ẩm', windspeed: 'tốc độ gió' };
    $('imputation-note').textContent = result.imputed_features.length ? `Đã điền giá trị thiếu cho: ${result.imputed_features.map((f) => labels[f] || f).join(', ')}.` : '';
    $('imputation-note').hidden = result.imputed_features.length === 0;
    hasResult = true;
  } catch (error) {
    showError(error.name === 'AbortError' ? 'Yêu cầu mất quá nhiều thời gian. Vui lòng thử lại.' : error.message);
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
