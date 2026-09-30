/*
 * Cortex-M4 packed compression/decompression for DAWN-Prime-256.
 *
 * Each input word holds two non-negative int16_t coefficients.  SMLAWB and
 * SMLAWT compute the signed 32x16 products, return product[47:16] and add
 * the accumulator, i.e. floor(a[i] * scale / 2^16) + offset for the
 * documented input ranges.  This matches the reference "(d >> 16) + offset"
 * exactly; poly_compress uses offset 0.  PKHBT then packs the two 16-bit
 * results back into one word.
 *
 * Contract used by the M4 backend:
 *   - a is 32-bit aligned and contains ZEN_N == 1024 coefficients;
 *   - poly_compress inputs are in [0, 768];
 *   - poly_decompress inputs are in [0, 255].
 */

.syntax unified
.cpu cortex-m4
.thumb

.macro scale_q16_function name, scale_lo, scale_hi, offset
.align 2
.global \name
.type \name, %function
.thumb_func
\name:
    push.w {r4-r10, lr}

    add.w r1, r0, #2048
    movw r2, #\scale_lo
.if \scale_hi
    movt r2, #\scale_hi
.endif
    movs r12, #\offset

1:
    ldm r0, {r3-r6}

    /* Four independent low-lane products + offset. */
    smlawb r7,  r2, r3, r12
    smlawb r8,  r2, r4, r12
    smlawb r9,  r2, r5, r12
    smlawb r10, r2, r6, r12

    /* Four independent high-lane products + offset. */
    smlawt r3, r2, r3, r12
    smlawt r4, r2, r4, r12
    smlawt r5, r2, r5, r12
    smlawt r6, r2, r6, r12

    /* low_result[15:0] | high_result[15:0] << 16 */
    pkhbt r3, r7,  r3, lsl #16
    pkhbt r4, r8,  r4, lsl #16
    pkhbt r5, r9,  r5, lsl #16
    pkhbt r6, r10, r6, lsl #16

    stm r0!, {r3-r6}
    cmp r0, r1
    bne 1b

    pop.w {r4-r10, pc}
.size \name, . - \name
.endm

scale_q16_function poly_compress,   21817, 0, 0
/* 0x00030100 == 196864; result = floor(a * 196864 / 2^16) + 2 */
scale_q16_function poly_decompress, 0x0100, 3, 2
