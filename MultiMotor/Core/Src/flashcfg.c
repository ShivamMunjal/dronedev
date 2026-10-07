/**
 * flashcfg.c — settings store in the last flash page (see flashcfg.h)
 *
 * Programmed on a NUCLEO-C092RC: STM32C0 flash is written in 64-bit
 * doublewords and a bit can only go 1 -> 0, so every save erases the page
 * first. All operations are timeout-bounded: a wedged flash controller must
 * never hang the control loop that is calling us.
 */
#include "flashcfg.h"
#include "stm32c0xx.h"

#define CFG_MAGIC     0x47464346u    /* "FCFG" */
#define CFG_VERSION   1u
#define HDR_SIZE      16u            /* magic, version, len, checksum = 2 dwords */
#define PAGE_SIZE     2048u

#define SR_CLEARABLE  (FLASH_SR_EOP_Msk | FLASH_SR_PROGERR_Msk | FLASH_SR_WRPERR_Msk | \
                       FLASH_SR_PGAERR_Msk | FLASH_SR_SIZERR_Msk | FLASH_SR_PGSERR_Msk | \
                       FLASH_SR_MISERR_Msk | FLASH_SR_FASTERR_Msk | FLASH_SR_OPTVERR_Msk)

/* A stale option-byte flag shows up in SR and is not our error to report. */
#define SR_ERRORS     (FLASH_SR_PROGERR_Msk | FLASH_SR_WRPERR_Msk | FLASH_SR_PGAERR_Msk | \
                       FLASH_SR_SIZERR_Msk | FLASH_SR_PGSERR_Msk | FLASH_SR_MISERR_Msk | \
                       FLASH_SR_FASTERR_Msk)

/* Payload copy, word aligned by construction: the caller's struct may be
 * packed or odd-sized, and Cortex-M0+ cannot do unaligned word loads. */
static uint32_t s_buf[FLASHCFG_MAX_PAYLOAD / 4];

static uint32_t fnv1a(const uint8_t *p, uint32_t n)
{
    uint32_t h = 2166136261u;
    while (n--) { h ^= *p++; h *= 16777619u; }
    return h;
}

/* Wait for the controller to go idle. Returns 0 on success, -1 on timeout. */
static int flash_wait(void)
{
    uint32_t spin = 0;
    while (FLASH->SR & FLASH_SR_BSY1_Msk) {
        if (++spin > 2000000u) return -1;    /* ~100 ms at 48 MHz */
    }
    return 0;
}

int flashcfg_read(void *out, uint32_t max_len)
{
    const uint32_t *page = (const uint32_t *)FLASHCFG_ADDR;
    uint32_t magic = page[0], version = page[1], len = page[2], sum = page[3];

    if (magic != CFG_MAGIC || version != CFG_VERSION) return -1;
    if (len == 0 || len > FLASHCFG_MAX_PAYLOAD || len > max_len) return -1;
    if (len & 7u) return -1;

    const uint8_t *payload = (const uint8_t *)(FLASHCFG_ADDR + HDR_SIZE);
    if (fnv1a(payload, len) != sum) return -1;

    uint8_t *dst = (uint8_t *)out;
    for (uint32_t i = 0; i < len; i++) dst[i] = payload[i];
    return (int)len;
}

int flashcfg_write(const void *data, uint32_t len)
{
    if (len == 0 || len > FLASHCFG_MAX_PAYLOAD || (len & 7u)) return -1;

    const uint8_t *src = (const uint8_t *)data;
    uint8_t *buf = (uint8_t *)s_buf;
    for (uint32_t i = 0; i < len; i++) buf[i] = src[i];

    uint32_t hdr[4];
    hdr[0] = CFG_MAGIC;
    hdr[1] = CFG_VERSION;
    hdr[2] = len;
    hdr[3] = fnv1a(buf, len);

    if (FLASH->CR & FLASH_CR_LOCK_Msk) {
        FLASH->KEYR = 0x45670123u;
        FLASH->KEYR = 0xCDEF89ABu;
    }
    if (FLASH->CR & FLASH_CR_LOCK_Msk) return -2;      /* unlock failed */

    FLASH->SR = SR_CLEARABLE;

    /* ── page erase ─────────────────────────────────────────────── */
    uint32_t page_no = (FLASHCFG_ADDR - FLASH_BASE) / PAGE_SIZE;
    FLASH->CR = (FLASH->CR & ~FLASH_CR_PNB_Msk) | (page_no << FLASH_CR_PNB_Pos) | FLASH_CR_PER_Msk;
    FLASH->CR |= FLASH_CR_STRT_Msk;
    int err = flash_wait();
    FLASH->CR &= ~FLASH_CR_PER_Msk;
    if (err || (FLASH->SR & SR_ERRORS)) { FLASH->CR |= FLASH_CR_LOCK_Msk; return -3; }

    /* ── program ─────────────────────────────────────────────────
     * The header is 16 bytes and the payload length is a multiple of 8, so a
     * doubleword never straddles the header/payload boundary and the two
     * halves can be selected from the offset alone. */
    FLASH->CR |= FLASH_CR_PG_Msk;

    uint32_t total = HDR_SIZE + len;
    for (uint32_t off = 0; off < total; off += 8) {
        uint32_t d0, d1;
        if (off < HDR_SIZE) {
            d0 = hdr[off / 4];
            d1 = hdr[off / 4 + 1];
        } else {
            const uint32_t *pw = (const uint32_t *)(buf + off - HDR_SIZE);
            d0 = pw[0];
            d1 = pw[1];
        }

        __IO uint32_t *dst = (__IO uint32_t *)(FLASHCFG_ADDR + off);
        dst[0] = d0;
        dst[1] = d1;                     /* the second store starts programming */

        if (flash_wait() || (FLASH->SR & SR_ERRORS)) {
            FLASH->CR &= ~FLASH_CR_PG_Msk;
            FLASH->CR |= FLASH_CR_LOCK_Msk;
            return -4;
        }
    }

    FLASH->CR &= ~FLASH_CR_PG_Msk;
    FLASH->CR |= FLASH_CR_LOCK_Msk;
    FLASH->SR = SR_CLEARABLE;

    /* ── verify exactly as the loader will read it ───────────────── */
    const uint8_t *rb = (const uint8_t *)(FLASHCFG_ADDR + HDR_SIZE);
    for (uint32_t i = 0; i < len; i++) {
        if (rb[i] != buf[i]) return -5;
    }
    uint32_t magic_rb = *(const uint32_t *)FLASHCFG_ADDR;
    uint32_t sum_rb   = *(const uint32_t *)(FLASHCFG_ADDR + 12);
    if (magic_rb != CFG_MAGIC || sum_rb != hdr[3]) return -6;
    return 0;
}
