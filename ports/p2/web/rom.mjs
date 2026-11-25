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
                if (failure) throw failure;
                const found = pattern.exec(text);
                if (found) {
                    text = text.slice(found.index + found[0].length);
                    return found;
                }
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

// The caller owns the already-open 115200-baud port and closes it on error.
// Returns only after the running interpreter identifies itself.
export async function install(port, {bytes, mode, signal, report}) {
    if (mode !== "ram" && mode !== "flash") throw Error("Unknown installation mode.");
    const flash = mode === "flash";
    if (flash) verifyFlashImage(bytes);
    const payload = flash ? bytes : ramPayload(bytes);
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
        } else {
            await send(" ?");
            const ack = await input.until(/[.!]/, 12000, signal);
            if (ack?.[0] !== ".") throw Error("RAM download checksum was not acknowledged. Check the cable and retry.");
            report("Starting MicroPython", 1);
        }
        if (!await input.until(/MicroPython v1\.29\.0[^\r\n]* with Propeller 2/, flash ? 60000 : 12000, signal)) {
            throw Error("No MicroPython startup banner received. Check the board and boot switches, or try loading RAM.");
        }
        return version[1];
    } finally {
        output.releaseLock();
        await input?.release();
    }
}
