#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "hal.h"
#include "KEM_AlgorithmInstance.h"
#include "randombytes.h"
#define SEED_LEN_BYTES 64

static void printbytes(const unsigned char *x, unsigned long long xlen) {
    static const char hex[] = "0123456789abcdef";
    char *outs = malloc((size_t)(2 * xlen + 1));
    unsigned long long i;

    if (outs == NULL) {
        hal_send_str("alloc_failed");
        return;
    }
    for (i = 0; i < xlen; i++) {
        outs[2 * i] = hex[(x[i] >> 4) & 0xF];
        outs[2 * i + 1] = hex[x[i] & 0xF];
    }
    outs[2 * xlen] = 0;
    hal_send_str(outs);
    free(outs);
}


int main(void) {
    unsigned long long pk_len = kem_get_pk_len_bytes();
    unsigned long long sk_len = kem_get_sk_len_bytes();
    unsigned long long ss_len = kem_get_ss_len_bytes();
    unsigned long long ct_len = kem_get_ct_len_bytes();
    unsigned long long ignored_len = 0;
    unsigned char *pk = malloc(pk_len);
    unsigned char *sk = malloc(sk_len);
    unsigned char *ct = malloc(ct_len);
    unsigned char *ss_a = malloc(ss_len);
    unsigned char *ss_b = malloc(ss_len);
    unsigned char seed[SEED_LEN_BYTES];
    int i;

    hal_setup(CLOCK_FAST);
    hal_send_str("==========================");
    if (pk == NULL || sk == NULL || ct == NULL || ss_a == NULL || ss_b == NULL) {
        hal_send_str("alloc_failed");
        return -1;
    }

    for (i = 0; i < ITERATIONS; i++) {
        randombytes(seed, SEED_LEN_BYTES);
        printbytes(seed, SEED_LEN_BYTES);

        kem_keygen(pk, &ignored_len, sk, &ignored_len);
        kem_enc(pk, pk_len, ss_a, &ignored_len, ct, &ignored_len);
        kem_dec(sk, sk_len, ct, ct_len, ss_b, &ignored_len);
        if (memcmp(ss_a, ss_b, ss_len) != 0) {
            hal_send_str("ERROR");
            // hal_send_str("#");
            // return -1;
        }

        printbytes(pk, pk_len);
        printbytes(sk, sk_len);
        printbytes(ct, ct_len);
        printbytes(ss_a, ss_len);
        printbytes(ss_b, ss_len);
        hal_send_str("+");
    }

    hal_send_str("#");
    free(pk);
    free(sk);
    free(ct);
    free(ss_a);
    free(ss_b);

    return 0;
}
