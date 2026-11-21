using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;

// Native Stream Deck plugins register over the loopback WebSocket supplied by the host.
internal static class DeckHost
{
    private const string Prefix = "com.ju5tv.ag03mk2.";
    private static readonly JavaScriptSerializer Json = new JavaScriptSerializer();

    private static int Main(string[] args)
    {
        try { Run(args).GetAwaiter().GetResult(); return 0; }
        catch (WebSocketException) { return 1; }
        catch (IOException) { return 1; }
        catch (ArgumentException) { return 2; }
    }

    private static async Task Run(string[] args)
    {
        var options = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        for (int i = 0; i + 1 < args.Length; i += 2)
            options[args[i]] = args[i + 1];

        int port;
        string rawPort, uuid, registration;
        if (!options.TryGetValue("-port", out rawPort) ||
            !int.TryParse(rawPort, out port) || port < 1 || port > 65535 ||
            !options.TryGetValue("-pluginUUID", out uuid) || string.IsNullOrEmpty(uuid) ||
            !options.TryGetValue("-registerEvent", out registration) || registration != "registerPlugin")
            throw new ArgumentException("Stream Deck registration arguments required.");

        using (var socket = new ClientWebSocket())
        {
            var uri = new Uri("ws://127.0.0.1:" + port.ToString(CultureInfo.InvariantCulture));
            await socket.ConnectAsync(uri, CancellationToken.None);
            await Send(socket, new { @event = registration, uuid = uuid });
            while (socket.State == WebSocketState.Open)
            {
                string text = await Read(socket);
                if (text == null) return;
                var message = Json.Deserialize<Dictionary<string, object>>(text);
                object eventName, action, context;
                if (message == null || !message.TryGetValue("event", out eventName) ||
                    !object.Equals(eventName, "keyDown") || !message.TryGetValue("action", out action) ||
                    !message.TryGetValue("context", out context) || !(context is string)) continue;

                string control;
                if (object.Equals(action, Prefix + "mute")) control = "mute";
                else if (object.Equals(action, Prefix + "reverb")) control = "reverb";
                else continue;

                bool ok = Toggle(control);
                await Send(socket, new { @event = ok ? "showOk" : "showAlert", context = context });
            }
        }
    }

    private static bool Toggle(string control)
    {
        string folder = AppDomain.CurrentDomain.BaseDirectory;
        var info = new ProcessStartInfo(Path.Combine(folder, "AG03Toggle.exe"), control + " toggle --quiet");
        info.WorkingDirectory = folder;
        info.UseShellExecute = false;
        info.CreateNoWindow = true;
        try
        {
            using (var child = Process.Start(info))
            {
                if (child == null) return false;
                // The helper bounds MIDI operations and checks the hardware acknowledgement.
                return child.WaitForExit(30000) && child.ExitCode == 0;
            }
        }
        catch (System.ComponentModel.Win32Exception) { return false; }
    }

    private static Task Send(ClientWebSocket socket, object value)
    {
        byte[] data = Encoding.UTF8.GetBytes(Json.Serialize(value));
        return socket.SendAsync(new ArraySegment<byte>(data), WebSocketMessageType.Text, true, CancellationToken.None);
    }

    private static async Task<string> Read(ClientWebSocket socket)
    {
        var buffer = new byte[4096];
        using (var stream = new MemoryStream())
        {
            WebSocketReceiveResult part;
            do
            {
                part = await socket.ReceiveAsync(new ArraySegment<byte>(buffer), CancellationToken.None);
                if (part.MessageType == WebSocketMessageType.Close)
                {
                    await socket.CloseOutputAsync(WebSocketCloseStatus.NormalClosure, "", CancellationToken.None);
                    return null;
                }
                if (part.MessageType != WebSocketMessageType.Text || stream.Length + part.Count > 1024 * 1024)
                    throw new IOException("Invalid Stream Deck message.");
                stream.Write(buffer, 0, part.Count);
            } while (!part.EndOfMessage);
            return Encoding.UTF8.GetString(stream.ToArray());
        }
    }
}
