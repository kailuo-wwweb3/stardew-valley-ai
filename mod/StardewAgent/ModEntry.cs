using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Text;
using System.Text.Json;
using System.Threading;
using StardewModdingAPI;
using StardewModdingAPI.Events;
using StardewValley;

namespace StardewAgent
{
    /// <summary>
    /// SMAPI mod entry point. Starts a background HTTP server to serve game state.
    /// </summary>
    public class ModEntry : Mod
    {
        private HttpListener _listener;
        private Thread _serverThread;
        private bool _running;

        private const int HttpPort = 7880;

        // Queued responses that need to be built on the game thread
        private readonly object _lock = new();
        private string _cachedState;
        private string _cachedMap;
        private bool _stateRequested;
        private bool _mapRequested;
        private ManualResetEventSlim _stateReady = new(false);
        private ManualResetEventSlim _mapReady = new(false);

        public override void Entry(IModHelper helper)
        {
            helper.Events.GameLoop.UpdateTicked += OnUpdateTicked;
            helper.Events.GameLoop.ReturnedToTitle += OnReturnedToTitle;

            StartHttpServer();
            Monitor.Log($"StardewAgent HTTP server started on port {HttpPort}", LogLevel.Info);
        }

        private void StartHttpServer()
        {
            _running = true;
            _listener = new HttpListener();
            _listener.Prefixes.Add($"http://127.0.0.1:{HttpPort}/");
            _listener.Start();

            _serverThread = new Thread(ListenLoop)
            {
                IsBackground = true,
                Name = "StardewAgent-HTTP"
            };
            _serverThread.Start();
        }

        private void ListenLoop()
        {
            while (_running)
            {
                try
                {
                    var context = _listener.GetContext();
                    HandleRequest(context);
                }
                catch (HttpListenerException) when (!_running)
                {
                    // Server shutting down
                    break;
                }
                catch (Exception ex)
                {
                    Monitor.Log($"HTTP error: {ex.Message}", LogLevel.Error);
                }
            }
        }

        private void HandleRequest(HttpListenerContext context)
        {
            var request = context.Request;
            var response = context.Response;

            try
            {
                string path = request.Url.AbsolutePath.TrimEnd('/');
                string method = request.HttpMethod;

                if (method == "GET" && path == "/state")
                {
                    // Signal the game thread to capture state
                    lock (_lock)
                    {
                        _stateRequested = true;
                        _stateReady.Reset();
                    }

                    // Wait up to 2 seconds for the game thread to populate state
                    if (_stateReady.Wait(2000))
                    {
                        string json;
                        lock (_lock)
                        {
                            json = _cachedState;
                        }
                        SendJson(response, 200, json);
                    }
                    else
                    {
                        SendJson(response, 503, "{\"error\":\"Game thread did not respond in time\"}");
                    }
                }
                else if (method == "GET" && path == "/map")
                {
                    lock (_lock)
                    {
                        _mapRequested = true;
                        _mapReady.Reset();
                    }

                    // Map generation can be slow on large maps — allow 5 seconds
                    if (_mapReady.Wait(5000))
                    {
                        string json;
                        lock (_lock)
                        {
                            json = _cachedMap;
                        }
                        SendJson(response, 200, json);
                    }
                    else
                    {
                        SendJson(response, 503, "{\"error\":\"Map generation timed out\"}");
                    }
                }
                else
                {
                    SendJson(response, 404, "{\"error\":\"Not found\"}");
                }
            }
            catch (Exception ex)
            {
                Monitor.Log($"Request handler error: {ex.Message}", LogLevel.Error);
                SendJson(response, 500, $"{{\"error\":\"{EscapeJson(ex.Message)}\"}}");
            }
        }

        /// <summary>
        /// Called every game tick (~60 times/sec). Fulfills any pending HTTP requests on the game thread
        /// so that SMAPI/game APIs are accessed safely.
        /// </summary>
        private void OnUpdateTicked(object sender, UpdateTickedEventArgs e)
        {
            if (!Context.IsWorldReady) return;

            lock (_lock)
            {
                if (_stateRequested)
                {
                    try
                    {
                        var state = GameStateService.GetState();
                        _cachedState = JsonSerializer.Serialize(state);
                    }
                    catch (Exception ex)
                    {
                        _cachedState = $"{{\"error\":\"{EscapeJson(ex.Message)}\"}}";
                        Monitor.Log($"State capture error: {ex.Message}", LogLevel.Error);
                    }
                    _stateRequested = false;
                    _stateReady.Set();
                }

                if (_mapRequested)
                {
                    try
                    {
                        var mapData = GameStateService.GetMapData();
                        _cachedMap = JsonSerializer.Serialize(mapData);
                    }
                    catch (Exception ex)
                    {
                        _cachedMap = $"{{\"error\":\"{EscapeJson(ex.Message)}\"}}";
                        Monitor.Log($"Map capture error: {ex.Message}", LogLevel.Error);
                    }
                    _mapRequested = false;
                    _mapReady.Set();
                }
            }
        }

        private void OnReturnedToTitle(object sender, ReturnedToTitleEventArgs e)
        {
            // Clear cached data when returning to title screen
            lock (_lock)
            {
                _cachedState = null;
                _cachedMap = null;
            }
        }

        private static void SendJson(HttpListenerResponse response, int statusCode, string json)
        {
            response.StatusCode = statusCode;
            response.ContentType = "application/json";
            response.Headers.Add("Access-Control-Allow-Origin", "*");
            byte[] buffer = Encoding.UTF8.GetBytes(json);
            response.ContentLength64 = buffer.Length;
            response.OutputStream.Write(buffer, 0, buffer.Length);
            response.OutputStream.Close();
        }

        private static string EscapeJson(string s)
        {
            return s.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\n", "\\n").Replace("\r", "");
        }
    }
}
