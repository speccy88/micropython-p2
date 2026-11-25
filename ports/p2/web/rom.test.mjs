// SPDX-License-Identifier: MIT
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { digest, install, ramPayload } from "./rom.mjs";

const firmware = new URL("../firmware/", import.meta.url);
const profiles = JSON.parse(readFileSync(new URL("manifest.json", firmware))).profiles;
const banner = "MicroPython v1.29.0-p2.1 on 2026-11-25; P2-EC32MB with Propeller 2\r\n>>> ";

function emulateROM({ ack = ".", silicon = "G", sdReply = banner } = {}) {
    let serial;
    const encoder = new TextEncoder(), decoder = new TextDecoder();
    const reply = msg => serial.enqueue(encoder.encode(msg));
    const chunks = [], signals = [], commands = [];
    const port = {
        readable: new ReadableStream({start(controller) { serial = controller; }}),
        writable: new WritableStream({write(bytes) {
            const text = decoder.decode(bytes);
            if (text.startsWith("> Prop_Chk")) {
                commands.push("Prop_Chk");
                if (silicon) {
                    reply("Prop_V");
                    reply("er " + silicon + "\r\n");
                }
            } else if (text === "\x04") {
                commands.push("monitor");
                reply("P2-MONITOR V1.3\r\n");
            } else if (text === "R_BOOT_P2.BIX\r") {
                commands.push(text.trim());
                reply(sdReply);
            } else if (text.startsWith("> Prop_Txt")) {
                commands.push("Prop_Txt");
            } else if (text.trim() === "?" || text === "~") {
                commands.push(text.trim());
                if (text.trim() === "?") reply(ack);
                if (text === "~") {
                    reply("P2");
                    setTimeout(() => reply("OK"), 25);
                }
            } else if (text === "\r") {
                reply(">>> ");
            } else if (text.startsWith("import sys;")) {
                reply("\r\nP2LINK p2\r\n>>> ");
            } else {
                assert.match(text, /^[A-Za-z0-9+/]+\n$/);
                chunks.push(text.trim());
            }
        }}),
        async close() { assert.equal(this.readable.locked || this.writable.locked, false); },
        async open(options) { assert.equal(options.baudRate, 115200); },
        async setSignals(s) { signals.push(s); },
    };
    return { port, commands, chunks, signals };
}

function run(port, bytes, mode, report = () => {}, signal = new AbortController().signal) {
    return install(port, {bytes, mode, signal, report});
}

function sum32(bytes) {
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    let sum = 0;
    for (let i = 0; i < bytes.length; i += 4) sum += view.getUint32(i, true);
    return sum >>> 0;
}

test("RAM padding and little-endian ROM checksum at the hub boundary", () => {
    for (const size of [1, 2, 3, 4, 512 * 1024 - 4]) {
        const source = new Uint8Array(size).fill(0x73);
        const padded = ramPayload(source);
        assert.deepEqual(padded.subarray(0, size), source);
        assert.equal(sum32(padded), 0x706f7250);
    }
    assert.throws(() => ramPayload(new Uint8Array()), /size/);
    assert.throws(() => ramPayload(new Uint8Array(512 * 1024 - 3)), /size/);
});

for (const [profile, {flat}] of Object.entries(profiles)) {
    const image = readFileSync(new URL(flat.file, firmware));
    test(profile + " RAM stream decodes to the released firmware and ROM checksum", async () => {
        assert.equal(await digest(image), flat.sha256);
        const { port, commands, chunks, signals } = emulateROM();
        assert.equal(await run(port, image, "ram"), "G");
        const received = Buffer.from(chunks.join(""), "base64");
        assert.deepEqual(received.subarray(0, -4), image);
        assert.equal(sum32(received), 0x706f7250);
        assert.deepEqual(commands, ["Prop_Chk", "Prop_Txt", "?"]);
        assert.deepEqual(signals.map(s => s.dataTerminalReady), [true, false]);
        assert.equal(port.readable.locked || port.writable.locked, false);
    });

    test(profile + " flash stream matches the fast programmer and carries unmodified firmware", async () => {
        const script = "import sys; from flash_boot import programmer; sys.stdout.buffer.write(programmer(sys.argv[1], web=True))";
        const built = spawnSync("python", ["-c", script, profile], {
            cwd: fileURLToPath(new URL("../tools/", import.meta.url)),
        });
        assert.equal(built.status, 0, built.stderr?.toString());
        const { port, commands, chunks } = emulateROM();
        const progress = [];
        await run(port, built.stdout, "flash", (...event) => progress.push(event));
        const received = Buffer.from(chunks.join(""), "base64");
        assert.deepEqual(received, built.stdout);
        assert.equal(sum32(received), 0);
        assert.deepEqual(received.subarray(built.stdout.length - image.length), image);
        assert.deepEqual(commands, ["Prop_Chk", "Prop_Txt", "~"]);
        assert.equal(progress.at(-1)[2], true);
    });
}

test("SD boot runs the named card file and releases the open port for the IDE", async () => {
    const {port, commands, chunks} = emulateROM();
    assert.equal(await run(port, null, "sd"), "G");
    assert.deepEqual(commands, ["Prop_Chk", "monitor", "R_BOOT_P2.BIX"]);
    assert.deepEqual(chunks, []);
    assert.equal(port.readable.locked || port.writable.locked, false);
});

test("SD boot reports the ROM's file error", async () => {
    const {port} = emulateROM({sdReply: "R_BOOT_P2.BIX\r\n!\r\n"});
    await assert.rejects(run(port, null, "sd"), /SD card did not start/);
    assert.equal(port.readable.locked || port.writable.locked, false);
});

test("corrupt flash data is rejected before reset", async () => {
    const {port, signals, commands} = emulateROM();
    const image = new Uint8Array(504);
    image[500] = 1;
    await assert.rejects(run(port, image, "flash"), /checksum/);
    assert.deepEqual([signals, commands], [[], []]);
});

test("a wrong target never receives a loader or a boot command", async () => {
    const {port, commands} = emulateROM({silicon: null});
    await assert.rejects(run(port, Uint8Array.of(1), "ram"), /No P2 ROM/);
    assert.deepEqual(commands, ["Prop_Chk", "Prop_Chk", "Prop_Chk"]);
});

test("the ROM's negative acknowledgement is reported and both locks are released", async () => {
    const {port} = emulateROM({ack: "!"});
    await assert.rejects(run(port, Uint8Array.of(1), "ram"), /checksum/);
    assert.equal(port.readable.locked || port.writable.locked, false);
});

test("cancelling a partial flash transfer leaves the programmer unstarted", async () => {
    const {port, commands} = emulateROM();
    const ctl = new AbortController();
    await assert.rejects(run(port, new Uint8Array(8192), "flash", (_stage, progress) => {
        if (progress > 0) ctl.abort();
    }, ctl.signal), {name: "AbortError"});
    assert.deepEqual(commands, ["Prop_Chk", "Prop_Txt"]);
    assert.equal(port.readable.locked || port.writable.locked, false);
});
