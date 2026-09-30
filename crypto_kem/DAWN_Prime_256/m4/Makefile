CC = gcc
CFLAGS += -std=c99 -Wpedantic -Wall -Wextra -O2

HEADERS = sample.h ntt.h poly.h symmetric.h pke.h KEM_AlgorithmInstance.h
SOURCES = sample.c ntt.c poly.c symmetric.c pke.c KEM_AlgorithmInstance.c
KAT_KEM_SOURCES = $(SOURCES) KAT_KEM.c
SPEED_KEM_SOURCES = $(SOURCES) cpucycles.c SPEED_KEM.c 


KAT_KEM: $(HEADERS) $(KAT_KEM_SOURCES)
	$(CC) $(CFLAGS) -o $@ $(KAT_KEM_SOURCES)

SPEED_KEM: $(HEADERS) $(SPEED_KEM_SOURCES)
	$(CC) $(CFLAGS) -o $@ $(SPEED_KEM_SOURCES)

.PHONY: clean
clean:
	-rm KAT_KEM SPEED_KEM

