using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Text;
using System.Text.Json;
using System.Threading;
using Microsoft.Xna.Framework;
using StardewModdingAPI;
using StardewModdingAPI.Events;
using StardewValley;

namespace StardewAgent
{
    /// <summary>
    /// SMAPI mod entry point. Starts a background HTTP server to serve game state
    /// and accept action commands.
    /// </summary>
    public class ModEntry : Mod
    {
        private HttpListener _listener;
        private Thread _serverThread;
        private bool _running;

        private const int HttpPort = 7880;
        private const float MoveThreshold = 4f; // pixels — close enough to snap to target
        private const int HeartbeatTimeoutTicks = 300; // ~5 seconds at 60 tps

        // Queued responses that need to be built on the game thread
        private readonly object _lock = new();
        private string _cachedState;
        private string _cachedMap;
        private bool _stateRequested;
        private bool _mapRequested;
        private ManualResetEventSlim _stateReady = new(false);
        private ManualResetEventSlim _mapReady = new(false);

        // Action queue — written by HTTP thread, consumed by game thread
        private ActionRequest _pendingAction;
        private string _actionResult;
        private ManualResetEventSlim _actionReady = new(false);

        // Active path state — executed on game thread tick by tick
        private List<Vector2> _activePath;
        private int _activePathIndex;
        private bool _pathActive;
        private int _lastHeartbeatTick;
        private int _currentTick;

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

                // GET /state
                if (method == "GET" && path == "/state")
                {
                    lock (_lock)
                    {
                        _stateRequested = true;
                        _stateReady.Reset();
                    }

                    if (_stateReady.Wait(2000))
                    {
                        string json;
                        lock (_lock) { json = _cachedState; }
                        SendJson(response, 200, json);
                    }
                    else
                    {
                        SendJson(response, 503, "{\"error\":\"Game thread did not respond in time\"}");
                    }
                }
                // GET /map
                else if (method == "GET" && path == "/map")
                {
                    lock (_lock)
                    {
                        _mapRequested = true;
                        _mapReady.Reset();
                    }

                    if (_mapReady.Wait(5000))
                    {
                        string json;
                        lock (_lock) { json = _cachedMap; }
                        SendJson(response, 200, json);
                    }
                    else
                    {
                        SendJson(response, 503, "{\"error\":\"Map generation timed out\"}");
                    }
                }
                // POST /action
                else if (method == "POST" && path == "/action")
                {
                    string body;
                    using (var reader = new StreamReader(request.InputStream, request.ContentEncoding))
                    {
                        body = reader.ReadToEnd();
                    }

                    ActionRequest actionReq;
                    try
                    {
                        actionReq = JsonSerializer.Deserialize<ActionRequest>(body,
                            new JsonSerializerOptions { PropertyNameCaseInsensitive = true });
                    }
                    catch (Exception ex)
                    {
                        SendJson(response, 400, $"{{\"error\":\"Invalid JSON: {EscapeJson(ex.Message)}\"}}");
                        return;
                    }

                    if (actionReq == null || string.IsNullOrEmpty(actionReq.Type))
                    {
                        SendJson(response, 400, "{\"error\":\"Missing 'type' field\"}");
                        return;
                    }

                    // Queue the action for game thread execution
                    lock (_lock)
                    {
                        _pendingAction = actionReq;
                        _actionReady.Reset();
                    }

                    // For walk_path, return 202 immediately (async)
                    if (actionReq.Type == "walk_path")
                    {
                        // Wait briefly for validation on game thread
                        if (_actionReady.Wait(2000))
                        {
                            string result;
                            lock (_lock) { result = _actionResult; }
                            if (result == "ok")
                                SendJson(response, 202, "{\"status\":\"accepted\",\"message\":\"Path walking started\"}");
                            else
                                SendJson(response, 400, $"{{\"error\":\"{EscapeJson(result)}\"}}");
                        }
                        else
                        {
                            SendJson(response, 503, "{\"error\":\"Game thread did not respond in time\"}");
                        }
                    }
                    else
                    {
                        // For use_tool, wait for completion
                        if (_actionReady.Wait(2000))
                        {
                            string result;
                            lock (_lock) { result = _actionResult; }
                            if (result == "ok")
                                SendJson(response, 200, "{\"status\":\"ok\"}");
                            else
                                SendJson(response, 400, $"{{\"error\":\"{EscapeJson(result)}\"}}");
                        }
                        else
                        {
                            SendJson(response, 503, "{\"error\":\"Game thread did not respond in time\"}");
                        }
                    }
                }
                // POST /heartbeat
                else if (method == "POST" && path == "/heartbeat")
                {
                    lock (_lock)
                    {
                        _lastHeartbeatTick = _currentTick;
                    }
                    SendJson(response, 200, "{\"status\":\"ok\"}");
                }
                // GET /pathstatus
                else if (method == "GET" && path == "/pathstatus")
                {
                    bool active;
                    int index, total;
                    lock (_lock)
                    {
                        active = _pathActive;
                        index = _activePathIndex;
                        total = _activePath?.Count ?? 0;
                    }
                    var status = new Dictionary<string, object>
                    {
                        ["active"] = active,
                        ["currentIndex"] = index,
                        ["totalPoints"] = total
                    };
                    SendJson(response, 200, JsonSerializer.Serialize(status));
                }
                // POST /stop
                else if (method == "POST" && path == "/stop")
                {
                    lock (_lock)
                    {
                        _pathActive = false;
                        _activePath = null;
                    }
                    SendJson(response, 200, "{\"status\":\"stopped\"}");
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
        /// Called every game tick (~60 times/sec). Handles state requests,
        /// action execution, and path walking.
        /// </summary>
        private void OnUpdateTicked(object sender, UpdateTickedEventArgs e)
        {
            if (!Context.IsWorldReady) return;

            _currentTick = (int)e.Ticks;

            lock (_lock)
            {
                // Fulfill state request
                if (_stateRequested)
                {
                    try
                    {
                        var state = GameStateService.GetState();
                        // Add path status to state
                        state["pathActive"] = _pathActive;
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

                // Fulfill map request
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

                // Process pending action
                if (_pendingAction != null)
                {
                    var action = _pendingAction;
                    _pendingAction = null;

                    try
                    {
                        _actionResult = ExecuteAction(action);
                    }
                    catch (Exception ex)
                    {
                        _actionResult = $"error: {ex.Message}";
                        Monitor.Log($"Action error: {ex.Message}", LogLevel.Error);
                    }
                    _actionReady.Set();
                }
            }

            // Execute active path (outside lock to avoid blocking HTTP thread)
            if (_pathActive)
            {
                ExecutePathTick();
            }
        }

        /// <summary>
        /// Dispatches an action request to the appropriate handler.
        /// </summary>
        private string ExecuteAction(ActionRequest action)
        {
            switch (action.Type)
            {
                case "use_tool":
                    return ActionService.UseTool(action.TargetX, action.TargetY, action.Tool);

                case "walk_path":
                    if (action.Path == null || action.Path.Count == 0)
                        return "error: missing 'path' array";

                    var pixelPath = ActionService.BuildPixelPath(action.Path, out string error);
                    if (pixelPath == null)
                        return error;

                    _activePath = pixelPath;
                    _activePathIndex = 0;
                    _pathActive = true;
                    _lastHeartbeatTick = _currentTick;
                    Monitor.Log($"Path started: {pixelPath.Count} points", LogLevel.Debug);
                    return "ok";

                default:
                    return $"error: unknown action type '{action.Type}'";
            }
        }

        /// <summary>
        /// Moves the player toward the next point in the active path each tick.
        /// Stops on heartbeat timeout.
        /// </summary>
        private void ExecutePathTick()
        {
            // Heartbeat check — stop if no heartbeat for 5 seconds
            if (_currentTick - _lastHeartbeatTick > HeartbeatTimeoutTicks)
            {
                Monitor.Log("Heartbeat timeout — stopping path execution", LogLevel.Warn);
                _pathActive = false;
                _activePath = null;
                return;
            }

            if (_activePath == null || _activePathIndex >= _activePath.Count)
            {
                _pathActive = false;
                _activePath = null;
                Monitor.Log("Path completed", LogLevel.Debug);
                return;
            }

            var player = Game1.player;
            var target = _activePath[_activePathIndex];
            var current = player.Position;
            var diff = target - current;
            float distance = diff.Length();

            if (distance <= MoveThreshold)
            {
                // Snap to target and move to next point
                player.Position = target;
                _activePathIndex++;
                return;
            }

            // Calculate movement speed (pixels per tick)
            float speed = (player.Speed + player.addedSpeed) * 64f / 60f;
            // Stardew default speed=2 → ~2.13 pixels/tick. Scale up for smooth movement.
            speed = Math.Max(speed, 2f);

            if (distance <= speed)
            {
                player.Position = target;
                _activePathIndex++;
            }
            else
            {
                // Move toward target
                var direction = diff / distance;
                player.Position = current + direction * speed;

                // Update facing direction
                if (Math.Abs(diff.X) >= Math.Abs(diff.Y))
                    player.FacingDirection = diff.X > 0 ? 1 : 3;
                else
                    player.FacingDirection = diff.Y > 0 ? 2 : 0;
            }
        }

        private void OnReturnedToTitle(object sender, ReturnedToTitleEventArgs e)
        {
            lock (_lock)
            {
                _cachedState = null;
                _cachedMap = null;
                _pathActive = false;
                _activePath = null;
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

    /// <summary>
    /// Represents an action request from the Python agent.
    /// </summary>
    public class ActionRequest
    {
        /// <summary>Action type: "use_tool" or "walk_path"</summary>
        public string Type { get; set; }

        /// <summary>Target tile X for use_tool</summary>
        public int TargetX { get; set; }

        /// <summary>Target tile Y for use_tool</summary>
        public int TargetY { get; set; }

        /// <summary>Optional tool name to switch to before using</summary>
        public string Tool { get; set; }

        /// <summary>Path array for walk_path: [[x,y], [x,y], ...]</summary>
        public List<int[]> Path { get; set; }
    }
}
