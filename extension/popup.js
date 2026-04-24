var API_BASE = 'http://127.0.0.1:8900';

var statusText = document.getElementById('statusText');
var proxyDisplay = document.getElementById('proxyDisplay');
var proxyCount = document.getElementById('proxyCount');
var btnConnect = document.getElementById('btnConnect');
var btnRotate = document.getElementById('btnRotate');
var btnDisconnect = document.getElementById('btnDisconnect');
var errorBar = document.getElementById('errorBar');
var setupHint = document.getElementById('setupHint');

document.addEventListener('DOMContentLoaded', function() {
  loadStatus();

  btnConnect.addEventListener('click', function() {
    apiCall('POST', '/connect');
  });

  btnRotate.addEventListener('click', function() {
    apiCall('POST', '/rotate');
  });

  btnDisconnect.addEventListener('click', function() {
    apiCall('POST', '/disconnect');
  });
});

function showError(msg) {
  errorBar.textContent = msg;
  errorBar.style.display = msg ? 'block' : 'none';
}

function loadStatus() {
  fetch(API_BASE + '/status', { method: 'GET' })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      showError('');
      setupHint.style.display = 'none';
      applyUI(data);
    })
    .catch(function(e) {
      statusText.textContent = 'RELAY OFFLINE';
      statusText.className = 'status-text error';
      proxyDisplay.textContent = 'Start ProxyRelay.exe first';
      proxyDisplay.className = 'proxy-display';
      btnConnect.disabled = true;
      btnRotate.disabled = true;
      btnDisconnect.disabled = true;
      setupHint.style.display = 'block';
      showError('Cannot reach relay at ' + API_BASE);
    });
}

function apiCall(method, path) {
  btnConnect.disabled = true;
  btnRotate.disabled = true;
  btnDisconnect.disabled = true;
  statusText.textContent = 'SWITCHING...';
  showError('');

  fetch(API_BASE + path, { method: method })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.success) {
        applyUI(data.status);
      } else {
        showError(data.error || 'Operation failed');
        loadStatus();
      }
    })
    .catch(function(e) {
      showError('Relay error: ' + e.message);
      loadStatus();
    });
}

function applyUI(status) {
  if (status.connected) {
    statusText.textContent = 'CONNECTED';
    statusText.className = 'status-text connected';
    proxyDisplay.textContent = status.proxy || 'Unknown';
    proxyDisplay.className = 'proxy-display active';
    btnConnect.disabled = true;
    btnRotate.disabled = false;
    btnDisconnect.disabled = false;
  } else {
    statusText.textContent = 'NOT CONNECTED';
    statusText.className = 'status-text disconnected';
    proxyDisplay.textContent = 'No upstream proxy';
    proxyDisplay.className = 'proxy-display';
    btnConnect.disabled = false;
    btnRotate.disabled = true;
    btnDisconnect.disabled = true;
  }

  if (status.proxy_count !== undefined) {
    proxyCount.textContent = status.proxy_count + ' proxies loaded | Port ' + (status.proxy_port || 8899);
  }
}
