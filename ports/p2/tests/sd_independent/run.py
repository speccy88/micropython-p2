"""Load the independent Smart Pin SD reader into hub RAM and record aggregate results."""
import argparse
import json
import re
import secrets
import sys
from pathlib import Path


def run(args):
    sys.path.insert(0, str(args.loader_dir.resolve()))
    from p2ram import P2Serial, read_image

    lbas = (0, 2048, 31916, 31917, 31918)
    challenge = secrets.token_bytes(4)
    while 3 in challenge:
        challenge = secrets.token_bytes(4)
    payload, details = read_image(args.image)
    result = dict(port=args.port, image=details, challenge=challenge.hex(), passed=False,
                  sd_driver="ne75/p2llvm libc/drivers/sdmmc.c Smart Pins, CMD17",
                  sector_sha256={}, repeated_sector_sha256={}, slot_classes={})
    try:
        with P2Serial(args.port) as target:
            result["rom"] = target.identify()
            result["download"] = target.load(payload)

            def line():
                response = target.line(timeout=12).decode("ascii").strip()
                if response.startswith("ERROR"):
                    raise ValueError(response)
                return response

            if line() != "P2SD ready":
                raise ValueError("missing diagnostic greeting")
            target.send(challenge)
            if line() != "RUN " + challenge.hex():
                raise ValueError("challenge mismatch")
            for read_pass, key in enumerate(("sector_sha256", "repeated_sector_sha256")):
                for lba in lbas:
                    fields = line().split()
                    if (len(fields) != 4 or fields[0] != "SEC" or int(fields[1], 16) != read_pass
                            or int(fields[2], 16) != lba or not re.fullmatch("[0-9a-f]{64}", fields[3])):
                        raise ValueError(f"invalid sector report at pass {read_pass} LBA {lba}")
                    result[key][str(lba)] = fields[3]
            if result["sector_sha256"] != result["repeated_sector_sha256"]:
                raise ValueError("sector digests changed between reads")
            for lba in lbas[2:]:
                fields = line().split()
                if (len(fields) != 3 or fields[0] != "DIR" or int(fields[1], 16) != lba
                        or not re.fullmatch("[-EDLVPS]{16}", fields[2])):
                    raise ValueError(f"invalid slot classes for sector {lba}")
                result["slot_classes"][str(lba)] = fields[2]
            tag, total, unique, ended = line().split()
            if tag != "SFN" or line() != "DONE " + challenge.hex():
                raise ValueError("incomplete diagnostic response")
            result.update(raw_sfn_count=int(total, 16), raw_sfn_unique=int(unique, 16),
                          root_terminator_seen=bool(int(ended, 16)))
            if result["raw_sfn_count"] != sum(s.count("S") for s in result["slot_classes"].values()):
                raise ValueError("slot counts disagree")
        if args.compare:
            other = json.loads(args.compare.read_text())["sector_sha256"]
            common = sorted(result["sector_sha256"].keys() & other.keys())
            result["matching_reference_sectors"] = {
                k: other[k] == result["sector_sha256"][k] for k in common
            }
            if not common or not all(result["matching_reference_sectors"].values()):
                raise ValueError("sector hashes disagree with supplied reference or no common LBAs")
        result["passed"] = True
    except Exception as exc:
        result["error"] = str(exc)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--loader-dir", type=Path, required=True)
    parser.add_argument("--port", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compare", type=Path, help="prior FAT diagnostic JSON with sector_sha256")
    sys.exit(run(parser.parse_args()))
