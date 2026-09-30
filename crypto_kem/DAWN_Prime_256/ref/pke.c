/*
Copyright (c) 2026 Yu Zhang.
Organization: State Key Laboratory of Cyberspace Security Defense,Institute of Information Engineering, CAS
              School of Cyber Security, University of Chinese Academy of Sciences  
File Description: Declares the DAWNP key-encapsulation mechanism layer for the optimized DAWNP-256 instance.
*/
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include "params.h"
#include "sample.h"
#include "ntt.h"
#include "poly.h"
#include "randombytes.h"


void pke_keygen_derand(unsigned char *pk, unsigned char *sk, const unsigned char *seed)
{
    unsigned i;
    uint8_t nonce;
    int16_t f[DAWNP_N], g[DAWNP_N], f2[DAWNP_N4];
    int16_t t0[DAWNP_N], t1[DAWNP_N];

    nonce = 0;
    //generate f
    poly_generate_f(f, seed, nonce++);
    //chechk f
    for(;;)
    {
        for(i = 0; i < DAWNP_N4; i++)
        {
            t0[i] = (f[i] & 1) ^ (f[i + DAWNP_N4] & 1) ^ (f[i + 2*DAWNP_N4] & 1) ^ (f[i + 3*DAWNP_N4] & 1); //t0 = f mod (x^(n/4)+1)
        }
        if(check_poly_inv_Z2(t0))
        {
            poly_generate_f(f, seed, nonce++);
            continue;
        }
        poly_ntt_mq(f);
        if(check_poly_inv_Zq(f))
        {
            poly_generate_f(f, seed, nonce++);
            continue;
        }

        poly_baseinv_ntt(t1, f); //t1 = f^(-1) mod (x^n+1, q)
        FastInversion(f2, t0); //t0 = f2
 
        break;
    }

    //generate g
    poly_generate_g(g, seed, nonce++);
    //check g
    for(;;)
    {
        poly_ntt_mq(g);
        if(check_poly_inv_Zq(g))
        {
            poly_generate_g(g, seed, nonce++);
            continue;
        }
        break;
    }

    poly_basemul_ntt_mq(t0, g, t1);
    poly_publickey_pack(pk, t0);
    poly_secretkey_pack(sk, f);
    poly_bit2byte_pack(sk+DAWNP_F_NTT_PACK, f2, DAWNP_N4);

}

void pke_keygen(unsigned char *pk, unsigned char *sk)
{
    uint8_t seed[SEED_LEN_BYTES];

    randombytes(seed, SEED_LEN_BYTES);
    pke_keygen_derand(pk, sk, seed);

}

void pke_enc(unsigned char *pk, unsigned char *m, unsigned char *seed, unsigned char *ct)
{
    unsigned i;
    uint8_t nonce;
    int16_t h[DAWNP_N], s[DAWNP_N], e[DAWNP_N];
    int16_t t0[DAWNP_N], t1[DAWNP_N];

    poly_publickey_unpack(h, pk);

    nonce = 0;
    poly_generate_se(s, seed, nonce++);
    poly_generate_se(e, seed, nonce++);

    poly_byte2bit_unpack(t0, m, DAWNP_N4);

    for(i = 0; i < DAWNP_N4; i++)
    {
        t1[i] = t1[i + DAWNP_N4] = t1[i + 2*DAWNP_N4] = t1[i + 3*DAWNP_N4] = t0[i] * ((DAWNP_Q+1)/2);
    }

    poly_ntt(s);
    poly_basemul_ntt(t0, h, s);
    poly_intt(t0);

    for(i = 0; i < DAWNP_N; i++)
    {
        t1[i] = montgomery_reduce((t0[i] + e[i] + t1[i]) * MONT);
        t1[i] += (t1[i] >> 15) & DAWNP_Q;
    }

    poly_compress(t1);
    poly_ciphertext_pack(ct, t1);

}

void pke_dec(unsigned char *sk, unsigned char *ct, unsigned char *m)
{
    unsigned int i, idx, mask;
    int16_t c0, c1, c2, c3;
    int16_t f[DAWNP_N], f2[DAWNP_N2] = {0}, mp0[DAWNP_N2], mp1[DAWNP_N2];
    int16_t t0[DAWNP_N], t1[DAWNP_N], t2[DAWNP_N2];

    poly_secretkey_unpack(f, sk); 
    poly_byte2bit_unpack(f2, sk+DAWNP_F_NTT_PACK, DAWNP_N4);
    poly_ciphertext_unpack(t0, ct);
    poly_decompress(t0);

    // cf mod <q, x^n+1>
    poly_ntt(t0);
    poly_basemul_ntt(t1, t0, f);
    poly_intt(t1);

    // (x^(n/2)+1)cf mod <q, x^n+1>
    for(i = 0; i < DAWNP_N2; i++)
    {
        t0[i] = montgomery_reduce((t1[i + DAWNP_N2] - t1[i]) * MONT);
    }

    for(i = DAWNP_N2; i < DAWNP_N; i++)
    {
        t0[i] = montgomery_reduce((t1[i - DAWNP_N2] + t1[i]) * MONT);
    }

    // a mod <2, x^(n/2)+1>
    for(i = 0; i < DAWNP_N2; i++)
    {
        t1[i] = (t0[i] & 1) ^ (t0[i + DAWNP_N2] & 1);
    }

    // m_prim = af2 mod <2, x^(n/2)+1>
    memset(f2 + DAWNP_N4, 0, DAWNP_N4 * sizeof(int16_t));
    mul_in_R2_512(t1, f2, mp0);

    //SimpleDecoding
    for(i = 0; i < DAWNP_N4; i++)
    {
        t1[i] = (t0[i] & 1) ^ (t0[i + DAWNP_N4] & 1) ^ (t0[i + 2*DAWNP_N4] & 1) ^ (t0[i + 3*DAWNP_N4] & 1);
    }
    
    memset(t2, 0, DAWNP_N2 * sizeof(int16_t));
    for(i = 0; i < DAWNP_N4; i++)
    {
        c0 = t0[i];
        c1 = t0[i + DAWNP_N4];
        c2 = t0[i + 2*DAWNP_N4];
        c3 = t0[i + 3*DAWNP_N4];

        mask = (c0 >= 0);
        c0 = ((DAWNP_Q2 - c0) & (-mask)) | ((DAWNP_Q2 + c0) & (~(-mask)));
        mask = (c1 >= 0);
        c1 = ((DAWNP_Q2 - c1) & (-mask)) | ((DAWNP_Q2 + c1) & (~(-mask)));
        mask = (c2 >= 0);
        c2 = ((DAWNP_Q2 - c2) & (-mask)) | ((DAWNP_Q2 + c2) & (~(-mask)));
        mask = (c3 >= 0);
        c3 = ((DAWNP_Q2 - c3) & (-mask)) | ((DAWNP_Q2 + c3) & (~(-mask)));

        mask = (c0 <= c2);
        c0 = (c0 & (-mask)) | (c2 & (~(-mask)));
        mask = (c1 <= c3);
        c1 = (c1 & (-mask)) | (c3 & (~(-mask)));
        mask = (c0 <= c1);
        idx = (i & (-mask)) | ((i + DAWNP_N4) & (~(-mask)));
        t2[idx] = t1[i] & 1;
    }
    mul_in_R2_512(t2, f2, t1);

    for(i = 0; i < DAWNP_N4; i++)
    {
        mp1[i] = mp0[i] ^ t1[i];
    }

    poly_bit2byte_pack(m, mp1, DAWNP_N4);
    
}
