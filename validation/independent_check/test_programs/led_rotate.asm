; led_rotate.asm — LED rotate on P1 with delay loop
; Expected: first full rotation period = measurable in machine cycles
; This is the same program referenced in the paper's Table V.
;
; At 12 MHz: 1 machine cycle = 1 µs
; The delay subroutine inner loop: DJNZ R1,$ = 2 cycles × 255 = 510 cycles
; Outer: DJNZ R0,AGAIN = 2 cycles × 200 iterations of inner = 200×(510+2) = 102400
; Plus overhead per rotation step.

ORG 0000H

START:
    MOV A, #01H        ; 1 cycle  — initial LED pattern
    MOV P1, A          ; 1 cycle  — drive P1

ROTATE:
    ACALL DELAY        ; 2 cycles — call delay subroutine
    RL A               ; 1 cycle  — rotate left
    MOV P1, A          ; 1 cycle  — update P1
    SJMP ROTATE        ; 2 cycles — loop forever

DELAY:
    MOV R0, #200       ; 1 cycle
AGAIN:
    MOV R1, #255       ; 1 cycle
    DJNZ R1, $         ; 2 cycles × 255 = 510 (inner loop)
    DJNZ R0, AGAIN     ; 2 cycles (outer loop)
    RET                ; 2 cycles

END
