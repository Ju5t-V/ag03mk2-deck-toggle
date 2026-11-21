"use strict";

const { execFile } = require("node:child_process");
const path = require("node:path");
const { promisify } = require("node:util");
const WebSocket = require("ws");
const manifest = require("../manifest.json");

const { UUID: pluginId } = manifest;
const executable = path.join(__dirname, "..", "bin", "AG03Toggle.exe");
const runExecutable = promisify(execFile);
const controls = new Map([
  [`${pluginId}.mute`, { name: "Mute", command: "mute" }],
  [`${pluginId}.reverb`, { name: "Reverb", command: "reverb" }],
]);

async function toggle({ command, name }) {
  try {
    const { stdout } = await runExecutable(executable, [command, "toggle", "--quiet"], {
      timeout: 20000,
      windowsHide: true,
    });
    const confirmed = stdout.split(/\r?\n/).find((line) =>
      line === `CH1 ${name} ON confirmed.` || line === `CH1 ${name} OFF confirmed.`);
    return confirmed?.split(" ")[2] ?? "OK";
  } catch (error) {
    const message = error.stderr?.trim().split(/\r?\n/).at(-1);
    throw new Error(message || `Could not confirm the AG03MK2 ${name} toggle.`);
  }
}

function connect(host) {
  let queue = Promise.resolve();

  function open() {
    const socket = new WebSocket(host, { handshakeTimeout: 5000 });
    const feedback = new Map();
    const send = (message) => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ uuid: pluginId, ...message }));
      }
    };
    const setIcon = (target, text = "") => send({
      cmd: "state",
      param: { statelist: [{ ...target, type: 0, state: 0, showtext: Boolean(text), textData: text }] },
    });
    const resetIcon = (target) => {
      clearTimeout(feedback.get(target.actionid));
      feedback.delete(target.actionid);
      setIcon(target);
    };

    socket.on("open", () => send({ cmd: "connected", code: 0 }));
    socket.on("error", (err) => console.warn(`Ulanzi Studio connection: ${err.message}`));
    socket.on("close", () => {
      for (const timer of feedback.values()) clearTimeout(timer);
      setTimeout(open, 2000);
    });

    socket.on("message", (data) => {
      let message;
      try {
        message = JSON.parse(data);
      } catch {
        return;
      }
      if (!message || typeof message.cmd !== "string" ||
          (message.code !== undefined && message.cmdType !== "REQUEST")) return;

      // The main service acknowledges requests before starting a mixer operation.
      send({ ...message, code: 0 });
      if (message.cmd === "clear" && Array.isArray(message.param)) {
        for (const item of message.param) {
          clearTimeout(feedback.get(item?.actionid));
          feedback.delete(item?.actionid);
        }
        return;
      }
      const { uuid, key, actionid, cmd } = message;
      const control = controls.get(uuid);
      if (!control || key == null || actionid == null) return;
      const target = { uuid, key, actionid };
      if (cmd === "add" || (cmd === "setactive" && message.active !== false)) resetIcon(target);
      if (cmd !== "run") return;

      // Studio may send keydown and keyup as well. Only run invokes the mixer.
      queue = queue.then(async () => {
        if (socket.readyState !== WebSocket.OPEN) return;
        resetIcon(target);
        try {
          const text = await toggle(control);
          if (socket.readyState !== WebSocket.OPEN) return;
          setIcon(target, text);
          feedback.set(actionid, setTimeout(() => resetIcon(target), 2500));
        } catch (error) {
          send({ cmd: "showAlert", ...target });
          send({ cmd: "toast", msg: `AG03MK2 ${control.name}: ${error.message}` });
        }
      });
    });
  }

  open();
}

const [, , address = "127.0.0.1", port = "3906"] = process.argv;
connect(`ws://${address}:${port}`);
