#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "hal.h"
#include "sendfn.h"
#include "KEM_AlgorithmInstance.h"

#include "randombytes.h"
unsigned long long hash_cycles;
unsigned long long func_cycles;

static void fail_and_halt(const char *reason) {
    hal_send_str(reason);
#ifdef MPS2_AN386
    __builtin_trap();
#endif
    while (1) {
    }
}

int main(void) {
    unsigned long long pk_len = kem_get_pk_len_bytes();
    unsigned long long sk_len = kem_get_sk_len_bytes();
    unsigned long long ss_len = kem_get_ss_len_bytes();
    unsigned long long ct_len = kem_get_ct_len_bytes();
    unsigned long long ignored_len = 0;
    uint64_t t0;
    uint64_t t1;
    unsigned char *pk;
    unsigned char *sk;
    unsigned char *ct;
    unsigned char *ss_a;
    unsigned char *ss_b;

    hal_setup(CLOCK_BENCHMARK);
    hal_send_str("==========================");


    pk = malloc(pk_len);
    sk = malloc(sk_len);
    ct = malloc(ct_len);
    ss_a = malloc(ss_len);
    ss_b = malloc(ss_len);
    if (pk == NULL || sk == NULL || ct == NULL || ss_a == NULL || ss_b == NULL) {
        fail_and_halt("alloc_failed");
    }
    for(int i=0;i<ITERATIONS;i++){
        hash_cycles = 0;
        func_cycles = 0;
        t0 = hal_get_time();
        if (kem_keygen(pk, &ignored_len, sk, &ignored_len) != 0) fail_and_halt("kem_keygen_failed");
        t1 = hal_get_time();
        send_unsignedll("keypair cycles:", (unsigned long long)(t1 - t0));
        send_unsignedll("keypair hash cycles:", hash_cycles);
        send_unsignedll("keypair func cycles:", func_cycles);

        hash_cycles = 0;
        func_cycles = 0;
        t0 = hal_get_time();
        if (kem_enc(pk, pk_len, ss_a, &ignored_len, ct, &ignored_len) != 0) fail_and_halt("kem_enc_failed");
        t1 = hal_get_time();
        send_unsignedll("encaps cycles:", (unsigned long long)(t1 - t0));
        send_unsignedll("encaps hash cycles:", hash_cycles);
        send_unsignedll("encaps func cycles:", func_cycles);

        hash_cycles = 0;
        func_cycles = 0;
        t0 = hal_get_time();
        if (kem_dec(sk, sk_len, ct, ct_len, ss_b, &ignored_len) != 0) fail_and_halt("kem_dec_failed");
        t1 = hal_get_time();
        send_unsignedll("decaps cycles:", (unsigned long long)(t1 - t0));
        send_unsignedll("decaps hash cycles:", hash_cycles);
        send_unsignedll("decaps func cycles:", func_cycles);
        
        if (memcmp(ss_a, ss_b, ss_len) != 0) {
            fail_and_halt("ERROR KEYS");
        }

        hal_send_str("OK KEYS");
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
