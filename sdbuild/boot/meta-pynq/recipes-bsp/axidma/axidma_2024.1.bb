SUMMARY = "AXI DMA embeddedsw driver for PYNQ.remote"
SECTION = "PETALINUX/libs"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${WORKDIR}/git/license.txt;md5=0dcabd3719e5ac33f7c03f0d77d473f2"

DEPENDS = "standalone"

SRC_URI = "git://github.com/Xilinx/embeddedsw.git;protocol=https;branch=xlnx_rel_v2024.1"
SRCREV = "b173d246826f662b9a98215d8f39e93d39d699b4"

S = "${WORKDIR}/git/XilinxProcessorIPLib/drivers/axidma/src"

CFLAGS:append = " -ffunction-sections -fdata-sections"

do_compile() {
    ${CC} ${CFLAGS} ${CPPFLAGS} -I${S} -I${STAGING_INCDIR} -c ${S}/xaxidma.c -o xaxidma.o
    ${CC} ${CFLAGS} ${CPPFLAGS} -I${S} -I${STAGING_INCDIR} -c ${S}/xaxidma_bd.c -o xaxidma_bd.o
    ${CC} ${CFLAGS} ${CPPFLAGS} -I${S} -I${STAGING_INCDIR} -c ${S}/xaxidma_bdring.c -o xaxidma_bdring.o
    ${AR} rcs libaxidma.a xaxidma.o xaxidma_bd.o xaxidma_bdring.o
}

do_install() {
    install -d ${D}${libdir}
    install -d ${D}${includedir}

    install -m 0644 libaxidma.a ${D}${libdir}/libaxidma.a
    install -m 0644 \
        ${S}/xaxidma.h \
        ${S}/xaxidma_bd.h \
        ${S}/xaxidma_bdring.h \
        ${S}/xaxidma_hw.h \
        ${S}/xaxidma_porting_guide.h \
        ${D}${includedir}/
}
