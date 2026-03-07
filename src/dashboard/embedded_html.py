"""Embedded HTML fallback pages (used when client/dist/ is not available)."""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>XianyuAutoAgent Control Panel</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      min-height: 100vh;
      padding: 20px;
    }
    .container {
      max-width: 1200px;
      margin: 0 auto;
      background: #fff;
      border-radius: 12px;
      box-shadow: 0 20px 60px rgba(0,0,0,0.3);
      padding: 36px;
    }
    h1 {
      color: #333;
      margin-bottom: 24px;
      font-size: 32px;
    }
    .quickstart {
      margin-bottom: 20px;
      padding: 14px 16px;
      border: 1px solid #dbeafe;
      background: #eff6ff;
      border-radius: 8px;
      color: #1e3a8a;
      font-size: 13px;
      line-height: 1.7;
    }
    .quickstart strong { color: #1d4ed8; }
    .quickstart code { background: #dbeafe; padding: 1px 5px; border-radius: 4px; }
    .action-row {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 12px;
      margin-bottom: 16px;
    }
    .action-btn {
      border: none;
      padding: 10px 14px;
      border-radius: 8px;
      cursor: pointer;
      font-size: 13px;
      font-weight: 700;
      color: #fff;
      background: #3b82f6;
    }
    .action-btn.warning { background: #f59e0b; }
    .action-btn:hover { opacity: 0.92; }
    .service-box {
      margin-bottom: 26px;
      padding: 18px;
      background: #f8f9fa;
      border-radius: 8px;
      border-left: 4px solid #667eea;
    }
    .service-title {
      color: #333;
      margin-bottom: 12px;
      font-size: 20px;
      font-weight: 700;
    }
    .service-row {
      display: flex;
      gap: 12px;
      align-items: center;
      flex-wrap: wrap;
    }
    .badge {
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 13px;
      font-weight: 700;
      color: #fff;
      background: #28a745;
    }
    .service-btn {
      border: none;
      padding: 9px 16px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 14px;
      font-weight: 600;
      transition: all 0.2s ease;
    }
    .service-btn:hover { transform: translateY(-1px); }
    .btn-suspend { background: #ffc107; color: #333; }
    .btn-resume { background: #28a745; color: #fff; }
    .btn-start { background: #1f9d55; color: #fff; }
    .btn-stop { background: #dc3545; color: #fff; }
    .service-msg {
      margin-top: 10px;
      color: #666;
      font-size: 12px;
    }
    .btn-note {
      margin-top: 8px;
      color: #6b7280;
      font-size: 12px;
      line-height: 1.6;
    }

    .module-box {
      margin-bottom: 24px;
      padding: 18px;
      background: #f8f9fa;
      border-radius: 8px;
      border-left: 4px solid #764ba2;
    }
    .module-title {
      color: #333;
      margin-bottom: 14px;
      font-size: 20px;
      font-weight: 700;
    }
    .module-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
      gap: 12px;
    }
    .module-card {
      background: #fff;
      border-radius: 8px;
      padding: 14px;
      border: 2px solid #e0e0e0;
      transition: all 0.2s ease;
      cursor: pointer;
    }
    .module-card:hover {
      border-color: #667eea;
      transform: translateY(-2px);
      box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }
    .module-card h3 {
      margin-bottom: 4px;
      color: #333;
      font-size: 16px;
    }
    .module-card p { color: #666; font-size: 12px; }

    .status-box {
      background: #f8f9fa;
      border-radius: 8px;
      padding: 16px;
      margin-bottom: 14px;
      border-left: 4px solid #667eea;
    }
    .status-box h2 {
      color: #333;
      font-size: 18px;
      margin-bottom: 12px;
    }
    .status-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 8px 0;
      border-bottom: 1px solid #e5e7eb;
      gap: 10px;
    }
    .status-item:last-child { border-bottom: none; }
    .status-label { color: #4b5563; font-size: 14px; }
    .status-value { font-size: 14px; font-weight: 600; }
    .status-value.success { color: #28a745; }
    .status-value.warning { color: #f59e0b; }
    .status-value.error { color: #dc3545; }
    .status-value.info { color: #0ea5e9; }

    .refresh-btn {
      width: 100%;
      background: #667eea;
      color: #fff;
      border: none;
      padding: 10px 14px;
      border-radius: 6px;
      cursor: pointer;
      margin-top: 10px;
      font-weight: 600;
      font-size: 14px;
    }
    .refresh-btn:hover { background: #5568d3; }

    .charts-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
      gap: 16px;
      margin-top: 24px;
    }
    .chart-box {
      background: #fff;
      border-radius: 8px;
      padding: 16px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.1);
      border: 1px solid #e5e7eb;
    }
    .chart-box h3 {
      color: #333;
      font-size: 16px;
      margin-bottom: 10px;
      text-align: center;
    }
    .chart-container { position: relative; height: 280px; }
    .chart-info {
      margin-bottom: 8px;
      color: #666;
      font-size: 12px;
      text-align: center;
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>XianyuAutoAgent Control Panel</h1>
    <div class="quickstart">
      <strong>3步上手（推荐）</strong><br>
      1. 配置管理里导入 Cookie。<br>
      2. 配置管理里导入路线数据与加价数据。<br>
      3. 首页点“启动服务”并执行“全链路体检”。<br>
      体检失败时：先更新 Cookie，再点“售前一键恢复”。<br>
    </div>
    <div class="quickstart">
      <strong>0基础快速上手（建议按顺序）</strong><br>
      1. 先点“配置管理”填写 Cookie。<br>
      2. 在“路线数据”导入报价表。<br>
      3. 在“测试调试”里先验证报价与回复。<br>
      4. 回到首页启动服务，确认状态为“运行中”。<br>
      5. 用“日志查看/实时日志”排查问题。<br>
      默认面板地址：<code>http://127.0.0.1:8091</code>
    </div>

    <div class="status-box" style="border-left-color:#0ea5e9;">
      <h2>系统概览条</h2>
      <div id="systemOverviewStrip"></div>
    </div>

    <div class="service-box">
      <div class="service-title">服务控制</div>
      <div class="service-row">
        <span style="color:#666;font-size:14px;">服务状态：</span>
        <span id="serviceStatusBadge" class="badge">运行中</span>
        <button id="suspendBtn" class="service-btn btn-suspend" title="临时暂停自动处理消息，不会退出程序" onclick="controlService('suspend')">挂起服务</button>
        <button id="resumeBtn" class="service-btn btn-resume" title="从挂起状态恢复自动处理" onclick="controlService('resume')" style="display:none;">恢复服务</button>
        <button id="startBtn" class="service-btn btn-start" title="服务已停止时重新启动" onclick="controlService('start')" style="display:none;">启动服务</button>
        <button id="stopBtn" class="service-btn btn-stop" title="停止自动处理（需手动再启动）" onclick="controlService('stop')">关闭服务</button>
      </div>
      <div class="btn-note">按钮说明：挂起适合临时停；关闭是完全停；恢复/启动用于继续运行。</div>
      <div id="serviceStatusMessage" class="service-msg"></div>
    </div>

    <div class="module-box">
      <div class="module-title">功能模块</div>
      <div class="module-grid">
        <div class="module-card" onclick="window.location.href='/cookie'">
          <h3>配置管理</h3>
          <p>Cookie、路线数据、回复模板</p>
        </div>
        <div class="module-card" onclick="window.location.href='/test'">
          <h3>测试调试</h3>
          <p>测试自动回复与报价结果</p>
        </div>
        <div class="module-card" onclick="window.location.href='/logs'">
          <h3>日志查看</h3>
          <p>分页检索历史日志</p>
        </div>
        <div class="module-card" onclick="window.location.href='/logs/realtime'">
          <h3>实时日志</h3>
          <p>实时监控运行状态</p>
        </div>
      </div>
    </div>

    <div class="status-box">
      <h2>系统运行状况</h2>
      <div id="systemStatusContent"></div>
    </div>

    <div class="status-box">
      <h2>咸鱼客服状态</h2>
      <div id="xianyuStatusContent"></div>
    </div>

    <div class="status-box">
      <h2>路线数据情况</h2>
      <div id="routeStatusContent"></div>
    </div>

    <div class="status-box">
      <h2>消息回复统计</h2>
      <div id="messageStatusContent"></div>
    </div>

    <div class="status-box">
      <h2>Wave C 虚拟商品总览</h2>
      <div id="virtualGoodsMetricsContent"></div>
      <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
        <input id="inspectOrderId" type="text" placeholder="输入订单号查看 drill-down" style="flex:1;min-width:260px;padding:8px;border:1px solid #d1d5db;border-radius:6px;">
        <button class="action-btn" onclick="inspectVirtualGoodsOrder()">inspect_order</button>
      </div>
      <div id="virtualGoodsInspectContent" style="margin-top:10px;color:#374151;font-size:12px;line-height:1.7;white-space:pre-wrap;"></div>
    </div>

    <div class="status-box">
      <h2>闲管家自动履约</h2>
      <div id="xgjStatusContent"></div>
      <div style="margin-top:12px; display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:12px;">
        <div style="border:1px solid #e5e7eb; border-radius:8px; padding:12px; background:#f8fafc;">
          <div style="font-weight:700; margin-bottom:10px;">连接与开关</div>
          <input id="xgjAppKey" type="text" placeholder="AppKey" style="width:100%; padding:8px; margin-bottom:8px; border:1px solid #d1d5db; border-radius:6px;">
          <input id="xgjAppSecret" type="password" placeholder="AppSecret（留空表示不改）" style="width:100%; padding:8px; margin-bottom:8px; border:1px solid #d1d5db; border-radius:6px;">
          <input id="xgjMerchantId" type="text" placeholder="Merchant ID（可选）" style="width:100%; padding:8px; margin-bottom:8px; border:1px solid #d1d5db; border-radius:6px;">
          <input id="xgjBaseUrl" type="text" placeholder="Base URL" style="width:100%; padding:8px; margin-bottom:8px; border:1px solid #d1d5db; border-radius:6px;">
          <label style="display:block; margin:6px 0; color:#374151;"><input id="xgjAutoPriceEnabled" type="checkbox"> 启用 API 改价通道</label>
          <label style="display:block; margin:6px 0; color:#374151;"><input id="xgjAutoShipEnabled" type="checkbox"> 启用自动物流发货</label>
          <label style="display:block; margin:6px 0 10px; color:#374151;"><input id="xgjAutoShipOnPaid" type="checkbox"> 支付后自动触发履约</label>
          <button class="action-btn" style="width:100%;" onclick="saveXgjSettings()">保存闲管家设置</button>
        </div>
        <div style="border:1px solid #e5e7eb; border-radius:8px; padding:12px; background:#f8fafc;">
          <div style="font-weight:700; margin-bottom:10px;">手动重试改价</div>
          <input id="xgjRetryProductId" type="text" placeholder="商品 ID" style="width:100%; padding:8px; margin-bottom:8px; border:1px solid #d1d5db; border-radius:6px;">
          <input id="xgjRetryNewPrice" type="number" min="0" step="0.01" placeholder="新价格" style="width:100%; padding:8px; margin-bottom:8px; border:1px solid #d1d5db; border-radius:6px;">
          <input id="xgjRetryOldPrice" type="number" min="0" step="0.01" placeholder="原价（可选）" style="width:100%; padding:8px; margin-bottom:8px; border:1px solid #d1d5db; border-radius:6px;">
          <button class="action-btn" style="width:100%;" onclick="retryXgjPrice()">提交 API 改价</button>
        </div>
        <div style="border:1px solid #e5e7eb; border-radius:8px; padding:12px; background:#f8fafc;">
          <div style="font-weight:700; margin-bottom:10px;">手动重试发货</div>
          <input id="xgjRetryOrderId" type="text" placeholder="订单号" style="width:100%; padding:8px; margin-bottom:8px; border:1px solid #d1d5db; border-radius:6px;">
          <input id="xgjRetryWaybillNo" type="text" placeholder="物流单号" style="width:100%; padding:8px; margin-bottom:8px; border:1px solid #d1d5db; border-radius:6px;">
          <input id="xgjRetryExpressName" type="text" placeholder="快递公司名称（如 圆通）" style="width:100%; padding:8px; margin-bottom:8px; border:1px solid #d1d5db; border-radius:6px;">
          <input id="xgjRetryExpressCode" type="text" placeholder="快递编码（可选）" style="width:100%; padding:8px; margin-bottom:8px; border:1px solid #d1d5db; border-radius:6px;">
          <button class="action-btn warning" style="width:100%;" onclick="retryXgjShip()">提交 API 发货</button>
        </div>
      </div>
    </div>

    <div class="action-row">
      <button class="refresh-btn" onclick="loadStatus()">刷新所有状态</button>
      <button class="action-btn" onclick="runFullCheck()">全链路体检</button>
      <button class="action-btn" onclick="runAutoFix()">一键修复</button>
      <button class="action-btn warning" onclick="recoverPresales()">售前一键恢复</button>
    </div>

    <div class="status-box" id="doctorStatusBox" style="display:none;">
      <h2>全链路体检结果</h2>
      <div id="doctorStatusContent"></div>
    </div>

    <div class="charts-grid" id="chartsContainer" style="display:none;">
      <div class="chart-box">
        <h3>最近24小时回复趋势</h3>
        <div class="chart-container"><canvas id="hourlyChart"></canvas></div>
      </div>
      <div class="chart-box">
        <h3>最近7天回复统计</h3>
        <div class="chart-container"><canvas id="dailyChart"></canvas></div>
      </div>
      <div class="chart-box">
        <h3>快递公司路线分布</h3>
        <div class="chart-container"><canvas id="courierChart"></canvas></div>
      </div>
      <div class="chart-box">
        <h3>路线数据概览</h3>
        <div id="routeChartInfo" class="chart-info"></div>
        <div class="chart-container"><canvas id="routeChart"></canvas></div>
      </div>
    </div>
  </div>

  <script>
    let hourlyChart = null;
    let dailyChart = null;
    let courierChart = null;
    let routeChart = null;

    function statusClassByBool(v) {
      return v ? "success" : "error";
    }

    function statusClassByService(v) {
      if (v === "running") return "success";
      if (v === "degraded") return "warning";
      if (v === "suspended") return "warning";
      return "error";
    }

    function statusClassByRisk(level) {
      if (level === "blocked") return "error";
      if (level === "warning") return "warning";
      if (level === "normal") return "success";
      return "info";
    }

    function statusClassByRecovery(stage) {
      if (stage === "healthy") return "success";
      if (stage === "recover_triggered") return "warning";
      if (stage === "waiting_cookie_update" || stage === "waiting_reconnect") return "warning";
      if (stage === "inactive") return "info";
      return "info";
    }

    function recoveryStageText(stage, stageLabel) {
      const s = String(stage || "").trim();
      if (stageLabel) return String(stageLabel);
      if (s === "healthy") return "链路正常";
      if (s === "recover_triggered") return "已触发自动恢复";
      if (s === "waiting_cookie_update") return "等待更新 Cookie";
      if (s === "waiting_reconnect") return "等待重连";
      if (s === "token_error") return "鉴权异常";
      if (s === "inactive") return "服务未运行";
      if (s === "monitoring") return "监控中";
      return "状态未知";
    }

    function row(label, value, cls) {
      return (
        '<div class="status-item">' +
        '<span class="status-label">' + label + "</span>" +
        '<span class="status-value ' + (cls || "info") + '">' + value + "</span>" +
        "</div>"
      );
    }

    function formatCount(n) {
      const val = Number(n || 0);
      return Number.isFinite(val) ? val.toLocaleString() : "0";
    }

    function updateServiceStatus(status) {
      const badge = document.getElementById("serviceStatusBadge");
      const suspendBtn = document.getElementById("suspendBtn");
      const resumeBtn = document.getElementById("resumeBtn");
      const startBtn = document.getElementById("startBtn");
      const stopBtn = document.getElementById("stopBtn");
      const messageEl = document.getElementById("serviceStatusMessage");

      if (status === "running") {
        badge.textContent = "运行中";
        badge.style.background = "#28a745";
        suspendBtn.style.display = "inline-block";
        resumeBtn.style.display = "none";
        startBtn.style.display = "none";
        stopBtn.style.display = "inline-block";
        messageEl.textContent = "服务正在运行，正常处理消息";
      } else if (status === "degraded") {
        badge.textContent = "降级运行";
        badge.style.background = "#f59e0b";
        suspendBtn.style.display = "inline-block";
        resumeBtn.style.display = "none";
        startBtn.style.display = "none";
        stopBtn.style.display = "inline-block";
        messageEl.textContent = "服务在运行，但鉴权或风控异常导致自动回复受限";
      } else if (status === "suspended") {
        badge.textContent = "已挂起";
        badge.style.background = "#f59e0b";
        suspendBtn.style.display = "none";
        resumeBtn.style.display = "inline-block";
        startBtn.style.display = "none";
        stopBtn.style.display = "inline-block";
        messageEl.textContent = "服务已挂起，不会处理新消息";
      } else {
        badge.textContent = "已停止";
        badge.style.background = "#dc3545";
        suspendBtn.style.display = "none";
        resumeBtn.style.display = "none";
        startBtn.style.display = "inline-block";
        stopBtn.style.display = "none";
        messageEl.textContent = "服务已停止";
      }
    }

    function controlService(action) {
      if (action === "stop" && !confirm("确定要关闭服务吗？")) return;

      fetch("/api/service/control", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: action })
      })
      .then(r => r.json())
      .then(data => {
        if (!data.success) throw new Error(data.error || "操作失败");
        updateServiceStatus(data.status || "running");
        loadStatus();
      })
      .catch(err => alert("操作失败: " + err.message));
    }

    function buildHourlySeries(hourlyMap) {
      const labels = [];
      const values = [];
      for (let i = 0; i < 24; i++) {
        const h = String(i).padStart(2, "0");
        labels.push(h + ":00");
        values.push(Number((hourlyMap || {})[h] || 0));
      }
      return { labels, values };
    }

    function buildDailySeries(dailyMap) {
      const localDateKey = (d) => {
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, "0");
        const day = String(d.getDate()).padStart(2, "0");
        return y + "-" + m + "-" + day;
      };
      const labels = [];
      const values = [];
      for (let i = 6; i >= 0; i--) {
        const d = new Date();
        d.setDate(d.getDate() - i);
        const key = localDateKey(d);
        labels.push((d.getMonth() + 1) + "/" + d.getDate());
        values.push(Number((dailyMap || {})[key] || 0));
      }
      return { labels, values };
    }

    function renderCharts(data) {
      const messageStats = data.message_stats || {};
      const routeByCourier = data.route_stats_by_courier || {};
      const routeStats = data.route_stats || {};
      document.getElementById("chartsContainer").style.display = "grid";

      const hourly = buildHourlySeries(messageStats.hourly_replies || {});
      const daily = buildDailySeries(messageStats.daily_replies || {});

      if (hourlyChart) hourlyChart.destroy();
      hourlyChart = new Chart(document.getElementById("hourlyChart").getContext("2d"), {
        type: "line",
        data: {
          labels: hourly.labels,
          datasets: [{
            label: "回复数",
            data: hourly.values,
            borderColor: "#667eea",
            backgroundColor: "rgba(102,126,234,0.15)",
            fill: true,
            tension: 0.35
          }]
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
      });

      if (dailyChart) dailyChart.destroy();
      dailyChart = new Chart(document.getElementById("dailyChart").getContext("2d"), {
        type: "bar",
        data: {
          labels: daily.labels,
          datasets: [{ label: "回复数", data: daily.values, backgroundColor: "#764ba2" }]
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
      });

      const courierLabels = Object.keys(routeByCourier);
      const courierData = Object.values(routeByCourier);
      if (courierChart) courierChart.destroy();
      courierChart = new Chart(document.getElementById("courierChart").getContext("2d"), {
        type: "doughnut",
        data: {
          labels: courierLabels.length ? courierLabels : ["暂无数据"],
          datasets: [{
            data: courierData.length ? courierData : [1],
            backgroundColor: ["#667eea", "#764ba2", "#f093fb", "#4facfe", "#43e97b", "#fa709a"]
          }]
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: "bottom" } } }
      });

      document.getElementById("routeChartInfo").textContent =
        "总路线数: " + formatCount(routeStats.routes) + " 条 | 快递公司数: " + formatCount(routeStats.couriers) + " 家";

      if (routeChart) routeChart.destroy();
      routeChart = new Chart(document.getElementById("routeChart").getContext("2d"), {
        type: "bar",
        data: {
          labels: ["快递公司", "路线总数"],
          datasets: [{
            data: [Number(routeStats.couriers || 0), Number(routeStats.routes || 0)],
            backgroundColor: ["#667eea", "#764ba2"]
          }]
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
      });
    }

    function renderStatusBlocks(data) {
      const routeStats = data.route_stats || {};
      const msgStats = data.message_stats || {};
      const xgj = data.xianguanjia || {};
      const modules = (data.module && data.module.modules) || {};
      const risk = data.risk_control || {};
      const aliveCount = Number(data.alive_count || 0);
      const totalModules = Number(data.total_modules || 0);

      document.getElementById("systemOverviewStrip").innerHTML = [
        row("service_status", data.service_status || "-", statusClassByService(data.service_status)),
        row("alive_count/total_modules", formatCount(aliveCount) + " / " + formatCount(totalModules), aliveCount > 0 ? "success" : "warning"),
        row("cookie_exists", data.cookie_exists ? "true" : "false", statusClassByBool(!!data.cookie_exists)),
        row("xianyu_connected", data.xianyu_connected ? "true" : "false", statusClassByBool(!!data.xianyu_connected)),
        row("token_available", data.token_available ? "true" : "false", statusClassByBool(!!data.token_available)),
        row("recovery_stage", data.recovery_stage || "-", statusClassByRecovery(data.recovery_stage || "monitoring"))
      ].join("");

      document.getElementById("systemStatusContent").innerHTML = [
        row("系统运行", data.system_running ? "运行中" : "未运行", statusClassByBool(!!data.system_running)),
        row("服务状态", data.service_status || "unknown", statusClassByService(data.service_status)),
        row("模块在线", formatCount(aliveCount) + " / " + formatCount(totalModules), aliveCount > 0 ? "success" : "warning"),
        row("启动时间", data.service_start_time || "-", "info")
      ].join("");

      const presalesAlive = !!((modules.presales || {}).process || {}).alive;
      const riskLevel = String(risk.level || "unknown");
      const riskScore = Number(risk.score || 0);
      const signalText = Array.isArray(risk.signals) && risk.signals.length ? risk.signals.join(" | ") : "-";
      const riskEvent = ((risk.last_event_at || "") + " " + (risk.last_event || "-")).trim();
      const tokenError = data.token_error || "-";
      const recovery = data.recovery || {};
      const recoveryStage = String(recovery.stage || "monitoring");
      const recoveryStageLabel = String(recovery.stage_label || "");
      const recoveryTriggered = !!recovery.auto_recover_triggered;
      const recoveryReason = String(recovery.reason || "-");
      const recoveryAdvice = String(recovery.advice || "-");
      const recoveryAt = String(recovery.last_auto_recover_at || "-");
      document.getElementById("xianyuStatusContent").innerHTML = [
        row("Cookie存在", data.cookie_exists ? "是" : "否", statusClassByBool(!!data.cookie_exists)),
        row("Cookie长度", formatCount(data.cookie_length || 0), "info"),
        row("售前模块进程", presalesAlive ? "已连接" : "未连接", statusClassByBool(presalesAlive)),
        row("闲鱼链路连接", data.xianyu_connected ? "可用" : "不可用", statusClassByBool(!!data.xianyu_connected)),
        row("Token可用", data.token_available ? "是" : "否", statusClassByBool(!!data.token_available)),
        row("Token异常", tokenError, tokenError === "-" ? "info" : "error"),
        row("需更新Cookie", data.cookie_update_required ? "是" : "否", data.cookie_update_required ? "warning" : "success"),
        row("封控状态", risk.label || "未知", statusClassByRisk(riskLevel)),
        row("风险分/信号", String(riskScore) + " / " + signalText, statusClassByRisk(riskLevel)),
        row("最近封控事件", riskEvent, riskLevel === "blocked" ? "error" : "info"),
        row("恢复阶段", recoveryStageText(recoveryStage, recoveryStageLabel), statusClassByRecovery(recoveryStage)),
        row("自动恢复触发", recoveryTriggered ? "是" : "否", recoveryTriggered ? "warning" : "info"),
        row("恢复原因", recoveryReason, "info"),
        row("建议操作", recoveryAdvice, "info"),
        row("最近恢复时间", recoveryAt, "info")
      ].join("");

      document.getElementById("routeStatusContent").innerHTML = [
        row("快递公司数", formatCount(routeStats.couriers || 0), "info"),
        row("路线总数", formatCount(routeStats.routes || 0), "info"),
        row("最后更新", routeStats.last_updated || "-", "info")
      ].join("");

      document.getElementById("messageStatusContent").innerHTML = [
        row("累计回复", formatCount(msgStats.total_replied || 0), "info"),
        row("今日回复", formatCount(msgStats.today_replied || 0), "info"),
        row("最近事件", formatCount(msgStats.recent_replied || 0), "info"),
        row("会话数量", formatCount(msgStats.total_conversations || 0), "info")
      ].join("");

      document.getElementById("xgjStatusContent").innerHTML = [
        row("凭证状态", xgj.configured ? "已配置" : "未配置", xgj.configured ? "success" : "warning"),
        row("API 地址", xgj.base_url || "-", "info"),
        row("自动改价", xgj.auto_price_enabled ? "开启" : "关闭", xgj.auto_price_enabled ? "success" : "warning"),
        row("自动发货", xgj.auto_ship_enabled ? "开启" : "关闭", xgj.auto_ship_enabled ? "success" : "warning"),
        row("支付后自动触发", xgj.auto_ship_on_paid ? "开启" : "关闭", xgj.auto_ship_on_paid ? "success" : "warning"),
        row("订单推送地址", xgj.callback_url || "/api/orders/callback", "info")
      ].join("");

      document.getElementById("xgjAppKey").value = xgj.app_key || "";
      document.getElementById("xgjMerchantId").value = xgj.merchant_id || "";
      document.getElementById("xgjBaseUrl").value = xgj.base_url || "https://open.goofish.pro";
      document.getElementById("xgjAppSecret").value = "";
      document.getElementById("xgjAutoPriceEnabled").checked = !!xgj.auto_price_enabled;
      document.getElementById("xgjAutoShipEnabled").checked = !!xgj.auto_ship_enabled;
      document.getElementById("xgjAutoShipOnPaid").checked = !!xgj.auto_ship_on_paid;
    }

    async function saveXgjSettings() {
      try {
        const res = await fetch("/api/xgj/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            app_key: document.getElementById("xgjAppKey").value.trim(),
            app_secret: document.getElementById("xgjAppSecret").value.trim(),
            merchant_id: document.getElementById("xgjMerchantId").value.trim(),
            base_url: document.getElementById("xgjBaseUrl").value.trim(),
            auto_price_enabled: document.getElementById("xgjAutoPriceEnabled").checked,
            auto_ship_enabled: document.getElementById("xgjAutoShipEnabled").checked,
            auto_ship_on_paid: document.getElementById("xgjAutoShipOnPaid").checked
          })
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "保存失败");
        await loadStatus();
        alert(data.message || "闲管家设置已保存");
      } catch (err) {
        alert("保存失败: " + err.message);
      }
    }

    async function retryXgjPrice() {
      try {
        const res = await fetch("/api/xgj/retry-price", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            product_id: document.getElementById("xgjRetryProductId").value.trim(),
            new_price: document.getElementById("xgjRetryNewPrice").value.trim(),
            original_price: document.getElementById("xgjRetryOldPrice").value.trim()
          })
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "改价失败");
        alert("改价成功，通道: " + (data.channel || "unknown"));
      } catch (err) {
        alert("改价失败: " + err.message);
      }
    }

    async function retryXgjShip() {
      try {
        const res = await fetch("/api/xgj/retry-ship", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            order_id: document.getElementById("xgjRetryOrderId").value.trim(),
            waybill_no: document.getElementById("xgjRetryWaybillNo").value.trim(),
            express_name: document.getElementById("xgjRetryExpressName").value.trim(),
            express_code: document.getElementById("xgjRetryExpressCode").value.trim()
          })
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "发货失败");
        alert("发货结果: " + ((data.delivery && data.delivery.message) || data.status || "success"));
      } catch (err) {
        alert("发货失败: " + err.message);
      }
    }

    function renderVirtualGoodsMetrics(payload) {
      const box = document.getElementById("virtualGoodsMetricsContent");
      if (!payload || !payload.success) {
        box.innerHTML = [row("模块状态", "未就绪", "warning"), row("原因", (payload && payload.error) || "-", "info")].join("");
        return;
      }

      const panels = payload.dashboard_panels || {};
      const funnel = panels.operations_funnel_overview || {};
      const exceptionPool = panels.exception_priority_pool || {};
      const efficiency = panels.fulfillment_efficiency || {};
      const productOps = panels.product_operations || {};
      const productSummary = productOps.summary || {};
      const productFieldState = productOps.field_state || {};
      const drillDown = panels.drill_down || {};

      const exceptionItems = Array.isArray(exceptionPool.items) ? exceptionPool.items : [];
      const exceptionPreview = exceptionItems
        .slice(0, 3)
        .map((x) => [x.priority || "P1", x.type || "UNKNOWN", "x" + formatCount(x.count || 0)].join(" "))
        .join(" | ") || "-";

      const stableFields = ["exposure_count","paid_order_count","paid_amount_cents","refund_order_count","exception_count","manual_takeover_count","conversion_rate_pct"];
      const productSummaryText = stableFields.map((k) => {
        const state = productFieldState[k] || "placeholder";
        const val = productSummary[k];
        return state === "available" ? (k + "=" + String(val)) : (k + "=占位(禁用态)");
      }).join(" | ");

      const stageTotals = funnel.stage_totals || {};
      const funnelSummaryText = Object.keys(stageTotals).length
        ? Object.entries(stageTotals).map(([k, v]) => k + ":" + formatCount(v)).join(" | ")
        : "暂无漏斗数据";

      box.innerHTML = [
        row("运营漏斗总览", funnelSummaryText, "info"),
        row("异常优先级池", "数量 " + formatCount(exceptionPool.total_items || 0) + " | " + exceptionPreview, Number(exceptionPool.total_items || 0) > 0 ? "warning" : "success"),
        row("履约效率", "已履约 " + formatCount(efficiency.fulfilled_orders || 0) + " | 失败 " + formatCount(efficiency.failed_orders || 0) + " | 履约率 " + String(efficiency.fulfillment_rate_pct || 0) + "%", "info"),
        row("商品运营", productSummaryText, "info"),
        row("成品化 Drill-down", (drillDown.message || "输入订单号查看明细") + "（参数: " + (drillDown.query_key || "order_id") + "）", "info")
      ].join("");
    }

    async function inspectVirtualGoodsOrder() {
      const orderId = (document.getElementById("inspectOrderId").value || "").trim();
      const box = document.getElementById("virtualGoodsInspectContent");
      if (!orderId) {
        box.textContent = "请输入订单号";
        return;
      }
      box.textContent = "加载中...";
      try {
        const res = await fetch("/api/virtual-goods/inspect-order?order_id=" + encodeURIComponent(orderId));
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "inspect_order failed");
        const view = data.drill_down_view || {};
        const currentStatus = view.current_status || {};
        const callbackChain = Array.isArray(view.callback_chain) ? view.callback_chain : [];
        const claimReplayTrace = Array.isArray(view.claim_replay_trace) ? view.claim_replay_trace : [];
        const manualTakeover = view.manual_takeover || {};
        const recentErrors = Array.isArray(view.recent_errors) ? view.recent_errors : [];
        const exceptionPool = view.exception_priority_pool || {};
        const exceptionItems = Array.isArray(exceptionPool.items) ? exceptionPool.items : [];
        const actions = Array.isArray(view.actions) ? view.actions : [];

        const exceptionSummary = exceptionItems.map((x) => {
          return (x.priority || "P1") + " " + (x.type || "UNKNOWN") + " x" + String(x.count || 0) + " - " + (x.summary || "");
        }).join("\\n") || "无异常项";

        const callbackSummary = callbackChain.slice(0, 8).map((x) => {
          return "#" + String(x.step || 0) + " | kind=" + (x.event_kind || "-") + " | verify=" + (x.verify_passed ? "Y" : "N") + " | processed=" + (x.processed ? "Y" : "N");
        }).join("\\n") || "无回调链";

        const replaySummary = claimReplayTrace.slice(0, 8).map((x) => {
          return "callback_id=" + String(x.callback_id || 0) + " | event_id=" + (x.external_event_id || "-") + " | dedupe=" + (x.dedupe_key || "-") + " | attempt=" + String(x.attempt_count || 0);
        }).join("\\n") || "无 claim-replay 轨迹";

        const errorSummary = recentErrors.map((x) => {
          return "callback_id=" + String(x.callback_id || 0) + " | kind=" + (x.event_kind || "-") + " | error=" + (x.error || "-") + " | at=" + (x.at || "-");
        }).join("\\n") || "无最近错误";

        const actionSummary = actions.map((x) => {
          return (x.name || "action") + "=" + (x.enabled ? "enabled" : "disabled") + "(" + (x.reason || "-") + ")";
        }).join("\\n") || "无动作";

        box.textContent = [
          "【当前状态】",
          "订单号: " + (currentStatus.xianyu_order_id || orderId),
          "订单状态: " + (currentStatus.order_status || "-"),
          "履约状态: " + (currentStatus.fulfillment_status || "-"),
          "更新时间: " + (currentStatus.updated_at || "-"),
          "",
          "【异常优先级池】",
          exceptionSummary,
          "",
          "【回调链】",
          callbackSummary,
          "",
          "【claim-replay轨迹】",
          replaySummary,
          "",
          "【manual_takeover】",
          "enabled=" + (manualTakeover.enabled ? "true" : "false") + " | reason=" + (manualTakeover.reason || "-"),
          "",
          "【最近错误】",
          errorSummary,
          "",
          "【可执行动作（禁用态）】",
          actionSummary
        ].join("\\n");
      } catch (err) {
        box.textContent = "inspect_order 失败: " + err.message;
      }
    }

    function loadStatus() {
      fetch("/api/status")
      .then(r => r.json())
      .then(async data => {
        if (data.error) throw new Error(data.error);
        updateServiceStatus(data.service_status || "running");
        renderStatusBlocks(data);
        renderCharts(data);
        try {
          const vgRes = await fetch("/api/virtual-goods/metrics");
          const vgData = await vgRes.json();
          renderVirtualGoodsMetrics(vgData);
        } catch (e) {
          renderVirtualGoodsMetrics({ success: false, error: e.message || "metrics unavailable" });
        }
      })
      .catch(err => {
        document.getElementById("systemStatusContent").innerHTML = row("错误", err.message, "error");
      });
    }

    function renderDoctorStatus(data) {
      const box = document.getElementById("doctorStatusBox");
      const el = document.getElementById("doctorStatusContent");
      box.style.display = "block";

      const ready = !!data.ready;
      const blockers = Array.isArray(data.blockers) ? data.blockers : [];
      const nextSteps = Array.isArray(data.next_steps) ? data.next_steps : [];
      const summary = data.doctor_summary || {};
      const statusText = ready ? "通过" : "未通过";
      const statusClass = ready ? "success" : "error";
      const blockerNames = blockers
        .slice(0, 4)
        .map(item => {
          const target = item && item.target ? "[" + item.target + "] " : "";
          return target + String(item.name || "unknown");
        })
        .join(" | ") || "-";
      const stepText = nextSteps.slice(0, 3).join(" | ") || "无";

      el.innerHTML = [
        row("体检状态", statusText, statusClass),
        row("关键失败", String(summary.critical_failed || 0), Number(summary.critical_failed || 0) > 0 ? "error" : "success"),
        row("警告项", String(summary.warning_failed || 0), Number(summary.warning_failed || 0) > 0 ? "warning" : "success"),
        row("阻塞项", blockerNames, blockers.length > 0 ? "warning" : "success"),
        row("建议动作", stepText, "info"),
      ].join("");
    }

    async function runFullCheck() {
      try {
        const res = await fetch("/api/module/check?skip_gateway=1");
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        renderDoctorStatus(data);
      } catch (err) {
        alert("体检失败: " + err.message);
      }
    }

    async function recoverPresales() {
      try {
        const res = await fetch("/api/service/recover", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ target: "presales" })
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || data.message || "恢复失败");
        await loadStatus();
        alert("售前恢复已触发。当前状态: " + (data.service_status || "unknown"));
      } catch (err) {
        alert("恢复失败: " + err.message);
      }
    }

    async function runAutoFix() {
      try {
        const res = await fetch("/api/service/auto-fix", { method: "POST" });
        const data = await res.json();
        await loadStatus();
        if (data.success) {
          alert("一键修复完成: " + (data.message || "成功"));
        } else {
          const msg = data.message || "修复未完成";
          const needCookie = data.needs_cookie_update ? "（请先更新 Cookie）" : "";
          alert("一键修复结果: " + msg + needCookie);
        }
      } catch (err) {
        alert("一键修复失败: " + err.message);
      }
    }

    loadStatus();
    setInterval(loadStatus, 10000);
  </script>
</body>
</html>
"""
MIMIC_COOKIE_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>闲鱼自动客服 - Cookie管理</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      min-height: 100vh;
      padding: 20px;
    }
    .container {
      max-width: 980px;
      margin: 0 auto;
      background: white;
      border-radius: 12px;
      box-shadow: 0 20px 60px rgba(0,0,0,0.3);
      padding: 34px;
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 22px;
      padding-bottom: 18px;
      border-bottom: 2px solid #e5e7eb;
      gap: 12px;
    }
    h1 { color: #333; font-size: 28px; margin-bottom: 6px; }
    .subtitle { color: #666; font-size: 14px; }
    .back-link {
      color: #667eea;
      text-decoration: none;
      font-size: 14px;
      padding: 8px 14px;
      border-radius: 6px;
      border: 2px solid #667eea;
      transition: all 0.2s ease;
      font-weight: 600;
      white-space: nowrap;
    }
    .back-link:hover {
      background: #667eea;
      color: white;
      transform: translateY(-1px);
    }
    .info-box {
      background: #f8f9fa;
      border-left: 4px solid #667eea;
      padding: 14px;
      border-radius: 4px;
      margin-bottom: 16px;
    }
    .info-box p { margin: 4px 0; font-size: 13px; color: #4b5563; }
    .guide-card {
      background: #eff6ff;
      border: 1px solid #bfdbfe;
      border-radius: 8px;
      padding: 12px 14px;
      margin-bottom: 14px;
      color: #1e3a8a;
      font-size: 13px;
      line-height: 1.7;
    }
    .guide-card strong { color: #1d4ed8; }
    .cookie-help {
      border: 1px solid #dbeafe;
      border-radius: 8px;
      background: #f8fbff;
      padding: 10px 12px;
      margin-bottom: 14px;
    }
    .cookie-help summary {
      cursor: pointer;
      font-size: 13px;
      color: #1d4ed8;
      font-weight: 700;
      outline: none;
    }
    .cookie-help-content {
      margin-top: 10px;
      color: #334155;
      font-size: 12px;
      line-height: 1.75;
    }
    .cookie-help-content p { margin: 2px 0; }
    .cookie-help-tip {
      margin-top: 8px;
      padding: 8px 10px;
      border-radius: 6px;
      background: #fff7ed;
      color: #9a3412;
      border: 1px solid #fed7aa;
      font-size: 12px;
    }
    .current-cookie {
      background: #f8f9fa;
      padding: 12px;
      border-radius: 6px;
      margin-bottom: 16px;
      font-size: 12px;
      color: #666;
      word-break: break-all;
      max-height: 100px;
      overflow-y: auto;
      display: none;
    }
    .tabs {
      display: flex;
      gap: 10px;
      margin-bottom: 18px;
      border-bottom: 2px solid #e5e7eb;
      flex-wrap: wrap;
    }
    .tab {
      padding: 10px 16px;
      cursor: pointer;
      border: none;
      background: none;
      color: #6b7280;
      border-bottom: 2px solid transparent;
      font-size: 14px;
      font-weight: 600;
    }
    .tab.active {
      color: #667eea;
      border-bottom-color: #667eea;
    }
    .tab-content { display: none; }
    .tab-content.active { display: block; }
    .section {
      margin-bottom: 24px;
      padding-bottom: 20px;
      border-bottom: 1px solid #e5e7eb;
    }
    .section:last-child { border-bottom: none; }
    .section-title {
      font-size: 20px;
      color: #333;
      margin-bottom: 14px;
      padding-bottom: 8px;
      border-bottom: 2px solid #667eea;
    }
    .form-group { margin-bottom: 14px; }
    label {
      display: block;
      margin-bottom: 7px;
      color: #333;
      font-size: 14px;
      font-weight: 600;
    }
    textarea, input[type="file"] {
      width: 100%;
      padding: 12px;
      border: 2px solid #e5e7eb;
      border-radius: 6px;
      font-size: 14px;
      transition: border-color 0.2s ease;
    }
    textarea {
      font-family: "SFMono-Regular", Menlo, Consolas, monospace;
      resize: vertical;
      min-height: 150px;
    }
    textarea:focus, input[type="file"]:focus {
      outline: none;
      border-color: #667eea;
    }
    .hint { margin-top: 6px; font-size: 12px; color: #6b7280; }
    .inline-note {
      margin-top: 8px;
      color: #6b7280;
      font-size: 12px;
      line-height: 1.6;
    }
    .button-group {
      display: flex;
      gap: 10px;
      margin-top: 14px;
      flex-wrap: wrap;
    }
    button {
      border: none;
      padding: 10px 16px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 14px;
      font-weight: 600;
      transition: all 0.2s ease;
    }
    button:disabled { opacity: 0.6; cursor: not-allowed; }
    .btn-primary {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: #fff;
    }
    .btn-secondary { background: #f3f4f6; color: #1f2937; }
    .btn-danger { background: #dc3545; color: #fff; }
    .btn-primary:hover, .btn-secondary:hover, .btn-danger:hover { transform: translateY(-1px); }
    .panel {
      margin-top: 16px;
      background: #f8f9fa;
      border-radius: 6px;
      padding: 12px;
      font-size: 13px;
      color: #374151;
      line-height: 1.6;
      display: none;
      white-space: pre-line;
    }
    .message {
      margin-top: 18px;
      padding: 12px;
      border-radius: 6px;
      font-size: 14px;
      display: none;
      white-space: pre-line;
      line-height: 1.6;
    }
    .message.success {
      background: #d4edda;
      color: #155724;
      border: 1px solid #c3e6cb;
    }
    .message.error {
      background: #f8d7da;
      color: #721c24;
      border: 1px solid #f5c6cb;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div>
        <h1>闲鱼自动客服</h1>
        <p class="subtitle">Cookie管理与系统配置</p>
      </div>
      <a href="/" class="back-link">← 返回首页</a>
    </div>

    <div class="guide-card">
      <strong>Cookie 极简流程（默认推荐）</strong><br>
      1. 上传插件导出的 <code>cookies.txt / JSON / ZIP</code>，点击“上传并一键更新”。<br>
      2. 或者直接粘贴 Cookie 字符串，点击“粘贴并更新”。<br>
      3. 更新后回首页点“刷新状态”，看连接是否正常。<br>
      需要详细说明时，再展开下方“高级选项”。
    </div>

    <div id="currentCookie" class="current-cookie"><strong>当前Cookie：</strong> <span id="currentCookieText"></span></div>

    <div class="tabs">
      <button class="tab active" onclick="switchTab('cookie', this)">Cookie</button>
      <button class="tab" onclick="switchTab('routes', this)">路线数据</button>
      <button class="tab" onclick="switchTab('markup', this)">加价数据</button>
      <button class="tab" onclick="switchTab('template', this)">回复模板</button>
    </div>

    <div id="cookieTab" class="tab-content active">
      <div class="section">
        <h2 class="section-title">Cookie管理（极简）</h2>
        <div class="form-group">
          <label for="cookiePluginFile">插件导出文件（支持多选）</label>
          <input type="file" id="cookiePluginFile" accept=".txt,.json,.log,.cookies,.csv,.tsv,.har,.zip" multiple>
          <div class="hint">推荐：上传插件导出的 cookies.txt/JSON（也支持 csv/tsv/har/zip，自动识别）。</div>
        </div>
        <div class="form-group">
          <label for="cookie">Cookie字符串</label>
          <textarea id="cookie" placeholder="支持直接粘贴表格文本 / Cookie请求头 / cookies.txt / JSON"></textarea>
        </div>
        <div class="button-group">
          <button class="btn-primary" title="上传插件导出文件并自动更新到系统 Cookie" onclick="importCookiePlugin()">上传并一键更新</button>
          <button class="btn-primary" title="保存当前输入的 Cookie 到系统配置" onclick="saveCookie()">粘贴并更新</button>
          <button class="btn-secondary" title="检测 Cookie 可用性分级与修复建议" onclick="diagnoseCookie()">诊断可用性</button>
          <button class="btn-secondary" title="读取当前已保存的 Cookie 到输入框" onclick="loadCurrentCookie()">查看当前</button>
        </div>
        <div class="inline-note">只用上面3个按钮就够用。导入成功后，回首页刷新状态即可。</div>
        <details class="cookie-help" style="margin-top: 12px;">
          <summary>Cookie 详细获取步骤（推荐按这个顺序）</summary>
          <div class="cookie-help-content">
            <p><strong>0基础 Cookie 复制方式：</strong></p>
            <ol style="margin-left: 20px; margin-top: 8px;">
              <li>登录闲鱼网页版</li>
              <li>按 F12 打开开发者工具</li>
              <li>切换到 Network（网络）标签</li>
              <li>刷新页面，点击任意请求</li>
              <li>在 Request Headers 中找到 Cookie</li>
              <li>建议确保包含关键字段：<code>_tb_token_</code>、<code>cookie2</code>、<code>sgcookie</code>、<code>unb</code></li>
            </ol>
            <p style="margin-top: 10px;"><strong>更新后如何确认生效：</strong>导入成功后，回到首页点击"刷新状态"按钮，确认账号状态正常。</p>
            <p style="margin-top: 10px;"><strong>插件一键导入并更新：</strong>在下方"高级选项"中下载内置插件包，加载后导出 Cookie，再通过"插件导出文件"按钮一键导入。</p>
          </div>
        </details>
        <details class="cookie-help" style="margin-top: 12px;">
          <summary>高级选项：插件安装与手动解析</summary>
          <div class="cookie-help-content">
            <p><strong>0基础 Cookie 复制方式：</strong>登录后按 F12，点 Network，任选一个请求，在 Request Headers 里复制整段 Cookie。</p>
            <p><strong>Cookie 详细获取步骤：</strong>打开 goofish 并登录账号 → 按 F12 打开开发者工具 → Network 任意请求复制 Cookie 请求头。</p>
            <p><strong>关键字段检查：</strong>请确认 Cookie 至少包含 <code>unb</code>、<code>_m_h5_tk</code>、<code>_m_h5_tk_enc</code>、<code>cookie2</code>、<code>_tb_token_</code>。</p>
            <p><strong>更新后如何确认生效：</strong>回到首页点击“刷新所有状态”，确认 Cookie 存在、长度正常、风险状态为低风险。</p>
            <p><strong>插件一键导入并更新：</strong>优先使用上方“上传并一键更新”，系统会自动解析 txt/json/zip 并写入配置。</p>
            <p><strong>插件安装：</strong>下载内置插件包 → 浏览器扩展页加载 <code>Get-cookies.txt-LOCALLY/src</code>。</p>
            <div class="button-group" style="margin-top: 8px;">
              <button class="btn-secondary" onclick="window.location.href='/api/download-cookie-plugin'">下载内置插件包</button>
            </div>
            <p><a href="https://github.com/kairi003/Get-cookies.txt-LOCALLY" target="_blank" rel="noopener">插件项目地址（GitHub）</a></p>
            <div class="form-group" style="margin-top: 10px;">
              <label for="cookieFile">手动导入 Cookie 文件</label>
              <input type="file" id="cookieFile" accept=".txt,.json,.log,.cookies,.csv,.tsv,.har">
            </div>
            <div class="button-group">
              <button class="btn-secondary" onclick="importCookieFile()">导入文件到输入框</button>
              <button class="btn-secondary" onclick="normalizeCookieText()">智能解析</button>
            </div>
          </div>
        </details>
        <div id="cookieParseResult" class="panel"></div>
      </div>
    </div>

    <div id="routesTab" class="tab-content">
      <div class="section">
        <h2 class="section-title">导入路线数据</h2>
        <div class="form-group">
          <label for="routeFile">选择文件（可多选）</label>
          <input type="file" id="routeFile" accept=".xlsx,.xls,.csv,.zip" multiple>
          <div class="hint">支持 Excel/CSV/ZIP（ZIP 内可放 xlsx/xls/csv），导入后立即可用于报价。</div>
        </div>
        <div class="button-group">
          <button id="importBtn" class="btn-primary" title="将你上传的成本表写入本地报价成本目录" onclick="importRoutes()">导入到成本库</button>
          <button class="btn-secondary" title="查看当前已加载路线数量/快递公司数量" onclick="loadRouteStats()">查看统计</button>
          <button class="btn-secondary" title="导出当前成本表备份，便于迁移或回滚" onclick="window.location.href='/api/export-routes'">导出ZIP</button>
        </div>
        <div class="button-group" style="margin-top: 10px;">
          <button class="btn-danger" title="清空路线数据（高风险操作）" onclick="resetDatabase('routes')">重置路线数据库</button>
          <button class="btn-danger" title="清空聊天状态（高风险操作）" onclick="resetDatabase('chat')">重置聊天记录</button>
        </div>
        <div class="inline-note">先导入，再点“查看统计”确认路线数不为0；重置仅在数据错误时使用。</div>
        <div id="routeStats" class="panel"></div>
        <div id="importResult" class="panel"></div>
      </div>
    </div>

    <div id="markupTab" class="tab-content">
      <div class="section">
        <h2 class="section-title">加价数据配置</h2>
        <div class="info-box" style="margin-bottom: 14px;">
          <p><strong>说明：</strong>这里配置“成本价 → 对外报价”的加价规则。</p>
          <p>普通/会员 分别配置 首重加价、续重加价（元）。</p>
        </div>
        <div class="form-group">
          <label for="markupFile">导入加价文件（支持多选）</label>
          <input type="file" id="markupFile" accept=".xlsx,.xls,.csv,.json,.yaml,.yml,.txt,.md,.zip,.png,.jpg,.jpeg,.bmp,.webp,.gif" multiple>
          <div class="hint">支持 Excel/CSV/JSON/YAML/TXT/ZIP/图片（OCR 自动识别）。</div>
        </div>
        <div class="button-group">
          <button class="btn-primary" title="自动识别导入加价文件并保存到配置" onclick="importMarkupFiles()">导入加价文件</button>
          <button class="btn-secondary" title="读取当前配置中的加价规则" onclick="loadMarkupRules()">加载加价规则</button>
          <button class="btn-primary" title="保存当前表格的加价规则到配置文件" onclick="saveMarkupRules()">保存加价规则</button>
        </div>
        <div class="inline-note">建议每次导入新路线后检查一次加价规则，确保报价口径一致。</div>
        <div class="form-group" style="margin-top: 14px;">
          <div style="overflow-x:auto;">
            <table id="markupTable" style="width:100%; border-collapse:collapse; min-width:760px;">
              <thead>
                <tr>
                  <th style="border:1px solid #e5e7eb; background:#f9fafb; padding:8px;">运力</th>
                  <th style="border:1px solid #e5e7eb; background:#f9fafb; padding:8px;">首重溢价(普通)</th>
                  <th style="border:1px solid #e5e7eb; background:#f9fafb; padding:8px;">首重溢价(会员)</th>
                  <th style="border:1px solid #e5e7eb; background:#f9fafb; padding:8px;">续重溢价(普通)</th>
                  <th style="border:1px solid #e5e7eb; background:#f9fafb; padding:8px;">续重溢价(会员)</th>
                </tr>
              </thead>
              <tbody id="markupTableBody"></tbody>
            </table>
          </div>
        </div>
        <div id="markupResult" class="panel"></div>
      </div>
    </div>

    <div id="templateTab" class="tab-content">
      <div class="section">
        <h2 class="section-title">回复模板管理</h2>
        <div class="info-box" style="margin-bottom: 14px;">
          <p><strong>重量版模板：</strong>按实际重量报价。</p>
          <p><strong>体积版模板：</strong>按体积重报价，可包含 {volume_formula}。</p>
          <p><strong>常用变量：</strong>{origin}/{destination}、{origin_province}/{dest_province}、{weight}/{billing_weight}、{courier}、{price}、{eta_days}、{volume_formula}</p>
          <p><strong>兼容变量：</strong>{first_price}、{remaining_price}、{volume_weight}、{additional_units}、{courier_name}、{total_price}</p>
        </div>
        <div class="form-group">
          <label for="weightTemplateContent">重量版模板</label>
          <textarea id="weightTemplateContent" rows="10"></textarea>
        </div>
        <div class="form-group">
          <label for="volumeTemplateContent">体积版模板</label>
          <textarea id="volumeTemplateContent" rows="10"></textarea>
        </div>
        <div class="button-group">
          <button class="btn-secondary" title="读取当前生效模板内容" onclick="loadCurrentTemplate()">加载当前</button>
          <button class="btn-secondary" title="将编辑区替换为系统默认模板" onclick="resetToDefault()">恢复默认</button>
          <button class="btn-primary" title="保存模板并立即生效" onclick="saveTemplate()">保存模板</button>
        </div>
        <div class="inline-note">建议先“加载当前”，修改后“保存模板”；模板会用于后续自动回复。</div>
      </div>
    </div>

    <div id="message" class="message"></div>
  </div>

  <script>
    function showMessage(text, type) {
      const el = document.getElementById("message");
      el.textContent = text;
      el.className = "message " + type;
      el.style.display = "block";
      setTimeout(() => { el.style.display = "none"; }, Math.max(3500, text.length * 35));
    }

    function switchTab(tabName, btnEl) {
      document.querySelectorAll(".tab-content").forEach(t => t.classList.remove("active"));
      document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
      document.getElementById(tabName + "Tab").classList.add("active");
      if (btnEl) btnEl.classList.add("active");

      if (tabName === "routes") loadRouteStats();
      if (tabName === "markup") loadMarkupRules();
      if (tabName === "template") loadCurrentTemplate();
    }

    async function loadCurrentCookie() {
      try {
        const res = await fetch("/api/get-cookie");
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "未找到Cookie");
        document.getElementById("cookie").value = data.cookie || "";
        showMessage("已加载当前Cookie", "success");
      } catch (err) {
        showMessage("加载Cookie失败: " + err.message, "error");
      }
    }

    async function importCookieFile() {
      const fileInput = document.getElementById("cookieFile");
      const file = fileInput && fileInput.files ? fileInput.files[0] : null;
      if (!file) {
        showMessage("请选择 Cookie 文件", "error");
        return;
      }
      try {
        const text = await file.text();
        document.getElementById("cookie").value = text || "";
        showMessage("已导入文件内容，请点击“智能解析”", "success");
      } catch (err) {
        showMessage("读取文件失败: " + err.message, "error");
      }
    }

    async function importCookiePlugin() {
      const fileInput = document.getElementById("cookiePluginFile");
      const files = fileInput && fileInput.files ? Array.from(fileInput.files) : [];
      if (!files.length) {
        showMessage("请选择插件导出文件", "error");
        return;
      }

      const panel = document.getElementById("cookieParseResult");
      panel.style.display = "block";
      panel.textContent = "导入中...";

      const fd = new FormData();
      files.forEach(f => fd.append("file", f));

      try {
        const res = await fetch("/api/import-cookie-plugin", { method: "POST", body: fd });
        const data = await res.json();
        if (!data.success) {
          const msg = [data.error || "导入失败", data.hint || ""].filter(Boolean).join(" | ");
          throw new Error(msg);
        }

        document.getElementById("cookie").value = data.cookie || "";

        let text = "插件导入成功\\n";
        text += "来源文件: " + (data.source_file || "-") + "\\n";
        text += "识别格式: " + (data.detected_format || "-") + "\\n";
        text += "Cookie 项数: " + (data.cookie_items || 0) + "\\n";
        text += "字符长度: " + (data.length || 0) + "\\n";
        text += "可用性分级: " + (data.cookie_grade || "未知") + "\\n";
        if ((data.missing_required || []).length > 0) {
          text += "关键字段缺失: " + data.missing_required.join(", ") + "\\n";
        } else {
          text += "关键字段检查: 通过\\n";
        }
        if ((data.cookie_actions || []).length > 0) {
          text += "建议动作: " + data.cookie_actions.join(" | ") + "\\n";
        }
        const pluginRecover = data.auto_recover || {};
        if (Object.keys(pluginRecover).length > 0) {
          text += "自动恢复: " + (pluginRecover.triggered ? "已触发" : "未触发/失败") + "\\n";
          if (pluginRecover.at) {
            text += "恢复时间: " + pluginRecover.at + "\\n";
          }
          if (pluginRecover.result && pluginRecover.result.error) {
            text += "恢复错误: " + pluginRecover.result.error + "\\n";
          }
        }
        if ((data.recognized_key_hits || []).length > 0) {
          text += "识别关键字段: " + data.recognized_key_hits.join(", ") + "\\n";
        }
        if ((data.imported_files || []).length > 0) {
          text += "已识别文件: " + data.imported_files.join(", ") + "\\n";
        }
        if ((data.skipped_files || []).length > 0) {
          text += "已跳过文件: " + data.skipped_files.join(", ") + "\\n";
        }
        if ((data.details || []).length > 0) {
          text += "详细说明: " + data.details.join(" | ");
        }

        panel.textContent = text.trim();
        showMessage("插件 Cookie 导入并更新成功", "success");
        await initCookiePreview();
      } catch (err) {
        panel.textContent = "插件导入失败: " + err.message;
        showMessage("插件导入失败: " + err.message, "error");
      }
    }

    async function normalizeCookieText() {
      const raw = document.getElementById("cookie").value;
      if (!raw || !raw.trim()) {
        showMessage("请输入或导入 Cookie 文本", "error");
        return;
      }

      const panel = document.getElementById("cookieParseResult");
      panel.style.display = "block";
      panel.textContent = "解析中...";

      try {
        const res = await fetch("/api/parse-cookie", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: raw })
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "解析失败");

        document.getElementById("cookie").value = data.cookie || "";

        let text = "解析成功\\n";
        text += "识别格式: " + (data.detected_format || "-") + "\\n";
        text += "Cookie 项数: " + (data.cookie_items || 0) + "\\n";
        text += "字符长度: " + (data.length || 0) + "\\n";
        if ((data.missing_required || []).length > 0) {
          text += "关键字段缺失: " + data.missing_required.join(", ");
        } else {
          text += "关键字段检查: 通过";
        }
        panel.textContent = text;
        showMessage("Cookie 文本已标准化", "success");
      } catch (err) {
        panel.textContent = "解析失败: " + err.message;
        showMessage("解析失败: " + err.message, "error");
      }
    }

    async function saveCookie() {
      const cookie = document.getElementById("cookie").value.trim();
      if (!cookie) {
        showMessage("请输入Cookie", "error");
        return;
      }
      try {
        const res = await fetch("/api/update-cookie", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ cookie })
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "更新失败");
        let msg = "Cookie更新成功";
        if (data.cookie_items) {
          msg += "\\n识别项数: " + data.cookie_items + "（格式: " + (data.detected_format || "-") + "）";
        }
        if (data.cookie_grade) {
          msg += "\\n可用性分级: " + data.cookie_grade;
        }
        if ((data.missing_required || []).length > 0) {
          msg += "\\n缺少关键字段: " + data.missing_required.join(", ");
        }
        if ((data.cookie_actions || []).length > 0) {
          msg += "\\n建议动作: " + data.cookie_actions.join(" | ");
        }
        const manualRecover = data.auto_recover || {};
        if (Object.keys(manualRecover).length > 0) {
          msg += "\\n自动恢复: " + (manualRecover.triggered ? "已触发" : "未触发/失败");
          if (manualRecover.result && manualRecover.result.error) {
            msg += "\\n恢复错误: " + manualRecover.result.error;
          }
        }
        showMessage(msg, "success");
        await initCookiePreview();
      } catch (err) {
        showMessage("更新Cookie失败: " + err.message, "error");
      }
    }

    async function diagnoseCookie() {
      const raw = document.getElementById("cookie").value.trim();
      if (!raw) {
        showMessage("请先粘贴 Cookie 再诊断", "error");
        return;
      }
      const panel = document.getElementById("cookieParseResult");
      panel.style.display = "block";
      panel.textContent = "诊断中...";

      try {
        const res = await fetch("/api/cookie-diagnose", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: raw })
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "诊断失败");

        let text = "Cookie 诊断结果\\n";
        text += "可用性分级: " + (data.grade || "-") + "\\n";
        text += "识别格式: " + (data.detected_format || "-") + "\\n";
        text += "Cookie 项数: " + (data.cookie_items || 0) + "\\n";
        text += "字符长度: " + (data.length || 0) + "\\n";
        text += "缺失字段: " + ((data.required_missing || []).join(", ") || "无") + "\\n";
        const domainFilter = data.domain_filter || {};
        text += "域过滤: checked=" + (domainFilter.checked || 0) + ", rejected=" + (domainFilter.rejected || 0) + "\\n";
        if ((data.actions || []).length > 0) {
          text += "建议: " + data.actions.join(" | ");
        }
        panel.textContent = text.trim();
        showMessage("Cookie 诊断完成", "success");
      } catch (err) {
        panel.textContent = "诊断失败: " + err.message;
        showMessage("诊断失败: " + err.message, "error");
      }
    }

    function renderMarkupRules(rules) {
      const tbody = document.getElementById("markupTableBody");
      tbody.innerHTML = "";
      const entries = Object.entries(rules || {});
      const ordered = entries
        .filter(([k]) => k !== "default")
        .sort((a, b) => a[0].localeCompare(b[0], "zh-CN"));
      if (rules && rules.default) ordered.unshift(["default", rules.default]);

      ordered.forEach(([courier, row]) => {
        const tr = document.createElement("tr");
        const values = {
          normal_first_add: Number((row || {}).normal_first_add || 0),
          member_first_add: Number((row || {}).member_first_add || 0),
          normal_extra_add: Number((row || {}).normal_extra_add || 0),
          member_extra_add: Number((row || {}).member_extra_add || 0),
        };
        tr.innerHTML = `
          <td style="border:1px solid #e5e7eb; padding:8px; font-weight:600;">${courier}</td>
          <td style="border:1px solid #e5e7eb; padding:8px;"><input data-courier="${courier}" data-key="normal_first_add" type="number" min="0" step="0.01" value="${values.normal_first_add.toFixed(2)}" style="width:100%; padding:8px; border:1px solid #d1d5db; border-radius:4px;"></td>
          <td style="border:1px solid #e5e7eb; padding:8px;"><input data-courier="${courier}" data-key="member_first_add" type="number" min="0" step="0.01" value="${values.member_first_add.toFixed(2)}" style="width:100%; padding:8px; border:1px solid #d1d5db; border-radius:4px;"></td>
          <td style="border:1px solid #e5e7eb; padding:8px;"><input data-courier="${courier}" data-key="normal_extra_add" type="number" min="0" step="0.01" value="${values.normal_extra_add.toFixed(2)}" style="width:100%; padding:8px; border:1px solid #d1d5db; border-radius:4px;"></td>
          <td style="border:1px solid #e5e7eb; padding:8px;"><input data-courier="${courier}" data-key="member_extra_add" type="number" min="0" step="0.01" value="${values.member_extra_add.toFixed(2)}" style="width:100%; padding:8px; border:1px solid #d1d5db; border-radius:4px;"></td>
        `;
        tbody.appendChild(tr);
      });
    }

    function collectMarkupRules() {
      const rows = {};
      document.querySelectorAll("#markupTableBody input[data-courier][data-key]").forEach(input => {
        const courier = input.getAttribute("data-courier");
        const key = input.getAttribute("data-key");
        if (!rows[courier]) {
          rows[courier] = {
            normal_first_add: 0,
            member_first_add: 0,
            normal_extra_add: 0,
            member_extra_add: 0,
          };
        }
        const n = Number(input.value);
        rows[courier][key] = Number.isFinite(n) && n >= 0 ? Number(n.toFixed(4)) : 0;
      });
      return rows;
    }

    async function importMarkupFiles() {
      const fileInput = document.getElementById("markupFile");
      const panel = document.getElementById("markupResult");
      if (!fileInput.files || fileInput.files.length === 0) {
        showMessage("请选择至少一个加价文件", "error");
        return;
      }

      const fd = new FormData();
      Array.from(fileInput.files).forEach(f => fd.append("file", f));

      panel.style.display = "block";
      panel.textContent = "导入中...";

      try {
        const res = await fetch("/api/import-markup", { method: "POST", body: fd });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "导入失败");

        renderMarkupRules(data.markup_rules || {});

        let text = "导入成功\\n";
        text += "识别快递公司: " + (data.imported_couriers || []).length + "\\n";
        text += "导入文件: " + ((data.imported_files || []).join(", ") || "-") + "\\n";
        if ((data.skipped_files || []).length > 0) {
          text += "跳过文件: " + data.skipped_files.join(", ") + "\\n";
        }
        if ((data.detected_formats || {}) && Object.keys(data.detected_formats || {}).length > 0) {
          const fmt = Object.entries(data.detected_formats || {}).map(([k, v]) => `${k}:${v}`).join(", ");
          text += "识别格式: " + fmt + "\\n";
        }
        if ((data.details || []).length > 0) {
          text += "\\n详细说明: " + data.details.join(" | ");
        }
        panel.textContent = text.trim();
        showMessage("加价数据导入成功", "success");
      } catch (err) {
        panel.textContent = "导入失败: " + err.message;
        showMessage("导入加价数据失败: " + err.message, "error");
      }
    }

    async function loadMarkupRules() {
      const panel = document.getElementById("markupResult");
      panel.style.display = "block";
      panel.textContent = "加载中...";
      try {
        const res = await fetch("/api/get-markup-rules");
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "加载失败");
        renderMarkupRules(data.markup_rules || {});
        panel.textContent = "已加载加价规则，快递公司数: " + (data.couriers || []).length;
      } catch (err) {
        panel.textContent = "加载失败: " + err.message;
      }
    }

    async function saveMarkupRules() {
      const rules = collectMarkupRules();
      const panel = document.getElementById("markupResult");
      panel.style.display = "block";
      panel.textContent = "保存中...";
      try {
        const res = await fetch("/api/save-markup-rules", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ markup_rules: rules })
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "保存失败");
        panel.textContent = "保存成功\\n规则数: " + Object.keys(data.markup_rules || {}).length + "\\n备份: " + (data.backup_path || "-");
        showMessage("加价规则保存成功", "success");
      } catch (err) {
        panel.textContent = "保存失败: " + err.message;
        showMessage("保存加价规则失败: " + err.message, "error");
      }
    }

    async function loadRouteStats() {
      const statsDiv = document.getElementById("routeStats");
      statsDiv.style.display = "block";
      statsDiv.textContent = "加载中...";
      try {
        const res = await fetch("/api/route-stats");
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "获取失败");
        const stats = data.stats || {};
        let text = "路线统计\\n";
        text += "快递公司数: " + (stats.couriers || 0) + "\\n";
        text += "路线总数: " + (stats.routes || 0) + "\\n";
        text += "成本表文件: " + (stats.tables || 0) + "\\n";
        text += "最后更新: " + (stats.last_updated || "-") + "\\n";
        if (stats.parse_error) {
          text += "解析提示: " + stats.parse_error + "\\n";
        }
        if (stats.courier_details && Object.keys(stats.courier_details).length > 0) {
          text += "\\n快递公司明细:\\n";
          Object.entries(stats.courier_details).forEach(([k, v]) => {
            text += "- " + k + ": " + v + "\\n";
          });
        }
        statsDiv.textContent = text;
      } catch (err) {
        statsDiv.textContent = "加载失败: " + err.message;
      }
    }

    async function importRoutes() {
      const fileInput = document.getElementById("routeFile");
      if (!fileInput.files || fileInput.files.length === 0) {
        showMessage("请选择至少一个文件", "error");
        return;
      }

      const fd = new FormData();
      for (const f of fileInput.files) fd.append("file", f);

      const btn = document.getElementById("importBtn");
      const oldText = btn.textContent;
      btn.disabled = true;
      btn.textContent = "导入中...";

      try {
        const res = await fetch("/api/import-routes", { method: "POST", body: fd });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "导入失败");

        const stats = data.stats || {};
        let text = "导入成功\\n";
        text += "文件: " + ((data.saved_files || []).join(", ") || "-") + "\\n";
        text += "快递公司数: " + (stats.couriers || 0) + "\\n";
        text += "路线总数: " + (stats.routes || 0) + "\\n";
        text += "成本表文件: " + (stats.tables || 0);
        if (stats.parse_error) {
          text += "\\n解析提示: " + stats.parse_error;
        }
        if ((data.skipped_files || []).length > 0) {
          text += "\\n\\n已跳过文件: " + data.skipped_files.join(", ");
        }
        if ((data.details || []).length > 0) {
          text += "\\n\\n详细说明: " + data.details.join(" | ");
        }

        const resultDiv = document.getElementById("importResult");
        resultDiv.style.display = "block";
        resultDiv.textContent = text;

        showMessage("路线数据导入成功", "success");
        fileInput.value = "";
        loadRouteStats();
      } catch (err) {
        showMessage("导入失败: " + err.message, "error");
      } finally {
        btn.disabled = false;
        btn.textContent = oldText;
      }
    }

    async function resetDatabase(type) {
      const typeName = type === "routes" ? "路线数据库" : "聊天记录";
      if (!confirm("确定重置" + typeName + "吗？此操作不可恢复。")) return;
      try {
        const res = await fetch("/api/reset-database", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ type })
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "重置失败");
        showMessage(typeName + "重置成功", "success");
        if (type === "routes") {
          loadRouteStats();
          const resultDiv = document.getElementById("importResult");
          resultDiv.style.display = "none";
        }
      } catch (err) {
        showMessage(typeName + "重置失败: " + err.message, "error");
      }
    }

    async function loadCurrentTemplate(useDefault) {
      const qs = useDefault ? "?default=true" : "";
      try {
        const res = await fetch("/api/get-template" + qs);
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "加载失败");
        document.getElementById("weightTemplateContent").value = data.weight_template || "";
        document.getElementById("volumeTemplateContent").value = data.volume_template || "";
        showMessage(useDefault ? "已加载默认模板" : "模板加载成功", "success");
      } catch (err) {
        showMessage("模板加载失败: " + err.message, "error");
      }
    }

    function resetToDefault() {
      if (!confirm("恢复默认模板会覆盖当前内容，是否继续？")) return;
      loadCurrentTemplate(true);
    }

    async function saveTemplate() {
      const weight_template = document.getElementById("weightTemplateContent").value;
      const volume_template = document.getElementById("volumeTemplateContent").value;
      try {
        const res = await fetch("/api/save-template", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ weight_template, volume_template })
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "保存失败");
        showMessage("模板保存成功", "success");
      } catch (err) {
        showMessage("模板保存失败: " + err.message, "error");
      }
    }

    async function initCookiePreview() {
      try {
        const res = await fetch("/api/get-cookie");
        const data = await res.json();
        if (!data.success || !data.cookie) return;
        document.getElementById("currentCookie").style.display = "block";
        document.getElementById("currentCookieText").textContent =
          data.cookie.slice(0, 200) + (data.cookie.length > 200 ? "..." : "");
      } catch (_) {}
    }

    initCookiePreview();
  </script>
</body>
</html>
"""
MIMIC_TEST_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Test LLM Reply</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      min-height: 100vh;
      padding: 20px;
    }
    .container {
      max-width: 1100px;
      margin: 0 auto;
      background: #fff;
      border-radius: 12px;
      box-shadow: 0 20px 60px rgba(0,0,0,0.3);
      padding: 34px;
    }
    h1 { color: #333; margin-bottom: 8px; font-size: 28px; }
    .subtitle { color: #666; margin-bottom: 18px; font-size: 14px; }
    .guide-card {
      background: #eff6ff;
      border: 1px solid #bfdbfe;
      border-radius: 8px;
      padding: 12px 14px;
      margin-bottom: 16px;
      color: #1e3a8a;
      font-size: 13px;
      line-height: 1.7;
    }
    .guide-card strong { color: #1d4ed8; }
    .nav-links {
      margin-bottom: 22px;
      padding-bottom: 14px;
      border-bottom: 1px solid #e5e7eb;
    }
    .nav-links a {
      color: #667eea;
      text-decoration: none;
      margin-right: 18px;
      font-size: 14px;
      font-weight: 600;
    }
    .nav-links a:hover { text-decoration: underline; }
    .form-group { margin-bottom: 16px; }
    label {
      display: block;
      margin-bottom: 8px;
      color: #333;
      font-weight: 600;
      font-size: 14px;
    }
    textarea, input {
      width: 100%;
      padding: 12px;
      border: 2px solid #e5e7eb;
      border-radius: 6px;
      font-size: 14px;
      font-family: inherit;
      transition: border-color 0.2s ease;
    }
    textarea {
      resize: vertical;
      min-height: 120px;
      font-family: "SFMono-Regular", Menlo, Consolas, monospace;
    }
    textarea:focus, input:focus {
      outline: none;
      border-color: #667eea;
    }
    .row {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 12px;
    }
    .btn {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: #fff;
      border: none;
      border-radius: 6px;
      padding: 12px 16px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      min-width: 160px;
    }
    .btn:disabled { opacity: 0.6; cursor: not-allowed; }
    .btn-row { display: flex; gap: 10px; flex-wrap: wrap; }
    .btn-secondary {
      background: #f3f4f6;
      color: #1f2937;
      border: none;
      border-radius: 6px;
      padding: 12px 16px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
    }
    .hint {
      margin-top: 6px;
      color: #6b7280;
      font-size: 12px;
      line-height: 1.5;
    }
    .result-box {
      margin-top: 18px;
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      overflow: hidden;
      display: none;
    }
    .result-head {
      padding: 10px 14px;
      background: #f8f9fa;
      border-bottom: 1px solid #e5e7eb;
      color: #374151;
      font-size: 13px;
      display: flex;
      justify-content: space-between;
      gap: 10px;
      flex-wrap: wrap;
    }
    .result-content {
      padding: 14px;
      white-space: pre-wrap;
      line-height: 1.7;
      color: #111827;
    }
    .result-json {
      margin-top: 10px;
      background: #111827;
      color: #d1fae5;
      border-radius: 6px;
      padding: 12px;
      max-height: 260px;
      overflow: auto;
      font-size: 12px;
      white-space: pre;
      display: none;
    }
    .error {
      margin-top: 12px;
      color: #b91c1c;
      background: #fee2e2;
      border: 1px solid #fecaca;
      border-radius: 6px;
      padding: 10px;
      display: none;
      white-space: pre-line;
    }
    @media (max-width: 860px) {
      .row { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>测试调试</h1>
    <p class="subtitle">用于验证售前回复、报价输出、上下文串联效果（不发送到真实买家）。</p>
    <div class="guide-card">
      <strong>新手测试顺序：</strong> 先点“填充示例”→ 再点“生成回复”→ 查看“意图/代理/耗时”→ 满意后再上线自动回复。
    </div>

    <div class="nav-links">
      <a href="/">首页</a>
      <a href="/cookie">配置管理</a>
      <a href="/logs">日志查看</a>
      <a href="/logs/realtime">实时日志</a>
    </div>

    <div class="form-group">
      <label for="userMsg">买家消息</label>
      <textarea id="userMsg" placeholder="例如：安徽到广州3kg圆通多少钱？"></textarea>
    </div>

    <div class="form-group">
      <label for="itemDesc">商品描述（可选）</label>
      <input id="itemDesc" placeholder="例如：代下单快递服务，自动报价" />
    </div>

    <div class="row">
      <div class="form-group">
        <label for="origin">始发地</label>
        <input id="origin" placeholder="安徽" />
      </div>
      <div class="form-group">
        <label for="destination">目的地</label>
        <input id="destination" placeholder="广州" />
      </div>
      <div class="form-group">
        <label for="weight">重量(kg)</label>
        <input id="weight" placeholder="3" />
      </div>
    </div>

    <div class="row">
      <div class="form-group">
        <label for="courier">快递（可选）</label>
        <input id="courier" placeholder="圆通" />
      </div>
      <div class="form-group">
        <label for="serviceLevel">服务等级</label>
        <input id="serviceLevel" placeholder="standard" />
      </div>
      <div class="form-group">
        <label for="itemType">商品类型</label>
        <input id="itemType" placeholder="general" />
      </div>
    </div>

    <div class="form-group">
      <label for="context">上下文(JSON，可选)</label>
      <textarea id="context" style="min-height: 100px;" placeholder='例如：[{"role":"user","content":"在吗"},{"role":"assistant","content":"在的亲"}]'></textarea>
      <p class="hint">如果不填，系统将使用当前输入单轮测试。填入合法JSON数组可模拟多轮对话。</p>
    </div>

    <div class="btn-row">
      <button id="submitBtn" class="btn" title="调用回复/报价引擎进行一次完整测试" onclick="generateReply()">生成回复</button>
      <button class="btn-secondary" title="自动填入可跑通的演示数据" onclick="fillDemo()">填充示例</button>
      <button class="btn-secondary" title="查看完整返回JSON，便于排查字段问题" onclick="toggleRaw()">显示/隐藏原始JSON</button>
      <button class="btn-secondary" title="清空本页所有输入与结果" onclick="clearAll()">清空</button>
    </div>

    <div id="errorBox" class="error"></div>

    <div id="resultBox" class="result-box">
      <div id="resultMeta" class="result-head"></div>
      <div id="resultContent" class="result-content"></div>
      <pre id="rawJson" class="result-json"></pre>
    </div>
  </div>

  <script>
    function showError(msg) {
      const box = document.getElementById("errorBox");
      box.textContent = msg || "";
      box.style.display = msg ? "block" : "none";
    }

    function parseContext() {
      const raw = document.getElementById("context").value.trim();
      if (!raw) return [];
      try {
        const parsed = JSON.parse(raw);
        return Array.isArray(parsed) ? parsed : [];
      } catch (err) {
        throw new Error("context JSON 解析失败: " + err.message);
      }
    }

    function fillDemo() {
      document.getElementById("userMsg").value = "安徽到广州3kg圆通多少钱";
      document.getElementById("itemDesc").value = "快递代下单服务";
      document.getElementById("origin").value = "安徽";
      document.getElementById("destination").value = "广州";
      document.getElementById("weight").value = "3";
      document.getElementById("courier").value = "圆通";
      document.getElementById("context").value = "";
    }

    function toggleRaw() {
      const raw = document.getElementById("rawJson");
      raw.style.display = raw.style.display === "block" ? "none" : "block";
    }

    function clearAll() {
      ["userMsg", "itemDesc", "origin", "destination", "weight", "courier", "serviceLevel", "itemType", "context"].forEach(id => {
        document.getElementById(id).value = "";
      });
      showError("");
      document.getElementById("resultBox").style.display = "none";
      document.getElementById("rawJson").style.display = "none";
      document.getElementById("rawJson").textContent = "";
    }

    async function generateReply() {
      showError("");
      const submitBtn = document.getElementById("submitBtn");
      const originalText = submitBtn.textContent;

      const userMsg = document.getElementById("userMsg").value.trim();
      if (!userMsg) {
        showError("请先输入买家消息");
        return;
      }

      let context = [];
      try {
        context = parseContext();
      } catch (err) {
        showError(err.message);
        return;
      }

      const payload = {
        user_msg: userMsg,
        item_desc: document.getElementById("itemDesc").value.trim(),
        context: context,
        message: userMsg,
        item_title: document.getElementById("itemDesc").value.trim(),
        origin: document.getElementById("origin").value.trim(),
        destination: document.getElementById("destination").value.trim(),
        weight: document.getElementById("weight").value.trim(),
        courier: document.getElementById("courier").value.trim(),
        service_level: document.getElementById("serviceLevel").value.trim(),
        item_type: document.getElementById("itemType").value.trim()
      };

      submitBtn.disabled = true;
      submitBtn.textContent = "生成中...";

      try {
        const res = await fetch("/api/test-reply", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || "生成失败");

        const resultBox = document.getElementById("resultBox");
        const resultMeta = document.getElementById("resultMeta");
        const resultContent = document.getElementById("resultContent");
        const rawJson = document.getElementById("rawJson");

        resultMeta.innerHTML =
          "<span><strong>意图：</strong>" + (data.intent || "-") + "</span>" +
          "<span><strong>代理：</strong>" + (data.agent || "-") + "</span>" +
          "<span><strong>响应时间：</strong>" + (Number(data.response_time || 0).toFixed(2)) + "ms</span>";

        resultContent.textContent = data.reply || "(空回复)";
        rawJson.textContent = JSON.stringify(data, null, 2);
        resultBox.style.display = "block";
      } catch (err) {
        showError("生成回复失败: " + err.message);
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = originalText;
      }
    }
  </script>
</body>
</html>
"""
MIMIC_LOGS_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>日志查看 - XianyuAutoAgent</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #f5f5f5;
      padding: 20px;
    }
    .container {
      max-width: 1400px;
      margin: 0 auto;
      background: #fff;
      border-radius: 8px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.1);
      padding: 30px;
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
      padding-bottom: 20px;
      border-bottom: 2px solid #e0e0e0;
      gap: 12px;
    }
    .guide-card {
      background: #eff6ff;
      border: 1px solid #bfdbfe;
      border-radius: 8px;
      padding: 12px 14px;
      margin-bottom: 14px;
      color: #1e3a8a;
      font-size: 13px;
      line-height: 1.7;
    }
    .guide-card strong { color: #1d4ed8; }
    .guide-card {
      background: #eff6ff;
      border: 1px solid #bfdbfe;
      border-radius: 8px;
      padding: 12px 14px;
      margin-bottom: 14px;
      color: #1e3a8a;
      font-size: 13px;
      line-height: 1.7;
    }
    .guide-card strong { color: #1d4ed8; }
    h1 { color: #333; font-size: 28px; }
    .nav-link {
      color: #667eea;
      text-decoration: none;
      font-size: 14px;
      padding: 10px 20px;
      border-radius: 6px;
      border: 2px solid #667eea;
      transition: all 0.2s ease;
      font-weight: 600;
      display: inline-block;
      white-space: nowrap;
    }
    .nav-link:hover {
      background: #667eea;
      color: #fff;
      transform: translateY(-1px);
    }
    .file-selector { margin-bottom: 14px; }
    .file-selector select {
      width: 100%;
      padding: 10px;
      border: 2px solid #e0e0e0;
      border-radius: 6px;
      font-size: 14px;
      background: white;
    }
    .search-bar {
      display: flex;
      gap: 10px;
      margin-bottom: 14px;
      flex-wrap: wrap;
    }
    .search-bar input {
      flex: 1;
      min-width: 260px;
      padding: 10px;
      border: 2px solid #e0e0e0;
      border-radius: 6px;
      font-size: 14px;
    }
    .search-bar button {
      padding: 10px 16px;
      border: none;
      border-radius: 6px;
      background: #667eea;
      color: #fff;
      cursor: pointer;
      font-size: 14px;
      font-weight: 600;
    }
    .search-bar button.secondary { background: #6b7280; }
    .search-bar button:hover { opacity: 0.92; }
    .log-viewer {
      background: #1e1e1e;
      color: #d4d4d4;
      padding: 16px;
      border-radius: 6px;
      font-family: "Courier New", monospace;
      font-size: 13px;
      line-height: 1.55;
      min-height: 520px;
      max-height: 68vh;
      overflow-y: auto;
      white-space: pre-wrap;
      word-break: break-word;
      border: 1px solid #111827;
    }
    .log-line { margin-bottom: 2px; }
    .log-line.highlight {
      background: #fde047;
      color: #111827;
      border-radius: 2px;
      padding: 1px 3px;
    }
    .loading {
      text-align: center;
      padding: 36px;
      color: #9ca3af;
    }
    .pagination {
      display: flex;
      justify-content: center;
      align-items: center;
      gap: 10px;
      margin-top: 16px;
      flex-wrap: wrap;
    }
    .pagination button {
      padding: 8px 14px;
      border: 1px solid #e5e7eb;
      background: white;
      border-radius: 4px;
      cursor: pointer;
      font-size: 13px;
    }
    .pagination button:disabled { opacity: 0.5; cursor: not-allowed; }
    .pagination span { color: #4b5563; font-size: 13px; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>日志查看</h1>
      <a href="/" class="nav-link">← 返回首页</a>
    </div>
    <div class="guide-card">
      <strong>使用说明：</strong> 先选日志文件，再用搜索定位关键词（如报价、错误、超时），分页查看历史记录。
    </div>

    <div class="file-selector">
      <select id="logFileSelect">
        <option value="">加载中...</option>
      </select>
    </div>

    <div class="search-bar">
      <input type="text" id="searchInput" placeholder="搜索日志内容...">
      <button title="按关键词过滤当前日志文件" onclick="searchLogs()">搜索</button>
      <button class="secondary" title="清空关键词并恢复默认列表" onclick="clearSearch()">清除</button>
      <button class="secondary" title="重新加载日志文件列表" onclick="loadLogFiles()">刷新文件</button>
    </div>

    <div id="logViewer" class="log-viewer">
      <div class="loading">请选择日志文件</div>
    </div>

    <div class="pagination">
      <button id="prevBtn" title="查看上一页日志" onclick="previousPage()" disabled>上一页</button>
      <span id="pageInfo">第 0 页，共 0 页</span>
      <button id="nextBtn" title="查看下一页日志" onclick="nextPage()" disabled>下一页</button>
    </div>
  </div>

  <script>
    let currentFile = "";
    let currentPage = 1;
    let totalPages = 1;
    let searchKeyword = "";
    const pageSize = 120;

    function formatSize(bytes) {
      const n = Number(bytes || 0);
      if (n < 1024) return n + " B";
      if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
      return (n / (1024 * 1024)).toFixed(1) + " MB";
    }

    function escapeHtml(text) {
      const div = document.createElement("div");
      div.textContent = text;
      return div.innerHTML;
    }

    function loadLogFiles() {
      fetch("/api/logs/files")
        .then(r => r.json())
        .then(data => {
          const select = document.getElementById("logFileSelect");
          select.innerHTML = '<option value="">请选择日志文件</option>';
          (data.files || []).forEach(file => {
            const option = document.createElement("option");
            option.value = file.name;
            const modified = file.modified ? (" | " + file.modified.replace("T", " ").slice(0, 19)) : "";
            option.textContent = file.name + " (" + formatSize(file.size) + ")" + modified;
            select.appendChild(option);
          });

          if (!currentFile && (data.files || []).length > 0) {
            currentFile = data.files[0].name;
            select.value = currentFile;
            loadLogs();
          }
        })
        .catch(err => {
          document.getElementById("logViewer").innerHTML = '<div class="loading">文件列表加载失败: ' + escapeHtml(err.message || String(err)) + '</div>';
        });
    }

    document.getElementById("logFileSelect").addEventListener("change", (e) => {
      currentFile = e.target.value;
      currentPage = 1;
      if (currentFile) {
        loadLogs();
      } else {
        document.getElementById("logViewer").innerHTML = '<div class="loading">请选择日志文件</div>';
      }
    });

    function loadLogs() {
      if (!currentFile) return;
      document.getElementById("logViewer").innerHTML = '<div class="loading">加载中...</div>';
      const url =
        "/api/logs/content?file=" + encodeURIComponent(currentFile) +
        "&page=" + currentPage +
        "&size=" + pageSize +
        "&search=" + encodeURIComponent(searchKeyword);

      fetch(url)
        .then(r => r.json())
        .then(data => {
          if (!data.success) throw new Error(data.error || "读取失败");
          renderLines(data.lines || []);
          currentPage = Number(data.page || 1);
          totalPages = Number(data.total_pages || 1);
          updatePagination();
        })
        .catch(err => {
          document.getElementById("logViewer").innerHTML = '<div class="loading">加载失败: ' + escapeHtml(err.message || String(err)) + '</div>';
          totalPages = 1;
          currentPage = 1;
          updatePagination();
        });
    }

    function renderLines(lines) {
      const viewer = document.getElementById("logViewer");
      if (!lines.length) {
        viewer.innerHTML = '<div class="loading">没有找到日志内容</div>';
        return;
      }

      const keyword = searchKeyword.trim().toLowerCase();
      let html = "";
      lines.forEach(line => {
        const escaped = escapeHtml(line);
        const cls = keyword && line.toLowerCase().includes(keyword) ? "log-line highlight" : "log-line";
        html += '<div class="' + cls + '">' + escaped + '</div>';
      });
      viewer.innerHTML = html;
      viewer.scrollTop = 0;
    }

    function searchLogs() {
      searchKeyword = document.getElementById("searchInput").value.trim();
      currentPage = 1;
      if (currentFile) loadLogs();
    }

    function clearSearch() {
      searchKeyword = "";
      document.getElementById("searchInput").value = "";
      currentPage = 1;
      if (currentFile) loadLogs();
    }

    function previousPage() {
      if (currentPage > 1) {
        currentPage--;
        loadLogs();
      }
    }

    function nextPage() {
      if (currentPage < totalPages) {
        currentPage++;
        loadLogs();
      }
    }

    function updatePagination() {
      document.getElementById("prevBtn").disabled = currentPage <= 1;
      document.getElementById("nextBtn").disabled = currentPage >= totalPages;
      document.getElementById("pageInfo").textContent = "第 " + currentPage + " 页，共 " + totalPages + " 页";
    }

    document.getElementById("searchInput").addEventListener("keypress", (e) => {
      if (e.key === "Enter") searchLogs();
    });

    loadLogFiles();
  </script>
</body>
</html>
"""

MIMIC_LOGS_REALTIME_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>实时日志 - XianyuAutoAgent</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #f5f5f5;
      padding: 20px;
    }
    .container {
      max-width: 1400px;
      margin: 0 auto;
      background: #fff;
      border-radius: 8px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.1);
      padding: 30px;
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
      padding-bottom: 20px;
      border-bottom: 2px solid #e0e0e0;
      gap: 12px;
    }
    h1 { color: #333; font-size: 28px; }
    .nav-link {
      color: #667eea;
      text-decoration: none;
      font-size: 14px;
      padding: 10px 20px;
      border-radius: 6px;
      border: 2px solid #667eea;
      transition: all 0.2s ease;
      font-weight: 600;
      display: inline-block;
      white-space: nowrap;
    }
    .nav-link:hover {
      background: #667eea;
      color: #fff;
      transform: translateY(-1px);
    }
    .controls {
      display: flex;
      gap: 10px;
      margin-bottom: 14px;
      flex-wrap: wrap;
      align-items: center;
    }
    .controls select {
      min-width: 280px;
      padding: 10px;
      border: 2px solid #e0e0e0;
      border-radius: 6px;
      font-size: 14px;
      background: #fff;
    }
    .controls button {
      padding: 10px 16px;
      border: none;
      border-radius: 6px;
      cursor: pointer;
      font-size: 14px;
      font-weight: 600;
    }
    .btn-start { background: #28a745; color: #fff; }
    .btn-stop { background: #dc3545; color: #fff; }
    .btn-clear { background: #6b7280; color: #fff; }
    .btn-refresh { background: #667eea; color: #fff; }
    .status {
      padding: 10px;
      border-radius: 6px;
      margin-bottom: 14px;
      font-size: 14px;
      font-weight: 600;
    }
    .status.connected {
      background: #d4edda;
      color: #155724;
      border: 1px solid #c3e6cb;
    }
    .status.disconnected {
      background: #f8d7da;
      color: #721c24;
      border: 1px solid #f5c6cb;
    }
    .log-viewer {
      background: #1e1e1e;
      color: #d4d4d4;
      padding: 16px;
      border-radius: 6px;
      font-family: "Courier New", monospace;
      font-size: 13px;
      line-height: 1.55;
      height: 620px;
      overflow-y: auto;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .log-line { margin-bottom: 2px; }
    .log-line.error { color: #f48771; }
    .log-line.warning { color: #dcdcaa; }
    .log-line.info { color: #4ec9b0; }
    .log-line.debug { color: #9cdcfe; }
    .meta { margin-top: 8px; font-size: 12px; color: #6b7280; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>实时日志</h1>
      <a href="/" class="nav-link">← 返回首页</a>
    </div>
    <div class="guide-card">
      <strong>使用说明：</strong> 先选日志源，点击“开始”进入实时监控。排查结束后点“停止”，避免无意义刷新占用资源。
    </div>

    <div class="controls">
      <select id="logFileSelect"></select>
      <button class="btn-refresh" title="重新加载可选日志源" onclick="refreshLogFiles()">刷新文件</button>
      <button class="btn-start" title="连接SSE日志流并持续刷新" onclick="startStream()">开始</button>
      <button class="btn-stop" title="断开实时流连接" onclick="stopStream()">停止</button>
      <button class="btn-clear" title="仅清空页面显示，不删除真实日志" onclick="clearLogs()">清空</button>
    </div>

    <div id="status" class="status disconnected">未连接</div>
    <div id="logViewer" class="log-viewer"></div>
    <div id="meta" class="meta">等待连接...</div>
  </div>

  <script>
    let eventSource = null;
    let running = false;

    function escapeHtml(text) {
      const div = document.createElement("div");
      div.textContent = text;
      return div.innerHTML;
    }

    function statusClass(line) {
      const l = String(line || "").toLowerCase();
      if (l.includes("error") || l.includes("失败") || l.includes("exception")) return "error";
      if (l.includes("warn") || l.includes("warning") || l.includes("超时")) return "warning";
      if (l.includes("debug") || l.includes("调试")) return "debug";
      return "info";
    }

    function setStatus(connected, text) {
      const status = document.getElementById("status");
      status.className = "status " + (connected ? "connected" : "disconnected");
      status.textContent = text;
    }

    function getSelectedFile() {
      const select = document.getElementById("logFileSelect");
      return select.value || "presales";
    }

    function refreshLogFiles() {
      fetch("/api/logs/files")
        .then(r => r.json())
        .then(data => {
          const select = document.getElementById("logFileSelect");
          const oldVal = select.value;
          select.innerHTML = "";

          const fallback = ["presales", "operations", "aftersales"];
          let files = (data.files || []).map(f => f.name);
          if (!files.length) files = fallback;

          files.forEach(name => {
            const option = document.createElement("option");
            option.value = name;
            option.textContent = name;
            select.appendChild(option);
          });

          if (oldVal && files.includes(oldVal)) {
            select.value = oldVal;
          } else if (files.includes("runtime/presales.log")) {
            select.value = "runtime/presales.log";
          } else {
            select.selectedIndex = 0;
          }
        })
        .catch(() => {
          const select = document.getElementById("logFileSelect");
          if (!select.options.length) {
            ["presales", "operations", "aftersales"].forEach(name => {
              const option = document.createElement("option");
              option.value = name;
              option.textContent = name;
              select.appendChild(option);
            });
            select.value = "presales";
          }
        });
    }

    function renderLines(lines) {
      const viewer = document.getElementById("logViewer");
      let html = "";
      (lines || []).forEach(line => {
        html += '<div class="log-line ' + statusClass(line) + '">' + escapeHtml(line) + '</div>';
      });
      viewer.innerHTML = html || '<div class="log-line info">暂无日志...</div>';
      viewer.scrollTop = viewer.scrollHeight;
    }

    function stopStream() {
      running = false;
      if (eventSource) {
        eventSource.close();
        eventSource = null;
      }
      setStatus(false, "已停止");
    }

    function startStream() {
      stopStream();
      running = true;
      const file = getSelectedFile();
      const url = "/api/logs/realtime/stream?file=" + encodeURIComponent(file) + "&tail=300";

      setStatus(false, "连接中...");
      document.getElementById("meta").textContent = "连接地址: " + url;

      eventSource = new EventSource(url);
      eventSource.onopen = () => {
        if (!running) return;
        setStatus(true, "已连接: " + file);
      };
      eventSource.onmessage = (ev) => {
        if (!running) return;
        try {
          const data = JSON.parse(ev.data || "{}");
          renderLines(data.lines || []);
          document.getElementById("meta").textContent = "最近更新: " + (data.updated_at || new Date().toLocaleString());
        } catch (_) {}
      };
      eventSource.onerror = () => {
        if (!running) return;
        setStatus(false, "连接中断，2秒后重试...");
        setTimeout(() => {
          if (running) startStream();
        }, 2000);
      };
    }

    function clearLogs() {
      document.getElementById("logViewer").innerHTML = "";
      document.getElementById("meta").textContent = "日志已清空";
    }

    refreshLogFiles();
    setTimeout(startStream, 250);
  </script>
</body>
</html>
"""
