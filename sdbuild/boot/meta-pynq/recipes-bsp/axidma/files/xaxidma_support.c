#include <stdarg.h>

#include "xil_assert.h"
#include "xil_printf.h"
#include "xil_types.h"

u32 Xil_AssertStatus = XIL_ASSERT_NONE;
s32 Xil_AssertWait = 0;

void Xil_Assert(const char8 *File, s32 Line)
{
    (void)File;
    (void)Line;
}

void XNullHandler(void *NullParameter)
{
    (void)NullParameter;
}

void Xil_AssertSetCallback(Xil_AssertCallback Routine)
{
    (void)Routine;
}

void outbyte(char c)
{
    (void)c;
}

char inbyte(void)
{
    return 0;
}

void xil_printf(const char8 *ctrl1, ...)
{
    (void)ctrl1;
}

void xil_vprintf(const char8 *ctrl1, va_list argp)
{
    (void)ctrl1;
    (void)argp;
}

void print(const char8 *ptr)
{
    (void)ptr;
}

void Xil_DCacheEnable(void) {}
void Xil_DCacheDisable(void) {}
void Xil_DCacheInvalidate(void) {}
void Xil_DCacheFlush(void) {}
void Xil_ICacheEnable(void) {}
void Xil_ICacheDisable(void) {}
void Xil_ICacheInvalidate(void) {}

void Xil_DCacheInvalidateRange(INTPTR adr, INTPTR len)
{
    (void)adr;
    (void)len;
}

void Xil_DCacheInvalidateLine(INTPTR adr)
{
    (void)adr;
}

void Xil_DCacheFlushLine(INTPTR adr)
{
    (void)adr;
}

void Xil_ICacheInvalidateRange(INTPTR adr, INTPTR len)
{
    (void)adr;
    (void)len;
}

void Xil_ICacheInvalidateLine(INTPTR adr)
{
    (void)adr;
}

void Xil_ConfigureL1Prefetch(u8 num)
{
    (void)num;
}
