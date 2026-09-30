/*
Copyright (c) 2026 Yu Zhang.
Organization: State Key Laboratory of Cyberspace Security Defense,Institute of Information Engineering, CAS
              School of Cyber Security, University of Chinese Academy of Sciences  
File Description: Declares the DAWNP key-encapsulation mechanism layer for the optimized DAWNP-128 instance.
*/
#ifndef PARAMS_H
#define PARAMS_H

#define SEED_LEN_BYTES 64
#define DAWNP_N 512
#define DAWNP_N_LEN_BYTES DAWNP_N/8
#define DAWNP_N2 DAWNP_N/2
#define DAWNP_N4 DAWNP_N/4
#define DAWNP_N4_LOG2 7
#define DAWNP_Q 769
#define DAWNP_Q2 384

#define DAWNP_SYM_LEN_BYTES 16 /* size in bytes of hashes*/
#define DAWNP_SHAREDKEY_LEN_BYTES 16 /* size in bytes of shared key */
#define DAWNP_F_NTT_PACK 640
#define DAWNP_F2_PACK 16

#define DAWNP_INDCPA_MSG_LEN_BYTES 16
#define DAWNP_INDCPA_PUBLICKEY_LEN_BYTES 615
#define DAWNP_INDCPA_SECREKEY_LEN_BYTES DAWNP_F_NTT_PACK+DAWNP_F2_PACK
#define DAWNP_INDCPA_CIPHERTEXT_LEN_BYTES 461

#define DAWNP_PUBLICKEY_LEN_BYTES DAWNP_INDCPA_PUBLICKEY_LEN_BYTES
#define DAWNP_SECREKEY_LEN_BYTES DAWNP_INDCPA_SECREKEY_LEN_BYTES+DAWNP_INDCPA_PUBLICKEY_LEN_BYTES+DAWNP_SYM_LEN_BYTES+DAWNP_SHAREDKEY_LEN_BYTES
#define DAWNP_CIPHERTEXT_LEN_BYTES DAWNP_INDCPA_CIPHERTEXT_LEN_BYTES

#endif