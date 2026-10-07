/**
 * flashcfg.h — tiny settings store in the last flash page
 *
 * The C0 programs flash in 64-bit doublewords and can only clear bits, so a
 * record is always erased-and-rewritten as a whole. The last 2 KB page is
 * reserved for this (the linker script stops 2 KB short of the end of flash so
 * code can never be placed here).
 *
 * Layout at FLASHCFG_ADDR:
 *   u32 magic | u32 version | u32 len | payload... | u32 checksum
 * A record whose magic, version, length or checksum does not match is treated
 * as absent, so a blank ("erased" = all ones) or half-written page is safe.
 */
#ifndef FLASHCFG_H
#define FLASHCFG_H

#include <stdint.h>

#define FLASHCFG_ADDR       0x0803F800u     /* last 2 KB page of 256 KB flash */
#define FLASHCFG_MAX_PAYLOAD 128u           /* bytes; must stay 8-byte aligned */

/* Write (erase + program) len bytes at the settings page. len must be a
 * multiple of 8 and <= FLASHCFG_MAX_PAYLOAD. Returns 0 on success. */
int flashcfg_write(const void *data, uint32_t len);

/* Copy the stored payload into out. Returns payload length, or -1 if the page
 * holds no valid record (blank page, bad magic, wrong length, bad checksum). */
int flashcfg_read(void *out, uint32_t max_len);

#endif /* FLASHCFG_H */
