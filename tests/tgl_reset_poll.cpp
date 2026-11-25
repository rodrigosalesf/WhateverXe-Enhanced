// Host-only tests: no hardware access or native donor required.
#include "kern_tgl_reset_poll.hpp"
#include <cassert>
#include <cstdio>
#include <initializer_list>
#include <vector>
struct Write {uint32_t reg,value;};
struct IO {
    uint32_t mask=4,peer=0x40000000,scratch=0x21;
    unsigned ack=0,delays=0,statusReads=0,scratchReads=0;
    unsigned badStatus=0,badScratch=0;
    uint64_t ticks=0;
    bool stalled=false;
    std::vector<Write> writes;
    uint64_t now(){return ticks;}
    uint32_t read(uint32_t reg){
        if(reg==0x941c){
            ++statusReads;
            if(statusReads==badStatus)return UINT32_MAX;
            return peer|((ack && statusReads>=ack)?0:mask);
        }
        assert(reg==0xcec4);++scratchReads;
        return scratchReads==badScratch?UINT32_MAX:scratch;
    }
    void write(uint32_t reg,uint32_t value){
        writes.push_back({reg,value});
        if(reg==0xcec4)scratch=value;
    }
    void delay(){++delays;if(!stalled)ticks+=10000;}
};
static void cleanup(const IO &io){
    assert(!io.writes.empty());
    const auto last=io.writes.back();
    assert(last.reg==0x4a08 && last.value==0x40000);
}
int main(){
    for(uint32_t mask:{4U,0x20U,0x80U,0x2000U}){
        for(unsigned ack:{1U,2U,201U}){
            IO io;io.mask=mask;io.ack=ack;
            assert(TGLResetPoll::wait(io,mask));
            assert(io.statusReads==ack && io.delays==ack-1);
            assert(io.writes.size()==3 && io.writes[0].reg==0x4100 &&
                io.writes[1].reg==0x4104 && io.writes[2].reg==0xcec4 &&
                io.writes[2].value==0x20);
        }
        for(bool stalled:{false,true}){
            IO io;io.mask=mask;io.stalled=stalled;
            assert(!TGLResetPoll::wait(io,mask));
            assert(io.delays==200 && io.statusReads==201);
            assert(io.writes.size()==4);cleanup(io);
        }
        for(bool statusFault:{false,true})for(unsigned at:{1U,2U}){
            IO io;io.mask=mask;io.ack=2;
            if(statusFault)io.badStatus=at;else io.badScratch=at;
            assert(!TGLResetPoll::wait(io,mask));
            assert(io.statusReads==at && io.delays==at-1);
            assert(io.scratchReads==at-unsigned(statusFault));
            assert(io.writes.size()==(at==1?1U:4U));cleanup(io);
        }
    }
    IO zero;assert(!TGLResetPoll::wait(zero,0));
    assert(!zero.statusReads && !zero.scratchReads && !zero.delays);
    assert(zero.writes.size()==1);cleanup(zero);
    puts("PASS reset domain acknowledgement, invalid MMIO, zero mask and bounded polling");
}
