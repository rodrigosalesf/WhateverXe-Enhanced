#include "kern_xelp_memory_layout.hpp"
#include <cassert>
#include <cstdio>
#include <initializer_list>
#include <vector>
using namespace XELPMemory;
struct ReservationIO {
 uint32_t hi=1,lo=0x95f00000,again=1,blocked=0;
 std::vector<uint32_t> reads;
 bool readable(uint32_t offset) const {return offset!=blocked;}
 uint32_t read(uint32_t offset) {
  reads.push_back(offset);
  assert(offset==0x1082C0 || offset==0x1082C4);
  return offset==0x1082C0 ? lo : reads.size()==1 ? hi : again;
 }
};
int main() {
 // 32-bit windows: exact end, subword windows, unaligned addresses and wrap boundary.
 for(uint64_t length=0;length<=32;++length)for(uint32_t offset=0;offset<=36;++offset) {
  const bool expected=offset%4==0 && uint64_t(offset)+4<=length;
  assert(register32(length,offset)==expected);
 }
 assert(register32(0x1000000,0xfffffc) && !register32(0x1000000,0xfffffd));
 assert(!register32(0x1000000,UINT32_MAX) && register32(UINT64_MAX,0xfffffffc));
 for(unsigned failure=0;failure<7;++failure) {
  ReservationIO io;
  if(failure==1)io.blocked=0x1082C0;
  if(failure==2)io.blocked=0x1082C4;
  if(failure==3)io.hi=io.again=UINT32_MAX;
  if(failure==4)io.lo=UINT32_MAX;
  if(failure==5)io.again=2;
  const auto raw=readReservation(io,failure!=6);
  assert(raw==(failure ? UINT64_MAX : 0x195f00000ULL));
  if(failure==1 || failure==2 || failure==6)assert(io.reads.empty());
  else assert((io.reads==std::vector<uint32_t>{0x1082C4,0x1082C0,0x1082C4}));
 }
 // After a valid sample, a failed refresh must revoke allocator admission.
 {auto m=decode(0x02C1,0x92000000,1);const auto raw=m.base+m.bytes-0x100000;
  for(auto bad:{uint64_t(0),uint64_t(UINT64_MAX),uint64_t(0x1FFFFFFFFULL)}) {
   assert(reservation(m,raw) && displayPool(m,0x4000000));
   assert(!reservation(m,bad) && !m.reservationKnown && !m.reservationRegister);
   assert(m.usable()==m.bytes-m.gttBytes && !displayPool(m,0x4000000));
   uint32_t recycle=4096;assert(!boundRecycle(m,m.base,recycle));
  }}
 uint32_t first,end;
 for(auto base:{0x4010000000ULL,0x80000000ULL,0x6000000000ULL}) {
  assert(mmioPages(base,base,0x1000000,0x1000000,first,end));
  assert(first==base/4096 && end==(base+0x1000000)/4096);
  assert(!mmioPages(base,base+4096,0x1000000,0x1000000,first,end));
  assert(!mmioPages(base,base,0x1000000,0x1000,first,end));
 }
 for(uint64_t base:std::initializer_list<uint64_t>{0,1,UINT64_MAX,0xFFFFFFFF000ULL})
  assert(!mmioPages(base,base,0x1000000,0x1000000,first,end));
 unsigned cases=0;
 for(unsigned gms=1;gms<255;++gms)for(unsigned ggms=1;ggms<4;++ggms) {
  const uint64_t bytes=gms<240 ? uint64_t(gms)*0x2000000 : uint64_t(gms-239)*0x400000;
  const auto m=decode((gms<<8)|(ggms<<6)|1,0x7A800001,0);
  const bool expected=bytes<(Aperture-0x195000) && bytes>(1ULL<<ggms)*0x100000 && bytes-(1ULL<<ggms)*0x100000>=0x1000000;
  assert(m.valid==expected);
  if(m.valid){assert(m.bytes==bytes && m.base==0x7A800000 && m.gttBytes==(1ULL<<ggms)*0x100000);assert(m.pte(4096)==0x7A801001 && m.pte(bytes)==0);++cases;}
 }
 for(unsigned ggc:{0x03C1u,0x02C1u,0xFEC1u,0x04C1u}) {
  auto m=decode(ggc,0x92000001,1);assert(m.valid && m.base==0x192000000ULL);
  assert(m.range(0,m.usable(),true) && !m.range(m.usable(),4096,true));
  assert(m.minimumReservation()==m.bytes+0x192000 && !m.range(UINT64_MAX-4095,8192));
 }
 assert(!decode(0x03C1,0,0).valid && !decode(0xFFFF,0x7A800001,0).valid && !decode(0x03C1,UINT32_MAX,0).valid);
 assert(!decode(0x03C1,0xFFF00000,0x7F).valid && !decode(0x03C1,0x7A800001,0x80).valid);
 assert(!decode(0xFFC1,0x7A800001,0).valid && !decode(0x0301,0x7A800001,0).valid);
 auto a=decode(0x03C1,0x7A800001,0),b=decode(0x03C1,0x7A800000,0);assert(same(a,b));
 b.base+=0x100000;assert(!same(a,b));
 unsigned reservations=0;
 for(unsigned ggc:{0x02C1u,0x03C1u,0xFEC1u,0x04C1u})for(unsigned size=0;size<4;++size)for(unsigned gap:{0u,0x200000u}) {
  auto m=decode(ggc,0x92000000,1);const uint64_t reservedSize=0x100000ULL<<size;
  const auto raw=(m.base+m.bytes-reservedSize-gap)|(uint64_t(size)<<7)|1;
  assert(reservation(m,raw) && m.usable()==m.bytes-reservedSize-gap);
  assert(m.gttBytes==0x800000); // GGMS is unrelated to DSM reservation size.
  const auto pool=displayPool(m,0x4000000);
  assert(pool && pool<=m.usable()-4096 && !(pool&4095));
  assert(pool==(m.usable()-4096<0x4000000 ? m.usable()-4096 : 0x4000000));
  assert(displayPool(m,0x4000000,0x3C00000)<=pool);
  assert(!displayPool(m,0x4000000,0x4001000) && !displayPool(m,0x4000000,17));
  uint32_t recycle=uint32_t(m.bytes-reservedSize-pool);
  assert(boundRecycle(m,m.base+pool,recycle) && recycle==m.usable()-pool);
  assert(!boundRecycle(m,m.base-4096,recycle));++reservations;
 }
 auto m=decode(0xFEC1,0x7A800000,0);assert(!displayPool(m,0x4000000));
 assert(!reservation(m,0) && !reservation(m,UINT64_MAX));
 assert(!reservation(m,(m.base+m.bytes+0x100000)|0x180));
 assert(!reservation(m,(m.base+m.bytes-0x100000)|0x180));
 assert(reservation(m,m.base+m.bytes));assert(m.usable()==m.bytes);
 assert(displayPool(m,0x4000000)==m.bytes-0x100000-4096);
 printf("PASS %u admitted GMS/GGMS profiles; 60/64/96/128MiB relocated/64-bit base; exact ranges, overflow and changed layout refusal\n",cases);
 printf("PASS %u DSM reservation/pool/recycle cases; independent 1/2/4/8MiB reservations, firmware gap, 60MiB cap and no-reservation\n",reservations);
}
