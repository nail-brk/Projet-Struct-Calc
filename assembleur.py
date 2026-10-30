import argparse
import re
import sys


ALU_OPS = {"ADD": 0, "SUB": 1, "AND": 2, "OR": 3, "XOR": 4, "SL": 5, "SR": 6,"MUL": 7}  
CTRL_OPS = {"JMP": 0, "JEQU": 1, "JNEQ": 2, "JSUP": 3, "JINF": 4, "CALL": 5, "RET": 6}
COND_JUMPS = {"JEQU", "JNEQ", "JSUP", "JINF"}
TYPE_ALU, TYPE_MEM, TYPE_CTRL = 0b00, 0b10, 0b11  
MEM_SIZE = 1 << 16


class ErreurAsm(Exception):
    pass


def encode(typ, op=0, imm=0, dr=0, sr1=0, sr2=0, cst=0):
    return (typ & 3) | (op & 7) << 2 | (imm & 1) << 5 | (dr & 7) << 6 \
        | (sr1 & 7) << 9 | (sr2 & 7) << 12 | (cst & 0xFFFF) << 16


REG_RE = re.compile(r"^R([0-7])$", re.I)


def parse_reg(tok):
    m = REG_RE.match(tok.strip())
    return int(m.group(1)) if m else None


def parse_value(tok, labels, resolve):
    tok = tok.strip()
    if tok.startswith("#"):
        tok = tok[1:].strip()
    try:
        return int(tok, 0)
    except ValueError:
        pass
    if re.match(r"^[A-Za-z_.][\w.]*$", tok):
        if not resolve:
            return 0
        if tok not in labels:
            raise ErreurAsm(f"étiquette inconnue : {tok}")
        return labels[tok]
    raise ErreurAsm(f"valeur invalide : {tok!r}")


def check16(v):
    if not -32768 <= v <= 65535:
        raise ErreurAsm(f"constante hors limites (16 bits) : {v}")
    return v & 0xFFFF


def need(ops, n, mnem):
    if len(ops) != n:
        raise ErreurAsm(f"{mnem} attend {n} opérande(s), {len(ops)} fourni(s)")


def need_reg(tok, what="registre"):
    r = parse_reg(tok)
    if r is None:
        raise ErreurAsm(f"{what} attendu (R0..R7), trouvé {tok!r}")
    return r


def parse_mem(tok, labels, resolve):
    m = re.match(r"^\[\s*(.*?)\s*\]$", tok)
    if not m:
        raise ErreurAsm(f"opérande mémoire attendu entre crochets, trouvé {tok!r}")
    inner = m.group(1)
    base, cst = 0, 0
    m2 = re.match(r"^(R[0-7])\s*(?:([+-])\s*(.+))?$", inner, re.I)
    if m2:
        base = parse_reg(m2.group(1))
        if m2.group(3):
            v = parse_value(m2.group(3), labels, resolve)
            cst = -v if m2.group(2) == "-" else v
    else:
        cst = parse_value(inner, labels, resolve)
    return base, check16(cst)


def assemble_line(mnem, ops, labels, resolve):
    mnem = mnem.upper()
    forced_imm = False
    if mnem not in ALU_OPS and mnem not in CTRL_OPS and mnem not in ("LD", "ST") \
            and mnem.endswith("I") and mnem[:-1] in ALU_OPS:
        mnem, forced_imm = mnem[:-1], True

    if mnem in ALU_OPS:
        need(ops, 3, mnem)
        dr, sr1 = need_reg(ops[0]), need_reg(ops[1])
        r3 = parse_reg(ops[2])
        if r3 is not None and not forced_imm and not ops[2].strip().startswith("#"):
            return encode(TYPE_ALU, ALU_OPS[mnem], 0, dr, sr1, r3)
        cst = check16(parse_value(ops[2], labels, resolve))
        return encode(TYPE_ALU, ALU_OPS[mnem], 1, dr, sr1, 0, cst)

    if mnem in ("LD", "ST"):
        need(ops, 2, mnem)
        reg = need_reg(ops[0])
        base, cst = parse_mem(ops[1], labels, resolve)
        return encode(TYPE_MEM, 0 if mnem == "LD" else 1, 0, reg, base, 0, cst)

    if mnem in CTRL_OPS:
        op = CTRL_OPS[mnem]
        if mnem == "RET":
            need(ops, 0, mnem)
            return encode(TYPE_CTRL, op)
        if mnem in COND_JUMPS:
            need(ops, 3, mnem)
            sr1, sr2 = need_reg(ops[0]), need_reg(ops[1])
            addr = check16(parse_value(ops[2], labels, resolve))
            return encode(TYPE_CTRL, op, 0, 0, sr1, sr2, addr)
        need(ops, 1, mnem)
        addr = check16(parse_value(ops[0], labels, resolve))
        return encode(TYPE_CTRL, op, 0, 0, 0, 0, addr)

    raise ErreurAsm(f"instruction inconnue : {mnem}")


def clean(line):
    line = re.split(r";|//", line, maxsplit=1)[0]
    return line.strip()


def split_label(line):
    labels = []
    while True:
        m = re.match(r"^([A-Za-z_.][\w.]*)\s*:\s*(.*)$", line)
        if not m:
            return labels, line
        labels.append(m.group(1))
        line = m.group(2)


def parse_ops(rest):
    if not rest:
        return []
    ops, depth, cur = [], 0, ""
    for ch in rest:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        if ch == "," and depth == 0:
            ops.append(cur.strip())
            cur = ""
        else:
            cur += ch
    ops.append(cur.strip())
    return ops


def run_pass(lines, labels, resolve):
    out, addr = [], 0
    for lineno, raw in enumerate(lines, 1):
        try:
            line = clean(raw)
            lbls, line = split_label(line)
            if not resolve:
                for l in lbls:
                    if l in labels:
                        raise ErreurAsm(f"étiquette définie deux fois : {l}")
                    labels[l] = addr
            if not line:
                continue
            parts = line.split(None, 1)
            mnem, rest = parts[0], (parts[1] if len(parts) > 1 else "")
            ops = parse_ops(rest)
            if mnem.lower() == ".org":
                need(ops, 1, ".org")
                new = parse_value(ops[0], labels, True)
                if new < addr:
                    raise ErreurAsm(".org ne peut pas revenir en arrière")
                addr = new
                continue
            if mnem.lower() == ".word":
                need(ops, 1, ".word")
                word = parse_value(ops[0], labels, resolve) & 0xFFFFFFFF
            else:
                word = assemble_line(mnem, ops, labels, resolve)
            if addr >= MEM_SIZE:
                raise ErreurAsm("programme trop long pour la mémoire (2^16 mots)")
            out.append((addr, word, lineno, line))
            addr += 1
        except ErreurAsm as e:
            raise ErreurAsm(f"ligne {lineno} : {e}\n > {raw.rstrip()}")
    return out


def assemble(text):
    lines = text.splitlines()
    labels = {}
    run_pass(lines, labels, resolve=False)       
    return run_pass(lines, labels, resolve=True), labels  


def to_image(words):
    size = (words[-1][0] + 1) if words else 0
    mem = [0] * size
    for addr, w, _, _ in words:
        mem[addr] = w
    return "v2.0 raw\n" + "\n".join(f"{w:08x}" for w in mem) + "\n"


def main():
    ap = argparse.ArgumentParser(description="Assembleur pour le processeur Logisim")
    ap.add_argument("source", help="fichier .asm")
    ap.add_argument("-o", "--output", help="fichier de sortie (défaut : <source>.mem)")
    ap.add_argument("-l", "--listing", action="store_true", help="affiche un listing")
    args = ap.parse_args()

    with open(args.source, encoding="utf-8") as f:
        text = f.read()
    try:
        words, labels = assemble(text)
    except ErreurAsm as e:
        print(f"Erreur : {e}", file=sys.stderr)
        sys.exit(1)

    out = args.output or re.sub(r"\.[^.]*$", "", args.source) + ".mem"
    with open(out, "w", encoding="utf-8") as f:
        f.write(to_image(words))

    if args.listing:
        for addr, w, _, line in words:
            print(f"{addr:04x}: {w:08x}  {w:032b}  {line}")
    print(f"{len(words)} mot(s) écrit(s) dans {out}")


if __name__ == "__main__":
    main()
