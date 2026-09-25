// M7-02 (BRIEF §8: "the web app makes no LLM calls at all (network assertion)"): preloaded into the Next server
// (playwright.config.ts NODE_OPTIONS), this logs every outbound TCP connection (host, port) to NET_LOG_FILE, one JSON
// line each. Every HTTP client in Node (fetch/undici, http, https, tls) connects through net.Socket#connect.
const fs = require("node:fs");
const net = require("node:net");

const file = process.env.NET_LOG_FILE;
if (file) {
  fs.writeFileSync(file, "");
  const connect = net.Socket.prototype.connect;
  net.Socket.prototype.connect = function (...args) {
    try {
      let opts = args[0];
      if (Array.isArray(opts)) opts = opts[0];
      const entry =
        opts && typeof opts === "object"
          ? { host: opts.path ? `unix:${opts.path}` : (opts.host ?? "localhost"), port: opts.port ?? null }
          : { host: typeof args[1] === "string" ? args[1] : "localhost", port: opts ?? null };
      fs.appendFileSync(file, `${JSON.stringify({ ...entry, pid: process.pid })}\n`);
    } catch {
      // logging never breaks a connection
    }
    return connect.apply(this, args);
  };
}
