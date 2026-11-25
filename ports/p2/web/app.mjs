// SPDX-License-Identifier: MIT
import {digest, install} from "./rom.mjs";

const $ = id => document.getElementById(id);
const form = $("install-form");
const supported = window.isSecureContext && "serial" in navigator;
let job = null, ideLoading = null, editorOpened = false, lastInstalledPort = null;

function updateForm() {
    const flash = form.elements.mode.value === "flash";
    const profile = $("profile").value;
    $("action").textContent = flash ? "Replace boot flash & open ViperIDE" : "Load RAM & open ViperIDE";
    $("explain").textContent = flash
        ? "Overwrites your current boot program. Keep a recovery copy and leave power connected until Python starts."
        : "Runs until the next hardware reset or power cycle. Your boot flash stays intact.";
    $("board-code").textContent = profile === "lean" ? "P2 EDGE" : "P2-EC32MB";
    $("board-photo").src = profile === "lean" ? "./p2-edge.png" : "./p2-ec32mb.png";
    $("board-photo").alt = profile === "lean" ? "Plain P2 Edge with LEDs P56 and P57" : "P2-EC32MB with 32 MB PSRAM and LEDs P38 and P39";
    $("extra-label").textContent = profile === "edge" ? "PSRAM" : "GC arena";
    const option = $("profile").selectedOptions[0];
    $("extra-value").textContent = profile === "edge" ? "32 MiB" : option.dataset.gcKib + " KiB";
    $("board-name").textContent = profile === "threaded" ? "P2 Edge · Threaded" : "P2 Edge";
    for (const element of form.elements) element.disabled = Boolean(job) || !supported;
    $("connect").disabled = Boolean(job) || !supported;
    $("boot-sd").disabled = Boolean(job) || !supported;
    $("explore").disabled = Boolean(job);
}

function progress(message, fraction, programming = false) {
    $("status").hidden = false;
    $("status").removeAttribute("data-error");
    $("stage").textContent = message;
    $("progress").hidden = fraction == null;
    $("percent").textContent = fraction == null ? "" : Math.floor(fraction * 100) + "%";
    if (fraction != null) $("progress").value = fraction;
    if (programming) $("cancel").hidden = true;
}

function describe(err) {
    if (err.name === "NotFoundError") return "No port selected. Choose your USB serial adapter to try again.";
    if (err.name === "AbortError") return "Transfer cancelled. You can start again.";
    if (err.name === "NetworkError" || err.name === "InvalidStateError") {
        return "Could not use the serial port. Close mpremote, the RAM relay and any other serial tabs, then reconnect. " + err.message;
    }
    return err.message || String(err);
}

async function loadFirmware(profile, mode, signal) {
    const get = async url => {
        const response = await fetch(url, {signal, cache: "no-cache"});
        if (!response.ok) throw Error("Could not fetch " + url + " (HTTP " + response.status + ").");
        return response;
    };
    const manifest = await (await get("./firmware/index.json")).json();
    const info = manifest.profiles[profile][mode];
    const bytes = new Uint8Array(await (await get("./firmware/" + info.file)).arrayBuffer());
    if (bytes.length !== info.bytes || await digest(bytes) !== info.sha256) {
        throw Error("The firmware download failed its SHA-256 check. Reload the page and try again.");
    }
    return bytes;
}

function loadEditor() {
    if (ideLoading) return ideLoading;
    const frame = $("ide");
    frame.src = frame.dataset.entry;
    ideLoading = new Promise((resolve, reject) => {
        const deadline = Date.now() + 60000;
        const timer = setInterval(() => {
            const ready = frame.contentDocument?.documentElement.dataset.p2IdeReady;
            if (ready && frame.contentWindow.app?.connectInstalledP2) {
                clearInterval(timer);
                resolve(frame.contentWindow.app);
            } else if (Date.now() >= deadline) {
                clearInterval(timer);
                ideLoading = null;
                reject(Error("ViperIDE could not finish loading. Check your connection and retry."));
            }
        }, 100);
    });
    return ideLoading;
}

function showEditor() {
    editorOpened = true;
    $("setup").hidden = true;
    $("workspace").hidden = false;
    $("ide").contentWindow.dispatchEvent(new Event("resize"));
    $("ide").focus();
}

async function start(action) {
    if (job) return;
    const controller = new AbortController();
    job = controller;
    const {signal} = controller;
    const profile = $("profile").value;
    const mode = form.elements.mode.value;
    updateForm();
    let port, ownsPort = false;
    try {
        if (action === "explore") {
            progress("Opening ViperIDE…");
            await loadEditor();
            showEditor();
            return;
        }
        progress("Choose the serial adapter connected to your P2.");
        // requestPort must run in the click's user activation, before fetch or IDE setup.
        port = await navigator.serial.requestPort();
        progress(action === "install" ? "Checking the release firmware…" : "Opening ViperIDE…");
        $("cancel").hidden = false;
        const [ide, bytes] = await Promise.all([
            loadEditor(), action === "install" ? loadFirmware(profile, mode, signal) : null
        ]);
        signal.throwIfAborted();
        if (action === "connect" && port === lastInstalledPort && port.writable?.locked) {
            showEditor();
            return;
        }
        await ide.disconnectDevice(false);
        lastInstalledPort = null;
        signal.throwIfAborted();
        await port.open({baudRate: 115200, bufferSize: 65536, flowControl: "none"});
        ownsPort = true;
        if (action === "install") await install(port, {bytes, mode, signal, report: progress});
        if (action === "sd") await install(port, {mode: "sd", signal, report: progress});
        signal.throwIfAborted();
        $("cancel").hidden = true;
        progress("Opening the board in ViperIDE…");
        const state = await ide.connectInstalledP2(port);
        ownsPort = false;
        lastInstalledPort = port;
        showEditor();
        if (state === "ready") {
            if (action === "install" && profile === "threaded") {
                await ide.openP2Example(profile);
            } else {
                const sample = await fetch("./blink_p2.py");
                if (!sample.ok) throw new Error("Could not load the LED example.");
                await ide.openP2Example(profile, await sample.text());
            }
        }
    } catch (err) {
        progress(describe(err));
        $("status").setAttribute("data-error", "");
    } finally {
        if (ownsPort) {
            try { await port.close(); } catch { /* Unplugged adapters may already be closed. */ }
        }
        $("cancel").hidden = true;
        job = null;
        updateForm();
    }
}

form.addEventListener("change", updateForm);
form.addEventListener("submit", e => { e.preventDefault(); start("install"); });
$("cancel").onclick = () => job?.abort();
$("connect").onclick = () => start("connect");
$("boot-sd").onclick = () => start("sd");
$("explore").onclick = () => start("explore");
$("back").onclick = () => {
    $("workspace").hidden = true;
    $("setup").hidden = false;
    $("status").hidden = true;
    if (editorOpened) $("explore").textContent = "Return to ViperIDE";
    $("install-button").focus();
};
window.addEventListener("beforeunload", e => {
    if (job) { e.preventDefault(); e.returnValue = ""; }
});
if (!supported) {
    $("support").hidden = false;
    $("support").innerHTML = 'USB installation needs desktop Chrome or Edge over HTTPS. You can still open the editor or use the <a href="https://github.com/speccy88/micropython-p2/releases/latest">command-line starter kit</a>.';
    document.querySelector(".install").prepend($("support"));
}
updateForm();
