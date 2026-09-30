#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "params.h"
#include "auxfunc.h"
#include "sample.h"
#include "symmetric.h"
#include "radix16_r2.h"
#ifdef HASHING_PROFILE
#include "hal.h"
extern unsigned long long func_cycles;
#endif
static uint32_t r2_radix16_word_parity(uint32_t x)
{
    x &= R2_RADIX16_LANE_MASK;
    x ^= x >> 16;
    x ^= x >> 8;
    x ^= x >> 4;
    return x & 1u;
}

static uint32_t r2_radix16_prefix_word(uint32_t x, uint32_t carry)
{
    x &= R2_RADIX16_LANE_MASK;
    x ^= x << 4;
    x ^= x << 8;
    x ^= x << 16;
    x &= R2_RADIX16_LANE_MASK;
    return x ^ (R2_RADIX16_LANE_MASK & (0u - (carry & 1u)));
}

static void r2_radix16_prefix_xor_128_fixed(uint32_t out[R2_RADIX16_WORDS(ZEN_N4)],
                                            const uint32_t in[R2_RADIX16_WORDS(ZEN_N4)])
{
    uint32_t carry = 0;
    unsigned int i;

    for (i = 0; i < R2_RADIX16_WORDS(ZEN_N4); i++) {
        uint32_t word = r2_radix16_prefix_word(in[i], carry);

        out[i] = word;
        carry = word >> 28;
    }
}

static uint32_t r2_radix16_parity_128_fixed(const uint32_t a[R2_RADIX16_WORDS(ZEN_N4)])
{
    uint32_t acc = 0;
    unsigned int i;

    for (i = 0; i < R2_RADIX16_WORDS(ZEN_N4); i++) {
        acc ^= a[i];
    }
    return r2_radix16_word_parity(acc);
}

static void r2_radix16_xor_mask_128_fixed(uint32_t dst[R2_RADIX16_WORDS(ZEN_N4)],
                                          const uint32_t src[R2_RADIX16_WORDS(ZEN_N4)],
                                          uint32_t bit)
{
    uint32_t mask = 0u - (bit & 1u);
    unsigned int i;

    for (i = 0; i < R2_RADIX16_WORDS(ZEN_N4); i++) {
        dst[i] ^= src[i] & R2_RADIX16_LANE_MASK & mask;
    }
}

static void r2_radix16_zero_tail_128(uint32_t a[R2_RADIX16_WORDS(ZEN_N4)],
                                     unsigned int words)
{
    unsigned int i;

    for (i = words; i < R2_RADIX16_WORDS(ZEN_N4); i++) {
        a[i] = 0;
    }
}

static void r2_radix16_fold_128_fixed(uint32_t out[R2_RADIX16_WORDS(ZEN_N4)],
                                      const uint32_t in[R2_RADIX16_WORDS(ZEN_N4)],
                                      unsigned int out_n)
{
    unsigned int i, j;
    unsigned int out_words = R2_RADIX16_WORDS(out_n);

    if (out_n == 2u) {
        uint32_t even = 0;
        uint32_t odd = 0;

        for (i = 0; i < R2_RADIX16_WORDS(ZEN_N4); i++) {
            uint32_t word = in[i] & R2_RADIX16_LANE_MASK;

            even ^= word ^ (word >> 8) ^ (word >> 16) ^ (word >> 24);
            odd ^= (word >> 4) ^ (word >> 12) ^ (word >> 20) ^ (word >> 28);
        }
        out[0] = (even & 1u) | ((odd & 1u) << 4);
    } else if (out_n == 4u) {
        uint32_t acc = 0;

        for (i = 0; i < R2_RADIX16_WORDS(ZEN_N4); i++) {
            uint32_t word = in[i] & R2_RADIX16_LANE_MASK;

            acc ^= word ^ (word >> 16);
        }
        out[0] = acc & 0x1111u;
    } else if (out_n == 8u) {
        uint32_t acc = 0;

        for (i = 0; i < R2_RADIX16_WORDS(ZEN_N4); i++) {
            acc ^= in[i];
        }
        out[0] = acc & R2_RADIX16_LANE_MASK;
    } else {
        unsigned int step_words = out_n >> 3;

        for (i = 0; i < step_words; i++) {
            uint32_t acc = 0;

            for (j = i; j < R2_RADIX16_WORDS(ZEN_N4); j += step_words) {
                acc ^= in[j];
            }
            out[i] = acc & R2_RADIX16_LANE_MASK;
        }
    }

    r2_radix16_zero_tail_128(out, out_words);
}

static void r2_radix16_div_xn_plus1_128_fixed(uint32_t a[R2_RADIX16_WORDS(ZEN_N4)],
                                              unsigned int step)
{
    unsigned int i;

    if ((step & 7u) == 0u) {
        unsigned int step_words = step >> 3;

        for (i = step_words; i < R2_RADIX16_WORDS(ZEN_N4); i++) {
            a[i] ^= a[i - step_words];
            a[i] &= R2_RADIX16_LANE_MASK;
        }
    } else {
        uint32_t prev = 0;
        unsigned int shift = 4u * step;

        for (i = 0; i < R2_RADIX16_WORDS(ZEN_N4); i++) {
            uint32_t word = (a[i] & R2_RADIX16_LANE_MASK)
                          ^ (prev >> (32u - shift));
            unsigned int distance;

            for (distance = shift; distance < 32u; distance <<= 1) {
                word ^= word << distance;
            }
            word &= R2_RADIX16_LANE_MASK;
            a[i] = word;
            prev = word;
        }
    }
}

static void r2_radix16_xor_shifted_fixed(uint32_t *dst,
                                         const uint32_t *src,
                                         unsigned int src_n,
                                         unsigned int shift)
{
    unsigned int words = R2_RADIX16_WORDS(src_n);
    unsigned int word_shift = shift >> 3;
    unsigned int lane_shift = shift & 7u;
    unsigned int bit_shift = 4u * lane_shift;
    unsigned int tail = src_n & 7u;
    unsigned int i;

    for (i = 0; i < words; i++) {
        uint32_t word = src[i] & R2_RADIX16_LANE_MASK;

        if ((i + 1u == words) && tail) {
            word &= (1u << (4u * tail)) - 1u;
        }
        dst[word_shift + i] ^= word << bit_shift;
        if (lane_shift
                && (8u * i + (8u - lane_shift) < src_n)) {
            dst[word_shift + i + 1u] ^= word >> (32u - bit_shift);
        }
    }
}

extern int poly_xor4_radix16_asm(uint32_t *out, const int16_t *in);

int poly_xor4_radix16(uint32_t *out, const int16_t *in)
{
    return poly_xor4_radix16_asm(out, in);
}

void FastInversion(uint32_t *f_inv, const uint32_t *f_rad)
{
    unsigned int l, n;
    uint32_t k[R2_RADIX16_WORDS(ZEN_N4)];
    uint32_t b[R2_RADIX16_WORDS(ZEN_N4)];
    uint32_t tmp[R2_RADIX16_WORDS(ZEN_N4)];
    uint32_t b0;

    r2_radix16_prefix_xor_128_fixed(k, f_rad);

    b0 = r2_radix16_parity_128_fixed(k);
    r2_radix16_xor_mask_128_fixed(k, f_rad, b0);
    r2_radix16_prefix_xor_128_fixed(k, k);

    memset(f_inv, 0, R2_RADIX16_WORDS(ZEN_N4) * sizeof(uint32_t));
    f_inv[0] = (b0 ^ 1u) | (b0 << 4);

    n = 1;
    for(l = 1; l < ZEN_N4_LOG2; l++)
    {
        unsigned int words;

        n = 2 * n;
        words = R2_RADIX16_WORDS(n);

        r2_radix16_fold_128_fixed(tmp, k, n);
        r2_radix16_mul(b, f_inv, tmp, n);
        r2_radix16_zero_tail_128(b, words);

        r2_radix16_mul(tmp, b, f_rad, ZEN_N4);
        for (words = 0; words < R2_RADIX16_WORDS(ZEN_N4); words++) {
            k[words] ^= tmp[words] & R2_RADIX16_LANE_MASK;
        }

        r2_radix16_div_xn_plus1_128_fixed(k, n);
        r2_radix16_xor_shifted_fixed(f_inv, b, n, 0);
        r2_radix16_xor_shifted_fixed(f_inv, b, n, n);
    }
}


void poly_generate_g(int16_t *a, const uint8_t *seed, uint8_t nonce)
{
    uint8_t buf[ZEN_N_LEN_BYTES*2];

    zen_pseudoXOF(ZEN_N*2, seed, SEED_LEN_BYTES*8, buf, nonce);
    cbd1(a, buf);
}

void poly_generate_f(int16_t *a, const uint8_t *seed, uint8_t nonce)
{
    uint8_t buf[ZEN_N_LEN_BYTES*4];

    zen_pseudoXOF(ZEN_N*4, seed, SEED_LEN_BYTES*8, buf, nonce);
    tenary3_16(a, buf);
}

void poly_generate_se(int16_t *a, const uint8_t *seed, uint8_t nonce)
{
    uint8_t buf[ZEN_N_LEN_BYTES*2];

    zen_pseudoXOF(ZEN_N*2, seed, SEED_LEN_BYTES*8, buf, nonce);
    cbd1(a, buf);
}

void poly_bit2byte_pack(uint8_t *pa, const int16_t *a, const unsigned int n)
{
    unsigned int i;
    const int16_t *src = a;

    for(i = 0; i < n / 8; i++)
    {
        pa[i] = (uint8_t)(
              ((uint16_t)src[0] & 1u)
            | (((uint16_t)src[1] & 1u) << 1)
            | (((uint16_t)src[2] & 1u) << 2)
            | (((uint16_t)src[3] & 1u) << 3)
            | (((uint16_t)src[4] & 1u) << 4)
            | (((uint16_t)src[5] & 1u) << 5)
            | (((uint16_t)src[6] & 1u) << 6)
            | (((uint16_t)src[7] & 1u) << 7));

        src += 8;
    }
}

void poly_byte2bit_unpack(int16_t *a, const uint8_t *pa, const unsigned int n)
{
    unsigned int i;
    int16_t *dst = a;

    for(i = 0; i < n / 8; i++)
    {
        uint8_t byte = pa[i];

        dst[0] = (int16_t)((byte >> 0) & 1u);
        dst[1] = (int16_t)((byte >> 1) & 1u);
        dst[2] = (int16_t)((byte >> 2) & 1u);
        dst[3] = (int16_t)((byte >> 3) & 1u);
        dst[4] = (int16_t)((byte >> 4) & 1u);
        dst[5] = (int16_t)((byte >> 5) & 1u);
        dst[6] = (int16_t)((byte >> 6) & 1u);
        dst[7] = (int16_t)((byte >> 7) & 1u);

        dst += 8;
    }
}

void poly_secretkey_pack(uint8_t *ss, const int16_t *a)
{
    unsigned int i, j, k;

    for(i = 0; i < ZEN_N; i += 32)
    {
        const int16_t *src = a + i;
        uint8_t *dst = ss + (i / 32) * 40;

        for(k = 0; k < 10; k++)
        {
            uint32_t w = 0;

            for(j = 0; j < 32; j++)
            {
                w |= (uint32_t)((((uint16_t)src[j] >> k) & 1u) << j);
            }

            dst[4 * k + 0] = (uint8_t)(w);
            dst[4 * k + 1] = (uint8_t)(w >> 8);
            dst[4 * k + 2] = (uint8_t)(w >> 16);
            dst[4 * k + 3] = (uint8_t)(w >> 24);
        }
    }
}

void poly_secretkey_unpack(int16_t *a, const uint8_t *ss)
{
    unsigned int i, j, k;

    for(i = 0; i < ZEN_N; i += 32)
    {
        int16_t *dst = a + i;
        const uint8_t *src = ss + (i / 32) * 40;

        for(j = 0; j < 32; j++)
        {
            dst[j] = 0;
        }

        for(k = 0; k < 10; k++)
        {
            uint32_t w;

            w  = (uint32_t)src[4 * k + 0];
            w |= (uint32_t)src[4 * k + 1] << 8;
            w |= (uint32_t)src[4 * k + 2] << 16;
            w |= (uint32_t)src[4 * k + 3] << 24;

            for(j = 0; j < 32; j++)
            {
                dst[j] |= (int16_t)(((w >> j) & 1u) << k);
            }
        }
    }
}

static const uint64_t pack_publickey_table[] = 
{
    1, 769, 591361, 454756609, 349707832321
};

void poly_publickey_pack(uint8_t *pa, const int16_t *a)
{
    int i, idx;
    uint64_t tmp[103] = {0};
    uint64_t res[77]  = {0};

    idx = 0;
    for(i = 0; i < ZEN_N - 2; i += 5)
    {
        tmp[idx] =
              (uint64_t)(uint16_t)a[i]
            + (uint64_t)(uint16_t)a[i + 1] * pack_publickey_table[1]
            + (uint64_t)(uint16_t)a[i + 2] * pack_publickey_table[2]
            + (uint64_t)(uint16_t)a[i + 3] * pack_publickey_table[3]
            + (uint64_t)(uint16_t)a[i + 4] * pack_publickey_table[4];
        idx++;
    }

    tmp[102] =
          (uint64_t)(uint16_t)a[ZEN_N - 2]
        + (uint64_t)(uint16_t)a[ZEN_N - 1] * pack_publickey_table[1];

    idx = 0;
    for(i = 0; i < 100; i += 4)
    {
        uint64_t x0 = tmp[i];
        uint64_t x1 = tmp[i + 1];
        uint64_t x2 = tmp[i + 2];
        uint64_t x3 = tmp[i + 3];

        res[idx++] = x0 | ((x3 & 0xFFFFULL) << 48);
        res[idx++] = x1 | (((x3 >> 16) & 0xFFFFULL) << 48);
        res[idx++] = x2 | (((x3 >> 32) & 0xFFFFULL) << 48);
    }

    res[idx++] = tmp[100] | ((tmp[102] & 0xFFFFULL) << 48);
    res[idx++] = tmp[101] | (((tmp[102] >> 16) & 0xFULL) << 48);

    memcpy(pa, (const uint8_t *)res, ZEN_INDCPA_PUBLICKEY_LEN_BYTES);
}

static inline uint16_t divmod769_tail(uint64_t *x)
{
    uint32_t v = (uint32_t)*x;
    uint32_t q = ((uint64_t)v * 349071u) >> 28;
    uint32_t r = v - q * 769u;
    uint32_t underflow = r >> 31;

    q -= underflow;
    r += underflow * 769u;

    *x = q;
    return (uint16_t)r;
}

static inline uint32_t div769_u26(uint32_t x, uint32_t *r)
{
    uint32_t q = ((uint64_t)x * 44681065u) >> 35;

    *r = x - q * 769u;
    return q;
}

static inline uint16_t divmod769_u48(uint64_t *x)
{
    uint64_t v = *x;
    uint32_t r = 0;
    uint32_t q2, q1, q0;

    q2 = div769_u26((uint32_t)(v >> 32), &r);
    q1 = div769_u26((r << 16) | ((uint32_t)(v >> 16) & 0xffffu), &r);
    q0 = div769_u26((r << 16) | ((uint32_t)v & 0xffffu), &r);

    *x = ((uint64_t)q2 << 32) | ((uint64_t)q1 << 16) | q0;
    return (uint16_t)r;
}

void poly_publickey_unpack(int16_t *a, const uint8_t *pa)
{
    int i, idx;
    uint64_t res[77]  = {0};
    uint64_t tmp[103] = {0};
    const uint64_t MASK48   = 0x0000FFFFFFFFFFFFULL;

    memcpy((uint8_t *)res, pa, ZEN_INDCPA_PUBLICKEY_LEN_BYTES);

    idx = 76;

    tmp[101] = res[idx] & MASK48;
    tmp[102] = ((res[idx--] >> 48) & 0xFULL) << 16;

    tmp[100] = res[idx] & MASK48;
    tmp[102] |= ((res[idx--] >> 48) & 0xFFFFULL);

    for(i = 99; i > 0; i -= 4)
    {
        tmp[i - 1] = res[idx] & MASK48;
        tmp[i]     = ((res[idx--] >> 48) & 0xFFFFULL) << 32;

        tmp[i - 2] = res[idx] & MASK48;
        tmp[i]    |= ((res[idx--] >> 48) & 0xFFFFULL) << 16;

        tmp[i - 3] = res[idx] & MASK48;
        tmp[i]    |= ((res[idx--] >> 48) & 0xFFFFULL);
    }

    for(i = 0; i < 2; i++)
    {
        a[ZEN_N - 2 + i] = divmod769_tail(&tmp[102]);
    }

    idx = 0;
    for(i = 0; i < ZEN_N - 2; i += 5)
    {
        int j;

        for(j = 0; j < 5; j++)
        {
            a[i + j] = divmod769_u48(&tmp[idx]);
        }

        idx++;
    }
}

#define PACK147_GROUPS 102
#define PACK147_WORDS 58

static const uint64_t pack_ciphertext_table[] = 
{
    1, 147, 21609, 3176523, 466948881
};

static inline uint32_t div147_u24(uint32_t x, uint32_t *r)
{
    uint32_t q = ((uint64_t)x * 14608733u) >> 31;

    *r = x - q * 147u;
    return q;
}

static inline uint64_t div147_u64(uint64_t x, uint64_t *r)
{
    uint32_t r32 = 0;
    uint32_t q2, q1, q0;

    q2 = div147_u24((uint32_t)(x >> 32), &r32);
    q1 = div147_u24((r32 << 16) | ((uint32_t)(x >> 16) & 0xffffu), &r32);
    q0 = div147_u24((r32 << 16) | ((uint32_t)x & 0xffffu), &r32);

    *r = r32;
    return ((uint64_t)q2 << 32) | ((uint64_t)q1 << 16) | q0;
}

void poly_ciphertext_pack(uint8_t *pa, const int16_t *a)
{
    unsigned int i, idx, bitpos, wi, off;
    uint64_t x;
    uint64_t buf[PACK147_WORDS];

    memset(buf, 0, sizeof(buf));

    idx = 0;
    for (i = 0; i < ZEN_N - 2; i += 5)
    {
        x =
              (uint64_t)(uint16_t)a[i]
            + (uint64_t)(uint16_t)a[i + 1] * pack_ciphertext_table[1]
            + (uint64_t)(uint16_t)a[i + 2] * pack_ciphertext_table[2]
            + (uint64_t)(uint16_t)a[i + 3] * pack_ciphertext_table[3]
            + (uint64_t)(uint16_t)a[i + 4] * pack_ciphertext_table[4];

        bitpos = idx * 36u;
        wi = bitpos >> 6;
        off = bitpos & 63u;

        buf[wi] |= x << off;
        if (off > 28u)
        {
            buf[wi + 1u] |= x >> (64u - off);
        }

        idx++;
    }

    x =
          (uint64_t)(uint16_t)a[ZEN_N - 2]
        + (uint64_t)(uint16_t)a[ZEN_N - 1] * pack_ciphertext_table[1];

    bitpos = PACK147_GROUPS * 36u;
    wi = bitpos >> 6;
    off = bitpos & 63u;

    buf[wi] |= x << off;
    if (off > 49u)
    {
        buf[wi + 1u] |= x >> (64u - off);
    }

    memcpy(pa, (const uint8_t *)buf, ZEN_INDCPA_CIPHERTEXT_LEN_BYTES);
}

void poly_ciphertext_unpack(int16_t *a, const uint8_t *pa)
{
    unsigned int i, idx, bitpos, wi, off;
    uint64_t x, q, r;
    uint64_t buf[PACK147_WORDS];
    const uint64_t MASK36 = UINT64_C(0xFFFFFFFFF);
    const uint64_t MASK15 = UINT64_C(0x7FFF);

    memset(buf, 0, sizeof(buf));
    memcpy((uint8_t *)buf, pa, ZEN_INDCPA_CIPHERTEXT_LEN_BYTES);

    idx = 0;
    for (i = 0; i < ZEN_N - 2; i += 5)
    {
        bitpos = idx * 36u;
        wi = bitpos >> 6;
        off = bitpos & 63u;

        x = buf[wi] >> off;
        if (off > 28u)
        {
            x |= buf[wi + 1u] << (64u - off);
        }
        x &= MASK36;

        q = div147_u64(x, &r);
        a[i] = (int16_t)r;

        q = div147_u64(q, &r);
        a[i + 1] = (int16_t)r;

        q = div147_u64(q, &r);
        a[i + 2] = (int16_t)r;

        q = div147_u64(q, &r);
        a[i + 3] = (int16_t)r;

        q = div147_u64(q, &r);
        a[i + 4] = (int16_t)r;

        idx++;
    }

    bitpos = PACK147_GROUPS * 36u;
    wi = bitpos >> 6;
    off = bitpos & 63u;

    x = buf[wi] >> off;
    if (off > 49u)
    {
        x |= buf[wi + 1u] << (64u - off);
    }
    x &= MASK15;

    q = div147_u64(x, &r);
    a[ZEN_N - 2] = (int16_t)r;

    q = div147_u64(q, &r);
    a[ZEN_N - 1] = (int16_t)r;
}
