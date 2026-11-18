/* tc_compat.h -- Turbo C 2.0 text-mode conio for OpenWatcom (16-bit DOS).
 *
 * TINY.C uses the Turbo C text API (window/gotoxy/textattr/clrscr/putch/
 * cputs/cprintf/wherex/wherey/textmode/gettextinfo/sound/delay). OpenWatcom
 * has none of it, so this file provides the whole set on top of the VGA text
 * buffer and INT 10h. It is only used by the DOS UI build.
 */
#ifndef TC_COMPAT_H
#define TC_COMPAT_H

/* Turbo C text modes */
#define BW40 0
#define C40  1
#define BW80 2
#define C80  3
#define MONO 7

struct time {                  /* Turbo C's DOS clock struct */
    unsigned char ti_min, ti_hour, ti_hund, ti_sec;
};

struct text_info {
    unsigned char winleft, wintop, winright, winbottom;
    unsigned char attribute, normattr;
    unsigned char currmode;
    unsigned char screenheight, screenwidth;
};

void gettextinfo(struct text_info *ti);
void gotoxy(int x, int y);
int wherex(void);
int wherey(void);
void clrscr(void);
void window(int x1, int y1, int x2, int y2);
void textattr(int attr);
void textmode(int mode);
int putch(int c);
int cputs(const char *s);
int cprintf(const char *fmt, ...);
void gettime(struct time *t);
void gettext(int x1, int y1, int x2, int y2, void *buf);
void puttext(int x1, int y1, int x2, int y2, const void *buf);
void delay(unsigned ms);
void sound(unsigned hz);
void nosound(void);

#endif
