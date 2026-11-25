// The fixed donor truncates GDRST to eight bits before testing the engine
// domain. VECS uses bit 13. Match the complete domain, and do not enter native
// context replay while that domain still reports reset in progress.
#ifndef KERN_TGL_RESET_POLL_HPP
#define KERN_TGL_RESET_POLL_HPP
#include <stdint.h>
namespace TGLResetPoll {
// Linux v6.12 gen6_hw_domain_reset waits 2000 us for the selected GDRST mask.
// The read cap also bounds a stalled clock. The caller owns native forcewake
// and the recovery context; this helper neither resumes nor retires any job.
template<class IO> bool wait(IO &io,uint32_t mask) {
    const auto start=io.now();
    // A missing domain cannot certify a reset. All-ones MMIO is an
    // inaccessible read, not a scratch request or a completed engine.
    for(unsigned n=0;mask && n<201;++n) {
        const auto status=io.read(0x941c);
        if(status==UINT32_MAX)break;
        const auto scratch=io.read(0xcec4);
        if(scratch==UINT32_MAX)break;
        if(scratch&1) {
            io.write(0x4100,0xf0f0b1b1);
            io.write(0x4104,0xf0f0b2b2);
            io.write(0xcec4,scratch&~1U);
        }
        if(!(status&mask))return true;
        if(n==200 || io.now()-start>=2000000)break;
        io.delay();
    }
    // Undo native's reset-clock control before its existing false/forcewake
    // release exit. Never clear GDRST or manufacture completion on timeout.
    io.write(0x4a08,0x40000);
    return false;
}
}
#endif
