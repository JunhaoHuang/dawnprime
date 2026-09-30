#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "hal.h"
#include "sendfn.h"
#include "KEM_AlgorithmInstance.h"
#include "drng.h"
#include "poly.h"
#include "params.h"
#include "ntt.h"
static const unsigned char speed_seed[] = {
    0x6e, 0x67, 0x63, 0x63, 0x6d, 0x34, 0x2d, 0x73,
    0x70, 0x65, 0x65, 0x64, 0x2d, 0x73, 0x65, 0x65, 0x64
};


int main(void) {
    uint64_t t0;
    uint64_t t1;
	int32_t i,nonce = 0;
    int16_t a[ZEN_N], b[ZEN_N], res[ZEN_N];

    hal_setup(CLOCK_BENCHMARK);
    hal_send_str("==========================");


    for (i = 0; i < NGCC_ITERATIONS; i++) {
        t0= hal_get_time();
        poly_generate_f(a, speed_seed, nonce++);
        t1 = hal_get_time();
        send_unsignedll("poly_generate_f cycles:", (unsigned long long)(t1 - t0));

        t0 = hal_get_time();
        poly_generate_se(b, speed_seed, nonce++);
        t1 = hal_get_time();
        send_unsignedll("poly_generate_se cycles:", (unsigned long long)(t1 - t0));

        t0 = hal_get_time();
        poly_ntt(a);
        t1 = hal_get_time();
        send_unsignedll("poly_ntt cycles:", (unsigned long long)(t1 - t0));

        poly_ntt(b);

        t0 = hal_get_time();
        poly_basemul_ntt(res,a,b);
        t1 = hal_get_time();
        send_unsignedll("poly_basemul_ntt cycles:", (unsigned long long)(t1 - t0));

        t0 = hal_get_time();
        poly_baseinv_ntt(res, a);
        t1 = hal_get_time();
        send_unsignedll("poly_baseinv_ntt cycles:", (unsigned long long)(t1 - t0));

        t0 = hal_get_time();
        poly_intt(res);
        t1 = hal_get_time();
        send_unsignedll("poly_intt cycles:", (unsigned long long)(t1 - t0));

        t0 = hal_get_time();
        poly_compress(res);
        t1 = hal_get_time();
        send_unsignedll("poly_compress cycles:", (unsigned long long)(t1 - t0));

        t0= hal_get_time();
        poly_decompress(res);
        t1 = hal_get_time();
        send_unsignedll("poly_decompress cycles:", (unsigned long long)(t1 - t0));
        hal_send_str("+");
    }

    hal_send_str("#");
    return 0;
}
