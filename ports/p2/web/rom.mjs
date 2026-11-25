// SPDX-License-Identifier: MIT
// Propeller 2 ROM transport. See ../tools/p2ram.py and ../tools/flash_boot.py.
const encoder = new TextEncoder();
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

export async function digest(bytes) {
    const hash = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
    return Array.from(hash, n => n.toString(16).padStart(2, "0")).join("");
}

export function ramPayload(image) {
    if (!image.length || image.length > 512 * 1024 - 4) throw Error("Invalid hub image size.");
    const bytes = new Uint8Array(Math.ceil(image.length / 4) * 4 + 4);
    bytes.set(image);
    const words = new DataView(bytes.buffer);
    let checksum = 0x706f7250;  // ROM signature "Prop", little endian.
    for (let i = 0; i < bytes.length - 4; i += 4) checksum -= words.getUint32(i, true);
    words.setUint32(bytes.length - 4, checksum >>> 0, true);
    return bytes;
}

function verifyFlashImage(image) {
    if (image.length <= 496 || image.length % 4 || image.length + 1024 > 512 * 1024) {
        throw Error("Invalid flash programmer size.");
    }
    const words = new DataView(image.buffer, image.byteOffset, image.byteLength);
    let sum = 0;
    for (let i = 0; i < image.length; i += 4) sum += words.getUint32(i, true);
    if ((sum >>> 0) !== 0) throw Error("Invalid flash programmer checksum.");
}

// Releasing a Web Serial reader's lock keeps the readable stream available to
// ViperIDE. Cancelling the stream here can discard bytes or close the port.
function watch(port) {
    const reader = port.readable.getReader();
    const decoder = new TextDecoder();
    let text = "", closed = false, failure;
    const reading = (async () => {
        try {
            while (!closed) {
                const {value, done} = await reader.read();
                if (done) throw Error("USB serial disconnected.");
                text = (text + decoder.decode(value, {stream: true})).slice(-16384);
            }
        } catch (e) {
            if (!closed) failure = e;
        }
    })();
    return {
        clear() { text = ""; },
        async until(pattern, timeout, signal) {
            const deadline = performance.now() + timeout;
            do {
                signal.throwIfAborted();
                const found = pattern.exec(text);
                if (found) {
                    text = text.slice(found.index + found[0].length);
                    return found;
                }
                if (failure) throw failure;
                await delay(15);
            } while (performance.now() < deadline);
            return null;
        },
        async release() {
            closed = true;
            reader.releaseLock();
            await reading;
        }
    };
}

// RAM and flash start in the ROM at upload speed. SD starts at console speed.
async function transfer(port, {bytes, mode, signal, report}) {
    if (!["ram", "flash", "sd"].includes(mode)) throw Error("Unknown P2 boot mode.");
    const flash = mode === "flash";
    if (flash) verifyFlashImage(bytes);
    const payload = mode === "ram" ? ramPayload(bytes) : bytes;
    const output = port.writable.getWriter();
    let input;
    async function send(text) {
        signal.throwIfAborted();
        // An unplugged or stalled adapter must not leave the installer busy forever.
        let timer;
        try {
            await Promise.race([
                output.write(encoder.encode(text)),
                new Promise((_, reject) => { timer = setTimeout(() => reject(Error("Serial write timed out. Reconnect the USB adapter.")), 10000); })
            ]);
        } finally {
            clearTimeout(timer);
        }
    }
    try {
        input = watch(port);
        report("Looking for the P2 ROM", 0);
        let version;
        for (let attempt = 0; attempt < 3 && !version; attempt++) {
            signal.throwIfAborted();
            await port.setSignals({dataTerminalReady: true, requestToSend: false});
            await delay(10);
            await port.setSignals({dataTerminalReady: false, requestToSend: false});
            await delay(25);
            input.clear();
            await send("> Prop_Chk 0 0 0 0  ");
            version = await input.until(/Prop_Ver ([A-Za-z0-9])\s/, 650, signal);
        }
        if (!version) throw Error("No P2 ROM answered. Check power, reset wiring and the serial-boot switch settings, then retry.");
        if (mode === "sd") {
            report("Starting _BOOT_P2.BIX from your SD cardâ€¦");
            await send("\x04");
            if (!await input.until(/P2-MONITOR [^\r\n]+\r?\n/, 3000, signal)) {
                throw Error("The P2 ROM monitor did not answer. Check the serial-boot settings and retry.");
            }
            await send("R_BOOT_P2.BIX\r");
            const reply = await input.until(/MicroPython v[^\r\n]* with Propeller 2|(?:^|\n)!\r?\n/, 15000, signal);
            if (!reply || !reply[0].startsWith("MicroPython")) {
                throw Error("The SD card did not start MicroPython. Check _BOOT_P2.BIX in the root of a bootable FAT32 card.");
            }
            return version[1];
        }
        const stage = flash ? "Sending flash programmer" : "Loading hub RAM";
        report(stage, 0);
        input.clear();
        // Each intermediate chunk is divisible by three, so the concatenation
        // is one unpadded base64 stream as required by Prop_Txt.
        await send("> Prop_Txt 0 0 0 0 ");
        for (let offset = 0; offset < payload.length; offset += 3072) {
            const block = payload.subarray(offset, offset + 3072);
            await send(btoa(String.fromCharCode(...block)).replace(/=+$/, "") + "\n");
            report(stage, (offset + block.length) / payload.length);
        }
        if (flash) {
            // The signed-sum loadp2 stub consumes the ROM length. An appended
            // ROM checksum word would invalidate the programmer's own checksum.
            report("Programming boot flash. Keep power connected.", 1, true);
            await send("~");
            if (!await input.until(/P2OK/, 60000, signal)) {
                throw Error("Flash completion was not confirmed. Keep the board powered.");
            }
        } else {
            await send(" ?");
            const ack = await input.until(/[.!]/, 12000, signal);
            if (ack?.[0] !== ".") throw Error("RAM download checksum was not acknowledged. Check the cable and retry.");
            report("Starting MicroPython", 1);
        }
        return version[1];
    } finally {
        output.releaseLock();
        await input?.release();
    }
}

export const UPLOAD_BAUD = 2000000;
export const CONSOLE_BAUD = 115200;

export async function install(port, options) {
    const version = await transfer(port, options);
    if (options.mode === "sd") return version;
    // Web Serial can only change baud on open. For flash, P2OK is sent
    // after the final BUSY check, before the application takes over.
    await port.close();
    await port.open({baudRate: CONSOLE_BAUD, bufferSize: 65536, flowControl: "none"});
    const input = watch(port);
    const writer = port.writable.getWriter();
    try {
        // The first banner bytes can arrive while the adapter changes speed.
        // A carriage return asks an idle friendly REPL to repeat its prompt.
        for (let i = 0; i < 12; i++) {
            options.signal.throwIfAborted();
            await writer.write(encoder.encode("\r"));
            if (await input.until(/>>> /, 1000, options.signal)) {
                await writer.write(encoder.encode("import sys; print('P2LINK', sys.platform)\r"));
                if (await input.until(/\r?\nP2LINK p2\r?\n/, 2000, options.signal)) return version;
                break;
            }
        }
        throw Error("No P2 MicroPython reply at 115200 baud after the upload.");
    } finally {
        writer.releaseLock();
        await input.release();
    }
}
