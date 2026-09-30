#include <string.h>
#include <stdint.h>
#include <stdlib.h>

#include "hal.h"
#include "sendfn.h"
#include "KEM_AlgorithmInstance.h"
#if defined(__has_include)
#if __has_include("parameters.h")
#include "parameters.h"
#endif
#if __has_include("ntt.h")
#include "ntt.h"
#endif
#endif
#include "randombytes.h"

static int test_roundtrip(void) {
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

    if (pk == NULL || sk == NULL || ct == NULL || ss_a == NULL || ss_b == NULL) {
        return -1;
    }
    if (kem_keygen(pk, &ignored_len, sk, &ignored_len) != 0) {
        return -1;
    }
    if (kem_enc(pk, pk_len, ss_a, &ignored_len, ct, &ignored_len) != 0) {
        return -1;
    }
    if (kem_dec(sk, sk_len, ct, ct_len, ss_b, &ignored_len) != 0) {
        return -1;
    }
    int ret = memcmp(ss_a, ss_b, ss_len);

    free(pk);
    free(sk);
    free(ct);
    free(ss_a);
    free(ss_b);
    return ret;
}

int main(void) {
    int i;

    hal_setup(CLOCK_FAST);
    hal_send_str("==========================");


    for (i = 0; i < NGCC_ITERATIONS; i++) {
        if (test_roundtrip() != 0) {
            hal_send_str("ERROR KEYS");
            return -1;
        }
        else{
            hal_send_str("OK KEYS");
        }        
        hal_send_str("+");
    }

    hal_send_str("#");
    return 0;
}
