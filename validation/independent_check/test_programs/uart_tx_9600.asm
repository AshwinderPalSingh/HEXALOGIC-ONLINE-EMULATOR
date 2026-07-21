; uart_tx_9600.asm — UART Mode 1, 9600 baud via Timer 1
; At 11.0592 MHz, TH1=0xFD, SMOD=0 → 9600 baud exact
; Transmits 0x48 ('H') then 0x49 ('I') and halts.

ORG 0000H

    MOV TMOD, #20H      ; Timer 1, Mode 2 (8-bit auto-reload)
    MOV TH1, #0FDH      ; Reload value for 9600 baud at 11.0592 MHz
    MOV SCON, #50H       ; Mode 1, REN=1
    SETB TR1             ; Start Timer 1

    MOV SBUF, #48H       ; Transmit 'H'
TX1:
    JNB TI, TX1          ; Wait for TX complete
    CLR TI               ; Clear TI

    MOV SBUF, #49H       ; Transmit 'I'
TX2:
    JNB TI, TX2
    CLR TI

    SJMP $               ; Halt

END
