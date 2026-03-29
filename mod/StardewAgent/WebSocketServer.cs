using System;
using System.Collections.Concurrent;
using System.Net;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using StardewModdingAPI;

namespace StardewAgent
{
    /// <summary>
    /// Simple WebSocket server that broadcasts one-way game events to connected clients.
    /// </summary>
    public class WebSocketServer
    {
        private readonly HttpListener _listener;
        private readonly ConcurrentDictionary<string, WebSocket> _clients = new();
        private readonly IMonitor _monitor;
        private readonly CancellationTokenSource _cts = new();
        private bool _running;

        private const int WssPort = 7881;

        public WebSocketServer(IMonitor monitor)
        {
            _monitor = monitor;
            _listener = new HttpListener();
            _listener.Prefixes.Add($"http://127.0.0.1:{WssPort}/");
        }

        public void Start()
        {
            _running = true;
            _listener.Start();

            var thread = new Thread(AcceptLoop)
            {
                IsBackground = true,
                Name = "StardewAgent-WSS"
            };
            thread.Start();

            _monitor.Log($"WebSocket server started on port {WssPort}", LogLevel.Info);
        }

        private async void AcceptLoop()
        {
            while (_running)
            {
                try
                {
                    var context = await _listener.GetContextAsync();
                    if (context.Request.IsWebSocketRequest)
                    {
                        _ = HandleClient(context);
                    }
                    else
                    {
                        context.Response.StatusCode = 400;
                        context.Response.Close();
                    }
                }
                catch (HttpListenerException) when (!_running)
                {
                    break;
                }
                catch (Exception ex)
                {
                    _monitor.Log($"WSS accept error: {ex.Message}", LogLevel.Error);
                }
            }
        }

        private async Task HandleClient(HttpListenerContext context)
        {
            WebSocket ws = null;
            string clientId = Guid.NewGuid().ToString("N")[..8];

            try
            {
                var wsContext = await context.AcceptWebSocketAsync(null);
                ws = wsContext.WebSocket;
                _clients[clientId] = ws;
                _monitor.Log($"WSS client connected: {clientId}", LogLevel.Debug);

                // Keep connection alive — just read and discard any incoming messages
                var buffer = new byte[256];
                while (ws.State == WebSocketState.Open)
                {
                    var result = await ws.ReceiveAsync(new ArraySegment<byte>(buffer), _cts.Token);
                    if (result.MessageType == WebSocketMessageType.Close)
                        break;
                }
            }
            catch (WebSocketException) { }
            catch (OperationCanceledException) { }
            finally
            {
                _clients.TryRemove(clientId, out _);
                if (ws != null && ws.State != WebSocketState.Aborted)
                {
                    try { ws.Dispose(); } catch { }
                }
                _monitor.Log($"WSS client disconnected: {clientId}", LogLevel.Debug);
            }
        }

        /// <summary>
        /// Broadcast a JSON event to all connected WebSocket clients.
        /// Fire-and-forget — errors are logged but don't propagate.
        /// </summary>
        public void Broadcast(object eventData)
        {
            if (_clients.IsEmpty) return;

            string json = JsonSerializer.Serialize(eventData);
            byte[] bytes = Encoding.UTF8.GetBytes(json);
            var segment = new ArraySegment<byte>(bytes);

            foreach (var kvp in _clients)
            {
                var ws = kvp.Value;
                if (ws.State == WebSocketState.Open)
                {
                    try
                    {
                        // Fire-and-forget send
                        _ = ws.SendAsync(segment, WebSocketMessageType.Text, true, CancellationToken.None);
                    }
                    catch
                    {
                        _clients.TryRemove(kvp.Key, out _);
                    }
                }
                else
                {
                    _clients.TryRemove(kvp.Key, out _);
                }
            }
        }

        public void Stop()
        {
            _running = false;
            _cts.Cancel();
            try { _listener.Stop(); } catch { }
        }
    }
}
