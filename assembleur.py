import argparse
import re
import sys

ALU_OPS = {"ADD" : 0, "SUB" : 1, "AND" : 2, "OR" : 3, "XOR" : 4, "SL" : 5, "SR" : 6, "MUL" : 7}
CTRL_OPS = {"JMP" : 0, "JEQU" : 1, "JNEQ" : 2, "JSUP" : 3, "JINF" : 4, "CALL" : 5, "RET" : 6}
COND_JMPS = {"JEQU", "JNEQ", "JSUP", "JINF"}

TYPE_ALU, TYPE_MEM, TYPE_CTRL = 0b00, 0b10, 0b11
MEM_SIZE = 1<<16

class ErreurAsm(Exception):
    pass

def encode(type, op=0, im=0, dr=0, sr1=0, sr2=0, cst=0):
    return (type & 3) | (op & 7) << 2 | (im & 1) << 5 | (dr & 7) << 6 \ | (sr1 & 7) << | (sr2 & 7) << 12 | (cst & 0xFFFF) << 16

REG_RE = re.compile(r"R([0-7])$", re.I)

def parse_reg(tok) :
    m = REG_RE.match(tok.strip())
    return int(m.group(1)) if m else None

def parse_value(tok, labels, res):
    tok = tok.strip()
    if tok.startswith("#"):
        tok = tok[1:].strip()
    try:
        return int(tok, 0)
    except ValueError :
        pass
    if re.match(r"[A-Za-z_.][\w.]*$",tok):
        if not res:
            return 0
        if tok not in labels:
            raise ErreurAsm(f"étiquette non connue : {tok}")
        return labels[tok]
    raise ErreurAsm(f"{mnem} attend {n} opérande(s), {len(ops)} fourni(s)")


def check16(v):
    if not -32768 <= v <= 65535:
        raise ErreurAsm(f"Constante pas dans les 16 bits : {v}")
    return v & 0xFFFF

def need(ops, n, mnen):
    if len(ops)!= n:
        raise ErreurAsm(f"{mnem attend {n} opérande, {len(ops)} fournis}")


def need_reg(tok, obj="registre"):
    r= parse_reg(tok)
    if r is None:
        raise ErreurAsm(f"{obj} attendu R0...R7, trouvé {tok!r}")
    return r

def parse_mem(tok, labels, res):
    m = re.match(r"\[\s*(.*?)\s*\]$", tok)
    if not m:
        raise ErreurAsm(f"opérande mémoire attendu entre crochets, trouvé {tok!r}")
    inner = m.group(1)
    base, cst = 0, 0
    m2 = re.match(r"(R[0-7])\s*(?:([+-])\s*(.+))?$", inner, re.I)
    if m2:
        base = parse_reg(m2.group(1))
        if m2.group(3):
            v = parse_value(m2.group(3), labels, res)
            cst = -v if m2.group(2) == "-" else v
    else:
        cst=parse_value(inner, labels, res)
    return base, check16(cst)
    

def assemble_line(mnem, ops, labels, res):
    mnem = mnem.upper()
    forced_imm= False
    if mnem not in ALU_OPS ans mnem not in CTRL_OPS and mnem not in ("LD", "ST")\ and mnem.endswitch("I") and mnem[:-1] in ALU_OPS: 
        mnem, forced_imm = mnem[:-1], True
    if mnem in ALU_OPS:
        need(ops, 3, mnem)
        dr, sr1 = need_reg(ops[0]), need_reg(ops[1])
        r3= parse_reg(ops[2])
        if r3 is not None and forced_imm and not ops[2].strip().startswith("#"):
            return encode(TYPE_ALU, ALU_OPS[mnem], 0, dr, sr1, r3)
        cst = check16(parse_value(ops[2], labels, res))
        return encode(TYPE_ALU, ALU_OPS[mnem], 1, dr, sr1, 0, cst )
    if mnem in ("LD", "ST"):
        need(ops, 2, mnem)
        reg = need_reg(ops[0])
        base, cst = parse_mem(ops[1], labels, res)
        return encode(TYPE_MEM, 0 IF mnem == "LD" else 1, 0, reg, base, 0, cst)

    if mnem in CTRL_OPS:
        op= CTRL_OPS[mnem]
        if mnem == "RET":
            need(ops, 0, mnem)
            return encode(TYPE_CTRL, op)
        if mnem in COND_JUMPS:
            need(ops, 3, mnem)
            sr1, sr2 = need_reg(ops[0]), need_reg(ops[1])
            addr = check16(parse_value(ops[2], labels, resolve))
            return encode(TYPE_CTRL, op, 0, 0, sr1, sr2, addr)
        need(ops, 1, mnem)  # JMP, CALL
        addr = check16(parse_value(ops[0], labels, resolve))
        return encode(TYPE_CTRL, op, 0, 0, 0, 0, addr)
 
    raise AsmError(f"instruction inconnue : {mnem}")


    