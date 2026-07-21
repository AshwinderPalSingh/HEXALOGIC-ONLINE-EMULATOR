; timer0_overflow.asm — Timer 0 Mode 1, count cycles until overflow
; Timer 0 Mode 1: 16-bit counter, counts from TH0:TL0 to 0xFFFF then overflows
; With TH0=TL0=0x00, overflow after 65536 counts.
; At 12 MHz, each timer count = 1 machine cycle.

ORG 0000H

    MOV TMOD, #01H     ; Timer 0, Mode 1 (16-bit)
    MOV TH0, #00H      ; Start from 0
    MOV TL0, #00H
    SETB TR0            ; Start Timer 0

WAIT:
    JNB TF0, WAIT       ; Poll TF0 until overflow
    CLR TF0              ; Clear overflow flag
    CLR TR0              ; Stop timer
    SJMP $               ; Halt

END
