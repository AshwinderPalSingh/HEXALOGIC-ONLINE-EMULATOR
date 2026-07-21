import ast
import inspect
from pathlib import Path

from sim8051 import Assembler8051, CPU8051
from sim8051.opcodes import opcodes_lookup

SAMPLE_OPERANDS = {
    "DIRECT": "30H",
    "BIT": "20H",
    "/BIT": "/20H",
    "#IMMED": "#01H",
    "ADDR11": "30H",
    "ADDR16": "1234H",
    "A": "A",
    "AB": "AB",
    "C": "C",
    "DPTR": "DPTR",
    "@R0": "@R0",
    "@R1": "@R1",
    "@A+DPTR": "@A+DPTR",
    "@A+PC": "@A+PC",
    "R0": "R0",
    "R1": "R1",
    "R2": "R2",
    "R3": "R3",
    "R4": "R4",
    "R5": "R5",
    "R6": "R6",
    "R7": "R7",
}


def _run_code(code: str) -> CPU8051:
    assembler = Assembler8051(code_size=0x10000)
    program = assembler.assemble(code.strip())
    cpu = CPU8051(code_size=0x10000)
    cpu.load_program(program)
    for _ in range(500):
        if cpu.halted:
            break
        cpu.step_into()
    return cpu


# Branch/call forms encode their relative-offset or page byte as an extra
# trailing placeholder token in this table (a holdover from the legacy
# engine's key-naming convention), so their table arity doesn't match their
# real user-facing operand count. Their encoding is already covered directly
# by the execution tests below (and by the two-pass assembler tests in
# test_sim8051_core.py), so this generic mechanical check only needs to cover
# the remaining, unambiguous non-branch forms.
_BRANCH_MNEMONICS = {
    "SJMP", "JZ", "JNZ", "JC", "JNC", "JB", "JNB", "JBC",
    "CJNE", "DJNZ", "AJMP", "ACALL", "LJMP", "LCALL", "RET", "RETI",
}


def test_every_opcode_form_assembles_without_error():
    """Every non-branch mnemonic+addressing-form declared in the shared opcode
    table must actually produce machine code through the real two-pass
    assembler, not just exist as a dict key."""
    forms = sorted({key.upper() for key in opcodes_lookup if key not in {"undefined", "ORG DIRECT"}})
    failures = []
    for form in forms:
        opcode, *params = form.split()
        if opcode in _BRANCH_MNEMONICS:
            continue
        args = [SAMPLE_OPERANDS.get(param, param) for param in params]
        operand_str = ",".join(args)
        command = f"{opcode} {operand_str}".strip() if args else opcode
        assembler = Assembler8051(code_size=0x10000)
        try:
            assembler.assemble(f"ORG 0000H\n{command}\nEND\n")
        except Exception as exc:  # pragma: no cover - failure path only
            failures.append((form, command, str(exc)))
    assert failures == []


def test_opcode_table_has_no_duplicate_source_keys():
    """Regression guard for the AJMP/ACALL duplicate-key bug: a Python dict
    literal silently keeps only the last assignment for a repeated key, so a
    duplicate key here would mean 7 of 8 page-dependent opcode forms silently
    vanish without any error at import time. Parse the source as an AST and
    fail loudly if the same key literal is ever written twice."""
    from sim8051 import opcodes as opcodes_module

    tree = ast.parse(Path(opcodes_module.__file__).read_text())
    dict_node = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Dict) and any(isinstance(k, ast.Constant) for k in node.keys)
    )
    seen = set()
    duplicates = []
    for key_node in dict_node.keys:
        key = key_node.value
        if key in seen:
            duplicates.append(key)
        seen.add(key)
    assert duplicates == []


def test_acall_and_ret_return_to_next_instruction():
    cpu = _run_code(
        """
        ORG 0000H
        MOV A,#01H
        ACALL SUB
        INC A
        SJMP DONE
        SUB: INC A
        RET
        DONE: NOP
        END
        """
    )
    assert cpu.a == 0x03
    assert cpu.sp == 0x07


def test_jbc_clears_bit_and_jumps():
    cpu = _run_code(
        """
        ORG 0000H
        SETB 20H
        JBC 20H,TAKEN
        MOV A,#00H
        SJMP END_
        TAKEN: MOV A,#01H
        END_: NOP
        END
        """
    )
    assert cpu.a == 0x01
    assert cpu.memory.read_bit(0x20) == 0


def test_subb_respects_carry_borrow():
    cpu = CPU8051(code_size=0x10000)
    assembler = Assembler8051(code_size=0x10000)
    program = assembler.assemble(
        """
        ORG 0000H
        MOV A,#03H
        SUBB A,#01H
        END
        """.strip()
    )
    cpu.load_program(program)
    cpu.memory.write_sfr("PSW", 0x80)  # CY=1 before SUBB, mirrors the borrow-in case
    for _ in range(10):
        if cpu.halted:
            break
        cpu.step_into()
    assert cpu.a == 0x01
    assert (cpu.memory.read_sfr("PSW") & 0x80) == 0


def test_mov_dptr_keeps_high_low_byte_order():
    cpu = _run_code("ORG 0000H\nMOV DPTR,#1234H\nEND\n")
    assert cpu.memory.read_sfr("DPH") == 0x12
    assert cpu.memory.read_sfr("DPL") == 0x34
    assert cpu.dptr == 0x1234


def test_movc_reads_code_memory_with_a_plus_dptr():
    cpu = CPU8051(code_size=0x10000)
    assembler = Assembler8051(code_size=0x10000)
    program = assembler.assemble(
        """
        ORG 0000H
        MOV DPTR,#0010H
        MOV A,#02H
        MOVC A,@A+DPTR
        END
        """.strip()
    )
    cpu.load_program(program)
    cpu.memory.rom[0x0012] = 0x7A
    for _ in range(10):
        if cpu.halted:
            break
        cpu.step_into()
    assert cpu.a == 0x7A


def test_mov_c_bit_and_mov_bit_c():
    cpu = _run_code(
        """
        ORG 0000H
        CLR C
        SETB 20H
        MOV C,20H
        MOV 21H,C
        END
        """
    )
    assert cpu.memory.read_bit(0x21) == 1


def test_orl_anl_c_with_complement_bit():
    cpu = _run_code(
        """
        ORG 0000H
        CLR C
        CLR 23H
        ORL C,/23H
        MOV 24H,C
        SETB C
        SETB 25H
        ANL C,/25H
        MOV 26H,C
        END
        """
    )
    assert cpu.memory.read_bit(0x24) == 1
    assert cpu.memory.read_bit(0x26) == 0


def test_mul_and_div_ab_operands():
    cpu = _run_code(
        """
        ORG 0000H
        MOV A,#10H
        MOV B,#10H
        MUL AB
        END
        """
    )
    assert cpu.a == 0x00
    assert cpu.b == 0x01

    cpu = _run_code(
        """
        ORG 0000H
        MOV A,#06H
        MOV B,#03H
        DIV AB
        END
        """
    )
    assert cpu.a == 0x02
    assert cpu.b == 0x00


def test_end_directive_and_label_only_jump_target():
    cpu = _run_code(
        """
        ORG 0000H
        MOV A,#01H
        SJMP HERE
        MOV A,#0FFH
        HERE:
        INC A
        END
        MOV A,#00H
        """
    )
    assert cpu.a == 0x02


def test_mov_to_tmod_and_timer_sfr_registers():
    cpu = _run_code(
        """
        ORG 0000H
        MOV TMOD,#01H
        MOV TH0,#0FCH
        MOV TL0,#018H
        END
        """
    )
    assert cpu.memory.read_sfr("TMOD") == 0x01
    assert cpu.memory.read_sfr("TH0") == 0xFC
    assert cpu.memory.read_sfr("TL0") == 0x18


def test_djnz_hex_like_label_name_resolves_as_label():
    cpu = _run_code(
        """
        ORG 0000H
        MOV R5,#03H
        D1: DJNZ R5,D1
        MOV A,#0AAH
        END
        """
    )
    assert cpu.a == 0xAA
    assert cpu.memory.read_direct(0x05) == 0x00


def test_ei_alias_sets_interrupt_enable_bits():
    cpu = _run_code(
        """
        ORG 0000H
        SETB EI.7
        SETB EI.1
        END
        """
    )
    assert cpu.memory.read_sfr("IE") == 0x82
