/* tc_compat.c -- Turbo C 2.0 text-mode conio for OpenWatcom (16-bit DOS).
 *
 * Writes through the VGA text buffer at B800:0000 (fast, exact attributes),
 * uses INT 10h for scroll/clear/mode, the PIT for the speaker, and keeps the
 * window/cursor state the way Turbo C exposes it. Only used by TINY.
 */
#include <i86.h>
#include <stdarg.h>
#include <stdio.h>

#include "tc_compat.h"

/* Watcom declares inp/outp in conio.h; we avoid pulling conio.h in here. */
extern unsigned inp(unsigned port);
extern unsigned outp(unsigned port, unsigned value);

#define VID_SEG 0xB800u

static unsigned char __far *scr = (unsigned char __far *)MK_FP(VID_SEG, 0);
static unsigned char attr = 0x07;
static int wx1 = 1, wy1 = 1, wx2 = 80, wy2 = 25;
static int cx = 1, cy = 1;
static int mode = C80;

static void cursor(void)
{
    union REGS r;
    r.h.ah = 2;
    r.h.bh = 0;
    r.h.dh = (unsigned char)(cy - 1);
    r.h.dl = (unsigned char)(cx - 1);
    int86(0x10, &r, &r);
}

static void scroll_up(void)
{
    union REGS r;
    r.h.ah = 6;
    r.h.al = 1;
    r.h.bh = attr;
    r.h.ch = (unsigned char)(wy1 - 1);
    r.h.cl = (unsigned char)(wx1 - 1);
    r.h.dh = (unsigned char)(wy2 - 1);
    r.h.dl = (unsigned char)(wx2 - 1);
    int86(0x10, &r, &r);
}

/* Turbo C coordinates are WINDOW-relative; the app relies on that
   (chat_win sets a window and works in window coordinates). */
void gotoxy(int x, int y)
{
    cx = wx1 + x - 1;
    cy = wy1 + y - 1;
    cursor();
}

int wherex(void) { return cx - wx1 + 1; }
int wherey(void) { return cy - wy1 + 1; }

int putch(int c)
{
    unsigned off;
    if (c == '\n') {
        cx = wx1;
        cy++;
    } else if (c == '\r') {
        cx = wx1;
    } else if (c == '\b') {
        if (cx > wx1) cx--;
    } else {
        off = (unsigned)(((cy - 1) * 80 + (cx - 1)) * 2);
        scr[off] = (unsigned char)c;
        scr[off + 1] = attr;
        cx++;
        if (cx > wx2) { cx = wx1; cy++; }
    }
    if (cy > wy2) {
        scroll_up();
        cy = wy2;
    }
    cursor();
    return c;
}

int cputs(const char *s)
{
    while (*s)
        putch((unsigned char)*s++);
    return 0;
}

int cprintf(const char *fmt, ...)
{
    char buf[512];
    va_list ap;
    int n;
    va_start(ap, fmt);
    n = vsprintf(buf, fmt, ap);
    va_end(ap);
    cputs(buf);
    return n;
}

void clrscr(void)
{
    union REGS r;
    r.h.ah = 6;
    r.h.al = 0;
    r.h.bh = attr;
    r.h.ch = (unsigned char)(wy1 - 1);
    r.h.cl = (unsigned char)(wx1 - 1);
    r.h.dh = (unsigned char)(wy2 - 1);
    r.h.dl = (unsigned char)(wx2 - 1);
    int86(0x10, &r, &r);
    cx = wx1;
    cy = wy1;
    cursor();
}

void window(int x1, int y1, int x2, int y2)
{
    wx1 = x1; wy1 = y1; wx2 = x2; wy2 = y2;
    cx = x1; cy = y1;
}

void textattr(int a) { attr = (unsigned char)a; }

void textmode(int m)
{
    union REGS r;
    r.h.ah = 0;
    r.h.al = (unsigned char)m;
    int86(0x10, &r, &r);
    mode = m;
    wx1 = 1; wy1 = 1; wx2 = 80; wy2 = 25;
    cx = 1; cy = 1;
    attr = 0x07;
}

void gettextinfo(struct text_info *ti)
{
    ti->winleft = (unsigned char)wx1;
    ti->wintop = (unsigned char)wy1;
    ti->winright = (unsigned char)wx2;
    ti->winbottom = (unsigned char)wy2;
    ti->attribute = attr;
    ti->normattr = 0x07;
    ti->currmode = (unsigned char)mode;
    ti->screenheight = 25;
    ti->screenwidth = 80;
}

void gettime(struct time *t)
{
    union REGS r;
    r.h.ah = 2;
    int86(0x1A, &r, &r);
    t->ti_hour = r.h.ch;
    t->ti_min = r.h.cl;
    t->ti_sec = r.h.dh;
    t->ti_hund = 0;
}

/* Save/restore a rectangle of the text screen as char,attr pairs. */
void gettext(int x1, int y1, int x2, int y2, void *buf)
{
    unsigned char *p = (unsigned char *)buf;
    int x, y;
    for (y = y1; y <= y2; y++)
        for (x = x1; x <= x2; x++) {
            unsigned off = (unsigned)(((y - 1) * 80 + (x - 1)) * 2);
            *p++ = scr[off];
            *p++ = scr[off + 1];
        }
}

void puttext(int x1, int y1, int x2, int y2, const void *buf)
{
    const unsigned char *p = (const unsigned char *)buf;
    int x, y;
    for (y = y1; y <= y2; y++)
        for (x = x1; x <= x2; x++) {
            unsigned off = (unsigned)(((y - 1) * 80 + (x - 1)) * 2);
            scr[off] = *p++;
            scr[off + 1] = *p++;
        }
}

/* INT 15h AH=86h waits CX:DX microseconds (AT+). clock() would quantise
   every delay to the 55 ms BIOS tick, which made the boot and the answer
   typewriter several times slower than the Turbo C build. */
void delay(unsigned ms)
{
    unsigned long us = (unsigned long)ms * 1000UL;
    union REGS r;
    if (ms == 0)
        return;
    r.h.ah = 0x86;
    r.x.cx = (unsigned)(us >> 16);
    r.x.dx = (unsigned)(us & 0xFFFFUL);
    int86(0x15, &r, &r);
}

void sound(unsigned hz)
{
    unsigned d = (unsigned)(1193180UL / (hz ? hz : 1));
    outp(0x43, 0xB6);
    outp(0x42, d & 0xFF);
    outp(0x42, (d >> 8) & 0xFF);
    outp(0x61, inp(0x61) | 3);
}

void nosound(void)
{
    outp(0x61, inp(0x61) & 0xFC);
}
