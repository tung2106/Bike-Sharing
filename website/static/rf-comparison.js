(async () => {
  const get = (id) => document.getElementById(id);
  const picker = get("rf-day");
  const status = get("rf-status");
  const svg = get("rf-chart");
  if (!svg) return;
  const modelLabel = svg.dataset.modelLabel;
  const fmt = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 });
  function draw(tag, attrs, text) {
    const el = document.createElementNS(svg.namespaceURI, tag);
    for (const [key, value] of Object.entries(attrs))
      el.setAttribute(key, value);
    if (text !== undefined) el.textContent = text;
    svg.append(el);
    return el;
  }
  function render(rows) {
    const byHour = new Map(rows.map((row) => [row.hour, row]));
    const mae =
      rows.reduce(
        (sum, row) => sum + Math.abs(row.prediction - row.actual),
        0,
      ) / rows.length;
    status.textContent =
      rows.length +
      "/24 giờ có dữ liệu · MAE trong ngày: " +
      fmt.format(mae) +
      " lượt/giờ.";
    const ceiling = Math.max(
      4,
      Math.ceil(
        Math.max(...rows.map((r) => Math.max(r.actual, r.prediction))) / 4,
      ) * 4,
    );
    const x = (h) => 54 + 28 * h;
    const y = (n) => 206 - (170 * n) / ceiling;
    svg.replaceChildren();
    draw("text", { x: 54, y: 18, class: "chart-label" }, "Lượt thuê");
    for (let i = 0; i <= 4; i++) {
      const n = (ceiling * i) / 4;
      draw("line", {
        x1: 54,
        x2: 698,
        y1: y(n),
        y2: y(n),
        class: "chart-grid",
      });
      draw(
        "text",
        { x: 46, y: y(n) + 4, "text-anchor": "end", class: "chart-label" },
        fmt.format(n),
      );
    }
    for (const h of [0, 3, 6, 9, 12, 15, 18, 21, 23])
      draw(
        "text",
        { x: x(h), y: 232, "text-anchor": "middle", class: "chart-label" },
        h + "h",
      );
    for (const [field, color] of [
      ["actual", "#106997"],
      ["prediction", "#a84a10"],
    ]) {
      let path = "";
      for (let h = 0; h < 24; h++) {
        const row = byHour.get(h);
        if (!row) continue;
        path +=
          (byHour.has(h - 1) ? "L" : "M") + x(h) + "," + y(row[field]) + " ";
        draw("circle", { cx: x(h), cy: y(row[field]), r: 2.8, fill: color });
      }
      draw("path", {
        d: path,
        fill: "none",
        stroke: color,
        "stroke-width": 2.4,
        "stroke-dasharray": field === "actual" ? "none" : "7 4",
      });
    }
    enableHourlyHover(svg, x, 36, 206, (h) => {
      const row = byHour.get(h);
      return row
        ? "Thực tế: " +
            fmt.format(row.actual) +
            " lượt\n" +
            modelLabel +
            ": " +
            fmt.format(row.prediction) +
            " lượt"
        : "Không có bản ghi";
    });
    const body = get("rf-rows");
    body.replaceChildren();
    for (let h = 0; h < 24; h++) {
      const row = byHour.get(h);
      const tr = body.insertRow();
      const values = row
        ? [row.actual, row.prediction, row.prediction - row.actual].map(
            fmt.format,
          )
        : ["—", "—", "—"];
      for (const value of [h + "h", ...values])
        tr.insertCell().textContent = value;
    }
    get("rf-results").hidden = false;
  }
  try {
    status.textContent = "Đang tải kết quả kiểm tra…";
    const response = await fetch("/api/history/model-test");
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    const dates = Object.keys(data.days).sort();
    for (const day of dates)
      picker.add(new Option(day.split("-").reverse().join("/"), day));
    picker.value =
      dates.find((day) => data.days[day].length === 24) || dates[0];
    picker.onchange = () => render(data.days[picker.value]);
    picker.disabled = false;
    render(data.days[picker.value]);
  } catch (error) {
    status.textContent = error.message || "Không tải được dữ liệu đối chiếu.";
  }
})();
