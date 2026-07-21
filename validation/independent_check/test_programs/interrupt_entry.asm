; interrupt_entry.asm — External interrupt 0, measure cycles to enter ISR
; INT0 vector is at 0x0003. The CPU takes 3 machine cycles to respond
; to a pending interrupt (save PC, vector fetch).

ORG 0000H
    LJMP MAIN

ORG 0003H              ; External Interrupt 0 vector
ISR_INT0:
    MOV R7, #0AAH       ; marker: ISR executed
    RETI

ORG 0030H
MAIN:
    MOV IE, #81H        ; Enable EA + EX0
    SETB IT0             ; Edge-triggered INT0 (falling-edge per MCS-51 spec)
    CLR P3.2             ; P3 defaults high at reset -> this is the falling edge that triggers INT0
    SETB P3.2            ; Return the pin high (not itself a trigger)
    NOP                  ; Allow interrupt to be serviced
    NOP
    NOP
    NOP
    SJMP $               ; Halt

END
