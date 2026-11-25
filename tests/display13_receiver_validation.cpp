// Receiver qualification is independent of native modeset and AUX ownership.
#include <cstring>
#include <cassert>
#include <cstdio>
#include <initializer_list>
#include "kern_display13_handoff.hpp"

using namespace Display13Handoff;
struct Sink {
    unsigned lanes=4, reads=0;
    uint8_t rate=10, revision=0x14;
    uint32_t fail=UINT32_MAX;
    bool allOnes=false, untrained=false, unaligned=false, compression=false;
    bool read(uint32_t reg,void *dest,size_t len) {
        ++reads;
        if(reg==fail)return false;
        auto b=static_cast<uint8_t *>(dest);
        memset(b,0,len);
        switch(reg) {
        case 0x100: assert(len==3); b[0]=rate;b[1]=uint8_t(lanes|0x80);break;
        case 0x202: assert(len==3); b[0]=untrained?0x76:0x77;b[1]=0x77;b[2]=unaligned?0:1;
            if(allOnes)memset(b,0xff,len);break;
        case 0: assert(len==1);b[0]=revision;break;
        case 0x60: assert(len==1);b[0]=1;break;
        case 0x160: assert(len==1);b[0]=compression?1:0;break;
        case 0x10a: assert(len==1);b[0]=1;break;
        case 0x115: assert(len==1);b[0]=1;break;
        case 0x12: assert(len==2);b[0]=0xbc;b[1]=0x34;break;
        default: assert(false);
        }
        return true;
    }
};
static bool qualify(Sink &s,unsigned lanes,bool panel,Receiver &out) {
    return receiver([&](uint32_t r,void *d,size_t n){return s.read(r,d,n);},lanes,panel,out);
}
static void empty(const Receiver &r) {
    assert(!r.symbolKHz && !r.lanes && !r.enhanced && !r.alternateReset);
}
int main() {
    for(unsigned n=0;n<32;++n) {
        Sink s;s.lanes=n;Receiver out{540000,4,true,true};
        const bool valid=n==1 || n==2 || n==4;
        assert(qualify(s,n,true,out)==valid);
        if(valid)assert(out.lanes==n && out.symbolKHz==270000 && out.enhanced && out.alternateReset);
        else {empty(out);assert(!s.reads);}
    }
    for(bool panel:{false,true}) {
        Sink s;Receiver out;
        assert(qualify(s,4,panel,out));
        for(unsigned reg:{0x100U,0x202U,0U,0x60U,0x160U,0x10aU}) {
            if(!panel && reg==0x10a)continue;
            s.fail=reg;out={540000,4,true,true};
            assert(!qualify(s,4,panel,out));empty(out);
        }
        s.fail=UINT32_MAX;
        for(unsigned fault=0;fault<5;++fault) {
            Sink bad;
            if(fault==0)bad.allOnes=true;
            if(fault==1)bad.untrained=true;
            if(fault==2)bad.unaligned=true;
            if(fault==3)bad.compression=true;
            if(fault==4)bad.revision=0xff;
            out={540000,4,true,true};
            assert(!qualify(bad,4,panel,out));empty(out);
        }
        s.rate=0;out={540000,4,true,true};
        assert(qualify(s,4,panel,out)==panel);
        if(panel)assert(out.symbolKHz==270000);else empty(out);
        if(panel)for(unsigned reg:{0x115U,0x12U}) {
            s.fail=reg;out={540000,4,true,true};
            assert(!qualify(s,4,panel,out));empty(out);
        }
    }
    puts("PASS Display13 receiver qualification, lane limits, failed AUX and stale state");
}
