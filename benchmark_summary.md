## crypto_kem
**speed**

| scheme | implementation | metric | count | average | median | min | max |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| DAWN_Prime_128 | m4 | keypair | 100 | 303,318 | 300,984 | 262,089 | 456,564 |
| DAWN_Prime_128 | m4 | encaps | 100 | 153,125 | 153,124 | 153,123 | 153,164 |
| DAWN_Prime_128 | m4 | decaps | 100 | 288,173 | 288,173 | 288,173 | 288,211 |
| DAWN_Prime_128 | ref | keypair | 100 | 594,002 | 588,807 | 548,854 | 1,188,102 |
| DAWN_Prime_128 | ref | encaps | 100 | 273,453 | 273,453 | 273,452 | 273,491 |
| DAWN_Prime_128 | ref | decaps | 100 | 570,266 | 570,265 | 570,265 | 570,306 |
| DAWN_Prime_256 | m4 | keypair | 100 | 630,972 | 569,236 | 569,236 | 935,979 |
| DAWN_Prime_256 | m4 | encaps | 100 | 287,574 | 287,573 | 287,573 | 287,612 |
| DAWN_Prime_256 | m4 | decaps | 100 | 557,117 | 557,116 | 557,116 | 557,155 |
| DAWN_Prime_256 | ref | keypair | 100 | 1,275,254 | 1,239,983 | 1,208,457 | 1,901,611 |
| DAWN_Prime_256 | ref | encaps | 100 | 612,826 | 612,826 | 612,825 | 612,863 |
| DAWN_Prime_256 | ref | decaps | 100 | 1,413,137 | 1,413,134 | 1,413,134 | 1,413,173 |

**code size (speed)**

| scheme | implementation | .text | .data | .bss | total |
| --- | --- | ---: | ---: | ---: | ---: |
| DAWN_Prime_128 | m4 | 52,476 | 1,352 | 380 | 54,208 |
| DAWN_Prime_128 | ref | 34,428 | 1,352 | 380 | 36,160 |
| DAWN_Prime_256 | m4 | 60,412 | 1,352 | 380 | 62,144 |
| DAWN_Prime_256 | ref | 41,616 | 1,352 | 380 | 43,348 |
