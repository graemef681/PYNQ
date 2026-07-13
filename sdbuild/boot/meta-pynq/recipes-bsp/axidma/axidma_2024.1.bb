SUMMARY = "AXI DMA embeddedsw driver for PYNQ.remote"
SECTION = "PETALINUX/libs"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${WORKDIR}/git/license.txt;md5=0dcabd3719e5ac33f7c03f0d77d473f2"

SRC_URI = "git://github.com/Xilinx/embeddedsw.git;protocol=https;branch=xlnx_rel_v2024.1 \
           file://bspconfig.h \
           file://xaxidma_support.c"
SRCREV = "b173d246826f662b9a98215d8f39e93d39d699b4"

S = "${WORKDIR}/git/XilinxProcessorIPLib/drivers/axidma/src"

AXIDMA_STANDALONE_COMMON = "${WORKDIR}/git/lib/bsp/standalone/src/common"
AXIDMA_STANDALONE_COMMON_GCC = "${WORKDIR}/git/lib/bsp/standalone/src/arm/common/gcc"
# PYNQ.remote only targets 64-bit ZynqMP/RFSoC boards, so stage the
# AArch64 standalone headers that XAxiDma depends on.
AXIDMA_STANDALONE_ARCH_DIR = "${WORKDIR}/git/lib/bsp/standalone/src/arm/ARMv8/64bit"
AXIDMA_STANDALONE_ARCH_GCC_DIR = "${WORKDIR}/git/lib/bsp/standalone/src/arm/ARMv8/64bit/gcc"
AXIDMA_ARCH_REG_HEADER = "xreg_cortexa53.h"

CFLAGS:append = " -ffunction-sections -fdata-sections -DSDT -DNDEBUG"

do_compile() {
    incs="-I${S} \
          -I${WORKDIR} \
          -I${AXIDMA_STANDALONE_COMMON} \
          -I${AXIDMA_STANDALONE_COMMON_GCC} \
          -I${AXIDMA_STANDALONE_ARCH_DIR} \
          -I${AXIDMA_STANDALONE_ARCH_GCC_DIR}"

    ${CC} ${CFLAGS} ${CPPFLAGS} ${incs} -c ${S}/xaxidma.c -o xaxidma.o
    ${CC} ${CFLAGS} ${CPPFLAGS} ${incs} -c ${S}/xaxidma_bd.c -o xaxidma_bd.o
    ${CC} ${CFLAGS} ${CPPFLAGS} ${incs} -c ${S}/xaxidma_bdring.c -o xaxidma_bdring.o
    ${CC} ${CFLAGS} ${CPPFLAGS} ${incs} -c ${WORKDIR}/xaxidma_support.c -o xaxidma_support.o
    ${AR} rcs libaxidma.a xaxidma.o xaxidma_bd.o xaxidma_bdring.o xaxidma_support.o
}

do_install() {
    install -d ${D}${libdir}
    install -d ${D}${includedir}
    install -d ${D}${includedir}/xaxidma-standalone

    install -m 0644 libaxidma.a ${D}${libdir}/libaxidma.a
    install -m 0644 \
        ${S}/xaxidma.h \
        ${S}/xaxidma_bd.h \
        ${S}/xaxidma_bdring.h \
        ${S}/xaxidma_hw.h \
        ${S}/xaxidma_porting_guide.h \
        ${D}${includedir}/

    # Keep XAxiDma's standalone support headers out of the global include
    # namespace so they do not collide with Linux-side RFDC headers.
    install -m 0644 \
        ${AXIDMA_STANDALONE_COMMON}/xbasic_types.h \
        ${AXIDMA_STANDALONE_COMMON}/xdebug.h \
        ${AXIDMA_STANDALONE_COMMON}/xil_assert.h \
        ${AXIDMA_STANDALONE_COMMON}/xil_io.h \
        ${AXIDMA_STANDALONE_COMMON}/xil_printf.h \
        ${AXIDMA_STANDALONE_COMMON}/xil_types.h \
        ${AXIDMA_STANDALONE_COMMON}/xstatus.h \
        ${WORKDIR}/bspconfig.h \
        ${D}${includedir}/xaxidma-standalone/

    install -m 0644 \
        ${AXIDMA_STANDALONE_ARCH_DIR}/xil_cache.h \
        ${AXIDMA_STANDALONE_ARCH_DIR}/xpseudo_asm.h \
        ${AXIDMA_STANDALONE_ARCH_DIR}/${AXIDMA_ARCH_REG_HEADER} \
        ${AXIDMA_STANDALONE_COMMON_GCC}/xpseudo_asm_gcc.h \
        ${D}${includedir}/xaxidma-standalone/
}
