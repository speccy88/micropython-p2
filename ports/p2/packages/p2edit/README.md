# Editing a script on the P2

Install this package onto a writable volume, open the friendly serial REPL
and run `import p2edit; p2edit.edit('/main.py')`. Use `a TEXT` to append,
`r N TEXT` to replace a numbered line, `d N` to delete and `p` to list the
buffer. `q` discards the buffer. `w` saves and returns. The editor handles
UTF-8 text up to 4096 bytes and 256 lines. Saved lines end with LF.

A save writes `main.py.new`, flushes and closes it, moves the previous file
to `main.py.bak`, then renames the complete new file into place. An ordinary
failed save keeps the editable buffer in memory. If storage was full, make
room and retry. After power loss, inspect the three paths before starting
another save. The `.bak` contains the previous version. If `main.py` is
missing, rename the backup back to `main.py`, or use the verified complete
`.new` if you prefer the edit. Remove or rename the leftover files once you
have recovered your chosen version. Raw-mode soft reset skips startup scripts
while you repair them.
