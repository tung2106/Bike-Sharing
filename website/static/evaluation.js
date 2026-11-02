// The metric and example change on screen; every score uses the same saved test hours.
(() => {
  const get = (id) => document.getElementById(id);
  const modelPicker = get("eval-model");
  const datePicker = get("eval-date");
  const hourPicker = get("eval-hour");
  const metricInputs = [
    ...document.querySelectorAll('input[name="eval-metric"]'),
  ];
  const status = get("eval-status");
  const retry = get("eval-retry");
  const format = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 })
    .format;
  const coefficient = new Intl.NumberFormat("vi-VN", {
    minimumFractionDigits: 4,
    maximumFractionDigits: 4,
  }).format;
  const dateLabel = (date) => date.slice(0, 10).split("-").reverse().join("/");
  const hourLabel = (hour) => String(hour).padStart(2, "0") + ":00";
  const metrics = {
    mae: {
      label: "MAE",
      meaning: "Số lượt dự đoán lệch trung bình mỗi giờ.",
      example: "Thực tế và dự đoán",
      rule: "Lấy độ lệch tuyệt đối từng giờ, cộng lại rồi chia cho số giờ kiểm tra.",
    },
    rmse: {
      label: "RMSE",
      meaning: "Những giờ dự đoán lệch nhiều ảnh hưởng mạnh hơn.",
      example: "Sai số qua diện tích hình vuông",
      rule: "Cạnh hình vuông là số lượt lệch. Lấy trung bình các diện tích (sai số bình phương) rồi lấy căn bậc hai.",
    },
    r2: {
      label: "R²",
      meaning:
        "Điểm 1 là khớp hoàn toàn, điểm 0 ngang với đoán mức trung bình.",
      example: "Sai số bình phương so với mốc",
      rule: "Lấy 1 trừ tỷ số giữa tổng sai số bình phương của mô hình và của mốc trung bình. R² âm khi mô hình kém hơn mốc.",
    },
  };
  let report;
  let metric = "mae";
  let loading = false;

  function score(key, value) {
    return value == null
      ? "Không xác định"
      : key === "r2"
        ? coefficient(value)
        : format(value);
  }

  function drawBars(container, entries, limits) {
    const values = entries.map((e) => e.value ?? 0);
    const [low, high] = limits ?? [
      Math.min(0, ...values),
      Math.max(0, ...values),
    ];
    const position = (v) =>
      high === low ? 0 : (100 * (v - low)) / (high - low);
    const zero = position(0);
    container.style.setProperty("--eval-zero", zero + "%");
    container.replaceChildren(
      ...entries.map(({ label, reading, value, series }) => {
        const row =
          get("eval-bar-template").content.firstElementChild.cloneNode(true);
        row.querySelector("span").textContent = label;
        row.querySelector("strong").textContent = reading;
        const fill = row.querySelector("i");
        const end = position(value ?? 0);
        fill.dataset.series = series;
        fill.style.left = Math.min(end, zero) + "%";
        fill.style.width = Math.abs(end - zero) + "%";
        return row;
      }),
    );
  }

  function drawSquares(day, selected, key) {
    const deviation = (row) => Math.abs(row[key] - row.actual);
    const other = day.reduce(
      (best, row) =>
        row !== selected && (!best || deviation(row) > deviation(best))
          ? row
          : best,
      null,
    );
    const pair = other ? [selected, other] : [selected];
    const largest = Math.max(...pair.map(deviation));
    // Scale sides, not areas: a doubled error must occupy four times the area.
    get("eval-rmse-squares").replaceChildren(
      ...pair.map((row, i) => {
        const cell = get(
          "eval-square-template",
        ).content.firstElementChild.cloneNode(true);
        cell.querySelector(".eval-square-hour").textContent =
          hourLabel(row.hour) + (i ? " · So sánh" : " · Đã chọn");
        cell.querySelector(".eval-square-side").textContent =
          "Lệch " + format(deviation(row)) + " lượt";
        cell.querySelector("i").style.width =
          (largest ? (100 * deviation(row)) / largest : 0) + "%";
        return cell;
      }),
    );
    return other;
  }

  function drawExample(model) {
    const hours = format(report.count);
    const bars = get("eval-example-bars");
    const note = get("eval-takeaway");
    const term = get("eval-term");
    const total = get("eval-total");
    // R² compares whole-test sums, so a date or hour cannot change its chart.
    if (metric === "r2") {
      const baseline = report.baseline_squares;
      bars.hidden = baseline === 0;
      if (baseline === 0) {
        bars.replaceChildren();
        note.textContent = "R² không xác định: mọi giờ có cùng số lượt thuê.";
        term.textContent = "Tổng sai số bình phương của mốc trung bình bằng 0.";
        total.textContent = "Không thể chia cho 0.";
        return;
      }
      const share = format((100 * model.squared_sum) / baseline) + "%";
      drawBars(bars, [
        {
          label: "Đoán mức trung bình",
          reading: "100%",
          value: baseline,
          series: "reference",
        },
        {
          label: model.label,
          reading: share,
          value: model.squared_sum,
          series: "estimate",
        },
      ]);
      note.textContent = `Mốc 100%: luôn đoán ${format(report.actual_mean)} lượt/giờ.`;
      term.textContent = `Tính trên toàn bộ ${hours} giờ kiểm tra.`;
      total.textContent = `R² ≈ 1 − (${format(model.squared_sum)} ÷ ${format(baseline)}) ≈ ${coefficient(model.r2)}`;
      return;
    }
    const day = report.days[datePicker.value];
    const row = day.find((r) => r.hour === Number(hourPicker.value));
    const predicted = row[model.key],
      error = predicted - row.actual,
      absolute = Math.abs(error);
    if (metric === "mae") {
      drawBars(bars, [
        {
          label: "Thực tế",
          reading: format(row.actual) + " lượt",
          value: row.actual,
          series: "reference",
        },
        {
          label: "Dự đoán",
          reading: format(predicted) + " lượt",
          value: predicted,
          series: "estimate",
        },
      ]);
      const amount = absolute < 0.005 ? "chưa tới 0,01" : format(absolute);
      note.textContent = !error
        ? "Dự đoán khớp với thực tế."
        : `Dự đoán ${error > 0 ? "cao" : "thấp"} hơn ${amount} lượt.`;
      term.textContent = `Giờ đã chọn: |${format(predicted)} − ${format(row.actual)}| ≈ ${format(absolute)} lượt.`;
      total.textContent = `MAE ≈ ${format(model.absolute_sum)} ÷ ${hours} ≈ ${format(model.mae)} lượt/giờ`;
    } else {
      const other = drawSquares(day, row, model.key);
      note.textContent = other
        ? `${hourLabel(other.hour)} lệch nhiều nhất trong các giờ còn lại của ngày.`
        : "Ngày này chỉ có một giờ trong tập kiểm tra.";
      const squaredTerm = (r) =>
        `${hourLabel(r.hour)}: ${format(Math.abs(r[model.key] - r.actual))}² ≈ ${format((r[model.key] - r.actual) ** 2)} lượt².`;
      term.textContent = [row, ...(other ? [other] : [])]
        .map(squaredTerm)
        .join(" ");
      total.textContent = `RMSE ≈ √(${format(model.squared_sum)} ÷ ${hours}) ≈ ${format(model.rmse)} lượt/giờ`;
    }
  }

  const selectedModel = () =>
    report.models.find((m) => m.key === modelPicker.value);

  function showMetric() {
    const model = selectedModel();
    const info = metrics[metric];
    for (const key of Object.keys(metrics)) {
      get("eval-score-" + key).textContent = score(key, model[key]);
    }
    get("eval-chart-title").textContent = "So sánh " + info.label;
    get("eval-direction").textContent =
      metric === "r2" ? "↑ Càng cao càng tốt" : "↓ Càng thấp càng tốt";
    get("eval-meaning").textContent = info.meaning;
    // MAE and RMSE keep the same scale (rentals/hour). R² can be negative.
    const limits =
      metric === "r2"
        ? [Math.min(0, ...report.models.map((m) => Math.floor(m.r2 ?? 0))), 1]
        : [
            0,
            Math.max(
              10,
              10 *
                Math.ceil(
                  Math.max(...report.models.flatMap((m) => [m.mae, m.rmse])) /
                    10,
                ),
            ),
          ];
    drawBars(
      get("eval-model-bars"),
      report.models.map((m) => ({
        label: m.label,
        reading: score(metric, m[metric]),
        value: m[metric],
        series: m.key,
      })),
      limits,
    );
    get("eval-example-title").textContent = info.example;
    get("eval-time-pickers").hidden = metric === "r2";
    get("eval-example-bars").hidden = metric === "rmse";
    get("eval-rmse-squares").hidden = metric !== "rmse";
    get("eval-calculation-label").textContent = "Xem cách tính " + info.label;
    get("eval-rule").textContent = info.rule;
    drawExample(model);
  }

  function fillHours() {
    const previous = hourPicker.value;
    const rows = report.days[datePicker.value];
    hourPicker.replaceChildren(
      ...rows.map((r) => new Option(hourLabel(r.hour), r.hour)),
    );
    if (rows.some((r) => String(r.hour) === previous))
      hourPicker.value = previous;
  }

  async function openEvaluation() {
    if (location.hash !== "#danh-gia" || report || loading) return;
    loading = true;
    status.textContent = "Đang tải kết quả…";
    retry.hidden = retry.disabled = true;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch("/api/evaluation", {
        signal: controller.signal,
      });
      if (!response.ok) throw new Error("unavailable");
      const data = await response.json();
      const days = Object.keys(data.days)
        .filter((date) => data.days[date].length)
        .sort();
      if (!data.count || !data.models.length || !days.length) {
        status.textContent = "Chưa có dữ liệu kiểm tra.";
        retry.hidden = retry.disabled = false;
        return;
      }
      modelPicker.replaceChildren(
        ...data.models.map((m) => new Option(m.label, m.key)),
      );
      const active = data.default_model || "rf85";
      modelPicker.value = data.models.some((m) => m.key === active)
        ? active
        : data.models[0].key;
      datePicker.replaceChildren(
        ...days.map((day) => new Option(dateLabel(day), day)),
      );
      report = data;
      fillHours();
      metricInputs.find((input) => input.value === metric).checked = true;
      showMetric();
      status.textContent = `${format(data.count)} giờ kiểm tra · ${dateLabel(data.first)} – ${dateLabel(data.last)}`;
      get("eval-model-control").hidden = get("eval-content").hidden = false;
    } catch {
      report = null;
      status.textContent = "Chưa tải được kết quả đánh giá.";
      retry.hidden = retry.disabled = false;
    } finally {
      clearTimeout(timer);
      loading = false;
    }
  }

  for (const input of metricInputs)
    input.addEventListener("change", () => {
      if (!input.checked) return;
      metric = input.value;
      get("eval-calculation").open = false;
      showMetric();
    });
  modelPicker.addEventListener("change", showMetric);
  datePicker.addEventListener("change", () => {
    fillHours();
    drawExample(selectedModel());
  });
  hourPicker.addEventListener("change", () => drawExample(selectedModel()));
  retry.addEventListener("click", openEvaluation);
  window.addEventListener("hashchange", openEvaluation);
  openEvaluation();
})();
