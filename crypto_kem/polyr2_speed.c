#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "hal.h"
#include "sendfn.h"
#include "KEM_AlgorithmInstance.h"
#include "drng.h"
#include "poly.h"
#include "params.h"

/* The polynomial generators consume SEED_LEN_BYTES bytes. */
static const unsigned char speed_seed[SEED_LEN_BYTES] = {
    0x6e, 0x67, 0x63, 0x63, 0x6d, 0x34, 0x2d, 0x73,
    0x70, 0x65, 0x65, 0x64, 0x2d, 0x73, 0x65, 0x65, 0x64
};

static volatile uint32_t benchmark_sink;

static void fail_and_halt(const char *reason)
{
    hal_send_str(reason);
#ifdef MPS2_AN386
    __builtin_trap();
#endif
    while (1) {
    }
}

#if defined(__has_include)
#if __has_include("radix16_r2.h")
#include "radix16_r2.h"
#define ZENSPEED_HAVE_RADIX16 1
#endif
#endif

#ifndef ZENSPEED_HAVE_RADIX16
#define ZENSPEED_HAVE_RADIX16 0
#endif

#if ZEN_N != 512 && ZEN_N != 1024
#error "polyr2_speed supports only DAWN_Prime_128 and DAWN_Prime_256"
#endif

#if !ZENSPEED_HAVE_RADIX16

/*
 * Benchmark-only cyclic R2 multipliers for the FastInversion levels that
 * are inlined in the reference implementations and therefore have no
 * externally callable symbol of their own.
 */
#define DEFINE_MUL_IN_R2_SMALL(N, MASKN)                         \
    __attribute__((noinline))                                    \
    void mul_in_R2_##N(int16_t *a, int16_t *b, int16_t *res)     \
    {                                                            \
        unsigned int i;                                          \
        uint64_t B = 0;                                          \
        uint64_t R = 0;                                          \
        uint64_t mask;                                           \
        uint64_t wrap;                                           \
                                                                 \
        for (i = 0; i < (N); i++) {                              \
            B |= ((uint64_t)((uint16_t)b[i] & 1u)) << i;         \
        }                                                        \
        B &= (MASKN);                                            \
                                                                 \
        for (i = 0; i < (N); i++) {                              \
            mask = 0ULL - (uint64_t)((uint16_t)a[i] & 1u);       \
            R ^= B & mask;                                       \
            wrap = (B >> ((N) - 1)) & 1ULL;                      \
            B = ((B << 1) | wrap) & (MASKN);                     \
        }                                                        \
                                                                 \
        for (i = 0; i < (N); i++) {                              \
            res[i] = (int16_t)((R >> i) & 1ULL);                 \
        }                                                        \
    }

#define DEFINE_MUL_IN_R2_LARGE(N, WORDS)                         \
    __attribute__((noinline))                                    \
    void mul_in_R2_##N(int16_t *a, int16_t *b, int16_t *res)     \
    {                                                            \
        unsigned int i;                                          \
        unsigned int word;                                       \
        uint64_t B[WORDS] = {0};                                 \
        uint64_t R[WORDS] = {0};                                 \
        uint64_t U[WORDS];                                       \
        uint64_t mask;                                           \
        uint64_t wrap;                                           \
                                                                 \
        for (i = 0; i < (N); i++) {                              \
            B[i >> 6] |=                                         \
                ((uint64_t)((uint16_t)b[i] & 1u)) << (i & 63u);  \
        }                                                        \
                                                                 \
        for (i = 0; i < (N); i++) {                              \
            mask = 0ULL - (uint64_t)((uint16_t)a[i] & 1u);       \
            for (word = 0; word < (WORDS); word++) {             \
                R[word] ^= B[word] & mask;                        \
            }                                                    \
                                                                 \
            wrap = B[(WORDS) - 1u] >> 63;                        \
            U[0] = (B[0] << 1) | wrap;                           \
            for (word = 1; word < (WORDS); word++) {             \
                U[word] = (B[word] << 1) | (B[word - 1u] >> 63); \
            }                                                    \
            for (word = 0; word < (WORDS); word++) {             \
                B[word] = U[word];                               \
            }                                                    \
        }                                                        \
                                                                 \
        for (i = 0; i < (N); i++) {                              \
            res[i] = (int16_t)((R[i >> 6] >> (i & 63u)) & 1ULL);\
        }                                                        \
    }

DEFINE_MUL_IN_R2_SMALL(2, 0x0000000000000003ULL)
DEFINE_MUL_IN_R2_SMALL(4, 0x000000000000000FULL)
DEFINE_MUL_IN_R2_SMALL(8, 0x00000000000000FFULL)
DEFINE_MUL_IN_R2_SMALL(16, 0x000000000000FFFFULL)
DEFINE_MUL_IN_R2_SMALL(32, 0x00000000FFFFFFFFULL)
DEFINE_MUL_IN_R2_SMALL(64, UINT64_MAX)
DEFINE_MUL_IN_R2_LARGE(128, 2)

/* DAWN_Prime_128 already exports mul_in_R2_256 from ref/poly.c. */
#if ZEN_N == 1024
DEFINE_MUL_IN_R2_LARGE(256, 4)
#endif

#else

extern void r2_radix16_mul_2_asm(uint32_t *res, const uint32_t *a,
                                 const uint32_t *b);
extern void r2_radix16_mul_4_asm(uint32_t *res, const uint32_t *a,
                                 const uint32_t *b);
extern void r2_radix16_mul_8_asm(uint32_t *res, const uint32_t *a,
                                 const uint32_t *b);
extern void r2_radix16_mul_16_asm(uint32_t *res, const uint32_t *a,
                                  const uint32_t *b);
extern void r2_radix16_mul_32_asm(uint32_t *res, const uint32_t *a,
                                  const uint32_t *b);
extern void r2_radix16_mul_64_asm(uint32_t *res, const uint32_t *a,
                                  const uint32_t *b);
extern void r2_radix16_mul_128_asm(uint32_t *res, const uint32_t *a,
                                   const uint32_t *b);
extern void r2_radix16_mul_256_asm(uint32_t *res, const uint32_t *a,
                                   const uint32_t *b);
extern void r2_radix16_mul_512_asm(uint32_t *res, const uint32_t *a,
                                   const uint32_t *b);

#if ZEN_N == 512
extern void r2_radix16_mul_256x128_asm(uint32_t *res, const uint32_t *a,
                                       const uint32_t *b);
#else
extern void r2_radix16_mul_512x256_asm(uint32_t *res, const uint32_t *a,
                                       const uint32_t *b);
#endif

#endif

#define BENCHMARK_CALL(LABEL, CALL, RESULT_WORD)                     \
    do {                                                            \
        t0 = hal_get_time();                                        \
        CALL;                                                       \
        t1 = hal_get_time();                                        \
        benchmark_sink ^= (uint32_t)(RESULT_WORD);                  \
        send_unsignedll((LABEL), (unsigned long long)(t1 - t0));    \
    } while (0)

int main(void)
{
    uint64_t t0;
    uint64_t t1;
    unsigned int attempt;
    int32_t iteration;
    int16_t a[ZEN_N];
    int16_t b[ZEN_N];

#if ZENSPEED_HAVE_RADIX16
    uint32_t rad_a_2[R2_RADIX16_WORDS(2)];
    uint32_t rad_b_2[R2_RADIX16_WORDS(2)];
    uint32_t rad_a[R2_RADIX16_WORDS(ZEN_N2)];
    uint32_t rad_b[R2_RADIX16_WORDS(ZEN_N2)];
    uint32_t rad_res[R2_RADIX16_WORDS(ZEN_N2)];
    uint32_t inv_in[R2_RADIX16_WORDS(ZEN_N4)];
    uint32_t inv_res[R2_RADIX16_WORDS(ZEN_N4)];
#else
    int16_t res[ZEN_N2];
    int16_t inv_in[ZEN_N4];
    int16_t inv_res[ZEN_N4];
#endif

    hal_setup(CLOCK_BENCHMARK);
    hal_send_str("==========================");

    /* Prepare deterministic, valid inputs outside all timed regions. */
    for (attempt = 0; attempt < 256u; attempt++) {
#if !ZENSPEED_HAVE_RADIX16
        unsigned int i;
#endif

        poly_generate_f(a, speed_seed, (uint8_t)attempt);
#if ZENSPEED_HAVE_RADIX16
        if (poly_xor4_radix16(inv_in, a) == 0) {
            break;
        }
#else
        for (i = 0; i < ZEN_N4; i++) {
            inv_in[i] = (int16_t)(((uint16_t)a[i] & 1u)
                       ^ ((uint16_t)a[i + ZEN_N4] & 1u)
                       ^ ((uint16_t)a[i + 2u * ZEN_N4] & 1u)
                       ^ ((uint16_t)a[i + 3u * ZEN_N4] & 1u));
        }
        if (check_poly_inv_Z2(inv_in) == 0) {
            break;
        }
#endif
    }
    if (attempt == 256u) {
        fail_and_halt("ERROR: no invertible R2 benchmark input");
    }

    poly_generate_g(b, speed_seed, 0x80u);

#if ZENSPEED_HAVE_RADIX16
    r2_radix16_pack(rad_a_2, a, 2);
    r2_radix16_pack(rad_b_2, b, 2);
    r2_radix16_pack(rad_a, a, ZEN_N2);
    r2_radix16_pack(rad_b, b, ZEN_N2);
#endif

    for (iteration = 0; iteration < NGCC_ITERATIONS; iteration++) {
#if ZENSPEED_HAVE_RADIX16
        BENCHMARK_CALL("r2_radix16_mul 2 cycles:",
                       r2_radix16_mul_2_asm(rad_res, rad_a_2, rad_b_2),
                       rad_res[0]);
        BENCHMARK_CALL("r2_radix16_mul 4 cycles:",
                       r2_radix16_mul_4_asm(rad_res, rad_a, rad_b),
                       rad_res[0]);
        BENCHMARK_CALL("r2_radix16_mul 8 cycles:",
                       r2_radix16_mul_8_asm(rad_res, rad_a, rad_b),
                       rad_res[0]);
        BENCHMARK_CALL("r2_radix16_mul 16 cycles:",
                       r2_radix16_mul_16_asm(rad_res, rad_a, rad_b),
                       rad_res[0]);
        BENCHMARK_CALL("r2_radix16_mul 32 cycles:",
                       r2_radix16_mul_32_asm(rad_res, rad_a, rad_b),
                       rad_res[0]);
        BENCHMARK_CALL("r2_radix16_mul 64 cycles:",
                       r2_radix16_mul_64_asm(rad_res, rad_a, rad_b),
                       rad_res[0]);
        BENCHMARK_CALL("r2_radix16_mul 128 cycles:",
                       r2_radix16_mul_128_asm(rad_res, rad_a, rad_b),
                       rad_res[0]);
        BENCHMARK_CALL("r2_radix16_mul 256 cycles:",
                       r2_radix16_mul_256_asm(rad_res, rad_a, rad_b),
                       rad_res[0]);

#if ZEN_N == 1024
        BENCHMARK_CALL("r2_radix16_mul 512 cycles:",
                       r2_radix16_mul_512_asm(rad_res, rad_a, rad_b),
                       rad_res[0]);
        BENCHMARK_CALL("r2_radix16_mul 512x256 cycles:",
                       r2_radix16_mul_512x256_asm(rad_res, rad_a, rad_b),
                       rad_res[0]);
#else
        BENCHMARK_CALL("r2_radix16_mul 256x128 cycles:",
                       r2_radix16_mul_256x128_asm(rad_res, rad_a, rad_b),
                       rad_res[0]);
#endif

        BENCHMARK_CALL("FastInversion cycles:",
                       FastInversion(inv_res, inv_in), inv_res[0]);
#else
        BENCHMARK_CALL("mul_in_R2_2 cycles:",
                       mul_in_R2_2(a, b, res), res[0]);
        BENCHMARK_CALL("mul_in_R2_4 cycles:",
                       mul_in_R2_4(a, b, res), res[0]);
        BENCHMARK_CALL("mul_in_R2_8 cycles:",
                       mul_in_R2_8(a, b, res), res[0]);
        BENCHMARK_CALL("mul_in_R2_16 cycles:",
                       mul_in_R2_16(a, b, res), res[0]);
        BENCHMARK_CALL("mul_in_R2_32 cycles:",
                       mul_in_R2_32(a, b, res), res[0]);
        BENCHMARK_CALL("mul_in_R2_64 cycles:",
                       mul_in_R2_64(a, b, res), res[0]);
        BENCHMARK_CALL("mul_in_R2_128 cycles:",
                       mul_in_R2_128(a, b, res), res[0]);
        BENCHMARK_CALL("mul_in_R2_256 cycles:",
                       mul_in_R2_256(a, b, res), res[0]);

#if ZEN_N == 1024
        BENCHMARK_CALL("mul_in_R2_512 cycles:",
                       mul_in_R2_512(a, b, res), res[0]);
#endif

        BENCHMARK_CALL("FastInversion cycles:",
                       FastInversion(inv_res, inv_in), inv_res[0]);
#endif

        hal_send_str("+");
    }

    hal_send_str("#");
    return 0;
}
