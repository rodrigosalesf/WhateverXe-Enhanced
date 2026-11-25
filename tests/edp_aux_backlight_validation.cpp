#include "kern_edp_aux_backlight.hpp"
#include <cassert>
#include <cstdio>
#include <initializer_list>
#include <map>
using namespace EDPAuxBacklight;
struct IO {
 std::map<uint32_t,uint8_t> regs{{0x700,3},{0x701,5},{0x702,6},{0x724,12},{0x720,0x82},{0x721,0x28},{0x722,0},{0x723,0}};
 unsigned reads=0,writes=0;
 uint32_t fail=UINT32_MAX;
 bool read(uint32_t reg,uint8_t *d,unsigned n) {
  ++reads;if(reg==fail)return false;
  for(unsigned i=0;i<n;++i)d[i]=regs.at(reg+i);
  return true;
 }
 bool write(uint32_t reg,const uint8_t *d,unsigned n) {
  ++writes;for(unsigned i=0;i<n;++i)regs[reg+i]=d[i];return true;
 }
};
static void empty(const Caps &c) {assert(!c.set && !c.enable && !c.wide && !c.maximum);}
int main() {
 for(bool wide:{false,true})for(unsigned bits=0;bits<32;++bits) {
  IO io;io.regs[0x702]=wide?6:2;io.regs[0x724]=bits;
  Caps c{true,true,true,4095};
  const bool valid=bits>0 && bits<=(wide?16U:8U);
  assert(probe(io,c)==valid);
  if(!valid){empty(c);assert(!io.writes);continue;}
  assert(c.set && c.enable && c.wide==wide && c.maximum==(1U<<bits)-1);
  for(unsigned b:{0U,1U,32768U,65535U}) {
   assert(apply(io,c,Action::Level,b));
   const auto level=uint32_t(uint64_t(b)*c.maximum/65535);
   assert(io.regs[0x722]==(wide?level>>8:level));
   if(wide)assert(io.regs[0x723]==uint8_t(level));
   assert(io.regs[0x721]==0x2a);
  }
  assert(apply(io,c,Action::Enable,65535) && io.regs[0x720]==0x83);
  assert(apply(io,c,Action::Disable,0) && io.regs[0x720]==0x82);
 }
 for(unsigned fault=0;fault<5;++fault) {
  IO io;Caps c;assert(probe(io,c));
  if(fault==0)io.fail=0x700;
  if(fault==1)io.fail=0x724;
  if(fault==2)io.regs[0x701]=0;
  if(fault==3)io.regs[0x702]=0;
  if(fault==4)io.regs[0x700]=io.regs[0x701]=io.regs[0x702]=0xff;
  assert(!probe(io,c));empty(c);assert(!io.writes);
 }
 for(const Caps c:{Caps{true,true,false,0},Caps{true,true,false,256},Caps{true,true,true,65536},Caps{true,true,true,100},Caps{false,true,false,255}}) {
  IO io;for(auto action:{Action::Level,Action::Enable,Action::Disable})assert(!apply(io,c,action,100));
  assert(!io.reads && !io.writes);
 }
 IO io;Caps c;assert(probe(io,c));
 const auto before=io.reads;
 assert(!apply(io,c,static_cast<Action>(99),100));assert(!apply(io,c,Action::Level,65536));
 assert(io.reads==before && !io.writes);
 io.regs[0x702]=1;assert(probe(io,c));assert(!c.set && c.enable && !c.maximum);
 const auto old=io.regs[0x722];assert(apply(io,c,Action::Level,32768));assert(io.regs[0x722]==old && io.regs[0x721]==0x28);
 puts("PASS AUX backlight capability validation, level mapping, PWM coexistence and rejected inputs");
}
